"""Unit tests for singleton GCP clients: Firestore, GCS, CloudTasks."""

from unittest.mock import MagicMock, patch

import pytest


# ─── Firestore Singleton ────────────────────────────────────────────


class TestFirestoreSingleton:
    """Tests for src.services.firestore._get_client() singleton."""

    @pytest.fixture(autouse=True)
    def _reset(self, patch_settings):
        """Reset singleton before/after each test."""
        import src.services.firestore as mod

        mod._client = None
        yield
        mod._client = None

    @patch("src.services.firestore.firestore.AsyncClient")
    def test_creates_client_on_first_call(self, mock_cls):
        from src.services.firestore import _get_client

        mock_cls.return_value = MagicMock()
        client = _get_client()
        mock_cls.assert_called_once_with(
            project="test-project",
            database="test-db",
        )
        assert client is mock_cls.return_value

    @patch("src.services.firestore.firestore.AsyncClient")
    def test_returns_same_client_on_second_call(self, mock_cls):
        from src.services.firestore import _get_client

        mock_cls.return_value = MagicMock()
        a = _get_client()
        b = _get_client()
        assert a is b
        assert mock_cls.call_count == 1

    @patch("src.services.firestore.firestore.AsyncClient")
    def test_resets_when_global_cleared(self, mock_cls):
        import src.services.firestore as mod
        from src.services.firestore import _get_client

        first = MagicMock()
        second = MagicMock()
        mock_cls.side_effect = [first, second]

        a = _get_client()
        assert a is first

        mod._client = None
        b = _get_client()
        assert b is second
        assert a is not b


# ─── GCS Singleton ──────────────────────────────────────────────────


class TestGCSSingleton:
    """Tests for src.services.document_store._get_storage_client() singleton."""

    @pytest.fixture(autouse=True)
    def _reset(self, patch_settings):
        import src.services.document_store as mod

        mod._storage_client = None
        yield
        mod._storage_client = None

    @patch("src.services.document_store.storage.Client")
    def test_creates_client_on_first_call(self, mock_cls):
        from src.services.document_store import _get_storage_client

        mock_cls.return_value = MagicMock()
        client = _get_storage_client()
        mock_cls.assert_called_once_with(project="test-project")
        assert client is mock_cls.return_value

    @patch("src.services.document_store.storage.Client")
    def test_returns_same_client_on_second_call(self, mock_cls):
        from src.services.document_store import _get_storage_client

        mock_cls.return_value = MagicMock()
        a = _get_storage_client()
        b = _get_storage_client()
        assert a is b
        assert mock_cls.call_count == 1

    @patch("src.services.document_store.storage.Client")
    def test_resets_when_global_cleared(self, mock_cls):
        import src.services.document_store as mod
        from src.services.document_store import _get_storage_client

        first = MagicMock()
        second = MagicMock()
        mock_cls.side_effect = [first, second]

        a = _get_storage_client()
        mod._storage_client = None
        b = _get_storage_client()
        assert a is not b


# ─── CloudTasks Singleton ───────────────────────────────────────────


class TestCloudTasksSingleton:
    """Tests for src.services.task_queue._get_client() singleton."""

    @pytest.fixture(autouse=True)
    def _reset(self, patch_settings):
        import src.services.task_queue as mod

        mod._tasks_client = None
        yield
        mod._tasks_client = None

    @patch("src.services.task_queue.tasks_v2.CloudTasksClient")
    def test_creates_client_on_first_call(self, mock_cls):
        from src.services.task_queue import _get_client

        mock_cls.return_value = MagicMock()
        client = _get_client()
        mock_cls.assert_called_once()
        assert client is mock_cls.return_value

    @patch("src.services.task_queue.tasks_v2.CloudTasksClient")
    def test_returns_same_client_on_second_call(self, mock_cls):
        from src.services.task_queue import _get_client

        mock_cls.return_value = MagicMock()
        a = _get_client()
        b = _get_client()
        assert a is b
        assert mock_cls.call_count == 1

    @patch("src.services.task_queue.tasks_v2.CloudTasksClient")
    def test_resets_when_global_cleared(self, mock_cls):
        import src.services.task_queue as mod
        from src.services.task_queue import _get_client

        first = MagicMock()
        second = MagicMock()
        mock_cls.side_effect = [first, second]

        a = _get_client()
        mod._tasks_client = None
        b = _get_client()
        assert a is not b
