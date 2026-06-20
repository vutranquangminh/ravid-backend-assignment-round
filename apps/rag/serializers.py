"""DRF serializers for the RAG app (slice 05).

``ChatQuerySerializer`` validates the ``POST /api/chat/query/`` request body.
An empty or whitespace-only ``query`` is rejected with a 400-compatible
validation error so the view can surface ``{"error": "query is required."}``.
"""

from __future__ import annotations

from rest_framework import serializers


class ChatQuerySerializer(serializers.Serializer):
    """Validate the chat query request body.

    Fields:
        query: Non-empty, non-whitespace string containing the user's question.
    """

    query = serializers.CharField(
        trim_whitespace=True,
        error_messages={
            "blank": "query is required.",
            "required": "query is required.",
        },
    )

    def validate_query(self, value: str) -> str:
        """Reject purely whitespace queries after trimming."""
        if not value.strip():
            raise serializers.ValidationError("query is required.")
        return value
