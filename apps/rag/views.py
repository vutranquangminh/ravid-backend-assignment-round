"""Views for the RAG app (slice 04: ingestion status; slice 05: chat query).

Protected routes (JWT required):
  GET  /api/documents/status/?task_id=<id>  — poll ingestion job status
  POST /api/chat/query/                     — RAG chat with credit accounting

All error responses use the ``{"error": "..."}`` envelope (D-022).
Cross-user or unknown task_id → 404, never 403 (D-020).
"""

from __future__ import annotations

import logging

from django.db.models import F, Value
from django.db.models.functions import Greatest
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import IngestionJob

logger = logging.getLogger(__name__)

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

# Fixed answer when retrieval finds no relevant chunks (D-015).
_NO_CONTEXT_ANSWER = "I couldn't find anything relevant in your documents to answer that."


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


class ChatQueryView(APIView):
    """POST /api/chat/query/ — grounded RAG chat with credit accounting.

    Flow:
      1. Validate request body → empty/missing query → 400.
      2. Retrieve top-k chunks from the caller's Chroma collection.
      3. No-context guard: if no chunks → 200 fixed answer, 0 tokens, no charge.
      4. Credit check: balance ≤ 0 → 402 (no LLM call).
      5. Call LLM → build answer + tokens.
      6. Decrement balance atomically (floored at 0).
      7. Return 200 {answer, tokens_consumed}.

    On embedding / LLM failure → 502 {error} (logged, no secrets).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        from apps.accounts.models import get_or_create_account  # noqa: PLC0415

        from .llm import get_llm_client  # noqa: PLC0415
        from .retrieval import retrieve  # noqa: PLC0415
        from .serializers import ChatQuerySerializer  # noqa: PLC0415

        # ------------------------------------------------------------------
        # 1. Validate input
        # ------------------------------------------------------------------
        serializer = ChatQuerySerializer(data=request.data)
        if not serializer.is_valid():
            errors = serializer.errors
            # Surface the first validation message directly (D-022).
            message = _first_error(errors)
            return Response({"error": message}, status=status.HTTP_400_BAD_REQUEST)

        query: str = serializer.validated_data["query"]

        # ------------------------------------------------------------------
        # 2. Retrieve relevant chunks (scoped to this user only — D-013)
        # ------------------------------------------------------------------
        try:
            chunks = retrieve(request.user.id, query)
        except Exception as exc:
            logger.error(
                "chat_query: retrieval failed",
                extra={"owner_id": request.user.id, "error": str(exc)},
            )
            return Response(
                {"error": "Failed to retrieve context. Please try again."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # ------------------------------------------------------------------
        # 3. No-context guard (D-015): no chunks → fixed answer, no charge
        # ------------------------------------------------------------------
        if not chunks:
            return Response(
                {"answer": _NO_CONTEXT_ANSWER, "tokens_consumed": 0},
                status=status.HTTP_200_OK,
            )

        # ------------------------------------------------------------------
        # 4. Credit check — before calling the LLM (D-016)
        # ------------------------------------------------------------------
        account = get_or_create_account(request.user)
        if account.balance <= 0:
            return Response(
                {"error": "Insufficient credits."},
                status=status.HTTP_402_PAYMENT_REQUIRED,
            )

        # ------------------------------------------------------------------
        # 5. Build bounded context + call LLM (D-014)
        # ------------------------------------------------------------------
        context = "\n\n".join(chunk["text"] for chunk in chunks)
        system = (
            "You are a helpful assistant. "
            "Answer ONLY using the information in the provided context. "
            "If the answer is not in the context, say you don't know."
        )

        try:
            result = get_llm_client().complete(system, context, query)
        except Exception as exc:
            # Log the error type / message only — never the context (M-008).
            logger.error(
                "chat_query: llm call failed",
                extra={
                    "owner_id": request.user.id,
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:200],
                },
            )
            return Response(
                {"error": "LLM request failed. Please try again later."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # ------------------------------------------------------------------
        # 6. Decrement balance atomically, floored at 0 (D-016)
        # ------------------------------------------------------------------
        from apps.accounts.models import CreditAccount  # noqa: PLC0415

        CreditAccount.objects.filter(pk=account.pk).update(
            balance=Greatest(Value(0), F("balance") - result.tokens)
        )

        # ------------------------------------------------------------------
        # 7. Return the answer
        # ------------------------------------------------------------------
        return Response(
            {"answer": result.answer, "tokens_consumed": result.tokens},
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _first_error(errors: dict) -> str:
    """Extract the first human-readable error string from a DRF error dict."""
    for value in errors.values():
        if isinstance(value, str):
            return value
        if isinstance(value, list) and value:
            return str(value[0])
        if isinstance(value, dict):
            return _first_error(value)
    return "Invalid input."
