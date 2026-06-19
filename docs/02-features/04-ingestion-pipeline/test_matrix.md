# Test Matrix — 04 Ingestion pipeline (chunk → embed → Chroma) + status

> Spec: `openspec/changes/s04-ingestion-pipeline-chunk-embed-chroma/`. Completes RAVID Part 2. Tests: stub embeddings + temp Chroma, fully offline.

| Area | Scenario | Type | Expected Result | Command Or Evidence |
|------|----------|------|-----------------|---------------------|
| Happy | extract → split → embed → upsert | Unit | chunk_count > 0; vectors in `user_<id>` collection | `tests/unit/test_pipeline_units.py` |
| Happy | Upload → poll status SUCCESS | Integration | `200 {status:"SUCCESS", message:"Document successfully parsed, embedded, and indexed in vector storage."}` | `tests/integration/test_ingestion_api.py` |
| Validation | missing `task_id` param | Integration | `400 {error}` | same |
| Auth | status without JWT | Integration | `401 {error}` | same |
| Async | Celery state machine PENDING→STARTED→SUCCESS/FAILURE | Integration | job row is source of truth | same |
| Async | constructed STARTED job → PROCESSING | Integration | `200 {status:"PROCESSING"}` | same |
| Failure | unparseable / no-text doc | Integration | job FAILURE + error_message; `200 {status:"FAILURE", error}`; failure logged, not swallowed | same (caplog) |
| Observability | `operation=ingest` logged; no text/secrets | Design/Unit | JSON log fields only | `apps/rag/tasks.py` |
| Docker | (deferred to slice 07; chroma service) | — | — | — |
| **Isolation** | cross-user status → 404; A's vectors only in `user_A`; delete removes vectors | Integration | 404; collection-scoped; count drops on delete | `test_user_a_vectors_not_in_user_b_collection`, `test_delete_removes_vectors_from_chroma` |
| Regression | `/api/chat/query/` still ABSENT | Smoke | `404`; status now present | `tests/smoke/test_endpoints_absent.py` |
| Hygiene | lint/format/commit hooks | Local | all pass | `pre-commit run --all-files` |

**Total:** 151 tests pass (36 new for ingestion + 115 prior). Offline (stub embeddings, temp Chroma, eager Celery).
