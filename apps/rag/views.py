"""Views for the RAG app (slice 04: ingestion status; slice 05: chat query).

Protected routes (JWT required):
  GET  /api/documents/status/?task_id=<id>  — poll ingestion job status

All error responses use the ``{"error": "..."}`` envelope (D-022).
Cross-user or unknown task_id → 404, never 403 (D-020).
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import IngestionJob

# ---------------------------------------------------------------------------
# Public status strings (D-019)
# ---------------------------------------------------------------------------

_SUCCESS_MESSAGE = "Document successfully parsed, embedded, and indexed in vector storage."

_INTERNAL_TO_PUBLIC = {
    IngestionJob.Status.PENDING: "PROCESSING",
    IngestionJob.Status.STARTED: "PROCESSING",
    IngestionJob.Status.SUCCESS: "SUCCESS",
    IngestionJob.Status.FAILURE: "FAILURE",
}


class StatusView(APIView):
    """GET /api/documents/status/?task_id=<id> — poll ingestion job status.

    Maps internal ``IngestionJob.status`` to the public contract:
      PENDING / STARTED  → ``{"task_id", "status": "PROCESSING"}``
      SUCCESS            → ``{"task_id", "status": "SUCCESS", "message": "..."}``
      FAILURE            → ``{"task_id", "status": "FAILURE", "error": "<msg>"}``

    Missing ``task_id`` param → 400.
    Unknown id or another user's job → 404 (D-020).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        task_id = request.query_params.get("task_id", "").strip()
        if not task_id:
            return Response(
                {"error": "task_id query parameter is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            job = IngestionJob.objects.get(
                celery_task_id=task_id,
                owner=request.user,
            )
        except IngestionJob.DoesNotExist:
            return Response(
                {"error": "Task not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        public_status = _INTERNAL_TO_PUBLIC.get(job.status, "PROCESSING")

        if public_status == "SUCCESS":
            return Response(
                {
                    "task_id": task_id,
                    "status": "SUCCESS",
                    "message": _SUCCESS_MESSAGE,
                },
                status=status.HTTP_200_OK,
            )

        if public_status == "FAILURE":
            return Response(
                {
                    "task_id": task_id,
                    "status": "FAILURE",
                    "error": job.error_message,
                },
                status=status.HTTP_200_OK,
            )

        # PROCESSING (PENDING or STARTED)
        return Response(
            {
                "task_id": task_id,
                "status": "PROCESSING",
            },
            status=status.HTTP_200_OK,
        )
