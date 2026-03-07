"""Structured logging setup using structlog.

Provides:
- Console output for local development (colored, human-readable)
- JSON output for Cloud Run (structured, Cloud Logging compatible)

Usage:
    from src.config.logging import get_logger

    logger = get_logger(__name__)
    logger.info("Processing request", user_id="123", game_type="quiz")
"""

import logging
import sys
from typing import Any

import structlog
from structlog.types import Processor

from .settings import get_settings


def _add_gcp_fields(
    logger: logging.Logger, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Add GCP Cloud Logging compatible fields.

    Maps structlog fields to Cloud Logging JSON payload structure:
    - severity: Maps to Cloud Logging severity
    - logging.googleapis.com/labels: Custom labels for filtering
    """
    # Map log level to Cloud Logging severity
    level = event_dict.get("level", "info").upper()
    severity_map = {
        "DEBUG": "DEBUG",
        "INFO": "INFO",
        "WARNING": "WARNING",
        "ERROR": "ERROR",
        "CRITICAL": "CRITICAL",
        "EXCEPTION": "ERROR",
    }
    event_dict["severity"] = severity_map.get(level, "DEFAULT")

    # Extract common fields for GCP labels
    labels = {}
    for key in ["user_id", "request_id", "game_type", "job_id"]:
        if key in event_dict:
            labels[key] = str(event_dict[key])

    if labels:
        event_dict["logging.googleapis.com/labels"] = labels

    return event_dict


def _configure_structlog(json_format: bool = False) -> None:
    """Configure structlog processors and output format.

    Args:
        json_format: If True, output JSON for Cloud Logging. If False, pretty console output.
    """
    # Shared processors for all formats
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if json_format:
        # JSON format for Cloud Run / Cloud Logging
        processors: list[Processor] = [
            *shared_processors,
            _add_gcp_fields,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        # Console format for local development
        processors = [
            *shared_processors,
            structlog.dev.ConsoleRenderer(
                colors=True,
                exception_formatter=structlog.dev.plain_traceback,
            ),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def _configure_stdlib_logging(log_level: str) -> None:
    """Configure standard library logging to work with structlog.

    This ensures third-party libraries (httpx, google-cloud-*, etc.)
    also output through structlog.
    """
    # Set root logger level
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level),
    )

    # Reduce noise from verbose libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("google").setLevel(logging.INFO)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def setup_logging() -> None:
    """Initialize logging configuration.

    Should be called once at application startup (main.py).
    Reads LOG_LEVEL and LOG_FORMAT from settings.
    """
    settings = get_settings()

    json_format = settings.log_format == "json"
    _configure_structlog(json_format=json_format)
    _configure_stdlib_logging(settings.log_level)


def get_logger(name: str | None = None) -> structlog.BoundLogger:
    """Get a logger instance.

    Args:
        name: Logger name, typically __name__ of the calling module.

    Returns:
        A bound structlog logger.

    Example:
        logger = get_logger(__name__)
        logger.info("Event", key="value")
    """
    return structlog.get_logger(name)


# --- Context helpers for request tracing ---


def bind_context(**kwargs: Any) -> None:
    """Bind context variables that persist across log calls in the same request.

    Use at the start of request handling to set request_id, user_id, etc.

    Example:
        bind_context(request_id="abc123", user_id="user456")
        logger.info("Processing")  # Will include request_id and user_id
    """
    structlog.contextvars.bind_contextvars(**kwargs)


def clear_context() -> None:
    """Clear all bound context variables.

    Use at the end of request handling to prevent context leakage.
    """
    structlog.contextvars.clear_contextvars()
