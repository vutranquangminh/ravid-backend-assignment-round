"""Test settings — offline, key-free, fast.

Requirements:
- No network calls (Celery is eager, no ML libs imported).
- No docker dependencies (sqlite, temp dir for Chroma path config).
- Fast password hashing.
- Heavy ML deps (torch, chromadb, langchain) are NEVER imported here.
"""

import tempfile

from .base import *  # noqa: F401, F403

# ---------------------------------------------------------------------------
# Database: sqlite for speed and portability
# ---------------------------------------------------------------------------

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# ---------------------------------------------------------------------------
# Password hasher: MD5 is fast in tests (never use in production)
# ---------------------------------------------------------------------------

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# ---------------------------------------------------------------------------
# Celery: eager so tasks run synchronously without a broker
# ---------------------------------------------------------------------------

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# ---------------------------------------------------------------------------
# Media: temp directory so uploads don't pollute the repo
# ---------------------------------------------------------------------------

MEDIA_ROOT = tempfile.mkdtemp(prefix="ravid_test_media_")

# ---------------------------------------------------------------------------
# Chroma: temp directory (path only — do NOT import chromadb here)
# ---------------------------------------------------------------------------

CHROMA_PERSIST_DIR = tempfile.mkdtemp(prefix="ravid_test_chroma_")

# ---------------------------------------------------------------------------
# Stub seams for embedding and OpenRouter — filled by rag slice
# ---------------------------------------------------------------------------

RAVID_EMBEDDINGS_STUB = True
EMBEDDING_MODEL = "stub"
OPENROUTER_API_KEY = "stub-key-not-real"
OPENROUTER_MODEL = "stub/model"

# ---------------------------------------------------------------------------
# LLM stub (slice 05) — avoids any real OpenRouter network call in tests
# ---------------------------------------------------------------------------

RAVID_LLM_STUB = True

# ---------------------------------------------------------------------------
# Silence logging noise in tests
# ---------------------------------------------------------------------------

LOGGING["root"]["level"] = "WARNING"  # noqa: F405
