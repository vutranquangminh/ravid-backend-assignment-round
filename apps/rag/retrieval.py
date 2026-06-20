"""Retrieval helper for the RAG chat pipeline (slice 05).

``retrieve(owner_id, query, k)`` is the single public entry point:
  1. Embed the query text using the same embeddings factory as ingestion.
  2. Query the caller's Chroma collection for the ``k`` nearest chunks.
  3. Return a list of ``{"text": ..., "document_id": ...}`` dicts.

Per-user isolation is guaranteed by delegating to ``vectorstore.query``, which
operates exclusively on ``user_<owner_id>`` (D-013, M-005).  This function
never touches any other user's collection.

When the collection is empty (no ingested documents), ``vectorstore.query``
returns an empty result and this function returns an empty list — triggering
the no-context guard in the view (D-015).
"""

from __future__ import annotations

import logging

from django.conf import settings

from . import vectorstore
from .embeddings import get_embeddings

logger = logging.getLogger(__name__)


def retrieve(owner_id: int, query: str, k: int | None = None) -> list[dict]:
    """Return the top-k most relevant chunks from the owner's knowledge base.

    Args:
        owner_id: PK of the user whose collection to search.
        query:    Raw query text (will be embedded on the fly).
        k:        Number of chunks to return; defaults to
                  ``settings.RETRIEVAL_TOP_K`` (D-012).

    Returns:
        A list of dicts ``{"text": str, "document_id": str}`` sorted by
        relevance (nearest first).  Empty list when no collection exists or
        when no chunks are stored for this user.
    """
    top_k = k if k is not None else settings.RETRIEVAL_TOP_K

    # Embed the query using the same model as ingestion (D-010).
    query_vector: list[float] = get_embeddings().embed_query(query)

    # Query the owner's Chroma collection only (D-013).
    try:
        result = vectorstore.query(owner_id, query_vector, top_k)
    except Exception:
        # Collection may not exist yet (user has never ingested a document).
        logger.debug(
            "retrieve: no collection for owner",
            extra={"owner_id": owner_id},
        )
        return []

    # Chromadb returns lists-of-lists; index 0 is the first (only) query row.
    documents: list[str] = (result.get("documents") or [[]])[0]
    metadatas: list[dict] = (result.get("metadatas") or [[]])[0]

    if not documents:
        return []

    chunks: list[dict] = []
    for text, meta in zip(documents, metadatas, strict=False):
        if text is None:
            continue
        chunks.append(
            {
                "text": text,
                "document_id": str((meta or {}).get("document_id", "")),
            }
        )

    return chunks
