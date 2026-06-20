"""Production settings for the RAVID backend.

All values are read from environment variables — no defaults that would be
acceptable in a real production environment.  The .env.example file documents
every required variable.

Import chain: production → base (contains LOGGING, REST_FRAMEWORK, etc.)
"""

from apps.common.env import env, env_bool, env_int, env_list  # noqa: F401

from .base import *  # noqa: F401, F403

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------

DEBUG = env_bool("DEBUG", default=False)

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", default="*")

# ---------------------------------------------------------------------------
# Database — PostgreSQL (required; no sqlite fallback in production)
# ---------------------------------------------------------------------------

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB"),
        "USER": env("POSTGRES_USER"),
        "PASSWORD": env("POSTGRES_PASSWORD"),
        "HOST": env("POSTGRES_HOST", default="db"),
        "PORT": env_int("POSTGRES_PORT", default=5432),
        "CONN_MAX_AGE": 60,
    }
}

# ---------------------------------------------------------------------------
# Celery — real broker (Redis), not eager
# ---------------------------------------------------------------------------

CELERY_TASK_ALWAYS_EAGER = False
CELERY_TASK_EAGER_PROPAGATES = False

_redis_url = env("REDIS_URL", default="redis://redis:6379/0")
CELERY_BROKER_URL = _redis_url  # noqa: F405
CELERY_RESULT_BACKEND = _redis_url  # noqa: F405

# ---------------------------------------------------------------------------
# Chroma — HttpClient mode (set CHROMA_HOST in environment)
# ---------------------------------------------------------------------------

CHROMA_HOST = env("CHROMA_HOST", default="chroma")
CHROMA_PORT = env_int("CHROMA_PORT", default=8000)

# ---------------------------------------------------------------------------
# Embeddings — real model (not stub)
# ---------------------------------------------------------------------------

RAVID_EMBEDDINGS_STUB = False
RAVID_LLM_STUB = False
