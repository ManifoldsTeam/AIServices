"""Internal endpoints invoked by Cloud Tasks."""

from fastapi import APIRouter, Header, HTTPException, status

from src.services.generation_executor import execute_generation_job
from src.services.firestore import get_job

router = APIRouter(prefix="/internal", tags=["internal"])


def _verify_cloud_tasks_headers(
    task_name: str | None,
    queue_name: str | None,
) -> None:
    """Ensure endpoint is called by Cloud Tasks.

    Cloud Tasks injects X-CloudTasks-* headers on HTTP dispatches.
    """
    if not task_name or not queue_name:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: missing Cloud Tasks headers",
        )


@router.post("/execute-generation/{request_id}")
async def execute_generation(
    request_id: str,
    x_cloudtasks_taskname: str | None = Header(default=None),
    x_cloudtasks_queuename: str | None = Header(default=None),
) -> dict:
    """Execute LangGraph pipeline for a queued generation job."""
    _verify_cloud_tasks_headers(
        task_name=x_cloudtasks_taskname,
        queue_name=x_cloudtasks_queuename,
    )

    job = await get_job(request_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
        )

    try:
        return await execute_generation_job(request_id)

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Generation failed: {exc}",
        ) from exc
