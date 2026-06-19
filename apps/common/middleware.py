"""Cross-cutting HTTP middleware for RAVID.

Middleware order in settings.MIDDLEWARE:
  1. RequestIdMiddleware   — generates request_id early so it's available to all
  2. ... (other Django middleware) ...
  3. RequestLoggingMiddleware — runs after the response is ready, logs duration

Hard rules (D-027):
  - NEVER log request bodies, document content, or credentials.
  - Only log metadata: method, path, status, duration, request_id.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

logger = logging.getLogger(__name__)

# Thread-local storage for request_id propagation within a single request.
# Using a simple attribute on the request object is sufficient and avoids
# threading issues since Django's WSGI/ASGI handlers bind one request per call.
REQUEST_ID_ATTR = "_ravid_request_id"


def get_request_id(request: HttpRequest) -> str:
    """Return the request_id attached to *request*, or an empty string."""
    return getattr(request, REQUEST_ID_ATTR, "")


class RequestIdMiddleware:
    """Generate a UUID4 request_id and attach it to the request object.

    Reads ``X-Request-ID`` from the incoming headers if present (so upstream
    proxies can propagate a trace id); otherwise generates a fresh uuid4.

    The request_id is echoed in the ``X-Request-ID`` response header so
    clients can correlate requests with logs.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        setattr(request, REQUEST_ID_ATTR, request_id)

        response = self.get_response(request)

        response["X-Request-ID"] = request_id
        return response


class RequestLoggingMiddleware:
    """Emit a structured JSON log line for every HTTP request.

    Logged fields (per observability.md contract):
      - request_id
      - method
      - path
      - status
      - duration_ms

    NOT logged: headers, query strings, request/response bodies, credentials.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        start = time.monotonic()

        response = self.get_response(request)

        duration_ms = round((time.monotonic() - start) * 1000, 2)

        logger.info(
            "http_request",
            extra={
                "request_id": get_request_id(request),
                "method": request.method,
                "path": request.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
            },
        )

        return response
