"""LLM service factory — cached ChatGoogleGenerativeAI providers.

Provides centralized LLM instantiation with:
1. Config-driven model selection (generation vs review)
2. Singleton caching — same (temperature, max_tokens) → same instance
3. Retry logic + error handling via LangChain max_retries

Usage:
    from src.services.llm import get_generation_llm, get_review_llm

    # For content generation (higher quality, more tokens)
    llm = get_generation_llm()

    # For review/validation (faster, cheaper)
    llm = get_review_llm()
"""

from functools import lru_cache

import structlog
from langchain_google_genai import ChatGoogleGenerativeAI

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


@lru_cache(maxsize=8)
def get_generation_llm(
    temperature: float = GENERATION_TEMPERATURE,
    max_output_tokens: int = GENERATION_MAX_TOKENS,
) -> ChatGoogleGenerativeAI:
    """Get (cached) LLM for content generation tasks.

    Instances are cached by (temperature, max_output_tokens).
    Same parameters → same instance across the entire process.
    """
    settings = get_settings()
    location = settings.generation_model_location or settings.gcp_location

    logger.info(
        "creating_generation_llm",
        model=settings.generation_model,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        location=location,
    )

    return ChatGoogleGenerativeAI(
        model=settings.generation_model,
        project=settings.gcp_project_id,
        location=location,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        max_retries=LLM_MAX_RETRIES,
    )


@lru_cache(maxsize=4)
def get_review_llm(
    temperature: float = REVIEW_TEMPERATURE,
    max_output_tokens: int = REVIEW_MAX_TOKENS,
) -> ChatGoogleGenerativeAI:
    """Get (cached) LLM for review/validation tasks.

    Instances are cached by (temperature, max_output_tokens).
    Same parameters → same instance across the entire process.
    """
    settings = get_settings()
    location = settings.review_model_location or settings.gcp_location

    logger.info(
        "creating_review_llm",
        model=settings.review_model,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        location=location,
    )

    return ChatGoogleGenerativeAI(
        model=settings.review_model,
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
) -> ChatGoogleGenerativeAI:
    """Get LLM with structured output for a given Pydantic schema.

    Note: `.with_structured_output()` returns a new runnable each time,
    but the underlying LLM instance is cached via get_generation_llm().
    """
    llm = get_generation_llm(
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )
    return llm.with_structured_output(output_schema)
