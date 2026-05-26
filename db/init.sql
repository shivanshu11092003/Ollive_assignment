-- Schema Initialization for LLM Inference Telemetry and Chatbot

-- Enable UUID extension if not present
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Conversations Table
CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. Messages Table
CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL, -- 'user', 'assistant', 'system'
    content TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Index for retrieving conversation history quickly
CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);

-- 3. Inference Logs Table
CREATE TABLE IF NOT EXISTS inference_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL,
    message_id UUID REFERENCES messages(id) ON DELETE SET NULL,
    provider VARCHAR(50) NOT NULL, -- 'gemini', 'openai', 'mock'
    model VARCHAR(100) NOT NULL,  -- e.g. 'gemini-1.5-flash', 'gpt-4o'
    status VARCHAR(50) NOT NULL,   -- 'success', 'error'
    latency_ms INTEGER NOT NULL,  -- Duration of request in ms
    tokens_prompt INTEGER NOT NULL DEFAULT 0,
    tokens_completion INTEGER NOT NULL DEFAULT 0,
    tokens_total INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    pii_redacted BOOLEAN NOT NULL DEFAULT FALSE,
    inference_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance telemetry dashboard queries
CREATE INDEX IF NOT EXISTS idx_inference_logs_conversation_id ON inference_logs(conversation_id);
CREATE INDEX IF NOT EXISTS idx_inference_logs_timestamp ON inference_logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_inference_logs_provider ON inference_logs(provider);
CREATE INDEX IF NOT EXISTS idx_inference_logs_model ON inference_logs(model);
CREATE INDEX IF NOT EXISTS idx_inference_logs_status ON inference_logs(status);
CREATE INDEX IF NOT EXISTS idx_inference_logs_timestamp_latency ON inference_logs(timestamp DESC, latency_ms);
