#!/usr/bin/env bash
# The ERPNext development stack (compose.yaml): ./dev.sh up | new-site | test [run-tests args] | restart | login | keys |
# shell | bench <args> | down | destroy. The site is erp.localhost, served on http://127.0.0.1:8300 (README "Local setup").
set -euo pipefail
cd "$(dirname "$0")"

SITE=erp.localhost
NEED_MB=${NEED_MB:-3072}   # free + inactive memory to ask for before starting (the stack takes about 1.5 GB)
WAIT_MINUTES=${WAIT_MINUTES:-20}
MINIMAL=(db cache queue configurator backend websocket frontend)  # nginx needs the websocket host

compose() { docker compose --env-file .env "$@"; }
bench() { compose exec -T backend bench "$@"; }

ensure_env() {
  [[ -f .env ]] && return
  local db admin
  db=$(openssl rand -hex 16)
  admin=$(openssl rand -hex 16)
  sed -e "s/^DB_ROOT_PASSWORD=.*/DB_ROOT_PASSWORD=$db/" -e "s/^ADMIN_PASSWORD=.*/ADMIN_PASSWORD=$admin/" .env.example >.env
  chmod 600 .env
  echo "Made compose/.env with random dev passwords (Administrator's is ADMIN_PASSWORD there)."
}

available_mb() {
  if command -v vm_stat >/dev/null; then  # macOS: free + inactive + speculative pages
    vm_stat | awk '/page size of/ {size = $8} /Pages (free|inactive|speculative)/ {gsub(/\./, "", $NF); pages += $NF}
      END {print int(pages * size / 1048576)}'
  else
    awk '/MemAvailable/ {print int($2 / 1024)}' /proc/meminfo
  fi
}

wait_for_memory() {
  local waited=0 have
  while have=$(available_mb); ((have < NEED_MB)); do
    if ((waited >= WAIT_MINUTES)); then
      echo "Only ${have} MB free after ${WAIT_MINUTES} minutes (want ${NEED_MB}): not starting." >&2
      exit 1
    fi
    echo "Only ${have} MB free, want ${NEED_MB}: waiting a minute (${waited}/${WAIT_MINUTES})."
    sleep 60
    waited=$((waited + 1))
  done
  echo "${have} MB free."
}

case "${1:-}" in
  up)
    ensure_env
    wait_for_memory
    compose build backend
    if [[ "${2:-}" == "--minimal" ]]; then compose up -d "${MINIMAL[@]}"; else compose up -d; fi
    ;;
  new-site)
    # each step is skipped when already done, so a failed run can be started again
    ensure_env
    # shellcheck disable=SC1091
    source .env
    if ! compose exec -T backend test -f "sites/$SITE/site_config.json"; then
      bench new-site "$SITE" --db-type mariadb --mariadb-user-host-login-scope='%' \
        --db-root-username root --db-root-password "$DB_ROOT_PASSWORD" --admin-password "$ADMIN_PASSWORD" \
        --install-app erpnext --install-app india_compliance --set-default
    fi
    # the placeholders of site_config.example.json (no secrets: empty values are left out), the test series and the
    # test runner allowed (this is a development site), then the app and the company
    compose exec -T backend env/bin/python -c '
import json, sys
path = "sites/'"$SITE"'/site_config.json"
config = json.load(open(path))
config.update({key: value for key, value in json.load(sys.stdin).items() if value not in ("", None, 0)})
config.update({"examleaf_allow_test_series": 1, "allow_tests": True})
json.dump(config, open(path, "w"), indent=1)
' <site_config.example.json
    if ! bench --site "$SITE" list-apps | grep -q '^examleaf_erp'; then
      bench --site "$SITE" install-app examleaf_erp
    fi
    bench --site "$SITE" execute examleaf_erp.setup.bootstrap
    ;;
  test)
    shift
    bench --site "$SITE" run-tests --app examleaf_erp "$@"
    ;;
  keys)
    # API key and secret of the sync user, for curl on this machine only: kept in compose/.sync-keys (gitignored)
    user=$(python3 -c 'import json; print(json.load(open("site_config.example.json"))["examleaf_sync_user"])')
    bench --site "$SITE" execute frappe.core.doctype.user.user.generate_keys --args "['$user']" |
      python3 -c 'import json, sys; d = json.loads(sys.stdin.read().strip().splitlines()[-1]); print(d["api_key"] + ":" + d["api_secret"])' >.sync-keys
    chmod 600 .sync-keys
    echo "Wrote compose/.sync-keys (token for: Authorization: token \$(cat compose/.sync-keys))."
    ;;
  login)
    # a Desk session for Administrator, who holds every role and so signs in with two factors; the first two-factor
    # sign-in emails the authenticator's set-up, and this stack sends no email. In a container of its own: browse
    # leaves an xdg-open behind, and in the backend gunicorn would reap its exit code 3 as a worker that failed to boot.
    compose run --rm --no-deps -T backend bench --site "$SITE" browse --user Administrator 2>/dev/null |
      sed -n 's|^Login URL: .*\(/app?sid=.*\)$|http://127.0.0.1:8300\1|p'
    ;;
  restart) compose restart backend scheduler queue-short queue-default queue-long ;;  # they load Python code once
  shell) compose exec backend bash ;;
  bench) shift; bench "$@" ;;
  down) compose down ;;
  destroy) compose down -v ;;
  *)
    echo "usage: ./dev.sh up [--minimal] | new-site | test [args] | restart | login | keys | shell | bench <args> | down | destroy" >&2
    exit 2
    ;;
esac
