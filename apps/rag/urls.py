"""URL patterns for the RAG app.

Registered in ``config/urls.py`` under ``api/``, so the full paths become:
  GET  /api/documents/status/  — StatusView (slice 04)

The chat query route (slice 05) will be added here when that slice lands.
"""

from django.urls import path

from .views import StatusView

app_name = "rag"

urlpatterns = [
    path("documents/status/", StatusView.as_view(), name="ingestion-status"),
]
