# document-ingestion Specification

## Purpose
TBD - created by archiving change s04-ingestion-pipeline-chunk-embed-chroma. Update Purpose after archive.
## Requirements
### Requirement: Asynchronous ingestion pipeline
On upload, the system SHALL asynchronously extract text, chunk it, embed it, and index the vectors in the uploading user's isolated vector collection.

#### Scenario: Successful ingestion
- **WHEN** an authenticated user uploads a valid PDF/TXT/MD document
- **THEN** a Celery task extracts the text, splits it with a 1000/150 recursive splitter, embeds the chunks, and upserts them into the Chroma collection `user_<owner_id>`
- **AND** an `IngestionJob` row transitions `PENDING` → `STARTED` → `SUCCESS` and records `chunk_count > 0`

#### Scenario: Ingestion failure is surfaced
- **WHEN** a document cannot be parsed or embedded
- **THEN** the `IngestionJob` is set to `FAILURE` with a non-empty `error_message`
- **AND** the failure is recorded in the structured logs (without document contents or secrets)
- **AND** the failure is NOT silently swallowed

### Requirement: Ingestion status endpoint
The system SHALL expose `GET /api/documents/status/?task_id=<id>` returning the job state for the caller's own jobs.

#### Scenario: Processing
- **WHEN** the caller polls the status of a job that is queued or running
- **THEN** the response is `200` with `{"task_id":"<id>","status":"PROCESSING"}`

#### Scenario: Success
- **WHEN** the caller polls the status of a completed job
- **THEN** the response is `200` with `{"task_id":"<id>","status":"SUCCESS","message":"Document successfully parsed, embedded, and indexed in vector storage."}`

#### Scenario: Failure
- **WHEN** the caller polls the status of a failed job
- **THEN** the response is `200` with `{"task_id":"<id>","status":"FAILURE","error":"<message>"}`

#### Scenario: Unknown or other user's task
- **WHEN** the caller polls a task_id that does not exist or belongs to another user
- **THEN** the response is `404` (no existence leak)

### Requirement: Per-user vector isolation
Vectors SHALL be stored and queried only within the owning user's collection.

#### Scenario: Vectors are stored per owner
- **WHEN** two different users ingest documents
- **THEN** each user's chunks live in their own `user_<owner_id>` collection and never appear in another user's collection

#### Scenario: Deleting a document removes its vectors
- **WHEN** a user deletes a document
- **THEN** that document's chunks are removed from the user's collection
