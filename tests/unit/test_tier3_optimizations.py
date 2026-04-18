"""Unit tests for Tier 3 performance optimizations.

Tests cover:
- T-OPT-3.3: Deterministic supervisor (skip LLM call when USE_LLM_CLASSIFICATION=False)
- T-OPT-3.4: Parallel formatter batches (asyncio.gather for quiz/flashcard/fill_blank)
- T-OPT-3.2: SDK migration verification (ChatGoogleGenerativeAI in use, no ChatVertexAI)
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ─── Module paths ────────────────────────────────────────────────────
SUPERVISOR_MOD = "src.graph.nodes.supervisor"
FORMATTER_MOD = "src.graph.nodes.formatter"


# ═══════════════════════════════════════════════════════════════════════
# T-OPT-3.3: Deterministic Supervisor
# ═══════════════════════════════════════════════════════════════════════


class TestDeterministicSupervisor:
    """T-OPT-3.3: supervisor_node skips LLM call when USE_LLM_CLASSIFICATION=False."""

    def _make_state(self) -> dict:
        """Create minimal AgentState for supervisor tests."""
        request = MagicMock()
        request.user_id = "test-user"
        request.topic = "Toán 10"
        request.doc_scope.value = "lesson"
        request.game_types = [MagicMock(value="quiz")]
        request.difficulty.value = "recall"
        request.language = "vi"
        return {"request": request, "search_context": ["ctx1"], "iteration_count": 0}

    @pytest.mark.asyncio
    @patch(f"{SUPERVISOR_MOD}.USE_LLM_CLASSIFICATION", False)
    @patch(f"{SUPERVISOR_MOD}.rate_limited_llm_call")
    async def test_deterministic_no_llm_call(self, mock_rate_limit):
        """With USE_LLM_CLASSIFICATION=False, no LLM call is made."""
        from src.graph.nodes.supervisor import supervisor_node

        state = self._make_state()
        result = await supervisor_node(state)

        assert result["content_type"] == "math"
        mock_rate_limit.assert_not_called()

    @pytest.mark.asyncio
    @patch(f"{SUPERVISOR_MOD}.USE_LLM_CLASSIFICATION", False)
    async def test_deterministic_returns_math(self):
        """Deterministic mode always returns content_type='math'."""
        from src.graph.nodes.supervisor import supervisor_node

        state = self._make_state()
        result = await supervisor_node(state)

        assert result["content_type"] == "math"
        assert "doc_scope" in result
        assert "iteration_count" in result

    @pytest.mark.asyncio
    @patch(f"{SUPERVISOR_MOD}.USE_LLM_CLASSIFICATION", True)
    @patch(f"{SUPERVISOR_MOD}.rate_limited_llm_call", new_callable=AsyncMock)
    @patch(f"{SUPERVISOR_MOD}._get_llm")
    async def test_llm_mode_calls_llm(self, mock_get_llm, mock_rate_limit):
        """With USE_LLM_CLASSIFICATION=True, LLM call is made."""
        from src.graph.nodes.supervisor import supervisor_node

        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_rate_limit.return_value = "math"

        state = self._make_state()
        result = await supervisor_node(state)

        assert result["content_type"] == "math"
        mock_rate_limit.assert_called_once()

    @pytest.mark.asyncio
    @patch(f"{SUPERVISOR_MOD}.USE_LLM_CLASSIFICATION", True)
    @patch(f"{SUPERVISOR_MOD}.rate_limited_llm_call", new_callable=AsyncMock)
    @patch(f"{SUPERVISOR_MOD}._get_llm")
    async def test_llm_mode_unsupported_type_defaults_math(
        self, mock_get_llm, mock_rate_limit
    ):
        """LLM returns unsupported type → falls back to 'math'."""
        from src.graph.nodes.supervisor import supervisor_node

        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_rate_limit.return_value = "story"

        state = self._make_state()
        result = await supervisor_node(state)

        assert result["content_type"] == "math"

    @pytest.mark.asyncio
    @patch(f"{SUPERVISOR_MOD}.USE_LLM_CLASSIFICATION", True)
    @patch(f"{SUPERVISOR_MOD}.rate_limited_llm_call", new_callable=AsyncMock)
    @patch(f"{SUPERVISOR_MOD}._get_llm")
    async def test_llm_mode_exception_defaults_math(
        self, mock_get_llm, mock_rate_limit
    ):
        """LLM call raises exception → defaults to 'math'."""
        from src.graph.nodes.supervisor import supervisor_node

        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_rate_limit.side_effect = RuntimeError("API error")

        state = self._make_state()
        result = await supervisor_node(state)

        assert result["content_type"] == "math"


# ═══════════════════════════════════════════════════════════════════════
# T-OPT-3.4: Parallel Formatter Batches
# ═══════════════════════════════════════════════════════════════════════


class TestParallelFormatterBatches:
    """T-OPT-3.4: _format_quizzes, _format_flashcards, _format_fill_blanks
    dispatch batches concurrently via asyncio.gather."""

    def _make_items(self, n: int) -> list[dict]:
        """Create n dummy content items."""
        return [
            {
                "question": f"Q{i}",
                "answer": f"A{i}",
                "explanation": f"E{i}",
                "topic": "Toán",
                "difficulty": "recall",
            }
            for i in range(n)
        ]

    # ─── Quiz ────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    @patch(f"{FORMATTER_MOD}.rate_limited_llm_call", new_callable=AsyncMock)
    async def test_quiz_parallel_batches(self, mock_rate_limit):
        """14 items → 2 parallel batches (7+7)."""
        from src.graph.nodes.formatter import _format_quizzes, FORMATTER_BATCH_SIZE

        result_obj = MagicMock()
        quiz_item = MagicMock()
        quiz_item.question = "Q?"
        quiz_item.option_a = "A"
        quiz_item.option_b = "B"
        quiz_item.option_c = "C"
        quiz_item.option_d = "D"
        quiz_item.correct_index = 0
        quiz_item.explanation = "E"

        # Return 7 items per batch call
        result_obj.questions = [quiz_item] * FORMATTER_BATCH_SIZE
        mock_rate_limit.return_value = result_obj

        llm = MagicMock()
        llm.with_structured_output.return_value = MagicMock()
        # Make ainvoke return the mock result
        llm.with_structured_output.return_value.__or__ = MagicMock(
            return_value=MagicMock(ainvoke=AsyncMock(return_value=result_obj))
        )

        items = self._make_items(14)
        quizzes = await _format_quizzes(items, llm)

        assert len(quizzes) == 14
        # rate_limited_llm_call called for 2 batches
        assert mock_rate_limit.call_count == 2

    @pytest.mark.asyncio
    @patch(f"{FORMATTER_MOD}.rate_limited_llm_call", new_callable=AsyncMock)
    async def test_quiz_single_batch(self, mock_rate_limit):
        """5 items → 1 batch only."""
        from src.graph.nodes.formatter import _format_quizzes

        result_obj = MagicMock()
        quiz_item = MagicMock()
        quiz_item.question = "Q?"
        quiz_item.option_a = "A"
        quiz_item.option_b = "B"
        quiz_item.option_c = "C"
        quiz_item.option_d = "D"
        quiz_item.correct_index = 0
        quiz_item.explanation = "E"
        result_obj.questions = [quiz_item] * 5
        mock_rate_limit.return_value = result_obj

        llm = MagicMock()
        llm.with_structured_output.return_value = MagicMock()
        llm.with_structured_output.return_value.__or__ = MagicMock(
            return_value=MagicMock(ainvoke=AsyncMock(return_value=result_obj))
        )

        quizzes = await _format_quizzes(self._make_items(5), llm)

        assert len(quizzes) == 5
        assert mock_rate_limit.call_count == 1

    # ─── Flashcard ───────────────────────────────────────────────────

    @pytest.mark.asyncio
    @patch(f"{FORMATTER_MOD}.rate_limited_llm_call", new_callable=AsyncMock)
    async def test_flashcard_parallel_batches(self, mock_rate_limit):
        """14 items → 2 parallel batches."""
        from src.graph.nodes.formatter import _format_flashcards, FORMATTER_BATCH_SIZE

        result_obj = MagicMock()
        fc_item = MagicMock()
        fc_item.front = "Front"
        fc_item.back = "Back"
        fc_item.tags = ["tag"]
        result_obj.cards = [fc_item] * FORMATTER_BATCH_SIZE
        mock_rate_limit.return_value = result_obj

        llm = MagicMock()
        llm.with_structured_output.return_value = MagicMock()
        llm.with_structured_output.return_value.__or__ = MagicMock(
            return_value=MagicMock(ainvoke=AsyncMock(return_value=result_obj))
        )

        flashcards = await _format_flashcards(self._make_items(14), llm)

        assert len(flashcards) == 14
        assert mock_rate_limit.call_count == 2

    # ─── Fill Blank ──────────────────────────────────────────────────

    @pytest.mark.asyncio
    @patch(f"{FORMATTER_MOD}.rate_limited_llm_call", new_callable=AsyncMock)
    async def test_fill_blank_parallel_batches(self, mock_rate_limit):
        """14 items → 2 parallel batches."""
        from src.graph.nodes.formatter import (
            _format_fill_blanks,
            FORMATTER_BATCH_SIZE,
        )

        result_obj = MagicMock()
        fb_item = MagicMock()
        fb_item.template = "The answer is ___"
        fb_item.blanks = ["42"]
        fb_item.hints = ["hint"]
        fb_item.explanation = "Because"
        result_obj.questions = [fb_item] * FORMATTER_BATCH_SIZE
        mock_rate_limit.return_value = result_obj

        llm = MagicMock()
        llm.with_structured_output.return_value = MagicMock()
        llm.with_structured_output.return_value.__or__ = MagicMock(
            return_value=MagicMock(ainvoke=AsyncMock(return_value=result_obj))
        )

        fill_blanks = await _format_fill_blanks(self._make_items(14), llm)

        assert len(fill_blanks) == 14
        assert mock_rate_limit.call_count == 2

    @pytest.mark.asyncio
    @patch(f"{FORMATTER_MOD}.rate_limited_llm_call", new_callable=AsyncMock)
    async def test_fill_blank_blanks_structure(self, mock_rate_limit):
        """Verify FillBlankQuestion has correct BlankSlot structure."""
        from src.graph.nodes.formatter import _format_fill_blanks

        result_obj = MagicMock()
        fb_item = MagicMock()
        fb_item.template = "x + ___ = 5"
        fb_item.blanks = ["3"]
        fb_item.hints = ["Think subtraction"]
        fb_item.explanation = "5 - 2 = 3"
        result_obj.questions = [fb_item]
        mock_rate_limit.return_value = result_obj

        llm = MagicMock()
        llm.with_structured_output.return_value = MagicMock()
        llm.with_structured_output.return_value.__or__ = MagicMock(
            return_value=MagicMock(ainvoke=AsyncMock(return_value=result_obj))
        )

        fill_blanks = await _format_fill_blanks(self._make_items(1), llm)

        assert len(fill_blanks) == 1
        fb = fill_blanks[0]
        assert fb.template == "x + ___ = 5"
        assert len(fb.blanks) == 1
        assert fb.blanks[0].correct_answer == "3"
        assert fb.blanks[0].hint == "Think subtraction"


# ═══════════════════════════════════════════════════════════════════════
# T-OPT-3.2: SDK Migration Verification
# ═══════════════════════════════════════════════════════════════════════


class TestSDKMigration:
    """T-OPT-3.2: Verify ChatGoogleGenerativeAI is used, no ChatVertexAI in src/."""

    def test_llm_service_uses_google_genai(self):
        """llm.py imports ChatGoogleGenerativeAI, not ChatVertexAI."""
        import inspect
        import src.services.llm as llm_mod

        source = inspect.getsource(llm_mod)
        assert "ChatGoogleGenerativeAI" in source
        assert "ChatVertexAI" not in source

    def test_no_chatvertexai_in_source(self):
        """No 'ChatVertexAI' import in any src/ python file."""
        from pathlib import Path

        src_dir = Path(__file__).resolve().parents[2] / "src"
        violations = []
        for py_file in src_dir.rglob("*.py"):
            content = py_file.read_text()
            if "ChatVertexAI" in content:
                violations.append(str(py_file.relative_to(src_dir)))
        assert violations == [], f"ChatVertexAI found in: {violations}"


# ═══════════════════════════════════════════════════════════════════════
# T-OPT-3.3: Deterministic supervisor constant
# ═══════════════════════════════════════════════════════════════════════


class TestSupervisorConstant:
    """Verify USE_LLM_CLASSIFICATION defaults to False."""

    def test_default_is_false(self):
        from src.graph.nodes.supervisor import USE_LLM_CLASSIFICATION

        assert USE_LLM_CLASSIFICATION is False
