"""Supervisor node — routes requests to specialized agents.

The Supervisor:
1. Analyzes the generation request (topic, document content)
2. Classifies content type (math, story, visual, structure)
3. Routes to the appropriate specialized agent

Phase 1: Only routes to Math Agent (handles math/physics/chemistry)
Phase 2+: Will route to Story Agent, Visual Agent, Structure Agent

T-OPT-3.3: Phase 1 uses deterministic routing (no LLM call) since only
"math" is supported. When Phase 2+ agents are added, re-enable LLM
classification by setting USE_LLM_CLASSIFICATION = True.
"""

import structlog
from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from src.graph.state import AgentState
from src.config import get_settings
from src.services.llm import get_review_llm
from src.services.rate_limiter import rate_limited_llm_call

logger = structlog.get_logger(__name__)

# T-OPT-3.3: Disable LLM classification in Phase 1 (only "math" supported).
# Set to True when Phase 2+ agents are added.
USE_LLM_CLASSIFICATION: bool = False

# Content type classification prompt
SUPERVISOR_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are a content classifier for an educational game system.
Analyze the request and classify the primary content type.

Available content types:
- math: Mathematics, Physics, Chemistry - requires calculations, formulas, equations
- story: History, Literature, Social studies - requires narrative, timeline, causality
- visual: Geography, Biology - requires spatial understanding, diagrams, images
- structure: Grammar, Tables, Structured data - requires pattern matching, parsing

For Phase 1, only "math" is supported. Classify as "math" for any STEM content.

Respond with ONLY the content type (one word, lowercase).""",
        ),
        (
            "human",
            """Request:
Topic: {topic}
Document scope: {doc_scope}
Game types: {game_types}
Difficulty: {difficulty}
Language: {language}

Retrieved context (first 500 chars):
{context_preview}

What is the content type?""",
        ),
    ]
)


def _get_llm() -> BaseChatModel:
    """Get Gemini LLM for supervisor classification."""
    return get_review_llm(temperature=0, max_output_tokens=10)


async def supervisor_node(state: AgentState) -> dict:
    """Analyze request and classify content type.

    T-OPT-3.3: When USE_LLM_CLASSIFICATION is False (Phase 1), skips the
    LLM call entirely and defaults to "math" — saves ~3-5s per run.

    Reads:
        - state["request"]: GenerationRequest
        - state["search_context"]: Retrieved document chunks (optional)

    Writes:
        - state["content_type"]: Classified type for routing
        - state["doc_scope"]: Extracted from request
    """
    request = state["request"]

    logger.info(
        "supervisor_analyzing",
        user_id=request.user_id,
        topic=request.topic,
        doc_scope=request.doc_scope.value,
    )

    if not USE_LLM_CLASSIFICATION:
        # T-OPT-3.3: Deterministic routing — Phase 1 only supports "math"
        content_type = "math"
        logger.info(
            "supervisor_deterministic",
            content_type=content_type,
            reason="Phase 1 — USE_LLM_CLASSIFICATION=False",
        )
    else:
        # Phase 2+: LLM-based classification
        search_context = state.get("search_context", [])
        context_preview = (
            "\n".join(search_context[:3])[:500]
            if search_context
            else "No context yet"
        )

        llm = _get_llm()
        chain = SUPERVISOR_PROMPT | llm | StrOutputParser()

        try:
            content_type = await rate_limited_llm_call(
                chain.ainvoke(
                    {
                        "topic": request.topic or "General",
                        "doc_scope": request.doc_scope.value,
                        "game_types": ", ".join(
                            [gt.value for gt in request.game_types]
                        ),
                        "difficulty": request.difficulty.value,
                        "language": request.language,
                        "context_preview": context_preview,
                    }
                )
            )
            content_type = content_type.strip().lower()

            if content_type not in ["math"]:
                logger.warning(
                    "unsupported_content_type_defaulting_to_math",
                    detected=content_type,
                )
                content_type = "math"

        except Exception as e:
            logger.error("supervisor_classification_failed", error=str(e))
            content_type = "math"

    logger.info("supervisor_classified", content_type=content_type)

    return {
        "content_type": content_type,
        "doc_scope": request.doc_scope.value,
        "iteration_count": state.get("iteration_count", 0),
    }


def route_to_agent(state: AgentState) -> str:
    """Route to specialized agent based on content type.

    Phase 1: Only routes to math_agent
    Phase 2+: Will route to story_agent, visual_agent, structure_agent
    """
    content_type = state.get("content_type", "math")

    # Phase 1: All routes go to math_agent
    routing_map = {
        "math": "math_agent",
        # Phase 2+
        # "story": "story_agent",
        # "visual": "visual_agent",
        # "structure": "structure_agent",
    }

    route = routing_map.get(content_type, "math_agent")
    logger.info("routing_to_agent", content_type=content_type, route=route)

    return route
