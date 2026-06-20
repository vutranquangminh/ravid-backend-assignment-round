"""Views for the documents app.

Protected routes (JWT required):
  POST   /api/documents/upload/   — upload a PDF/TXT/MD file (→ 202)
  GET    /api/documents/          — list the caller's own documents
  DELETE /api/documents/<pk>/     — delete a caller-owned document (→ 204)

All error responses use the ``{"error": "..."}`` envelope (D-022).
Cross-user or missing document → 404, never 403 (D-020).
"""

from __future__ import annotations

from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.rag.models import IngestionJob
from apps.rag.tasks import ingest_document

from .models import Document
from .serializers import DocumentSerializer, DocumentUploadSerializer
from .services import create_document


class UploadView(APIView):
    """POST /api/documents/upload/ — validate and store an uploaded file.

    Returns ``202 {message, document_id, task_id}`` on success.
    Returns ``400 {"error": "<msg>"}`` on validation failure.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Upload a document",
        description=(
            "Upload a PDF, TXT, or Markdown file. The file is stored and an ingestion "
            "job is dispatched asynchronously. Returns 202 with the document ID and "
            "Celery task ID to poll status."
        ),
        request={"multipart/form-data": DocumentUploadSerializer},
        responses={
            202: OpenApiResponse(
                response=inline_serializer(
                    name="UploadSuccessResponse",
                    fields={
                        "message": serializers.CharField(),
                        "document_id": serializers.IntegerField(),
                        "task_id": serializers.UUIDField(),
                    },
                ),
                description="Document accepted and ingestion started.",
                examples=[
                    OpenApiExample(
                        name="accepted",
                        value={
                            "message": "Document uploaded and ingestion started",
                            "document_id": 1,
                            "task_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                        },
                        response_only=True,
                    )
                ],
            ),
            400: OpenApiResponse(
                response=inline_serializer(
                    name="UploadErrorResponse",
                    fields={"error": serializers.CharField()},
                ),
                description="Invalid file format or validation failure.",
                examples=[
                    OpenApiExample(
                        name="invalid_format",
                        value={
                            "error": "Invalid file format. Only PDF, TXT, and Markdown files are allowed."
                        },
                        response_only=True,
                    )
                ],
            ),
            401: OpenApiResponse(
                response=inline_serializer(
                    name="UploadUnauthorizedResponse",
                    fields={"detail": serializers.CharField()},
                ),
                description="Authentication credentials were not provided or are invalid.",
            ),
        },
    )
    def post(self, request: Request) -> Response:
        serializer = DocumentUploadSerializer(data=request.data)
        if not serializer.is_valid():
            # Extract the first error message and wrap it in the envelope.
            # We return directly (not via raise) to guarantee the exact body
            # shape, consistent with how accounts/views.py handles errors.
            errors = serializer.errors
            message = _first_error(errors)
            return Response({"error": message}, status=status.HTTP_400_BAD_REQUEST)

        uploaded_file = serializer.validated_data["file"]
        doc = create_document(owner=request.user, uploaded_file=uploaded_file)

        # Create the IngestionJob row first (PENDING, no celery_task_id yet).
        # This avoids the eager-mode chicken-and-egg: if CELERY_TASK_ALWAYS_EAGER
        # is True, .delay() runs the task synchronously and the task needs the
        # job.pk to load the row.  Creating the row first gives the task a valid pk.
        job = IngestionJob.objects.create(
            owner=request.user,
            source_document=doc,
            status=IngestionJob.Status.PENDING,
        )

        # Dispatch the task (may run eagerly / synchronously in tests).
        result = ingest_document.delay(job.pk)

        # Record the Celery task id back onto the job row.
        # In eager mode the task already ran, but the row is still there —
        # the status has been updated by the task; only celery_task_id is missing.
        IngestionJob.objects.filter(pk=job.pk).update(celery_task_id=result.id)

        return Response(
            {
                "message": "Document uploaded and ingestion started",
                "document_id": doc.id,
                "task_id": result.id,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class DocumentListView(APIView):
    """GET /api/documents/ — list all documents owned by the caller."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="List documents",
        description="Return a list of all documents owned by the authenticated user.",
        request=None,
        responses={
            200: OpenApiResponse(
                response=DocumentSerializer(many=True),
                description="List of the caller's documents.",
            ),
            401: OpenApiResponse(
                response=inline_serializer(
                    name="DocumentListUnauthorizedResponse",
                    fields={"detail": serializers.CharField()},
                ),
                description="Authentication credentials were not provided or are invalid.",
            ),
        },
    )
    def get(self, request: Request) -> Response:
        queryset = Document.objects.filter(owner=request.user)
        serializer = DocumentSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class DocumentDeleteView(APIView):
    """DELETE /api/documents/<pk>/ — delete a caller-owned document.

    Returns ``204 No Content`` on success.
    Cross-user or missing pk → 404 (D-020).
    Also removes all vectors for the document from the owner's Chroma
    collection (slice 04 delete integration).
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Delete a document",
        description=(
            "Delete the caller-owned document by ID. Also removes all associated "
            "vectors from the vector store. Cross-user or missing ID returns 404."
        ),
        request=None,
        responses={
            204: OpenApiResponse(description="Document deleted successfully. No content returned."),
            401: OpenApiResponse(
                response=inline_serializer(
                    name="DocumentDeleteUnauthorizedResponse",
                    fields={"detail": serializers.CharField()},
                ),
                description="Authentication credentials were not provided or are invalid.",
            ),
            404: OpenApiResponse(
                response=inline_serializer(
                    name="DocumentDeleteNotFoundResponse",
                    fields={"detail": serializers.CharField()},
                ),
                description="Document not found or belongs to another user.",
            ),
        },
    )
    def delete(self, request: Request, pk: int) -> Response:
        doc = get_object_or_404(Document, pk=pk, owner=request.user)

        # Remove vectors from Chroma before deleting the DB row.
        try:
            from apps.rag import vectorstore  # noqa: PLC0415

            vectorstore.delete_document_vectors(
                owner_id=request.user.pk,
                document_id=pk,
            )
        except Exception:  # noqa: BLE001
            # Vector deletion is best-effort; don't block the HTTP response.
            pass

        doc.file.delete(save=False)
        doc.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


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
