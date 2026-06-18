# Test Matrix Template

> One row per scenario. All seven Areas are mandatory — keep the row even if the entry is
> `N/A for this slice` with a one-line reason. `Type` is `automated` (pytest/integration) or
> `manual` (curl/HTTPie/compose). `Command Or Evidence` must be a runnable command or a concrete
> artifact path (log line, screenshot, response body), never a vague claim. Use the verbatim
> endpoints and locked values from `.agents/references/assessment-decisions.md`.

| Area | Scenario | Type | Expected Result | Command Or Evidence |
| --- | --- | --- | --- | --- |
| Happy path | e.g. upload `.pdf` -> 202 with `document_id`,`task_id`; query -> 200 `{answer,tokens_consumed}` |  |  |  |
| Validation | e.g. reject `.exe` and >10 MB with 400 `{error}`; empty `query` rejected |  |  |  |
| Auth | e.g. missing/invalid JWT -> 401; cross-user document/task/vector -> 404 (not 403) |  |  |  |
| Async | e.g. Celery status maps internal -> public `PROCESSING|SUCCESS|FAILURE`; parse/embed failure -> `FAILURE` |  |  |  |
| Observability | e.g. structured JSON log contains required fields; no raw doc text / keys / embeddings leaked |  |  |  |
| Docker | e.g. `docker compose up` brings web+worker+redis+postgres+chroma healthy; endpoint reachable |  |  |  |
| Regression | e.g. prior slices still green (auth, upload, ingestion) after this change |  |  |  |
