"""Shared fixtures for all test levels (unit, integration, system).

Provides mock settings and GCP service stubs so tests never hit real APIs.
"""

from __future__ import annotations

from unittest.mock import MagicMock, AsyncMock, patch

import pytest


# ─── Mock Settings ──────────────────────────────────────────────────


class _FakeSettings:
    """Minimal settings stub matching src.config.settings.Settings fields."""

    env = "develop"
    gcp_project_id = "test-project"
    gcp_location = "us-central1"
    generation_model = "gemini-3-flash-preview"
    generation_model_location = "global"
    review_model = "gemini-3-flash-preview"
    review_model_location = "global"
    gcs_bucket = "test-bucket"
    firestore_database = "test-db"
    cloud_tasks_queue = "test-queue"
    cloud_tasks_location = "us-central1"
    cloud_tasks_invoker_service_account = None
    cloud_run_base_url = "https://test.run.app"
    local_async_mode = False
    system_user_id = "__system__"
    data_store_id = "test-ds"
    search_engine_id = "test-engine"
    data_store_location = "global"
    llm_rate_limit_rpm = 60
    llm_max_concurrent = 10
    log_level = "INFO"
    log_format = "console"
    host = "0.0.0.0"
    port = 8000


@pytest.fixture()
def fake_settings():
    """Return a FakeSettings instance."""
    return _FakeSettings()


@pytest.fixture()
def patch_settings(fake_settings):
    """Patch get_settings() globally to return fake_settings."""
    with patch("src.config.get_settings", return_value=fake_settings):
        yield fake_settings


# ─── LLM Mocks ─────────────────────────────────────────────────────


@pytest.fixture()
def mock_chat_llm():
    """A MagicMock that behaves like ChatGoogleGenerativeAI."""
    llm = MagicMock()
    llm.model = "gemini-3-flash-preview"
    llm.temperature = 0.7
    llm.max_output_tokens = 8192
    llm.with_structured_output = MagicMock(return_value=MagicMock())
    llm.ainvoke = AsyncMock(return_value=MagicMock(content="test response"))
    return llm


# ─── GCP Client Mocks ──────────────────────────────────────────────


@pytest.fixture()
def mock_firestore_client():
    """Mock Firestore AsyncClient."""
    client = MagicMock()
    doc_ref = MagicMock()
    doc_ref.set = AsyncMock()
    doc_ref.get = AsyncMock()
    doc_ref.update = AsyncMock()
    client.collection.return_value.document.return_value = doc_ref
    return client


@pytest.fixture()
def mock_gcs_client():
    """Mock GCS storage.Client."""
    client = MagicMock()
    bucket = MagicMock()
    blob = MagicMock()
    blob.upload_from_file = MagicMock()
    bucket.blob.return_value = blob
    client.bucket.return_value = bucket
    return client


@pytest.fixture()
def mock_tasks_client():
    """Mock CloudTasks client."""
    client = MagicMock()
    client.queue_path.return_value = "projects/test/locations/us/queues/test"
    client.create_task.return_value = MagicMock(name="tasks/123")
    return client
