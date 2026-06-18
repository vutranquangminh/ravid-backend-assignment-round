"""AppConfig for the rag app."""

from django.apps import AppConfig


class RagConfig(AppConfig):
    """RAG ingestion pipeline and chat query (slices 04–05)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.rag"
