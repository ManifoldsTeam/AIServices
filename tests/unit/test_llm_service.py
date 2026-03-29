"""Unit tests for src/services/llm.py — LLM factory + caching."""

from unittest.mock import MagicMock, patch

import pytest


# ─── Helpers ────────────────────────────────────────────────────────

MODULE = "src.services.llm"


def _clear_caches():
    """Clear lru_cache between tests so instances are not shared."""
    from src.services.llm import get_generation_llm, get_review_llm

    get_generation_llm.cache_clear()
    get_review_llm.cache_clear()


# ─── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clear(patch_settings):
    """Ensure clean cache + mocked settings for every test."""
    _clear_caches()
    yield
    _clear_caches()


# ─── get_generation_llm ─────────────────────────────────────────────


class TestGetGenerationLlm:
    """Tests for get_generation_llm() factory + caching."""

    @patch(f"{MODULE}.ChatGoogleGenerativeAI")
    def test_returns_llm_instance(self, mock_cls):
        from src.services.llm import get_generation_llm

        mock_cls.return_value = MagicMock()
        llm = get_generation_llm()
        assert llm is mock_cls.return_value

    @patch(f"{MODULE}.ChatGoogleGenerativeAI")
    def test_passes_correct_params(self, mock_cls):
        from src.services.llm import get_generation_llm

        get_generation_llm(temperature=0.5, max_output_tokens=4096)
        mock_cls.assert_called_once_with(
            model="gemini-3-flash-preview",
            project="test-project",
            location="global",
            temperature=0.5,
            max_output_tokens=4096,
            max_retries=3,
        )

    @patch(f"{MODULE}.ChatGoogleGenerativeAI")
    def test_cache_same_params_returns_same_instance(self, mock_cls):
        from src.services.llm import get_generation_llm

        mock_cls.return_value = MagicMock()
        a = get_generation_llm(temperature=0.7, max_output_tokens=8192)
        b = get_generation_llm(temperature=0.7, max_output_tokens=8192)
        assert a is b
        assert mock_cls.call_count == 1

    @patch(f"{MODULE}.ChatGoogleGenerativeAI")
    def test_cache_diff_params_returns_diff_instance(self, mock_cls):
        from src.services.llm import get_generation_llm

        mock_cls.side_effect = [MagicMock(), MagicMock()]
        a = get_generation_llm(temperature=0.7, max_output_tokens=8192)
        b = get_generation_llm(temperature=0.3, max_output_tokens=4096)
        assert a is not b
        assert mock_cls.call_count == 2


# ─── get_review_llm ─────────────────────────────────────────────────


class TestGetReviewLlm:
    """Tests for get_review_llm() factory + caching."""

    @patch(f"{MODULE}.ChatGoogleGenerativeAI")
    def test_uses_review_model(self, mock_cls):
        from src.services.llm import get_review_llm

        get_review_llm(temperature=0.0, max_output_tokens=4096)
        mock_cls.assert_called_once_with(
            model="gemini-3-flash-preview",
            project="test-project",
            location="global",
            temperature=0.0,
            max_output_tokens=4096,
            max_retries=3,
        )

    @patch(f"{MODULE}.ChatGoogleGenerativeAI")
    def test_cache_same_params(self, mock_cls):
        from src.services.llm import get_review_llm

        mock_cls.return_value = MagicMock()
        a = get_review_llm()
        b = get_review_llm()
        assert a is b
        assert mock_cls.call_count == 1


# ─── get_structured_llm ─────────────────────────────────────────────


class TestGetStructuredLlm:
    """Tests for get_structured_llm() — delegates to cached generation LLM."""

    @patch(f"{MODULE}.ChatGoogleGenerativeAI")
    def test_calls_with_structured_output(self, mock_cls):
        from src.services.llm import get_structured_llm

        base_llm = MagicMock()
        structured_runnable = MagicMock()
        base_llm.with_structured_output.return_value = structured_runnable
        mock_cls.return_value = base_llm

        class FakeSchema:
            pass

        result = get_structured_llm(FakeSchema)
        base_llm.with_structured_output.assert_called_once_with(FakeSchema)
        assert result is structured_runnable

    @patch(f"{MODULE}.ChatGoogleGenerativeAI")
    def test_uses_structured_temperature(self, mock_cls):
        from src.services.llm import get_structured_llm
        from src.config.constants import STRUCTURED_TEMPERATURE, STRUCTURED_MAX_TOKENS

        mock_cls.return_value = MagicMock()

        class FakeSchema:
            pass

        get_structured_llm(FakeSchema)
        mock_cls.assert_called_once_with(
            model="gemini-3-flash-preview",
            project="test-project",
            location="global",
            temperature=STRUCTURED_TEMPERATURE,
            max_output_tokens=STRUCTURED_MAX_TOKENS,
            max_retries=3,
        )
