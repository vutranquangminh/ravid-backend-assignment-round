"""Unit + integration tests for apps.common infrastructure.

Targets:
  - apps.common.env       — env / env_bool / env_int / env_list helpers
  - apps.common.middleware— RequestIdMiddleware, RequestLoggingMiddleware
  - apps.common.exceptions— error_envelope_handler + _extract_message
  - apps.common.views     — GET /api/health/ liveness probe

All tests are offline and deterministic. The env tests use monkeypatch on
os.environ (no Django needed). Middleware/health tests use the Django test
Client; exception-handler tests call the handler directly with a minimal
context (DRF's default handler tolerates an empty context dict).

NOTE: tests here intentionally complement (not duplicate) tests/unit/test_env.py
by exercising additional boundaries/edge cases for the env helpers and by
covering the middleware/exception/health surface that test_env.py does not.
"""

from __future__ import annotations

import json
import logging
import uuid

import pytest
from apps.common.env import env, env_bool, env_int, env_list
from apps.common.exceptions import _extract_message, error_envelope_handler
from apps.common.middleware import (
    REQUEST_ID_ATTR,
    RequestIdMiddleware,
    RequestLoggingMiddleware,
    get_request_id,
)
from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import Client, RequestFactory
from rest_framework import exceptions as drf_exc
from rest_framework import status

User = get_user_model()

HEALTH_URL = "/api/health/"
REGISTER_URL = "/api/register/"
LOGIN_URL = "/api/login/"


# ===========================================================================
# env() helper — boundaries beyond the existing test_env.py coverage
# ===========================================================================


class TestEnv:
    def test_default_used_when_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("RAVID_X", raising=False)
        assert env("RAVID_X", default="fallback") == "fallback"

    def test_override_takes_precedence_over_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RAVID_X", "live")
        assert env("RAVID_X", default="fallback") == "live"

    def test_returns_none_without_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("RAVID_X", raising=False)
        assert env("RAVID_X") is None

    def test_empty_string_value_is_returned_not_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # An explicitly empty env var is a *set* value, not "absent".
        monkeypatch.setenv("RAVID_X", "")
        assert env("RAVID_X", default="fallback") == ""

    def test_whitespace_value_is_not_stripped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # env() is a thin os.environ.get — it does NOT strip.
        monkeypatch.setenv("RAVID_X", "  spaced  ")
        assert env("RAVID_X") == "  spaced  "


# ===========================================================================
# env_bool() — all documented truthy/falsy variants + case-insensitivity
# ===========================================================================


