import asyncio
import json
import logging
import uuid
import re
import redis.asyncio as async_redis
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from fastapi import FastAPI, Depends, HTTPException, Request, Response, WebSocket, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from services.chatbot import config, database
from services.chatbot.llm import LLMProviderClient

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ChatbotService")

app = FastAPI(
    title="LLM Telemetry Chatbot API",
    description="Operational Chatbot and Observability backend.",
    version="1.0.0"
)

# Enable CORS for the React Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# DB creation on startup
database.Base.metadata.create_all(bind=database.engine)

# Pydantic schemas for REST API
class ConversationCreate(BaseModel):
    title: Optional[str] = None

class ChatRequest(BaseModel):
    prompt: str
    provider: str
    model: str

class ConversationResponse(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str

class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    created_at: str

class ConversationDeleteResponse(BaseModel):
    status: str
    message: str

class ProviderStats(BaseModel):
    calls: int
    errors: int
    success_rate: float

class ModelStats(BaseModel):
    calls: int
    avg_latency_ms: int

class MetricsResponse(BaseModel):
    total_calls: int
    success_rate: float
    avg_latency_ms: int
    total_tokens: int
    avg_throughput_tps: float
    error_rate: float
    provider_breakdown: Dict[str, ProviderStats]
    model_breakdown: Dict[str, ModelStats]

class TimeseriesPointResponse(BaseModel):
    id: str
    timestamp: str
    latency_ms: int
    tokens_total: int
    tokens_prompt: int
    tokens_completion: int
    throughput_tps: float
    status: str
    model: str
    provider: str

class TelemetryLogResponse(BaseModel):
    id: str
    conversation_id: Optional[str] = None
    message_id: Optional[str] = None
    provider: str
    model: str
    status: str
    latency_ms: int
    tokens_prompt: int
    tokens_completion: int
    tokens_total: int
    error_message: Optional[str] = None
    pii_redacted: bool
    metadata: Dict[str, Any]
    timestamp: str

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "chatbot-backend"}

# --- Conversational APIs ---

@app.get("/api/conversations", response_model=List[ConversationResponse])
def list_conversations(db: Session = Depends(database.get_db)):
    """Lists conversations."""
    conversations = database.get_conversations(db)
    return [
        {
            "id": str(c.id),
            "title": c.title,
            "created_at": c.created_at.isoformat(),
            "updated_at": c.updated_at.isoformat()
        }
        for c in conversations
    ]

