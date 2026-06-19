"""Custom DRF exception handler that normalises all API errors to the
single-string envelope ``{"error": "<message>"}`` (decision D-022).

Only shapes responses that DRF's own default handler produced (i.e. genuine
API errors). Non-DRF / 500-level errors are left to Django's standard error
handling so stack traces are not swallowed.

Covered status codes: 400, 401, 403, 404, 405.
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_default_handler

_HANDLED_STATUSES = {
    status.HTTP_400_BAD_REQUEST,
    status.HTTP_401_UNAUTHORIZED,
    status.HTTP_403_FORBIDDEN,
    status.HTTP_404_NOT_FOUND,
    status.HTTP_405_METHOD_NOT_ALLOWED,
}


def _extract_message(data: object) -> str:
    """Pull a single human-readable string out of DRF error data.

    DRF produces either:
    - a plain string (e.g. from ``raise AuthenticationFailed("…")``)
    - a list of strings (e.g. a single-field validation error)
    - a dict mapping field names → list[str] (serializer validation errors)

    In all cases we return the *first* error message string found.
    """
    if isinstance(data, str):
        return data

    if isinstance(data, list):
        # Flatten one level — each item may itself be a string or list.
        for item in data:
            if isinstance(item, str):
                return item
            if isinstance(item, list) and item:
                return str(item[0])
        return str(data[0]) if data else "An error occurred."

    if isinstance(data, dict):
        # DRF serializer errors: {"field": ["msg1", "msg2"], ...}
        # Also handles simplejwt's {"detail": "..."} style.
        for value in data.values():
            if isinstance(value, str):
                return value
            if isinstance(value, list) and value:
                first = value[0]
                # ErrorDetail objects are str subclasses.
                return str(first)

    return "An error occurred."


def error_envelope_handler(exc: Exception, context: dict) -> Response | None:
    """DRF exception handler — wraps errors in ``{"error": "<msg>"}``."""
    response = drf_default_handler(exc, context)

    if response is None:
        # Not a DRF exception — let Django handle it (500 etc.).
        return None

    if response.status_code not in _HANDLED_STATUSES:
        return response

    message = _extract_message(response.data)
    response.data = {"error": message}
    return response
