"""Edge-case integration tests for the authentication surface (slice 02).

Targets:
  apps.accounts.views / serializers / services
  apps.common.exceptions  (the {"error": "<msg>"} envelope)

Endpoints under test:
  POST /api/register/   (AllowAny)   -> 201 {message, user_id} | 400 {error}
  POST /api/login/      (AllowAny)   -> 200 {message, token}    | 401 {error}
  GET  /api/auth/me/    (JWT)        -> 200 {user_id, email}    | 401/405 {error}

These tests document *actual* observed behavior (probed against the live test
stack), not assumptions:
  - EmailField trims surrounding whitespace and accepts the address before
    ``validate_email`` lowercases it; duplicate detection is case-insensitive.
  - Password min length is enforced at the serializer (>= 8 chars); the Django
    AUTH_PASSWORD_VALIDATORS do NOT run on register (create_user path).
  - ``confirm_password`` is optional (D-023): absent => OK, matching => OK,
    mismatching => 400 "Passwords do not match.".
  - Login is case-insensitive and whitespace-trimming on the email; every
    failure (wrong pw, unknown email, missing/malformed fields) returns the
    SAME 401 "Invalid email or password" (no user enumeration).
  - All error bodies are the single-string envelope {"error": "<str>"}; never a
    dict-of-fields. This holds for 400, 401 and 405.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from rest_framework_simplejwt.tokens import AccessToken

User = get_user_model()

REGISTER_URL = "/api/register/"
LOGIN_URL = "/api/login/"
ME_URL = "/api/auth/me/"


# ---------------------------------------------------------------------------
# Helpers (kept local to this file per the test-authoring rules)
# ---------------------------------------------------------------------------


def _post_json(client: Client, url: str, data: dict) -> object:
    return client.post(url, data=json.dumps(data), content_type="application/json")


def _register(client: Client, email: str, password: str) -> object:
    return _post_json(client, REGISTER_URL, {"email": email, "password": password})


def _login(client: Client, email: str, password: str) -> object:
    return _post_json(client, LOGIN_URL, {"email": email, "password": password})


def _login_token(client: Client, email: str, password: str) -> str:
    """Register (if needed) + login and return a usable JWT access token."""
    resp = _login(client, email, password)
    assert resp.status_code == 200, resp.content
    token = resp.json()["token"]
    assert isinstance(token, str) and len(token) > 0
    return token


def _assert_error_envelope(body: object) -> str:
    """Assert ``body`` is exactly ``{"error": "<some non-empty string>"}``.

    Returns the error string so callers can additionally assert its content.
    This is the core D-022 invariant: a single string field, never a nested
    dict-of-fields DRF default shape.
    """
    assert isinstance(body, dict)
    assert list(body.keys()) == ["error"], f"expected only an 'error' key, got {body!r}"
    message = body["error"]
    assert isinstance(message, str)
    assert message != ""
    return message


# ===========================================================================
# Register — happy path + body shape
# ===========================================================================


@pytest.mark.django_db
class TestRegisterHappyPath:
    def test_success_body_shape_message_and_user_id(self) -> None:
        client = Client()
        resp = _register(client, "newbie@example.com", "strongpass1")
        assert resp.status_code == 201
        body = resp.json()
        assert set(body.keys()) == {"message", "user_id"}
        assert body["message"] == "Registration successful"
        assert isinstance(body["user_id"], int)

    def test_user_id_matches_persisted_row(self) -> None:
        client = Client()
        resp = _register(client, "persist@example.com", "strongpass1")
        assert resp.status_code == 201
        user = User.objects.get(username="persist@example.com")
        assert resp.json()["user_id"] == user.pk

    def test_password_is_hashed_never_plaintext(self) -> None:
        client = Client()
        plaintext = "myplain1pw"
        assert _register(client, "hash@example.com", plaintext).status_code == 201
        user = User.objects.get(username="hash@example.com")
        assert user.password != plaintext
        assert user.check_password(plaintext)

    def test_email_and_username_both_set_to_normalised_value(self) -> None:
        client = Client()
        assert _register(client, "both@example.com", "strongpass1").status_code == 201
        user = User.objects.get(username="both@example.com")
        assert user.email == "both@example.com"
        assert user.username == "both@example.com"


# ===========================================================================
# Register — email normalisation, case, whitespace, duplicates
# ===========================================================================


@pytest.mark.django_db
class TestRegisterEmailNormalisation:
    def test_email_stored_lowercase(self) -> None:
        client = Client()
        assert _register(client, "MixedCase@Example.COM", "strongpass1").status_code == 201
        assert User.objects.filter(username="mixedcase@example.com").exists()
        assert not User.objects.filter(username="MixedCase@Example.COM").exists()

    def test_surrounding_whitespace_is_trimmed(self) -> None:
        # EmailField strips leading/trailing whitespace before storage.
        client = Client()
        assert _register(client, "  trimmed@example.com  ", "strongpass1").status_code == 201
        assert User.objects.filter(username="trimmed@example.com").exists()
        assert User.objects.count() == 1

    def test_case_insensitive_duplicate_detection_upper_then_lower(self) -> None:
        # Foo@x.com registered first; foo@x.com is treated as the same account.
        client = Client()
        assert _register(client, "Foo@dup.com", "strongpass1").status_code == 201
        resp = _register(client, "foo@dup.com", "anotherpass1")
        assert resp.status_code == 400
        assert _assert_error_envelope(resp.json()) == "User with this email already exists."
        assert User.objects.filter(email__iexact="foo@dup.com").count() == 1

    def test_case_insensitive_duplicate_detection_lower_then_upper(self) -> None:
        client = Client()
        assert _register(client, "bar@dup.com", "strongpass1").status_code == 201
        resp = _register(client, "BAR@DUP.COM", "anotherpass1")
        assert resp.status_code == 400
        assert _assert_error_envelope(resp.json()) == "User with this email already exists."

    def test_exact_duplicate_message_is_verbatim(self) -> None:
        client = Client()
        assert _register(client, "exact@dup.com", "strongpass1").status_code == 201
        resp = _register(client, "exact@dup.com", "strongpass1")
        assert resp.status_code == 400
        assert resp.json() == {"error": "User with this email already exists."}


# ===========================================================================
# Register — malformed / missing fields
# ===========================================================================


@pytest.mark.django_db
class TestRegisterInvalidInput:
    @pytest.mark.parametrize(
        "bad_email",
        [
            "noatsign",  # no @
            "no@domain",  # no dot / TLD
            "a@b",  # domain has no dot
            "@example.com",  # missing local part
            "spaces in@example.com",  # whitespace inside
            "",  # empty
        ],
    )
    def test_malformed_email_returns_400_envelope(self, bad_email: str) -> None:
        client = Client()
        resp = _register(client, bad_email, "strongpass1")
        assert resp.status_code == 400
        _assert_error_envelope(resp.json())
        assert User.objects.count() == 0

    def test_missing_email_field(self) -> None:
        client = Client()
        resp = _post_json(client, REGISTER_URL, {"password": "strongpass1"})
        assert resp.status_code == 400
        assert _assert_error_envelope(resp.json()) == "This field is required."

    def test_missing_password_field(self) -> None:
        client = Client()
        resp = _post_json(client, REGISTER_URL, {"email": "nopw@example.com"})
        assert resp.status_code == 400
        assert _assert_error_envelope(resp.json()) == "This field is required."

    def test_empty_body(self) -> None:
        client = Client()
        resp = _post_json(client, REGISTER_URL, {})
        assert resp.status_code == 400
        _assert_error_envelope(resp.json())
        assert User.objects.count() == 0

    def test_null_email_value(self) -> None:
        client = Client()
        resp = _post_json(client, REGISTER_URL, {"email": None, "password": "strongpass1"})
        assert resp.status_code == 400
        _assert_error_envelope(resp.json())


# ===========================================================================
# Register — password length boundaries
# ===========================================================================


@pytest.mark.django_db
class TestRegisterPasswordBoundaries:
    def test_password_exactly_8_chars_is_accepted(self) -> None:
        client = Client()
        resp = _register(client, "eight@example.com", "12345678")  # exactly 8
        assert resp.status_code == 201

    def test_password_7_chars_is_rejected(self) -> None:
        client = Client()
        resp = _register(client, "seven@example.com", "1234567")  # 7
        assert resp.status_code == 400
        assert _assert_error_envelope(resp.json()) == "Ensure this field has at least 8 characters."
        assert User.objects.count() == 0

    def test_empty_password_rejected(self) -> None:
        client = Client()
        resp = _register(client, "emptypw@example.com", "")
        assert resp.status_code == 400
        _assert_error_envelope(resp.json())

    def test_very_long_password_accepted(self) -> None:
        client = Client()
        resp = _register(client, "longpw@example.com", "p" * 4096)
        assert resp.status_code == 201
        # The long password must still authenticate (hashing handled it).
        user = User.objects.get(username="longpw@example.com")
        assert user.check_password("p" * 4096)


# ===========================================================================
# Register — very long email
# ===========================================================================


@pytest.mark.django_db
class TestRegisterLongEmail:
    def test_long_local_part_email_accepted(self) -> None:
        # A 200-char local part is accepted by EmailField in this stack.
        client = Client()
        email = ("a" * 200) + "@example.com"
        resp = _register(client, email, "strongpass1")
        assert resp.status_code == 201
        assert User.objects.filter(username=email.lower()).exists()


# ===========================================================================
# Register — confirm_password handling (D-023)
# ===========================================================================


@pytest.mark.django_db
class TestRegisterConfirmPassword:
    def test_absent_confirm_password_is_ok(self) -> None:
        client = Client()
        resp = _post_json(
            client, REGISTER_URL, {"email": "noconfirm@example.com", "password": "strongpass1"}
        )
        assert resp.status_code == 201

    def test_matching_confirm_password_is_ok(self) -> None:
        client = Client()
        resp = _post_json(
            client,
            REGISTER_URL,
            {
                "email": "matchconfirm@example.com",
                "password": "strongpass1",
                "confirm_password": "strongpass1",
            },
        )
        assert resp.status_code == 201
        assert set(resp.json().keys()) == {"message", "user_id"}

    def test_mismatched_confirm_password_is_rejected(self) -> None:
        client = Client()
        resp = _post_json(
            client,
            REGISTER_URL,
            {
                "email": "badconfirm@example.com",
                "password": "strongpass1",
                "confirm_password": "differentpw1",
            },
        )
        assert resp.status_code == 400
        # The nested {"confirm_password": [...]} error is flattened to a string.
        assert _assert_error_envelope(resp.json()) == "Passwords do not match."
        assert User.objects.count() == 0


# ===========================================================================
# Register — method / content-type robustness
# ===========================================================================


@pytest.mark.django_db
class TestRegisterMethod:
    def test_get_register_returns_405_envelope(self) -> None:
        client = Client()
        resp = client.get(REGISTER_URL)
        assert resp.status_code == 405
        # Even 405 bodies are wrapped in the single-string envelope.
        _assert_error_envelope(resp.json())


# ===========================================================================
# Login — happy path + token usability
# ===========================================================================


@pytest.mark.django_db
class TestLoginHappyPath:
    def setup_method(self) -> None:
        self.email = "loginok@example.com"
        self.password = "correcthorse1"
        User.objects.create_user(username=self.email, email=self.email, password=self.password)

    def test_success_body_shape(self) -> None:
        client = Client()
        resp = _login(client, self.email, self.password)
        assert resp.status_code == 200
        body = resp.json()
        assert set(body.keys()) == {"message", "token"}
        assert body["message"] == "Login successful"
        assert isinstance(body["token"], str)
        assert len(body["token"]) > 0

    def test_token_has_three_jwt_segments(self) -> None:
        client = Client()
        token = _login_token(client, self.email, self.password)
        assert token.count(".") == 2  # header.payload.signature

    def test_returned_token_authenticates_me(self) -> None:
        client = Client()
        token = _login_token(client, self.email, self.password)
        me = client.get(ME_URL, HTTP_AUTHORIZATION=f"Bearer {token}")
        assert me.status_code == 200
        body = me.json()
        assert body["email"] == self.email
        assert isinstance(body["user_id"], int)

    def test_login_is_case_insensitive_on_email(self) -> None:
        client = Client()
        resp = _login(client, self.email.upper(), self.password)
        assert resp.status_code == 200
        assert len(resp.json()["token"]) > 0

    def test_login_trims_surrounding_whitespace_on_email(self) -> None:
        client = Client()
        resp = _login(client, f"  {self.email}  ", self.password)
        assert resp.status_code == 200

    def test_two_logins_yield_distinct_tokens(self) -> None:
        # Each access token carries a distinct jti, so re-login is not identical.
        client = Client()
        t1 = _login_token(client, self.email, self.password)
        t2 = _login_token(client, self.email, self.password)
        assert t1 != t2
        # Both still authenticate to the same identity.
        for tok in (t1, t2):
            me = client.get(ME_URL, HTTP_AUTHORIZATION=f"Bearer {tok}")
            assert me.json()["email"] == self.email


# ===========================================================================
# Login — failures all return the SAME opaque 401 (no user enumeration)
# ===========================================================================


@pytest.mark.django_db
class TestLoginFailures:
    EXACT = "Invalid email or password"

    def setup_method(self) -> None:
        self.email = "victim@example.com"
        self.password = "rightpassword1"
        User.objects.create_user(username=self.email, email=self.email, password=self.password)

    def test_wrong_password(self) -> None:
        client = Client()
        resp = _login(client, self.email, "wrongpassword1")
        assert resp.status_code == 401
        assert resp.json() == {"error": self.EXACT}

    def test_unknown_email(self) -> None:
        client = Client()
        resp = _login(client, "ghost@example.com", "anypassword1")
        assert resp.status_code == 401
        assert resp.json() == {"error": self.EXACT}

    def test_unknown_email_and_wrong_password_are_indistinguishable(self) -> None:
        # Enumeration guard: a present user with a wrong password and a totally
        # unknown email must return byte-identical bodies + status.
        client = Client()
        wrong_pw = _login(client, self.email, "nope12345")
        unknown = _login(client, "stranger@example.com", "nope12345")
        assert wrong_pw.status_code == unknown.status_code == 401
        assert wrong_pw.json() == unknown.json() == {"error": self.EXACT}

    def test_missing_password_field_returns_401(self) -> None:
        client = Client()
        resp = _post_json(client, LOGIN_URL, {"email": self.email})
        assert resp.status_code == 401
        assert resp.json() == {"error": self.EXACT}

    def test_missing_email_field_returns_401(self) -> None:
        client = Client()
        resp = _post_json(client, LOGIN_URL, {"password": self.password})
        assert resp.status_code == 401
        assert resp.json() == {"error": self.EXACT}

    def test_empty_body_returns_401(self) -> None:
        client = Client()
        resp = _post_json(client, LOGIN_URL, {})
        assert resp.status_code == 401
        assert resp.json() == {"error": self.EXACT}

    def test_malformed_email_format_returns_401_not_400(self) -> None:
        # A bad email *format* is still an auth failure here, not a 400.
        client = Client()
        resp = _login(client, "not-an-email", self.password)
        assert resp.status_code == 401
        assert resp.json() == {"error": self.EXACT}

    def test_get_login_returns_405_envelope(self) -> None:
        client = Client()
        resp = client.get(LOGIN_URL)
        assert resp.status_code == 405
        _assert_error_envelope(resp.json())


# ===========================================================================
# /api/auth/me/ — token validation edge cases
# ===========================================================================


@pytest.mark.django_db
class TestMeTokenEdges:
    def setup_method(self) -> None:
        self.email = "meuser@example.com"
        self.password = "validpass123"
        self.user = User.objects.create_user(
            username=self.email, email=self.email, password=self.password
        )

    def _valid_token(self) -> str:
        return str(AccessToken.for_user(self.user))

    def test_valid_token_returns_identity(self) -> None:
        client = Client()
        resp = client.get(ME_URL, HTTP_AUTHORIZATION=f"Bearer {self._valid_token()}")
        assert resp.status_code == 200
        body = resp.json()
        assert set(body.keys()) == {"user_id", "email"}
        assert body["user_id"] == self.user.pk
        assert body["email"] == self.email

    def test_no_authorization_header(self) -> None:
        client = Client()
        resp = client.get(ME_URL)
        assert resp.status_code == 401
        _assert_error_envelope(resp.json())

    def test_empty_authorization_header(self) -> None:
        client = Client()
        resp = client.get(ME_URL, HTTP_AUTHORIZATION="")
        assert resp.status_code == 401
        _assert_error_envelope(resp.json())

    def test_garbage_bearer_token(self) -> None:
        client = Client()
        resp = client.get(ME_URL, HTTP_AUTHORIZATION="Bearer not.a.real.jwt")
        assert resp.status_code == 401
        _assert_error_envelope(resp.json())

    def test_bearer_with_no_value(self) -> None:
        client = Client()
        resp = client.get(ME_URL, HTTP_AUTHORIZATION="Bearer")
        assert resp.status_code == 401
        _assert_error_envelope(resp.json())

    def test_bearer_with_extra_segments(self) -> None:
        client = Client()
        resp = client.get(ME_URL, HTTP_AUTHORIZATION=f"Bearer {self._valid_token()} extra")
        assert resp.status_code == 401
        _assert_error_envelope(resp.json())

    def test_wrong_auth_scheme_is_ignored(self) -> None:
        # Only "Bearer" is configured (AUTH_HEADER_TYPES); "Token" is not honored.
        client = Client()
        resp = client.get(ME_URL, HTTP_AUTHORIZATION=f"Token {self._valid_token()}")
        assert resp.status_code == 401
        _assert_error_envelope(resp.json())

    def test_expired_token(self) -> None:
        client = Client()
        token = AccessToken.for_user(self.user)
        token.set_exp(lifetime=timedelta(seconds=-10))  # already expired
        resp = client.get(ME_URL, HTTP_AUTHORIZATION=f"Bearer {token!s}")
        assert resp.status_code == 401
        _assert_error_envelope(resp.json())

    def test_invalid_signature_token(self) -> None:
        import jwt as pyjwt

        client = Client()
        good = AccessToken.for_user(self.user)
        forged = pyjwt.encode(
            dict(good.payload), "a-totally-wrong-signing-secret-key", algorithm="HS256"
        )
        resp = client.get(ME_URL, HTTP_AUTHORIZATION=f"Bearer {forged}")
        assert resp.status_code == 401
        _assert_error_envelope(resp.json())

    def test_token_for_deleted_user(self) -> None:
        # A perfectly valid token whose subject no longer exists must 401.
        ghost = User.objects.create_user(
            username="ghost@example.com", email="ghost@example.com", password="pw12345678"
        )
        token = str(AccessToken.for_user(ghost))
        ghost.delete()
        client = Client()
        resp = client.get(ME_URL, HTTP_AUTHORIZATION=f"Bearer {token}")
        assert resp.status_code == 401
        _assert_error_envelope(resp.json())

    def test_post_to_me_returns_405_envelope(self) -> None:
        client = Client()
        resp = client.post(ME_URL, HTTP_AUTHORIZATION=f"Bearer {self._valid_token()}")
        assert resp.status_code == 405
        _assert_error_envelope(resp.json())


# ===========================================================================
# Per-user ISOLATION — a token resolves ONLY to its own owner
# ===========================================================================


@pytest.mark.django_db
class TestPerUserIsolation:
    def _bootstrap(self, client: Client, email: str, password: str) -> tuple[int, str]:
        resp = _register(client, email, password)
        assert resp.status_code == 201
        user_id = resp.json()["user_id"]
        token = _login_token(client, email, password)
        return user_id, token

    def test_each_token_returns_its_own_identity(self) -> None:
        client = Client()
        id_a, tok_a = self._bootstrap(client, "alice@iso.com", "alicepass1")
        id_b, tok_b = self._bootstrap(client, "bob@iso.com", "bobpass1234")
        assert id_a != id_b

        me_a = client.get(ME_URL, HTTP_AUTHORIZATION=f"Bearer {tok_a}").json()
        me_b = client.get(ME_URL, HTTP_AUTHORIZATION=f"Bearer {tok_b}").json()

        assert me_a == {"user_id": id_a, "email": "alice@iso.com"}
        assert me_b == {"user_id": id_b, "email": "bob@iso.com"}

    def test_one_user_token_never_leaks_another_users_email(self) -> None:
        client = Client()
        _id_a, tok_a = self._bootstrap(client, "carol@iso.com", "carolpass1")
        self._bootstrap(client, "dave@iso.com", "davepass123")

        me_a = client.get(ME_URL, HTTP_AUTHORIZATION=f"Bearer {tok_a}").json()
        assert me_a["email"] == "carol@iso.com"
        assert me_a["email"] != "dave@iso.com"

    def test_token_embeds_correct_user_id_claim(self) -> None:
        # The simplejwt USER_ID_CLAIM is serialized as a string in this stack;
        # compare against str(user_id) to match the actual claim type.
        client = Client()
        user_id, token = self._bootstrap(client, "eve@iso.com", "evepass1234")
        decoded = AccessToken(token)
        assert str(decoded["user_id"]) == str(user_id)

    def test_tampered_user_id_claim_is_rejected(self) -> None:
        # Forge a token claiming user 999999 but signed with the wrong key:
        # signature verification must fail before any DB lookup trusts it.
        import jwt as pyjwt

        client = Client()
        user_id, token = self._bootstrap(client, "frank@iso.com", "frankpass1")
        payload = dict(AccessToken(token).payload)
        payload["user_id"] = user_id + 999999
        forged = pyjwt.encode(payload, "wrong-key-not-the-server-secret", algorithm="HS256")
        resp = client.get(ME_URL, HTTP_AUTHORIZATION=f"Bearer {forged}")
        assert resp.status_code == 401
        _assert_error_envelope(resp.json())
