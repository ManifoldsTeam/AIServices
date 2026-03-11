"""Formatter node — transforms content items into game-specific formats.

The Formatter:
1. Takes reviewed content items (Q&A format)
2. Groups them by requested game type
3. Transforms each item using game-specific templates
4. Returns final GameContentResponse

Uses Gemini Flash with structured output for reliable formatting.
"""

import time
import uuid
from datetime import datetime

import structlog
from langchain_google_vertexai import ChatVertexAI
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from src.graph.state import AgentState
from src.api.schemas import (
    GameType,
    QuizQuestion,
    QuizOption,
    Flashcard,
    FillBlankQuestion,
    BlankSlot,
    GameContentResponse,
    GenerationMetadata,
)
from src.config import get_settings

logger = structlog.get_logger(__name__)


# --- Quiz Formatter ---
class QuizOutput(BaseModel):
    """Structured output for quiz questions."""

    question: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_index: int = Field(..., ge=0, le=3, description="0=A, 1=B, 2=C, 3=D")
    explanation: str


class QuizBatch(BaseModel):
    """Batch of quiz questions."""

    questions: list[QuizOutput]


QUIZ_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """Transform educational content items into multiple-choice quiz questions.

For each content item:
1. Use the question as-is or rephrase for clarity
2. Create 4 plausible options (A, B, C, D)
3. Make distractors believable but clearly wrong
4. Include the correct answer among options
5. Keep explanations concise

All content must be in Vietnamese.""",
        ),
        (
            "human",
            """Transform these {num_items} content items into quiz questions:

{items_json}""",
        ),
    ]
)


# --- Flashcard Formatter ---
class FlashcardOutput(BaseModel):
    """Structured output for flashcard."""

    front: str = Field(..., description="Question/concept/formula")
    back: str = Field(..., description="Answer with explanation")
    tags: list[str] = Field(default_factory=list)


class FlashcardBatch(BaseModel):
    """Batch of flashcards."""

    cards: list[FlashcardOutput]


FLASHCARD_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """Transform educational content items into flashcards.

For each content item:
1. Front: The question or key concept/formula
2. Back: The answer with a brief explanation
3. Tags: Relevant topic tags

Keep content concise and memorable. All in Vietnamese.""",
        ),
        (
            "human",
            """Transform these {num_items} content items into flashcards:

{items_json}""",
        ),
    ]
)


# --- Fill-in-blank Formatter ---
class FillBlankOutput(BaseModel):
    """Structured output for fill-in-blank."""

    template: str = Field(..., description="Sentence with ___ for blanks")
    blanks: list[str] = Field(..., description="List of correct answers in order")
    hints: list[str] = Field(
        default_factory=list, description="Optional hints for each blank"
    )
    explanation: str


class FillBlankBatch(BaseModel):
    """Batch of fill-in-blank questions."""

    questions: list[FillBlankOutput]


FILL_BLANK_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """Transform educational content items into fill-in-the-blank questions.

For each content item:
1. Create a sentence/statement with blanks (use ___ for each blank)
2. Blanks should test key concepts from the answer
3. Include hints if helpful
4. Keep explanations brief

All content in Vietnamese.""",
        ),
        (
            "human",
            """Transform these {num_items} content items into fill-in-blank questions:

{items_json}""",
        ),
    ]
)


def _get_llm() -> ChatVertexAI:
    """Get Gemini Flash LLM for formatting."""
    settings = get_settings()
    return ChatVertexAI(
        model_name="gemini-1.5-flash",  # 2.0 not available in asia-southeast1
        project=settings.gcp_project_id,
        location=settings.gcp_location,
        temperature=0.3,  # Some creativity in options
        max_output_tokens=8192,
    )


async def _format_quizzes(items: list[dict], llm: ChatVertexAI) -> list[dict]:
    """Format content items into quiz questions."""
    import json

    structured_llm = llm.with_structured_output(QuizBatch)
    chain = QUIZ_PROMPT | structured_llm

    result: QuizBatch = await chain.ainvoke(
        {
            "num_items": len(items),
            "items_json": json.dumps(items, ensure_ascii=False, indent=2),
        }
    )

    quizzes = []
    for i, q in enumerate(result.questions):
        item = items[i] if i < len(items) else items[-1]
        quiz = QuizQuestion(
            id=str(uuid.uuid4()),
            question=q.question,
            options=[
                QuizOption(text=q.option_a, is_correct=(q.correct_index == 0)),
                QuizOption(text=q.option_b, is_correct=(q.correct_index == 1)),
                QuizOption(text=q.option_c, is_correct=(q.correct_index == 2)),
                QuizOption(text=q.option_d, is_correct=(q.correct_index == 3)),
            ],
            correct_answer_index=q.correct_index,
            explanation=q.explanation,
            difficulty=item.get("difficulty", "medium"),
            topic=item.get("topic", ""),
            computation_trace=item.get("computation_trace"),
        )
        quizzes.append(quiz.model_dump())

    return quizzes


