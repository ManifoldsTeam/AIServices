# Services package — GCP service wrappers
from .vertex_search import (
    get_retriever,
    retrieve_with_user_first,
    retrieve_context,
    SYSTEM_USER_ID,
)
from .llm import (
    get_generation_llm,
    get_review_llm,
    get_structured_llm,
)
from .document_store import (
    upload_document,
    trigger_import,
    list_user_documents,
    list_system_documents,
    delete_document,
    validate_file,
)
from .firestore import (
    create_job,
    get_job,
    update_job,
    complete_job,
    fail_job,
)
from .task_queue import enqueue_generation

__all__ = [
    # Vertex AI Search
    "get_retriever",
    "retrieve_with_user_first",
    "retrieve_context",
    "SYSTEM_USER_ID",
    # LLM
    "get_generation_llm",
    "get_review_llm",
    "get_structured_llm",
    # Document Store
    "upload_document",
    "trigger_import",
    "list_user_documents",
    "list_system_documents",
    "delete_document",
    "validate_file",
    # Firestore
    "create_job",
    "get_job",
    "update_job",
    "complete_job",
    "fail_job",
    # Task Queue
    "enqueue_generation",
]
