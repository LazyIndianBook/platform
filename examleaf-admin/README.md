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

1. Django for signing in, from `../examleaf-web/` (its README), on port 8103, trusting the console's origin:

   ```sh
   DEBUG=1 SITE_URL=http://localhost:3020 CSRF_TRUSTED_ORIGINS=http://localhost:3020 USE_X_FORWARDED_HOST=1 \
     INTERNAL_API_TOKEN=dev-token .venv/bin/python manage.py runserver 8103
   ```

   On SQLite add `DATABASE_URL='sqlite:////<path>/db.sqlite3?transaction_mode=IMMEDIATE&timeout=20'` (allauth's device
   list writes on every signed-in request). A member of staff needs `is_staff`, a role group (`accounts/roles.py`) and
   an authenticator app or a passkey; `e2e/django.ts` shows how the tests make one through `manage.py shell` with a
   known TOTP secret.

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

Until the backend's staff app exists, `STAFF_API_MOCK=1 npm run dev` answers every staff API path from the
deterministic fixtures of `src/mocks/staff/` (the browser's calls through `src/app/api/mock/staff/[...path]/`, server
components' in the same process). Signing in stays real: each mock request asks the Django backend whose session cookie
it carries who is signed in (`GET /api/v1/me/`: 401 signed out, 403 `mfa_setup_required` for staff without two-step
sign-in, the role groups otherwise), "confirm it's you" reads allauth's own record of the last authentication, the CSRF
token is checked as Django checks it, actions write audit events, and the brief's second-person rules make change
requests. Each staff member gets a world of their own, changed by what they do. Dev-only cookies change what it
answers: `staff_mock_role=SUPPORT` (another role's permissions), `staff_mock_reauth_after=<epoch seconds>` (an older
authentication counts as stale). `next.config.ts` sets the flag only under `next dev`: every build compiles it to "",
so a production bundle cannot reach a fixture (the route throws and the import sits behind the same check).

## Environment

| Variable                  | Where   | What                                                                                       |
| ------------------------- | ------- | ------------------------------------------------------------------------------------------ |
| `NEXT_PUBLIC_SITE_URL`    | build   | the console's own address (`https://admin.examleaf.in`), the host Django sees              |
| `NEXT_PUBLIC_WEBSITE_URL` | build   | the public website, where staff set up two-step sign-in and passkeys                       |
| `NEXT_PUBLIC_ERP_URL`     | build   | ERPNext's desk, for the business modules' links; empty: none are drawn                     |
| `API_INTERNAL_BASE`       | runtime | Django for server components (`http://web:8000` in compose)                                |
| `INTERNAL_API_TOKEN`      | runtime | the secret shared with Django: Django then counts each person's address, not this server's |
| `STAFF_API_MOCK`          | dev     | `1`: the staff API from fixtures (`next dev` only)                                         |

No `NEXT_PUBLIC_` value is a secret. Sign-in methods come from `GET /api/v1/config/` (Google), never hard-coded.

## The API boundary

- **`src/lib/api/staff.ts` holds every staff call**: thin typed functions for the contract, each with a runtime guard in
  plain TypeScript (no schema library) that turns the answer into its type or fails as `bad_response` naming the field,
  so a renamed field costs this one file. Once the backend publishes its OpenAPI schema, `npm run api:snapshot`
  (against a running backend) and `npm run api:types` generate `src/lib/api/schema.d.ts`, and these types come from
  there.
- **The same function, two places.** Server components pass `await staffTransport()` (`src/lib/api/server.ts`): Django
  over the internal network with the person's cookies, address and browser, never cached, and no credential of the
  server's own. In the browser the transport is left out: same origin, the CSRF token from the `csrftoken` cookie on
  every change, and the browser's reactions (`src/lib/api/client.ts`).
- **Answers the console acts on** (`src/lib/api/errors.ts`): a 401 sends the person to sign in and back (what they
  typed stays in sessionStorage, `useDraftForm`); 403 `reauth_required` opens "Confirm it's you" (allauth's
  reauthenticate flows: the authenticator's code, the password, a passkey) and sends the call once more;
  `permission_denied` and `scope_denied` render the page again from the server, which reads the manifest afresh;
  `approval_required` (or a 202 with a change request) shows that a change request was made and links to it; 409 offers
  Reload and keeps the draft; 429 says when to try again (`Retry-After`). No answer is "cannot be reached", never a
  sign-out.
- **Every page checks the session itself** (`requireStaff`, `src/lib/auth/session.ts`): a layout is not rendered again
  on a client-side navigation, and the proxy never is the check.
- **The session's limits come from the manifest**, never from the console: `idle_timeout_s` (15 or 30 minutes by
  role) and `absolute_expires_at` (8 hours from the log-in) drive the idle watcher's warning and sign-out; the backend
  enforces both. While there is activity the console tells the server now and then; it never polls in the background.
- **The TEST band**: when the manifest's `flags.test_mode` is true (absent means production) a band in night ink sits
  above every page, with the impersonation banner when there is one; neither can be dismissed.
- **Permissions** are read in one place, `src/lib/modules.ts` (`P` and `MODULES`): the codenames the backend's
  `staff/permissions.py` must emit. A module is drawn when the manifest lists any of its permissions.

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
  `/account/`; `/orders/`, `/catalogue/`, `/marketing/`, `/content/`, `/course/`, `/partners/` (distributors, schools,
  teachers) and `/support/` (tickets: the platform's own, Frappe Helpdesk is not installed) say they come in the next
  phase and where that work is done today.
- In ERPNext (links out, in a new tab, said in words and marked with the external-link icon; drawn only when
  `NEXT_PUBLIC_ERP_URL` is set): Finance `/app/accounting`, Tax `/app/gst-india`, Inventory `/app/stock`, Purchases
  `/app/buying`, CRM `/app/crm` (ERPNext's own Lead, Opportunity and Quotation: Frappe CRM is not installed).

## Add a module

1. The calls and their guards in `src/lib/api/staff.ts`; its permissions in `P` and its entry in `MODULES`
   (`src/lib/modules.ts`, in the plan's order); its words in `src/lib/copy.ts`.
2. A server page in `src/app/(panel)/<module>/page.tsx`: `staffPage(path)` (the session check and the transport), each
   call through `attempt()` (its data or its `ApiError`, which the page draws as a `Problem`), `metadata` from the copy.
3. Lists through `DataTable` (filters, saved views, columns, keyboard, bulk jobs, export), records through
   `RecordPage` (status, actions, timeline, Danger), forms through `ActionForm` (one send, the API's field errors, the
   draft); dangerous actions through `ConfirmDialog` or `ConfirmTyped`. Interactive parts in
   `src/components/modules/<module>/`.
4. A fixture and a route in `src/mocks/staff/` to exercise it before the backend has it; a test.

## Tests

```sh
npm run lint && npm run format:check && npm run typecheck
npm test                                 # Vitest
npx playwright test --project=chromium   # e2e/, next dev in mock mode and a real Django for signing in
```

The Playwright tests reuse a running console (3020) and Django (8103), or start them: `scripts/e2e-backend.sh`
migrates a SQLite file of its own (`.e2e/db.sqlite3`) and runs Django; `next dev` runs with `STAFF_API_MOCK=1`. In a
worktree without examleaf-web's virtualenv set `DJANGO_PYTHON` to a Python that has its requirements, and
`DJANGO_DATABASE_URL` to the running Django's database (the tests make their staff members through `manage.py shell`).
They sign in with a password and an authenticator code, check every page with axe-core (WCAG 2.0 to 2.2 A and AA and
best practice, as the public site's audit did: its `axe.min.js` evaluated in the page) and for sideways scrolling at
1280, 390 and 320 px, then walk the day's work and the idle sign-out at the limit the manifest gives the role
(Playwright's clock) at 1280 and 390.

## Deploy

`Dockerfile`: multi-stage, standalone output, the unprivileged `node` user, a health check on `/api/health/` (the
process only). `../examleaf-web/docker-compose.yml` builds it as the `admin` service of the `admin` profile
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

Base `/api/v1/staff/`, JSON, cursor pagination `{results, next, previous}` (the `cursor` of the links), `Cache-Control:
no-store`, DRF's error format with `detail` and `code`. Field names are provisional and live in `src/lib/api/staff.ts`;
beyond the brief the console also calls `GET people/{id}/`, `GET data-requests/{id}/`, `GET incidents/{id}/`
(the detail routes of the brief's PATCH routes), `DELETE users/{id}/impersonate/` (end the "sign in as" window),
`POST jobs/` with `GET jobs/{id}/` (bulk actions and exports as background jobs: `{id, state, done, total, errors:
[{id, label, message}], result_url}`), and sends the version it read as `If-Match` on PATCH.
