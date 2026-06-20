FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Install OS-level build dependencies required by some Python packages
# (e.g. psycopg needs libpq, sentence-transformers may need gcc)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the project descriptor first so Docker can cache the pip layer
COPY pyproject.toml README.md manage.py ./
COPY apps ./apps
COPY config ./config

# Install runtime deps (rag extra) + gunicorn; skip dev/test extras
RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install -e '.[rag]' gunicorn

# Create non-root user for security
RUN groupadd --gid 1000 appuser \
    && useradd --uid 1000 --gid appuser --no-create-home --shell /bin/false appuser

# Copy entrypoint and make it executable
COPY docker/django/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Media directory — owned by appuser so gunicorn can write uploads
RUN mkdir -p /app/media && chown -R appuser:appuser /app/media

USER appuser

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
