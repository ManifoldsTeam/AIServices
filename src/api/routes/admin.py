"""Admin endpoints for managing system documents."""

import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from src.api.schemas.responses import DocumentListResponse, DocumentResponse
from src.config import SYSTEM_USER_ID
from src.services.document_store import delete_document, trigger_import, upload_document
from src.services.firestore import (
    delete_document_record,
    get_document_record,
    list_document_records,
    save_document_record,
)

router = APIRouter(prefix="/api/v1/admin/documents", tags=["admin-documents"])


@router.post(
    "/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED
)
async def upload_system_document(
    file: UploadFile = File(...),
    subject: str = Form(...),
    grade: str | None = Form(default=None),
) -> DocumentResponse:
    """Upload a system-scoped document and trigger Vertex AI Search import."""
    content = await file.read()
    session_id = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())

    try:
        upload_result = upload_document(
            file_content=content,
            filename=file.filename or "document",
            user_id=SYSTEM_USER_ID,
            session_id=session_id,
            scope="system",
            subject=subject,
            grade=grade,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Upload failed: {exc}",
        ) from exc

    await save_document_record(
        doc_id=doc_id,
        user_id=upload_result["metadata_user_id"],
        gcs_uri=upload_result["gcs_uri"],
        filename=file.filename or "document",
        scope="system",
        subject=subject,
        grade=grade,
        session_id=session_id,
        upload_date=upload_result["upload_date"],
        size_bytes=upload_result["size_bytes"],
    )

    gcs_prefix = upload_result["gcs_uri"].rsplit("/", 1)[0] + "/**"
    trigger_import(gcs_uri=gcs_prefix, reconciliation_mode="INCREMENTAL")

    return DocumentResponse(
        document_id=doc_id,
        user_id=SYSTEM_USER_ID,
        filename=file.filename or "document",
        file_format=(
            file.filename.rsplit(".", 1)[-1].lower()
            if file.filename and "." in file.filename
            else "unknown"
        ),
        gcs_uri=upload_result["gcs_uri"],
        index_status="indexing",
        scope="system",
    )


@router.get("", response_model=DocumentListResponse)
async def list_system_document_records() -> DocumentListResponse:
    """List all system documents from Firestore tracking records."""
    documents = await list_document_records(scope="system", user_id=SYSTEM_USER_ID)
    responses = [
        DocumentResponse(
            document_id=doc["doc_id"],
            user_id=SYSTEM_USER_ID,
            filename=doc["filename"],
            file_format=(
                doc["filename"].rsplit(".", 1)[-1].lower()
                if "." in doc["filename"]
                else "unknown"
            ),
            gcs_uri=doc["gcs_uri"],
            index_status=doc.get("index_status", "indexing"),
            scope="system",
        )
        for doc in documents
    ]
    return DocumentListResponse(documents=responses, total=len(responses))


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_system_document(doc_id: str) -> None:
    """Delete a system document from GCS and Firestore tracking."""
    record = await get_document_record(doc_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )

    if record.get("scope") != "system" or record.get("user_id") != SYSTEM_USER_ID:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only system documents can be deleted via admin endpoint",
        )

    gcs_uri = record.get("gcs_uri", "")
    if not gcs_uri.startswith("gs://"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invalid gcs_uri"
        )

    # gs://bucket/path/to/file -> path/to/file
    parts = gcs_uri.split("/", 3)
    gcs_path = parts[3] if len(parts) >= 4 else ""

    deleted = delete_document(gcs_path)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete document from storage",
        )

    await delete_document_record(doc_id)
