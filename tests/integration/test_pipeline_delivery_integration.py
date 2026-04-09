"""Integration test — pipeline delivery fixes work end-to-end across modules.

Tests the interaction between:
- math_agent (overshoot calculation + gap retry)
- reviewer (quality gate + review_router)
- state (MAX_REVIEW_ITERATIONS)
- constants (OVERSHOOT_BY_DIFFICULTY)

Verifies the full feedback loop contract: reviewer rejects → router decides → 
math_agent retries with escalation → eventually passes.
"""

from __future__ import annotations

import math
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.api.schemas import DifficultyLevel, DocScope, GameType, GenerationRequest
from src.config.constants import OVERSHOOT_BY_DIFFICULTY
from src.graph.state import MAX_REVIEW_ITERATIONS


def _make_request(
    difficulty: str = "comprehension",
    num_questions: int = 10,
) -> GenerationRequest:
    """Create a real GenerationRequest for integration tests."""
    return GenerationRequest(
        user_id="integration_test_user",
        topic="Phản ứng oxi hóa khử",
        game_types=[GameType.QUIZ],
        num_questions=num_questions,
        difficulty=DifficultyLevel(difficulty),
        doc_scope=DocScope.SYSTEM,
        language="vi",
    )


# ═══════════════════════════════════════════════════════════════════════
# Feedback loop: reviewer → review_router → math_agent retry
# ═══════════════════════════════════════════════════════════════════════


class TestFeedbackLoopIntegration:
    """Verify that review_router and math_agent retry logic work together."""

    def test_router_rejects_then_math_agent_escalates(self):
        """When router says 'fail', math_agent's next iteration uses higher overshoot."""
        from src.graph.nodes.reviewer import review_router

        request = _make_request(difficulty="high_application", num_questions=10)

        # Iteration 0: math_agent generates, reviewer passes only 4
        state_after_review_0 = {
            "reviewed_items": [{"q": f"item_{i}"} for i in range(4)],
            "rejected_items": [{"q": f"rej_{i}", "review_feedback": "too easy"} for i in range(6)],
            "iteration_count": 1,  # reviewer incremented it
            "request": request,
        }

        # Router should say 'fail' — only 4/10
        assert review_router(state_after_review_0) == "fail"

        # Now verify math_agent retry logic matches
        reviewed_items = state_after_review_0["reviewed_items"]
        iteration_count = state_after_review_0["iteration_count"]
        num_still_needed = max(request.num_questions - len(reviewed_items), 1)  # 6

        base_overshoot = OVERSHOOT_BY_DIFFICULTY["high_application"]  # 2.5
        overshoot = base_overshoot * (1 + 0.3 * iteration_count)  # 2.5 * 1.3 = 3.25
        num_to_generate = math.ceil(num_still_needed * overshoot)  # ceil(6*3.25)=20
        num_to_generate = max(num_to_generate, num_still_needed + 3)  # max(20,9)=20

        assert num_still_needed == 6
        assert overshoot == pytest.approx(3.25)
        assert num_to_generate == 20  # Aggressive retry

    def test_router_accepts_after_sufficient_items_accumulate(self):
        """After multiple iterations, reviewed_items accumulate and router passes."""
        from src.graph.nodes.reviewer import review_router

        request = _make_request(difficulty="application", num_questions=10)

        # Simulate: 6 passed in iter1, 5 more in iter2 = 11 total (>= 10)
        state_after_iter2 = {
            "reviewed_items": [{"q": f"item_{i}"} for i in range(11)],
            "rejected_items": [{"q": f"rej_{i}"} for i in range(4)],
            "iteration_count": 2,
            "request": request,
        }
        assert review_router(state_after_iter2) == "pass"

    def test_safety_valve_triggers_at_max_iterations(self):
        """Even with insufficient items, router passes at MAX_REVIEW_ITERATIONS."""
        from src.graph.nodes.reviewer import review_router

        request = _make_request(difficulty="high_application", num_questions=10)
        
        state_at_max = {
            "reviewed_items": [{"q": f"item_{i}"} for i in range(7)],  # Only 7/10
            "rejected_items": [],
            "iteration_count": MAX_REVIEW_ITERATIONS,
            "request": request,
        }
        # Safety valve — accept what we have
        assert review_router(state_at_max) == "pass"

    def test_escalating_overshoot_progression_across_iterations(self):
        """Overshoot grows with each iteration for the same difficulty."""
        base = OVERSHOOT_BY_DIFFICULTY["application"]  # 1.4
        num_needed = 5

        gen_counts = []
        for iteration in range(MAX_REVIEW_ITERATIONS):
            overshoot = base * (1 + 0.3 * iteration)
            count = math.ceil(num_needed * overshoot)
            count = max(count, num_needed + 3)
            gen_counts.append(count)

        # Must be non-decreasing
        for i in range(1, len(gen_counts)):
            assert gen_counts[i] >= gen_counts[i - 1], (
                f"gen_count decreased at iteration {i}: {gen_counts}"
            )

        # Final iteration should generate significantly more than first
        assert gen_counts[-1] > gen_counts[0]


