"""Configuration module.

Exports:
    - Settings: Pydantic settings class
    - get_settings: Cached settings getter
    - clear_settings_cache: Clear cached settings (for testing)
    - setup_logging: Initialize logging
    - get_logger: Get a structlog logger
    - bind_context, clear_context: Request context helpers
"""

from .constants import (
    ALLOWED_MIME_TYPES,
    EXTENSION_MIME_MAP,
    GENERATION_MAX_TOKENS,
    GENERATION_TEMPERATURE,
    LLM_MAX_RETRIES,
    MAX_FILE_SIZE_BYTES,
    REVIEW_MAX_TOKENS,
    REVIEW_TEMPERATURE,
    STRUCTURED_MAX_TOKENS,
    STRUCTURED_TEMPERATURE,
    SYSTEM_USER_ID,
)
from .logging import bind_context, clear_context, get_logger, setup_logging
from .settings import Settings, clear_settings_cache, get_settings

__all__ = [
    # Settings
    "Settings",
    "get_settings",
    "clear_settings_cache",
    # Logging
    "setup_logging",
    "get_logger",
    "bind_context",
    "clear_context",
    # Constants
    "GENERATION_TEMPERATURE",
    "GENERATION_MAX_TOKENS",
    "REVIEW_TEMPERATURE",
    "REVIEW_MAX_TOKENS",
    "STRUCTURED_TEMPERATURE",
    "STRUCTURED_MAX_TOKENS",
    "LLM_MAX_RETRIES",
    "MAX_FILE_SIZE_BYTES",
    "ALLOWED_MIME_TYPES",
    "EXTENSION_MIME_MAP",
    "SYSTEM_USER_ID",
]
