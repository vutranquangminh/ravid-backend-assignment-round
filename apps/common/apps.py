"""AppConfig for the common app."""

from django.apps import AppConfig


class CommonConfig(AppConfig):
    """Shared cross-cutting infrastructure: logging, middleware, env helpers."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.common"
