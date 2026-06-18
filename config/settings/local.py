"""Local development settings.

Inherits base and switches to sqlite for quick local runs without Docker.
Default DJANGO_SETTINGS_MODULE points here.
"""

from .base import *  # noqa: F401, F403

DEBUG = True

ALLOWED_HOSTS = ["*"]

# ---------------------------------------------------------------------------
# Use sqlite locally so Docker/Postgres are optional for basic dev work.
# ---------------------------------------------------------------------------

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",  # noqa: F405
    }
}

# ---------------------------------------------------------------------------
# Celery: keep local dev fast without a running broker.
# Override to False and set a real CELERY_BROKER_URL when testing async tasks.
# ---------------------------------------------------------------------------

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
