"""Firestore service — CRUD operations + job status tracking.

Handles:
1. Generation job lifecycle (create → processing → completed/failed)
2. Document records tracking
3. User data storage

Collections:
- generations/{request_id}: Job status + results
- documents/{doc_id}: Document metadata
"""

from datetime import datetime, timezone
from typing import Any

import structlog
from google.cloud import firestore

from src.config import get_settings

logger = structlog.get_logger(__name__)


def _get_client() -> firestore.AsyncClient:
    """Get Firestore async client."""
    settings = get_settings()
    return firestore.AsyncClient(
        project=settings.gcp_project_id,
        database=settings.firestore_database,
    )


# ─── Generation Jobs ────────────────────────────────────────────


async def create_job(
    request_id: str,
    user_id: str,
    request_data: dict,
) -> dict:
    """Create a new generation job record.

    Args:
        request_id: Unique job identifier.
        user_id: User who initiated the generation.
        request_data: Serialized GenerationRequest.

    Returns:
        Created job record.
    """
    client = _get_client()

    job = {
        "request_id": request_id,
        "user_id": user_id,
        "status": "processing",
        "request": request_data,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }

    logger.info("creating_job", request_id=request_id, user_id=user_id)

    doc_ref = client.collection("generations").document(request_id)
    await doc_ref.set(job)

    logger.info("job_created", request_id=request_id)
    return job


async def get_job(request_id: str) -> dict | None:
    """Get a generation job by ID.

    Args:
        request_id: Job identifier.

    Returns:
        Job dict or None if not found.
    """
    client = _get_client()
    doc_ref = client.collection("generations").document(request_id)
    doc = await doc_ref.get()

    if not doc.exists:
        logger.warning("job_not_found", request_id=request_id)
        return None

    return doc.to_dict()


async def update_job(request_id: str, updates: dict) -> bool:
    """Update a generation job.

    Args:
        request_id: Job identifier.
        updates: Fields to update.

    Returns:
        True if updated successfully.
    """
    client = _get_client()

    updates["updated_at"] = datetime.now(timezone.utc)

    logger.info(
        "updating_job",
        request_id=request_id,
        status=updates.get("status"),
    )

    doc_ref = client.collection("generations").document(request_id)
    await doc_ref.update(updates)

    return True


async def complete_job(request_id: str, content: dict) -> bool:
    """Mark a generation job as completed with results.

    Args:
        request_id: Job identifier.
        content: Generated content result.

    Returns:
        True if updated.
    """
    return await update_job(
        request_id,
        {
            "status": "completed",
            "content": content,
            "completed_at": datetime.now(timezone.utc),
        },
    )


async def fail_job(request_id: str, error: str) -> bool:
    """Mark a generation job as failed.

    Args:
        request_id: Job identifier.
        error: Error message.

    Returns:
        True if updated.
    """
    return await update_job(
        request_id,
        {
            "status": "failed",
            "error": error,
            "completed_at": datetime.now(timezone.utc),
        },
    )


async def list_user_jobs(
    user_id: str,
    limit: int = 20,
    status: str | None = None,
) -> list[dict]:
    """List generation jobs for a user.

    Args:
        user_id: User identifier.
        limit: Maximum results.
        status: Optional status filter.

    Returns:
        List of job dicts.
    """
    client = _get_client()

    query = (
        client.collection("generations")
        .where("user_id", "==", user_id)
        .order_by("created_at", direction=firestore.Query.DESCENDING)
        .limit(limit)
    )

    if status:
        query = query.where("status", "==", status)

    docs = query.stream()
    jobs = []
    async for doc in docs:
        jobs.append(doc.to_dict())

    logger.info("listed_user_jobs", user_id=user_id, count=len(jobs))
    return jobs


# ─── Document Records ───────────────────────────────────────────


async def save_document_record(
    doc_id: str,
    user_id: str,
    gcs_uri: str,
    filename: str,
    scope: str = "user",
    **extra_metadata: Any,
) -> dict:
    """Save a document metadata record.

    Args:
        doc_id: Unique document identifier.
        user_id: Owner user ID.
        gcs_uri: GCS location.
        filename: Original filename.
        scope: "user" or "system".
        **extra_metadata: Additional metadata (subject, grade, etc.).

    Returns:
        Created document record.
    """
    client = _get_client()

    record = {
        "doc_id": doc_id,
        "user_id": user_id,
        "gcs_uri": gcs_uri,
        "filename": filename,
        "scope": scope,
        "created_at": datetime.now(timezone.utc),
        **extra_metadata,
    }

    doc_ref = client.collection("documents").document(doc_id)
    await doc_ref.set(record)

    logger.info("document_record_saved", doc_id=doc_id, scope=scope)
    return record


async def get_document_record(doc_id: str) -> dict | None:
    """Get a document record by ID."""
    client = _get_client()
    doc_ref = client.collection("documents").document(doc_id)
    doc = await doc_ref.get()

    if not doc.exists:
        return None
    return doc.to_dict()


async def delete_document_record(doc_id: str) -> bool:
    """Delete a document record."""
    client = _get_client()
    doc_ref = client.collection("documents").document(doc_id)
    await doc_ref.delete()

    logger.info("document_record_deleted", doc_id=doc_id)
    return True


async def list_document_records(
    scope: str | None = None,
    user_id: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """List document records with optional scope/user filters.

    Args:
        scope: Optional scope filter ("user" or "system").
        user_id: Optional user ID filter.
        limit: Maximum records to return.

    Returns:
        List of document records sorted by newest first.
    """
    client = _get_client()
    query = client.collection("documents")

    if scope:
        query = query.where("scope", "==", scope)
    if user_id:
        query = query.where("user_id", "==", user_id)

    query = query.limit(limit)

    docs = query.stream()
    records = []
    async for doc in docs:
        records.append(doc.to_dict())

    records.sort(
        key=lambda item: item.get("created_at")
        or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )

    logger.info(
        "listed_document_records",
        scope=scope,
        user_id=user_id,
        count=len(records),
    )
    return records
