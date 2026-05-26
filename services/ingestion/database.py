import uuid
from datetime import datetime
from sqlalchemy import create_engine, Column, String, Integer, Boolean, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID as pgUUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from services.ingestion import config

# Create database engine
engine = create_engine(config.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class InferenceLog(Base):
    """
    SQLAlchemy model representing an LLM inference telemetry log entry.
    """
    __tablename__ = "inference_logs"

    id = Column(pgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(pgUUID(as_uuid=True), nullable=True)
    message_id = Column(pgUUID(as_uuid=True), nullable=True)
    provider = Column(String(50), nullable=False)
    model = Column(String(100), nullable=False)
    status = Column(String(50), nullable=False)
    latency_ms = Column(Integer, nullable=False)
    tokens_prompt = Column(Integer, nullable=False, default=0)
    tokens_completion = Column(Integer, nullable=False, default=0)
    tokens_total = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    pii_redacted = Column(Boolean, nullable=False, default=False)
    inference_metadata = Column("metadata", JSONB, nullable=False, default=dict)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

# Database dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
