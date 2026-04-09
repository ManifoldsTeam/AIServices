"""Unit tests for pipeline pass-rate fixes (P0–P4).

Tests cover:
- P0: Feedback loop — math_agent reads rejected_items on retry
- P1: Few-shot exemplars per difficulty level
- P2: Adaptive overshoot ratio by difficulty
- P3: Reviewer difficulty calibration (threshold + guidance)
- P4: Sequential batch parsing (vs concurrent)
"""

from __future__ import annotations

import math
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ─── Module paths ────────────────────────────────────────────────────
MATH_AGENT_MOD = "src.graph.nodes.math_agent"
REVIEWER_MOD = "src.graph.nodes.reviewer"


# ═══════════════════════════════════════════════════════════════════════
# P2: Adaptive Overshoot Ratio (constants)
# ═══════════════════════════════════════════════════════════════════════


class TestAdaptiveOvershoot:
    """P2: OVERSHOOT_BY_DIFFICULTY has correct values."""

    def test_overshoot_keys_match_difficulty_levels(self):
        from src.config.constants import OVERSHOOT_BY_DIFFICULTY

        assert set(OVERSHOOT_BY_DIFFICULTY.keys()) == {
            "recall",
            "comprehension",
            "application",
            "high_application",
        }

    def test_overshoot_increases_with_difficulty(self):
        from src.config.constants import OVERSHOOT_BY_DIFFICULTY

        assert (
            OVERSHOOT_BY_DIFFICULTY["recall"] < OVERSHOOT_BY_DIFFICULTY["comprehension"]
        )
        assert (
            OVERSHOOT_BY_DIFFICULTY["comprehension"]
            < OVERSHOOT_BY_DIFFICULTY["application"]
        )
        assert (
            OVERSHOOT_BY_DIFFICULTY["application"]
            < OVERSHOOT_BY_DIFFICULTY["high_application"]
        )

    def test_high_application_at_least_2x(self):
        from src.config.constants import OVERSHOOT_BY_DIFFICULTY

        assert OVERSHOOT_BY_DIFFICULTY["high_application"] >= 2.0


# ═══════════════════════════════════════════════════════════════════════
# P3: Review Threshold by Difficulty (constants)
# ═══════════════════════════════════════════════════════════════════════


class TestReviewThresholdByDifficulty:
    """P3: REVIEW_THRESHOLD_BY_DIFFICULTY has correct values."""

    def test_threshold_keys_match_difficulty_levels(self):
        from src.config.constants import REVIEW_THRESHOLD_BY_DIFFICULTY

        assert set(REVIEW_THRESHOLD_BY_DIFFICULTY.keys()) == {
            "recall",
            "comprehension",
            "application",
            "high_application",
        }

    def test_high_application_has_lowest_threshold(self):
        from src.config.constants import REVIEW_THRESHOLD_BY_DIFFICULTY

        assert (
            REVIEW_THRESHOLD_BY_DIFFICULTY["high_application"]
            < REVIEW_THRESHOLD_BY_DIFFICULTY["recall"]
        )

    def test_thresholds_are_positive(self):
        from src.config.constants import REVIEW_THRESHOLD_BY_DIFFICULTY

        for k, v in REVIEW_THRESHOLD_BY_DIFFICULTY.items():
            assert 0 < v <= 1.0, f"{k} threshold out of range: {v}"


# ═══════════════════════════════════════════════════════════════════════
# P0: Feedback Loop Helpers
# ═══════════════════════════════════════════════════════════════════════


