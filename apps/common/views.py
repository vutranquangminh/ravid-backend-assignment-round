"""Common views for the RAVID backend.

Health endpoint:
  GET /api/health/  ->  200 {"status": "ok"}
  - AllowAny (no auth required)
  - No DB interaction (pure liveness check)
"""

from django.http import JsonResponse
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request


@extend_schema(
    summary="Health check",
    description="Liveness probe that returns 200 OK without touching the database.",
    request=None,
    responses={
        200: OpenApiResponse(
            response=inline_serializer(
                name="HealthResponse",
                fields={"status": serializers.CharField()},
            ),
            description="Service is healthy.",
            examples=[
                OpenApiExample(
                    name="ok",
                    value={"status": "ok"},
                    response_only=True,
                )
            ],
        )
    },
    auth=[],
)
@api_view(["GET"])
@permission_classes([AllowAny])
def health(request: Request) -> JsonResponse:
    """Liveness probe — returns 200 OK without touching the database."""
    return JsonResponse({"status": "ok"})
