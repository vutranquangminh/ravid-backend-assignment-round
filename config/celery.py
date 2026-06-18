"""Celery application for the RAVID backend."""

import os

from celery import Celery

# Set the default Django settings module for the Celery command-line program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

app = Celery("ravid")

# Use the CELERY_ namespace in Django settings so Celery settings are grouped.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks in all installed apps.
app.autodiscover_tasks()
