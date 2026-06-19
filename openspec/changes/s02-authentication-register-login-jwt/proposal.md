# Proposal — s02 Authentication: register / login / JWT

> Workstream **02** · branch `feature/02-authentication-register-login-jwt` · delivery artifacts in `docs/02-features/02-authentication/`. Implements RAVID brief **Part 1**.

## Why

Every later slice (documents, ingestion, chat) is per-user and JWT-protected. This slice delivers the identity layer: email/password registration, login that returns a JWT, and a global "authenticated by default" posture. It also establishes the **ownership baseline** — `request.user` is the owner key that slices 03–05 scope all documents, tasks, and vector queries to.

## What Changes

- Implement `apps/accounts`: `RegisterView` and `LoginView` (DRF `APIView`, `AllowAny`, empty `authentication_classes`), serializers for input validation, and a thin `services.py` for user creation/authentication.
- **`POST /api/register/`** — JSON `{email, password}` → `201 {message, user_id}`; duplicate email → `400 {error:"User with this email already exists."}`.
- **`POST /api/login/`** — JSON `{email, password}` → `200 {message, token:<jwt>}`; bad credentials → `401 {error:"Invalid email or password"}`.
- Wire **`djangorestframework-simplejwt`** as the DRF default authentication; set global `DEFAULT_PERMISSION_CLASSES = IsAuthenticated`. `/api/health/`, `/api/register/`, `/api/login/` stay public.
- Use the **default Django `User`** with email stored as the (unique) username and authentication by email — no custom user model (keeps migrations simple).
- Add accounts URLs and migrations; add an authenticated probe path used by tests to prove the global permission gate works.

## Capabilities

### New Capabilities
- `authentication`: email/password registration, JWT login, and the global authenticated-by-default access control that protects all non-public routes.

### Modified Capabilities
- (none — the global `IsAuthenticated` default and the `{error}` envelope are captured as ADDED requirements under `authentication`; health stays public.)

## Impact

- **New code:** `apps/accounts/{serializers,services,views,urls,apps}.py` + migrations; `tests/integration/test_authentication_api.py`, `tests/unit/test_authentication_units.py`.
- **Modified:** `config/settings/base.py` (simplejwt auth class, `IsAuthenticated` default, `INSTALLED_APPS += rest_framework_simplejwt` if needed), `config/urls.py` (include accounts).
- **Decisions to lock:** email-as-username; `confirm_password` not required (brief shows only email/password); access-token lifetime; password min length.
- **No business models yet** beyond the auth user; documents/chat remain absent (regression tests still assert that).
