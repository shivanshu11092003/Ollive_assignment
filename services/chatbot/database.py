import uuid
from datetime import datetime
from typing import List, Optional
from sqlalchemy import create_engine, Column, String, DateTime, ForeignKey, Text, Integer, Boolean
from sqlalchemy.dialects.postgresql import UUID as pgUUID, JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, Session

from services.chatbot import config

# Create database engine
engine = create_engine(config.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class Conversation(Base):
    """
    SQLAlchemy model representing a chatbot conversation session.
    """
    __tablename__ = "conversations"

    id = Column(pgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    """
    SQLAlchemy model representing a message in a conversation.
    """
    __tablename__ = "messages"

    id = Column(pgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(pgUUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(50), nullable=False) # 'user', 'assistant', 'system'
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    conversation = relationship("Conversation", back_populates="messages")


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



# DB Helpers
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_conversations(db: Session) -> List[Conversation]:
    """
    Lists conversations sorted by update date (descending).
    """
    return db.query(Conversation).order_by(Conversation.updated_at.desc()).all()

def create_conversation(db: Session, title: str) -> Conversation:
    """
    Creates a new conversation.
    """
    conv = Conversation(title=title)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv

def delete_conversation(db: Session, conv_id: str) -> bool:
    """
    Deletes a conversation and its messages.
    """
    conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
    if conv:
        db.delete(conv)
        db.commit()
        return True
    return False

def get_conversation_messages(db: Session, conv_id: str) -> List[Message]:
    """
    Retrieves all messages for a specific conversation in chronological order.
    """
    return db.query(Message).filter(Message.conversation_id == conv_id).order_by(Message.created_at.asc()).all()

def create_message(db: Session, conversation_id: str, role: str, content: str, message_id: Optional[str] = None) -> Message:
    """
    Adds a message to an active conversation and updates conversation's last active timestamp.
    """
    if message_id:
        msg = Message(id=uuid.UUID(message_id) if isinstance(message_id, str) else message_id, conversation_id=conversation_id, role=role, content=content)
    else:
        msg = Message(conversation_id=conversation_id, role=role, content=content)
    db.add(msg)
    
    # Touch conversation timestamp
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if conv:
        conv.updated_at = datetime.utcnow()
        
    db.commit()
    db.refresh(msg)
    return msg
