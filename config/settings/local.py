"""Local development settings.

Inherits base. Uses sqlite by default for zero-setup runs; set
``LOCAL_USE_POSTGRES=1`` (with POSTGRES_* env vars) to point local dev at a real
PostgreSQL — handy for inspecting data in a GUI like DataGrip.
Default DJANGO_SETTINGS_MODULE points here.
"""

from apps.common.env import env, env_bool, env_int

from .base import *  # noqa: F401, F403

DEBUG = True

ALLOWED_HOSTS = ["*"]

# ---------------------------------------------------------------------------
# Database: sqlite by default; optional local Postgres via LOCAL_USE_POSTGRES.
# ---------------------------------------------------------------------------

if env_bool("LOCAL_USE_POSTGRES", default=False):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("POSTGRES_DB", default="ravid"),
            "USER": env("POSTGRES_USER", default="postgres"),
            "PASSWORD": env("POSTGRES_PASSWORD", default=""),
            "HOST": env("POSTGRES_HOST", default="localhost"),
            "PORT": env_int("POSTGRES_PORT", default=5432),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",  # noqa: F405
        }
    }

# ---------------------------------------------------------------------------
# Celery: keep local dev fast without a running broker.
# Tasks run inline (eager), so document ingestion happens during the upload
# request — no separate worker needed.
# ---------------------------------------------------------------------------

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
