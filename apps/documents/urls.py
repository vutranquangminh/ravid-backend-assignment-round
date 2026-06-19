"""URL patterns for the documents app.

Registered under ``api/`` in ``config/urls.py``, so the full paths become:
  POST   /api/documents/upload/   — UploadView
  GET    /api/documents/          — DocumentListView
  DELETE /api/documents/<pk>/     — DocumentDeleteView

``upload/`` is listed before the pk pattern so it is never mis-matched as an
integer pk (even though "upload" is not an integer, explicit ordering is safer).
"""

from django.urls import path

from .views import DocumentDeleteView, DocumentListView, UploadView

app_name = "documents"

urlpatterns = [
    path("documents/upload/", UploadView.as_view(), name="document-upload"),
    path("documents/", DocumentListView.as_view(), name="document-list"),
    path("documents/<int:pk>/", DocumentDeleteView.as_view(), name="document-delete"),
]
