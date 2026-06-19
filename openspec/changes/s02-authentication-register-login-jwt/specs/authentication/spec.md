# Spec delta — authentication

## ADDED Requirements

### Requirement: User registration
The system SHALL let a new user register with an email and password and SHALL reject duplicate emails.

#### Scenario: Successful registration
- **WHEN** a client sends `POST /api/register/` with JSON `{email, password}` for a new email
- **THEN** the response is `201 Created` with body `{"message": "Registration successful", "user_id": <id>}`
- **AND** the user is persisted with the email as a unique identifier and a hashed password

#### Scenario: Duplicate email
- **WHEN** a client registers with an email that already exists
- **THEN** the response is `400 Bad Request` with body `{"error": "User with this email already exists."}`

#### Scenario: Invalid input
- **WHEN** the email is malformed or the password is shorter than 8 characters
- **THEN** the response is `400 Bad Request` with body `{"error": "<message>"}` (single-string envelope)

### Requirement: User login issues a JWT
The system SHALL authenticate by email + password and return a JWT access token on success.

#### Scenario: Successful login
- **WHEN** a client sends `POST /api/login/` with valid `{email, password}`
- **THEN** the response is `200 OK` with body `{"message": "Login successful", "token": "<jwt_access_token>"}`

#### Scenario: Invalid credentials
- **WHEN** the email is unknown or the password is wrong
- **THEN** the response is `401 Unauthorized` with body `{"error": "Invalid email or password"}`

### Requirement: Authenticated-by-default access control
All API routes except explicitly public ones SHALL require a valid JWT in the `Authorization: Bearer <token>` header.

#### Scenario: Protected route without token
- **WHEN** a client calls a protected route with no or an invalid Authorization header
- **THEN** the response is `401 Unauthorized` with body `{"error": "<message>"}`

#### Scenario: Protected route with valid token
- **WHEN** a client calls `GET /api/auth/me/` with a valid bearer token
- **THEN** the response is `200 OK` and identifies the authenticated user

#### Scenario: Public routes stay open
- **WHEN** a client calls `/api/health/`, `/api/register/`, or `/api/login/` without a token
- **THEN** the request is NOT rejected for missing authentication

### Requirement: Consistent error envelope
API error responses SHALL use the single-string envelope `{"error": "<message>"}` for client and auth errors (400/401/403/404/405).

#### Scenario: Errors are reshaped
- **WHEN** any DRF API error is returned (validation, auth, not-found, method-not-allowed)
- **THEN** the response body is `{"error": "<message>"}` rather than a field-keyed dict
