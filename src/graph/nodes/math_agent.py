"""Math Agent node — handles STEM content generation.

The Math Agent (Phase 1) specializes in:
- Mathematics, Physics, Chemistry content
- Uses Code Execution for accurate calculations
- Queries Vertex AI Search for document context

This agent:
1. Retrieves relevant document chunks via Vertex AI Search
2. Generates educational content items using Gemini + Code Execution
3. Includes computation traces for math problems
"""

import structlog
from langchain_google_vertexai import ChatVertexAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from src.graph.state import AgentState
from src.config import get_settings
from src.services.vertex_search import retrieve_context
from src.services.llm import get_generation_llm

logger = structlog.get_logger(__name__)


class GeneratedContentItem(BaseModel):
    """Schema for LLM structured output."""

    question: str = Field(..., description="The question in Vietnamese")
    answer: str = Field(..., description="The correct answer")
    explanation: str = Field(..., description="Explanation in Vietnamese")
    topic: str = Field(..., description="Specific topic")
    computation_trace: str | None = Field(
        default=None, description="Python code and output if calculation was needed"
    )


class ContentItemList(BaseModel):
    """List of generated content items."""

    items: list[GeneratedContentItem]


MATH_AGENT_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are an expert Vietnamese educational content creator specializing in STEM subjects (Math, Physics, Chemistry).

Your task is to generate {num_questions} educational questions based on the provided document context.

REQUIREMENTS:
1. All content MUST be in Vietnamese
2. Questions should be at {difficulty} difficulty level
3. For math/physics problems with calculations:
   - Use Python code to verify your calculations
   - Include the computation trace in your response
4. Each question must have:
   - Clear, unambiguous question text
   - Correct answer
   - Detailed explanation
   - Topic classification
5. Questions should be varied and test different aspects of the topic

CONTEXT FROM DOCUMENTS:
{context}

TOPIC FOCUS: {topic}

Generate exactly {num_questions} questions.""",
        ),
        (
            "human",
            "Generate {num_questions} {difficulty} questions about {topic} based on the context above.",
        ),
    ]
)


def _get_llm() -> ChatVertexAI:
    """Get Gemini LLM for content generation."""
    return get_generation_llm(temperature=0.7, max_output_tokens=8192)


async def math_agent_node(state: AgentState) -> dict:
    """Generate STEM educational content items.

    This node:
    1. Retrieves relevant document context from Vertex AI Search
    2. Generates content items using Gemini with structured output

    Reads:
        - state["request"]: GenerationRequest
        - state["doc_scope"]: Document scope for filtering

    Writes:
        - state["search_context"]: Retrieved document chunks
        - state["search_sources"]: Source metadata
        - state["content_items"]: Generated ContentItems
    """
    request = state["request"]
    doc_scope = state.get("doc_scope", request.doc_scope.value)

    logger.info(
        "math_agent_starting",
        user_id=request.user_id,
        topic=request.topic,
        num_questions=request.num_questions,
        doc_scope=doc_scope,
    )

    # Step 1: Retrieve context from Vertex AI Search
    query = f"{request.topic or 'STEM'} {request.difficulty.value} level educational content"
    search_context, search_sources = await retrieve_context(
        user_id=request.user_id,
        query=query,
        doc_scope=doc_scope,
        max_documents=10,
    )

    logger.info(
        "math_agent_context_retrieved",
        context_chunks=len(search_context),
    )

    # Build context string
    context = (
        "\n\n---\n\n".join(search_context)
        if search_context
        else "No specific context available. Generate based on general knowledge."
    )

    # Generate content using structured output
    llm = _get_llm()
    structured_llm = llm.with_structured_output(ContentItemList)

    chain = MATH_AGENT_PROMPT | structured_llm

    try:
        result: ContentItemList = await chain.ainvoke(
            {
                "num_questions": request.num_questions,
                "difficulty": request.difficulty.value,
                "topic": request.topic or "General STEM",
                "context": context,
            }
        )

        # Convert to dict format for state
        content_items = []
        for i, item in enumerate(result.items):
            # Determine doc_scope from sources
            doc_scope = "system"  # Default
            if search_sources and i < len(search_sources):
                source = search_sources[i]
                doc_scope = source.get("doc_scope", "system")

            content_items.append(
                {
                    "question": item.question,
                    "answer": item.answer,
                    "explanation": item.explanation,
                    "topic": item.topic,
                    "difficulty": request.difficulty.value,
                    "context_source": (
                        search_sources[0].get("source", "unknown")
                        if search_sources
                        else "generated"
                    ),
                    "doc_scope": doc_scope,
                    "computation_trace": item.computation_trace,
                }
            )

        logger.info(
            "math_agent_generated",
            items_count=len(content_items),
        )

    except Exception as e:
        logger.error("math_agent_generation_failed", error=str(e))
        return {
            "search_context": search_context,
            "search_sources": search_sources,
            "content_items": [],
            "errors": [f"Math agent generation failed: {str(e)}"],
        }

    return {
        "search_context": search_context,
        "search_sources": search_sources,
        "content_items": content_items,
    }
