"""DRF serializers for the RAG app (slice 05 + 08).

``ChatQuerySerializer`` validates the ``POST /api/chat/query/`` and
``POST /api/chat/stream/`` request bodies.
An empty or whitespace-only ``query`` is rejected with a 400-compatible
validation error so the view can surface ``{"error": "query is required."}``.
The optional ``chat_id`` field enables chat continuation (slice 08).
"""

from __future__ import annotations

from rest_framework import serializers


class ChatQuerySerializer(serializers.Serializer):
    """Validate the chat query request body.

    Fields:
        query:   Non-empty, non-whitespace string containing the user's question.
        chat_id: Optional integer PK of an existing Conversation to continue.
                 Omit or pass null to start a new conversation.
    """

    query = serializers.CharField(
        trim_whitespace=True,
        error_messages={
            "blank": "query is required.",
            "required": "query is required.",
        },
    )
    chat_id = serializers.IntegerField(required=False, allow_null=True)

    def validate_query(self, value: str) -> str:
        """Reject purely whitespace queries after trimming."""
        if not value.strip():
            raise serializers.ValidationError("query is required.")
        return value
