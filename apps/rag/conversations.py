"""Conversation resolution and history helpers for the RAG chat pipeline (slice 08).

Public API:
  - ``get_or_create_conversation(user, chat_id)`` — resolve or create a Conversation
    for the given user; cross-user/missing chat_id → Http404.
  - ``recent_history(conversation, n)`` — return the last n messages in chronological
    order as a list of ``{"role", "content"}`` dicts for use in the LLM prompt.
"""

from __future__ import annotations

from django.conf import settings
from django.shortcuts import get_object_or_404

from .models import Conversation, Message


def get_or_create_conversation(user: object, chat_id: int | None) -> Conversation:
    """Return a Conversation for *user*.

    If *chat_id* is None/falsy: create and return a new Conversation owned by *user*.
    If *chat_id* is given: fetch ``Conversation(pk=chat_id, owner=user)``.
    Cross-user or missing → raises ``Http404`` (via ``get_object_or_404``).

    Args:
        user:    A Django auth user instance (the request owner).
        chat_id: Optional PK of an existing Conversation to continue.

    Returns:
        The resolved or newly created ``Conversation``.

    Raises:
        Http404: When ``chat_id`` is given but belongs to another user or does not exist.
    """
    if not chat_id:
        return Conversation.objects.create(owner=user)
    return get_object_or_404(Conversation, pk=chat_id, owner=user)


def recent_history(conversation: Conversation, n: int | None = None) -> list[dict]:
    """Return the last *n* messages of *conversation* in chronological order.

    Args:
        conversation: The ``Conversation`` to read from.
        n:            Maximum number of messages to include; defaults to
                      ``settings.CHAT_HISTORY_TURNS``.

    Returns:
        List of ``{"role": str, "content": str}`` dicts, oldest first (chronological).
        Empty list if the conversation has no messages yet.
    """
    if n is None:
        n = getattr(settings, "CHAT_HISTORY_TURNS", 6)

    # Fetch the last n messages by newest-first, then reverse for chronological order.
    msgs = list(Message.objects.filter(conversation=conversation).order_by("-created_at")[:n])
    msgs.reverse()
    return [{"role": m.role, "content": m.content} for m in msgs]
