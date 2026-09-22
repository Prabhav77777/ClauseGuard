"""
MODULE: Gemini API SDK client singleton and structured JSON call wrapper.

@level-one-validation: Singleton client configuration enables connection pooling. Response schema validation guarantees Pydantic return types. Tested via test_e2e_integration.py and test_qa_grounding.py.

#Scope-Of-Improvement: Add exponential backoff retry decorator to handle transient HTTP 429 / rate limit errors gracefully.
"""

import logging
from typing import Type, TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel

from backend.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Efficiency: Singleton client instance reused across API calls
_CLIENT_INSTANCE: genai.Client | None = None


# #What: Manages singleton Gemini Client instance for connection pooling across requests
def _get_gemini_client() -> genai.Client:
    """Retrieve or create the module-level singleton Gemini client.

    Efficiency: Reuses a single client instance across requests to enable connection
    reuse and eliminate repeated TCP/TLS handshake setup latency.
    """
    global _CLIENT_INSTANCE
    if _CLIENT_INSTANCE is None:
        _CLIENT_INSTANCE = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _CLIENT_INSTANCE


# @risk-area: Synchronous generate_content call blocks worker thread; if network latency increases, worker thread pool can saturate.
# #What: Generates structured JSON output from Gemini API validated against target Pydantic schema
def call_gemini_structured(
    system_instruction: str,
    user_content: str,
    response_schema: Type[T],
    temperature: float = 0.1,
) -> T:
    """Generate structured JSON output from Gemini matching a Pydantic schema.

    Args:
        system_instruction: System prompt rules and role instructions
        user_content: User prompt containing wrapped document text or queries
        response_schema: Target Pydantic model for structured output validation
        temperature: Sampling temperature (default 0.1 for high determinism)

    Returns:
        Instance of response_schema populated with Gemini's response
    """
    client = _get_gemini_client()

    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        response_mime_type="application/json",
        response_schema=response_schema,
        temperature=temperature,
    )

    response = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=user_content,
        config=config,
    )

    raw_text = response.text or "{}"
    return response_schema.model_validate_json(raw_text)
