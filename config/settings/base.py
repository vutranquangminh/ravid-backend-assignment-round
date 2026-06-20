"""Base settings shared by all environments.

All secrets and connection strings are read from environment variables via
apps.common.env helpers — never hard-coded (spec requirement D-027).
"""

from datetime import timedelta
from pathlib import Path

from apps.common.env import env, env_bool, env_int, env_list

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------

SECRET_KEY = env("SECRET_KEY", default="insecure-dev-secret-change-in-production")

DEBUG = env_bool("DEBUG", default=False)

ALLOWED_HOSTS: list[str] = env_list("ALLOWED_HOSTS", default="localhost,127.0.0.1")

# ---------------------------------------------------------------------------
# Application definition
# ---------------------------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt",
    # Project apps
    "apps.common.apps.CommonConfig",
    "apps.accounts.apps.AccountsConfig",
    "apps.documents.apps.DocumentsConfig",
    "apps.rag.apps.RagConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.common.middleware.RequestIdMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.common.middleware.RequestLoggingMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", default="ravid"),
        "USER": env("POSTGRES_USER", default="ravid"),
        "PASSWORD": env("POSTGRES_PASSWORD", default="ravid"),
        "HOST": env("POSTGRES_HOST", default="localhost"),
        "PORT": env_int("POSTGRES_PORT", default=5432),
    }
}

# ---------------------------------------------------------------------------
# Auth password validation
# ---------------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------

STATIC_URL = "static/"

# ---------------------------------------------------------------------------
# Media files (uploaded documents)
# ---------------------------------------------------------------------------

MEDIA_URL = "/media/"
MEDIA_ROOT = env("MEDIA_ROOT", default=str(BASE_DIR / "media"))

# ---------------------------------------------------------------------------
# Upload constraints (D-018)
# ---------------------------------------------------------------------------

MAX_UPLOAD_MB = env_int("MAX_UPLOAD_MB", default=10)

# ---------------------------------------------------------------------------
# Default primary key
# ---------------------------------------------------------------------------

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "EXCEPTION_HANDLER": "apps.common.exceptions.error_envelope_handler",
}

# ---------------------------------------------------------------------------
# SimpleJWT
# ---------------------------------------------------------------------------

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env_int("ACCESS_TOKEN_MINUTES", default=60)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# ---------------------------------------------------------------------------
# Celery
# ---------------------------------------------------------------------------

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://localhost:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"

# ---------------------------------------------------------------------------
# Chroma (vector store for RAG — slice 04)
# ---------------------------------------------------------------------------

CHROMA_PERSIST_DIR = env("CHROMA_PERSIST_DIR", default=str(BASE_DIR / "chroma_data"))

# ---------------------------------------------------------------------------
# Embedding model (local HuggingFace — D-010)
# ---------------------------------------------------------------------------

EMBEDDING_MODEL = env("EMBEDDING_MODEL", default="sentence-transformers/all-MiniLM-L6-v2")

# ---------------------------------------------------------------------------
# RAG pipeline parameters (D-011, D-012)
# ---------------------------------------------------------------------------

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150
RETRIEVAL_TOP_K = 4

# ---------------------------------------------------------------------------
# OpenRouter (placeholder — used in rag slice)
# ---------------------------------------------------------------------------

OPENROUTER_API_KEY = env("OPENROUTER_API_KEY", default="")
OPENROUTER_BASE_URL = env("OPENROUTER_BASE_URL", default="https://openrouter.ai/api/v1")
OPENROUTER_MODEL = env("OPENROUTER_MODEL", default="mistralai/mistral-7b-instruct:free")

# ---------------------------------------------------------------------------
# Chat credit defaults (slice 05)
# ---------------------------------------------------------------------------

DEFAULT_CHAT_CREDITS = env_int("DEFAULT_CHAT_CREDITS", default=100000)

# ---------------------------------------------------------------------------
# Structured JSON logging
# ---------------------------------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.json.JsonFormatter",
            "fmt": "%(asctime)s %(levelname)s %(name)s %(message)s",
            "rename_fields": {
                "asctime": "ts",
                "levelname": "level",
                "name": "logger",
            },
        },
    },
    "handlers": {
        "stdout_json": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
    },
    "root": {
        "handlers": ["stdout_json"],
        "level": "INFO",
    },
    "loggers": {
        "celery": {
            "handlers": ["stdout_json"],
            "level": "INFO",
            "propagate": False,
        },
        "django": {
            "handlers": ["stdout_json"],
            "level": "INFO",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["stdout_json"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}