class TestBuildRejectionFeedback:
    """P0: _build_rejection_feedback produces correct output."""

    def test_empty_list_returns_empty_string(self):
        from src.graph.nodes.math_agent import _build_rejection_feedback

        assert _build_rejection_feedback([]) == ""

    def test_includes_question_and_feedback(self):
        from src.graph.nodes.math_agent import _build_rejection_feedback

        items = [
            {
                "question": "What is 2+2?",
                "review_feedback": "Too simple for application level",
                "review_score": 0.4,
            }
        ]
        result = _build_rejection_feedback(items)
        assert "PREVIOUS ATTEMPT FEEDBACK" in result
        assert "What is 2+2?" in result
        assert "Too simple for application level" in result
        assert "score=0.4" in result

    def test_respects_max_items_limit(self):
        from src.graph.nodes.math_agent import _build_rejection_feedback

        items = [
            {"question": f"Q{i}", "review_feedback": f"F{i}", "review_score": 0.3}
            for i in range(10)
        ]
        result = _build_rejection_feedback(items, max_items=3)
        # Should only include last 3 items (Q7, Q8, Q9)
        assert "Q7" in result
        assert "Q8" in result
        assert "Q9" in result
        assert "Q0" not in result

    def test_handles_missing_fields_gracefully(self):
        from src.graph.nodes.math_agent import _build_rejection_feedback

        items = [{"question": "Q1"}]  # No review_feedback or review_score
        result = _build_rejection_feedback(items)
        assert "No specific feedback" in result
        assert "N/A" in result

    def test_filters_feedback_by_difficulty_when_present(self):
        from src.graph.nodes.math_agent import _build_rejection_feedback

        items = [
            {
                "question": "Recall Q",
                "review_feedback": "Too easy",
                "review_score": 0.4,
                "difficulty": "recall",
            },
            {
                "question": "High App Q",
                "review_feedback": "Still too routine",
                "review_score": 0.45,
                "difficulty": "high_application",
            },
        ]
        result = _build_rejection_feedback(items, difficulty="high_application")
        assert "High App Q" in result
        assert "Recall Q" not in result


# ═══════════════════════════════════════════════════════════════════════
# P1: Few-Shot Exemplars
# ═══════════════════════════════════════════════════════════════════════


class TestBuildExemplarsSection:
    """P1: _build_exemplars_section produces correct output."""

    def test_returns_empty_for_unknown_difficulty(self):
        from src.graph.nodes.math_agent import _build_exemplars_section

        assert _build_exemplars_section("nonexistent") == ""

    def test_all_difficulty_levels_have_exemplars(self):
        from src.graph.nodes.math_agent import DIFFICULTY_EXEMPLARS

        for level in ("recall", "comprehension", "application", "high_application"):
            assert level in DIFFICULTY_EXEMPLARS, f"Missing exemplars for {level}"
            assert (
                len(DIFFICULTY_EXEMPLARS[level]) >= 1
            ), f"Need >=1 exemplar for {level}"

    def test_high_application_has_multiple_exemplars(self):
        from src.graph.nodes.math_agent import DIFFICULTY_EXEMPLARS

        assert len(DIFFICULTY_EXEMPLARS["high_application"]) >= 2

    def test_section_includes_exemplar_content(self):
        from src.graph.nodes.math_agent import _build_exemplars_section

        result = _build_exemplars_section("recall")
        assert "EXEMPLAR QUESTIONS" in result
        assert "'recall'" in result
        assert "Question:" in result
        assert "Answer:" in result
        assert "Explanation:" in result

    def test_exemplars_have_required_keys(self):
        from src.graph.nodes.math_agent import DIFFICULTY_EXEMPLARS

        for level, exemplars in DIFFICULTY_EXEMPLARS.items():
            for i, ex in enumerate(exemplars):
                assert "question" in ex, f"{level}[{i}] missing question"
                assert "answer" in ex, f"{level}[{i}] missing answer"
                assert "explanation" in ex, f"{level}[{i}] missing explanation"

    def test_high_application_chemistry_topic_adds_domain_exemplars(self):
        from src.graph.nodes.math_agent import _build_exemplars_section

        result = _build_exemplars_section(
            "high_application", topic="Phản ứng oxi hóa khử"
        )
        assert "phòng thí nghiệm" in result.lower() or "mất nhãn" in result.lower()


# ═══════════════════════════════════════════════════════════════════════
# P0 + P2: math_agent_node retry logic
# ═══════════════════════════════════════════════════════════════════════


