"""Celery tasks for the RAG pipeline (slice 04 — real implementation).

``ingest_document`` receives a job_id (``IngestionJob.pk``), loads the job,
runs the full parse → chunk → embed → upsert pipeline, and writes the
terminal status back to the DB row.  The DB row is the source of truth
(D-019).  Failures are surfaced in BOTH structured logs and the job row
(D-026); raw document text and secrets are never logged (D-027, M-008).

State machine:
  PENDING → STARTED (on task entry, via atomic .update())
           → SUCCESS + chunk_count  (on success)
           → FAILURE + error_message[:500]  (on any exception)
"""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def ingest_document(self, job_id: int) -> dict:
    """Run the ingestion pipeline for the given ``IngestionJob`` PK.

    Args:
        job_id: Primary key of the ``IngestionJob`` to process.

    Returns:
        A dict with ``job_id`` and terminal ``status`` — useful for eager-mode
        callers (tests) to inspect the outcome without a DB query.
    """
    # Deferred imports keep the rag app importable without ML libraries when
    # the worker hasn't loaded the rag extra.
    from apps.rag.models import IngestionJob  # noqa: PLC0415
    from apps.rag.pipeline import run_ingestion  # noqa: PLC0415

    # Load job — silently return if it was deleted between dispatch and pick-up.
    try:
        job = IngestionJob.objects.get(pk=job_id)
    except IngestionJob.DoesNotExist:
        logger.warning(
            "ingest_document: job not found",
            extra={"operation": "ingest", "job_id": job_id},
        )
        return {"job_id": job_id, "status": "NOT_FOUND"}

    # Deferred import for Document model (also needed for status sync).
    from apps.documents.models import Document  # noqa: PLC0415

    # PENDING → STARTED (atomic; avoids overwriting a concurrent worker)
    IngestionJob.objects.filter(pk=job_id).update(status=IngestionJob.Status.STARTED)
    job.status = IngestionJob.Status.STARTED

    document_id = job.source_document_id
    owner_id = job.owner_id

    # Also update the Document.status for observability / backward compatibility.
    Document.objects.filter(pk=document_id).update(status="PROCESSING")

    try:
        chunk_count = run_ingestion(job)
    except Exception as exc:
        error_msg = str(exc)[:500]
        IngestionJob.objects.filter(pk=job_id).update(
            status=IngestionJob.Status.FAILURE,
            error_message=error_msg,
        )
        Document.objects.filter(pk=document_id).update(status="FAILURE")
        # Log structured failure info — NEVER the document text (M-008).
        logger.error(
            "ingest_document: pipeline failed",
            extra={
                "operation": "ingest",
                "status": "failure",
                "document_id": document_id,
                "owner_id": owner_id,
                "job_id": job_id,
                "error": error_msg,
            },
        )
        # Do not re-raise — the job row is the source of truth; the caller
        # (upload view) reads the task_id and polls /api/documents/status/.
        return {"job_id": job_id, "status": "FAILURE", "error": error_msg}

    # SUCCESS
    IngestionJob.objects.filter(pk=job_id).update(
        status=IngestionJob.Status.SUCCESS,
        chunk_count=chunk_count,
    )
    Document.objects.filter(pk=document_id).update(status="SUCCESS")
    logger.info(
        "ingest_document: pipeline succeeded",
        extra={
            "operation": "ingest",
            "status": "success",
            "document_id": document_id,
            "owner_id": owner_id,
            "job_id": job_id,
            "chunk_count": chunk_count,
        },
    )
    return {"job_id": job_id, "status": "SUCCESS", "chunk_count": chunk_count}
