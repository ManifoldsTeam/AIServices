"""Public generation endpoints (async Cloud Tasks flow)."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from src.api.schemas.requests import GenerationRequest
from src.api.schemas.responses import JobResponse, JobStatus
from src.api.schemas.game_content import GameType, DifficultyLevel
from src.config import get_settings
from src.services.generation_executor import execute_generation_job
from src.services.firestore import create_job, get_job
from src.services.task_queue import enqueue_generation

router = APIRouter(prefix="/api/v1", tags=["generation"])


@router.post(
    "/generate", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED
)
async def create_generation_job(
    request: GenerationRequest,
    background_tasks: BackgroundTasks,
) -> JobResponse:
    """Create job record and enqueue Cloud Task for async execution."""
    settings = get_settings()

    request_id = str(uuid.uuid4())
    await create_job(
        request_id=request_id,
        user_id=request.user_id,
        request_data=request.model_dump(mode="json"),
    )

    created_at = datetime.now(timezone.utc)

    if settings.cloud_run_base_url:
        try:
            enqueue_generation(
                request_id=request_id,
                cloud_run_url=settings.cloud_run_base_url,
                service_account_email=settings.cloud_tasks_invoker_service_account,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to enqueue generation task: {exc}",
            ) from exc
    elif settings.local_async_mode:
        background_tasks.add_task(execute_generation_job, request_id)
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Set CLOUD_RUN_BASE_URL or enable LOCAL_ASYNC_MODE",
        )

    return JobResponse(
        request_id=request_id,
        status=JobStatus.PROCESSING,
        content=None,
        error=None,
        created_at=created_at,
        completed_at=None,
    )


@router.get("/generations/{request_id}", response_model=JobResponse)
async def get_generation_job(request_id: str) -> JobResponse:
    """Poll generation status/result by request id."""
    job = await get_job(request_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
        )

    status_value = job.get("status", JobStatus.FAILED)
    try:
        parsed_status = JobStatus(status_value)
    except ValueError:
        import logging

        logging.getLogger(__name__).warning(
            "Invalid job status %r for request %s, defaulting to FAILED",
            status_value,
            request_id,
        )
        parsed_status = JobStatus.FAILED

    return JobResponse(
        request_id=job["request_id"],
        status=parsed_status,
        content=job.get("content"),
        error=job.get("error"),
        created_at=job["created_at"],
        completed_at=job.get("completed_at"),
    )


@router.get("/game-types")
async def list_game_types() -> list[dict]:
    """List supported game types with their difficulty levels.

    Used by Game Client to discover available content formats.
    """
    return [
        {
            "type": game_type.value,
            "name": game_type.name.replace("_", " ").title(),
            "difficulties": [d.value for d in DifficultyLevel],
        }
        for game_type in GameType
    ]
