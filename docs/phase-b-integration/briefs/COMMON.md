# ExamLeaf Phase B: the common brief for every module agent

You are one of several agents building Phase B of the ExamLeaf Admin Control Panel in parallel, each in its own git
worktree (a checkout of `main`). A tech lead merges the worktrees afterwards and runs the final verification. Read this
whole file, then your package file, then the repository documents named below, before writing a line of code. Your
package is the deliverable in full: nothing in it is optional, nothing is "for later" unless your package says so.

## 1. The repository and the plan

- Components: `examleaf-web/` (Django 6.1 backend, Python 3.14, DRF, drf-spectacular), `examleaf-admin/` (Next.js 16
  staff console at admin.<domain>), `examleaf-frontend/` (Next.js 16 public site), `examleaf-erp/` (ERPNext app),
  `deploy/kubernetes/` (Helm), `docs/`.
- The plan: `docs/examleaf-admin-control-panel-plan.md`. Read section 1 (the one rule), 3.5, 3.6, 4, 5.0 (the rules
  across every module), your module's subsections of section 5, section 7's table for your apps, section 9.2 (Phase B:
  scope, exit criteria), section 10.1 (decisions: where the owner has not decided, build the recommendation and say so).
  The research behind each line is in `docs/research/2026-10-09-admin-control-panel/` (read the sections a plan row
  cites when the row is not self-explanatory).
- The state of the code: `docs/HANDOVER.md` sections 2, 3, 7 and 8.
- Backend conventions, read in full: `examleaf-web/staff/README.md` (the model, adding a permission, approvals, the
  audit log, sessions), `examleaf-web/API.md` "Staff API" (and the shipping and erp staff sections as examples),
  `examleaf-web/RESILIENCE.md` (tasks, timeouts, locks), the heads of `examleaf-web/README.md`, `CHANGELOG.md` (the
  style of an entry), `RUNBOOK.md`, `DEPLOYMENT.md`.
- Console conventions, read in full: `examleaf-admin/README.md` (above all "The API boundary", "Design", "Add a
  module", "Tests", "The contract this console speaks"), `examleaf-admin/AGENTS.md` (Next.js 16 differs from your
  training data: read `node_modules/next/dist/docs/` where it says so), and one module end to end as the template:
  `src/app/(panel)/users/`, `src/components/modules/users/`, `src/components/data/`, `src/lib/api/staff.ts`,
  `src/lib/api/page.ts`, `src/lib/modules.ts`, `src/lib/copy.ts`, `src/mocks/staff/`, `e2e/console.spec.ts`,
  `e2e/real.spec.ts`, `e2e/django.ts`.

## 2. The one rule and the guardrails (never break these)

- **The backend decides everything.** Every rule, limit, state transition, permission and approval lives in Django.
  The console draws what the staff API answers and hides only what the session manifest says the person cannot use; it
  decides nothing. A refusal is shown in the API's words.
- Deny by default: every endpoint names a catalogued permission; every GET names a `view_` permission; every staff
  queryset of customer-related rows goes through `scoped()`; high and critical permissions need a recent
  re-authentication (the catalogue's risk does this for you); actions the research marks (money, roles, keys, exports,
  bulk, erasure, prices) go through `staff.approvals` as a `ChangeRequest` bound to the payload's hash; every change
  writes `staff.audit.record(...)` inside the caller's transaction; every refusal is an `authz_fail` (the middleware).
