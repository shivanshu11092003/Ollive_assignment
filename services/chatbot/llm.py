import httpx
import json
import asyncio
import logging
import random
import time
from typing import AsyncGenerator, List, Dict, Any, Optional

from services.chatbot import config
from sdk.client import LLMTelemetryLogger

logger = logging.getLogger("LLMClient")

# Initialize SDK Logger Client
telemetry_logger = LLMTelemetryLogger(
    ingest_url=config.TELEMETRY_INGEST_URL,
    enable_pii_redaction=True
)

class LLMProviderClient:
    """
    Handles streaming chat queries across different providers
    (Gemini, OpenAI, Mock) while collecting inference logs via the Telemetry SDK.
    """

    @classmethod
    async def stream_chat(
        cls,
        conversation_id: str,
        message_id: str,
        provider: str,
        model: str,
        messages: List[Dict[str, str]]
    ) -> AsyncGenerator[str, None]:
        """
        Streams responses from the selected LLM provider and automatically
        records metrics (latency, tokens, metadata) via SDK trace_stream.
        """
        provider_clean = provider.lower().strip()
        
        # Build standard system prompt context
        formatted_prompt = ""
        for m in messages:
            formatted_prompt += f"{m['role'].upper()}: {m['content']}\n"

        # Instantiate tracking via SDK
        # We wrap the generator execution inside the SDK trace_stream manager
        with telemetry_logger.trace_stream(
            conversation_id=conversation_id,
            message_id=message_id,
            model=model,
            provider=provider_clean,
            metadata={"session_history_turns": len(messages)}
        ) as tracker:
            
            # Set original prompt in telemetry tracker
            tracker.set_prompt(formatted_prompt)
            
            try:
                if provider_clean == "gemini":
                    generator = cls._stream_gemini(model, messages)
                elif provider_clean == "openai":
                    generator = cls._stream_openai(model, messages)
                else:
                    # Fallback to Mock LLM
                    generator = cls._stream_mock(model, messages)

                async for chunk in generator:
                    tracker.add_chunk(chunk)
                    yield chunk

                # Commit success telemetry
                tracker.success()
                
            except Exception as e:
                logger.error(f"Error during streaming inference: {e}")
                tracker.error(e)
                # Yield a friendly error notice to the user
                yield f"\n\n*[System: Telemetry tracked an error. Provider disconnected: {str(e)}]*"
                raise e

    @classmethod
    async def _stream_gemini(cls, model: str, messages: List[Dict[str, str]]) -> AsyncGenerator[str, None]:
        """
        Streams from Google's Gemini API via HTTP POST SSE stream.
        """
        api_key = config.GEMINI_API_KEY
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not configured.")

        # Map typical frontend selection to actual Gemini model names
        actual_model = model
        if "flash" in model.lower() or model == "mock-llm":
            actual_model = "gemini-flash-latest"
        elif "pro" in model.lower():
            actual_model = "gemini-pro-latest"

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{actual_model}:streamGenerateContent?key={api_key}"
        
        # Translate messaging history to Gemini API format
        contents = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({
                "role": role,
                "parts": [{"text": msg["content"]}]
            })

        payload = {"contents": contents}
        headers = {"Content-Type": "application/json"}

        # Perform asynchronous streaming post request
        async with httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                if response.status_code != 200:
                    err_body = await response.aread()
                    raise RuntimeError(f"Gemini API returned status {response.status_code}: {err_body.decode()}")

                buffer = ""
                async for chunk in response.aiter_text():
                    buffer += chunk
                    while True:
                        buffer = buffer.lstrip(" \t\n\r,[")
                        if not buffer:
                            break
                        
                        # Look for complete JSON objects
                        brace_count = 0
                        in_str = False
                        escape = False
                        split_idx = -1
                        
                        for idx, char in enumerate(buffer):
                            if char == '"' and not escape:
                                in_str = not in_str
                            elif char == '\\' and in_str:
                                escape = not escape
                                continue
                            elif not in_str:
                                if char == '{':
                                    brace_count += 1
                                elif char == '}':
                                    brace_count -= 1
                                    if brace_count == 0:
                                        # Found a candidate complete JSON block!
                                        split_idx = idx + 1
                                        break
                            escape = False

                        if split_idx != -1:
                            candidate_str = buffer[:split_idx].strip()
                            buffer = buffer[split_idx:]
                            
                            try:
                                block = json.loads(candidate_str)
                                candidates = block.get("candidates", [])
                                if candidates and len(candidates) > 0:
                                    content = candidates[0].get("content", {})
                                    parts_list = content.get("parts", [])
                                    text_chunk = "".join([p.get("text", "") for p in parts_list])
                                    if text_chunk:
                                        yield text_chunk
                            except Exception as parse_err:
                                logger.error(f"Error parsing Gemini stream chunk: {parse_err}")
                                continue
                        else:
                            break

    @classmethod
    async def _stream_openai(cls, model: str, messages: List[Dict[str, str]]) -> AsyncGenerator[str, None]:
        """
        Streams from OpenAI / DeepSeek API using standard SSE format.
        """
        api_key = config.OPENAI_API_KEY
        if not api_key:
            raise ValueError("OPENAI_API_KEY is not configured.")

        # Let's map model Selection
        actual_model = model
        if model == "mock-llm":
            actual_model = "gpt-4o"

        url = f"{config.OPENAI_BASE_URL}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        payload = {
            "model": actual_model,
            "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
            "stream": True
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                if response.status_code != 200:
                    err_body = await response.aread()
                    raise RuntimeError(f"OpenAI API returned status {response.status_code}: {err_body.decode()}")

                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith("data: "):
                        data_content = line[6:]
                        if data_content == "[DONE]":
                            break
                        try:
                            block = json.loads(data_content)
                            choices = block.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    yield content
                        except Exception:
                            continue

    @classmethod
    async def _stream_mock(cls, model: str, messages: List[Dict[str, str]]) -> AsyncGenerator[str, None]:
        """
        Mock LLM provider. Generates highly intelligent, realistic responses about AI,
        development, and telemetry with realistic streaming speeds.
        Does not require any API keys.
        """
        user_prompt = messages[-1]["content"].lower() if messages else ""
        
        mock_responses = [
            "I'm an intelligent assistant. I see that you're testing the inference logging pipeline! Everything is working correctly.",
            "That's an excellent question. Implementing telemetry for large language models requires tracking token counts, throughput, latency, and status in near real-time.",
            "I am ready to assist you. With this system, you get full visibility into prompt/completion details, latency analytics, and event driven architectures.",
            "Indeed! We redact personal details like email addresses (e.g. test@example.com), credit card numbers, and API keys automatically to guarantee robust data compliance."
        ]

        # Smart matching of user queries to look highly reactive
        if "pii" in user_prompt or "redact" in user_prompt or "credit" in user_prompt or "email" in user_prompt:
            chosen_response = (
                "Understood! When PII is sent, like email addresses (e.g., phenom@ollive.ai) or card credentials "
                "(e.g., 4111-2222-3333-4444), both our client-side and server-side redactors scrub them "
                "instantly. Telemetry records will read '[REDACTED_EMAIL]' and '[REDACTED_CREDIT_CARD]' instead."
            )
        elif "latency" in user_prompt or "metrics" in user_prompt or "throughput" in user_prompt or "dashboard" in user_prompt:
            chosen_response = (
                "This observability dashboard calculates latency in milliseconds by recording start/end intervals. "
                "Throughput is measured in tokens/sec by dividing the generated token count by total latency in seconds. "
                "Live events stream in real-time via WebSockets!"
            )
        elif "cancel" in user_prompt:
            chosen_response = (
                "You can cancel a streaming conversation by clicking the 'Cancel' button in the chat interface! "
                "This terminates the streaming connection immediately, and logging will record this event."
            )
        elif "help" in user_prompt or "system" in user_prompt:
            chosen_response = (
                "This project is a high-fidelity inference monitoring application built with FastAPI, Redis, "
                "PostgreSQL, and React. It features an event-driven ingestion queue to prevent chatbot slow-downs."
            )
        else:
            chosen_response = random.choice(mock_responses)

        # Split response into words or characters to simulate smooth stream
        words = chosen_response.split(" ")
        for i, word in enumerate(words):
            yield word + (" " if i < len(words) - 1 else "")
            # Add subtle streaming latency (approx 50 words per second)
            await asyncio.sleep(0.04)
