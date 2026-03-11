# API schemas package
from .game_content import (
    ContentItem,
    QuizQuestion,
    QuizOption,
    Flashcard,
    FillBlankQuestion,
    BlankSlot,
    GameType,
    DifficultyLevel,
)
from .requests import GenerationRequest, DocScope
from .responses import GameContentResponse, GenerationMetadata, JobStatus

__all__ = [
    # Game content
    "ContentItem",
    "QuizQuestion",
    "QuizOption",
    "Flashcard",
    "FillBlankQuestion",
    "BlankSlot",
    "GameType",
    "DifficultyLevel",
    # Requests
    "GenerationRequest",
    "DocScope",
    # Responses
    "GameContentResponse",
    "GenerationMetadata",
    "JobStatus",
]
