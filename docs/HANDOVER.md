# Handover: where the ExamLeaf work stands and how to resume it

Written 9 October 2026 at the end of a long Claude Code session. Everything below is in this repository on the branch
`design/answer-script` (about 170 commits on top of `main`'s `b3cd16b`, not pushed anywhere). The branch was merged into `main` (fast-forward) and pushed to `origin` (github.com/LazyIndianBook/platform) on 9 October 2026, so `main` holds everything described here. A new person with
their own Claude Code can resume from this file alone: it says what exists, what is verified, what was in flight when the session
ended, what to do next and in which order, and which decisions only the business owner can take.

## 1. The two bodies of work on this branch

1. **The "Answer Script" redesign of the public site** (`examleaf-frontend/`): finished and verified. Report with
   before/after screenshots and numbers: `docs/design/answer-script-implementation.md`. Design sources:
   `implementation/design/*.dc.html`, plan `implementation/README_IMPLEMENTATION.md`.
2. **The Admin Control Panel** (the business's back office): planned in full, Phase A built and merged, Phases B to E
   pending. Plan: `docs/examleaf-admin-control-panel-plan.md` (1,650 lines; sections 9 and 10 are the phases and the
   owner's decisions). Research behind it: `docs/research/2026-10-09-admin-control-panel/` (seven reports, each with a
   numbered sources file; index row in `docs/research/README.md`).

## 2. Components and where each lives

| Directory | What | How to verify |
|---|---|---|
| `examleaf-web/` | Django 6.1 backend: the platform (accounts, content, learn, practice, shop) plus the Phase A apps `staff/`, `shipping/`, `integrations/`, `insights/`, `erp/` | `cd examleaf-web && .venv/bin/python -m pytest -q -p no:cacheprovider` (last runs on the final head: 1,030 passed, 11 skipped on SQLite; 1,040 passed, 1 skipped on PostgreSQL); `ruff check . && ruff format --check .`; `manage.py makemigrations --check` |
| `examleaf-frontend/` | Next.js 16 public site | `npm run lint && npm run format:check && npm run typecheck && npm test` (180 unit tests); Playwright needs the seeded backend (`scripts/e2e-backend.sh`, README "Tests") |
| `examleaf-admin/` | Next.js 16 staff console at `admin.<domain>` | same four commands (62 unit tests); `npx playwright test --project=chromium` in mock mode (`STAFF_API_MOCK=1`) or against a seeded Django (its README) |
| `examleaf-erp/` | ERPNext v16: the private Frappe app `examleaf_erp`, the image build, the dev stack | `cd examleaf-erp/compose && ./dev.sh up && ./dev.sh new-site && ./dev.sh test` (56 tests; needs Docker and about 3 GB RAM); contract in `examleaf-erp/API.md` |
| `deploy/kubernetes/` | Helm umbrella chart `examleaf-platform` (CloudNativePG, Traefik, cert-manager, mariadb-operator and frappe/helm for ERPNext, HA profile, alerts) | `make lint`; `make kind-up && make kind-install` for a one-node test cluster (README.md, TESTING.md records three runs) |
| `examleaf-web/docker-compose.yml` + `Caddyfile` | the simple production deployment (Caddy, web, worker, beat, media-worker, frontend, optional `admin` profile) | `examleaf-web/DEPLOYMENT.md` |

Every app has a README of its own; `examleaf-web/API.md` documents every endpoint (the staff section is generated and a
test fails if it drifts from the code); `examleaf-web/CHANGELOG.md` lists what each piece added; `RUNBOOK.md` the
operations; `DEPLOYMENT.md` the settings table (sections 21 to 24 are the new apps).

## 3. What Phase A delivered (all merged, all tests green at the merge)

- **RBAC and security** (`staff/`): roles in code (`accounts/roles.py`: OWNER, ADMIN, FINANCE, SALES, PACKER, SUPPORT,
  CONTENT_EDITOR, REVIEWER, MARKETING, AUDITOR, SALES_REP; limits and separation-of-duties conflicts), a catalogue of
  action permissions (`staff/catalogue.py`), scopes, approvals bound to a payload hash (`ChangeRequest`), two append-only
  hash-chained audit logs (money events kept 8 financial years) with a PostgreSQL trigger, background `Job`s with
  progress, inbox, saved views, settings and feature flags editable from the panel, API keys, invitations, offboarding,
  access reviews, DPDP queues (data requests with their 48 h and one-month/90-day clocks, incidents with the 6 h CERT-In
  and 72 h Board clocks, processors), notes, policy acknowledgements, impersonation (panel token → website session with
  a banner and refused writes), break-glass sessions with a required reason and a 2-hour limit, Google Workspace sign-in
  with the server-side `hd` check, per-role idle limits (15/30 min) on an 8-hour session, `ADMIN_HOSTS` (staff API and
  `/admin/` answer 404 elsewhere). OWNER is a role; only break-glass accounts are superusers.
- **Staff console** (`examleaf-admin/`): sign-in with two-step and passkeys, manifest-driven navigation, inbox,
  approvals, audit, people, customers with logged reveals, privacy queues, settings, system, jobs; "next phase" pages for
  orders, catalogue, content, course, marketing, partners, support. Reconciliation to the API as built was in flight
  when the session ended (see section 4).
- **Couriers** (`shipping/`, `integrations/`): manual carrier and Shiprocket (recorded double for test mode; live smoke
  test command), tracking webhook `/api/hooks/parcel-events/` plus polling, NDR/RTO, COD remittance and weight-dispute
  reconciliation, India Post tariff fixture, PIN serviceability survey; shared framework for every provider (encrypted
  credentials with MultiFernet key rotation, call log, circuit breaker, dead letters, inbound events).
- **Predictive analytics** (`insights/`): seasonal-naive forecasts with backtests, newsvendor print-run advice, item
  analysis, cohorts (aggregate only: the DPDP Act forbids behavioural monitoring of under-18s), code activation,
  delivery stats, fraud rules, offer effects. Staff enter exam seasons and print costs in the admin.
- **ERPNext** (`examleaf-erp/` and `erp/`): ERPNext v16.50.0 on MariaDB 11.8 (no supported release runs on PostgreSQL;
  revisit at v17), India Compliance for GST, HRMS, offsite backups, the private app with fixtures, five DocTypes, the
  12-method idempotent sync API, GST print formats and a hardening bootstrap; the Django outbox relay, signed doorbell
  webhooks with a 15-minute pull, nightly reconciliation, per-flow flags (all off: shadow mode). Ownership: the platform
  keeps B2C customers (never copied), legal invoice numbers, payments, book codes; ERPNext owns stock and the B2B side.
- **Kubernetes**: the chart tested on kind three times (install, routing, health, body limits, backups, point-in-time
  restore, upgrades, network policies, chaos under load with numbers in `deploy/kubernetes/TESTING.md`), HA profile
  (`values-ha.yaml`: replicas, budgets, autoscaling, PgBouncer pooler, replicated PostgreSQL and MariaDB, advisory-locked
  migrations, 15 Prometheus rules). Not yet run on three real nodes.
- **Backend fixes found on the way**: `/health/` no longer flaps (`examleaf/health.py`); the frontend's health probe
  sends the forwarded host (a 503 bug with DEBUG=0).

## 4. In flight when the session ended

Nothing: every agent branch was merged before the session ended. The last one, the console reconciliation
(`worktree-agent-a7c56ccbd5413ea94`), landed with the frontend resilience behaviour carried into its rewritten files:
generated types from the OpenAPI schema, every call mapped to the staff API as built, the mock regenerated, 87 console
unit tests, 207 website unit tests, Playwright 6/6 in mock mode and 9/9 against a real seeded Django (a refund above the
limit becoming a change request refused to its maker and approved by the owner, the audit trail, invites, a logged
reveal, a data request, a setting, a website sign-in as the customer with a real token and its end, axe at two widths,
the idle sign-out). Not verified end to end: the website's impersonation Playwright spec (the token is now bound to the
panel session that asked for it, so a token made from `manage.py shell` may be refused) and the website band beyond its
unit tests.

All agent worktrees under `.claude/worktrees/` can be removed (`git worktree remove <path>`; their branches are merged):
agent-a009a5704becda5fc, a0f7774fe32d7eeb9, a16ce5a2c3a326b06, a390e0b7103133571, a40021327d34afa3c, a4096b6004b90366f,
a4fd8184097a1d590, a7c56ccbd5413ea94, a7f1f0910b79f7cb6, aa3c9f6cbf68be366, aa730d1f1c1db6cea, ad642f6030a48fd85.

## 5. What to do next, in order (the plan's section 9 has the detail)

1. **Close Phase A**: run every suite once more on `main`; fix the three staff tests' dependence on `DEBUG` if it
   reappears (`STAFF_TEST_MODE` defaults to off under tests); regenerate `openapi.json` and the console's types
   (`manage.py spectacular --file openapi.json`, then `npm run api:types` in `examleaf-admin`); run the console's
   Playwright against a seeded Django; push the branch and open a pull request against `main`.
2. **Operations setup** (needs the owner's accounts): a Shiprocket Lite account with an API user, R2 buckets with bucket
   lock, a Google OAuth client with an Internal consent screen (`STAFF_GOOGLE_*`), `INTEGRATION_KEYS`, `ADMIN_HOSTS`,
   the admin host in `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`, Sentry or GlitchTip, the uptime monitors (`/health/`,
   `/health/integrations/`; basic auth on Kubernetes, the token header on Caddy). First deploy: compose (DEPLOYMENT.md)
   or the chart on a real cluster (deploy/kubernetes/README.md); restore drill; the live Shiprocket smoke test.
3. **Phase B (the panel's own modules)**: staff APIs and console pages for orders, customers, catalogue, content, course,
   marketing, support tickets (the grievance ticket numbers and the 48 h / one-month clocks), partners (distributors,
   schools, teachers with consented class links), reports; the HSN master with dated rates, one document series per type
   with the Table 13 register, billing state at checkout, per-bundle tax treatment, Razorpay settlement fetching
   (`erp/producers.py` has the hook), credit-note quantities, a `returned` order state (decision 10). Each module: the
   plan's capability table in section 5, the role × endpoint matrix test, audit on every change, `ADMIN_HOSTS`.
4. **ERPNext in shadow mode**: build the image (`examleaf-erp/image/build.sh`), deploy ERPNext from the chart (off by
   default: switch it on), create the site and run the bootstrap Job, create the `erp-sync@` API key into the
   integrations account, turn on the `ERP_SYNC_*` flags one at a time, watch `erp_status` and the nightly reconciliation;
   initial load with `erp_initial_load`; cut-over planned for 1 April 2027 (plan 9.3).
5. **Phases C to E**: the plan's sections 9.4 to 9.6 (B2B channel, predictive analytics graduating to statistical
   methods once two seasons exist, the DPDP deadline of 13 May 2027 for verifiable parental consent, access reviews).

## 6. Decisions only the owner can take (plan section 10 has recommendations)

Thresholds (refund caps per role, export and bulk limits: placeholders today in `accounts/roles.py` `ROLE_LIMITS`);
Gyan Post eligibility (ask the Guwahati postal division in writing); the Shiprocket plan; WhatsApp provider (MSG91
recommended; off today); Sentry (US/EU data) or GlitchTip (self-hosted); Tally export or Zoho; whether school and
distributor orders need their own channel; the CA questions (above all the GST treatment of a book sold with a printed
course code; "Exempted" or "Nil-Rated" for HSN 4901; one series or two; who files GSTR-1; the fee's GST; rounding;
returned COD parcels) and the lawyer's (the legal form under E-Commerce Rule 4(1)(a); the children's-data analytics).

## 7. Known gaps and follow-ups (small, deliberate)

- The chart's web readiness stays a static file on purpose (a shared dependency's hiccup must not empty the rotation);
  liveness is `/health/live/`; the pooler carries the statement limits (`query_timeout`, `idle_transaction_timeout`).
