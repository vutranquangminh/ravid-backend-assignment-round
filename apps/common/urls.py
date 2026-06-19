"""URL patterns for the common app.

Mounted at /api/health/ by config/urls.py.
"""

from django.urls import path

from .views import health

urlpatterns = [
    path("", health, name="health"),
]