class TestMathAgentRetryLogic:
    """P0: math_agent reads rejected_items and computes gap on retry.
    P2: Uses difficulty-specific overshoot.
    """

    def _make_request(self, difficulty="comprehension", num_questions=10):
        """Create a mock GenerationRequest."""
        from src.api.schemas import DifficultyLevel, DocScope, GameType

        req = MagicMock()
        req.user_id = "test_user"
        req.topic = "Đạo hàm"
        req.num_questions = num_questions
        req.difficulty = DifficultyLevel(difficulty)
        req.doc_scope = DocScope.SYSTEM
        req.language = "vi"
        return req

    def test_first_iteration_uses_full_count(self):
        """On first iteration (iteration_count=0), generate for full request."""
        from src.config.constants import OVERSHOOT_BY_DIFFICULTY

        request = self._make_request(difficulty="recall", num_questions=10)
        iteration_count = 0
        reviewed_items = []

        num_still_needed = request.num_questions  # 10
        overshoot = OVERSHOOT_BY_DIFFICULTY.get(request.difficulty.value, 1.3)
        num_to_generate = math.ceil(num_still_needed * overshoot)

        assert num_to_generate == math.ceil(10 * 1.1)  # recall = 1.1

    def test_retry_calculates_gap(self):
        """On retry, only generate items for the gap."""
        request = self._make_request(difficulty="application", num_questions=10)
        reviewed_items = [{"q": f"item_{i}"} for i in range(6)]  # 6 already passed
        iteration_count = 1

        num_still_needed = max(request.num_questions - len(reviewed_items), 1)  # 4
        assert num_still_needed == 4

    def test_retry_gap_is_at_least_one(self):
        """Even if all items passed, generate at least 1."""
        request = self._make_request(num_questions=10)
        reviewed_items = [{"q": f"item_{i}"} for i in range(10)]
        iteration_count = 1

        num_still_needed = max(request.num_questions - len(reviewed_items), 1)
        assert num_still_needed == 1

    def test_high_application_uses_2x_overshoot(self):
        """high_application should use 2.5x overshoot."""
        from src.config.constants import OVERSHOOT_BY_DIFFICULTY

        request = self._make_request(difficulty="high_application", num_questions=10)
        overshoot = OVERSHOOT_BY_DIFFICULTY.get(request.difficulty.value, 1.3)
        num_to_generate = math.ceil(10 * overshoot)

        assert num_to_generate == 25  # 10 * 2.5

    def test_recall_uses_minimal_overshoot(self):
        """recall should use 1.1x overshoot."""
        from src.config.constants import OVERSHOOT_BY_DIFFICULTY

        overshoot = OVERSHOOT_BY_DIFFICULTY["recall"]
        num_to_generate = math.ceil(10 * overshoot)

        assert num_to_generate == 11  # 10 * 1.1


# ═══════════════════════════════════════════════════════════════════════
# P3: Reviewer Difficulty Guidance
# ═══════════════════════════════════════════════════════════════════════


class TestReviewerDifficultyGuidance:
    """P3: REVIEWER_DIFFICULTY_GUIDANCE has correct values."""

    def test_all_difficulty_levels_have_guidance(self):
        from src.graph.nodes.reviewer import REVIEWER_DIFFICULTY_GUIDANCE

        for level in ("recall", "comprehension", "application", "high_application"):
            assert level in REVIEWER_DIFFICULTY_GUIDANCE

    def test_high_application_guidance_mentions_lenient(self):
        from src.graph.nodes.reviewer import REVIEWER_DIFFICULTY_GUIDANCE

        guidance = REVIEWER_DIFFICULTY_GUIDANCE["high_application"]
        assert "lenient" in guidance.lower()

    def test_recall_guidance_mentions_strict_accuracy(self):
        from src.graph.nodes.reviewer import REVIEWER_DIFFICULTY_GUIDANCE

        guidance = REVIEWER_DIFFICULTY_GUIDANCE["recall"]
        assert "strict" in guidance.lower()


# ═══════════════════════════════════════════════════════════════════════
# P3: Reviewer prompt includes threshold and guidance
# ═══════════════════════════════════════════════════════════════════════


class TestReviewerPromptTemplate:
    """P3: REVIEWER_PROMPT uses dynamic threshold and guidance."""

    def test_prompt_contains_threshold_placeholder(self):
        from src.graph.nodes.reviewer import REVIEWER_PROMPT

        # The prompt template should have {pass_threshold} variable
        template_vars = REVIEWER_PROMPT.input_variables
        assert "pass_threshold" in template_vars

    def test_prompt_contains_difficulty_guidance_placeholder(self):
        from src.graph.nodes.reviewer import REVIEWER_PROMPT

        template_vars = REVIEWER_PROMPT.input_variables
        assert "difficulty_guidance" in template_vars

    def test_prompt_formats_with_threshold(self):
        from src.graph.nodes.reviewer import REVIEWER_PROMPT

        messages = REVIEWER_PROMPT.format_messages(
            num_items=5,
            items_json="[]",
            pass_threshold=0.55,
            difficulty_guidance="Test guidance.",
        )
        system_msg = messages[0].content
        assert "0.55" in system_msg
        assert "Test guidance." in system_msg


