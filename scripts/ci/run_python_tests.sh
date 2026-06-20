#!/usr/bin/env bash
# Run the full pytest suite with config.settings.test.
# All tests must pass offline (no real DB/Redis/Chroma).

set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-./.venv/bin/python}"

"${PYTHON_BIN}" -m pytest -q --tb=short
