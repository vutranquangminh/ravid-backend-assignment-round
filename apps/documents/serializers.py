"""DRF serializers for the documents app.

``DocumentUploadSerializer`` — validates an uploaded file by extension,
MIME content-type, and size before any storage or queueing happens (M-006).

``DocumentSerializer`` — read-only output shape for document list responses.
"""

from __future__ import annotations

import os

from django.conf import settings
from rest_framework import serializers

from .models import Document

# Allowed file extensions (lowercase, with leading dot).
_ALLOWED_EXTENSIONS: frozenset[str] = frozenset({".pdf", ".txt", ".md"})

# Allowed MIME types reported by the client.
# ``application/octet-stream`` is tolerated only when the extension is valid
# (browser/curl fall-back when the type is unknown).
_ALLOWED_CONTENT_TYPES: frozenset[str] = frozenset(
    {
        "application/pdf",
        "text/plain",
        "text/markdown",
        "text/x-markdown",
        "application/octet-stream",
    }
)

# Exact error string required by the brief / spec (D-018, D-022).
_BAD_FORMAT_MESSAGE = "Invalid file format. Only PDF, TXT, and Markdown files are allowed."


class DocumentUploadSerializer(serializers.Serializer):
    """Validate a multipart file upload."""

    file = serializers.FileField()

    def validate_file(self, uploaded_file: object) -> object:
        """Reject files with wrong type, unsupported extension, or excessive size."""
        # --- Extension check ---
        _, ext = os.path.splitext(uploaded_file.name or "")
        ext = ext.lower()
        if ext not in _ALLOWED_EXTENSIONS:
            raise serializers.ValidationError(_BAD_FORMAT_MESSAGE)

        # --- Content-type check ---
        content_type: str = getattr(uploaded_file, "content_type", "") or ""
        # Normalise: strip parameters like "; charset=utf-8"
        mime = content_type.split(";")[0].strip().lower()
        if mime not in _ALLOWED_CONTENT_TYPES:
            raise serializers.ValidationError(_BAD_FORMAT_MESSAGE)

        # --- Size check ---
        max_bytes: int = getattr(settings, "MAX_UPLOAD_MB", 10) * 1024 * 1024
        if uploaded_file.size > max_bytes:
            max_mb = getattr(settings, "MAX_UPLOAD_MB", 10)
            raise serializers.ValidationError(
                f"File too large. Maximum allowed size is {max_mb} MB."
            )

        return uploaded_file


class DocumentSerializer(serializers.ModelSerializer):
    """Read-only serializer for document list output."""

    class Meta:
        model = Document
        fields = ["id", "original_name", "content_type", "size_bytes", "status", "uploaded_at"]
        read_only_fields = fields
