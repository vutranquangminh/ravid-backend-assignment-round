"""Chromadb vector store helpers for the RAG pipeline (slice 04).

Uses the chromadb client **directly** (not langchain_chroma) with a
PersistentClient so the same store is available across Celery workers and the
Django process.

Per-user isolation is enforced at the collection level: every read/write is
scoped to ``user_<owner_id>`` (D-013, M-005).

Chroma telemetry is disabled via Settings(anonymized_telemetry=False) to keep
everything offline (D-027).
"""

from __future__ import annotations

import contextlib
import threading

import chromadb
from django.conf import settings

# ---------------------------------------------------------------------------
# Thread-safe singleton client
# ---------------------------------------------------------------------------

_client_lock = threading.Lock()
_chroma_client: chromadb.PersistentClient | None = None


def _client() -> chromadb.PersistentClient:
    """Return (or lazily create) the shared PersistentClient singleton."""
    global _chroma_client
    if _chroma_client is None:
        with _client_lock:
            if _chroma_client is None:
                _chroma_client = chromadb.PersistentClient(
                    path=settings.CHROMA_PERSIST_DIR,
                    settings=chromadb.Settings(anonymized_telemetry=False),
                )
    return _chroma_client


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def get_collection(owner_id: int) -> chromadb.Collection:
    """Return (or create) the collection for *owner_id*.

    Collection name: ``user_<owner_id>`` (D-013).
    """
    return _client().get_or_create_collection(f"user_{owner_id}")


def upsert_chunks(
    owner_id: int,
    document_id: int,
    texts: list[str],
    embeddings: list[list[float]],
) -> None:
    """Upsert *texts* and their *embeddings* into the owner's collection.

    IDs are ``"<document_id>:<chunk_index>"`` — deterministic and idempotent,
    so re-ingesting the same document overwrites the old vectors cleanly.

    Metadatas carry ``document_id`` (as str) and ``chunk_index`` (int) so
    slice 05 can filter or scope retrieval by document.

    Args:
        owner_id:    Owning user's PK — selects the collection.
        document_id: Source document PK — stored in every chunk's metadata.
        texts:       Raw chunk strings (parallel to *embeddings*).
        embeddings:  Pre-computed embedding vectors (parallel to *texts*).
    """
    if not texts:
        return
    collection = get_collection(owner_id)
    ids = [f"{document_id}:{i}" for i in range(len(texts))]
    metadatas = [{"document_id": str(document_id), "chunk_index": i} for i in range(len(texts))]
    collection.upsert(
        ids=ids,
        embeddings=embeddings,
        documents=texts,
        metadatas=metadatas,
    )


def delete_document_vectors(owner_id: int, document_id: int) -> None:
    """Remove all vectors for *document_id* from the owner's collection.

    Safe to call even if no vectors exist for that document.  Used when the
    Document row is deleted (slice 04 delete integration).

    Args:
        owner_id:    Owning user's PK — selects the collection.
        document_id: Document whose chunks should be removed.
    """
    try:
        collection = get_collection(owner_id)
    except Exception:
        # Collection may not exist yet (e.g., ingestion never ran).
        return
    # Swallowing is safe here: the goal is absence of the vectors, not an
    # acknowledgement of deletion (chromadb may raise on a zero-match filter).
    with contextlib.suppress(Exception):
        collection.delete(where={"document_id": str(document_id)})


def query(
    owner_id: int,
    query_embedding: list[float],
    k: int,
) -> dict:
    """Query the owner's collection for the *k* nearest neighbours.

    Args:
        owner_id:        Owning user's PK — selects the collection.
        query_embedding: Pre-computed query vector.
        k:               Number of results to return.

    Returns:
        Raw chromadb ``QueryResult`` dict with keys ``documents``,
        ``metadatas``, ``distances``, ``ids``.  Used by slice 05.
    """
    collection = get_collection(owner_id)
    return collection.query(
        query_embeddings=[query_embedding],
        n_results=min(k, collection.count()) if collection.count() > 0 else 1,
        include=["documents", "metadatas", "distances"],
    )
