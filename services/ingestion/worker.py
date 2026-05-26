import json
import logging
import asyncio
import redis
import aio_pika
from sqlalchemy.orm import Session
from datetime import datetime

from services.ingestion import config
from services.ingestion.database import SessionLocal, InferenceLog, engine, Base
from sdk.redact import PIIRedactor

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("TelemetryWorker")

def init_db():
    """
    Ensures database tables are created.
    """
    logger.info("Initializing database tables...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialization complete.")

def process_log(raw_payload: str, db: Session, r_client: redis.Redis) -> bool:
    """
    Processes a raw log payload:
    1. Parses JSON.
    2. Performs server-side PII redaction.
    3. Stores it in the database.
    4. Publishes to Redis Pub/Sub for real-time WebSocket distribution.
    Returns True on success, False on failure.
    """
    try:
        data = json.loads(raw_payload)
        
        # 1. Server-side double PII check/redaction
        pii_was_redacted = data.get("pii_redacted", False)
        
        # Redact input/output previews if present in metadata
        metadata = data.get("metadata", {})
        if "input_preview" in metadata:
            metadata["input_preview"], r1 = PIIRedactor.redact_text(metadata["input_preview"])
            if r1: pii_was_redacted = True
        if "output_preview" in metadata:
            metadata["output_preview"], r2 = PIIRedactor.redact_text(metadata["output_preview"])
            if r2: pii_was_redacted = True
            
        # Redact general metadata fields recursively
        metadata, r3 = PIIRedactor.redact_value(metadata)
        if r3: pii_was_redacted = True

        err_msg = data.get("error_message")
        if err_msg:
            err_msg, r4 = PIIRedactor.redact_text(err_msg)
            if r4: pii_was_redacted = True

        # Extract values
        timestamp_val = data.get("timestamp")
        if timestamp_val:
            try:
                # Parse ISO format datetime
                timestamp = datetime.fromisoformat(timestamp_val.replace("Z", "+00:00"))
            except Exception:
                timestamp = datetime.utcnow()
        else:
            timestamp = datetime.utcnow()

        # Compute extra enrichment fields (e.g. token speed)
        latency_ms = data.get("latency_ms", 0)
        tokens_total = data.get("tokens_total", 0)
        if latency_ms > 0:
            tokens_per_sec = (tokens_total / (latency_ms / 1000.0))
            metadata["tokens_per_second"] = round(tokens_per_sec, 2)

        # Create database log record
        inference_log = InferenceLog(
            conversation_id=data.get("conversation_id"),
            message_id=data.get("message_id"),
            provider=data.get("provider"),
            model=data.get("model"),
            status=data.get("status"),
            latency_ms=latency_ms,
            tokens_prompt=data.get("tokens_prompt", 0),
            tokens_completion=data.get("tokens_completion", 0),
            tokens_total=tokens_total,
            error_message=err_msg,
            pii_redacted=pii_was_redacted,
            inference_metadata=metadata,
            timestamp=timestamp
        )

        db.add(inference_log)
        db.commit()
        db.refresh(inference_log)
        logger.info(f"Successfully processed and stored telemetry log: {inference_log.id}")

        # 4. Broadcast event onto Redis Pub/Sub for WebSockets
        if r_client:
            broadcast_payload = {
                "id": str(inference_log.id),
                "conversation_id": str(inference_log.conversation_id) if inference_log.conversation_id else None,
                "message_id": str(inference_log.message_id) if inference_log.message_id else None,
                "provider": inference_log.provider,
                "model": inference_log.model,
                "status": inference_log.status,
                "latency_ms": inference_log.latency_ms,
                "tokens_prompt": inference_log.tokens_prompt,
                "tokens_completion": inference_log.tokens_completion,
                "tokens_total": inference_log.tokens_total,
                "error_message": inference_log.error_message,
                "pii_redacted": inference_log.pii_redacted,
                "metadata": inference_log.inference_metadata,
                "timestamp": inference_log.timestamp.isoformat()
            }
            r_client.publish(config.REDIS_PUBSUB_CHANNEL, json.dumps(broadcast_payload))
        return True

    except Exception as e:
        logger.error(f"Error processing telemetry log event: {e}")
        db.rollback()
        return False


async def run_worker():
    """
    Main asynchronous worker consumer loop with reconnection resilience.
    """
    init_db()

    redis_conn = None

    while True:
        try:
            # 1. Connect to Redis (WebSocket publisher channel)
            if not redis_conn:
                logger.info(f"Connecting to Redis at {config.REDIS_HOST}:{config.REDIS_PORT}...")
                redis_conn = redis.Redis(
                    host=config.REDIS_HOST,
                    port=config.REDIS_PORT,
                    password=config.REDIS_PASSWORD,
                    decode_responses=True
                )
                redis_conn.ping()
                logger.info("Connected to Redis successfully.")

            # 2. Connect to RabbitMQ using Robust connection
            logger.info(f"Connecting to RabbitMQ at {config.RABBITMQ_HOST}:{config.RABBITMQ_PORT}...")
            connection = await aio_pika.connect_robust(
                host=config.RABBITMQ_HOST,
                port=config.RABBITMQ_PORT,
                login=config.RABBITMQ_USER,
                password=config.RABBITMQ_PASSWORD,
                timeout=10
            )

            async with connection:
                channel = await connection.channel()
                # Balance the load via prefetch limit
                await channel.set_qos(prefetch_count=1)

                # Declare durable queue matching the publisher
                queue = await channel.declare_queue(
                    config.RABBITMQ_QUEUE_NAME,
                    durable=True
                )

                logger.info("RabbitMQ connection active. Durably consuming messages...")

                async with queue.iterator() as queue_iter:
                    async for message in queue_iter:
                        # message.process() context manager handles automatic ACKs (on exit)
                        # and NACKs (if block raises exception)
                        async with message.process():
                            raw_payload = message.body.decode()
                            # Use clean transactional isolation per log event
                            db_session = SessionLocal()
                            try:
                                success = process_log(raw_payload, db_session, redis_conn)
                                if not success:
                                    raise RuntimeError("Failed to process and save telemetry event.")
                            finally:
                                db_session.close()

        except (redis.ConnectionError, aio_pika.exceptions.AMQPConnectionError) as conn_err:
            logger.error(f"Connection failure in telemetry worker: {conn_err}. Retrying in 5 seconds...")
            redis_conn = None
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"Unexpected worker error, retrying in 5 seconds... Detail: {e}")
            redis_conn = None
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(run_worker())
