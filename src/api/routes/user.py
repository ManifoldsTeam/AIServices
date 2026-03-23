"""User-facing endpoints for document and generation management."""

import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from src.api.schemas.responses import DocumentListResponse, DocumentResponse
from src.services.document_store import upload_document, trigger_import
from src.services.firestore import (
    list_document_records,
    save_document_record,
)

router = APIRouter(prefix="/api/v1/users", tags=["user-documents"])


@router.get("/{user_id}/documents", response_model=DocumentListResponse)
async def list_user_documents(user_id: str) -> DocumentListResponse:
    """List documents uploaded by a specific user."""
    try:
        documents = await list_document_records(scope="user", user_id=user_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list documents: {exc}",
        ) from exc
    responses = [
        DocumentResponse(
            document_id=doc["doc_id"],
            user_id=doc["user_id"],
            filename=doc["filename"],
            file_format=(
                doc["filename"].rsplit(".", 1)[-1].lower()
                if "." in doc["filename"]
                else "unknown"
            ),
            gcs_uri=doc["gcs_uri"],
            index_status=doc.get("index_status", "indexing"),
            scope="user",
        )
        for doc in documents
    ]
    return DocumentListResponse(documents=responses, total=len(responses))


@router.post(
    "/{user_id}/documents/upload",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_user_document(
    user_id: str,
    file: UploadFile = File(...),
    subject: str | None = Form(default=None),
) -> DocumentResponse:
    """Upload a user-scoped document and trigger Vertex AI Search import."""
    content = await file.read()
    session_id = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())

    try:
        upload_result = upload_document(
            file_content=content,
            filename=file.filename or "document",
            user_id=user_id,
            session_id=session_id,
            scope="user",
            subject=subject,
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
        user_id=user_id,
        gcs_uri=upload_result["gcs_uri"],
        filename=file.filename or "document",
        scope="user",
        subject=subject,
        session_id=session_id,
        upload_date=upload_result["upload_date"],
        size_bytes=upload_result["size_bytes"],
    )

    gcs_prefix = upload_result["gcs_uri"].rsplit("/", 1)[0] + "/**"
    trigger_import(gcs_uri=gcs_prefix, reconciliation_mode="INCREMENTAL")

    return DocumentResponse(
        document_id=doc_id,
        user_id=user_id,
        filename=file.filename or "document",
        file_format=(
            file.filename.rsplit(".", 1)[-1].lower()
            if file.filename and "." in file.filename
            else "unknown"
        ),
        gcs_uri=upload_result["gcs_uri"],
        index_status="indexing",
        scope="user",
    )
