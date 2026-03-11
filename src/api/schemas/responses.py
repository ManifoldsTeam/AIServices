"""Response schemas for API endpoints."""

from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    """Status of an async generation job."""

    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class GenerationMetadata(BaseModel):
    """Metadata about a generation run."""

    total_generated: int = Field(..., description="Total content items generated")
    total_passed_review: int = Field(
        ..., description="Items that passed quality review"
    )
    total_rejected: int = Field(..., description="Items rejected by reviewer")
    generation_time_seconds: float
    model_used: str
    vertex_search_queries: int = Field(default=1)
    game_types_generated: list[str]
    cost_estimate_usd: float | None = None


class GameContentResponse(BaseModel):
    """Response containing generated game content.

    Returned by GET /api/v1/generations/{request_id} when status is completed.
    """

    request_id: str
    user_id: str
    generated_at: datetime
    content: dict[str, list[dict]] = Field(
        ..., description="Game content by type: { 'quiz': [...], 'flashcard': [...] }"
    )
    metadata: GenerationMetadata


class JobResponse(BaseModel):
    """Response for job status check."""

    request_id: str
    status: JobStatus
    content: GameContentResponse | None = None
    error: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class DocumentResponse(BaseModel):
    """Response after document upload."""

    document_id: str
    user_id: str
    filename: str
    file_format: str
    gcs_uri: str
    index_status: str = "indexing"
    scope: str = "user"


class DocumentStatusResponse(BaseModel):
    """Document indexing status."""

    document_id: str
    index_status: str  # uploading | indexing | ready | failed


class DocumentListResponse(BaseModel):
    """List of documents."""

    documents: list[DocumentResponse]
    total: int


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: str
    detail: str | None = None
    request_id: str | None = None
