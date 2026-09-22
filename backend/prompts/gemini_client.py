"""Gemini API client helper for structured JSON generation.

Uses Google Gemini SDK (google-genai) to generate structured outputs
conforming strictly to Pydantic schemas.
"""

import logging
from typing import Type, TypeVar
from pydantic import BaseModel
from google import genai
from google.genai import types

from backend.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


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
    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    
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
    
    return response_schema.model_validate_json(response.text)
