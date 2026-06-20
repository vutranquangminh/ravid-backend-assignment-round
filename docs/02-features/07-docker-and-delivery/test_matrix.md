# Test Matrix — 07 Docker & delivery (compose + CI + API docs)

> Spec: `openspec/changes/s07-docker-and-delivery-compose-ci/`. Implements RAVID Part 4. Container run is the reviewer's step (Docker daemon unavailable in authoring env); validated statically + by structure tests.

| Area | Scenario | Type | Expected Result | Command Or Evidence |
|------|----------|------|-----------------|---------------------|
| Docker | compose defines full stack | Integration | services web/celery/db/redis/chroma/grafana/loki/alloy present, healthchecks, named volumes, chroma on 127.0.0.1:8001 | `tests/integration/test_delivery.py` |
| Docker | compose files parse | Static | `docker compose config` valid (compose.yaml + compose.ci.yaml) | re-run independently |
| Docker | delivery files exist | Integration | Dockerfile, entrypoint, observability configs, Postman collection, pr-ci.yml | `test_delivery.py` |
| Config | production settings import-clean | Static | `manage.py check` clean under `config.settings.production` | re-run independently |
| Config | `.env.example` has required keys | Integration | POSTGRES_*, CHROMA_HOST, OPENROUTER_*, ALLOWED_HOSTS | `test_delivery.py` |
| API docs | `/api/schema/` + `/api/docs/` | Integration | `200`; schema has `openapi` + `paths` incl. chat/upload | `test_delivery.py` |
| Vector store | dual-mode client | Unit | HttpClient when CHROMA_HOST set; PersistentClient otherwise | `tests/unit/test_vectorstore_modes.py` |
| CI | pipeline defined | Static | repo-checks → tests → container-validation jobs | `.github/workflows/pr-ci.yml` |
| Observability | Grafana dashboard + datasource provisioned | Static | `service` low-cardinality label; RAG fields in payload | `docker/grafana/**`, `docker/alloy/config.alloy` |
| Regression | full suite stays green | All | 620 passed | `pytest -q` |
| Hygiene | lint/format/commit hooks | Local | all pass | `pre-commit run --all-files` |

**Total:** 620 tests pass (48 new for delivery + 572 prior). Container build/run is documented for the reviewer; everything else validated offline.
