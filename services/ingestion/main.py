import json
import logging
from typing import Optional
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
import redis
import aio_pika

from services.ingestion import config
from sdk.schemas import InferenceLogPayload

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("IngestionService")

app = FastAPI(
    title="Inference Telemetry Ingestion Pipeline API",
    description="High-performance ingestion receiver for LLM telemetry with RabbitMQ.",
    version="1.0.0"
)

# Enable CORS for ingestion flexibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Connect to Redis (used for WebSocket pubsub broadcasting)
try:
    redis_client = redis.Redis(
        host=config.REDIS_HOST,
        port=config.REDIS_PORT,
        password=config.REDIS_PASSWORD,
        decode_responses=True
    )
    # Ping Redis to test connection
    redis_client.ping()
    logger.info("Connected to Redis successfully.")
except Exception as e:
    logger.error(f"Failed to connect to Redis on startup: {e}")
    redis_client = None

# Connect to RabbitMQ (used for durable log queue ingestion)
rabbitmq_connection: Optional[aio_pika.RobustConnection] = None
rabbitmq_channel: Optional[aio_pika.RobustChannel] = None

@app.on_event("startup")
async def startup_event():
    global rabbitmq_connection, rabbitmq_channel
    try:
        logger.info(f"Connecting to RabbitMQ at {config.RABBITMQ_HOST}:{config.RABBITMQ_PORT}...")
        # Create robust connection with auto-reconnection
        rabbitmq_connection = await aio_pika.connect_robust(
            host=config.RABBITMQ_HOST,
            port=config.RABBITMQ_PORT,
            login=config.RABBITMQ_USER,
            password=config.RABBITMQ_PASSWORD,
            timeout=10
        )
        rabbitmq_channel = await rabbitmq_connection.channel()
        
        # Declare durable queue for durability/persistence
        await rabbitmq_channel.declare_queue(
            config.RABBITMQ_QUEUE_NAME,
            durable=True
        )
        logger.info("Connected to RabbitMQ successfully and declared durable queue.")
    except Exception as e:
        logger.error(f"Failed to connect to RabbitMQ on startup: {e}")
        rabbitmq_connection = None
        rabbitmq_channel = None

@app.on_event("shutdown")
async def shutdown_event():
    global rabbitmq_connection
    if rabbitmq_connection and not rabbitmq_connection.is_closed:
        logger.info("Closing RabbitMQ connection...")
        await rabbitmq_connection.close()
        logger.info("RabbitMQ connection closed.")

@app.get("/health")
async def health_check():
    """
    Service health probe. Verifies Redis and RabbitMQ connection status.
    """
    redis_status = "unconnected"
    if redis_client:
        try:
            redis_client.ping()
            redis_status = "healthy"
        except Exception:
            redis_status = "unhealthy"

    rabbitmq_status = "unconnected"
    if rabbitmq_connection and not rabbitmq_connection.is_closed:
        try:
            if rabbitmq_channel and not rabbitmq_channel.is_closed:
                rabbitmq_status = "healthy"
            else:
                rabbitmq_status = "channel_closed"
        except Exception:
            rabbitmq_status = "unhealthy"

    return {
        "status": "healthy",
        "redis": redis_status,
        "rabbitmq": rabbitmq_status,
        "service": "ingestion-pipeline"
    }

@app.post("/v1/logs", status_code=status.HTTP_202_ACCEPTED)
async def ingest_log(payload: InferenceLogPayload):
    """
    Ingests LLM inference telemetry logs.
    Validates, pushes to RabbitMQ durable queue, and returns 202 Accepted in sub-milliseconds.
    """
    global rabbitmq_channel
    if not rabbitmq_connection or rabbitmq_connection.is_closed or not rabbitmq_channel or rabbitmq_channel.is_closed:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ingestion event broker (RabbitMQ) is currently unavailable."
        )

    try:
        # Convert Pydantic object to JSON string.
        payload_data = payload.dict()
        if payload_data.get("timestamp"):
            payload_data["timestamp"] = payload_data["timestamp"].isoformat()

        json_payload = json.dumps(payload_data)
        
        # Publish to RabbitMQ durable queue
        await rabbitmq_channel.default_exchange.publish(
            aio_pika.Message(
                body=json_payload.encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            ),
            routing_key=config.RABBITMQ_QUEUE_NAME
        )
        
        return {"status": "accepted", "message": "Log enqueued asynchronously via RabbitMQ"}
    except Exception as e:
        logger.error(f"Error queueing inference log to RabbitMQ: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to enqueue telemetry event."
        )
