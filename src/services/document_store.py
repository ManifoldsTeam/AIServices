"""Document Store service — GCS upload + Vertex AI Search import.

Handles document lifecycle:
1. Upload files to GCS with scope-aware path structure
2. Trigger Vertex AI Search import for indexing
3. Track document records

GCS Path Structure:
- System docs: gs://bucket/system/{date}/{session_id}/{filename}
- User docs:   gs://bucket/user/{user_id}/{date}/{session_id}/{filename}

Metadata attached to GCS objects:
- user_id: Owner ID (or "__system__" for admin docs)
- upload_date: ISO date
- session_id: Upload session identifier
- scope: "user" | "system"
- subject: Optional subject classification
- grade: Optional grade level
"""

import mimetypes
from datetime import datetime, timezone

import structlog
from google.cloud import storage
from google.cloud import discoveryengine_v1 as discoveryengine

from src.config import get_settings
from src.config.constants import (
    ALLOWED_MIME_TYPES,
    EXTENSION_MIME_MAP,
    MAX_FILE_SIZE_BYTES,
    SYSTEM_USER_ID,
)

logger = structlog.get_logger(__name__)


def _get_storage_client() -> storage.Client:
    """Get GCS client (cached at module level in production)."""
    return storage.Client(project=get_settings().gcp_project_id)


def validate_file(filename: str, file_size: int) -> tuple[bool, str]:
    """Validate file type and size before upload.

    Args:
        filename: Original filename with extension.
        file_size: File size in bytes.

    Returns:
        Tuple of (is_valid, error_message).
    """
    # Check file extension
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in EXTENSION_MIME_MAP:
        return False, f"Unsupported file type '{ext}'. Allowed: PDF, DOCX, PPTX"

    # Check file size
    if file_size > MAX_FILE_SIZE_BYTES:
        size_mb = file_size / (1024 * 1024)
        return False, f"File too large ({size_mb:.1f}MB). Maximum: 50MB"

    return True, ""


