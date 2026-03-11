"""Vertex AI Search service — document retrieval with scope filtering.

This module provides:
1. Retriever factory with doc_scope filtering (user, system, all)
2. User-first re-ranking for doc_scope="all"
3. High-level retrieval function for the graph

Document scope filtering:
- "user": Only user's personal documents (metadata user_id = {user_id})
- "system": Only admin-managed shared documents (metadata user_id = "__system__")
- "all": Both user + system docs, with user docs ranked first

Vertex AI Search handles:
- Semantic search across indexed documents
- Metadata filtering via filter expressions
- Extractive answers for better context (requires Enterprise edition)

Engine-level serving config:
    VertexAISearchRetriever builds a datastore-level serving config by default
    (projects/*/locations/*/dataStores/*/servingConfigs/*). Enterprise features
    (extractive answers, LLM add-ons) require engine-level path:
    projects/*/locations/*/collections/*/engines/*/servingConfigs/*

    We override _serving_config after construction to use the engine path
    from settings.search_engine_path.
"""

import structlog
from google.api_core.exceptions import FailedPrecondition
from langchain_google_community import VertexAISearchRetriever
from langchain_core.documents import Document

from src.config import get_settings

logger = structlog.get_logger(__name__)

# System user ID constant — used for admin-managed documents
SYSTEM_USER_ID = "__system__"


def _build_filter(user_id: str, doc_scope: str) -> str:
    """Build Vertex AI Search filter expression based on doc_scope."""
    if doc_scope == "user":
        return f'user_id: ANY("{user_id}")'
    elif doc_scope == "system":
        return f'user_id: ANY("{SYSTEM_USER_ID}")'
    else:  # "all" — both user and system docs
        return f'user_id: ANY("{user_id}", "{SYSTEM_USER_ID}")'


def _apply_engine_serving_config(retriever: VertexAISearchRetriever) -> None:
    """Override serving config to use engine-level path for enterprise features."""
    settings = get_settings()
    retriever._serving_config = (
        f"{settings.search_engine_path}/servingConfigs/default_config"
    )


def get_retriever(
    user_id: str,
    doc_scope: str = "all",
    max_documents: int = 10,
    get_extractive_answers: bool = True,
) -> VertexAISearchRetriever:
    """Create a Vertex AI Search retriever scoped by doc_scope.

    Args:
        user_id: The user ID for scoping personal documents
        doc_scope: Document scope filter
            - "user": only user's personal documents
            - "system": only admin-managed shared documents
            - "all": both user + system docs (default)
        max_documents: Maximum documents to retrieve
        get_extractive_answers: Whether to request extractive answers
            (requires Enterprise edition on the search engine)

    Returns:
        Configured VertexAISearchRetriever instance with engine-level serving config
    """
    settings = get_settings()
    filter_str = _build_filter(user_id, doc_scope)

    logger.debug(
        "creating_retriever",
        user_id=user_id,
        doc_scope=doc_scope,
        filter=filter_str,
        search_engine_id=settings.search_engine_id,
        extractive_answers=get_extractive_answers,
    )

    retriever = VertexAISearchRetriever(
        project_id=settings.gcp_project_id,
        data_store_id=settings.data_store_id,
        location_id=settings.data_store_location,  # "global"
        max_documents=max_documents,
        max_extractive_answer_count=3,
        get_extractive_answers=get_extractive_answers,
    )

    _apply_engine_serving_config(retriever)
    return retriever


def retrieve_with_user_first(
    retriever: VertexAISearchRetriever,
    query: str,
    doc_scope: str,
) -> list[Document]:
    """Retrieve documents and apply user-first re-ranking.

    For doc_scope="all", user documents are ranked before system documents.
    This ensures personalized content takes priority while system docs supplement.

    Args:
        retriever: Configured VertexAISearchRetriever
        query: Search query
        doc_scope: Document scope (used to decide if re-ranking needed)

    Returns:
        List of Documents, re-ranked if doc_scope="all"
    """
    logger.debug("retrieving_documents", query=query[:100], doc_scope=doc_scope)

    docs = retriever.invoke(query)

    logger.debug("retrieved_documents", count=len(docs))

    # No re-ranking needed for single-scope queries
    if doc_scope != "all":
        return docs

    # User-first re-ranking: user docs before system docs
    user_docs = []
    system_docs = []

    for doc in docs:
        metadata = doc.metadata or {}
        doc_user_id = metadata.get("user_id", "")

        if doc_user_id == SYSTEM_USER_ID:
            system_docs.append(doc)
        else:
            user_docs.append(doc)

    reranked = user_docs + system_docs

    logger.info(
        "reranked_documents",
        user_docs=len(user_docs),
        system_docs=len(system_docs),
        total=len(reranked),
    )

    return reranked


async def retrieve_context(
    user_id: str,
    query: str,
    doc_scope: str = "all",
    max_documents: int = 10,
) -> tuple[list[str], list[dict]]:
    """High-level function to retrieve context for content generation.

    Combines retriever creation, retrieval, and user-first re-ranking
    into a single async function for use in graph nodes.

    Falls back to non-extractive search if Enterprise features are unavailable.

    Args:
        user_id: User ID for document scoping
        query: Search query (typically the topic + request context)
        doc_scope: Document scope filter
        max_documents: Maximum documents to retrieve

    Returns:
        Tuple of (context_strings, source_metadata)
        - context_strings: List of document content strings
        - source_metadata: List of dicts with source info (doc_id, page, scope)
    """
    logger.info(
        "retrieving_context",
        user_id=user_id,
        query=query[:100],
        doc_scope=doc_scope,
    )

    try:
        retriever = get_retriever(
            user_id=user_id,
            doc_scope=doc_scope,
            max_documents=max_documents,
            get_extractive_answers=True,
        )

        try:
            docs = retrieve_with_user_first(retriever, query, doc_scope)
        except FailedPrecondition:
            # Enterprise features not yet available — fall back to basic search
            logger.warning(
                "enterprise_features_unavailable_falling_back",
                msg="Extractive answers require Enterprise edition. Using basic search.",
            )
            retriever = get_retriever(
                user_id=user_id,
                doc_scope=doc_scope,
                max_documents=max_documents,
                get_extractive_answers=False,
            )
            docs = retrieve_with_user_first(retriever, query, doc_scope)

        # Extract content and metadata
        context_strings = []
        source_metadata = []

        for doc in docs:
            context_strings.append(doc.page_content)

            metadata = doc.metadata or {}
            source_metadata.append(
                {
                    "source": metadata.get("source", "unknown"),
                    "page": metadata.get("page", 0),
                    "doc_scope": (
                        "system"
                        if metadata.get("user_id") == SYSTEM_USER_ID
                        else "user"
                    ),
                    "user_id": metadata.get("user_id", ""),
                }
            )

        logger.info(
            "context_retrieved",
            chunks=len(context_strings),
            sources=len(source_metadata),
        )

        return context_strings, source_metadata

    except Exception as e:
        logger.error("context_retrieval_failed", error=str(e))
        # Return empty context on error — graph can still generate with general knowledge
        return [], []
