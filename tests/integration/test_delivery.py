"""Delivery structure tests for slice 07 (Docker & delivery).

Validates:
  1. compose.yaml structure — services, healthchecks, volumes, Chroma port
  2. Required file existence — Dockerfile, entrypoint, observability configs, CI
  3. .env.example required keys
  4. /api/schema/ returns 200 and valid OpenAPI (has key paths)
  5. /api/docs/ returns 200
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

# Project root relative to this test file
_ROOT = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_compose() -> dict:
    compose_path = _ROOT / "compose.yaml"
    return yaml.safe_load(compose_path.read_text())


# ---------------------------------------------------------------------------
# 1. compose.yaml structure
# ---------------------------------------------------------------------------


class TestComposeStructure:
    """Assert compose.yaml has the required services, healthchecks, and volumes."""

    def test_required_services_present(self):
        compose = _load_compose()
        services = set(compose["services"].keys())
        required = {"web", "celery", "db", "redis", "chroma", "grafana", "loki", "alloy"}
        missing = required - services
        assert not missing, f"Missing services in compose.yaml: {missing}"

    def test_db_has_healthcheck(self):
        compose = _load_compose()
        assert "healthcheck" in compose["services"]["db"]

    def test_redis_has_healthcheck(self):
        compose = _load_compose()
        assert "healthcheck" in compose["services"]["redis"]

    def test_chroma_has_healthcheck(self):
        compose = _load_compose()
        assert "healthcheck" in compose["services"]["chroma"]

    def test_web_has_healthcheck(self):
        compose = _load_compose()
        assert "healthcheck" in compose["services"]["web"]

    def test_grafana_has_healthcheck(self):
        compose = _load_compose()
        assert "healthcheck" in compose["services"]["grafana"]

    def test_named_volumes_exist(self):
        compose = _load_compose()
        volumes = set((compose.get("volumes") or {}).keys())
        required = {"pg_data", "media", "chroma_data", "grafana_data"}
        missing = required - volumes
        assert not missing, f"Missing named volumes: {missing}"

    def test_chroma_port_bound_to_loopback(self):
        """Chroma must be published as 127.0.0.1:8001:8000 (not 0.0.0.0)."""
        compose = _load_compose()
        chroma_ports = compose["services"]["chroma"].get("ports", [])
        port_strings = [str(p) for p in chroma_ports]
        assert any("127.0.0.1:8001" in p for p in port_strings), (
            f"Chroma port should be bound to 127.0.0.1:8001, got: {port_strings}"
        )

    def test_web_depends_on_chroma(self):
        compose = _load_compose()
        depends = compose["services"]["web"].get("depends_on", {})
        # depends_on can be a list or a dict
        if isinstance(depends, dict):
            assert "chroma" in depends
        else:
            assert "chroma" in depends

    def test_celery_depends_on_chroma(self):
        compose = _load_compose()
        depends = compose["services"]["celery"].get("depends_on", {})
        if isinstance(depends, dict):
            assert "chroma" in depends
        else:
            assert "chroma" in depends


# ---------------------------------------------------------------------------
# 2. Required file existence
# ---------------------------------------------------------------------------


class TestFileExistence:
    """Assert that all required delivery files exist on disk."""

    @pytest.mark.parametrize(
        "rel_path",
        [
            "docker/django/Dockerfile",
            "docker/django/entrypoint.sh",
            "compose.ci.yaml",
            "docker/alloy/config.alloy",
            "docker/loki/config.yaml",
            "docker/grafana/provisioning/datasources/loki.yaml",
            "docker/grafana/provisioning/dashboards/observability.yaml",
            "docker/grafana/dashboards/overview.json",
            "docs/api/ravid.postman_collection.json",
            ".github/workflows/pr-ci.yml",
        ],
    )
    def test_file_exists(self, rel_path):
        path = _ROOT / rel_path
        assert path.exists(), f"Required file missing: {rel_path}"

    def test_postman_collection_is_valid_json(self):
        path = _ROOT / "docs/api/ravid.postman_collection.json"
        data = json.loads(path.read_text())
        assert "info" in data
        assert "item" in data

    def test_grafana_dashboard_is_valid_json(self):
        path = _ROOT / "docker/grafana/dashboards/overview.json"
        data = json.loads(path.read_text())
        assert "panels" in data
        assert "uid" in data

    def test_grafana_dashboard_service_variable(self):
        """Service variable must have allValue != '.*' (CI validation rule)."""
        path = _ROOT / "docker/grafana/dashboards/overview.json"
        data = json.loads(path.read_text())
        service_var = next(
            (v for v in data.get("templating", {}).get("list", []) if v.get("name") == "service"),
            None,
        )
        assert service_var is not None, "Missing 'service' template variable in dashboard"
        all_value = service_var.get("allValue", "")
        assert all_value not in {".*", "^.*$", ""}, (
            f"allValue must not be empty-compatible, got: {all_value!r}"
        )


# ---------------------------------------------------------------------------
# 3. .env.example required keys
# ---------------------------------------------------------------------------


class TestEnvExample:
    """Assert .env.example documents all required keys."""

    @pytest.fixture
    def env_example_text(self):
        return (_ROOT / ".env.example").read_text()

    @pytest.mark.parametrize(
        "key",
        [
            "POSTGRES_DB",
            "POSTGRES_USER",
            "POSTGRES_PASSWORD",
            "POSTGRES_HOST",
            "POSTGRES_PORT",
            "CHROMA_HOST",
            "CHROMA_PORT",
            "OPENROUTER_API_KEY",
            "ALLOWED_HOSTS",
            "DJANGO_SETTINGS_MODULE",
            "REDIS_URL",
            "GF_SECURITY_ADMIN_USER",
            "GF_SECURITY_ADMIN_PASSWORD",
        ],
    )
    def test_key_present(self, env_example_text, key):
        assert key in env_example_text, f"Key {key!r} missing from .env.example"


# ---------------------------------------------------------------------------
# 4. /api/schema/ and /api/docs/ endpoints
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestApiSchema:
    """Assert OpenAPI schema endpoint returns valid spec with expected paths."""

    def test_schema_returns_200(self, client):
        response = client.get("/api/schema/")
        assert response.status_code == 200

    def test_schema_is_openapi(self, client):
        response = client.get("/api/schema/")
        assert response.status_code == 200
        # Schema is returned as YAML by default; parse it
        data = yaml.safe_load(response.content)
        assert "openapi" in data, "Schema missing 'openapi' key"
        assert "paths" in data, "Schema missing 'paths' key"

    def test_schema_includes_chat_query_path(self, client):
        response = client.get("/api/schema/")
        data = yaml.safe_load(response.content)
        paths = data.get("paths", {})
        assert "/api/chat/query/" in paths, (
            f"/api/chat/query/ not in schema paths; found: {list(paths.keys())}"
        )

    def test_schema_includes_document_upload_path(self, client):
        response = client.get("/api/schema/")
        data = yaml.safe_load(response.content)
        paths = data.get("paths", {})
        assert "/api/documents/upload/" in paths, (
            f"/api/documents/upload/ not in schema paths; found: {list(paths.keys())}"
        )

    def test_docs_returns_200(self, client):
        response = client.get("/api/docs/")
        assert response.status_code == 200
