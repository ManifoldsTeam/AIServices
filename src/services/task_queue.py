"""Cloud Tasks service — async generation job dispatch.

Handles:
1. Enqueue generation jobs to Cloud Tasks
2. Cloud Tasks triggers internal HTTP endpoint on Cloud Run
3. Retry policy: max 3 retries, exponential backoff

Flow:
  POST /api/v1/generate
    → Create job in Firestore (status: "processing")
    → Enqueue task in Cloud Tasks
    → Return 202 { request_id }

  Cloud Tasks → POST /internal/execute-generation/{request_id}
    → Run LangGraph pipeline
    → Update Firestore (status: "completed" or "failed")
"""

import json

import structlog
from google.cloud import tasks_v2
from google.protobuf import duration_pb2, timestamp_pb2

from src.config import get_settings

logger = structlog.get_logger(__name__)


def _get_client() -> tasks_v2.CloudTasksClient:
    """Get Cloud Tasks client."""
    return tasks_v2.CloudTasksClient()


def enqueue_generation(
    request_id: str,
    cloud_run_url: str,
    service_account_email: str | None = None,
) -> str:
    """Dispatch a generation job to Cloud Tasks.

    The task will trigger an HTTP POST to the internal endpoint
    on Cloud Run, which runs the LangGraph pipeline.

    Args:
        request_id: Unique job identifier (created in Firestore first).
        cloud_run_url: Base URL of the Cloud Run service.
        service_account_email: SA email for OIDC token (Cloud Run auth).

    Returns:
        Cloud Tasks task name.

    Raises:
        Exception: On task creation failure.
    """
    settings = get_settings()
    client = _get_client()

    parent = client.queue_path(
        settings.gcp_project_id,
        settings.cloud_tasks_location,
        settings.cloud_tasks_queue,
    )

    url = f"{cloud_run_url}/internal/execute-generation/{request_id}"

    logger.info(
        "enqueuing_generation",
        request_id=request_id,
        queue=settings.cloud_tasks_queue,
        url=url,
    )

    # Build HTTP request
    http_request = tasks_v2.HttpRequest(
        http_method=tasks_v2.HttpMethod.POST,
        url=url,
        headers={"Content-Type": "application/json"},
        body=json.dumps({"request_id": request_id}).encode(),
    )

    # Add OIDC token for Cloud Run authentication (production)
    if service_account_email:
        http_request.oidc_token = tasks_v2.OidcToken(
            service_account_email=service_account_email,
            audience=cloud_run_url,
        )

    task = tasks_v2.Task(http_request=http_request)

    response = client.create_task(
        parent=parent,
        task=task,
    )

    logger.info(
        "generation_enqueued",
        request_id=request_id,
        task_name=response.name,
    )

    return response.name