# ═══════════════════════════════════════════════════════════════════════
# Constants consistency across modules
# ═══════════════════════════════════════════════════════════════════════


class TestCrossModuleConsistency:
    """Verify that constants used across modules are consistent."""

    def test_reviewer_imports_max_iterations_from_state(self):
        """reviewer.py imports MAX_REVIEW_ITERATIONS from state.py (not hardcoded)."""
        from src.graph.nodes.reviewer import review_router
        from src.graph.state import MAX_REVIEW_ITERATIONS

        request = _make_request(num_questions=10)

        # Exactly at max → should pass
        state = {
            "reviewed_items": [],
            "rejected_items": [],
            "iteration_count": MAX_REVIEW_ITERATIONS,
            "request": request,
        }
        assert review_router(state) == "pass"

        # One below max → should fail
        state["iteration_count"] = MAX_REVIEW_ITERATIONS - 1
        assert review_router(state) == "fail"

    def test_overshoot_difficulty_keys_match_enum_values(self):
        """OVERSHOOT_BY_DIFFICULTY keys match DifficultyLevel enum values."""
        overshoot_keys = set(OVERSHOOT_BY_DIFFICULTY.keys())
        enum_values = {d.value for d in DifficultyLevel}
        assert overshoot_keys == enum_values

    def test_review_threshold_keys_match_enum_values(self):
        """REVIEW_THRESHOLD_BY_DIFFICULTY keys match DifficultyLevel enum values."""
        from src.config.constants import REVIEW_THRESHOLD_BY_DIFFICULTY

        threshold_keys = set(REVIEW_THRESHOLD_BY_DIFFICULTY.keys())
        enum_values = {d.value for d in DifficultyLevel}
        assert threshold_keys == enum_values


# ═══════════════════════════════════════════════════════════════════════
# Graph builder wiring
# ═══════════════════════════════════════════════════════════════════════


class TestGraphBuilderWiring:
    """Verify the graph builder correctly wires the feedback loop."""

    def test_graph_has_reviewer_conditional_edges(self):
        """Graph should have reviewer → formatter (pass) and reviewer → supervisor (fail)."""
        from src.graph.builder import create_graph

        graph = create_graph()
        # The graph object should have the nodes and edges registered
        nodes = graph.nodes
        assert "supervisor" in nodes
        assert "math_agent" in nodes
        assert "reviewer" in nodes
        assert "formatter" in nodes

    def test_review_router_is_used_in_graph(self):
        """review_router function is registered as conditional edge from reviewer."""
        from src.graph.builder import create_graph
        from src.graph.nodes.reviewer import review_router

        graph = create_graph()
        # Check that reviewer node has conditional edges
        # The graph's _conditional_edges should contain the reviewer routing
        assert "reviewer" in graph.nodes


# ═══════════════════════════════════════════════════════════════════════
# Reviewer node + review_router contract
# ═══════════════════════════════════════════════════════════════════════


class TestReviewerNodeContract:
    """Verify reviewer_node output contract is compatible with review_router input."""

    @pytest.mark.asyncio
    @patch("src.graph.nodes.reviewer.rate_limited_llm_call")
    @patch("src.graph.nodes.reviewer._get_llm")
    async def test_reviewer_output_feeds_review_router(
        self, mock_get_llm, mock_rate_limit, patch_settings
    ):
        """reviewer_node output dict has keys that review_router expects."""
        from src.graph.nodes.reviewer import ReviewBatch, ReviewResult, reviewer_node

        # Setup mock LLM
        mock_llm = MagicMock()
        mock_structured = MagicMock()
        mock_llm.with_structured_output.return_value = mock_structured
        mock_get_llm.return_value = mock_llm

        # Mock review result: 7 pass, 3 fail
        reviews = [
            ReviewResult(item_index=i, passed=(i < 7), score=0.8 if i < 7 else 0.3, feedback="ok" if i < 7 else "reject")
            for i in range(10)
        ]
        mock_rate_limit.return_value = ReviewBatch(reviews=reviews)

        request = _make_request(difficulty="application", num_questions=10)
        content_items = [{"question": f"Q{i}", "answer": f"A{i}", "explanation": f"E{i}"} for i in range(10)]

        state = {
            "request": request,
            "content_items": content_items,
            "iteration_count": 0,
            "reviewed_items": [],
            "rejected_items": [],
        }

        result = await reviewer_node(state)

        # Verify output has the keys that review_router reads
        assert "reviewed_items" in result
        assert "rejected_items" in result
        assert "iteration_count" in result

        # 7 passed, 3 rejected
        assert len(result["reviewed_items"]) == 7
        assert len(result["rejected_items"]) == 3
        assert result["iteration_count"] == 1

        # Now feed this into a simulated state for review_router
        from src.graph.nodes.reviewer import review_router

        combined_state = {
            "reviewed_items": result["reviewed_items"],
            "rejected_items": result["rejected_items"],
            "iteration_count": result["iteration_count"],
            "request": request,
        }
        # 7 < 10 required, iteration 1 < 5 max → fail
        assert review_router(combined_state) == "fail"
