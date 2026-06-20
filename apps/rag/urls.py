"""URL patterns for the RAG app.

Registered in ``config/urls.py`` under ``api/``, so the full paths become:
  GET  /api/documents/status/  — StatusView (slice 04)
  POST /api/chat/query/        — ChatQueryView (slice 05 + 08)
  POST /api/chat/stream/       — ChatStreamView (slice 08, SSE)
"""

from django.urls import path

from .views import ChatQueryView, ChatStreamView, StatusView

app_name = "rag"

urlpatterns = [
    path("documents/status/", StatusView.as_view(), name="ingestion-status"),
    path("chat/query/", ChatQueryView.as_view(), name="chat-query"),
    path("chat/stream/", ChatStreamView.as_view(), name="chat-stream"),
]
