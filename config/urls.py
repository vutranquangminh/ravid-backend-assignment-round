"""Root URL configuration for the RAVID project."""

from django.urls import include, path

urlpatterns = [
    # --- Slice 01: liveness check ---
    path("api/health/", include("apps.common.urls")),
    # --- Slice 02: authentication (register / login / JWT) ---
    path("api/", include("apps.accounts.urls")),
    # --- Slice 04: ingestion status (MUST precede documents/<pk>/ to avoid shadowing) ---
    path("api/", include("apps.rag.urls")),
    # --- Slice 03: document upload / list / delete ---
    path("api/", include("apps.documents.urls")),
    # --- Reserved for later slices (uncomment as each slice lands) ---
    # path("api/chat/query/", ...),      # slice 05: chat query
]
