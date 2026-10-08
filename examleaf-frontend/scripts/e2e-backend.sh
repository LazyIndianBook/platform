#!/usr/bin/env sh
# The Django backend for the Playwright smoke tests (playwright.config.ts starts it; CI too): a fresh database with
# the four books' papers, the shop's starting catalogue and an open sample paper, email and SMS printed to the log
# (the tests read the codes there), the frontend's origin trusted. Runs from the repository's examleaf-web/.
set -eu
cd "$(dirname "$0")/../../examleaf-web"
PY="${DJANGO_PYTHON:-python}"
LOG="${DJANGO_LOG:?set DJANGO_LOG}"
mkdir -p "$(dirname "$LOG")"

$PY manage.py migrate --noinput
$PY manage.py bootstrap_roles
$PY manage.py import_papers --all
$PY manage.py seed_shop
# a fresh database has no open sample yet (content migration 0002 marks them only for papers that existed then)
$PY manage.py shell -c "from content.models import Paper; Paper.objects.filter(code='PHY-E01').update(is_sample=True)"
exec $PY manage.py runserver "${DJANGO_PORT:-8100}" --noreload >"$LOG" 2>&1
