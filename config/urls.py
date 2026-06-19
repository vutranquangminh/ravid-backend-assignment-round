"""Root URL configuration for the RAVID project."""

from django.urls import include, path

urlpatterns = [
    # --- Slice 01: liveness check ---
    path("api/health/", include("apps.common.urls")),
    # --- Slice 02: authentication (register / login / JWT) ---
    path("api/", include("apps.accounts.urls")),
    # --- Reserved for later slices (uncomment as each slice lands) ---
    # path("api/documents/", include("apps.documents.urls")),  # slice 03/04: upload / status
    # path("api/chat/", include("apps.rag.urls")),      # slice 05: query
]