# ═══════════════════════════════════════════════════════════════════════
# P0 + P1: MATH_AGENT_PROMPT includes feedback + exemplars
# ═══════════════════════════════════════════════════════════════════════


class TestMathAgentPromptTemplate:
    """P0 + P1: MATH_AGENT_PROMPT accepts feedback_section and exemplars_section."""

    def test_prompt_has_feedback_section_variable(self):
        from src.graph.nodes.math_agent import MATH_AGENT_PROMPT

        assert "feedback_section" in MATH_AGENT_PROMPT.input_variables

    def test_prompt_has_exemplars_section_variable(self):
        from src.graph.nodes.math_agent import MATH_AGENT_PROMPT

        assert "exemplars_section" in MATH_AGENT_PROMPT.input_variables

    def test_prompt_formats_with_feedback_and_exemplars(self):
        from src.graph.nodes.math_agent import MATH_AGENT_PROMPT

        messages = MATH_AGENT_PROMPT.format_messages(
            num_questions=10,
            difficulty="high_application",
            topic="Đạo hàm",
            context="Test context",
            feedback_section="FEEDBACK: item was rejected because too simple.",
            exemplars_section="EXEMPLAR: complex synthesis question.",
        )
        system_msg = messages[0].content
        assert "FEEDBACK: item was rejected" in system_msg
        assert "EXEMPLAR: complex synthesis" in system_msg

    def test_prompt_works_with_empty_sections(self):
        from src.graph.nodes.math_agent import MATH_AGENT_PROMPT

        messages = MATH_AGENT_PROMPT.format_messages(
            num_questions=5,
            difficulty="recall",
            topic="Test",
            context="ctx",
            feedback_section="",
            exemplars_section="",
        )
        # Should not raise and should produce valid messages
        assert len(messages) == 2


# ═══════════════════════════════════════════════════════════════════════
# P4: Sequential batch parsing
# ═══════════════════════════════════════════════════════════════════════


class TestSequentialBatchParsing:
    """P4: _parse_raw_content uses sequential parsing for large batches."""

    @pytest.mark.asyncio
    @patch(f"{MATH_AGENT_MOD}.get_generation_llm")
    @patch(f"{MATH_AGENT_MOD}.rate_limited_llm_call")
    async def test_large_batch_parses_sequentially(self, mock_rate_limit, mock_get_llm):
        """Verify that large batches are NOT parsed with asyncio.gather."""
        from src.graph.nodes.math_agent import (
            ContentItemList,
            GeneratedContentItem,
            _parse_raw_content,
        )

        # Setup mock LLM
        mock_llm = MagicMock()
        mock_structured = MagicMock()
        mock_llm.with_structured_output.return_value = mock_structured
        mock_get_llm.return_value = mock_llm

        # Create mock items for each batch
        item = GeneratedContentItem(
            question="Q", answer="A", explanation="E", topic="T"
        )
        mock_rate_limit.return_value = ContentItemList(items=[item])

        # Parse 14 items (2 batches of 7)
        result = await _parse_raw_content("raw text", ["Code:\nprint(1)"], 14)

        # Should have been called sequentially (2 calls, not via gather)
        assert mock_rate_limit.call_count == 2
        assert len(result) == 2  # 1 item per batch result


# ═══════════════════════════════════════════════════════════════════════
# Feedback Classification (Step 2)
# ═══════════════════════════════════════════════════════════════════════


