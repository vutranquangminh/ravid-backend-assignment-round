"""AppConfig for the documents app."""

from django.apps import AppConfig


class DocumentsConfig(AppConfig):
    """Document upload and metadata management (slice 03)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.documents"
