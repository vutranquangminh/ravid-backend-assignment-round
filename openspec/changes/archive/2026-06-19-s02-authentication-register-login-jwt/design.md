# Design — s02 Authentication

## Context

Slice 01 left a bootable project with `/api/health/` and DRF installed but no auth and the default (AllowAny) permission. The brief (Part 1) specifies exact request/response shapes and the `{error}` envelope. `simplejwt` is already a declared dependency. We use the default Django `User` (decision locked in slice 00 roadmap) to avoid the migration ordering hazard of a custom user model.

## Goals / Non-Goals

**Goals:**
- Exact brief compliance for `/api/register/` and `/api/login/` (status codes, bodies, error envelope).
- A global "authenticated by default" gate so later slices don't each re-implement auth.
- `request.user` available and reliable as the ownership key for slices 03–05.
- Fully offline tests (no network), reusing slice-01 posture.

**Non-Goals:**
- No custom user model, no email verification, no password reset, no refresh-token rotation UI (a `/api/token/refresh/` route is optional, off by default).
- No documents/chat — those are later slices.

## Decisions

- **User identity:** default `django.contrib.auth.models.User`; store the email in BOTH `username` and `email` (username unique). Authenticate by looking up the user by email then `user.check_password()` (or `authenticate(username=email, ...)`). Rationale: keeps the default migration graph, satisfies "email/password" from the brief.
- **`confirm_password`:** NOT required — the brief shows only `{email, password}`. If a `confirm_password` field is sent it must match, but absence is valid. (Documented divergence from the reference repo, which required it.)
- **Validation:** `email` must be a syntactically valid, unique email; `password` required, min length 8. Validation lives in DRF serializers; failures return `400 {error:"<first message>"}` (single-string envelope, not DRF's default dict).
- **JWT:** issue via `RefreshToken.for_user(user)`; return the **access** token as `"token"`. Access lifetime 60 min, refresh 1 day (configurable via env). `AUTH_HEADER_TYPES = ("Bearer",)`. simplejwt set as `DEFAULT_AUTHENTICATION_CLASSES`.
- **Permissions:** `DEFAULT_PERMISSION_CLASSES = ["rest_framework.permissions.IsAuthenticated"]`. `RegisterView`/`LoginView`/health override to `AllowAny`. Missing/invalid token on a protected route → `401` (DRF default, but normalize body to `{error}` via a custom exception handler).
- **Error envelope:** add a DRF `EXCEPTION_HANDLER` in `apps/common` that converts DRF error responses to `{"error": "<message>"}` for 400/401/403/404/405 so the whole API is consistent (M-... envelope consistency). 404 for cross-user ownership lands in later slices but the handler is introduced here.
- **Ownership note:** no owned models yet; the test suite includes an authenticated probe (e.g. a temporary `/api/auth/whoami/` or reuse DRF) to assert protected access requires a valid token. Prefer a minimal `GET /api/auth/me/` returning the current user id, which also gives slices a pattern.

## Risks / Trade-offs

- **Email-as-username length:** Django `username` max_length is 150; emails can exceed but rarely. Mitigation: validate length; acceptable for the assessment.
- **Custom exception handler scope:** must not swallow non-API errors. Mitigation: delegate to DRF's default handler first, then reshape only when there's a DRF `Response`.
- **Default User vs "professional" custom model:** custom is arguably cleaner, but the migration-ordering risk and time cost aren't worth it here; documented.
