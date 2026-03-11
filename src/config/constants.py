"""Public constants — centralized configuration for limits, defaults, and tuning params.

Model IDs live in Settings (env-configurable via GENERATION_MODEL / REVIEW_MODEL).
This file holds values that are truly constant across all environments.

Usage:
    from src.config.constants import GENERATION_TEMPERATURE, MAX_FILE_SIZE_BYTES
"""

# ─── LLM Default Parameters ─────────────────────────────────────────
GENERATION_TEMPERATURE: float = 0.7
GENERATION_MAX_TOKENS: int = 8192

REVIEW_TEMPERATURE: float = 0.1
REVIEW_MAX_TOKENS: int = 4096

STRUCTURED_TEMPERATURE: float = 0.3
STRUCTURED_MAX_TOKENS: int = 8192

LLM_MAX_RETRIES: int = 3

# ─── Document Upload Limits ─────────────────────────────────────────
MAX_FILE_SIZE_BYTES: int = 50 * 1024 * 1024  # 50 MB

ALLOWED_MIME_TYPES: set[str] = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # DOCX
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",  # PPTX
}

EXTENSION_MIME_MAP: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

# ─── System Defaults ────────────────────────────────────────────────
SYSTEM_USER_ID: str = "__system__"
"""Sentinel user ID for system-uploaded documents."""
