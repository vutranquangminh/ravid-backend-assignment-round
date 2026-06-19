"""Common views for the RAVID backend.

Health endpoint:
  GET /api/health/  ->  200 {"status": "ok"}
  - AllowAny (no auth required)
  - No DB interaction (pure liveness check)
"""

from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request: Request) -> JsonResponse:
    """Liveness probe — returns 200 OK without touching the database."""
    return JsonResponse({"status": "ok"})
