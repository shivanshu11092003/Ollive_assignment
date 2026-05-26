from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

class InferenceLogPayload(BaseModel):
    """
    Validation schema for LLM Inference Telemetry logs sent by the SDK
    and processed by the Ingestion pipeline.
    """
    conversation_id: Optional[str] = Field(
        None, description="UUID of the conversation session"
    )
    message_id: Optional[str] = Field(
        None, description="UUID of the message matching this inference log"
    )
    provider: str = Field(
        ..., description="The LLM API provider (e.g., gemini, openai, mock)"
    )
    model: str = Field(
        ..., description="The model name (e.g., gemini-1.5-flash, gpt-4o)"
    )
    status: str = Field(
        ..., description="The status of the call: 'success' or 'error'"
    )
    latency_ms: int = Field(
        ..., ge=0, description="Inference request duration in milliseconds"
    )
    tokens_prompt: int = Field(
        0, ge=0, description="Count of prompt/input tokens used"
    )
    tokens_completion: int = Field(
        0, ge=0, description="Count of completion/output tokens generated"
    )
    tokens_total: int = Field(
        0, ge=0, description="Total token usage (prompt + completion)"
    )
    error_message: Optional[str] = Field(
        None, description="Detailed error description if status is 'error'"
    )
    pii_redacted: bool = Field(
        False, description="Flag indicating if PII was redacted client-side"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Arbitrary execution context metadata"
    )
    timestamp: Optional[datetime] = Field(
        default_factory=datetime.utcnow, description="ISO Timestamp of the request initiation"
    )
