#!/usr/bin/env bash
# Run the pytest suite with config.settings.test (offline — no real DB/Redis/Chroma).
#
# TEST_SCOPE selects which shard to run so CI can parallelize across jobs:
#   unit | integration | smoke | all   (default: all)
# The tests/conftest.py fixtures (Chroma reset) apply to every shard.

set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-./.venv/bin/python}"
TEST_SCOPE="${TEST_SCOPE:-all}"

case "${TEST_SCOPE}" in
  unit)        TARGETS=(tests/unit) ;;
  integration) TARGETS=(tests/integration) ;;
  smoke)       TARGETS=(tests/smoke) ;;
  all)         TARGETS=(tests) ;;
  *)
    echo "Unsupported TEST_SCOPE: ${TEST_SCOPE}" >&2
    echo "Expected one of: unit, integration, smoke, all" >&2
    exit 1
    ;;
esac

echo "Running pytest (scope=${TEST_SCOPE}): ${TARGETS[*]}"
"${PYTHON_BIN}" -m pytest -q --tb=short "${TARGETS[@]}"
