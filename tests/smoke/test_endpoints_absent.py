"""Regression: future endpoints are NOT yet routed.

Paths still absent (introduced in later slices):
  /api/chat/query/         -> slice 05 (rag)

Paths removed from this list when their slice landed:
  /api/register/           — slice 02 ✓
  /api/login/              — slice 02 ✓
  /api/documents/upload/   — slice 03 ✓
  /api/documents/status/   — slice 04 ✓

Until those slices land, a request to any of these paths MUST return 404.
Remove the corresponding path from this list once the slice wires up its
routes and adds proper tests in its own test module.
"""

import pytest
from django.test import Client

ABSENT_PATHS = [
    "/api/chat/query/",
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
