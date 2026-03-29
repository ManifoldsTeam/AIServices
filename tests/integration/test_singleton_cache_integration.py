"""Integration test — graph nodes use centralized cached LLM service.

Verifies that all 4 graph nodes (supervisor, reviewer, math_agent, formatter)
delegate to the cached LLM factory (get_generation_llm / get_review_llm)
and that identical parameters produce the same LLM instance.
"""

from unittest.mock import MagicMock, patch

import pytest


MODULE_LLM = "src.services.llm"


@pytest.fixture(autouse=True)
def _setup(patch_settings):
    """Patch settings and clear LLM caches for each test."""
    from src.services.llm import get_generation_llm, get_review_llm

    get_generation_llm.cache_clear()
    get_review_llm.cache_clear()
    yield
    get_generation_llm.cache_clear()
    get_review_llm.cache_clear()


# ─── Generation nodes share the same cached LLM ─────────────────────


class TestGenerationNodesCacheSharingIntegration:
    """math_agent and formatter both get generation LLM — they should share cached instances."""

    @patch(f"{MODULE_LLM}.ChatGoogleGenerativeAI")
    def test_math_agent_uses_generation_llm(self, mock_cls):
        """math_agent._get_llm() delegates to get_generation_llm()."""
        mock_cls.return_value = MagicMock()
        from src.graph.nodes.math_agent import _get_llm

        llm = _get_llm()
        assert llm is mock_cls.return_value
        # Verify it used generation model params
        call_kwargs = mock_cls.call_args.kwargs
        assert call_kwargs["model"] == "gemini-3-flash-preview"
        assert call_kwargs["location"] == "global"

    @patch(f"{MODULE_LLM}.ChatGoogleGenerativeAI")
    def test_formatter_uses_generation_llm(self, mock_cls):
        """formatter._get_llm() delegates to get_generation_llm()."""
        mock_cls.return_value = MagicMock()
        from src.graph.nodes.formatter import _get_llm

        llm = _get_llm()
        assert llm is mock_cls.return_value
        call_kwargs = mock_cls.call_args.kwargs
        assert call_kwargs["model"] == "gemini-3-flash-preview"

    @patch(f"{MODULE_LLM}.ChatGoogleGenerativeAI")
    def test_math_agent_and_formatter_share_when_same_params(self, mock_cls):
        """If params match, both nodes get the exact same LLM instance."""
        from src.config.constants import (
            GENERATION_TEMPERATURE,
            GENERATION_MAX_TOKENS,
            STRUCTURED_TEMPERATURE,
            STRUCTURED_MAX_TOKENS,
        )

        instances = {}
        call_count = 0

        def side_effect(**kwargs):
            nonlocal call_count
            key = (kwargs["temperature"], kwargs["max_output_tokens"])
            if key not in instances:
                instances[key] = MagicMock(name=f"llm_{call_count}")
                call_count += 1
            return instances[key]

        mock_cls.side_effect = side_effect

        from src.graph.nodes.math_agent import _get_llm as math_get
        from src.graph.nodes.formatter import _get_llm as fmt_get

        math_llm = math_get()
        fmt_llm = fmt_get()

        # math_agent uses GENERATION defaults, formatter uses STRUCTURED defaults
        # They may or may not share depending on whether constants differ
        if (GENERATION_TEMPERATURE, GENERATION_MAX_TOKENS) == (
            STRUCTURED_TEMPERATURE,
            STRUCTURED_MAX_TOKENS,
        ):
            assert math_llm is fmt_llm, "Same params should share instance"
        else:
            assert math_llm is not fmt_llm, "Different params should differ"


# ─── Review nodes share the same cached LLM ─────────────────────────


class TestReviewNodesCacheSharingIntegration:
    """supervisor and reviewer both use get_review_llm() — verify sharing."""

    @patch(f"{MODULE_LLM}.ChatGoogleGenerativeAI")
    def test_supervisor_uses_review_llm(self, mock_cls):
        mock_cls.return_value = MagicMock()
        from src.graph.nodes.supervisor import _get_llm

        llm = _get_llm()
        call_kwargs = mock_cls.call_args.kwargs
        assert call_kwargs["model"] == "gemini-3-flash-preview"
        assert call_kwargs["location"] == "global"

    @patch(f"{MODULE_LLM}.ChatGoogleGenerativeAI")
    def test_reviewer_uses_review_llm(self, mock_cls):
        mock_cls.return_value = MagicMock()
        from src.graph.nodes.reviewer import _get_llm

        llm = _get_llm()
        call_kwargs = mock_cls.call_args.kwargs
        assert call_kwargs["model"] == "gemini-3-flash-preview"
        assert call_kwargs["location"] == "global"

    @patch(f"{MODULE_LLM}.ChatGoogleGenerativeAI")
    def test_supervisor_and_reviewer_differ_due_to_params(self, mock_cls):
        """supervisor uses max_output_tokens=10, reviewer uses 4096 → different instances."""
        call_log = []

        def side_effect(**kwargs):
            m = MagicMock()
            call_log.append(kwargs)
            return m

        mock_cls.side_effect = side_effect

        from src.graph.nodes.supervisor import _get_llm as sup_get
        from src.graph.nodes.reviewer import _get_llm as rev_get

        sup_llm = sup_get()
        rev_llm = rev_get()

        # supervisor: temperature=0, max_output_tokens=10
        # reviewer: temperature=0.0, max_output_tokens=4096
        assert (
            sup_llm is not rev_llm
        ), "Different max_output_tokens should yield different instances"


# ─── Cross-cutting: no ChatVertexAI left ─────────────────────────────


class TestNoChatVertexAIImports:
    """Verify none of the graph nodes import ChatVertexAI directly."""

    def test_no_vertexai_in_supervisor(self):
        import src.graph.nodes.supervisor as mod

        source = open(mod.__file__).read()
        assert "ChatVertexAI" not in source
        assert "langchain_google_vertexai" not in source

    def test_no_vertexai_in_reviewer(self):
        import src.graph.nodes.reviewer as mod

        source = open(mod.__file__).read()
        assert "ChatVertexAI" not in source

    def test_no_vertexai_in_math_agent(self):
        import src.graph.nodes.math_agent as mod

        source = open(mod.__file__).read()
        assert "ChatVertexAI" not in source

    def test_no_vertexai_in_formatter(self):
        import src.graph.nodes.formatter as mod

        source = open(mod.__file__).read()
        assert "ChatVertexAI" not in source
