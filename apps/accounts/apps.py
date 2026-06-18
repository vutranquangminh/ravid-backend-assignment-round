"""AppConfig for the accounts app."""

from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """Authentication and user management (slice 02)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
