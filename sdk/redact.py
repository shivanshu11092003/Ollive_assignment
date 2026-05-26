import re
from typing import Any, Dict, List, Union

class PIIRedactor:
    """
    A lightweight, high-performance regex-based PII Redactor.
    Detects and masks sensitive information like:
    - Email addresses
    - Phone numbers (common US & international)
    - Credit Card numbers
    - Social Security Numbers (SSN)
    - API keys (OpenAI, Gemini, general Bearer tokens)
    """

    # Compiled regex patterns for performance
    EMAIL_REGEX = re.compile(r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b')
    PHONE_REGEX = re.compile(r'\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b')
    CREDIT_CARD_REGEX = re.compile(r'\b(?:\d[ -]*?){13,16}\b')
    SSN_REGEX = re.compile(r'\b\d{3}-\d{2}-\d{4}\b')
    
    # Common API Keys
    OPENAI_KEY_REGEX = re.compile(r'\bsk-[a-zA-Z0-9]{48}\b')
    GEMINI_KEY_REGEX = re.compile(r'\bAIzaSy[a-zA-Z0-9-_]{33}\b')
    BEARER_TOKEN_REGEX = re.compile(r'\bBearer\s+[a-zA-Z0-9\-._~+/]+=*\b', re.IGNORECASE)

    PATTERNS = {
        "[REDACTED_EMAIL]": EMAIL_REGEX,
        "[REDACTED_PHONE]": PHONE_REGEX,
        "[REDACTED_CREDIT_CARD]": CREDIT_CARD_REGEX,
        "[REDACTED_SSN]": SSN_REGEX,
        "[REDACTED_OPENAI_KEY]": OPENAI_KEY_REGEX,
        "[REDACTED_GEMINI_KEY]": GEMINI_KEY_REGEX,
        "[REDACTED_AUTH_TOKEN]": BEARER_TOKEN_REGEX,
    }

    @classmethod
    def redact_text(cls, text: str) -> tuple[str, bool]:
        """
        Redacts PII from a given string.
        Returns a tuple of (redacted_text, was_redacted).
        """
        if not text:
            return text, False

        redacted_text = text
        was_redacted = False

        for replacement, pattern in cls.PATTERNS.items():
            new_text, count = pattern.subn(replacement, redacted_text)
            if count > 0:
                redacted_text = new_text
                was_redacted = True

        return redacted_text, was_redacted

    @classmethod
    def redact_value(cls, val: Any) -> tuple[Any, bool]:
        """
        Recursively redacts strings inside list or dict structures.
        """
        if isinstance(val, str):
            return cls.redact_text(val)
        elif isinstance(val, dict):
            new_dict = {}
            was_redacted = False
            for k, v in val.items():
                # Avoid redacting system metadata keys, just their string values
                redacted_v, sub_redacted = cls.redact_value(v)
                new_dict[k] = redacted_v
                if sub_redacted:
                    was_redacted = True
            return new_dict, was_redacted
        elif isinstance(val, list):
            new_list = []
            was_redacted = False
            for item in val:
                redacted_item, sub_redacted = cls.redact_value(item)
                new_list.append(redacted_item)
                if sub_redacted:
                    was_redacted = True
            return new_list, was_redacted
        else:
            return val, False
