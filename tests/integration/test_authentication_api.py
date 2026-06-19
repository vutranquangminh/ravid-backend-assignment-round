"""Integration tests for the authentication API (slice 02).

Covers:
  POST /api/register/  — success, duplicate, invalid input
  POST /api/login/     — success, wrong password, unknown email
  GET  /api/auth/me/   — without token (401), with valid token (200)
"""

from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

User = get_user_model()

REGISTER_URL = "/api/register/"
LOGIN_URL = "/api/login/"
ME_URL = "/api/auth/me/"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _post_json(client: Client, url: str, data: dict) -> object:
    return client.post(url, data=json.dumps(data), content_type="application/json")


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRegister:
    def test_success_returns_201_with_user_id(self) -> None:
        client = Client()
        response = _post_json(
            client, REGISTER_URL, {"email": "alice@example.com", "password": "strongpass1"}
        )
        assert response.status_code == 201
        body = response.json()
        assert body["message"] == "Registration successful"
        assert "user_id" in body
        assert isinstance(body["user_id"], int)

    def test_duplicate_email_returns_400_exact_message(self) -> None:
        client = Client()
        _post_json(client, REGISTER_URL, {"email": "bob@example.com", "password": "strongpass1"})
        response = _post_json(
            client, REGISTER_URL, {"email": "bob@example.com", "password": "anotherpass1"}
        )
        assert response.status_code == 400
        body = response.json()
        assert body == {"error": "User with this email already exists."}

    def test_invalid_email_returns_400_error_envelope(self) -> None:
        client = Client()
        response = _post_json(
            client, REGISTER_URL, {"email": "not-an-email", "password": "strongpass1"}
        )
        assert response.status_code == 400
        body = response.json()
        assert "error" in body
        assert isinstance(body["error"], str)
        assert len(body) == 1  # single-key envelope

    def test_short_password_returns_400_error_envelope(self) -> None:
        client = Client()
        response = _post_json(
            client, REGISTER_URL, {"email": "carol@example.com", "password": "short"}
        )
        assert response.status_code == 400
        body = response.json()
        assert "error" in body
        assert isinstance(body["error"], str)
        assert len(body) == 1

    def test_email_stored_case_insensitively(self) -> None:
        client = Client()
        response = _post_json(
            client, REGISTER_URL, {"email": "Dave@Example.COM", "password": "strongpass1"}
        )
        assert response.status_code == 201
        assert User.objects.filter(username="dave@example.com").exists()


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestLogin:
    def setup_method(self) -> None:
        # Create a user for login tests.
        self.email = "eve@example.com"
        self.password = "correcthorse1"
        User.objects.create_user(username=self.email, email=self.email, password=self.password)

    def test_success_returns_200_with_token(self) -> None:
        client = Client()
        response = _post_json(client, LOGIN_URL, {"email": self.email, "password": self.password})
        assert response.status_code == 200
        body = response.json()
        assert body["message"] == "Login successful"
        assert "token" in body
        assert len(body["token"]) > 0

    def test_wrong_password_returns_401_exact_message(self) -> None:
        client = Client()
        response = _post_json(client, LOGIN_URL, {"email": self.email, "password": "wrongpassword"})
        assert response.status_code == 401
        body = response.json()
        assert body == {"error": "Invalid email or password"}

    def test_unknown_email_returns_401_exact_message(self) -> None:
        client = Client()
        response = _post_json(
            client, LOGIN_URL, {"email": "nobody@example.com", "password": "somepass1"}
        )
        assert response.status_code == 401
        body = response.json()
        assert body == {"error": "Invalid email or password"}


# ---------------------------------------------------------------------------
# /api/auth/me/
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestMeView:
    def _get_token(self, email: str, password: str) -> str:
        client = Client()
        User.objects.create_user(username=email, email=email, password=password)
        response = _post_json(client, LOGIN_URL, {"email": email, "password": password})
        assert response.status_code == 200
        return response.json()["token"]

    def test_without_token_returns_401_error_envelope(self) -> None:
        client = Client()
        response = client.get(ME_URL)
        assert response.status_code == 401
        body = response.json()
        assert "error" in body
        assert isinstance(body["error"], str)
        assert len(body) == 1

    def test_with_valid_token_returns_200_with_user_id(self) -> None:
        email = "frank@example.com"
        password = "validpass123"
        token = self._get_token(email, password)

        client = Client()
        response = client.get(ME_URL, HTTP_AUTHORIZATION=f"Bearer {token}")
        assert response.status_code == 200
        body = response.json()
        assert "user_id" in body
        assert body["email"] == email
        assert isinstance(body["user_id"], int)