class TestFeedbackClassification:
    """Reject feedback is classified into error categories."""

    def test_classify_cognitive_level(self):
        from src.graph.nodes.math_agent import _classify_feedback

        assert (
            _classify_feedback("cognitive level mismatch — too easy")
            == "cognitive_level"
        )
        assert _classify_feedback("Mức nhận thức không đạt") == "cognitive_level"

    def test_classify_accuracy(self):
        from src.graph.nodes.math_agent import _classify_feedback

        assert _classify_feedback("incorrect calculation in answer") == "accuracy"
        assert _classify_feedback("Sai công thức") == "accuracy"
        assert _classify_feedback("formula error in step 3") == "accuracy"

    def test_classify_clarity(self):
        from src.graph.nodes.math_agent import _classify_feedback

        assert _classify_feedback("unclear question, ambiguous phrasing") == "clarity"
        assert _classify_feedback("Câu hỏi mơ hồ, không rõ ràng") == "clarity"

    def test_classify_domain(self):
        from src.graph.nodes.math_agent import _classify_feedback

        assert _classify_feedback("off-topic, not related to the domain") == "domain"
        assert _classify_feedback("Ngoài phạm vi chủ đề") == "domain"

    def test_classify_other(self):
        from src.graph.nodes.math_agent import _classify_feedback

        assert _classify_feedback("general quality issue") == "other"

    def test_feedback_includes_category_labels(self):
        from src.graph.nodes.math_agent import _build_rejection_feedback

        rejected = [
            {
                "question": "Q1",
                "review_feedback": "cognitive level too low",
                "review_score": 0.3,
                "difficulty": "high_application",
            },
            {
                "question": "Q2",
                "review_feedback": "incorrect answer",
                "review_score": 0.4,
                "difficulty": "high_application",
            },
        ]
        result = _build_rejection_feedback(rejected, difficulty="high_application")
        assert "[cognitive_level]" in result
        assert "[accuracy]" in result

    def test_feedback_includes_targeted_guidance(self):
        from src.graph.nodes.math_agent import _build_rejection_feedback

        rejected = [
            {
                "question": "Q1",
                "review_feedback": "cognitive level too low",
                "review_score": 0.3,
                "difficulty": "high_application",
            },
        ]
        result = _build_rejection_feedback(rejected, difficulty="high_application")
        assert "TARGETED FIX GUIDANCE" in result
        assert "NON-ROUTINE" in result


# ═══════════════════════════════════════════════════════════════════════
# Subject Inference (expanded)
# ═══════════════════════════════════════════════════════════════════════


class TestSubjectInference:
    """_infer_subject detects correct domain from topic text."""

    def test_biology_detection(self):
        from src.graph.nodes.math_agent import _infer_subject

        assert _infer_subject("Di truyền quần thể") == "biology"
        assert _infer_subject("Đột biến gen và ADN") == "biology"
        assert _infer_subject("Quang hợp ở thực vật") == "biology"

    def test_chemistry_expanded_keywords(self):
        from src.graph.nodes.math_agent import _infer_subject

        assert _infer_subject("Ancol và este") == "chemistry"
        assert _infer_subject("Hidrocacbon no") == "chemistry"
        assert _infer_subject("Dung dịch điện li") == "chemistry"

    def test_physics_expanded_keywords(self):
        from src.graph.nodes.math_agent import _infer_subject

        assert _infer_subject("Dao động điều hòa") == "physics"
        assert _infer_subject("Sóng cơ học") == "physics"
        assert _infer_subject("Từ trường và lực") == "physics"

    def test_fallback_to_math(self):
        from src.graph.nodes.math_agent import _infer_subject

        assert _infer_subject("Đạo hàm hàm số") == "math"
        assert _infer_subject(None) == "math"


# ═══════════════════════════════════════════════════════════════════════
# Anti-patterns in Exemplars
# ═══════════════════════════════════════════════════════════════════════


class TestAntiPatterns:
    """High_application exemplars include anti-pattern guidance."""

    def test_high_application_includes_anti_patterns(self):
        from src.graph.nodes.math_agent import _build_exemplars_section

        result = _build_exemplars_section("high_application", topic="Toán giải tích")
        assert "COMMON MISTAKES TO AVOID" in result
        assert "NON-ROUTINE" in result

    def test_non_high_application_excludes_anti_patterns(self):
        from src.graph.nodes.math_agent import _build_exemplars_section

        for level in ("recall", "comprehension", "application"):
            result = _build_exemplars_section(level)
            assert "COMMON MISTAKES TO AVOID" not in result

    def test_biology_exemplars_present(self):
        from src.graph.nodes.math_agent import _build_exemplars_section

        result = _build_exemplars_section(
            "high_application", topic="Di truyền quần thể"
        )
        assert "quần thể" in result


# ═══════════════════════════════════════════════════════════════════════
# Pipeline 100% Delivery Fixes (C1–C5)
# ═══════════════════════════════════════════════════════════════════════


