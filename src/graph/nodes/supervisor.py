"""Supervisor node — routes requests to specialized agents.

The Supervisor:
1. Analyzes the generation request (topic, document content)
2. Classifies content type (math, story, visual, structure)
3. Routes to the appropriate specialized agent

Phase 1: Only routes to Math Agent (handles math/physics/chemistry)
Phase 2+: Will route to Story Agent, Visual Agent, Structure Agent
"""

import structlog
from langchain_google_vertexai import ChatVertexAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from src.graph.state import AgentState
from src.config import get_settings

logger = structlog.get_logger(__name__)

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


def _get_llm() -> ChatVertexAI:
    """Get Gemini Pro LLM for supervisor."""
    settings = get_settings()
    return ChatVertexAI(
        model_name="gemini-1.5-flash",  # Fast classification (2.0 not available in asia-southeast1)
        project=settings.gcp_project_id,
        location=settings.gcp_location,
        temperature=0,  # Deterministic classification
        max_output_tokens=10,
    )


async def supervisor_node(state: AgentState) -> dict:
    """Analyze request and classify content type.

    Reads:
        - state["request"]: GenerationRequest
        - state["search_context"]: Retrieved document chunks (optional)

    Writes:
        - state["content_type"]: Classified type for routing
        - state["doc_scope"]: Extracted from request
    """
    request = state["request"]
    search_context = state.get("search_context", [])

    logger.info(
        "supervisor_analyzing",
        user_id=request.user_id,
        topic=request.topic,
        doc_scope=request.doc_scope.value,
    )

    # Build context preview
    context_preview = (
        "\n".join(search_context[:3])[:500] if search_context else "No context yet"
    )

    # Classify content type
    llm = _get_llm()
    chain = SUPERVISOR_PROMPT | llm | StrOutputParser()

    try:
        content_type = await chain.ainvoke(
            {
                "topic": request.topic or "General",
                "doc_scope": request.doc_scope.value,
                "game_types": ", ".join([gt.value for gt in request.game_types]),
                "difficulty": request.difficulty.value,
                "language": request.language,
                "context_preview": context_preview,
            }
        )
        content_type = content_type.strip().lower()

        # Phase 1: Only math is supported, default to math
        if content_type not in ["math"]:
            logger.warning(
                "unsupported_content_type_defaulting_to_math",
                detected=content_type,
            )
            content_type = "math"

    except Exception as e:
        logger.error("supervisor_classification_failed", error=str(e))
        content_type = "math"  # Default fallback

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
