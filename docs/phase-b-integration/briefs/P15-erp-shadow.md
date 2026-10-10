# Package P15: ERPNext in shadow mode on the dev stack (model: Claude Opus 5.5)

Ports: Django 8123; ERPNext's stack on 8300 (its compose: `examleaf-erp/compose/`). Docker here is Colima (running).
Read COMMON.md sections 1 to 4 and 7 first, then `examleaf-web/erp/README.md` in full (above all "Shadow mode and
the cut-over" and the local-stack section at its end), `examleaf-erp/README.md` and `API.md`, `examleaf-erp/compose/dev.sh`
and `compose.yaml`, `deploy/kubernetes/TESTING.md` (the style of a recorded run), plan sections 3.2, 7.5, 9.2
(the exit criteria: "the outbox idempotent (one event sent twice makes one ERPNext document) and the reconciliation
finding a difference planted on staging") and 9.3. Your worktree is a checkout of `phase-b` with every module merged.

The deliverable is a recorded shadow run of the platform's `erp` app against a real ERPNext (the dev stack standing
in for the staging site), with every gap found fixed in the code, and the record in `examleaf-web/erp/SHADOW-RUN.md`
(plus a pointer from `erp/README.md` and `docs/HANDOVER.md` section 3's ERPNext line).

1. **The stack**: `cd examleaf-erp/compose && ./dev.sh up && ./dev.sh new-site && ./dev.sh test` (the 56 tests of
   `examleaf_erp` must pass on this head: fix the app if the platform's contract moved), then `./dev.sh keys` for
   the sync user's key. Memory: the script waits for 3 GB free; do not start it while that is not there (say so
   and wait). Disk: `docker system df` before and after; prune the build cache at the end (`docker builder prune -f`),
   keep the images.
2. **The platform in shadow**: a SQLite database of your own (`DATABASE_URL=sqlite:////…/shadow.sqlite3`),
   `ERP_MODE=erpnext`, `ERP_ENABLED=1`, the site's URL and the key as `erp/README.md` says (an IntegrationAccount
   row of provider `erpnext` or the settings: read which), `examleaf_allow_test_series` on the site so the T-series
   is accepted, a Celery worker and beat in eager or real mode as the README's local section says (a real worker
   against the local Redis at 6379 is fine: it is running on this Mac), the flows switched on one at a time
   through the panel's flags (`manage.py` or the staff API with a member you make: catalogue, invoices, payments,
   deliveries, settlements) as the README's shadow-mode steps say, `ERP_PULL_STOCK` and `ERP_PULL_B2B` on.
3. **The run**, each step recorded with the command, the ERPNext document names and the platform's rows:
   - the initial load (`erp_initial_load`) of the catalogue: items and bundles in ERPNext with `examleaf_ref`;
   - a test order placed and paid through the shop's services (the T-series invoice), a parcel dispatched by hand,
     a refund with its credit note: the mirrored Sales Invoice, Payment Entry, Delivery Note and return invoice under
     the platform's numbers; `erp_status` after each;
   - **idempotency**: the same outbox event relayed twice (`erp_replay` on a sent row, or a forced second delivery of
     the task) makes one ERPNext document and the second attempt is recorded as such; a second order with the same
     number refused by ERPNext as the contract says;
   - a doorbell: a stock entry made in ERPNext (a receipt into `Main`) reaches `/api/hooks/erp-events/` (point the
     site's `examleaf_webhook_base` at the Django server) and the pull reads the stock back into the projection;
   - **the planted difference**: change a mirrored invoice's grand total in ERPNext (through the Desk or
     `bench --site erp.localhost execute` / `frappe.db.set_value`), run `erp_reconcile` for the day, and show the
     difference row, its inbox item and its resolution through the panel's endpoint;
   - a dead letter: an event ERPNext refuses for good (a payload the contract rejects, made on purpose), its inbox
     item, replay after the fix and discard with a reason;
   - the rollback by flag: a flow switched off, events waiting as pending, switched on, events replayed, no
     duplicates;
   - the nightly reconciliation's `daily_totals` matching on a clean day (the 0.01 tolerance of the rounding question
     noted).
4. **Fix what breaks** on the platform side (`erp/`, `examleaf-erp/apps/examleaf_erp/`): contract drift, a payload
   the real ERPNext refuses, a status the pull does not map, a race between the doorbell and the relay. Every fix
   with a test against the fake (`erp/tests/`) or the Frappe app's tests. Keep `erp/contract.py` the one place of
   names.
5. **Record** in `erp/SHADOW-RUN.md`: the versions, the commands, each step's result, the numbers (events relayed,
   documents made, the second-delivery outcome, the difference found, the time each step took), what failed and the
   fix's commit, and what the real staging site will need beyond this (the Kubernetes Job for the bootstrap, the
   integration user's `restrict_ip`, the webhook base over the cluster network).
6. **Tear down**: `./dev.sh down` (keep the volumes if the disk allows, so the next run is quick; say which); stop
   the worker and Django; delete the shadow database.

Commit per fix with the `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` trailer. Your report: the run's
outcome per step, the fixes, what remains for the real staging site, and resource use (memory, disk, time).
