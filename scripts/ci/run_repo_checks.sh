#!/usr/bin/env bash
# Repo-level checks: lint, validate agents, manage.py check, compose config,
# and observability file existence.

set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-./.venv/bin/python}"

# ── 1. Ruff lint ─────────────────────────────────────────────────────────────
"${PYTHON_BIN}" -m ruff check apps/ tests/ config/

# ── 2. Agent / assessment validation ─────────────────────────────────────────
"${PYTHON_BIN}" .agents/scripts/validate_agents.py
"${PYTHON_BIN}" .agents/scripts/check_assessment_coverage.py

# ── 3. Django system check (test settings — no DB/Redis/Chroma needed) ───────
"${PYTHON_BIN}" manage.py check --settings=config.settings.test

# ── 4. Compose file syntax ────────────────────────────────────────────────────
docker compose -f compose.ci.yaml config --quiet
docker compose -f compose.yaml config --quiet

# ── 5. Observability file existence ───────────────────────────────────────────
required_observability_files=(
  "docker/alloy/config.alloy"
  "docker/loki/config.yaml"
  "docker/grafana/provisioning/datasources/loki.yaml"
  "docker/grafana/provisioning/dashboards/observability.yaml"
  "docker/grafana/dashboards/overview.json"
)

for file_path in "${required_observability_files[@]}"; do
  if [[ ! -f "${file_path}" ]]; then
    echo "Missing required observability file: ${file_path}" >&2
    exit 1
  fi
done

# ── 6. Validate Grafana dashboard JSON ────────────────────────────────────────
"${PYTHON_BIN}" -m json.tool docker/grafana/dashboards/overview.json >/dev/null

"${PYTHON_BIN}" - <<'PY'
import json
from pathlib import Path

dashboard_path = Path("docker/grafana/dashboards/overview.json")
dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))

service_var = next(
    (
        item
        for item in dashboard.get("templating", {}).get("list", [])
        if item.get("name") == "service"
    ),
    None,
)

if not service_var:
    raise SystemExit("Missing Grafana service template variable in dashboard JSON")

all_value = service_var.get("allValue")
if not all_value or all_value in {".*", "^.*$"}:
    raise SystemExit(
        "Grafana service variable allValue must not be empty-compatible ('.*')."
    )

current_value = service_var.get("current", {}).get("value")
if current_value in {".*", "^.*$"}:
    raise SystemExit(
        "Grafana service variable current.value must not be empty-compatible ('.*')."
    )

panel_exprs: list[str] = []
for panel in dashboard.get("panels", []):
    for target in panel.get("targets", []):
        expr = target.get("expr")
        if isinstance(expr, str):
            panel_exprs.append(expr)

bad_exprs = [expr for expr in panel_exprs if 'service=~".*"' in expr]
if bad_exprs:
    raise SystemExit(
        "Dashboard contains Loki queries with empty-compatible matcher 'service=~\".*\"'."
    )

print("Grafana dashboard validation passed.")
PY

echo "All repo checks passed."
