"""System test — full import chain + singleton identity checks.

Verifies that the entire src/ package is importable and that all
singleton/cache patterns produce consistent instances across the process.
This mirrors the manual verification script but as automated pytest.
"""

from unittest.mock import MagicMock, patch

import pytest


MODULE_LLM = "src.services.llm"


@pytest.fixture(autouse=True)
def _setup(patch_settings):
    """Patch settings and reset all singletons."""
    from src.services.llm import get_generation_llm, get_review_llm

    get_generation_llm.cache_clear()
    get_review_llm.cache_clear()

    import src.services.firestore as fs_mod
    import src.services.document_store as ds_mod
    import src.services.task_queue as tq_mod

    fs_mod._client = None
    ds_mod._storage_client = None
    tq_mod._tasks_client = None
    yield
    get_generation_llm.cache_clear()
    get_review_llm.cache_clear()
    fs_mod._client = None
    ds_mod._storage_client = None
    tq_mod._tasks_client = None


# ─── Import Chain ────────────────────────────────────────────────────


class TestImportChain:
    """Verify all modules import without error."""

    def test_import_services(self):
        from src.services import llm, firestore, document_store, task_queue

        assert llm.get_generation_llm is not None
        assert llm.get_review_llm is not None
        assert llm.get_structured_llm is not None

    def test_import_graph_nodes(self):
        from src.graph.nodes import formatter, supervisor, reviewer, math_agent

        assert callable(formatter._get_llm)
        assert callable(supervisor._get_llm)
        assert callable(reviewer._get_llm)
        assert callable(math_agent._get_llm)

    def test_import_config(self):
        from src.config import get_settings, constants

        assert constants.GENERATION_TEMPERATURE is not None
        assert constants.REVIEW_TEMPERATURE is not None

    def test_import_graph_builder(self):
        from src.graph.builder import get_graph_app

        assert callable(get_graph_app)


# ─── Full Singleton Identity ─────────────────────────────────────────


class TestSingletonIdentityAcrossModules:
    """End-to-end: calling factory from different modules returns same instance."""

    @patch(f"{MODULE_LLM}.ChatGoogleGenerativeAI")
    def test_llm_generation_identity(self, mock_cls):
        """get_generation_llm() → same instance across math_agent and formatter."""
        mock_cls.return_value = MagicMock()

        from src.services.llm import get_generation_llm
        from src.graph.nodes.math_agent import _get_llm as math_get

        direct = get_generation_llm()
        from_node = math_get()
        assert direct is from_node

    @patch(f"{MODULE_LLM}.ChatGoogleGenerativeAI")
    def test_llm_review_identity(self, mock_cls):
        """get_review_llm(temp=0, tokens=10) → same instance from supervisor."""
        mock_cls.return_value = MagicMock()

        from src.services.llm import get_review_llm
        from src.graph.nodes.supervisor import _get_llm as sup_get

        direct = get_review_llm(temperature=0, max_output_tokens=10)
        from_node = sup_get()
        assert direct is from_node

    @patch("src.services.firestore.firestore.AsyncClient")
    def test_firestore_identity(self, mock_cls):
        """Firestore _get_client() always returns same instance."""
        mock_cls.return_value = MagicMock()

        from src.services.firestore import _get_client

        a = _get_client()
        b = _get_client()
        c = _get_client()
        assert a is b is c
        assert mock_cls.call_count == 1

    @patch("src.services.document_store.storage.Client")
    def test_gcs_identity(self, mock_cls):
        """GCS _get_storage_client() always returns same instance."""
        mock_cls.return_value = MagicMock()

        from src.services.document_store import _get_storage_client

        a = _get_storage_client()
        b = _get_storage_client()
        c = _get_storage_client()
        assert a is b is c
        assert mock_cls.call_count == 1

    @patch("src.services.task_queue.tasks_v2.CloudTasksClient")
    def test_cloud_tasks_identity(self, mock_cls):
        """CloudTasks _get_client() always returns same instance."""
        mock_cls.return_value = MagicMock()

        from src.services.task_queue import _get_client

        a = _get_client()
        b = _get_client()
        c = _get_client()
        assert a is b is c
        assert mock_cls.call_count == 1


# ─── No deprecated imports in src/ ───────────────────────────────────


class TestNoDeprecatedImports:
    """Scan all Python files in src/ for ChatVertexAI references."""

    def test_no_chat_vertex_ai_anywhere(self):
        from pathlib import Path

        src_dir = Path(__file__).parent.parent.parent / "src"
        violations = []
        for py_file in src_dir.rglob("*.py"):
            content = py_file.read_text()
            if "ChatVertexAI" in content or "langchain_google_vertexai" in content:
                violations.append(str(py_file.relative_to(src_dir.parent)))

        assert violations == [], f"Deprecated ChatVertexAI found in: {violations}"
