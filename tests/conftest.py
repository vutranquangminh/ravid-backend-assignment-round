"""Shared pytest fixtures for the RAVID test suite.

Chroma is external state that — unlike the Django DB (rolled back per test by
pytest-django) — persists across tests within a process. Collections are keyed
by ``user_<owner_id>`` and the test DB resets user ids to 1, 2, 3… each test,
so without a reset, vectors from earlier tests bleed into later ones and break
``collection.count()`` assertions. This autouse fixture wipes all Chroma
collections around every test so vector state is isolated.
"""

from __future__ import annotations

import contextlib

import pytest


def _wipe_chroma() -> None:
    from apps.rag import vectorstore

    client = vectorstore._client()
    for col in client.list_collections():
        name = getattr(col, "name", col)
        with contextlib.suppress(Exception):
            client.delete_collection(name)


@pytest.fixture(autouse=True)
def reset_chroma_state():
    """Isolate Chroma vector state for every test (before and after)."""
    _wipe_chroma()
    yield
    _wipe_chroma()
