"""Formatter node — transforms content items into game-specific formats.

The Formatter:
1. Takes reviewed content items (Q&A format)
2. Groups them by requested game type
3. Transforms each item using game-specific templates
4. Returns final GameContentResponse

Uses Gemini Flash with structured output for reliable formatting.
"""

import asyncio
import time
import uuid
from datetime import datetime

import structlog
from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from src.config.constants import (
    FORMATTER_BATCH_SIZE,
    STRUCTURED_MAX_TOKENS,
    STRUCTURED_TEMPERATURE,
)
from src.services.llm import get_generation_llm
from src.services.rate_limiter import rate_limited_llm_call

# Retry config for structured output batch parsing
_FORMAT_MAX_RETRIES = 2

from src.graph.state import AgentState
from src.api.schemas import (
    GameType,
    QuizQuestion,
    QuizOption,
    Flashcard,
    FillBlankQuestion,
    BlankSlot,
    GameContentMap,
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


def _get_llm() -> BaseChatModel:
    """Get cached generation LLM for formatting (structured output)."""
    return get_generation_llm(
        temperature=STRUCTURED_TEMPERATURE,
        max_output_tokens=STRUCTURED_MAX_TOKENS,
    )


async def _invoke_batch_with_retry(
    chain,
    batch_items: list[dict],
    label: str,
    json_mod,
    result_field: str = "questions",
) -> list:
    """Invoke structured output chain with retry + per-item fallback.

    Args:
        chain: LCEL chain (prompt | structured_llm)
        batch_items: Items to format in this batch
        label: Log prefix (e.g. "formatter_quiz")
        json_mod: The json module (passed to avoid re-import)
        result_field: Attribute name on the batch result ("questions", "cards")

    Returns:
        List of parsed output objects (may be shorter than batch_items on partial failure)
    """
    invoke_args = {
        "num_items": len(batch_items),
        "items_json": json_mod.dumps(batch_items, ensure_ascii=False, indent=2),
    }

    # --- Attempt full batch with retries ---
    for attempt in range(1, _FORMAT_MAX_RETRIES + 1):
        try:
            result = await rate_limited_llm_call(chain.ainvoke(invoke_args))
            items_out = getattr(result, result_field, None) if result else None
            if items_out is not None:
                if len(items_out) != len(batch_items):
                    logger.warning(
                        f"{label}_count_mismatch",
                        expected=len(batch_items),
                        got=len(items_out),
                        attempt=attempt,
                    )
                logger.info(
                    f"{label}_batch_parsed",
                    items=len(items_out),
                    attempt=attempt,
                )
                return items_out
        except Exception as exc:
            logger.warning(
                f"{label}_batch_error",
                attempt=attempt,
                error=str(exc)[:200],
            )

    # --- Fallback: format items one-by-one ---
    logger.warning(
        f"{label}_batch_failed_falling_back",
        batch_size=len(batch_items),
    )
    results = []
    for idx, single_item in enumerate(batch_items):
        single_args = {
            "num_items": 1,
            "items_json": json_mod.dumps([single_item], ensure_ascii=False, indent=2),
        }
        try:
            result = await rate_limited_llm_call(chain.ainvoke(single_args))
            items_out = getattr(result, result_field, None) if result else None
            if items_out:
                results.extend(items_out)
                logger.debug(f"{label}_single_ok", idx=idx)
            else:
                logger.warning(f"{label}_single_empty", idx=idx)
        except Exception as exc:
            logger.warning(
                f"{label}_single_failed",
                idx=idx,
                error=str(exc)[:200],
            )
    return results


async def _format_quizzes(items: list[dict], llm: BaseChatModel) -> list[QuizQuestion]:
    """Format content items into typed QuizQuestion models with batch parsing."""
    import json

    structured_llm = llm.with_structured_output(QuizBatch)
    all_quiz_outputs: list[tuple[QuizOutput, dict]] = []

    # Batch items to avoid structured output returning None
    for batch_start in range(0, len(items), FORMATTER_BATCH_SIZE):
        batch_items = items[batch_start : batch_start + FORMATTER_BATCH_SIZE]
        chain = QUIZ_PROMPT | structured_llm

        parsed = await _invoke_batch_with_retry(
            chain, batch_items, "formatter_quiz", json
        )

        for i, q in enumerate(parsed):
            source_item = batch_items[i] if i < len(batch_items) else batch_items[-1]
            all_quiz_outputs.append((q, source_item))

    quizzes: list[QuizQuestion] = []
    for q, item in all_quiz_outputs:
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
            difficulty=item.get("difficulty", "comprehension"),
            topic=item.get("topic", ""),
            computation_trace=item.get("computation_trace"),
        )
        quizzes.append(quiz)

    return quizzes


