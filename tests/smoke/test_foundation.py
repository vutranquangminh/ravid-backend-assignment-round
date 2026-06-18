"""Smoke tests — Django boots and the health endpoint works.

These tests are intentionally thin: they prove the project skeleton is
importable and the single public endpoint is wired correctly.

No DB interaction is exercised here (health is a pure liveness check).
"""

import json

import django
import pytest
from django.test import Client


def test_django_setup_is_clean() -> None:
    """Django's system check (manage.py check) equivalent at import time.

    django.setup() has already been called by pytest-django when the test
    session starts; if it raised an exception the session would abort before
    reaching this test. This assertion is a belt-and-suspenders guard.
    """
    # If we reach here, Django loaded without error.
    assert django.VERSION >= (5, 0), f"Expected Django 5.x, got {django.VERSION}"


@pytest.mark.django_db
def test_health_returns_200_with_ok_body() -> None:
    """GET /api/health/ returns 200 with {"status": "ok"}."""
    client = Client()
    response = client.get("/api/health/")
    assert response.status_code == 200
    data = json.loads(response.content)
    assert data == {"status": "ok"}


@pytest.mark.django_db
def test_health_requires_no_auth_header() -> None:
    """GET /api/health/ works with no Authorization header (AllowAny)."""
    client = Client()
    # Explicitly send no auth header — Client() has no default auth.
    response = client.get("/api/health/", HTTP_AUTHORIZATION="")
    assert response.status_code == 200
    data = json.loads(response.content)
    assert data["status"] == "ok"
