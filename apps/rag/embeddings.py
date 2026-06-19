"""Embeddings factory for the RAG pipeline (slice 04).

``get_embeddings()`` returns either:
  - A real ``HuggingFaceEmbeddings`` object (default, requires the rag extra).
  - A deterministic ``_StubEmbeddings`` instance when ``settings.RAVID_EMBEDDINGS_STUB``
    is True — used in tests so no model is downloaded and no network is hit (D-027).

The stub produces fixed-dimension (32) float vectors derived from a hash of
the input text, so the same text always returns the same vector (idempotent,
offline).  Dimension must not change between stub and real in tests — only the
content differs.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from django.conf import settings

if TYPE_CHECKING:
    pass

_STUB_DIM = 32  # fixed dimensionality for stub embeddings


class _StubEmbeddings:
    """Deterministic fake embeddings — no network, no model download.

    ``embed_documents(texts)`` and ``embed_query(text)`` both return L2-normalised
    vectors derived from a hash of the text, producing ``_STUB_DIM`` finite floats.
    Identical input always produces identical output.

    Implementation: we interpret the SHA-256 digest as 32 signed integers (one per
    byte) and convert them to floats.  Byte values 0–255 never produce NaN or Inf,
    so L2-normalisation is always safe.
    """

    def _hash_to_vector(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8", errors="replace")).digest()
        # Each byte 0–255 → float; repeat to reach _STUB_DIM if needed.
        floats: list[float] = [float(b) for b in digest]
        while len(floats) < _STUB_DIM:
            floats.extend(floats[: _STUB_DIM - len(floats)])
        floats = floats[:_STUB_DIM]
        # L2-normalise so cosine similarity behaves as expected.
        norm = sum(x * x for x in floats) ** 0.5 or 1.0
        return [x / norm for x in floats]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return a list of fixed-dim stub vectors, one per text."""
        return [self._hash_to_vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        """Return a single fixed-dim stub vector for the query text."""
        return self._hash_to_vector(text)


def get_embeddings() -> _StubEmbeddings | object:
    """Return the appropriate embeddings object for the current environment.

    Returns:
        ``_StubEmbeddings`` when ``settings.RAVID_EMBEDDINGS_STUB`` is True.
        ``HuggingFaceEmbeddings`` otherwise (requires langchain-huggingface +
        sentence-transformers from the ``rag`` extra).
    """
    if getattr(settings, "RAVID_EMBEDDINGS_STUB", False):
        return _StubEmbeddings()

    from langchain_huggingface import HuggingFaceEmbeddings  # noqa: PLC0415

    return HuggingFaceEmbeddings(model_name=settings.EMBEDDING_MODEL)
