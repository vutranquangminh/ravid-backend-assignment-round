# Tasks — s02 Authentication

## 1. Settings & auth wiring
- [ ] 1.1 Add simplejwt to `DEFAULT_AUTHENTICATION_CLASSES`; set `DEFAULT_PERMISSION_CLASSES=[IsAuthenticated]` and a custom `EXCEPTION_HANDLER`.
- [ ] 1.2 Add simplejwt token lifetimes (env-configurable) and `AUTH_HEADER_TYPES=("Bearer",)`.
- [ ] 1.3 Ensure `django.contrib.auth` + `contenttypes` in `INSTALLED_APPS`.

## 2. Common error envelope
- [ ] 2.1 `apps/common/exceptions.py`: DRF exception handler that reshapes API errors to `{"error": "<message>"}` (400/401/403/404/405).

## 3. Accounts app
- [ ] 3.1 `serializers.py`: `RegisterSerializer` (email valid+unique, password min-8, optional confirm_password match) and `LoginSerializer`.
- [ ] 3.2 `services.py`: `register_user(email, password)` (create_user, email-as-username) and `authenticate_user(email, password)`.
- [ ] 3.3 `views.py`: `RegisterView` (201 {message,user_id} | 400), `LoginView` (200 {message,token} | 401), both AllowAny + empty authentication_classes. `MeView` (GET /api/auth/me/, IsAuthenticated) returning the current user id.
- [ ] 3.4 `urls.py` + include in `config/urls.py` (uncomment the accounts include).

## 4. Migrations
- [ ] 4.1 `makemigrations` (auth uses default User → no custom model migration; ensure migration state clean) and check in any app migrations.

## 5. Tests
- [ ] 5.1 Integration: register success (201 + user_id), duplicate email (400 + exact message), invalid email/short password (400 envelope).
- [ ] 5.2 Integration: login success (200 + token), wrong password & unknown email (401 + exact message).
- [ ] 5.3 Integration: protected route without token → 401 `{error}`; with valid token → 200 (`/api/auth/me/`).
- [ ] 5.4 Unit: serializer validation; service register/authenticate; exception handler shapes `{error}`.
- [ ] 5.5 Regression: `/api/documents/upload/`, `/api/documents/status/`, `/api/chat/query/` still ABSENT (404).

## 6. Validate & deliver
- [ ] 6.1 `manage.py check` clean; `pytest` green; `pre-commit` clean.
- [ ] 6.2 Author `docs/02-features/02-authentication/{test_matrix,validation-report,pull_request}.md`.
- [ ] 6.3 Open PR into `main` (base main directly — no stacking, no branch deletion); `openspec archive s02` after merge.
