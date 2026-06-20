"""URL patterns for the RAG app.

Registered in ``config/urls.py`` under ``api/``, so the full paths become:
  GET  /api/documents/status/  — StatusView (slice 04)
  POST /api/chat/query/        — ChatQueryView (slice 05)
"""

from django.urls import path

from .views import ChatQueryView, StatusView

app_name = "rag"

urlpatterns = [
    path("documents/status/", StatusView.as_view(), name="ingestion-status"),
    path("chat/query/", ChatQueryView.as_view(), name="chat-query"),
]
