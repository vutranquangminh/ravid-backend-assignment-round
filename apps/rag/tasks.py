"""Celery tasks for the RAG pipeline.

``ingest_document`` — PLACEHOLDER for slice 03.

This slice only enqueues the task and returns its id; the real pipeline
(parse → chunk → embed → upsert to Chroma) is implemented in slice 04.
The placeholder is enough to:
  - exercise the eager-mode path in tests (CELERY_TASK_ALWAYS_EAGER=True).
  - confirm the Document status advances to "PROCESSING".
  - return a task_id to the caller (the Celery AsyncResult id).

DO NOT import chromadb / langchain / torch here — those are slice 04.
"""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def ingest_document(self, document_id: int) -> dict:
    """Placeholder ingestion task — marks the document as PROCESSING.

    Slice 04 replaces this body with the full parse/chunk/embed/upsert
    pipeline and introduces an ``IngestionJob`` row.

    Args:
        document_id: Primary key of the ``Document`` to ingest.

    Returns:
        A dict with ``document_id`` and ``status`` so eager-mode callers
        (tests) can inspect the outcome.
    """
    # Deferred import to avoid circular deps and keep the rag app importable
    # without ML libraries installed.
    from apps.documents.models import Document  # noqa: PLC0415

    try:
        doc = Document.objects.get(pk=document_id)
    except Document.DoesNotExist:
        logger.warning(
            "ingest_document called for missing document",
            extra={"operation": "ingest", "document_id": document_id},
        )
        return {"document_id": document_id, "status": "NOT_FOUND"}

    logger.info(
        "Starting document ingestion (placeholder)",
        extra={"operation": "ingest", "document_id": document_id},
    )

    doc.status = "PROCESSING"
    doc.save(update_fields=["status"])

    return {"document_id": document_id, "status": "PROCESSING"}