async def _format_flashcards(items: list[dict], llm: ChatVertexAI) -> list[dict]:
    """Format content items into flashcards."""
    import json

    structured_llm = llm.with_structured_output(FlashcardBatch)
    chain = FLASHCARD_PROMPT | structured_llm

    result: FlashcardBatch = await chain.ainvoke(
        {
            "num_items": len(items),
            "items_json": json.dumps(items, ensure_ascii=False, indent=2),
        }
    )

    flashcards = []
    for i, f in enumerate(result.cards):
        item = items[i] if i < len(items) else items[-1]
        flashcard = Flashcard(
            id=str(uuid.uuid4()),
            front=f.front,
            back=f.back,
            topic=item.get("topic", ""),
            difficulty=item.get("difficulty", "medium"),
            tags=f.tags,
        )
        flashcards.append(flashcard.model_dump())

    return flashcards


async def _format_fill_blanks(items: list[dict], llm: ChatVertexAI) -> list[dict]:
    """Format content items into fill-in-blank questions."""
    import json

    structured_llm = llm.with_structured_output(FillBlankBatch)
    chain = FILL_BLANK_PROMPT | structured_llm

    result: FillBlankBatch = await chain.ainvoke(
        {
            "num_items": len(items),
            "items_json": json.dumps(items, ensure_ascii=False, indent=2),
        }
    )

    fill_blanks = []
    for i, fb in enumerate(result.questions):
        item = items[i] if i < len(items) else items[-1]
        blanks = [
            BlankSlot(
                position=j,
                correct_answer=answer,
                hint=fb.hints[j] if j < len(fb.hints) else None,
            )
            for j, answer in enumerate(fb.blanks)
        ]
        fill_blank = FillBlankQuestion(
            id=str(uuid.uuid4()),
            template=fb.template,
            blanks=blanks,
            explanation=fb.explanation,
            difficulty=item.get("difficulty", "medium"),
            topic=item.get("topic", ""),
        )
        fill_blanks.append(fill_blank.model_dump())

    return fill_blanks


async def formatter_node(state: AgentState) -> dict:
    """Transform reviewed items into game-specific formats.

    Reads:
        - state["request"]: GenerationRequest (for game_types, user_id)
        - state["reviewed_items"]: Content items that passed review
        - state["rejected_items"]: Items that failed review (for metadata)

    Writes:
        - state["final_output"]: GameContentResponse
    """
    request = state["request"]
    reviewed_items = state.get("reviewed_items", [])
    rejected_items = state.get("rejected_items", [])

    start_time = time.time()

    logger.info(
        "formatter_starting",
        user_id=request.user_id,
        game_types=[gt.value for gt in request.game_types],
        items_count=len(reviewed_items),
    )

    if not reviewed_items:
        logger.warning("formatter_no_items")
        # Return empty response
        final_output = GameContentResponse(
            request_id=str(uuid.uuid4()),
            user_id=request.user_id,
            generated_at=datetime.utcnow(),
            content={gt.value: [] for gt in request.game_types},
            metadata=GenerationMetadata(
                total_generated=0,
                total_passed_review=0,
                total_rejected=len(rejected_items),
                generation_time_seconds=time.time() - start_time,
                model_used=get_settings().generation_model,
                game_types_generated=[gt.value for gt in request.game_types],
            ),
        )
        return {"final_output": final_output}

    llm = _get_llm()
    content = {}

    # Format for each requested game type
    for game_type in request.game_types:
        try:
            if game_type == GameType.QUIZ:
                content[game_type.value] = await _format_quizzes(reviewed_items, llm)
            elif game_type == GameType.FLASHCARD:
                content[game_type.value] = await _format_flashcards(reviewed_items, llm)
            elif game_type == GameType.FILL_BLANK:
                content[game_type.value] = await _format_fill_blanks(
                    reviewed_items, llm
                )
            else:
                logger.warning("formatter_unsupported_type", game_type=game_type.value)
                content[game_type.value] = []

        except Exception as e:
            logger.error(
                "formatter_type_failed",
                game_type=game_type.value,
                error=str(e),
            )
            content[game_type.value] = []

    generation_time = time.time() - start_time

    final_output = GameContentResponse(
        request_id=str(uuid.uuid4()),
        user_id=request.user_id,
        generated_at=datetime.utcnow(),
        content=content,
        metadata=GenerationMetadata(
            total_generated=len(reviewed_items) + len(rejected_items),
            total_passed_review=len(reviewed_items),
            total_rejected=len(rejected_items),
            generation_time_seconds=generation_time,
            model_used=get_settings().generation_model,
            game_types_generated=[gt.value for gt in request.game_types],
        ),
    )

    logger.info(
        "formatter_completed",
        game_types={gt: len(items) for gt, items in content.items()},
        generation_time=generation_time,
    )

    return {"final_output": final_output}
