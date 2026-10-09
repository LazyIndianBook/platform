# ExamLeaf admin console

The staff console of ExamLeaf's Admin Control Panel (`docs/examleaf-admin-control-panel-plan.md`), served at
`admin.examleaf.in`: the product side that ERPNext cannot see (customers and their consent, the data-rights queue and
the breach register, staff roles and scopes, approvals, the audit trail, settings and feature flags, the system's
health), with deep links into ERPNext for money, tax, stock, purchases and CRM. Next.js 16 (App Router, Turbopack),
React 19, TypeScript strict, Tailwind CSS 4, the public site's toolchain, token layer and design-system kit.

**The one rule: the backend decides.** Every button calls the staff API (`/api/v1/staff/`, examleaf-web's `staff`
app), which checks the person's role, capability and scope, writes an audit event and answers with the truth. The
console draws what the API answers. The only thing it does with permissions is hide what the session manifest says the
person cannot use (a module, a button); it never decides anything else on its own, and a refusal from the API is shown
in the API's words.

## Local setup

1. Django from `../examleaf-web/` (its README), on port 8103, trusting the console's origin:

   ```sh
   DEBUG=1 SITE_URL=http://localhost:3020 CSRF_TRUSTED_ORIGINS=http://localhost:3020 USE_X_FORWARDED_HOST=1 \
     INTERNAL_API_TOKEN=dev-token .venv/bin/python manage.py runserver 8103
   ```

   On SQLite add `DATABASE_URL='sqlite:////<path>/db.sqlite3?transaction_mode=IMMEDIATE&timeout=20'` (allauth's device
   list writes on every signed-in request). Run `manage.py bootstrap_roles` once (the role groups and their
   permissions). A member of staff needs `is_staff`, a role (`staff/README.md`: `RoleGrant`, or `manage.py shell` as
   `e2e/django.ts` does) and an authenticator app or a passkey; `e2e/django.ts` makes them with a known TOTP secret.

2. The console:

   ```sh
   cp .env.example .env.local     # API_INTERNAL_BASE=http://localhost:8103, the same INTERNAL_API_TOKEN
   npm install
   npm run dev                    # http://localhost:3020
   ```

   Open http://localhost:3020 only: the browser must stay on one origin for the session and CSRF cookies.
   `src/proxy.ts` passes Django's paths (`/api/v1/`, `/_allauth/`, `/static/`, `/admin/` … the public site's list in
   `src/lib/site.ts`) to `API_INTERNAL_BASE` in development; Caddy does it in production. Cookies do not separate by
   port: signing in on the public site's dev server (3000) signs in here too. In production the two hosts keep their
   own (host-only) cookies.

### Mock mode

`STAFF_API_MOCK=1 npm run dev` answers every staff API path from the deterministic fixtures of `src/mocks/staff/`,
typed from the same generated schema as the real calls (`fixtures.ts`, `handler.ts`): `src/proxy.ts` rewrites the
browser's `/api/v1/staff/…` to the route handler `src/app/api/mock/staff/[...path]/`, and server components call the
handler in the same process. It is for working on a screen quickly and for the states a fresh database does not have:
change requests in every state (pending, approved, rejected, expired, executed, failed), jobs queued,
running, done, failed and cancelled, an overdue inbox, a data request near its clock, an incident's 6-hour clock, a
scheduled setting, revoked API keys, a person who left. Signing in stays real: each mock request asks the Django
backend whose session cookie it carries who is signed in (`GET /api/v1/me/`: 401 signed out, 403 `mfa_setup_required`
for staff without two-step sign-in, the role groups otherwise), "confirm it's you" reads allauth's own record of the
last authentication, the CSRF token is checked as Django checks it, actions write audit events, and the backend's
second-person rules make change requests. Each staff member gets a world of their own, changed by what they do.

