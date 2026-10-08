#!/bin/zsh
# Baseline runner: every command is timed and logged. No edits to the project tree (ruff --no-cache, no pytest cache).
cd "/Users/chinmoybhuyan/Desktop/Personal/Book/Class 12/examleaf-web" || exit 1
L=${0:A:h}/logs; mkdir -p $L
PY=.venv/bin/python
date -u +"%Y-%m-%dT%H:%M:%SZ" > $L/started.txt
git -C .. status --porcelain | wc -l | tr -d ' ' > $L/uncommitted-at-start.txt

run() {  # name, command...
  local name=$1; shift
  local t0=$EPOCHREALTIME
  "$@" > $L/$name.out 2> $L/$name.err
  local rc=$?
  local t1=$EPOCHREALTIME
  printf '%s\t%s\t%.2f\n' "$name" "$rc" "$((t1 - t0))" >> $L/summary.tsv
}
zmodload zsh/datetime
: > $L/summary.tsv

run pytest $PY -m pytest -q -p no:cacheprovider
run ruff-check .venv/bin/ruff check --no-cache .
run ruff-format .venv/bin/ruff format --no-cache --check .

DEPLOY_KEY=$($PY -c "import secrets,string; a=string.ascii_letters+string.digits; print(''.join(secrets.choice(a) for _ in range(50)))")
run check-deploy env DEBUG=0 SECRET_KEY=$DEPLOY_KEY ALLOWED_HOSTS=examleaf.in SITE_URL=https://examleaf.in EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend $PY manage.py check --deploy
run makemigrations $PY manage.py makemigrations --check --dry-run
run spectacular $PY manage.py spectacular --validate --fail-on-warn --file /dev/null
git -C .. status --porcelain | wc -l | tr -d ' ' > $L/uncommitted-at-end.txt
date -u +"%Y-%m-%dT%H:%M:%SZ" > $L/finished.txt
