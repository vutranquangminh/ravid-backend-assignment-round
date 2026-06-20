#!/bin/sh
# Entrypoint for the RAVID Django container.
# Runs database migrations then starts gunicorn.
set -e

echo "Running database migrations..."
python manage.py migrate --noinput

echo "Starting gunicorn..."
exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-3}" \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