class TestEnvBool:
    @pytest.mark.parametrize(
        "raw",
        ["1", "true", "TRUE", "True", "yes", "YES", "Yes", "on", "ON", " true ", "  1  "],
    )
    def test_truthy_variants(self, monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
        monkeypatch.setenv("FLAG", raw)
        assert env_bool("FLAG") is True

    @pytest.mark.parametrize(
        "raw",
        ["0", "false", "FALSE", "False", "no", "NO", "off", "OFF", "", "   ", "2", "enabled", "y"],
    )
    def test_falsy_variants(self, monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
        monkeypatch.setenv("FLAG", raw)
        assert env_bool("FLAG") is False

    def test_absent_returns_default_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("FLAG", raising=False)
        assert env_bool("FLAG") is False

    def test_absent_returns_custom_default_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("FLAG", raising=False)
        assert env_bool("FLAG", default=True) is True

    def test_present_falsy_overrides_default_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # A present-but-falsy value must beat a True default.
        monkeypatch.setenv("FLAG", "0")
        assert env_bool("FLAG", default=True) is False

    def test_empty_string_is_false_even_with_default_true(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FLAG", "")
        assert env_bool("FLAG", default=True) is False

    def test_return_type_is_bool(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FLAG", "yes")
        assert isinstance(env_bool("FLAG"), bool)


# ===========================================================================
# env_int() — valid / invalid / default / boundaries
# ===========================================================================


class TestEnvInt:
    def test_parses_valid_int(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("N", "5432")
        assert env_int("N") == 5432

    def test_parses_negative_int(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("N", "-12")
        assert env_int("N") == -12

    def test_parses_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("N", "0")
        assert env_int("N") == 0

    def test_strips_surrounding_whitespace(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("N", "  42  ")
        assert env_int("N") == 42

    def test_invalid_non_numeric_returns_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("N", "not-a-number")
        assert env_int("N", default=9) == 9

    def test_invalid_float_string_returns_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # int("3.14") raises ValueError → default.
        monkeypatch.setenv("N", "3.14")
        assert env_int("N", default=7) == 7

    def test_empty_string_returns_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("N", "")
        assert env_int("N", default=100) == 100

    def test_whitespace_only_returns_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("N", "   ")
        assert env_int("N", default=100) == 100

    def test_absent_returns_default_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("N", raising=False)
        assert env_int("N") == 0

    def test_absent_returns_custom_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("N", raising=False)
        assert env_int("N", default=8080) == 8080

    def test_return_type_is_int(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("N", "1")
        assert isinstance(env_int("N"), int)


# ===========================================================================
# env_list() — comma parsing, whitespace, empties, default
# ===========================================================================


class TestEnvList:
    def test_simple_comma_parse(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOSTS", "a,b,c")
        assert env_list("HOSTS") == ["a", "b", "c"]

    def test_strips_whitespace_around_items(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOSTS", " a , b ,  c ")
        assert env_list("HOSTS") == ["a", "b", "c"]

    def test_filters_empty_segments(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOSTS", "a,,b,")
        assert env_list("HOSTS") == ["a", "b"]

    def test_only_commas_yields_empty_list(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOSTS", ",,,")
        assert env_list("HOSTS") == []

    def test_whitespace_only_yields_empty_list(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOSTS", "   ")
        assert env_list("HOSTS") == []

    def test_empty_string_yields_empty_list(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOSTS", "")
        assert env_list("HOSTS") == []

    def test_single_value_no_comma(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOSTS", "only")
        assert env_list("HOSTS") == ["only"]

    def test_absent_uses_default_string_parsed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("HOSTS", raising=False)
        assert env_list("HOSTS", default="localhost,127.0.0.1") == ["localhost", "127.0.0.1"]

    def test_absent_with_empty_default_yields_empty_list(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("HOSTS", raising=False)
        assert env_list("HOSTS") == []

    def test_present_value_overrides_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOSTS", "x,y")
        assert env_list("HOSTS", default="a,b,c") == ["x", "y"]

    def test_return_type_is_list_of_str(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOSTS", "a,b")
        result = env_list("HOSTS")
        assert isinstance(result, list)
        assert all(isinstance(x, str) for x in result)


# ===========================================================================
# RequestIdMiddleware
# ===========================================================================


def _ok_response(request: object) -> HttpResponse:
    """Trivial downstream handler returning a 200 response."""
    return HttpResponse("ok")


class TestRequestIdMiddleware:
    def test_generates_request_id_when_absent(self) -> None:
        rf = RequestFactory()
        request = rf.get("/anything/")
        mw = RequestIdMiddleware(_ok_response)

        mw(request)

        rid = getattr(request, REQUEST_ID_ATTR)
        assert rid  # non-empty
        # Generated id must be a valid uuid4 string.
        parsed = uuid.UUID(rid)
        assert parsed.version == 4

    def test_echoes_request_id_in_response_header(self) -> None:
        rf = RequestFactory()
        request = rf.get("/anything/")
        mw = RequestIdMiddleware(_ok_response)

        response = mw(request)

        assert response["X-Request-ID"] == getattr(request, REQUEST_ID_ATTR)

    def test_honors_incoming_request_id_header(self) -> None:
        rf = RequestFactory()
        incoming = "trace-abc-123"
        request = rf.get("/anything/", HTTP_X_REQUEST_ID=incoming)
        mw = RequestIdMiddleware(_ok_response)

        response = mw(request)

        assert getattr(request, REQUEST_ID_ATTR) == incoming
        assert response["X-Request-ID"] == incoming

    def test_blank_incoming_header_falls_back_to_generated(self) -> None:
        rf = RequestFactory()
        request = rf.get("/anything/", HTTP_X_REQUEST_ID="")
        mw = RequestIdMiddleware(_ok_response)

        mw(request)

        rid = getattr(request, REQUEST_ID_ATTR)
        assert rid  # blank header is falsy → generated uuid4
        assert uuid.UUID(rid).version == 4

    def test_distinct_requests_get_distinct_ids(self) -> None:
        rf = RequestFactory()
        mw = RequestIdMiddleware(_ok_response)

        r1 = rf.get("/a/")
        r2 = rf.get("/b/")
        mw(r1)
        mw(r2)

        assert getattr(r1, REQUEST_ID_ATTR) != getattr(r2, REQUEST_ID_ATTR)

    def test_get_request_id_helper_reads_attr(self) -> None:
        rf = RequestFactory()
        request = rf.get("/anything/")
        mw = RequestIdMiddleware(_ok_response)

        mw(request)

        assert get_request_id(request) == getattr(request, REQUEST_ID_ATTR)

    def test_get_request_id_returns_empty_when_unset(self) -> None:
        rf = RequestFactory()
        request = rf.get("/anything/")
        # No middleware ran → attribute absent → empty string.
        assert get_request_id(request) == ""

    @pytest.mark.django_db
    def test_request_id_propagates_end_to_end_via_client(self) -> None:
        """Full stack: a client-supplied X-Request-ID is echoed back."""
        client = Client()
        incoming = "client-supplied-trace-id"
        response = client.get(HEALTH_URL, HTTP_X_REQUEST_ID=incoming)
        assert response["X-Request-ID"] == incoming

    @pytest.mark.django_db
    def test_response_always_has_request_id_header(self) -> None:
        """Even without an incoming header the response carries one."""
        client = Client()
        response = client.get(HEALTH_URL)
        assert response.has_header("X-Request-ID")
        assert uuid.UUID(response["X-Request-ID"]).version == 4


# ===========================================================================
# RequestLoggingMiddleware
# ===========================================================================


class TestRequestLoggingMiddleware:
    def test_emits_info_log_with_metadata(self, caplog: pytest.LogCaptureFixture) -> None:
        rf = RequestFactory()
        request = rf.get("/some/path/")
        setattr(request, REQUEST_ID_ATTR, "rid-xyz")
        mw = RequestLoggingMiddleware(_ok_response)

        with caplog.at_level(logging.INFO, logger="apps.common.middleware"):
            mw(request)

        records = [r for r in caplog.records if r.getMessage() == "http_request"]
        assert len(records) == 1
        rec = records[0]
        assert rec.request_id == "rid-xyz"
        assert rec.method == "GET"
        assert rec.path == "/some/path/"
        assert rec.status == 200
        assert isinstance(rec.duration_ms, float)
        assert rec.duration_ms >= 0

    def test_logs_status_of_downstream_response(self, caplog: pytest.LogCaptureFixture) -> None:
        rf = RequestFactory()
        request = rf.post("/create/")
        setattr(request, REQUEST_ID_ATTR, "rid-201")

        def _created(_req: object) -> HttpResponse:
            return HttpResponse("created", status=201)

        mw = RequestLoggingMiddleware(_created)

        with caplog.at_level(logging.INFO, logger="apps.common.middleware"):
            mw(request)

        rec = next(r for r in caplog.records if r.getMessage() == "http_request")
        assert rec.status == 201
        assert rec.method == "POST"

    def test_log_level_is_info(self, caplog: pytest.LogCaptureFixture) -> None:
        rf = RequestFactory()
        request = rf.get("/x/")
        setattr(request, REQUEST_ID_ATTR, "rid")
        mw = RequestLoggingMiddleware(_ok_response)

        with caplog.at_level(logging.INFO, logger="apps.common.middleware"):
            mw(request)

        rec = next(r for r in caplog.records if r.getMessage() == "http_request")
        assert rec.levelno == logging.INFO

    def test_does_not_log_request_body(self, caplog: pytest.LogCaptureFixture) -> None:
        """Bodies/credentials must never be logged (D-027 / M-008)."""
        rf = RequestFactory()
        secret = "SECRET_PASSWORD_TOKEN_9f8e7d"
        request = rf.post(
            "/login/",
            data=json.dumps({"password": secret}),
            content_type="application/json",
        )
        setattr(request, REQUEST_ID_ATTR, "rid-secret")
        mw = RequestLoggingMiddleware(_ok_response)

        with caplog.at_level(logging.DEBUG):
            mw(request)

        for rec in caplog.records:
            assert secret not in rec.getMessage()
            # The structured extras must not carry the body either.
            assert secret not in str(getattr(rec, "__dict__", {}))

    def test_returns_downstream_response_unchanged(self) -> None:
        rf = RequestFactory()
        request = rf.get("/x/")
        setattr(request, REQUEST_ID_ATTR, "rid")
        sentinel = HttpResponse("payload", status=200)
        mw = RequestLoggingMiddleware(lambda _r: sentinel)

        assert mw(request) is sentinel

    def test_uses_empty_request_id_when_id_middleware_skipped(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """If RequestIdMiddleware did not run, request_id logs as empty string."""
        rf = RequestFactory()
        request = rf.get("/x/")
        mw = RequestLoggingMiddleware(_ok_response)

        with caplog.at_level(logging.INFO, logger="apps.common.middleware"):
            mw(request)

        rec = next(r for r in caplog.records if r.getMessage() == "http_request")
        assert rec.request_id == ""

    @pytest.mark.django_db
    def test_logging_middleware_runs_in_full_stack(self, caplog: pytest.LogCaptureFixture) -> None:
        """End-to-end: hitting /api/health/ emits an http_request log."""
        client = Client()
        with caplog.at_level(logging.INFO, logger="apps.common.middleware"):
            client.get(HEALTH_URL)

        records = [r for r in caplog.records if r.getMessage() == "http_request"]
        assert records, "expected an http_request log from the full stack"
        rec = records[-1]
        assert rec.path == HEALTH_URL
        assert rec.method == "GET"
        assert rec.status == 200
        # request_id must be populated by RequestIdMiddleware upstream.
        assert rec.request_id


# ===========================================================================
# error_envelope_handler — DRF error normalisation (D-022)
# ===========================================================================


class TestErrorEnvelopeHandler:
    def test_validation_error_becomes_error_envelope_400(self) -> None:
        resp = error_envelope_handler(drf_exc.ValidationError("bad input"), {})
        assert resp is not None
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert resp.data == {"error": "bad input"}

    def test_validation_error_dict_picks_first_field_message(self) -> None:
        exc = drf_exc.ValidationError({"email": ["This field is required."]})
        resp = error_envelope_handler(exc, {})
        assert resp.status_code == 400
        assert resp.data == {"error": "This field is required."}

    def test_not_authenticated_becomes_error_envelope_401(self) -> None:
        resp = error_envelope_handler(drf_exc.NotAuthenticated(), {})
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED
        assert set(resp.data.keys()) == {"error"}
        assert isinstance(resp.data["error"], str)
        assert resp.data["error"]

    def test_authentication_failed_becomes_error_envelope_401(self) -> None:
        resp = error_envelope_handler(drf_exc.AuthenticationFailed("nope"), {})
        assert resp.status_code == 401
        assert resp.data == {"error": "nope"}

    def test_permission_denied_becomes_error_envelope_403(self) -> None:
        resp = error_envelope_handler(drf_exc.PermissionDenied(), {})
        assert resp.status_code == status.HTTP_403_FORBIDDEN
        assert set(resp.data.keys()) == {"error"}
        assert resp.data["error"]

    def test_not_found_becomes_error_envelope_404(self) -> None:
        resp = error_envelope_handler(drf_exc.NotFound(), {})
        assert resp.status_code == status.HTTP_404_NOT_FOUND
        assert set(resp.data.keys()) == {"error"}
        assert resp.data["error"]

    def test_method_not_allowed_becomes_error_envelope_405(self) -> None:
        resp = error_envelope_handler(drf_exc.MethodNotAllowed("POST"), {})
        assert resp.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
        assert set(resp.data.keys()) == {"error"}
        assert "POST" in resp.data["error"]

    def test_custom_message_preserved_in_envelope(self) -> None:
        resp = error_envelope_handler(drf_exc.NotFound("Document not found."), {})
        assert resp.data == {"error": "Document not found."}

    def test_unhandled_status_passes_through_unchanged(self) -> None:
        """A 429 (Throttled) is a DRF error but outside the handled set: passthrough."""
        resp = error_envelope_handler(drf_exc.Throttled(wait=5), {})
        assert resp is not None
        assert resp.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        # Original DRF shape retained (NOT reshaped to {"error": ...}).
        assert "detail" in resp.data
        assert "error" not in resp.data

    def test_non_drf_exception_returns_none(self) -> None:
        """A plain Python exception is left to Django (handler returns None)."""
        assert error_envelope_handler(ValueError("boom"), {}) is None

    def test_unhandled_runtime_error_returns_none(self) -> None:
        assert error_envelope_handler(RuntimeError("kaboom"), {}) is None

    def test_envelope_is_single_string_field(self) -> None:
        resp = error_envelope_handler(drf_exc.ValidationError(["msg"]), {})
        assert len(resp.data) == 1
        assert list(resp.data.keys()) == ["error"]
        assert isinstance(resp.data["error"], str)


# ===========================================================================
# _extract_message — internal message-flattening helper
# ===========================================================================


class TestExtractMessage:
    def test_plain_string(self) -> None:
        assert _extract_message("just a string") == "just a string"

    def test_list_of_strings_returns_first(self) -> None:
        assert _extract_message(["first", "second"]) == "first"

    def test_nested_list_returns_inner_first(self) -> None:
        assert _extract_message([["nested msg", "x"]]) == "nested msg"

    def test_empty_list_returns_fallback(self) -> None:
        assert _extract_message([]) == "An error occurred."

    def test_dict_field_list_returns_first(self) -> None:
        assert _extract_message({"email": ["This field is required."]}) == "This field is required."

    def test_dict_detail_string(self) -> None:
        assert _extract_message({"detail": "token expired"}) == "token expired"

    def test_dict_picks_first_usable_value(self) -> None:
        # Insertion order: first value is an empty list (skipped), second is usable.
        data = {"a": [], "b": ["use me"]}
        assert _extract_message(data) == "use me"

    def test_empty_dict_returns_fallback(self) -> None:
        assert _extract_message({}) == "An error occurred."

    def test_unknown_type_returns_fallback(self) -> None:
        assert _extract_message(12345) == "An error occurred."

    def test_none_returns_fallback(self) -> None:
        assert _extract_message(None) == "An error occurred."


# ===========================================================================
# Health endpoint — GET /api/health/
# ===========================================================================


@pytest.mark.django_db
class TestHealthEndpoint:
    def test_get_returns_200_status_ok_without_auth(self) -> None:
        client = Client()
        response = client.get(HEALTH_URL)
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_get_returns_200_with_auth(self) -> None:
        """An authenticated request still succeeds (AllowAny)."""
        email = "health_user@test.com"
        password = "StrongPass1!"
        client = Client()
        creds = {"email": email, "password": password}
        client.post(REGISTER_URL, data=json.dumps(creds), content_type="application/json")
        login = client.post(LOGIN_URL, data=json.dumps(creds), content_type="application/json")
        token = login.json()["token"]

        response = client.get(HEALTH_URL, HTTP_AUTHORIZATION=f"Bearer {token}")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_get_with_invalid_bearer_token_returns_401_envelope(self) -> None:
        """JWTAuthentication runs before AllowAny: a malformed Bearer token is
        rejected with a 401 error envelope even on an AllowAny view (D-021/D-022).
        """
        client = Client()
        response = client.get(HEALTH_URL, HTTP_AUTHORIZATION="Bearer not-a-real-token")
        assert response.status_code == 401
        body = response.json()
        assert set(body.keys()) == {"error"}
        assert isinstance(body["error"], str)

    def test_get_with_no_auth_header_is_ok(self) -> None:
        """No Authorization header at all → AllowAny lets the probe through."""
        client = Client()
        response = client.get(HEALTH_URL)
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_post_returns_405_error_envelope(self) -> None:
        client = Client()
        response = client.post(HEALTH_URL)
        assert response.status_code == 405
        body = response.json()
        assert set(body.keys()) == {"error"}
        assert isinstance(body["error"], str)
        assert body["error"]

    def test_put_returns_405(self) -> None:
        client = Client()
        response = client.put(HEALTH_URL)
        assert response.status_code == 405
        assert "error" in response.json()

    def test_delete_returns_405(self) -> None:
        client = Client()
        response = client.delete(HEALTH_URL)
        assert response.status_code == 405
        assert "error" in response.json()

    def test_response_content_type_is_json(self) -> None:
        client = Client()
        response = client.get(HEALTH_URL)
        assert response["Content-Type"].startswith("application/json")

    def test_health_does_not_require_database_rows(self) -> None:
        """Liveness probe returns ok even with zero users in the DB."""
        assert User.objects.count() == 0
        client = Client()
        response = client.get(HEALTH_URL)
        assert response.status_code == 200
        assert User.objects.count() == 0  # no rows created by the probe
