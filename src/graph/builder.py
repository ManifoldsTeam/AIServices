"""LangGraph builder — constructs the StateGraph for content generation.

The graph flow:
1. supervisor → classifies content type, routes to agent
2. math_agent (Phase 1) → retrieves context + generates content items
3. reviewer → quality gate, passes/rejects items
4. formatter → transforms to game-specific output

Conditional edges:
- supervisor → agent (based on content_type)
- reviewer → formatter (pass) or supervisor (fail, up to MAX_ITERATIONS)
"""

import structlog
from langgraph.graph import StateGraph, END

from src.graph.state import AgentState
from src.graph.nodes import (
    supervisor_node,
    route_to_agent,
    math_agent_node,
    reviewer_node,
    review_router,
    formatter_node,
)

logger = structlog.get_logger(__name__)


def create_graph() -> StateGraph:
    """Create the LangGraph StateGraph with all nodes and edges.

    Returns:
        StateGraph ready to be compiled
    """
    logger.info("creating_graph")

    # Initialize graph with state schema
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("math_agent", math_agent_node)
    # Phase 2+: Add specialized agents
    # graph.add_node("story_agent", story_agent_node)
    # graph.add_node("visual_agent", visual_agent_node)
    # graph.add_node("structure_agent", structure_agent_node)
    graph.add_node("reviewer", reviewer_node)
    graph.add_node("formatter", formatter_node)

    # Set entry point
    graph.set_entry_point("supervisor")

    # Add edges from supervisor to agents (conditional routing)
    graph.add_conditional_edges(
        "supervisor",
        route_to_agent,
        {
            "math_agent": "math_agent",
            # Phase 2+
            # "story_agent": "story_agent",
            # "visual_agent": "visual_agent",
            # "structure_agent": "structure_agent",
        },
    )

    # Agent → Reviewer
    graph.add_edge("math_agent", "reviewer")
    # Phase 2+
    # graph.add_edge("story_agent", "reviewer")
    # graph.add_edge("visual_agent", "reviewer")
    # graph.add_edge("structure_agent", "reviewer")

    # Reviewer → Formatter (pass) or Supervisor (fail - feedback loop)
    graph.add_conditional_edges(
        "reviewer",
        review_router,
        {
            "pass": "formatter",
            "fail": "supervisor",  # Retry with feedback
        },
    )

    # Formatter → END
    graph.add_edge("formatter", END)

    logger.info("graph_created")
    return graph


def compile_graph(checkpointer=None):
    """Compile the graph into a runnable app.

    Args:
        checkpointer: Optional checkpointer for state persistence
                     (e.g., Firestore for production)

    Returns:
        Compiled LangGraph app ready for invocation
    """
    graph = create_graph()

    if checkpointer:
        app = graph.compile(checkpointer=checkpointer)
        logger.info("graph_compiled_with_checkpointer")
    else:
        app = graph.compile()
        logger.info("graph_compiled_without_checkpointer")

    return app


# Default compiled graph (without checkpointer, for local testing)
# For production, use compile_graph(checkpointer=firestore_checkpointer)
_graph_app = None


def get_graph_app():
    """Get or create the compiled graph app (singleton).

    For production, this should be initialized with a checkpointer.
    """
    global _graph_app
    if _graph_app is None:
        _graph_app = compile_graph()
    return _graph_app