- Personal data: never in audit `details`, inbox titles, labels, logs, filenames or error messages (numbers and codes
  only; `changes` are masked by rule). Every staff view of a customer's record is a `sensitive_read`
  (`staff/api.py` `UserViewSet.retrieve` shows how), a child's record (`is_minor`) too, and so is every lookup of a
  person by name, email or phone (record the query's keyed hash, not the query). Minors never reach a marketing path.
- Test mode kept out of every number: `Order.livemode` (`is_test`) filtered out of every count, every default list and
  every report; the T-series never mixes with the real series; a test row is shown only under the TEST banner.
- No sample values, no invented data, no placeholder content shipped: fixtures only in tests and the console's mock.
- UI: no emoji, gradients, glow or blur; copy as plain sentences; `noindex` on private pages; WCAG 2.2 AA; phones:
  one column, no sideways scroll; targets of at least 24 px; undo (5 s) for the frequent and reversible, a confirm
  dialog for the irreversible, a typed confirmation for the wide or destructive.
- Keep every existing URL, API field and component API: additive changes only, unless your package names a change.
  Do not change behaviour the public site or the app depends on except where your package names it.
- No new dependencies unless your package allows one: the standard library first, then what is installed
  (`requirements.txt`, `package.json`).
- Edge cases are yours to handle, not to list: concurrency (`select_for_update`, idempotency keys), time zones
  (`TIME_ZONE` is Asia/Kolkata; legal clocks run in calendar time across month ends and never pause), retries and
  partial failures, empty states, large lists (pagination, bounded searches, no query per row), the test series,
  deleted or anonymised users (orders with `user=None`), a provider that does not answer.

## 3. Environment and commands

- Python: use the main checkout's virtualenv (it has every requirement; never install into it):
  `PY=/Users/chinmoybhuyan/Desktop/Personal/Book/platform/examleaf-web/.venv/bin/python`. Run everything from your
  worktree's `examleaf-web/` directory: `$PY manage.py ...`; tests `$PY -m pytest -q -p no:cacheprovider <app or
  path>` (SQLite by default; the whole suite takes about 10 minutes: run the apps you touch often, the whole suite
  before you finish); lint `$PY -m ruff check . && $PY -m ruff format .` (format, not only check); migrations
  `$PY manage.py makemigrations --check --dry-run` must print nothing to make.
- Node 20 and npm are on PATH. Give your worktree's console its node_modules by cloning (APFS clonefile: seconds, no
  disk cost): `cp -Rc /Users/chinmoybhuyan/Desktop/Personal/Book/platform/examleaf-admin/node_modules
  <your worktree>/examleaf-admin/node_modules`, and the same from `examleaf-frontend/node_modules` if your package
  touches the public site. Never run `next build` in a worktree. Delete `examleaf-admin/.next` (and the frontend's)
  before you finish. Playwright's browsers are installed already.
- Ports: your package names your Django port and your console port; never use 8100, 8103, 3000 or 3020. Stop every
  server you started before you finish (`lsof -nP -iTCP:<port> -sTCP:LISTEN`).
- Disk is shared and nearly full: no builds, no large downloads, caches removed at the end.
- The contract after backend changes: `$PY manage.py spectacular --format openapi-json --file
  ../examleaf-admin/openapi.json`, then in `examleaf-admin/` `npm run api:types`. API.md's generated reference:
  `$PY manage.py staff_api_reference > /tmp/ref.md` and paste its output between the `<!-- staff-api-reference -->`
  and `<!-- /staff-api-reference -->` markers of `examleaf-web/API.md` (`staff/tests/test_matrix.py` fails otherwise).
- Keep the scratch files out of the repository (nothing under the repo but the deliverable).

## 4. Backend: how things are added here (follow exactly)

- A new action permission: a row in `staff/catalogue.py` `STAFF_ACTIONS` (codename, label, area, risk, approval,
  alert) in a block commented with your module's name at the end of the list → `makemigrations staff` (an
  AlterModelOptions) → give it to the roles in `accounts/roles.py` (the plan's 4.1 says who; ADMIN and OWNER have it
  by rule) → name it on the endpoint's `permissions` map → a row in `staff/tests/test_matrix.py` (`ENDPOINTS` for
  paths under `/api/v1/staff/`, `APP_ENDPOINTS` otherwise) with the object it needs made in `objects()` or
  `app_objects()`. Django's own `view_/add_/change_/delete_` verbs are catalogued by rule; a custom model permission of
  another app (`Meta.permissions`) goes in `catalogue.OTHERS`. The verb's area for a shop model: `SHOP_AREAS`.
- Where your endpoints live: one module file in your app (your package names it) with its own `urlpatterns`, mounted
  in `staff/urls.py` as one line `path("<module>/", include("<app>.<file>"))` placed in alphabetical order of
  `<module>` among such lines (several agents each add one line; keep the diff to that line). Views subclass
  `staff.api.StaffView` (cursor pages, the staff throttle, `coded` errors, `no-store`) with a `StaffSchema` giving the
  tag `"<module> (staff)"` as `erp/api.py` does; explicit serializers (never `fields = "__all__"`); filters with
  django-filter; `scoped(queryset, user, perm)` on every queryset of customer-related rows; `self.human()` for actions a
  key may not do; a per-action throttle scope where the plan asks for one (`throttle_scopes`).
- Approvals: a subclass of `staff.approvals.Action` in your module (validate, rule, run, the maker's and checker's
  permissions), registered in `staff/approvals.py` `ACTIONS` with one import line and one entry (conflicts there are
  expected and resolved at merge). A new numeric limit goes in `accounts/roles.py` `ROLE_LIMITS` and `LIMITS`.
- Background work: a `Job.Kind` value (`staff/models.py`), a runner in your app registered in `staff/jobs.py`
  `RUNNERS` (one import, one line) with its permission in `jobs.permission`; progress through `Progress`; result files
  in the private storage through the existing result link. Bulk actions above `bulk_rows` and exports above
  `export_rows` already wait for approval (`job.run`); a dry run first where the plan says so.
- Inbox: `staff.signals.open_item(kind, target, title, permission, due_at=..., **data)` and
  `close_items(target, kind)` (import them; do not duplicate); a new kind in `InboxItem.Kind`; titles name no person.
- Periodic jobs: a Celery task in your app's `tasks.py` on the `examleaf.celery.Task` rules (RESILIENCE.md: the
  `single_run` lock for anything that sends or alerts, idempotent on a second delivery, time limits by kind), one
  entry in `CELERY_BEAT_SCHEDULE` (append to the dict with `|=` in a block for your module in `examleaf/settings.py`),
  and a management command where RUNBOOK needs one.
- Settings: new environment settings in a commented block for your module in `examleaf/settings.py`, documented in
  `DEPLOYMENT.md`'s table and `.env.example`; switches staff change from the panel through `staff/config.py`
  `SETTINGS` with their permission (and `site_setting()` where the code reads them).
- History: `simple_history.HistoricalRecords()` where the plan says history; diffs through `diff_against`.
- Models: new models at the END of the app's `models.py` under one comment line `# Phase B: <module>`; new fields on
  an existing model at the end of its field list under the same comment; migrations named `00NN_phase_b_<module>.py`
  (a merge migration is made at integration; never edit an existing migration). Keep the deletion rules the existing
  models keep (tax records PROTECT, orders never deleted, a deleted user leaves `user=None`).
- Money: `djmoney` fields as the shop uses them, `rupees()` rounding to the paisa, Decimal everywhere, never float.
- Customer messages: through `shop.services.notify` and `ops.sms` (templates under `templates/`), never between
  21:00 and 08:00 IST (the SMS module holds them), never marketing, never to a minor's number for anything but
  service.
- Tests: pytest; the helpers of `staff/tests/conftest.py` (`make_staff`, `signed_in`, `events`), the factories of
  `accounts/factories.py` and `shop/factories.py`; every endpoint in the matrix; one test per rule your package's exit
  criteria name; a query-count test on each list (the pattern of `shop/test_query_counts.py`); tests that also pass on
  PostgreSQL (no SQLite-only SQL; dates through Django's functions; no reliance on insertion order without ordering).
- The Django admin stays for superusers: register new models minimally (read-only where the panel owns the flow). Do
  not build new admin screens.

## 5. Console: how a module is added here (follow exactly)

- Regenerate `openapi.json` and `schema.d.ts` from your backend; calls in `src/lib/api/staff.ts` through
  `api.GET/POST/…` on the generated paths (append a section `// ---- <Module> ----` at the end of the file);
  permissions in `P` and the module's entry in `MODULES` (`src/lib/modules.ts`: replace its `soon: true` entry in
  place and keep the plan's order; a new module goes where section 8 puts it); words in `src/lib/copy.ts` under one
  new top-level key named after your module, appended at the end of the object (British English, plain sentences, no
  exclamation marks, success toasts of three words or fewer).
- Pages under `src/app/(panel)/<module>/…` (server components: `staffPage(path)`, `attempt()`, `metadata` from the
  copy; `notFound()` for what the manifest does not open), interactive parts in `src/components/modules/<module>/`.
  Lists through `DataTable` (filters in the URL, saved views as tabs with your module's `list_key`, columns that stack
  on phones, the whole row a click target, the three empty states), records through `RecordPage` with `recordSide()`
  (notes and the audit trail), forms through `ActionForm`/`useAction` (one send, the API's field errors, the save bar
  and the leave warning), `ConfirmDialog`/`ConfirmTyped` for the dangerous, `JobProgress` for jobs, `ApprovalNotice`
  for a 202, `MaskedValue` for masked contact details.
- The mock (`src/mocks/staff/fixtures.ts`, `handler.ts`): every path your pages call, every state they draw, typed from
  the schema, the backend's rules kept (permission, re-authentication, limits, 404); a Vitest test for each component
  with logic; one journey through your module added to `e2e/console.spec.ts` (mock mode) and, where your package says
  so, to `e2e/real.spec.ts` with its seed in `e2e/django.ts`.
- Checks that must pass before you finish: `npm run lint && npm run format:check && npm run typecheck && npm test`,
  then `E2E_WEB_PORT=<your console port> E2E_API_PORT=<your Django port> npx playwright test --project=chromium`
  (mock mode; it starts `next dev` and Django itself).

## 6. Documentation (part of done)

- `examleaf-web/API.md`: the generated reference (section 3) and a prose section for your module in the style of
  "Shipping (staff)" placed before the generated reference.
- `examleaf-web/CHANGELOG.md`: prepend one entry under the heading `## Phase B, <module> (9 October 2026)` right after
  the file's introductory paragraph, in the file's style (what changed and why, the test counts at your end).
- `examleaf-web/README.md` (the module's place in the feature list), your app's README (a new `<app>/README.md` in the
  style of `staff/README.md` for a new app; a section in the existing one otherwise), `RUNBOOK.md` (replace the shell
  recipes your module makes unnecessary with the panel action, keeping the shell as the break-glass fallback),
  `DEPLOYMENT.md` (new settings in the table), `staff/README.md` (new approval actions in its table, new job kinds).
- `examleaf-admin/README.md`: the route list and "The contract this console speaks" gain your module.
- The one-page guide per role is not yours (a later agent writes them), but say in your app's README what your
  module's pages do for each role.

## 7. Working method and finishing

- Work on your worktree's branch only; commit in small commits per concern, each with a subject line saying what
  changed and a paragraph saying why, in sentences; end every commit message with the trailer
  `Co-Authored-By: <your model name> <noreply@anthropic.com>` (Claude Opus 5.5 or Claude Sonnet 5.5, whichever you
  are). Never merge, rebase, push, or touch `main` or another worktree.
- Do the whole package. Where the plan leaves a decision to the owner, build section 10.1's recommendation and name the
  decision in your report. Where something is genuinely blocked (an external account, a legal answer), build everything
  around it, make the blocked part a documented setting or a clearly labelled "not configured" state, and say so.
- Before finishing: the whole backend suite green on SQLite, ruff clean, migrations clean, API.md regenerated,
  openapi.json and schema.d.ts regenerated, the console's four checks and the mock Playwright green, `.next` removed,
  servers stopped, everything committed (`git status` clean).
- Your final message is your report, and the tech lead reads only it: what you built (models, endpoints with their
  permissions, pages, jobs, settings, tasks), what you verified (commands and counts), what you left out and why,
  decisions taken on the owner's behalf, what other modules should know (new signals, fields, inbox kinds, services),
  and the list of shared files you changed (`catalogue.py`, `roles.py`, `approvals.py`, `jobs.py`, `staff/models.py`
  kinds, `settings.py`, `test_matrix.py`, `staff/urls.py`, `modules.ts`, `copy.ts`, `staff.ts`, `fixtures.ts`,
  `handler.ts`, `console.spec.ts`, `real.spec.ts`, CHANGELOG, API.md). Keep the report under 1,500 words.
