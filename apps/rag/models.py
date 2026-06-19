"""IngestionJob model — tracks async ingestion of a Document into Chroma (slice 04).

The DB row is the source of truth for task status (D-019).  The Celery task
writes `celery_task_id` back onto the row after dispatch, and the status
endpoint queries by that id — scoped to the authenticated owner (D-020).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class IngestionJob(models.Model):
    """One ingestion pipeline run per document upload."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        STARTED = "STARTED", "Started"
        SUCCESS = "SUCCESS", "Success"
        FAILURE = "FAILURE", "Failure"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ingestion_jobs",
        db_index=True,
    )
    source_document = models.ForeignKey(
        "documents.Document",
        on_delete=models.CASCADE,
        related_name="jobs",
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )
    # Set after .delay() returns — null/blank until then.
    celery_task_id = models.CharField(
        max_length=255,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
    )
    chunk_count = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return (
            f"IngestionJob({self.pk}, owner={self.owner_id}, "
            f"doc={self.source_document_id}, status={self.status})"
        )
