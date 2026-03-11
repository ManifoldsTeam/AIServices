"""LLM service factory — ChatVertexAI Pro/Flash model providers.

Provides centralized LLM instantiation with:
1. Config-driven model selection (Pro for generation, Flash for review)
2. Retry logic + error handling
3. Token usage tracking via structlog

Usage:
    from src.services.llm import get_generation_llm, get_review_llm

    # For content generation (higher quality, more tokens)
    llm = get_generation_llm()

    # For review/validation (faster, cheaper)
    llm = get_review_llm()
"""

import structlog
from langchain_google_vertexai import ChatVertexAI

from src.config import get_settings
from src.config.constants import (
    GENERATION_MAX_TOKENS,
    GENERATION_TEMPERATURE,
    LLM_MAX_RETRIES,
    REVIEW_MAX_TOKENS,
    REVIEW_TEMPERATURE,
    STRUCTURED_MAX_TOKENS,
    STRUCTURED_TEMPERATURE,
)

logger = structlog.get_logger(__name__)


def get_generation_llm(
    temperature: float = GENERATION_TEMPERATURE,
    max_output_tokens: int = GENERATION_MAX_TOKENS,
) -> ChatVertexAI:
    """Get LLM for content generation tasks.

    Uses Gemini model with higher creativity settings for
    generating varied educational questions and content.

    Args:
        temperature: Sampling temperature (0.0-1.0). Higher = more creative.
        max_output_tokens: Maximum tokens in response.

    Returns:
        Configured ChatVertexAI instance for generation.
    """
    settings = get_settings()
    location = settings.generation_model_location or settings.gcp_location

    logger.debug(
        "creating_generation_llm",
        model=settings.generation_model,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        location=location,
    )

    return ChatVertexAI(
        model_name=settings.generation_model,
        project=settings.gcp_project_id,
        location=location,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        max_retries=LLM_MAX_RETRIES,
    )


def get_review_llm(
    temperature: float = REVIEW_TEMPERATURE,
    max_output_tokens: int = REVIEW_MAX_TOKENS,
) -> ChatVertexAI:
    """Get LLM for review/validation tasks.

    Uses Gemini Flash with low temperature for deterministic,
    consistent quality reviews.

    Args:
        temperature: Low temperature for consistent reviews.
        max_output_tokens: Generally smaller for review outputs.

    Returns:
        Configured ChatVertexAI instance for review.
    """
    settings = get_settings()
    location = settings.review_model_location or settings.gcp_location

    logger.debug(
        "creating_review_llm",
        model=settings.review_model,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        location=location,
    )

    return ChatVertexAI(
        model_name=settings.review_model,
        project=settings.gcp_project_id,
        location=location,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        max_retries=LLM_MAX_RETRIES,
    )


def get_structured_llm(
    output_schema: type,
    temperature: float = STRUCTURED_TEMPERATURE,
    max_output_tokens: int = STRUCTURED_MAX_TOKENS,
) -> ChatVertexAI:
    """Get LLM with structured output for a given Pydantic schema.

    Wraps `with_structured_output()` for use cases where we need
    deterministic JSON output matching a schema.

    Args:
        output_schema: Pydantic BaseModel class for structured output.
        temperature: Lower temperature for more deterministic output.
        max_output_tokens: Max tokens for the response.

    Returns:
        ChatVertexAI with structured output support.
    """
    llm = get_generation_llm(
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )
    return llm.with_structured_output(output_schema)