Dev-only cookies change what it answers: `staff_mock_role=SUPPORT` (another role's permissions),
`staff_mock_reauth_after=<epoch seconds>` (an older authentication counts as stale), `staff_mock_break_glass=1` (a
break-glass session that owes its reason), `staff_mock_policies=1` (a policy to acknowledge). `next.config.ts` sets the
flag only under `next dev`: every build compiles it to "", so a production bundle cannot reach a fixture (the route
throws and the import sits behind the same check).

## Environment

| Variable                  | Where   | What                                                                                       |
| ------------------------- | ------- | ------------------------------------------------------------------------------------------ |
| `NEXT_PUBLIC_SITE_URL`    | build   | the console's own address (`https://admin.examleaf.in`), the host Django sees              |
| `NEXT_PUBLIC_WEBSITE_URL` | build   | the public website: two-step sign-in and passkeys, and the impersonation link's address    |
| `NEXT_PUBLIC_ERP_URL`     | build   | ERPNext's desk, for the business modules' links; empty: none are drawn                     |
| `API_INTERNAL_BASE`       | runtime | Django for server components (`http://web:8000` in compose)                                |
| `INTERNAL_API_TOKEN`      | runtime | the secret shared with Django: Django then counts each person's address, not this server's |
| `API_INTERNAL_TIMEOUT_MS` | runtime | how long a request may wait on Django in all (default 10000), then "can't be reached"      |
| `NODE_OPTIONS`            | runtime | the image gives `--max-old-space-size=384` for a 512 MiB memory limit (RESILIENCE.md)      |
| `KEEP_ALIVE_TIMEOUT`      | runtime | the image gives 125000 ms: longer than a proxy keeps an idle connection                    |
| `STAFF_API_MOCK`          | dev     | `1`: the staff API from fixtures (`next dev` only)                                         |

No `NEXT_PUBLIC_` value is a secret. Sign-in methods come from `GET /api/v1/config/` (Google), never hard-coded.

## The API boundary

- **`src/lib/api/staff.ts` holds every staff call**, through `openapi-fetch` typed by the backend's own schema:
  `openapi.json` (committed) and `src/lib/api/schema.d.ts` generated from it. Paths, query parameters, bodies and
  answers come from `paths` and `components`, so a backend rename is a type error in staff.ts and in every page that
  reads the field. Nothing is typed by hand but the manifest's `policies_due`, which the schema gives as a map
  (`{policy, version}`). To regenerate, from `../examleaf-web/`:

  ```sh
  .venv/bin/python manage.py spectacular --format openapi-json --file ../examleaf-admin/openapi.json --validate --fail-on-warn
  cd ../examleaf-admin && npm run api:types && npm run typecheck
  ```

  (`npm run api:snapshot` saves the same file from a running backend's `/api/schema/`.)

- **The same function, two places.** Server components pass `await staffTransport()` (`src/lib/api/server.ts`): Django
  over the internal network with the person's cookies, address and browser, never cached, and no credential of the
  server's own. In the browser the transport is left out: same origin, the CSRF token from the `csrftoken` cookie on
  every change, and the browser's reactions (`src/lib/api/client.ts`).
- **Answers the console acts on** (`src/lib/api/errors.ts`, codes as the backend sends them):
  - 401 `session_idle` or `session_expired`: the sign-in page says it was the idle limit or the 8 hours, and what was
    typed stays in sessionStorage (`useDraftForm`) for the way back; any other 401 signs in and back.
  - 403 `reauthentication_required`: "Confirm it's you" (allauth's reauthenticate flows from the answer: the
    authenticator's code, the password, a passkey), then the call once more with the same `Idempotency-Key`.
  - 403 `permission_denied` or `break_glass_reason_required`: the page is rendered again from the server, which reads
    the manifest afresh (and so asks a break-glass session for its reason). `mfa_setup_required` sends to the
    website's two-step set-up. `impersonating` says the session is a customer's impersonation and what it may not do.
  - A refused Google sign-in comes back to `/sign-in/?error=…` and says why: `staff_google_domain` (not the
    Workspace's address), `staff_google_no_account`, `staff_google_not_staff`, `staff_google_break_glass`.
  - 202 with a change request (an action above the person's limit, or one that always needs a second person): nothing
    ran; `ApprovalNotice` shows the change request's number, its state and the permission its checker needs, and links
    to it.
  - 404 on a record: "Not found, or not yours to see" (a scope that does not reach it answers the same).
  - 400 with fields: each field's words beside it (nested ones as `parent.child`); 409 offers Reload and keeps the
    draft; 429 says when to try again (`Retry-After`). No answer at all is "cannot be reached", never a sign-out.
- **Every page checks the session itself** (`requireStaff`, `src/lib/auth/session.ts`): a layout is not rendered again
  on a client-side navigation, and the proxy never is the check.
- **The session's limits come from the manifest** (`GET session/`), never from the console: `idle_timeout_s` (15 or 30
  minutes by role) and `absolute_expires_at` (8 hours from the log-in) drive the idle watcher's warning and sign-out;
  the backend enforces both. While there is activity the console tells the server now and then; it never polls in the
  background.
- **What the manifest puts above every page**, none of it dismissable: the TEST band when `flags.test_mode` is true
  (absent means production); the impersonation banner while `impersonating` is set (End, with the token this tab
  started it with; otherwise it ends by itself or from the website's banner); a break-glass session's banner. A
  break-glass session that owes its reason (`break_glass.reason_required`) asks for it first (`POST session/reason/`),
  and policies due (`policies_due`) are acknowledged once each (`POST policies/ack/`), before anything else.
- **Permissions** are read in one place, `src/lib/modules.ts` (`P` and `MODULES`): the codenames of the backend's
  `staff/catalogue.py` (the shipping desk's and the insights' among them: `staff.view_parcels` … `staff.view_insights`)
  and the ERPNext sync's (`erp.*`). A module is drawn when the manifest lists any of its permissions.

## Design

The Answer Script tokens and fonts of the public site (paper, ink, navy as the only action colour, red ink for the
booklet's double rule beside the sidebar and nothing else), in a dense console layout: a sidebar of modules, a top bar
with ⌘K, lists with 44 px rows whose header sticks inside the table's own box and which scroll sideways in it on a
phone. Motion only inside `prefers-reduced-motion: no-preference` (the kit's dialog fade, button press and toasts);
nothing moves on load. Every word is in `src/lib/copy.ts` (English now; Assamese and Bengali as objects of the same
shape), and `<html lang>` with the `:lang` rule and Hind Siliguri in every font stack carry the scripts. The copied
`src/components/ui/` kit keeps its few words identical to the public site's, so a shared package later is a move.

## Routes

- Sign-in: `/sign-in/` (email and password, then the authenticator's code, a recovery code or a passkey; Google when
  on), `/set-up-two-step/` (staff without it: set it up on the website), `/no-access/`, `/inactive/`.
- The panel (`src/app/(panel)/`): `/` Home, `/inbox/`, `/audit/`, `/approvals/` and `/approvals/<id>/`, `/people/`,
  `/people/<id>/`, `/people/access-review/`, `/users/` and `/users/<id>/`, `/privacy/requests/` and `<id>/`,
  `/privacy/incidents/` and `<id>/`, `/privacy/processors/`, `/settings/`, `/settings/api-keys/`, `/system/`,
  `/account/` (the session's limits and the person's jobs). Every record page has its notes and its audit trail beside
  it. `/orders/`, `/shipping/`, `/catalogue/`, `/marketing/`, `/course/`, `/partners/` (distributors, schools,
  teachers) and `/insights/` say they come in the next phase and where that work is done today.
- Content (`src/app/(panel)/content/`, `src/components/modules/content/`): `/content/` (what waits: mistakes by kind,
  reviews for me, drafts, books missing legal deposits, the last import), `/content/books/` and `<id>/` (a book's ISBN,
  format, edition and publication day, its history), `/content/papers/` and `<id>/` (the questions and solutions as a
  tree; `?solution=<id>` or `?question=<id>` opens the editor: the Markdown and LaTeX on the left, the text as the
  site draws it on the right, KaTeX checking every formula before a save, the save bar, Submit for review, the
  history; the QR code, for a print run with `?printing=`), `/content/reviews/` and `<id>/` (waiting for me, the line
  diff beside the preview, approve, ask for changes, publish with five seconds to undo), `/content/reports/` and
  `<id>/` (the triage, Tell the reporter), `/content/errata/`, `/content/imports/` (a dry run's counts and labels,
  then Apply) and `/content/legal-deposits/`.
- In ERPNext (links out, in a new tab, said in words and marked with the external-link icon; drawn only when
  `NEXT_PUBLIC_ERP_URL` is set and the manifest has one of the sync's `erp.*` permissions): Finance `/app/accounting`,
  Tax `/app/gst-india`, Inventory `/app/stock`, Purchases `/app/buying`, CRM `/app/crm`.

## Add a module

1. Regenerate the types (above) once the backend has the module's endpoints; its calls in `src/lib/api/staff.ts`
   through `api.GET`/`POST`/… on the generated paths; its permissions in `P` and its entry in `MODULES`
   (`src/lib/modules.ts`, in the plan's order); its words in `src/lib/copy.ts`.
2. A server page in `src/app/(panel)/<module>/page.tsx`: `staffPage(path)` (the session check and the transport), each
   call through `attempt()` (its data or its `ApiError`, which the page draws as a `Problem`), `metadata` from the copy.
3. Lists through `DataTable` (filters, saved views, columns, keyboard), records through `RecordPage` (status, actions,
   timeline, Danger) with `recordSide()` for the notes and the audit trail, forms through `ActionForm` (one send, the
   API's field errors, the draft); dangerous actions through `ConfirmDialog` or `ConfirmTyped`. Interactive parts in
   `src/components/modules/<module>/`.
4. Its fixtures and answers in `src/mocks/staff/` (every state the screen draws); a test.

## Tests

```sh
npm run lint && npm run format:check && npm run typecheck
npm test                                                   # Vitest
npx playwright test --project=chromium                     # mock mode: e2e/console.spec.ts
E2E_STAFF_API=real npx playwright test --project=real      # the staff API as built: e2e/real.spec.ts
```

The Playwright tests reuse a running console (3020) and Django (8103), or start them: `scripts/e2e-backend.sh`
migrates a SQLite file of its own (`.e2e/db.sqlite3`) and runs Django; `next dev` runs with `STAFF_API_MOCK=1` in mock
mode and without it for the real project (the console in mock mode must not be the one reused). `E2E_WEB_PORT`,
`E2E_API_PORT` and `E2E_WEBSITE_URL` move them. In a worktree without examleaf-web's virtualenv set `DJANGO_PYTHON` to
a Python that has its requirements, and `DJANGO_DATABASE_URL` to the running Django's database (the tests make their
staff members and records through `manage.py shell`, and delete them afterwards). Both sign in with a password and an
authenticator code, check every page with axe-core (WCAG 2.0 to 2.2 A and AA and best practice, as the public site's
audit did: its `axe.min.js` evaluated in the page) and for sideways scrolling at 1280, 390 and 320 px, and check that
nothing animates with reduced motion.

- **Mock mode** walks every state at 1280 and 390: Home, the inbox (done, snooze, take one), approvals (approve with
  the payload's hash, reject, withdraw one's own, carry one out), invitations, a revealed email address, "confirm it's
  you", a note, impersonation and End, a setting with a reason found in the audit trail, jobs (cancel one, download a
  file), ⌘K, the idle sign-out; and a break-glass session's reason and a policy acknowledged before anything else.
- **Against the real backend** an OWNER and a SUPPORT member are made for the run, with an adult customer, an order
  of ₹1,500 paid online, the customer's erasure request and an incident: SUPPORT reads the manifest and the inbox and
  asks for a refund above their ₹1,000 (a 202 and a change request, which the maker cannot approve: 403); the OWNER
  approves it from the inbox and finds both steps in the audit trail; invites a colleague (a privileged role waits for
  another person, never the maker); searches for the customer and reveals their address with a reason (audited);
  acknowledges the data request; changes a setting with a reason; signs in to the website as the customer with the
  real token and ends it (both audited); and the idle sign-out comes at SUPPORT's 30 minutes, after which the API
  answers 401.

## Deploy

`Dockerfile`: multi-stage, standalone output, the unprivileged `node` user, a health check on `/api/health/` (the
process only; 503 from SIGTERM on). Timeouts, memory, shutdown, the load proof and the knobs: `RESILIENCE.md`. `../examleaf-web/docker-compose.yml` builds it as the `admin` service of the `admin` profile
(`docker compose --profile admin up -d`), and the Caddyfile's second site `admin.{$DOMAIN}` sends Django's paths to
`web:8000` and everything else to `admin:3000`, with the same limits, health rule and logging as the public site.
Caddy also drops the `X-Middleware-Subrequest` request header before anything reaches the console (Next.js's own
internal header, never a visitor's to send: CVE-2025-29927's bypass of a proxy), and the `admin` service publishes no
port, so every request to it passes through Caddy. The console never relies on its proxy for access anyway: every
page asks the staff API. Before turning it on:

- Django must answer the host: add `admin.<domain>` to `ALLOWED_HOSTS` and `https://admin.<domain>` to
  `CSRF_TRUSTED_ORIGINS` (the backend's DEPLOYMENT.md states it too). Cookies stay host-only: no cookie domain change.
- Point the host's DNS at the machine: Caddy asks for its certificate at start.
- Google sign-in for staff: add `https://admin.<domain>/account/google/login/callback/` to the OAuth client's
  redirect URIs.
- `ERP_URL` in `.env` (compose passes it as `NEXT_PUBLIC_ERP_URL`) once ERPNext runs.

## The contract this console speaks

The generated types are the contract (`src/lib/api/schema.d.ts`, from `openapi.json`); the backend's `API.md` ("Staff
API") explains it. Base `/api/v1/staff/`, JSON, `Cache-Control: no-store`, DRF's errors with `detail` and `code`,
cursor pagination `{next, previous, results}` (the `cursor` of the links, `page_size`). What the console calls:

- **The session**: `GET session/` (the manifest: `user`, `roles`, `permissions`, `scopes`, `idle_timeout_s`,
  `absolute_expires_at`, `flags.test_mode`, `impersonating`, `break_glass` `{reason_required, reason, ends_at}`,
  `policies_due` `[{policy, version}]`); `POST session/reason/` (`{reason}`), `POST policies/ack/`
  (`{policy, version}`, once each version).
- **The inbox**: `GET inbox/` (`?mine=1`, `done`, `snoozed`, `kind`), `GET inbox/count/`, `POST inbox/{id}/done/`,
  `snooze/` and `assign/`.
- **Approvals**: `GET change-requests/` (`status`, `action`, `?awaiting=1`, `?mine=1`), `GET change-requests/{id}/`,
  `POST change-requests/` (with an `Idempotency-Key`), `POST …/{id}/approve/` with the `payload_sha256` the checker
  read (a changed payload is refused), `reject/` and `execute/`.
- **Audit and jobs**: `GET audit/` (actor and its type, the action or its prefix, target, change request, outcome,
  break-glass, `since` and `until`), `POST audit/export/` (an ndjson file at once, or 202 with a job for a large one);
  `GET jobs/` (`?mine=1`), `GET jobs/{id}/`, `POST jobs/{id}/cancel/`; a done job's file is `result_url`, signed for 5
  minutes, so the link is asked for again each time (`result/?token=`). States: queued, running, done, failed,
  cancelled.
- **Saved views**: `GET`/`POST saved-views/`, `PATCH`/`DELETE saved-views/{id}/` (the owner's, or shared with a role).
- **Settings, flags, API keys**: `GET settings/`, `PUT settings/{key}/` (with a reason, now or from `effective_from`;
  maintenance is `PUT settings/MAINTENANCE_MODE/`), `GET flags/`, `GET`/`PUT flags/{key}/` (the history and a change),
  `GET`/`POST api-keys/`, `POST api-keys/{id}/revoke/`.
- **People (staff)**: `GET people/`, `GET people/{id}/`, `GET`/`POST people/invites/` and `people/invite/`,
  `DELETE people/invites/{invite}/`, `POST`/`DELETE people/{id}/roles/` and `…/roles/{role}/`, `…/scopes/` likewise,
  `POST people/{id}/end-sessions/`, `reset-mfa/`, `offboard/`; `GET access-review/`.
- **Customers**: `GET users/` (`q`, filters), `GET users/{id}/` (opening it is audited), `POST users/{id}/reveal/`
  with `{show: ["email"], reason}` (answered `{email: …}`, audited and throttled), `suspend/`, `unsuspend/`,
  `unlock/`, `end-sessions/`, `reset-mfa/`, `password-reset/`, `resend-verification/`; `POST users/{id}/impersonate/`
  with `{reason, ticket}` (answered `{token, expires_at}`: the console builds the website's link,
  `NEXT_PUBLIC_WEBSITE_URL/account/impersonate/?token=…`) and `POST users/{id}/impersonate/end/` with the token.
- **Data protection**: `GET`/`POST data-requests/`, `GET`/`PATCH data-requests/{id}/`, `POST …/acknowledge/`,
  `verify-identity/`, `close/`, `GET …/response/`, `GET …/erasure-report/`, `POST …/erase/`, `POST …/export/`;
  `GET`/`POST incidents/`, `GET`/`PATCH incidents/{id}/`, `POST …/close/`; `GET`/`POST processors/`.
- **Notes**: `GET`/`POST notes/?target_type=&target_id=` (a record's notes, not paged; only on records the reader may
  see).
- **The system**: `GET system/`, `POST system/reconcile/` (an order's payment checked with Razorpay again).
- **Content** (`content/…`, API.md "Content (staff)"; every list and record within the person's subjects):
  `GET content/summary/`; `GET`/`POST content/books/`, `GET`/`PATCH content/books/{id}/`; `GET content/papers/`,
  `GET`/`PATCH content/papers/{id}/` (`is_published` and `is_sample` need `staff.publish_paper`),
  `GET content/papers/{id}/qr/` (`?printing=`; `site_url_not_public` on a local site);
  `GET`/`PATCH content/questions/{id}/` and `content/solutions/{id}/` (the PATCH writes the draft, never the live
  text; the API's LaTeX check answers per field with its line), `POST …/submit/`, `discard/`, `rollback/`;
  `GET …/{id}/history/` and `POST …/history/{history_id}/restore/` for books, papers, questions and solutions;
  `GET content/reviews/` (`?mine=`, `?open=`), `GET content/reviews/{id}/` (`yours`, `changes` with their lines),
  `POST …/approve/`, `needs-changes/` (`{comment, field}`), `publish/` (`403 own_edit` for whoever edited or submitted
  it); `GET content/reports/`, `GET`/`PATCH content/reports/{id}/`, `POST …/confirm/`, `reject/` (`{staff_note}`),
  `fix-online/`, `fix-in-printing/` (`{fixed_in}`), `reopen/`, `tell/`; `GET content/errata/`;
  `GET content/imports/` and `POST jobs/` with
  `{kind: "content_import", params: {subject, commit, fixtures?, dry_run_job?}, dry_run}` (`staff.import_content`, a
  fresh authentication); `GET`/`POST content/legal-deposits/` (multipart with a scan),
  `GET content/legal-deposits/missing/`, `content/legal-deposits/{id}/proof/` (the scan, opened from this origin).
