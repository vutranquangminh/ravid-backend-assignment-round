#!/usr/bin/env bash
# Run any command with .env.local loaded into the environment.
# Usage: scripts/dev/run_local.sh <cmd...>
#   e.g. scripts/dev/run_local.sh .venv/bin/python manage.py migrate
set -euo pipefail
cd "$(dirname "$0")/../.."
if [[ ! -f .env.local ]]; then echo ".env.local not found"; exit 1; fi
set -a
eval "$(python3 -c '
import shlex, pathlib
for l in pathlib.Path(".env.local").read_text().splitlines():
    l=l.strip()
    if l and not l.startswith("#") and "=" in l:
        k,v=l.split("=",1); print(f"export {k}={shlex.quote(v)}")
')"
set +a
exec "$@"
