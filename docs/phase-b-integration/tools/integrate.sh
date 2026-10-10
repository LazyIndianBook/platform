#!/usr/bin/env bash
# Integration helper for Phase B (run from the platform repo root on the phase-b branch).
#   integrate.sh merge <branch>      merge an agent branch (no-ff); stops on conflicts for manual resolution
#   integrate.sh regen               merge migrations if needed, API.md reference, openapi.json, schema.d.ts
#   integrate.sh check               ruff, makemigrations --check, backend suite (SQLite), console checks
#   integrate.sh pg                  backend suite on the local PostgreSQL 17
set -euo pipefail
ROOT=/Users/chinmoybhuyan/Desktop/Personal/Book/platform
PY=$ROOT/examleaf-web/.venv/bin/python
cd "$ROOT"

case "${1:-}" in
  merge)
    git merge --no-ff --no-edit "$2" || { echo "CONFLICTS:"; git diff --name-only --diff-filter=U; exit 2; }
    ;;
  regen)
    cd examleaf-web
    $PY manage.py makemigrations --check --dry-run >/dev/null 2>&1 || $PY manage.py makemigrations --merge --noinput
    $PY manage.py makemigrations --check --dry-run
    $PY manage.py staff_api_reference > /tmp/staff-ref.md
    $PY - <<'EOF'
from pathlib import Path
text = Path("API.md").read_text()
start, end = "<!-- staff-api-reference -->\n", "<!-- /staff-api-reference -->"
a, b = text.index(start) + len(start), text.index(end)
Path("API.md").write_text(text[:a] + Path("/tmp/staff-ref.md").read_text() + text[b:])
print("API.md reference regenerated")
EOF
    $PY manage.py spectacular --format openapi-json --file ../examleaf-admin/openapi.json
    cd ../examleaf-admin && npm run -s api:types && npx -s prettier --write openapi.json src/lib/api/schema.d.ts >/dev/null
    echo "openapi.json and schema.d.ts regenerated"
    ;;
  check)
    cd examleaf-web
    $PY -m ruff check . && $PY -m ruff format --check .
    $PY manage.py makemigrations --check --dry-run
    $PY -m pytest -q -p no:cacheprovider -x --no-header 2>&1 | tail -3
    cd ../examleaf-admin && npm run -s lint && npm run -s format:check && npm run -s typecheck && npm test -- --run 2>&1 | tail -4
    ;;
  pg)
    createdb examleaf_phaseb 2>/dev/null || true
    cd examleaf-web
    DATABASE_URL=postgres://chinmoybhuyan@localhost:5432/examleaf_phaseb $PY -m pytest -q -p no:cacheprovider --no-header 2>&1 | tail -3
    ;;
  *) echo "usage: integrate.sh merge <branch> | regen | check | pg"; exit 1 ;;
esac