def build_gcs_path(
    user_id: str,
    filename: str,
    session_id: str,
    scope: str = "user",
) -> str:
    """Build GCS object path based on scope.

    Args:
        user_id: User ID (used for user-scope paths).
        filename: Original filename.
        session_id: Upload session identifier.
        scope: "user" or "system".

    Returns:
        GCS object path (without gs://bucket/ prefix).
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if scope == "system":
        return f"system/{today}/{session_id}/{filename}"
    else:
        return f"user/{user_id}/{today}/{session_id}/{filename}"


def upload_document(
    file_content: bytes,
    filename: str,
    user_id: str,
    session_id: str,
    scope: str = "user",
    subject: str | None = None,
    grade: str | None = None,
) -> dict:
    """Upload a document to GCS with metadata.

    Args:
        file_content: Raw file bytes.
        filename: Original filename.
        user_id: Uploader's user ID.
        session_id: Upload session identifier.
        scope: "user" or "system".
        subject: Optional subject (e.g., "toan", "vat-li").
        grade: Optional grade (e.g., "lop-10").

    Returns:
        Dict with upload result:
        {
            "gcs_uri": "gs://bucket/path/file.pdf",
            "gcs_path": "system/2026-03-09/session123/file.pdf",
            "metadata_user_id": "__system__" or user_id,
            "upload_date": "2026-03-09",
            "size_bytes": 12345,
        }

    Raises:
        ValueError: If file validation fails.
        Exception: On GCS upload failure.
    """
    settings = get_settings()

    # Validate
    is_valid, error = validate_file(filename, len(file_content))
    if not is_valid:
        raise ValueError(error)

    # Build path
    gcs_path = build_gcs_path(user_id, filename, session_id, scope)
    metadata_user_id = SYSTEM_USER_ID if scope == "system" else user_id
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Determine content type
    ext = "." + filename.rsplit(".", 1)[-1].lower()
    content_type = EXTENSION_MIME_MAP.get(ext, "application/octet-stream")

    logger.info(
        "uploading_document",
        filename=filename,
        gcs_path=gcs_path,
        scope=scope,
        user_id=metadata_user_id,
        size_bytes=len(file_content),
    )

    # Upload to GCS
    client = _get_storage_client()
    bucket = client.bucket(settings.gcs_bucket)
    blob = bucket.blob(gcs_path)

    # Set metadata for AI Search filtering
    blob.metadata = {
        "user_id": metadata_user_id,
        "upload_date": today,
        "session_id": session_id,
        "scope": scope,
    }
    if subject:
        blob.metadata["subject"] = subject
    if grade:
        blob.metadata["grade"] = grade

    blob.upload_from_string(file_content, content_type=content_type)

    gcs_uri = f"gs://{settings.gcs_bucket}/{gcs_path}"

    logger.info(
        "document_uploaded",
        gcs_uri=gcs_uri,
        size_bytes=len(file_content),
    )

    return {
        "gcs_uri": gcs_uri,
        "gcs_path": gcs_path,
        "metadata_user_id": metadata_user_id,
        "upload_date": today,
        "size_bytes": len(file_content),
    }


def trigger_import(
    gcs_uri: str,
    reconciliation_mode: str = "INCREMENTAL",
) -> str | None:
    """Trigger Vertex AI Search document import from GCS.

    Args:
        gcs_uri: GCS URI pattern (e.g., "gs://bucket/system/2026-03-09/**").
        reconciliation_mode: "INCREMENTAL" or "FULL".

    Returns:
        Operation name for tracking, or None on failure.
    """
    settings = get_settings()

    parent = (
        f"projects/{settings.gcp_project_id}/"
        f"locations/{settings.data_store_location}/"
        f"collections/default_collection/"
        f"dataStores/{settings.data_store_id}/"
        f"branches/default_branch"
    )

    logger.info(
        "triggering_import",
        gcs_uri=gcs_uri,
        parent=parent,
        mode=reconciliation_mode,
    )

    try:
        client = discoveryengine.DocumentServiceClient()

        gcs_source = discoveryengine.GcsSource(
            input_uris=[gcs_uri],
            data_schema="content",
        )

        # Map string to enum
        mode_enum = (
            discoveryengine.ImportDocumentsRequest.ReconciliationMode.INCREMENTAL
            if reconciliation_mode == "INCREMENTAL"
            else discoveryengine.ImportDocumentsRequest.ReconciliationMode.FULL
        )

        request = discoveryengine.ImportDocumentsRequest(
            parent=parent,
            gcs_source=gcs_source,
            reconciliation_mode=mode_enum,
        )

        operation = client.import_documents(request=request)

        logger.info(
            "import_triggered",
            operation_name=operation.operation.name,
        )

        return operation.operation.name

    except Exception as e:
        logger.error("import_trigger_failed", error=str(e))
        return None


def list_user_documents(
    user_id: str,
    prefix: str | None = None,
) -> list[dict]:
    """List documents uploaded by a user.

    Args:
        user_id: User ID to filter documents.
        prefix: Optional GCS prefix to narrow search.

    Returns:
        List of document info dicts.
    """
    settings = get_settings()
    client = _get_storage_client()
    bucket = client.bucket(settings.gcs_bucket)

    search_prefix = prefix or f"user/{user_id}/"

    logger.debug("listing_user_documents", user_id=user_id, prefix=search_prefix)

    documents = []
    for blob in bucket.list_blobs(prefix=search_prefix):
        if blob.name.endswith("/"):
            continue  # Skip folder markers

        metadata = blob.metadata or {}
        documents.append(
            {
                "gcs_uri": f"gs://{settings.gcs_bucket}/{blob.name}",
                "gcs_path": blob.name,
                "filename": blob.name.split("/")[-1],
                "size_bytes": blob.size,
                "content_type": blob.content_type,
                "upload_date": metadata.get("upload_date", ""),
                "session_id": metadata.get("session_id", ""),
                "scope": metadata.get("scope", "user"),
                "subject": metadata.get("subject", ""),
                "grade": metadata.get("grade", ""),
                "created": blob.time_created.isoformat() if blob.time_created else "",
            }
        )

    logger.info("listed_documents", user_id=user_id, count=len(documents))
    return documents


def list_system_documents(prefix: str | None = None) -> list[dict]:
    """List system (admin-managed) documents.

    Args:
        prefix: Optional GCS prefix to narrow search.

    Returns:
        List of document info dicts.
    """
    settings = get_settings()
    client = _get_storage_client()
    bucket = client.bucket(settings.gcs_bucket)

    search_prefix = prefix or "system/"

    logger.debug("listing_system_documents", prefix=search_prefix)

    documents = []
    for blob in bucket.list_blobs(prefix=search_prefix):
        if blob.name.endswith("/"):
            continue

        metadata = blob.metadata or {}
        documents.append(
            {
                "gcs_uri": f"gs://{settings.gcs_bucket}/{blob.name}",
                "gcs_path": blob.name,
                "filename": blob.name.split("/")[-1],
                "size_bytes": blob.size,
                "content_type": blob.content_type,
                "upload_date": metadata.get("upload_date", ""),
                "subject": metadata.get("subject", ""),
                "grade": metadata.get("grade", ""),
                "created": blob.time_created.isoformat() if blob.time_created else "",
            }
        )

    logger.info("listed_system_documents", count=len(documents))
    return documents


def delete_document(gcs_path: str) -> bool:
    """Delete a document from GCS.

    Args:
        gcs_path: GCS object path (without gs://bucket/).

    Returns:
        True if deleted, False on failure.
    """
    settings = get_settings()

    logger.info("deleting_document", gcs_path=gcs_path)

    try:
        client = _get_storage_client()
        bucket = client.bucket(settings.gcs_bucket)
        blob = bucket.blob(gcs_path)
        blob.delete()

        logger.info("document_deleted", gcs_path=gcs_path)
        return True
    except Exception as e:
        logger.error("document_delete_failed", gcs_path=gcs_path, error=str(e))
        return False