async def _format_flashcards(items: list[dict], llm: BaseChatModel) -> list[Flashcard]:
    """Format content items into typed Flashcard models with batch parsing."""
    import json

    structured_llm = llm.with_structured_output(FlashcardBatch)
    all_fc_outputs: list[tuple[FlashcardOutput, dict]] = []

    for batch_start in range(0, len(items), FORMATTER_BATCH_SIZE):
        batch_items = items[batch_start : batch_start + FORMATTER_BATCH_SIZE]
        chain = FLASHCARD_PROMPT | structured_llm

        parsed = await _invoke_batch_with_retry(
            chain, batch_items, "formatter_flashcard", json, result_field="cards"
        )

        for i, f in enumerate(parsed):
            source_item = batch_items[i] if i < len(batch_items) else batch_items[-1]
            all_fc_outputs.append((f, source_item))

    flashcards: list[Flashcard] = []
    for f, item in all_fc_outputs:
        flashcard = Flashcard(
            id=str(uuid.uuid4()),
            front=f.front,
            back=f.back,
            topic=item.get("topic", ""),
            difficulty=item.get("difficulty", "comprehension"),
            tags=f.tags,
        )
        flashcards.append(flashcard)

    return flashcards


async def _format_fill_blanks(
    items: list[dict], llm: BaseChatModel
) -> list[FillBlankQuestion]:
    """Format content items into typed FillBlankQuestion models with batch parsing."""
    import json

    structured_llm = llm.with_structured_output(FillBlankBatch)
    all_fb_outputs: list[tuple[FillBlankOutput, dict]] = []

    for batch_start in range(0, len(items), FORMATTER_BATCH_SIZE):
        batch_items = items[batch_start : batch_start + FORMATTER_BATCH_SIZE]
        chain = FILL_BLANK_PROMPT | structured_llm

        parsed = await _invoke_batch_with_retry(
            chain, batch_items, "formatter_fill_blank", json
        )

        for i, fb in enumerate(parsed):
            source_item = batch_items[i] if i < len(batch_items) else batch_items[-1]
            all_fb_outputs.append((fb, source_item))

    fill_blanks: list[FillBlankQuestion] = []
    for fb, item in all_fb_outputs:
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
            difficulty=item.get("difficulty", "comprehension"),
            topic=item.get("topic", ""),
        )
        fill_blanks.append(fill_blank)

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

    # Trim to requested count (overshoot buffer may produce extras)
    if len(reviewed_items) > request.num_questions:
        logger.info(
            "formatter_trimming",
            before=len(reviewed_items),
            after=request.num_questions,
        )
        reviewed_items = reviewed_items[: request.num_questions]

    start_time = time.time()

    logger.info(
        "formatter_starting",
        user_id=request.user_id,
        game_types=[gt.value for gt in request.game_types],
        items_count=len(reviewed_items),
    )

    if not reviewed_items:
        logger.warning("formatter_no_items")
        final_output = GameContentResponse(
            request_id=str(uuid.uuid4()),
            user_id=request.user_id,
            generated_at=datetime.utcnow(),
            content=GameContentMap(),
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
    quiz_items: list[QuizQuestion] = []
    flashcard_items: list[Flashcard] = []
    fill_blank_items: list[FillBlankQuestion] = []

    # Format all requested game types in parallel (they are independent)
    async def _safe_format(game_type: GameType):
        try:
            if game_type == GameType.QUIZ:
                return game_type, await _format_quizzes(reviewed_items, llm)
            elif game_type == GameType.FLASHCARD:
                return game_type, await _format_flashcards(reviewed_items, llm)
            elif game_type == GameType.FILL_BLANK:
                return game_type, await _format_fill_blanks(reviewed_items, llm)
            else:
                logger.warning("formatter_unsupported_type", game_type=game_type.value)
                return game_type, []
        except Exception as e:
            logger.error(
                "formatter_type_failed",
                game_type=game_type.value,
                error=str(e),
            )
            return game_type, []

    results = await asyncio.gather(*[_safe_format(gt) for gt in request.game_types])
    for game_type, items in results:
        if game_type == GameType.QUIZ:
            quiz_items = items
        elif game_type == GameType.FLASHCARD:
            flashcard_items = items
        elif game_type == GameType.FILL_BLANK:
            fill_blank_items = items

    content = GameContentMap(
        quiz=quiz_items,
        flashcard=flashcard_items,
        fill_blank=fill_blank_items,
    )

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

    total_items = len(quiz_items) + len(flashcard_items) + len(fill_blank_items)
    logger.info(
        "formatter_completed",
        total_items=total_items,
        quiz=len(quiz_items),
        flashcard=len(flashcard_items),
        fill_blank=len(fill_blank_items),
        generation_time=generation_time,
    )

    return {"final_output": final_output}
