# document-management Specification

## Purpose
TBD - created by archiving change s03-document-upload-pdf-txt-md. Update Purpose after archive.
## Requirements
### Requirement: Authenticated document upload
The system SHALL accept an authenticated multipart upload of a single file and SHALL only allow PDF, TXT, and Markdown files up to the configured size limit.

#### Scenario: Successful upload
- **WHEN** an authenticated user sends `POST /api/documents/upload/` with a multipart `file` that is a `.pdf`, `.txt`, or `.md` within the size limit
- **THEN** the response is `202 Accepted` with body `{"message":"Document uploaded and ingestion started","document_id":<id>,"task_id":"<id>"}`
- **AND** the file is stored under `uploads/user_<owner_id>/` and a `Document` row is created owned by the caller
- **AND** an ingestion task is enqueued for that document

#### Scenario: Rejected file type
- **WHEN** the uploaded file is not a PDF/TXT/MD (by extension or content-type)
- **THEN** the response is `400 Bad Request` with body `{"error":"Invalid file format. Only PDF, TXT, and Markdown files are allowed."}`
- **AND** no file is persisted and no task is enqueued

#### Scenario: Oversized file
- **WHEN** the uploaded file exceeds the size limit (default 10 MB)
- **THEN** the response is `400 Bad Request` with body `{"error":"<message>"}` and nothing is persisted

#### Scenario: Upload requires authentication
- **WHEN** `POST /api/documents/upload/` is called without a valid JWT
- **THEN** the response is `401 Unauthorized` with body `{"error":"<message>"}`

### Requirement: Per-user document isolation
A user SHALL only be able to see and delete their own documents; another user's documents SHALL appear not to exist.

#### Scenario: List returns only own documents
- **WHEN** an authenticated user sends `GET /api/documents/`
- **THEN** the response contains only documents owned by that user

#### Scenario: Deleting another user's document is not found
- **WHEN** user A sends `DELETE /api/documents/<id>/` for a document owned by user B
- **THEN** the response is `404 Not Found` (not 403) and user B's document is unchanged

#### Scenario: Deleting own document
- **WHEN** a user deletes their own document
- **THEN** the response is `204 No Content` and both the row and the stored file are removed