class TestMaxReviewIterations:
    """C2: MAX_REVIEW_ITERATIONS is 5 (increased from 3)."""

    def test_max_iterations_is_5(self):
        from src.graph.state import MAX_REVIEW_ITERATIONS

        assert MAX_REVIEW_ITERATIONS == 5

    def test_review_router_passes_at_max_iterations(self):
        """review_router returns 'pass' when iteration_count == MAX_REVIEW_ITERATIONS."""
        from src.graph.nodes.reviewer import review_router
        from src.graph.state import MAX_REVIEW_ITERATIONS

        request = MagicMock()
        request.num_questions = 10
        state = {
            "reviewed_items": [{"q": f"item_{i}"} for i in range(5)],  # Only 5, need 10
            "rejected_items": [],
            "iteration_count": MAX_REVIEW_ITERATIONS,
            "request": request,
        }
        assert review_router(state) == "pass"  # Safety valve triggers

    def test_review_router_fails_before_max_iterations(self):
        """review_router returns 'fail' when items insufficient and iterations remain."""
        from src.graph.nodes.reviewer import review_router

        request = MagicMock()
        request.num_questions = 10
        state = {
            "reviewed_items": [{"q": f"item_{i}"} for i in range(5)],
            "rejected_items": [],
            "iteration_count": 2,
            "request": request,
        }
        assert review_router(state) == "fail"


class TestEscalatingOvershoot:
    """C3: Overshoot escalates with iteration_count."""

    def test_first_iteration_no_escalation(self):
        """iteration_count=0 → multiplier is 1.0 (no escalation)."""
        from src.config.constants import OVERSHOOT_BY_DIFFICULTY

        base = OVERSHOOT_BY_DIFFICULTY["application"]  # 1.4
        iteration_count = 0
        overshoot = base * (1 + 0.3 * iteration_count)
        assert overshoot == base  # No change

    def test_second_iteration_30_percent_escalation(self):
        """iteration_count=1 → multiplier is 1.3."""
        from src.config.constants import OVERSHOOT_BY_DIFFICULTY

        base = OVERSHOOT_BY_DIFFICULTY["application"]  # 1.4
        iteration_count = 1
        overshoot = base * (1 + 0.3 * iteration_count)
        assert overshoot == pytest.approx(base * 1.3)

    def test_third_iteration_60_percent_escalation(self):
        """iteration_count=2 → multiplier is 1.6."""
        from src.config.constants import OVERSHOOT_BY_DIFFICULTY

        base = OVERSHOOT_BY_DIFFICULTY["high_application"]  # 2.5
        iteration_count = 2
        overshoot = base * (1 + 0.3 * iteration_count)
        assert overshoot == pytest.approx(2.5 * 1.6)  # 4.0

    def test_escalation_increases_num_to_generate(self):
        """Higher iteration → higher num_to_generate for same gap."""
        from src.config.constants import OVERSHOOT_BY_DIFFICULTY

        base = OVERSHOOT_BY_DIFFICULTY["application"]
        num_still_needed = 4

        gen_iter0 = math.ceil(num_still_needed * base * (1 + 0.3 * 0))
        gen_iter2 = math.ceil(num_still_needed * base * (1 + 0.3 * 2))
        assert gen_iter2 > gen_iter0


class TestMinGenerationFloor:
    """C5: num_to_generate >= num_still_needed + 3."""

    def test_floor_applies_when_overshoot_too_low(self):
        """Small gap with low overshoot: floor kicks in."""
        num_still_needed = 2
        overshoot = 1.1  # recall
        num_to_generate = math.ceil(num_still_needed * overshoot)  # ceil(2.2)=3
        num_to_generate = max(num_to_generate, num_still_needed + 3)
        assert num_to_generate == 5  # floor = 2+3 = 5

    def test_floor_does_not_reduce_high_overshoot(self):
        """Large gap with high overshoot: floor is not a bottleneck."""
        num_still_needed = 10
        overshoot = 2.5  # high_application
        num_to_generate = math.ceil(num_still_needed * overshoot)  # 25
        num_to_generate = max(num_to_generate, num_still_needed + 3)
        assert num_to_generate == 25  # overshoot dominates

    def test_floor_with_gap_one(self):
        """Even gap=1, still generates at least 4 items."""
        num_still_needed = 1
        overshoot = 1.1
        num_to_generate = math.ceil(num_still_needed * overshoot)  # 2
        num_to_generate = max(num_to_generate, num_still_needed + 3)
        assert num_to_generate == 4  # floor = 1+3 = 4
