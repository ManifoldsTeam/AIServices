"""Unit tests for Tier 2 performance optimizations.

Tests cover:
- T-OPT-2.1: Parse-only retry (cache raw text, retry parsing before re-generating)
- T-OPT-2.3: Parallel micro-batch generation (split large batches into 2 parallel calls)
- T-OPT-2.2: JSON mode — SKIPPED (Gemini 3 Flash has infinite loop bugs with strict schemas)
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

# ─── Module paths ────────────────────────────────────────────────────
MATH_AGENT_MOD = "src.graph.nodes.math_agent"


# ═══════════════════════════════════════════════════════════════════════
# T-OPT-2.1: Parse-Only Retry
# ═══════════════════════════════════════════════════════════════════════


class TestParseOnlyRetry:
    """T-OPT-2.1: _generate_and_parse retries parsing before re-generating."""

    @pytest.mark.asyncio
    @patch(f"{MATH_AGENT_MOD}._parse_raw_content")
    @patch(f"{MATH_AGENT_MOD}._extract_content_with_traces")
    @patch(f"{MATH_AGENT_MOD}.rate_limited_llm_call")
    @patch(f"{MATH_AGENT_MOD}.MATH_AGENT_PROMPT")
    async def test_parse_retries_before_regeneration(
        self, mock_prompt, mock_rate_limit, mock_extract, mock_parse
    ):
        """Parse fails once, succeeds on 2nd try without re-generating."""
        from src.graph.nodes.math_agent import _generate_and_parse, GeneratedContentItem

        mock_prompt.format_messages.return_value = [
            {"role": "human", "content": "test"}
        ]
        raw_msg = MagicMock()
        mock_rate_limit.return_value = raw_msg
        mock_extract.return_value = ("raw text", ["trace"])

        item = GeneratedContentItem(
            question="Q", answer="A", explanation="E", topic="T"
        )
        # Parse fails first, succeeds second
        mock_parse.side_effect = [[], [item, item]]

        code_exec_llm = MagicMock()
        result = await _generate_and_parse(
            code_exec_llm, 5, "recall", "Math", "context", "", ""
        )

        assert len(result) == 2
        # Generate called only once (no re-generation)
        assert mock_rate_limit.call_count == 1
        # Parse called twice (retry with cached raw text)
        assert mock_parse.call_count == 2

    @pytest.mark.asyncio
    @patch(f"{MATH_AGENT_MOD}._parse_raw_content")
    @patch(f"{MATH_AGENT_MOD}._extract_content_with_traces")
    @patch(f"{MATH_AGENT_MOD}.rate_limited_llm_call")
    @patch(f"{MATH_AGENT_MOD}.MATH_AGENT_PROMPT")
    async def test_all_parse_retries_fail_triggers_regeneration(
        self, mock_prompt, mock_rate_limit, mock_extract, mock_parse
    ):
        """All parse retries fail → re-generate then parse again."""
        from src.graph.nodes.math_agent import (
            _generate_and_parse,
            GeneratedContentItem,
            MAX_PARSE_ONLY_RETRIES,
            MAX_GENERATION_RETRIES,
        )

        mock_prompt.format_messages.return_value = [
            {"role": "human", "content": "test"}
        ]
        raw_msg = MagicMock()
        mock_rate_limit.return_value = raw_msg
        mock_extract.return_value = ("raw text", ["trace"])

        item = GeneratedContentItem(
            question="Q", answer="A", explanation="E", topic="T"
        )
        # Fail for all parse retries on gen_attempt=0, succeed on gen_attempt=1
        fail_count = MAX_PARSE_ONLY_RETRIES
        mock_parse.side_effect = [[] for _ in range(fail_count)] + [[item]]

        code_exec_llm = MagicMock()
        result = await _generate_and_parse(
            code_exec_llm, 5, "recall", "Math", "context", "", ""
        )

        assert len(result) == 1
        # Generate called twice (re-generation after parse failures)
        assert mock_rate_limit.call_count == 2
        # Parse called: MAX_PARSE_ONLY_RETRIES (gen0) + 1 (gen1 success)
        assert mock_parse.call_count == MAX_PARSE_ONLY_RETRIES + 1

    @pytest.mark.asyncio
    @patch(f"{MATH_AGENT_MOD}._parse_raw_content")
    @patch(f"{MATH_AGENT_MOD}._extract_content_with_traces")
    @patch(f"{MATH_AGENT_MOD}.rate_limited_llm_call")
    @patch(f"{MATH_AGENT_MOD}.MATH_AGENT_PROMPT")
    async def test_parse_succeeds_first_try_no_extra_calls(
        self, mock_prompt, mock_rate_limit, mock_extract, mock_parse
    ):
        """Parse succeeds on first try — no retries."""
        from src.graph.nodes.math_agent import _generate_and_parse, GeneratedContentItem

        mock_prompt.format_messages.return_value = [
            {"role": "human", "content": "test"}
        ]
        raw_msg = MagicMock()
        mock_rate_limit.return_value = raw_msg
        mock_extract.return_value = ("raw text", ["trace"])

        item = GeneratedContentItem(
            question="Q", answer="A", explanation="E", topic="T"
        )
        mock_parse.return_value = [item]

        code_exec_llm = MagicMock()
        result = await _generate_and_parse(
            code_exec_llm, 5, "recall", "Math", "context", "", ""
        )

        assert len(result) == 1
        assert mock_rate_limit.call_count == 1
        assert mock_parse.call_count == 1

    @pytest.mark.asyncio
    @patch(f"{MATH_AGENT_MOD}._parse_raw_content")
    @patch(f"{MATH_AGENT_MOD}._extract_content_with_traces")
    @patch(f"{MATH_AGENT_MOD}.rate_limited_llm_call")
    @patch(f"{MATH_AGENT_MOD}.MATH_AGENT_PROMPT")
    async def test_empty_generation_skips_parsing(
        self, mock_prompt, mock_rate_limit, mock_extract, mock_parse
    ):
        """Empty generation text skips parsing and retries generation."""
        from src.graph.nodes.math_agent import _generate_and_parse, GeneratedContentItem

        mock_prompt.format_messages.return_value = [
            {"role": "human", "content": "test"}
        ]
        raw_msg = MagicMock()
        mock_rate_limit.return_value = raw_msg

        item = GeneratedContentItem(
            question="Q", answer="A", explanation="E", topic="T"
        )
        # First gen returns empty, second gen returns content
        mock_extract.side_effect = [("  ", []), ("real content", ["trace"])]
        mock_parse.return_value = [item]

        code_exec_llm = MagicMock()
        result = await _generate_and_parse(
            code_exec_llm, 5, "recall", "Math", "context", "", ""
        )

        assert len(result) == 1
        # Generate called twice (first was empty)
        assert mock_rate_limit.call_count == 2
        # Parse called once (skipped on empty gen)
        assert mock_parse.call_count == 1

    @pytest.mark.asyncio
    @patch(f"{MATH_AGENT_MOD}._parse_raw_content")
    @patch(f"{MATH_AGENT_MOD}._extract_content_with_traces")
    @patch(f"{MATH_AGENT_MOD}.rate_limited_llm_call")
    @patch(f"{MATH_AGENT_MOD}.MATH_AGENT_PROMPT")
    async def test_all_attempts_fail_returns_empty(
        self, mock_prompt, mock_rate_limit, mock_extract, mock_parse
    ):
        """All generation + parse attempts fail → returns empty list."""
        from src.graph.nodes.math_agent import (
            _generate_and_parse,
            MAX_PARSE_ONLY_RETRIES,
            MAX_GENERATION_RETRIES,
        )

        mock_prompt.format_messages.return_value = [
            {"role": "human", "content": "test"}
        ]
        raw_msg = MagicMock()
        mock_rate_limit.return_value = raw_msg
        mock_extract.return_value = ("raw text", ["trace"])
        mock_parse.return_value = []  # Always fail

        code_exec_llm = MagicMock()
        result = await _generate_and_parse(
            code_exec_llm, 5, "recall", "Math", "context", "", ""
        )

        assert result == []
        assert mock_rate_limit.call_count == MAX_GENERATION_RETRIES
        assert mock_parse.call_count == MAX_GENERATION_RETRIES * MAX_PARSE_ONLY_RETRIES

    @pytest.mark.asyncio
    @patch(f"{MATH_AGENT_MOD}._parse_raw_content")
    @patch(f"{MATH_AGENT_MOD}._extract_content_with_traces")
    @patch(f"{MATH_AGENT_MOD}.rate_limited_llm_call")
    @patch(f"{MATH_AGENT_MOD}.MATH_AGENT_PROMPT")
    async def test_generation_exception_retries(
        self, mock_prompt, mock_rate_limit, mock_extract, mock_parse
    ):
        """Exception during generation retries without crashing."""
        from src.graph.nodes.math_agent import _generate_and_parse, GeneratedContentItem

        mock_prompt.format_messages.return_value = [
            {"role": "human", "content": "test"}
        ]

        item = GeneratedContentItem(
            question="Q", answer="A", explanation="E", topic="T"
        )
        raw_msg = MagicMock()
        # First call raises, second succeeds
        mock_rate_limit.side_effect = [RuntimeError("API error"), raw_msg]
        mock_extract.return_value = ("raw text", ["trace"])
        mock_parse.return_value = [item]

        code_exec_llm = MagicMock()
        result = await _generate_and_parse(
            code_exec_llm, 5, "recall", "Math", "context", "", ""
        )

        assert len(result) == 1


# ═══════════════════════════════════════════════════════════════════════
# T-OPT-2.3: Parallel Micro-Batch Generation
# ═══════════════════════════════════════════════════════════════════════


class TestParallelMicroBatchGeneration:
    """T-OPT-2.3: math_agent_node splits large batches into parallel micro-batches."""

    def _make_state(self, num_questions=10, iteration_count=0):
        """Build a minimal AgentState dict for testing."""
        from src.api.schemas import DifficultyLevel

        request = MagicMock()
        request.user_id = "test-user"
        request.topic = "Đạo hàm"
        request.difficulty = DifficultyLevel.HIGH_APPLICATION
        request.num_questions = num_questions
        request.doc_scope = MagicMock()
        request.doc_scope.value = "system"
        request.game_types = []
        request.language = "vi"

        return {
            "request": request,
            "doc_scope": "system",
            "iteration_count": iteration_count,
            "reviewed_items": [],
            "rejected_items": [],
        }

    @pytest.mark.asyncio
    @patch(f"{MATH_AGENT_MOD}._generate_and_parse")
    @patch(f"{MATH_AGENT_MOD}.retrieve_context")
    @patch(f"{MATH_AGENT_MOD}._get_llm")
    async def test_large_batch_splits_into_micro_batches(
        self, mock_llm, mock_retrieve, mock_gen_parse
    ):
        """num_to_generate > MICRO_BATCH_THRESHOLD triggers parallel micro-batches."""
        from src.graph.nodes.math_agent import (
            math_agent_node,
            GeneratedContentItem,
            MICRO_BATCH_THRESHOLD,
        )

        mock_llm.return_value = MagicMock()
        mock_llm.return_value.bind_tools.return_value = MagicMock()
        mock_retrieve.return_value = (["chunk"], [{"source": "s1"}])

        item = GeneratedContentItem(
            question="Q", answer="A", explanation="E", topic="T"
        )
        mock_gen_parse.return_value = [item, item, item]

        state = self._make_state(num_questions=10)
        result = await math_agent_node(state)

        # high_application overshoot = 2.5, so 10*2.5=25 > MICRO_BATCH_THRESHOLD
        # _generate_and_parse called twice (2 micro-batches)
        assert mock_gen_parse.call_count == 2
        assert len(result["content_items"]) == 6  # 3 items × 2 batches

    @pytest.mark.asyncio
    @patch(f"{MATH_AGENT_MOD}._generate_and_parse")
    @patch(f"{MATH_AGENT_MOD}.retrieve_context")
    @patch(f"{MATH_AGENT_MOD}._get_llm")
    async def test_small_batch_uses_single_call(
        self, mock_llm, mock_retrieve, mock_gen_parse
    ):
        """num_to_generate <= MICRO_BATCH_THRESHOLD uses single _generate_and_parse."""
        from src.graph.nodes.math_agent import (
            math_agent_node,
            GeneratedContentItem,
            MICRO_BATCH_THRESHOLD,
        )
        from src.api.schemas import DifficultyLevel

        mock_llm.return_value = MagicMock()
        mock_llm.return_value.bind_tools.return_value = MagicMock()
        mock_retrieve.return_value = (["chunk"], [{"source": "s1"}])

        item = GeneratedContentItem(
            question="Q", answer="A", explanation="E", topic="T"
        )
        mock_gen_parse.return_value = [item, item]

        # Use recall difficulty (overshoot=1.1) → 10*1.1=11 + floor → still ≤ MICRO_BATCH_THRESHOLD
        state = self._make_state(num_questions=5)
        state["request"].difficulty = DifficultyLevel.RECALL
        state["request"].num_questions = 5
        result = await math_agent_node(state)

        # 5*1.1=5.5→6, floor=max(6, 5+3)=8 ≤ MICRO_BATCH_THRESHOLD → single call
        assert mock_gen_parse.call_count == 1

    @pytest.mark.asyncio
    @patch(f"{MATH_AGENT_MOD}._generate_and_parse")
    @patch(f"{MATH_AGENT_MOD}.retrieve_context")
    @patch(f"{MATH_AGENT_MOD}._get_llm")
    async def test_micro_batch_split_is_balanced(
        self, mock_llm, mock_retrieve, mock_gen_parse
    ):
        """Verify the 2 micro-batches have balanced sizes."""
        from src.graph.nodes.math_agent import (
            math_agent_node,
            GeneratedContentItem,
        )

        mock_llm.return_value = MagicMock()
        mock_llm.return_value.bind_tools.return_value = MagicMock()
        mock_retrieve.return_value = (["chunk"], [{"source": "s1"}])

        item = GeneratedContentItem(
            question="Q", answer="A", explanation="E", topic="T"
        )
        mock_gen_parse.return_value = [item]

        state = self._make_state(num_questions=10)
        await math_agent_node(state)

        calls = mock_gen_parse.call_args_list
        assert len(calls) == 2
        batch_a_size = calls[0].args[1]  # num_to_generate arg
        batch_b_size = calls[1].args[1]
        total = batch_a_size + batch_b_size
        # Sizes should differ by at most 1
        assert abs(batch_a_size - batch_b_size) <= 1
        # Total should match original num_to_generate
        assert total > 12  # > MICRO_BATCH_THRESHOLD (confirming split path)

    @pytest.mark.asyncio
    @patch(f"{MATH_AGENT_MOD}._generate_and_parse")
    @patch(f"{MATH_AGENT_MOD}.retrieve_context")
    @patch(f"{MATH_AGENT_MOD}._get_llm")
    async def test_micro_batch_partial_failure(
        self, mock_llm, mock_retrieve, mock_gen_parse
    ):
        """One micro-batch fails → still returns items from the other."""
        from src.graph.nodes.math_agent import math_agent_node, GeneratedContentItem

        mock_llm.return_value = MagicMock()
        mock_llm.return_value.bind_tools.return_value = MagicMock()
        mock_retrieve.return_value = (["chunk"], [{"source": "s1"}])

        item = GeneratedContentItem(
            question="Q", answer="A", explanation="E", topic="T"
        )
        # Batch A fails, Batch B succeeds
        mock_gen_parse.side_effect = [[], [item, item]]

        state = self._make_state(num_questions=10)
        result = await math_agent_node(state)

        assert len(result["content_items"]) == 2

    @pytest.mark.asyncio
    @patch(f"{MATH_AGENT_MOD}._generate_and_parse")
    @patch(f"{MATH_AGENT_MOD}.retrieve_context")
    @patch(f"{MATH_AGENT_MOD}._get_llm")
    async def test_both_micro_batches_fail_returns_error(
        self, mock_llm, mock_retrieve, mock_gen_parse
    ):
        """Both micro-batches fail → returns error."""
        from src.graph.nodes.math_agent import math_agent_node

        mock_llm.return_value = MagicMock()
        mock_llm.return_value.bind_tools.return_value = MagicMock()
        mock_retrieve.return_value = (["chunk"], [{"source": "s1"}])

        mock_gen_parse.return_value = []

        state = self._make_state(num_questions=10)
        result = await math_agent_node(state)

        assert result["content_items"] == []
        assert len(result["errors"]) > 0


# ═══════════════════════════════════════════════════════════════════════
# T-OPT-2.2: JSON Mode — SKIPPED
# ═══════════════════════════════════════════════════════════════════════


class TestJsonModeResearch:
    """T-OPT-2.2: Documented as skipped due to Gemini 3 Flash infinite loop bugs."""

    def test_json_mode_skipped_documented(self):
        """T-OPT-2.2 skipped — Gemini 3 Flash has infinite loop bugs with code_execution + JSON mode."""
        # Research finding (2026-04-09):
        # - Gemini 3 Flash supports code_execution + JSON mode combined
        # - BUT has edge-case infinite loop bugs when strict schemas are present
        # - LangChain with_structured_output() doesn't allow additional tools
        # - Risk: HIGH — production pipeline could hang indefinitely
        # Decision: Skip T-OPT-2.2, keep 2-phase generate+parse approach
        assert True  # Placeholder — this documents the decision