@app.post("/api/conversations", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
def create_new_conversation(payload: ConversationCreate, db: Session = Depends(database.get_db)):
    """Creates a new conversation."""
    title = payload.title or "New Conversation"
    conv = database.create_conversation(db, title)
    return {
        "id": str(conv.id),
        "title": conv.title,
        "created_at": conv.created_at.isoformat(),
        "updated_at": conv.updated_at.isoformat()
    }

@app.get("/api/conversations/{conv_id}/messages", response_model=List[MessageResponse])
def get_messages(conv_id: str, db: Session = Depends(database.get_db)):
    """Resumes a conversation by listing its messages."""
    messages = database.get_conversation_messages(db, conv_id)
    return [
        {
            "id": str(m.id),
            "role": m.role,
            "content": m.content,
            "created_at": m.created_at.isoformat()
        }
        for m in messages
    ]

@app.delete("/api/conversations/{conv_id}", response_model=ConversationDeleteResponse)
def cancel_and_delete_conversation(conv_id: str, db: Session = Depends(database.get_db)):
    """Cancels and deletes a conversation and its logs reference."""
    success = database.delete_conversation(db, conv_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found."
        )
    return {"status": "deleted", "message": "Conversation successfully canceled and removed."}
def retrieve_rag_context(db: Session, conv_id: str, prompt: str, exclude_message_ids: List[Any]) -> List[str]:
    """
    Zero-Dependency RAG Search: Performs full-text keyword retrieval over
    past historical messages in the conversation (excluding active sliding window)
    to pull relevant facts.
    """
    # 1. Extract keywords from the prompt (words > 4 chars)
    words = re.findall(r'\b\w{4,}\b', prompt.lower())
    if not words:
        return []
    
    # 2. Query DB for matching assistant messages containing these keywords
    from services.chatbot.database import Message
    from sqlalchemy import or_
    
    conditions = [Message.content.ilike(f"%{word}%") for word in words]
    
    query = db.query(Message).filter(
        Message.conversation_id == conv_id,
        Message.role == "assistant",
        ~Message.id.in_(exclude_message_ids)
    )
    
    if conditions:
        query = query.filter(or_(*conditions))
        
    matches = query.order_by(Message.created_at.desc()).limit(3).all()
    
    context_snippets = []
    for msg in matches:
        # Pull a clean snippet of the past assistant message
        context_snippets.append(msg.content[:200] + "..." if len(msg.content) > 200 else msg.content)
        
    return context_snippets


@app.post("/api/conversations/{conv_id}/chat")
async def chat_stream(
    conv_id: str,
    payload: ChatRequest,
    request: Request,
    db: Session = Depends(database.get_db)
):
    """
    Accepts user prompts, streams back assistant completion chunks via SSE,
    captures client disconnection/cancel requests in real-time,
    and stores prompt/response details persistently.
    """
    # 1. Fetch conversation history for multi-turn context
    history_messages = database.get_conversation_messages(db, conv_id)
    
    # 2. Store the User's prompt in PostgreSQL
    database.create_message(db, conv_id, "user", payload.prompt)

    # Prepare Assistant message placeholder ID
    assistant_message_id = str(uuid.uuid4())

    # Pre-create Assistant message placeholder to prevent telemetry worker race condition violations
    database.create_message(db, conv_id, "assistant", "", message_id=assistant_message_id)

    # Reconstruct standard chat structure using a sliding window (last 20 messages)
    # This guarantees a cost cap, GPU prompt caching optimization, and low latency.
    CONTEXT_WINDOW_LIMIT = 20
    sliding_window = history_messages[-CONTEXT_WINDOW_LIMIT:] if len(history_messages) > CONTEXT_WINDOW_LIMIT else history_messages

    # Extract IDs of active sliding window messages to avoid duplicating facts in RAG
    sliding_window_ids = [msg.id for msg in sliding_window]

    # Perform Zero-Dependency Factual RAG search over older historical logs
    rag_context = retrieve_rag_context(db, conv_id, payload.prompt, sliding_window_ids)

    messages_payload = []

    # If relevant facts exist outside the active window, inject them as a system instruction at the very top
    if rag_context:
        rag_facts = "\n".join([f"- {fact}" for fact in rag_context])
        system_instruction = (
            "You are a helpful assistant. Use the following relevant facts retrieved "
            f"from the user's historical conversation memory if applicable:\n{rag_facts}\n"
            "Note: These facts are from earlier in the chat outside the immediate active window."
        )
        messages_payload.append({"role": "system", "content": system_instruction})

    for msg in sliding_window:
        messages_payload.append({"role": msg.role, "content": msg.content})
    messages_payload.append({"role": "user", "content": payload.prompt})

    async def event_generator():
        accumulated_text = []
        interrupted = False

        try:
            # Stream from provider
            stream = LLMProviderClient.stream_chat(
                conversation_id=conv_id,
                message_id=assistant_message_id,
                provider=payload.provider,
                model=payload.model,
                messages=messages_payload
            )

            async for chunk in stream:
                # Core Feature: Client Disconnect / Cancel Detection
                if await request.is_disconnected():
                    logger.info(f"Client disconnected / canceled streaming chat for conversation: {conv_id}")
                    interrupted = True
                    break

                accumulated_text.append(chunk)
                
                # Send chunk to client inside Server-Sent Event (SSE) structure
                yield f"data: {json.dumps({'content': chunk, 'message_id': assistant_message_id})}\n\n"

        except Exception as e:
            logger.error(f"Error yielding stream chunks: {e}")
            interrupted = True
            yield f"data: {json.dumps({'content': f' [Error: {str(e)}]', 'error': True})}\n\n"

        finally:
            # 3. Store Assistant's response (or what was successfully generated before cancel)
            full_response = "".join(accumulated_text).strip()
            if interrupted:
                full_response += " [Canceled by User]"

            # Update the Assistant message content in PostgreSQL
            # To operate in synchronous SQLAlchemy inside async generator, open a fresh session
            with database.SessionLocal() as fresh_db:
                msg = fresh_db.query(database.Message).filter(database.Message.id == assistant_message_id).first()
                if msg:
                    msg.content = full_response or "[No Response]"
                    fresh_db.commit()
                    logger.info("Updated streamed assistant message content in database.")

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# --- Telemetry Observability APIs ---

@app.get("/api/analytics/metrics", response_model=MetricsResponse)
def get_telemetry_metrics(db: Session = Depends(database.get_db)):
    """
    Computes key performance metrics across all LLM inference logs.
    """
    logs_query = db.query(database.InferenceLog)
    total_calls = logs_query.count()

    if total_calls == 0:
        return {
            "total_calls": 0,
            "success_rate": 0.0,
            "avg_latency_ms": 0,
            "total_tokens": 0,
            "avg_throughput_tps": 0.0,
            "error_rate": 0.0,
            "provider_breakdown": {},
            "model_breakdown": {}
        }

    success_calls = logs_query.filter(database.InferenceLog.status == "success").count()
    error_calls = logs_query.filter(database.InferenceLog.status == "error").count()

    # Latency Average
    avg_latency = db.query(func.avg(database.InferenceLog.latency_ms)).scalar() or 0
    
    # Token Totals
    total_tokens = db.query(func.sum(database.InferenceLog.tokens_total)).scalar() or 0

    # Calculate average throughput (tokens per second) where latency > 0
    tps_query = db.query(
        func.avg(
            database.InferenceLog.tokens_total / (database.InferenceLog.latency_ms / 1000.0)
        )
    ).filter(
        database.InferenceLog.latency_ms > 0,
        database.InferenceLog.status == "success"
    ).scalar() or 0.0

    # Provider breakdown
    provider_data = db.query(
        database.InferenceLog.provider,
        func.count(database.InferenceLog.id),
        func.count(func.nullif(database.InferenceLog.status, "success")) # counts error rows
    ).group_by(database.InferenceLog.provider).all()

    provider_breakdown = {}
    for prov, count, err_count in provider_data:
        provider_breakdown[prov] = {
            "calls": count,
            "errors": err_count,
            "success_rate": round(((count - err_count) / count) * 100.0, 1) if count > 0 else 100.0
        }

    # Model breakdown
    model_data = db.query(
        database.InferenceLog.model,
        func.count(database.InferenceLog.id),
        func.avg(database.InferenceLog.latency_ms)
    ).group_by(database.InferenceLog.model).all()

    model_breakdown = {}
    for mdl, count, avg_lat in model_data:
        model_breakdown[mdl] = {
            "calls": count,
            "avg_latency_ms": int(avg_lat)
        }

    return {
        "total_calls": total_calls,
        "success_rate": round((success_calls / total_calls) * 100.0, 1),
        "avg_latency_ms": int(avg_latency),
        "total_tokens": total_tokens,
        "avg_throughput_tps": round(tps_query, 1),
        "error_rate": round((error_calls / total_calls) * 100.0, 1),
        "provider_breakdown": provider_breakdown,
        "model_breakdown": model_breakdown
    }


@app.get("/api/analytics/timeseries", response_model=List[TimeseriesPointResponse])
def get_telemetry_timeseries(db: Session = Depends(database.get_db)):
    """
    Retrieves chronological telemetry data points to feed the UI line charts.
    """
    # Fetch recent 100 logs to display timeseries trends
    logs = db.query(database.InferenceLog).order_by(database.InferenceLog.timestamp.desc()).limit(100).all()
    logs.reverse() # chronologically ascending

    points = []
    for log in logs:
        # Avoid zero division
        tps = round(log.tokens_total / (log.latency_ms / 1000.0), 1) if log.latency_ms > 0 and log.status == "success" else 0.0
        points.append({
            "id": str(log.id),
            "timestamp": log.timestamp.isoformat(),
            "latency_ms": log.latency_ms,
            "tokens_total": log.tokens_total,
            "tokens_prompt": log.tokens_prompt,
            "tokens_completion": log.tokens_completion,
            "throughput_tps": tps,
            "status": log.status,
            "model": log.model,
            "provider": log.provider
        })
    return points


@app.get("/api/analytics/logs", response_model=List[TelemetryLogResponse])
def get_recent_logs(db: Session = Depends(database.get_db)):
    """
    Lists the latest 50 raw telemetry log events.
    """
    logs = db.query(database.InferenceLog).order_by(database.InferenceLog.timestamp.desc()).limit(50).all()
    return [
        {
            "id": str(log.id),
            "conversation_id": str(log.conversation_id) if log.conversation_id else None,
            "message_id": str(log.message_id) if log.message_id else None,
            "provider": log.provider,
            "model": log.model,
            "status": log.status,
            "latency_ms": log.latency_ms,
            "tokens_prompt": log.tokens_prompt,
            "tokens_completion": log.tokens_completion,
            "tokens_total": log.tokens_total,
            "error_message": log.error_message,
            "pii_redacted": log.pii_redacted,
            "metadata": log.inference_metadata,
            "timestamp": log.timestamp.isoformat()
        }
        for log in logs
    ]


# Set of active WebSocket connections
active_websockets = set()

async def redis_pubsub_listener():
    """
    Single background task that listens to Redis Pub/Sub channel
    and broadcasts incoming telemetry messages to all active WebSockets.
    """
    logger.info("Starting Redis Pub/Sub background listener...")
    r_client = None
    pubsub = None
    while True:
        try:
            r_client = async_redis.Redis(
                host=config.REDIS_HOST,
                port=config.REDIS_PORT,
                password=config.REDIS_PASSWORD,
                decode_responses=True
            )
            pubsub = r_client.pubsub()
            await pubsub.subscribe(config.REDIS_PUBSUB_CHANNEL)
            logger.info(f"Redis Pub/Sub background listener subscribed to {config.REDIS_PUBSUB_CHANNEL}")

            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message.get("data"):
                    payload = message["data"]
                    # Fan out to all active sockets concurrently
                    if active_websockets:
                        disconnected_sockets = []
                        for ws in list(active_websockets):
                            try:
                                await ws.send_text(payload)
                            except Exception:
                                disconnected_sockets.append(ws)
                        for ws in disconnected_sockets:
                            active_websockets.discard(ws)
                await asyncio.sleep(0.01)
        except Exception as e:
            logger.error(f"Error in Redis Pub/Sub listener: {e}. Reconnecting in 5 seconds...")
            await asyncio.sleep(5)
        finally:
            try:
                if pubsub:
                    await pubsub.close()
                if r_client:
                    await r_client.close()
            except Exception:
                pass

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(redis_pubsub_listener())

# --- Live Telemetry WebSocket Server ---

@app.websocket("/api/ws/analytics")
async def websocket_analytics(websocket: WebSocket):
    """
    Relays processed telemetry logs from single background listener to the frontend.
    """
    await websocket.accept()
    active_websockets.add(websocket)
    logger.info(f"WebSocket analytics connection established. Total connections: {len(active_websockets)}")

    try:
        while True:
            # Block to keep connection open and detect client disconnect
            await websocket.receive_text()
    except Exception:
        pass
    finally:
        active_websockets.discard(websocket)
        logger.info(f"WebSocket analytics client disconnected. Total connections: {len(active_websockets)}")
