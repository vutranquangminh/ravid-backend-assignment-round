"""DRF serializers for the accounts app.

Validation rules (per spec + D-023):
- RegisterSerializer: email (valid format + unique), password (min length 8).
  ``confirm_password`` is optional; if sent it must match ``password``.
- LoginSerializer: email and password fields (no cross-field validation here —
  authentication is performed in the view/service layer).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework import serializers

User = get_user_model()

_PASSWORD_MIN_LENGTH = 8


class RegisterSerializer(serializers.Serializer):
    """Validate a registration request body."""

    email = serializers.EmailField()
    password = serializers.CharField(min_length=_PASSWORD_MIN_LENGTH, write_only=True)
    confirm_password = serializers.CharField(write_only=True, required=False)

    def validate_email(self, value: str) -> str:
        """Reject duplicate emails."""
        normalised = value.lower()
        if User.objects.filter(username=normalised).exists():
            raise serializers.ValidationError("User with this email already exists.")
        return normalised

    def validate(self, attrs: dict) -> dict:
        """Cross-field: confirm_password must match password when present."""
        confirm = attrs.pop("confirm_password", None)
        if confirm is not None and confirm != attrs["password"]:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        return attrs


class LoginSerializer(serializers.Serializer):
    """Validate a login request body."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
