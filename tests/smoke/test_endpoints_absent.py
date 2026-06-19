"""Regression: future endpoints are NOT yet routed (slice 01 foundation).

These paths are introduced in later slices:
  /api/register/           -> slice 02 (accounts)
  /api/login/              -> slice 02 (accounts)
  /api/documents/upload/   -> slice 03 (documents)
  /api/documents/status/   -> slice 03/04 (documents/rag)
  /api/chat/query/         -> slice 05 (rag)

Until those slices land, a request to any of these paths MUST return 404.
This test will start failing once a slice wires up its routes — at that
point, remove the corresponding assertion and add proper tests in the new
slice's test module.
"""

import pytest
from django.test import Client

ABSENT_PATHS = [
    "/api/documents/upload/",
    "/api/documents/status/",
    "/api/chat/query/",
    "/api/register/",
    "/api/login/",
]


@pytest.mark.django_db
@pytest.mark.parametrize("path", ABSENT_PATHS)
def test_future_endpoint_returns_404(path: str) -> None:
    """Each not-yet-implemented path must return 404."""
    client = Client()
    # Try both GET and POST — either way, no route should exist yet.
    response_get = client.get(path)
    response_post = client.post(path, data={}, content_type="application/json")
    # At least one of them should be 404; both should be non-200.
    assert response_get.status_code == 404, (
        f"GET {path} returned {response_get.status_code}, expected 404"
    )
    assert response_post.status_code == 404, (
        f"POST {path} returned {response_post.status_code}, expected 404"
    )
