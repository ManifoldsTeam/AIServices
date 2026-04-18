"""LangGraph state definition for Edu Game AI Service.

AgentState is the central TypedDict that flows through all nodes in the graph.
All business logic reads from and writes to this state.
"""

from typing import TypedDict, Annotated
from operator import add

from src.api.schemas import GenerationRequest, GameContentResponse


class AgentState(TypedDict, total=False):
    """State that flows through the LangGraph pipeline.

    Fields:
        request: Original generation request from user
        doc_scope: Document scope filter ("user", "system", "all")
        content_type: Detected content type for routing (e.g., "math", "story")

        search_context: Retrieved document chunks from Vertex AI Search
        search_sources: Source metadata for retrieved chunks (doc_id, page, etc.)

        content_items: Generated ContentItems (generic Q&A format)
        reviewed_items: Items that passed quality review
        rejected_items: Items that failed review (accumulated via add operator)

        iteration_count: Current feedback loop iteration (max 5)

        final_output: Final GameContentResponse after formatting
        errors: Error messages accumulated during processing
    """

    # Input
    request: GenerationRequest
    doc_scope: str
    content_type: str

    # Retrieval
    search_context: list[str]
    search_sources: list[dict]

    # Generation
    content_items: list[dict]

    # Review
    reviewed_items: Annotated[list[dict], add]  # Accumulate across iterations
    rejected_items: Annotated[list[dict], add]  # Accumulate across iterations

    # Control flow
    iteration_count: int

    # Output
    final_output: GameContentResponse | None
    errors: Annotated[list[str], add]  # Accumulate errors


# Constants
MAX_REVIEW_ITERATIONS = 5
