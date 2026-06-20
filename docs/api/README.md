# API Documentation

RAVID ships API documentation in two formats:

- **Live Swagger UI:** `http://localhost:8000/api/docs/` (available when the stack is running)
- **OpenAPI schema:** `http://localhost:8000/api/schema/` (machine-readable YAML/JSON)
- **Postman collection:** [`docs/api/ravid.postman_collection.json`](ravid.postman_collection.json)

## Import Into Postman

1. Open Postman.
2. Click **Import** and select `docs/api/ravid.postman_collection.json`.
3. Review the collection variables (all pre-set to sensible defaults):
   - `baseUrl` — default: `http://localhost:8000`
   - `email` — default: `reviewer@example.com`
   - `password` — default: `Sup3rSecret!`
4. Run requests in this order:
   1. **Register** — creates your account
   2. **Login** — stores `accessToken` automatically
   3. **Upload Document** — select a `.pdf`, `.txt`, or `.md` file; stores `documentId` + `taskId`
   4. **Ingestion Status** — poll until `"status": "SUCCESS"`
   5. **Chat Query** — ask any question against your uploaded documents
   6. **List Documents** — returns your owner-scoped document list
   7. **Health Check** — unauthenticated liveness probe (`GET /api/health/`). Note: Health Check needs no Authorization header.

## Notes

- All protected endpoints require `Authorization: Bearer {{accessToken}}`.
- The collection auto-captures `accessToken`, `documentId`, and `taskId` from responses.
- Errors always use the envelope `{"error": "<message>"}`.
- Cross-user resource access returns **404** (not 403) — the API never leaks resource existence.
- API keys and JWTs are never logged (D-027).
