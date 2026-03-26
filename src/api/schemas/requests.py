"""Request schemas for API endpoints."""

from enum import Enum
from pydantic import BaseModel, Field

from .game_content import GameType, DifficultyLevel


class DocScope(str, Enum):
    """Document scope for generation requests.

    - user: Only search user's personal documents
    - system: Only search admin-uploaded system documents
    - all: Search both (default), with user docs ranked first
    """

    USER = "user"
    SYSTEM = "system"
    ALL = "all"


class GenerationRequest(BaseModel):
    """Request to generate educational game content.

    Submitted to POST /api/v1/generate, processed async via Cloud Tasks.
    """

    user_id: str = Field(..., description="User ID for document scoping")
    document_ids: list[str] | None = Field(
        default=None, description="Specific document IDs to use (optional)"
    )
    topic: str | None = Field(
        default=None, description="Chapter/topic to focus on (optional)"
    )
    game_types: list[GameType] = Field(
        ..., min_length=1, description="Game types to generate (e.g., quiz, flashcard)"
    )
    num_questions: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Number of questions to generate per game type",
    )
    difficulty: DifficultyLevel = Field(
        default=DifficultyLevel.COMPREHENSION, description="Target difficulty level"
    )
    doc_scope: DocScope = Field(
        default=DocScope.ALL, description="Document scope: user, system, or all"
    )
    language: str = Field(
        default="vi", description="Target language for content (ISO 639-1)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "user_id": "user_123",
                    "topic": "Đạo hàm",
                    "game_types": ["quiz", "flashcard"],
                    "num_questions": 10,
                    "difficulty": "comprehension",
                    "doc_scope": "all",
                    "language": "vi",
                }
            ]
        }
    }


class DocumentUploadRequest(BaseModel):
    """Metadata for document upload (file sent as multipart)."""

    user_id: str
    subject: str | None = None


class AdminDocumentUploadRequest(BaseModel):
    """Metadata for admin document upload."""

    subject: str
    grade: str | None = None
