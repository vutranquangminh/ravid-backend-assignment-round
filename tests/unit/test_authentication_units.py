"""Unit tests for authentication components (slice 02).

Covers:
  - RegisterSerializer and LoginSerializer validation
  - services.register_user / authenticate_user
  - apps.common.exceptions.error_envelope_handler reshaping
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from apps.accounts.serializers import LoginSerializer, RegisterSerializer
from apps.accounts.services import authenticate_user, register_user
from apps.common.exceptions import _extract_message, error_envelope_handler
from django.contrib.auth import get_user_model
from rest_framework.exceptions import NotFound, ValidationError

User = get_user_model()


# ---------------------------------------------------------------------------
# RegisterSerializer
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRegisterSerializer:
    def test_valid_data_passes(self) -> None:
        s = RegisterSerializer(data={"email": "alice@example.com", "password": "strongpass1"})
        assert s.is_valid(), s.errors
        assert s.validated_data["email"] == "alice@example.com"

    def test_email_normalised_to_lowercase(self) -> None:
        s = RegisterSerializer(data={"email": "Alice@Example.COM", "password": "strongpass1"})
        assert s.is_valid(), s.errors
        assert s.validated_data["email"] == "alice@example.com"

    def test_invalid_email_fails(self) -> None:
        s = RegisterSerializer(data={"email": "not-an-email", "password": "strongpass1"})
        assert not s.is_valid()
        assert "email" in s.errors

    def test_short_password_fails(self) -> None:
        s = RegisterSerializer(data={"email": "bob@example.com", "password": "short"})
        assert not s.is_valid()
        assert "password" in s.errors

    def test_duplicate_email_fails(self) -> None:
        User.objects.create_user(
            username="carol@example.com", email="carol@example.com", password="pass1234"
        )
        s = RegisterSerializer(data={"email": "carol@example.com", "password": "strongpass1"})
        assert not s.is_valid()
        assert "email" in s.errors
        assert "already exists" in str(s.errors["email"])

    def test_confirm_password_match_passes(self) -> None:
        s = RegisterSerializer(
            data={
                "email": "dave@example.com",
                "password": "strongpass1",
                "confirm_password": "strongpass1",
            }
        )
        assert s.is_valid(), s.errors
        # confirm_password is popped in validate()
        assert "confirm_password" not in s.validated_data

    def test_confirm_password_mismatch_fails(self) -> None:
        s = RegisterSerializer(
            data={
                "email": "eve@example.com",
                "password": "strongpass1",
                "confirm_password": "different1",
            }
        )
        assert not s.is_valid()

    def test_confirm_password_absent_is_valid(self) -> None:
        # confirm_password is optional per D-023
        s = RegisterSerializer(data={"email": "frank@example.com", "password": "strongpass1"})
        assert s.is_valid(), s.errors


# ---------------------------------------------------------------------------
# LoginSerializer
# ---------------------------------------------------------------------------


class TestLoginSerializer:
    def test_valid_data_passes(self) -> None:
        s = LoginSerializer(data={"email": "user@example.com", "password": "anypassword"})
        assert s.is_valid(), s.errors

    def test_invalid_email_fails(self) -> None:
        s = LoginSerializer(data={"email": "bad", "password": "anypassword"})
        assert not s.is_valid()

    def test_missing_password_fails(self) -> None:
        s = LoginSerializer(data={"email": "user@example.com"})
        assert not s.is_valid()


# ---------------------------------------------------------------------------
# services.register_user
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRegisterUser:
    def test_creates_user_with_hashed_password(self) -> None:
        user = register_user("gail@example.com", "strongpass1")
        assert user.pk is not None
        assert user.check_password("strongpass1")

    def test_stores_email_as_username_and_email(self) -> None:
        user = register_user("hal@example.com", "strongpass1")
        assert user.username == "hal@example.com"
        assert user.email == "hal@example.com"

    def test_normalises_email_to_lowercase(self) -> None:
        user = register_user("IVY@Example.COM", "strongpass1")
        assert user.username == "ivy@example.com"

    def test_duplicate_raises_value_error(self) -> None:
        register_user("jack@example.com", "strongpass1")
        with pytest.raises(ValueError, match="already exists"):
            register_user("jack@example.com", "anotherpass1")


# ---------------------------------------------------------------------------
# services.authenticate_user
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAuthenticateUser:
    def setup_method(self) -> None:
        self.email = "kate@example.com"
        self.password = "correctpass1"
        User.objects.create_user(username=self.email, email=self.email, password=self.password)

    def test_valid_credentials_returns_user(self) -> None:
        user = authenticate_user(self.email, self.password)
        assert user is not None
        assert user.email == self.email

    def test_wrong_password_returns_none(self) -> None:
        assert authenticate_user(self.email, "wrongpassword") is None

    def test_unknown_email_returns_none(self) -> None:
        assert authenticate_user("nobody@example.com", "somepass1") is None

    def test_email_lookup_is_case_insensitive(self) -> None:
        user = authenticate_user("Kate@Example.COM", self.password)
        assert user is not None


# ---------------------------------------------------------------------------
# error_envelope_handler
# ---------------------------------------------------------------------------


class TestErrorEnvelopeHandler:
    """Unit-test the exception handler in isolation (no Django request needed)."""

    def _context(self) -> dict:
        return {"request": MagicMock(), "view": MagicMock()}

    def test_drf_not_found_reshapes_to_error_dict(self) -> None:
        exc = NotFound("Resource not found.")
        response = error_envelope_handler(exc, self._context())
        assert response is not None
        assert response.status_code == 404
        assert response.data == {"error": "Resource not found."}

    def test_drf_validation_error_dict_extracts_first_message(self) -> None:
        exc = ValidationError({"email": ["Enter a valid email address."]})
        response = error_envelope_handler(exc, self._context())
        assert response is not None
        assert response.status_code == 400
        assert response.data == {"error": "Enter a valid email address."}

    def test_non_drf_exception_returns_none(self) -> None:
        exc = RuntimeError("something broke")
        response = error_envelope_handler(exc, self._context())
        assert response is None


# ---------------------------------------------------------------------------
# _extract_message (internal helper)
# ---------------------------------------------------------------------------


class TestExtractMessage:
    def test_plain_string(self) -> None:
        assert _extract_message("oops") == "oops"

    def test_list_of_strings(self) -> None:
        assert _extract_message(["first", "second"]) == "first"

    def test_dict_with_list_value(self) -> None:
        assert _extract_message({"field": ["msg1", "msg2"]}) == "msg1"

    def test_dict_with_string_value(self) -> None:
        assert _extract_message({"detail": "Not found."}) == "Not found."
