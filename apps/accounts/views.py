"""Views for the accounts app.

Public routes (AllowAny, empty authentication_classes):
  POST /api/register/  — register a new user
  POST /api/login/     — obtain a JWT access token

Protected route (IsAuthenticated — default, inherited):
  GET  /api/auth/me/   — return the authenticated user's id and email
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import LoginSerializer, RegisterSerializer
from .services import authenticate_user, register_user


class RegisterView(APIView):
    """POST /api/register/ — create a new user account."""

    authentication_classes: list = []
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            # The custom exception handler will not fire here because we are
            # returning a response directly.  Surface the first error message
            # ourselves so the body is always {"error": "<msg>"}.
            errors = serializer.errors
            message = _first_error(errors)
            return Response({"error": message}, status=status.HTTP_400_BAD_REQUEST)

        validated = serializer.validated_data
        try:
            user = register_user(
                email=validated["email"],
                password=validated["password"],
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {"message": "Registration successful", "user_id": user.pk},
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    """POST /api/login/ — authenticate and return a JWT access token."""

    authentication_classes: list = []
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"error": "Invalid email or password"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        validated = serializer.validated_data
        user = authenticate_user(
            email=validated["email"],
            password=validated["password"],
        )
        if user is None:
            return Response(
                {"error": "Invalid email or password"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        refresh = RefreshToken.for_user(user)
        token = str(refresh.access_token)

        return Response(
            {"message": "Login successful", "token": token},
            status=status.HTTP_200_OK,
        )


class MeView(APIView):
    """GET /api/auth/me/ — return the authenticated user's identity."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        return Response(
            {"user_id": request.user.pk, "email": request.user.email},
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _first_error(errors: dict) -> str:
    """Extract the first human-readable error string from a DRF error dict."""
    for value in errors.values():
        if isinstance(value, str):
            return value
        if isinstance(value, list) and value:
            return str(value[0])
        if isinstance(value, dict):
            # Nested serializer errors — recurse one level.
            return _first_error(value)
    return "Invalid input."
