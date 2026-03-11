"""Reviewer node — quality gate for generated content.

The Reviewer:
1. Evaluates each content item for quality
2. Checks accuracy, relevance, clarity, and educational value
3. Passes good items, rejects poor ones
4. Provides feedback for rejected items

Uses Gemini Flash for fast review (cost-effective).
"""

import structlog
from langchain_google_vertexai import ChatVertexAI
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from src.graph.state import AgentState, MAX_REVIEW_ITERATIONS
from src.config import get_settings
from src.services.llm import get_review_llm

logger = structlog.get_logger(__name__)


class ReviewResult(BaseModel):
    """Review result for a single content item."""

    item_index: int
    passed: bool
    score: float = Field(..., ge=0, le=1, description="Quality score 0-1")
    feedback: str = Field(..., description="Feedback for improvement if rejected")


class ReviewBatch(BaseModel):
    """Batch review results."""

    reviews: list[ReviewResult]


REVIEWER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are a quality reviewer for Vietnamese educational content.

Review each content item and evaluate:
1. **Accuracy** (40%): Is the answer correct? Is the explanation accurate?
2. **Clarity** (25%): Is the question clear and unambiguous?
3. **Educational Value** (20%): Does it effectively test the concept?
4. **Vietnamese Quality** (15%): Is the Vietnamese natural and correct?

PASS if score >= 0.7
REJECT if score < 0.7

For math/physics with computation_trace:
- Verify the calculation is correct
- Ensure the answer matches the computation

Be strict but fair. Educational content must be accurate.""",
        ),
        (
            "human",
            """Review these {num_items} content items:

{items_json}

For each item (0-indexed), provide:
- item_index: the index
- passed: true/false
- score: 0.0-1.0
- feedback: specific improvement suggestions if rejected""",
        ),
    ]
)


def _get_llm() -> ChatVertexAI:
    """Get Gemini Flash LLM for fast review."""
    return get_review_llm(temperature=0.0, max_output_tokens=4096)


async def reviewer_node(state: AgentState) -> dict:
    """Review generated content items for quality.

    Reads:
        - state["content_items"]: Generated ContentItems to review
        - state["iteration_count"]: Current feedback loop iteration

    Writes:
        - state["reviewed_items"]: Items that passed review
        - state["rejected_items"]: Items that failed (accumulated)
        - state["iteration_count"]: Incremented iteration count
    """
    content_items = state.get("content_items", [])
    iteration_count = state.get("iteration_count", 0)

    if not content_items:
        logger.warning("reviewer_no_items_to_review")
        return {
            "reviewed_items": [],
            "iteration_count": iteration_count + 1,
        }

    logger.info(
        "reviewer_reviewing",
        items_count=len(content_items),
        iteration=iteration_count,
    )

    # Format items for review
    import json

    items_json = json.dumps(content_items, ensure_ascii=False, indent=2)

    # Review using structured output
    llm = _get_llm()
    structured_llm = llm.with_structured_output(ReviewBatch)

    chain = REVIEWER_PROMPT | structured_llm

    try:
        result: ReviewBatch = await chain.ainvoke(
            {
                "num_items": len(content_items),
                "items_json": items_json,
            }
        )

        reviewed_items = []
        rejected_items = []

        for review in result.reviews:
            if review.item_index < len(content_items):
                item = content_items[review.item_index].copy()
                item["review_score"] = review.score

                if review.passed:
                    reviewed_items.append(item)
                else:
                    item["review_feedback"] = review.feedback
                    rejected_items.append(item)

        logger.info(
            "reviewer_completed",
            passed=len(reviewed_items),
            rejected=len(rejected_items),
            iteration=iteration_count,
        )

    except Exception as e:
        logger.error("reviewer_failed", error=str(e))
        # On error, pass all items through (fail-open for resilience)
        reviewed_items = content_items
        rejected_items = []

    return {
        "reviewed_items": reviewed_items,
        "rejected_items": rejected_items,
        "iteration_count": iteration_count + 1,
    }


def review_router(state: AgentState) -> str:
    """Route based on review results and iteration count.

    Returns:
        - "pass": Enough items passed, proceed to formatter
        - "fail": Need more items, retry with supervisor (if iterations remain)
    """
    reviewed_items = state.get("reviewed_items", [])
    rejected_items = state.get("rejected_items", [])
    iteration_count = state.get("iteration_count", 0)
    request = state["request"]

    # Calculate pass rate
    total = len(reviewed_items) + len(rejected_items)
    pass_rate = len(reviewed_items) / total if total > 0 else 0

    logger.info(
        "review_router_deciding",
        reviewed=len(reviewed_items),
        rejected=len(rejected_items),
        pass_rate=pass_rate,
        iteration=iteration_count,
        max_iterations=MAX_REVIEW_ITERATIONS,
    )

    # Pass conditions:
    # 1. Have enough reviewed items (at least 70% of requested)
    # 2. Or reached max iterations
    min_required = int(request.num_questions * 0.7)

    if len(reviewed_items) >= min_required:
        logger.info("review_router_pass", reason="sufficient_items")
        return "pass"

    if iteration_count >= MAX_REVIEW_ITERATIONS:
        logger.warning(
            "review_router_pass_max_iterations",
            reviewed=len(reviewed_items),
            required=min_required,
        )
        return "pass"  # Accept what we have

    logger.info(
        "review_router_fail",
        reason="insufficient_items",
        have=len(reviewed_items),
        need=min_required,
    )
    return "fail"
