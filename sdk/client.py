import time
import queue
import threading
import atexit
import logging
import requests
from typing import Generator, Optional, Any, Dict, List
from contextlib import contextmanager
from datetime import datetime

from sdk.schemas import InferenceLogPayload
from sdk.redact import PIIRedactor

logger = logging.getLogger("LLMTelemetryLogger")
logging.basicConfig(level=logging.INFO)

class StreamTracker:
    """
    Tracks telemetry during a streaming LLM response.
    """
    def __init__(
        self,
        parent: "LLMTelemetryLogger",
        conversation_id: Optional[str],
        model: str,
        provider: str,
        message_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.parent = parent
        self.conversation_id = conversation_id
        self.model = model
        self.provider = provider
        self.message_id = message_id
        self.metadata = metadata or {}
        self.start_time = time.time()
        self.chunks: List[str] = []
        self.prompt_text = ""
        self.tokens_prompt = 0

    def set_prompt(self, prompt: str):
        """Sets the prompt and estimates/saves prompt token counts."""
        self.prompt_text = prompt
        self.tokens_prompt = self.parent.estimate_tokens(prompt)

    def add_chunk(self, chunk: str):
        """Adds a streamed text chunk to the completion accumulator."""
        if chunk:
            self.chunks.append(chunk)

    def success(self, tokens_prompt: Optional[int] = None, tokens_completion: Optional[int] = None):
        """Dispatches a success log event once the stream concludes."""
        duration_ms = int((time.time() - self.start_time) * 1000)
        completion_text = "".join(self.chunks)

        t_prompt = tokens_prompt if tokens_prompt is not None else self.tokens_prompt
        t_completion = tokens_completion if tokens_completion is not None else self.parent.estimate_tokens(completion_text)

        # Build metadata rich previews
        meta = {
            **self.metadata,
            "input_preview": self.prompt_text[:500],
            "output_preview": completion_text[:500]
        }

        self.parent.log_inference(
            conversation_id=self.conversation_id,
            message_id=self.message_id,
            provider=self.provider,
            model=self.model,
            status="success",
            latency_ms=duration_ms,
            tokens_prompt=t_prompt,
            tokens_completion=t_completion,
            metadata=meta
        )

    def error(self, err: Exception):
        """Dispatches an error log event if the stream raises an exception."""
        duration_ms = int((time.time() - self.start_time) * 1000)
        completion_text = "".join(self.chunks)

        # Build metadata rich previews
        meta = {
            **self.metadata,
            "input_preview": self.prompt_text[:500],
            "output_preview": completion_text[:500]
        }

        self.parent.log_inference(
            conversation_id=self.conversation_id,
            message_id=self.message_id,
            provider=self.provider,
            model=self.model,
            status="error",
            latency_ms=duration_ms,
            tokens_prompt=self.tokens_prompt,
            tokens_completion=self.parent.estimate_tokens(completion_text),
            error_message=str(err),
            metadata=meta
        )


class CallTracker:
    """
    Tracks telemetry during a standard (unary) LLM response.
    """
    def __init__(
        self,
        parent: "LLMTelemetryLogger",
        conversation_id: Optional[str],
        model: str,
        provider: str,
        message_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.parent = parent
        self.conversation_id = conversation_id
        self.model = model
        self.provider = provider
        self.message_id = message_id
        self.metadata = metadata or {}
        self.start_time = time.time()
        self.prompt_text = ""
        self.tokens_prompt = 0

    def set_prompt(self, prompt: str):
        """Sets the prompt and estimates/saves prompt token counts."""
        self.prompt_text = prompt
        self.tokens_prompt = self.parent.estimate_tokens(prompt)

    def success(self, completion: str, tokens_prompt: Optional[int] = None, tokens_completion: Optional[int] = None):
        """Dispatches a success log event."""
        duration_ms = int((time.time() - self.start_time) * 1000)

        t_prompt = tokens_prompt if tokens_prompt is not None else self.tokens_prompt
        t_completion = tokens_completion if tokens_completion is not None else self.parent.estimate_tokens(completion)

        meta = {
            **self.metadata,
            "input_preview": self.prompt_text[:500],
            "output_preview": completion[:500]
        }

        self.parent.log_inference(
            conversation_id=self.conversation_id,
            message_id=self.message_id,
            provider=self.provider,
            model=self.model,
            status="success",
            latency_ms=duration_ms,
            tokens_prompt=t_prompt,
            tokens_completion=t_completion,
            metadata=meta
        )

    def error(self, err: Exception):
        """Dispatches an error log event."""
        duration_ms = int((time.time() - self.start_time) * 1000)

        meta = {
            **self.metadata,
            "input_preview": self.prompt_text[:500]
        }

        self.parent.log_inference(
            conversation_id=self.conversation_id,
            message_id=self.message_id,
            provider=self.provider,
            model=self.model,
            status="error",
            latency_ms=duration_ms,
            tokens_prompt=self.tokens_prompt,
            tokens_completion=0,
            error_message=str(err),
            metadata=meta
        )


class LLMTelemetryLogger:
    """
    Telemetry Logger Client SDK for tracking LLM metrics asynchronously.
    """
    def __init__(
        self,
        ingest_url: str = "http://localhost:8001/v1/logs",
        api_key: Optional[str] = None,
        enable_pii_redaction: bool = True
    ):
        self.ingest_url = ingest_url
        self.api_key = api_key
        self.enable_pii_redaction = enable_pii_redaction

        # Thread-safe logging queue
        self._queue: queue.Queue = queue.Queue()
        self._stop_event = threading.Event()
        self._worker_thread = threading.Thread(target=self._process_queue, daemon=True)
        self._worker_thread.start()

        # Register exit hook to flush remaining logs
        atexit.register(self.shutdown)

    def estimate_tokens(self, text: str) -> int:
        """
        Fallback token estimator based on average English token lengths
        (roughly 4 characters or 0.75 words per token).
        """
        if not text:
            return 0
        # Average characters per token: 4
        char_based = len(text) // 4
        # Average words per token: 0.75 -> 4 words is roughly 3 tokens
        word_based = int(len(text.split()) * 1.3)
        # Use average of both metrics for robust estimation
        return max(1, (char_based + word_based) // 2)

    def log_inference(
        self,
        provider: str,
        model: str,
        status: str,
        latency_ms: int,
        conversation_id: Optional[str] = None,
        message_id: Optional[str] = None,
        tokens_prompt: int = 0,
        tokens_completion: int = 0,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        Queues an inference log payload for async transmission.
        Does client-side PII redaction if enabled.
        """
        meta = metadata or {}
        pii_was_redacted = False

        if self.enable_pii_redaction:
            # Redact prompt and completion previews inside metadata, and error message
            if "input_preview" in meta:
                meta["input_preview"], r1 = PIIRedactor.redact_text(meta["input_preview"])
                if r1: pii_was_redacted = True
            if "output_preview" in meta:
                meta["output_preview"], r2 = PIIRedactor.redact_text(meta["output_preview"])
                if r2: pii_was_redacted = True
            if error_message:
                error_message, r3 = PIIRedactor.redact_text(error_message)
                if r3: pii_was_redacted = True
            
            # Redact general metadata fields recursively
            meta, r4 = PIIRedactor.redact_value(meta)
            if r4: pii_was_redacted = True

        log_payload = InferenceLogPayload(
            conversation_id=conversation_id,
            message_id=message_id,
            provider=provider,
            model=model,
            status=status,
            latency_ms=latency_ms,
            tokens_prompt=tokens_prompt,
            tokens_completion=tokens_completion,
            tokens_total=tokens_prompt + tokens_completion,
            error_message=error_message,
            pii_redacted=pii_was_redacted,
            metadata=meta,
            timestamp=datetime.utcnow()
        )

        # Enqueue the log model as a serialized dict
        self._queue.put(log_payload.dict())

    @contextmanager
    def trace(
        self,
        conversation_id: Optional[str],
        model: str,
        provider: str,
        message_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Generator[CallTracker, None, None]:
        """
        Context manager for tracking standard (non-streaming) LLM calls.
        """
        tracker = CallTracker(self, conversation_id, model, provider, message_id, metadata)
        try:
            yield tracker
        except Exception as e:
            tracker.error(e)
            raise e

    @contextmanager
    def trace_stream(
        self,
        conversation_id: Optional[str],
        model: str,
        provider: str,
        message_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Generator[StreamTracker, None, None]:
        """
        Context manager for tracking streaming LLM calls.
        """
        tracker = StreamTracker(self, conversation_id, model, provider, message_id, metadata)
        try:
            yield tracker
        except Exception as e:
            tracker.error(e)
            raise e

    def _process_queue(self):
        """
        Background worker loop to batch or continuously send logs to Ingest API.
        """
        session = requests.Session()
        if self.api_key:
            session.headers.update({"Authorization": f"Bearer {self.api_key}"})

        while not self._stop_event.is_set() or not self._queue.empty():
            try:
                # Block for 0.5s waiting for work
                payload_dict = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            # Convert datetime to string for json serialization
            if "timestamp" in payload_dict and isinstance(payload_dict["timestamp"], datetime):
                payload_dict["timestamp"] = payload_dict["timestamp"].isoformat()

            try:
                response = session.post(self.ingest_url, json=payload_dict, timeout=5)
                if response.status_code not in (200, 201, 202):
                    logger.warning(
                        f"Failed to post telemetry log: {response.status_code} - {response.text}"
                    )
            except Exception as e:
                logger.error(f"Error transmitting telemetry log to Ingest API: {e}")
            finally:
                self._queue.task_done()

    def shutdown(self):
        """
        Signals the queue processing thread to complete and flushes remaining logs.
        Called automatically on system exit.
        """
        if not self._stop_event.is_set():
            logger.info("Telemetry Logger SDK shutting down, flushing logs queue...")
            self._stop_event.set()
            # Wait for background queue processing to drain
            self._worker_thread.join(timeout=3.0)
            logger.info("Telemetry Logger SDK shutdown complete.")
