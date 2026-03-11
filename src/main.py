"""FastAPI application entrypoint for Edu Game AI Service."""

from fastapi import FastAPI

from src.api.routes import admin_router, generation_router, internal_router
from src.config import setup_logging

setup_logging()

app = FastAPI(
    title="Edu Game AI Service",
    version="0.1.0",
    description="Async educational game content generation service",
)


@app.get("/health", tags=["health"])
def health_check() -> dict:
    """Simple liveness probe endpoint."""
    return {"status": "ok"}


app.include_router(generation_router)
app.include_router(admin_router)
app.include_router(internal_router)
