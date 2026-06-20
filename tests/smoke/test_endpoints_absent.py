"""Regression: clearly-bogus paths that should never resolve.

All core API endpoints (slices 01–05) are now implemented.  This file remains
meaningful by asserting that a clearly-bogus path still returns 404, so we
keep a live regression guard without cluttering it with paths that have been
implemented.

Paths removed from the absent list when their slice landed:
  /api/register/           — slice 02 ✓
  /api/login/              — slice 02 ✓
  /api/documents/upload/   — slice 03 ✓
  /api/documents/status/   — slice 04 ✓
  /api/chat/query/         — slice 05 ✓
"""

import pytest
from django.test import Client

# Clearly-bogus paths that must never resolve to a real view.
ABSENT_PATHS = [
    "/api/nope/",
]


@pytest.mark.django_db
@pytest.mark.parametrize("path", ABSENT_PATHS)
def test_bogus_path_returns_404(path: str) -> None:
    """Each clearly-bogus path must return 404 regardless of method."""
    client = Client()
    response_get = client.get(path)
    response_post = client.post(path, data={}, content_type="application/json")
    assert response_get.status_code == 404, (
        f"GET {path} returned {response_get.status_code}, expected 404"
    )
    assert response_post.status_code == 404, (
        f"POST {path} returned {response_post.status_code}, expected 404"
    )
