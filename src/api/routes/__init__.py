"""API route modules."""

from .admin import router as admin_router
from .generation import router as generation_router
from .internal import router as internal_router

__all__ = ["admin_router", "generation_router", "internal_router"]
