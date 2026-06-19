"""URL patterns for the accounts app.

Mounted at the root (config/urls.py includes this without a prefix) so that:
  POST /api/register/   -> RegisterView
  POST /api/login/      -> LoginView
  GET  /api/auth/me/    -> MeView
"""

from django.urls import path

from .views import LoginView, MeView, RegisterView

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("auth/me/", MeView.as_view(), name="me"),
]
