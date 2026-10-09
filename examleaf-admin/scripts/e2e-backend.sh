#!/usr/bin/env sh
# The Django backend for the console's Playwright tests (playwright.config.ts starts it when none is running): only
# sign-in is real while the staff API is the mock (STAFF_API_MOCK=1), so the database needs its tables and the role
# groups, nothing else. Emails print to the log. Runs from examleaf-web/, on DATABASE_URL (the config's default is a
# SQLite file of its own under .e2e/, never the development database).
set -eu
cd "$(dirname "$0")/../../examleaf-web"
PY="${DJANGO_PYTHON:-python}"
LOG="${DJANGO_LOG:?set DJANGO_LOG}"
mkdir -p "$(dirname "$LOG")"

$PY manage.py migrate --noinput
$PY manage.py bootstrap_roles
exec $PY manage.py runserver "${DJANGO_PORT:-8103}" --noreload >"$LOG" 2>&1
