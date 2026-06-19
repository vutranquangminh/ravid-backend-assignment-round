# Test Matrix — 03 Document upload (PDF / TXT / MD)

> Spec: `openspec/changes/s03-document-upload-pdf-txt-md/`. Implements the upload half of RAVID Part 2. Settings: `config.settings.test` (temp MEDIA_ROOT).

| Area | Scenario | Type | Expected Result | Command Or Evidence |
|------|----------|------|-----------------|---------------------|
| Happy | Upload PDF / TXT / MD | Integration | `202 {message, document_id, task_id}`; Document row owned by caller; file under `uploads/user_<id>/` | `tests/integration/test_document_upload_api.py` |
| Happy | Owner lists own docs | Integration | `200` list of caller's documents only | same |
| Validation | Bad type (.exe) | Integration | `400 {"error":"Invalid file format. Only PDF, TXT, and Markdown files are allowed."}` (exact) | same |
| Validation | Oversize (>10MB) | Integration | `400 {error}` | same |
| Validation | serializer matrix + services | Unit | correct accept/reject | `tests/unit/test_document_units.py` |
| Auth | Upload without JWT | Integration | `401 {error}` | same |
| Async | Upload enqueues ingestion (eager) | Integration | task runs inline; status → PROCESSING | `test_ingestion_task_runs_and_sets_processing` |
| Observability | ingest task logs `operation=ingest document_id=` | Inherited/Design | JSON log line | `apps/rag/tasks.py` + middleware |
| Docker | (deferred to slice 07) | — | — | — |
| Regression | `/api/documents/status/`, `/api/chat/query/` still ABSENT | Smoke | `404`; upload now present | `tests/smoke/test_endpoints_absent.py` |
| **Isolation** | User B cannot see/delete user A's doc | Integration | not in B's list; `DELETE` by B → `404`; A deletes own → `204` + file gone | `test_cross_user_*`, `test_list_returns_own_documents_only` |
| Hygiene | lint/format/commit hooks | Local | all pass | `pre-commit run --all-files` |

**Total:** 115 tests pass (40 new for upload + 75 prior). No ML imports; offline.
