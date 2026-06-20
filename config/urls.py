"""Root URL configuration for the RAVID project."""

from django.urls import include, path

urlpatterns = [
    # --- Slice 01: liveness check ---
    path("api/health/", include("apps.common.urls")),
    # --- Slice 02: authentication (register / login / JWT) ---
    path("api/", include("apps.accounts.urls")),
    # --- Slice 04 + 05: ingestion status + chat query ---
    path("api/", include("apps.rag.urls")),
    # --- Slice 03: document upload / list / delete ---
    path("api/", include("apps.documents.urls")),
]
