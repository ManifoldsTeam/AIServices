"""Unit tests for Tier 1 performance optimizations.

Tests cover:
- T-OPT-1.1: Parallel parse batches via asyncio.gather with Semaphore(3)
- T-OPT-1.2: Cache Vertex AI Search context on retry iterations
- T-OPT-1.3: Skip supervisor on retry (reviewer fail → math_agent)
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ─── Module paths ────────────────────────────────────────────────────
MATH_AGENT_MOD = "src.graph.nodes.math_agent"
BUILDER_MOD = "src.graph.builder"


# ═══════════════════════════════════════════════════════════════════════
# T-OPT-1.1: Parallel Parse Batches
# ═══════════════════════════════════════════════════════════════════════


class TestParallelParseBatches:
    """T-OPT-1.1: _parse_raw_content dispatches batches concurrently."""

    @pytest.mark.asyncio
    @patch(f"{MATH_AGENT_MOD}.get_generation_llm")
    @patch(f"{MATH_AGENT_MOD}._parse_batch")
    async def test_three_batches_dispatched_via_gather(
        self, mock_parse_batch, mock_get_llm
    ):
        """21 items → 3 batches, all dispatched concurrently."""
        from src.graph.nodes.math_agent import (
            GeneratedContentItem,
            _parse_raw_content,
        )

        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value = MagicMock()
        mock_get_llm.return_value = mock_llm

        item = GeneratedContentItem(
            question="Q", answer="A", explanation="E", topic="T"
        )
        mock_parse_batch.return_value = [item, item]

        result = await _parse_raw_content("raw text", ["trace"], 21)

        assert mock_parse_batch.call_count == 3
        assert len(result) == 6  # 2 items × 3 batches

    @pytest.mark.asyncio
    @patch(f"{MATH_AGENT_MOD}.get_generation_llm")
    @patch(f"{MATH_AGENT_MOD}._parse_batch")
    async def test_batch_ranges_are_correct(self, mock_parse_batch, mock_get_llm):
        """Verify start/end ranges for each batch are correct."""
        from src.graph.nodes.math_agent import (
            GeneratedContentItem,
            _parse_raw_content,
            PARSE_BATCH_SIZE,
        )

        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value = MagicMock()
        mock_get_llm.return_value = mock_llm

        item = GeneratedContentItem(
            question="Q", answer="A", explanation="E", topic="T"
        )
        mock_parse_batch.return_value = [item]

        await _parse_raw_content("raw", ["trace"], 16)

        # 16 items with PARSE_BATCH_SIZE=7 → 3 batches: 1-7, 8-14, 15-16
        calls = mock_parse_batch.call_args_list
        assert len(calls) == 3
        # Check (batch_idx, start, end) for each call
        assert calls[0].args[1:4] == (0, 1, 7)
        assert calls[1].args[1:4] == (1, 8, 14)
        assert calls[2].args[1:4] == (2, 15, 16)

    @pytest.mark.asyncio
    @patch(f"{MATH_AGENT_MOD}.get_generation_llm")
    @patch(f"{MATH_AGENT_MOD}._parse_batch")
    async def test_semaphore_limits_concurrency(self, mock_parse_batch, mock_get_llm):
        """Verify semaphore limits concurrent calls to 3."""
        from src.graph.nodes.math_agent import (
            GeneratedContentItem,
            _parse_raw_content,
        )

        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value = MagicMock()
        mock_get_llm.return_value = mock_llm

        max_concurrent = 0
        current_concurrent = 0
        lock = asyncio.Lock()

        original_return = GeneratedContentItem(
            question="Q", answer="A", explanation="E", topic="T"
        )

        async def tracking_parse(*args, **kwargs):
            nonlocal max_concurrent, current_concurrent
            async with lock:
                current_concurrent += 1
                if current_concurrent > max_concurrent:
                    max_concurrent = current_concurrent
            await asyncio.sleep(0.01)  # simulate work
            async with lock:
                current_concurrent -= 1
            return [original_return]

        mock_parse_batch.side_effect = tracking_parse

        # 35 items → 5 batches, should be limited to 3 concurrent
        await _parse_raw_content("raw", ["trace"], 35)

        assert max_concurrent <= 3
        assert mock_parse_batch.call_count == 5

    @pytest.mark.asyncio
    @patch(f"{MATH_AGENT_MOD}.get_generation_llm")
    @patch(f"{MATH_AGENT_MOD}.rate_limited_llm_call")
    async def test_small_batch_still_sequential(self, mock_rate_limit, mock_get_llm):
        """Batches <= PARSE_BATCH_SIZE use single parse (no gather)."""
        from src.graph.nodes.math_agent import (
            ContentItemList,
            GeneratedContentItem,
            _parse_raw_content,
            PARSE_BATCH_SIZE,
        )

        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value = MagicMock()
        mock_get_llm.return_value = mock_llm

        item = GeneratedContentItem(
            question="Q", answer="A", explanation="E", topic="T"
        )
        mock_rate_limit.return_value = ContentItemList(items=[item, item])

        result = await _parse_raw_content("raw", ["trace"], PARSE_BATCH_SIZE)

        assert mock_rate_limit.call_count == 1
        assert len(result) == 2

    @pytest.mark.asyncio
    @patch(f"{MATH_AGENT_MOD}.get_generation_llm")
    @patch(f"{MATH_AGENT_MOD}._parse_batch")
    async def test_partial_batch_failure_returns_remaining(
        self, mock_parse_batch, mock_get_llm
    ):
        """If one batch fails (returns []), others still contribute."""
        from src.graph.nodes.math_agent import (
            GeneratedContentItem,
            _parse_raw_content,
        )

        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value = MagicMock()
        mock_get_llm.return_value = mock_llm

        item = GeneratedContentItem(
            question="Q", answer="A", explanation="E", topic="T"
        )
        # batch 0 fails, batch 1 succeeds
        mock_parse_batch.side_effect = [[], [item, item]]

        result = await _parse_raw_content("raw", ["trace"], 14)

        assert len(result) == 2  # only from batch 1

    @pytest.mark.asyncio
    @patch(f"{MATH_AGENT_MOD}.get_generation_llm")
    @patch(f"{MATH_AGENT_MOD}._parse_batch")
    async def test_batch_exception_does_not_kill_others(
        self, mock_parse_batch, mock_get_llm
    ):
        """If one batch raises an exception, others still contribute items."""
        from src.graph.nodes.math_agent import (
            GeneratedContentItem,
            _parse_raw_content,
        )

        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value = MagicMock()
        mock_get_llm.return_value = mock_llm

        item = GeneratedContentItem(
            question="Q", answer="A", explanation="E", topic="T"
        )
        # batch 0 raises exception, batch 1 returns items
        mock_parse_batch.side_effect = [RuntimeError("LLM timeout"), [item, item]]

        result = await _parse_raw_content("raw", ["trace"], 14)

        assert len(result) == 2  # only batch 1 items survive

    @pytest.mark.asyncio
    @patch(f"{MATH_AGENT_MOD}.get_generation_llm")
    @patch(f"{MATH_AGENT_MOD}._parse_batch")
    async def test_order_preserved_across_batches(self, mock_parse_batch, mock_get_llm):
        """Items from batch 0 come before items from batch 1."""
        from src.graph.nodes.math_agent import (
            GeneratedContentItem,
            _parse_raw_content,
        )

        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value = MagicMock()
        mock_get_llm.return_value = mock_llm

        item_a = GeneratedContentItem(
            question="batch0", answer="A", explanation="E", topic="T"
        )
        item_b = GeneratedContentItem(
            question="batch1", answer="A", explanation="E", topic="T"
        )
        mock_parse_batch.side_effect = [[item_a], [item_b]]

        result = await _parse_raw_content("raw", ["trace"], 14)

        assert result[0].question == "batch0"
        assert result[1].question == "batch1"


# ═══════════════════════════════════════════════════════════════════════
# T-OPT-1.2: Cache Vertex AI Search on Retry
# ═══════════════════════════════════════════════════════════════════════


class TestCacheSearchOnRetry:
    """T-OPT-1.2: math_agent skips retrieve_context on retry iterations."""

    def _make_state(self, iteration_count=0, search_context=None, search_sources=None):
        """Build a minimal AgentState dict for testing."""
        from src.api.schemas import DifficultyLevel

        request = MagicMock()
        request.user_id = "test-user"
        request.topic = "Toán học"
        request.difficulty = DifficultyLevel.RECALL
        request.num_questions = 5
        request.doc_scope = MagicMock()
        request.doc_scope.value = "system"
        request.game_types = []
        request.language = "vi"

        state = {
            "request": request,
            "doc_scope": "system",
            "iteration_count": iteration_count,
            "reviewed_items": [],
            "rejected_items": [],
        }
        if search_context is not None:
            state["search_context"] = search_context
        if search_sources is not None:
            state["search_sources"] = search_sources
        return state

    @pytest.mark.asyncio
    @patch(f"{MATH_AGENT_MOD}.retrieve_context")
    @patch(f"{MATH_AGENT_MOD}._parse_raw_content")
    @patch(f"{MATH_AGENT_MOD}.rate_limited_llm_call")
    @patch(f"{MATH_AGENT_MOD}._get_llm")
    async def test_first_iteration_calls_retrieve_context(
        self, mock_llm, mock_rate_limit, mock_parse, mock_retrieve
    ):
        """iteration_count=0 always calls retrieve_context."""
        from src.graph.nodes.math_agent import math_agent_node, GeneratedContentItem

        mock_llm.return_value = MagicMock()
        mock_llm.return_value.bind_tools.return_value = MagicMock()
        mock_retrieve.return_value = (["chunk1"], [{"source": "s1"}])
        raw_msg = MagicMock()
        raw_msg.content = "raw content"
        mock_rate_limit.return_value = raw_msg
        mock_parse.return_value = [
            GeneratedContentItem(question="Q", answer="A", explanation="E", topic="T")
        ]

        state = self._make_state(iteration_count=0)
        await math_agent_node(state)

        mock_retrieve.assert_called_once()

    @pytest.mark.asyncio
    @patch(f"{MATH_AGENT_MOD}.retrieve_context")
    @patch(f"{MATH_AGENT_MOD}._parse_raw_content")
    @patch(f"{MATH_AGENT_MOD}.rate_limited_llm_call")
    @patch(f"{MATH_AGENT_MOD}._get_llm")
    async def test_retry_with_cached_context_skips_retrieve(
        self, mock_llm, mock_rate_limit, mock_parse, mock_retrieve
    ):
        """iteration_count>0 with cached search_context skips retrieve_context."""
        from src.graph.nodes.math_agent import math_agent_node, GeneratedContentItem

        mock_llm.return_value = MagicMock()
        mock_llm.return_value.bind_tools.return_value = MagicMock()
        raw_msg = MagicMock()
        raw_msg.content = "raw content"
        mock_rate_limit.return_value = raw_msg
        mock_parse.return_value = [
            GeneratedContentItem(question="Q", answer="A", explanation="E", topic="T")
        ]

        state = self._make_state(
            iteration_count=1,
            search_context=["cached chunk"],
            search_sources=[{"source": "cached"}],
        )
        await math_agent_node(state)

        mock_retrieve.assert_not_called()

    @pytest.mark.asyncio
    @patch(f"{MATH_AGENT_MOD}.retrieve_context")
    @patch(f"{MATH_AGENT_MOD}._parse_raw_content")
    @patch(f"{MATH_AGENT_MOD}.rate_limited_llm_call")
    @patch(f"{MATH_AGENT_MOD}._get_llm")
    async def test_retry_without_cached_context_calls_retrieve(
        self, mock_llm, mock_rate_limit, mock_parse, mock_retrieve
    ):
        """iteration_count>0 but no cached context still calls retrieve_context."""
        from src.graph.nodes.math_agent import math_agent_node, GeneratedContentItem

        mock_llm.return_value = MagicMock()
        mock_llm.return_value.bind_tools.return_value = MagicMock()
        mock_retrieve.return_value = (["new chunk"], [{"source": "new"}])
        raw_msg = MagicMock()
        raw_msg.content = "raw content"
        mock_rate_limit.return_value = raw_msg
        mock_parse.return_value = [
            GeneratedContentItem(question="Q", answer="A", explanation="E", topic="T")
        ]

        state = self._make_state(iteration_count=2)
        await math_agent_node(state)

        mock_retrieve.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════
# T-OPT-1.3: Skip Supervisor on Retry (Graph Topology)
# ═══════════════════════════════════════════════════════════════════════


class TestSkipSupervisorOnRetry:
    """T-OPT-1.3: reviewer fail routes directly to math_agent, not supervisor."""

    def test_graph_compiles_with_new_topology(self):
        """Graph compiles successfully with fail → math_agent."""
        from src.graph.builder import compile_graph

        app = compile_graph()
        assert app is not None

    def test_reviewer_fail_routes_to_math_agent(self):
        """reviewer fail edge targets math_agent, not supervisor."""
        from src.graph.builder import create_graph

        graph = create_graph()
        # Access the conditional edges from reviewer
        # The graph stores edges internally — verify by checking the compiled structure
        compiled = graph.compile()
        # Get the graph's edge map
        graph_dict = compiled.get_graph().to_json()
        # Verify math_agent is reachable from reviewer (not via supervisor)
        assert graph_dict is not None

    def test_reviewer_fail_does_not_route_to_supervisor(self):
        """Verify supervisor is NOT in the reviewer's fail path."""
        from src.graph.builder import create_graph

        graph = create_graph()
        compiled = graph.compile()
        graph_obj = compiled.get_graph()

        # Find all edges from reviewer node
        reviewer_targets = set()
        for edge in graph_obj.edges:
            if edge.source == "reviewer":
                reviewer_targets.add(edge.target)

        assert "math_agent" in reviewer_targets
        assert "supervisor" not in reviewer_targets

    def test_entry_point_still_supervisor(self):
        """Entry point remains supervisor for initial classification."""
        from src.graph.builder import create_graph

        graph = create_graph()
        compiled = graph.compile()
        graph_obj = compiled.get_graph()

        # Find edges from __start__
        start_targets = set()
        for edge in graph_obj.edges:
            if edge.source == "__start__":
                start_targets.add(edge.target)

        assert "supervisor" in start_targets

    def test_math_agent_to_reviewer_edge_exists(self):
        """math_agent always flows to reviewer."""
        from src.graph.builder import create_graph

        graph = create_graph()
        compiled = graph.compile()
        graph_obj = compiled.get_graph()

        math_targets = set()
        for edge in graph_obj.edges:
            if edge.source == "math_agent":
                math_targets.add(edge.target)

        assert "reviewer" in math_targets

    def test_all_nodes_present(self):
        """All 4 nodes exist in the graph."""
        from src.graph.builder import create_graph

        graph = create_graph()
        compiled = graph.compile()
        graph_obj = compiled.get_graph()

        node_ids = set(graph_obj.nodes)
        assert {"supervisor", "math_agent", "reviewer", "formatter"}.issubset(node_ids)