- An abandoned break-glass session sends no end alert; the Django admin does not ask the break-glass reason (the panel
  does).
- Shiprocket response shapes marked `_inferred` in `shipping/carriers/fake.py` need checking against a live account.
- `insights` thresholds and weights are starting values; review monthly in season (`insights/README.md`).
- The three-node HA run, autoscaler scaling, synchronous replication and ERPNext on Kubernetes are untested.

## 8. Conventions used, so the history stays consistent

- Commit messages: a subject line saying what changed, then a paragraph on why, in sentences; each ends with a
  `Co-Authored-By:` trailer naming the model that wrote it. Small commits per concern.
- Work in parallel agents was done in git worktrees under `.claude/worktrees/`, each rebased onto the integration branch
  before merging; node_modules were cloned with `cp -Rc` (APFS clonefile) to save disk; builds happened once and `.next`
  was removed.
- Local quirks: Docker here is Colima (`colima ssh -- sudo fstrim -av` shrinks its disk image after `docker system
  prune`); the disk fills quickly with eight agents, so prune often; the backend venv is `examleaf-web/.venv`
  (Python 3.14); a scratch PostgreSQL for the backend suite can be started with `pg_ctl` (DEPLOYMENT.md section 23 has
  the DSN form); ports 3000 to 3041 and 8100 to 8104 were used by dev servers.
- Guardrails kept throughout: the backend decides everything (the console only draws the manifest); no sample values
  shipped; every URL kept; private pages `noindex`; never show PAID before the server confirms; no emoji, gradients,
  glow or blur in the UI; copy as written.
