"""Views for the RAG app.

Slice 04: ingestion status
Slice 05: chat query with credit accounting
Slice 08: chat continuation (chat_id) + SSE streaming

Protected routes (JWT required):
  GET  /api/documents/status/?task_id=<id>  — poll ingestion job status
  POST /api/chat/query/                     — RAG chat with credit accounting + chat_id
  POST /api/chat/stream/                    — SSE streaming chat with chat_id

All error responses use the ``{"error": "..."}`` envelope (D-022).
Cross-user or unknown task_id/chat_id → 404, never 403 (D-020).
"""

from __future__ import annotations

import json
import logging

from django.db import transaction
from django.db.models import F, Value
from django.db.models.functions import Greatest
from django.http import Http404, StreamingHttpResponse
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import IngestionJob, Message

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
    """POST /api/chat/query/ — grounded RAG chat with credit accounting + chat continuation.

    Flow:
      1. Validate request body → empty/missing query → 400.
      2. Resolve conversation via chat_id (optional; creates new if absent).
         Cross-user/missing chat_id → 404.
      3. Build history from recent messages (bounded by CHAT_HISTORY_TURNS).
      4. Retrieve top-k chunks from the caller's Chroma collection.
      5. No-context guard: if no chunks → 200 fixed answer, 0 tokens, no charge,
         but persist the user + assistant messages to the conversation.
      6. Credit check: balance ≤ 0 → 402 (no LLM call).
      7. Call LLM with history → build answer + tokens.
      8. Decrement balance atomically (floored at 0) + persist messages.
      9. Return 200 {answer, tokens_consumed, chat_id}.

    On embedding / LLM failure → 502 {error} (logged, no secrets).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        from apps.accounts.models import CreditAccount, get_or_create_account  # noqa: PLC0415

        from .conversations import get_or_create_conversation, recent_history  # noqa: PLC0415
        from .llm import get_llm_client  # noqa: PLC0415
        from .retrieval import retrieve  # noqa: PLC0415
        from .serializers import ChatQuerySerializer  # noqa: PLC0415

        # ------------------------------------------------------------------
        # 1. Validate input
        # ------------------------------------------------------------------
        serializer = ChatQuerySerializer(data=request.data)
        if not serializer.is_valid():
            errors = serializer.errors
            message = _first_error(errors)
            return Response({"error": message}, status=status.HTTP_400_BAD_REQUEST)

        query: str = serializer.validated_data["query"]
        chat_id = serializer.validated_data.get("chat_id")

        # ------------------------------------------------------------------
        # 2. Resolve conversation (errors must be JSON before any streaming)
        # ------------------------------------------------------------------
        try:
            conversation = get_or_create_conversation(request.user, chat_id)
        except Http404:
            return Response(
                {"error": "Conversation not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # ------------------------------------------------------------------
        # 3. Build history from recent messages
        # ------------------------------------------------------------------
        history = recent_history(conversation)

        # ------------------------------------------------------------------
        # 4. Retrieve relevant chunks (scoped to this user only — D-013)
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
        # 5. No-context guard (D-015): no chunks → fixed answer, no charge.
        #    Still persist the turn so history is complete.
        # ------------------------------------------------------------------
        if not chunks:
            with transaction.atomic():
                Message.objects.create(
                    conversation=conversation,
                    role=Message.Role.USER,
                    content=query,
                    tokens=0,
                )
                Message.objects.create(
                    conversation=conversation,
                    role=Message.Role.ASSISTANT,
                    content=_NO_CONTEXT_ANSWER,
                    tokens=0,
                )
                conversation.save()  # bump updated_at
            return Response(
                {
                    "answer": _NO_CONTEXT_ANSWER,
                    "tokens_consumed": 0,
                    "chat_id": conversation.id,
                },
                status=status.HTTP_200_OK,
            )

        # ------------------------------------------------------------------
        # 6. Credit check — before calling the LLM (D-016)
        # ------------------------------------------------------------------
        account = get_or_create_account(request.user)
        if account.balance <= 0:
            return Response(
                {"error": "Insufficient credits."},
                status=status.HTTP_402_PAYMENT_REQUIRED,
            )

        # ------------------------------------------------------------------
        # 7. Build bounded context + call LLM (D-014)
        # ------------------------------------------------------------------
        context = "\n\n".join(chunk["text"] for chunk in chunks)
        system = (
            "You are a helpful assistant. "
            "Answer ONLY using the information in the provided context. "
            "If the answer is not in the context, say you don't know."
        )

        try:
            result = get_llm_client().complete(system, context, query, history)
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
        # 8. Decrement balance atomically, floored at 0 (D-016) + persist
        # ------------------------------------------------------------------
        with transaction.atomic():
            CreditAccount.objects.filter(pk=account.pk).update(
                balance=Greatest(Value(0), F("balance") - result.tokens)
            )
            Message.objects.create(
                conversation=conversation,
                role=Message.Role.USER,
                content=query,
                tokens=0,
            )
            Message.objects.create(
                conversation=conversation,
                role=Message.Role.ASSISTANT,
                content=result.answer,
                tokens=result.tokens,
            )
            conversation.save()  # bump updated_at

        # ------------------------------------------------------------------
        # 9. Return the answer (chat_id is additive — slice 05 fields preserved)
        # ------------------------------------------------------------------
        return Response(
            {
                "answer": result.answer,
                "tokens_consumed": result.tokens,
                "chat_id": conversation.id,
            },
            status=status.HTTP_200_OK,
        )


class ChatStreamView(APIView):
    """POST /api/chat/stream/ — SSE streaming RAG chat with chat continuation.

    All pre-stream checks (auth, validation, conversation resolution, credit check)
    return normal JSON responses so errors are never embedded in the event stream.

    SSE event sequence:
      data: {"delta": "<text chunk>"}   (one per LLM chunk)
      ...
      data: {"event": "done", "chat_id": <id>, "tokens_consumed": <n>}
      data: [DONE]

    Messages are persisted and credits deducted AFTER the stream completes.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request: Request):  # noqa: ANN201
        from apps.accounts.models import get_or_create_account  # noqa: PLC0415

        from .conversations import get_or_create_conversation, recent_history  # noqa: PLC0415
        from .llm import get_llm_client  # noqa: PLC0415
        from .retrieval import retrieve  # noqa: PLC0415
        from .serializers import ChatQuerySerializer  # noqa: PLC0415

        # ------------------------------------------------------------------
        # 1. Validate input
        # ------------------------------------------------------------------
        serializer = ChatQuerySerializer(data=request.data)
        if not serializer.is_valid():
            message = _first_error(serializer.errors)
            return Response({"error": message}, status=status.HTTP_400_BAD_REQUEST)

        query: str = serializer.validated_data["query"]
        chat_id = serializer.validated_data.get("chat_id")

        # ------------------------------------------------------------------
        # 2. Resolve conversation (before streaming — errors must be JSON)
        # ------------------------------------------------------------------
        try:
            conversation = get_or_create_conversation(request.user, chat_id)
        except Http404:
            return Response(
                {"error": "Conversation not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # ------------------------------------------------------------------
        # 3. Build history
        # ------------------------------------------------------------------
        history = recent_history(conversation)

        # ------------------------------------------------------------------
        # 4. Retrieve chunks (before streaming — errors must be JSON)
        # ------------------------------------------------------------------
        try:
            chunks = retrieve(request.user.id, query)
        except Exception as exc:
            logger.error(
                "chat_stream: retrieval failed",
                extra={"owner_id": request.user.id, "error": str(exc)},
            )
            return Response(
                {"error": "Failed to retrieve context. Please try again."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        conv_id = conversation.id

        # ------------------------------------------------------------------
        # 5. No-context guard: persist turn then stream fixed answer
        # ------------------------------------------------------------------
        if not chunks:

            def _guard_stream():  # noqa: ANN202
                with transaction.atomic():
                    Message.objects.create(
                        conversation=conversation,
                        role=Message.Role.USER,
                        content=query,
                        tokens=0,
                    )
                    Message.objects.create(
                        conversation=conversation,
                        role=Message.Role.ASSISTANT,
                        content=_NO_CONTEXT_ANSWER,
                        tokens=0,
                    )
                    conversation.save()
                words = _NO_CONTEXT_ANSWER.split(" ")
                last = len(words) - 1
                for i, word in enumerate(words):
                    chunk_text = word if i == last else word + " "
                    yield f"data: {json.dumps({'delta': chunk_text})}\n\n".encode()
                yield (
                    f"data: {json.dumps({'event': 'done', 'chat_id': conv_id, 'tokens_consumed': 0})}\n\n"
                ).encode()
                yield b"data: [DONE]\n\n"

            resp = StreamingHttpResponse(_guard_stream(), content_type="text/event-stream")
            resp["Cache-Control"] = "no-cache"
            resp["X-Accel-Buffering"] = "no"
            return resp

        # ------------------------------------------------------------------
        # 6. Credit check (before streaming — 402 must be JSON, not an event)
        # ------------------------------------------------------------------
        account = get_or_create_account(request.user)
        if account.balance <= 0:
            return Response(
                {"error": "Insufficient credits."},
                status=status.HTTP_402_PAYMENT_REQUIRED,
            )

        # ------------------------------------------------------------------
        # 7. Build context + start streaming
        # ------------------------------------------------------------------
        context = "\n\n".join(chunk["text"] for chunk in chunks)
        system = (
            "You are a helpful assistant. "
            "Answer ONLY using the information in the provided context. "
            "If the answer is not in the context, say you don't know."
        )

        llm = get_llm_client()
        stream_result = llm.complete_stream(system, context, query, history)
        account_pk = account.pk

        def _sse_generator():  # noqa: ANN202
            answer_parts: list[str] = []
            for text_chunk in stream_result:
                answer_parts.append(text_chunk)
                yield f"data: {json.dumps({'delta': text_chunk})}\n\n".encode()

            tokens = stream_result.tokens
            full_answer = "".join(answer_parts)

            # Persist messages + deduct credits atomically AFTER streaming ends.
            with transaction.atomic():
                from apps.accounts.models import CreditAccount as _CA  # noqa: PLC0415

                _CA.objects.filter(pk=account_pk).update(
                    balance=Greatest(Value(0), F("balance") - tokens)
                )
                Message.objects.create(
                    conversation=conversation,
                    role=Message.Role.USER,
                    content=query,
                    tokens=0,
                )
                Message.objects.create(
                    conversation=conversation,
                    role=Message.Role.ASSISTANT,
                    content=full_answer,
                    tokens=tokens,
                )
                conversation.save()

            yield (
                f"data: {json.dumps({'event': 'done', 'chat_id': conv_id, 'tokens_consumed': tokens})}\n\n"
            ).encode()
            yield b"data: [DONE]\n\n"

        streaming_resp = StreamingHttpResponse(_sse_generator(), content_type="text/event-stream")
        streaming_resp["Cache-Control"] = "no-cache"
        streaming_resp["X-Accel-Buffering"] = "no"
        return streaming_resp


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
