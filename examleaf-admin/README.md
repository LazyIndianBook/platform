# ExamLeaf admin console

The staff console of ExamLeaf's Admin Control Panel (`docs/examleaf-admin-control-panel-plan.md`), served at
`admin.examleaf.in`: the product side that ERPNext cannot see (orders and packing, the catalogue, customers and their
consent, the revision course and its book codes, content review, support tickets, legal and privacy, staff roles and
scopes, approvals, the audit trail, settings and connections, the system's health, Home and its reports), the
platform's own records of money and tax (payments, refunds, settlements, GST documents), and deep links into ERPNext
for the books of account, GST returns, stock, purchases and CRM. Next.js 16 (App Router, Turbopack),
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
running, done, failed and cancelled, orders in every state (paid and to pack, held, cash on delivery with a high risk,
sent, delivered with returns, cancelled, a staff order waiting for its payment, a bank refund to mark paid, a test
order; `src/mocks/staff/orders.ts`), an overdue inbox, a data request near its clock, an incident's 6-hour clock, a
scheduled setting, revoked API keys, a person who left, and support tickets in every state (new, nearly due, overdue
with its deadline missed, an acknowledgement missed, waiting, an NCH complaint, a privacy request, a content error,
resolved, closed, spam) with saved replies in three languages (`src/mocks/staff/support-fixtures.ts` and
`support-handler.ts`, called from the two files), and Finance's records (`src/mocks/staff/finance.ts`): payments
captured, settled, stuck (authorised and never captured; Razorpay never had one; a link past its life), failed,
offline and of the test keys; refunds made, waiting, by bank and failed; staff orders' and B2B invoices' links open,
paid, posted, cancelled and expired; settlements posted, matched with ERPNext failing, one that does not match and a
test one, and Home's cards by role and the reports (`reports.ts`, with the backend's own words for every definition in
`reports-specs.ts` and `reports-words.ts`): five titles' sales over 400 days, places and districts with small ones the
minimum hides, book codes by print run, the course's use with a day too small to show, cash on delivery's ageing,
Razorpay's settlements, the newsvendor's sum worked out with the backend's arithmetic, the insights' own numbered
lists, and a report as an export job with a file that ends with who made it; and customers (`src/mocks/staff/customers.ts`: students whose parent's link ended, was never
sent, or went three times today; a parent with an account of her own; guest buyers; a long timeline for the paging;
the bulk actions' dry runs, a child among the targets and the job that waits for an approver). Signing in stays real: each mock request asks the Django
backend whose session cookie it carries who is signed in (`GET /api/v1/me/`: 401 signed out, 403 `mfa_setup_required`
for staff without two-step sign-in, the role groups otherwise), "confirm it's you" reads allauth's own record of the
last authentication, the CSRF token is checked as Django checks it, actions write audit events, and the backend's
second-person rules make change requests. Each staff member gets a world of their own, changed by what they do.

Dev-only cookies change what it answers: `staff_mock_role=SUPPORT` (another role's permissions),
`staff_mock_reauth_after=<epoch seconds>` (an older authentication counts as stale), `staff_mock_break_glass=1` (a
break-glass session that owes its reason), `staff_mock_policies=1` (a policy to acknowledge), `staff_mock_passkey=0`
(OWNER, ADMIN or FINANCE without a passkey: `passkey_required`), `staff_mock_factor_changed=1` (a second factor just
changed: the offer to end the other sessions, once), and for Home and reports `staff_mock_test_keys=1` (the site runs
on test keys), `staff_mock_card_error=<card key>` (that card could not be worked out), `staff_mock_settlements=off`
(the Finance module has not set up Razorpay's settlements), `staff_mock_health=empty` (the overnight count of the
course's use has not run) and `staff_mock_untested=1` (the forecast has not beaten the seasonal naive). `next.config.ts` sets the
flag only under `next dev`: every build compiles it to "", so a production bundle cannot reach a fixture (the route
throws and the import sits behind the same check).

## Environment

| Variable                  | Where   | What                                                                                       |
| ------------------------- | ------- | ------------------------------------------------------------------------------------------ |
| `NEXT_PUBLIC_SITE_URL`    | build   | the console's own address (`https://admin.examleaf.in`), the host Django sees              |
| `NEXT_PUBLIC_WEBSITE_URL` | build   | the public website: two-step sign-in and passkeys, and the impersonation link's address    |
| `NEXT_PUBLIC_ERP_URL`     | build   | ERPNext's desk, for the business modules' links; empty: none are drawn                     |
| `NEXT_PUBLIC_API_BASE`    | build   | base of the browser's `/_allauth/` calls; empty: its own origin (always, in the image)     |
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
  `/people/<id>/` (tabs `?tab=access`, `offboarding`, `erp`), `/people/roles/`, `/people/access-review/`, `/users/` (the
  tabs everyone, students, parents and guest buyers as `?kind=`, the badges, search, the filters in the address, saved
  views, the bulk bar: suspend, lift, sign out everywhere, send the parents' links again, each checked first), `/users/<id>/`
  (the badges, a student under 18's banner "Under 18: every view is logged", the details, the parent consent with the
  link's life, send it again and record it by hand, the linked accounts, what they bought, the Course section
  (a link to the learner's page, `/course/learners/<id>/`, for whoever holds `learn.view_entitlement`), the latest
  orders, the consent records, the customer's nominee, devices, actions and Danger), `/users/<id>/timeline/` (the
  merged timeline, `?kind=` and `?before=`) and `/users/consent-pending/` (the students waiting for a parent, the oldest first),
  `/privacy/` (Legal and privacy's compliance cockpit), `/privacy/requests/` and `<id>/` (the erasure's dry run with
  what the law keeps, each a sentence), `/privacy/policies/` and `<slug>/` (versions, diffs, publishing),
  `/privacy/incidents/` and `<id>/`, `/privacy/processors/`, `/privacy/retention/`, `/privacy/holds/` and `<id>/`,
  `/privacy/disclosures/`, `/privacy/dark-pattern-audit/`, `/settings/` (grouped, each switch's history),
  `/settings/api-keys/`, `/settings/connections/` and `/settings/connections/<provider>/`, `/settings/templates/`,
  `/system/` and `/system/sync/`, `backups/`, `logs/`, `dependencies/`, `hardening/`, `scripts/`, `/account/` (the
  session's limits, one's own sessions and jobs). Tax (`src/components/modules/tax/`, its own tabs): `/tax/`
  (the month's due dates with Previous and Next month, the threshold card, this year's table 13), `/tax/hsn/` (the HSN
  and SAC master, the products that disagree with it, a new code at `#new`) and `/tax/hsn/<code>/` (its rate history,
  its products, a new dated rate behind the save bar), `/tax/documents/` (invoices or credit notes by series, type,
  month, cancelled, the test series apart) and `/tax/documents/<number with dashes>/` (its lines, Rule 46's checks, the
  PDF, cancelling it with its number typed), `/tax/series/` (table 13 of a year or a month), `/tax/gstr1/` (the
  month's or the quarter's export as a job, and the person's exports with their files). Every record page has its
  notes and its audit trail beside it. The Orders module: `/orders/` (the tabs all, to pack, shipped, returns,
  cancelled and drafts, the filters in the address, saved views, the bulk bar: mark packed with 5 s to undo, print,
  cancel with the count typed, export; Space looks at an order beside the list), `/orders/<number>/` (the next step,
  its books, money, documents, parcels, the customer masked, risk, hold and tags, the timeline; Danger: cancel, the
  refund dialog, a return), `/orders/packing/` (packer mode), `/orders/returns/` and `<id>/`, `/orders/new/` (a staff
  order, the discount rule's answer before saving) and `/orders/quotes/` and `<id>/` (made into an order once).
  `/shipping/`, `/marketing/` and `/partners/` (distributors, schools, teachers) say they come in the next phase and
  where that work is done today (the Django admin; the shipping staff API is built, its pages are not).
- Home and reports (`src/components/modules/reports/`): Home (`/`) draws the numbers of the person's roles first
  (streamed on their own, so they show as soon as they are ready): the totals (net revenue, orders, codes redeemed,
  active learners) beside the period before them in a sentence, the queues (orders to pack, quotes, refunds to
  approve, tickets due, mistakes to triage, COD overdue …) as they stand, each card a link to the list or report it
  counts with its definition on hover and under "How this is counted", "Data as of", test data said first, the period
  chosen with `?period=today|week|month` (`week`, the last 7 days, with no parameter); the inbox, approvals, clocks
  and health stay below.
  `/reports/` (the `insights` entry of the modules became `reports`) lists the reports the role may open, each with a
  line of what it counts, and how every number is counted; `/reports/sales/` (`?from&to&by&grain`: title, subject,
  class, board or edition, by day, week or month, a bar beside each net), `/reports/place/` (`?level=state|district|pin`
  and `&state=`: a state's row opens its districts; a place under the minimum says "fewer than 10"),
  `/reports/codes/` (the insights' codes report, by print run and district, `?batch=`; the Course module has another,
  below), `/reports/course-health/` (`?subject&chapter&grain`: learners, clips, quiz answers and flash cards by day,
  week or month, the chapters over 28 days), `/reports/cod/` (what the
  couriers owe by how late, what they remitted, by courier), `/reports/settlements/` (the settlements Finance fetched
  in the period, of the live keys; it says it is not set up only where the platform has no Finance module, which the
  mock's `staff_mock_settlements=off` shows), `/reports/cohorts/` (`?page=`) and `/reports/forecasts/` (`?product=`:
  the print runs with their levels, the sum worked out again from the net price, print cost and salvage typed, and the weekly forecast as a
  range). Every report page has its tabs by permission, its filters in the address (a plain GET form), tables and CSS-width
  bars (no chart library) and, for whoever holds `staff.export_report`, "Export as a file" (a job, its file ending
  with who made it).
- Catalogue (`src/app/(panel)/catalogue/`, `src/components/modules/catalogue/`, its own tabs): `/catalogue/` (what
  waits: products the courier cannot be quoted for, GST disagreeing with the master, low and empty stock,
  back-in-stock requests, approvals; the prior-price rule's day), `/catalogue/products/` (the chips, the filters
  `incomplete`, `tax_problem`, `stock`, `published`, `kind`, saved views) and `/catalogue/products/new/`,
  `/catalogue/products/<slug or id>/` (by section, each behind its own save bar and sending only what changed: the
  prices with the website's prior price shown before saving and the change request when it waits, the page, the
  courier's data, the tax with today's rate and the next change, the stock set with the count read, a bundle's books
  one a line, pictures, the search engines' words with their lengths, the barcode, the versions), `/catalogue/stock/`,
  `/catalogue/coupons/`, `new/` and `<code>/` (its terms, a change with its reason, the single-use codes and a
  school's batch as a job with its file), `/catalogue/offers/`, `new/` and `<id>/`, `/catalogue/shipping-rates/` and
  `<id>/`, `/catalogue/categories/` (the tree, each shelf changed or moved), `/catalogue/collections/` and
  `/catalogue/import/` (the import's dry run then its apply, the export, each with its progress).
- Content (`src/app/(panel)/content/`, `src/components/modules/content/`): `/content/` (what waits: mistakes by kind,
  reviews for me, drafts, books missing legal deposits, the last import), `/content/books/` and `<id>/` (a book's ISBN,
  format, edition and publication day, its history), `/content/papers/` and `<id>/` (the questions and solutions as a
  tree; `?solution=<id>` or `?question=<id>` opens the editor: the Markdown and LaTeX on the left, the text as the
  site draws it on the right, KaTeX checking every formula before a save, the save bar, Submit for review, the
  history; the QR code, for a print run with `?printing=`), `/content/reviews/` and `<id>/` (waiting for me, the line
  diff beside the preview, approve, ask for changes, publish with five seconds to undo), `/content/reports/` and
  `<id>/` (the triage, Tell the reporter), `/content/errata/`, `/content/imports/` (a dry run's counts and labels,
  then Apply) and `/content/legal-deposits/`.
- Support: `/support/` (the queue by the next legal deadline, its tabs due soonest, mine, unassigned, overdue,
  waiting and all as `?tab=`, the module's numbers), `/support/tickets/<number>/` (the conversation and the reply box,
  the deadlines, the status, the actions, the customer and the audit trail beside it), `/support/new/` (a call, a
  WhatsApp message, an NCH complaint or an email logged), `/support/replies/` and `/support/export/` (the grievance
  register).
- Finance (`src/app/(panel)/finance/`, `src/components/modules/finance/`, its own tabs; under Shop, for
  `shop.view_payment`, `shop.view_settlement` or `staff.view_cod`): `/finance/` (Finance today, a line a duty and each
  a link to where it is dealt with; an invoice's or credit note's copy in ERPNext looked up by its number,
  `?document=`; "In ERPNext": accounting, payouts, purchase invoices, receivables, the bank's reconciliation, closing a
  period, MSME dues, the chart of accounts), `/finance/payments/` (the "Stuck" tab, filters, saved views) and `<id>/`
  (Razorpay's ids, the fee and its settlement, Ask Razorpay again, its refunds, the webhooks seen, the timeline),
  `/finance/refunds/` (by state, "To approve" opening each change request, the refund timelines to tell a customer),
  `/finance/offline-payments/` ("To approve" and "Recorded"), `/finance/payment-links/` (the staff orders' or the B2B
  invoices' links, sent again, cancelled, asked of Razorpay again, a B2B one's ERPNext entry recorded; a new link),
  `/finance/settlements/` (by state; a day fetched as a job) and `<id>/` (its figures, what does not match, its
  ERPNext entry, its lines matched by hand with a note).
- Course (`src/app/(panel)/course/`, `src/components/modules/course/`): `/course/` (the subjects, and the chosen one's
  outline as `?subject=PHY`: each chapter's must-do note, revision, clips, cards and quiz items, every row dragged by
  its handle or moved with "Move to…", a card edited, a row deleted: a clip once its title is typed, a card or an item
  with five seconds to undo), `/course/revisions/<id>/` (submit, approve, send back, publish now or at a time, back to
  draft; the title and length), `/course/clips/<id>/` (the reason in words with Retry beside it, the poster and the
  staff player, its details, delete or restore), `/course/bin/` (`?kind=clips|cards|items`, restore the chosen),
  `/course/items/` and `<id>/` (the quiz bank with its item analysis and "N/A", the metadata of many changed with a dry
  run; an item's text, key and metadata, "Needs checking", its history), `/course/entitlements/` (access found by
  subject, source, state or a whole email address; extended or revoked, one at once or many with a dry run; given to
  one account or to many), `/course/codes/` and `<key>/` (the lookup box answering in one line with Void this code; a
  print run made with the printer's file; the print runs, one with its weeks, signals, Mark dispatched and Void the
  run), `/course/report/` (the Course module's codes report, below) and `/course/learners/<id>/` (from a ticket's
  sidebar, an access row, a code or the customer's record; says at the top that the view is logged; a child's a
  summary; "Open the customer's record" goes back to `/users/<id>/` for whoever holds `accounts.view_user`).
- **The two codes reports** both stay, and answer different questions. `/course/report/` (`getCourseCodesReport`,
  `GET course/codes/report/`; `learn.view_codebatch`: SUPPORT, SALES, ADMIN, the owners and the auditor) works out the
  newest 200 print runs when asked: the codes printed; the copies of the run's book sold online from the run's day
  until the next run of that book (a bundle holding it counts); the codes activated; "revoked", the access a code
  opened that staff took back; "void", the codes voided before use; the activation rate; and the districts of the
  redemptions, one under 10 shown as "fewer than 10". `/reports/codes/` (`getCodesReport`, `GET reports/codes/`;
  `staff.view_insights` with `learn.view_bookcode`: ADMIN, the owners and the auditor) is the insights' own: by print
  run too, with the last 7 days; its "sold" is the book's copies sold in all, every run of it together; its "revoked"
  is the codes voided before use (the Course report's "void"); and its districts are the night's count (`?batch=`
  narrows them; the minimum is `INSIGHTS_MIN_CELL`). Its "sold" and "revoked" columns, empty until the Course module
  recorded the book of a run and the voided codes, are filled now; a run made with no book has no "sold" in either.
- In ERPNext (links out, in a new tab, said in words and marked with the external-link icon; drawn only when
  `NEXT_PUBLIC_ERP_URL` is set and the manifest has one of the sync's `erp.*` permissions): GST returns
  `/app/gst-india`, Inventory `/app/stock`, Purchases `/app/buying`, CRM `/app/crm` (Finance is a panel page that
  carries its own ERPNext links).

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
npm test                                                   # Vitest: 350 tests at the merge of Phase B
npx playwright test --project=chromium                     # mock mode: e2e/console.spec.ts, 23 tests
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

- **Mock mode** walks every state at 1280 and 390: customers (the tabs and the guest buyers, a child's record with its
  banner, badges and consent, a child's timeline narrowed to texts and an adult's paged at 200 rows, a consent recorded
  by hand after the API refused a contact as evidence and found in the audit trail and the timeline, the children
  waiting and the link again up to the day's limit, a bulk action checked first with a child among the targets and
  then an adult's run at once, SUPPORT's smaller view); Home, the inbox (done, snooze, take one), approvals (approve with
  the payload's hash, reject, withdraw one's own, carry one out), invitations, a revealed email address, "confirm it's
  you", a note, impersonation and End, a setting with a reason found in the audit trail, jobs (cancel one, download a
  file), ⌘K; legal and privacy (the cockpit, a child's deletion confirmed for the parent with the evidence, a legal
  hold that the erasure's dry run then names, the disclosures saved with a reason, both found in the audit trail); the
  Orders module (SUPPORT's refund of two books above their limit answered with its change request; the packing queue's
  mark packed undone, then sent); the support queue (a ticket opened, a saved reply put in with Alt 1 and sent, the
  status moved on, an NCH complaint logged); Finance (today's stuck payments, one asked of Razorpay again and
  captured, its line in the settlement that did not match matched by hand and the adjustment accepted, both in the
  audit trail); Home and reports (the OWNER's numbers with their definitions and the period before, the period of the
  totals changed, the PACKER's Home with the orders to pack and nothing of the money, a card in error, the sales report
  grouped by subject with how it is counted, its export as a job whose file ends with who made it, a place and a
  chapter too small to show, settlements not set up, the print run worked out again with an input that is not rupees
  refused, and FINANCE without the book codes' tab); the Course module (a clip moved first with "Move to…", a
  colleague's revision scheduled while one's own waits for another reviewer, a book code looked up and voided once VOID
  is typed, a redeemed code's learner page: logged, a child's a summary); the idle sign-out; and a break-glass session's
  reason and a policy acknowledged before anything else.
- **Against the real backend** an OWNER, a SUPPORT, a SALES and a FINANCE member are made for the run, with an adult
  customer, an order of ₹1,500 paid online, the customer's erasure request and an incident: SUPPORT reads the manifest
  and the inbox and asks for a refund above their ₹1,000 (a 202 and a change request, which the maker cannot approve:
  403); the OWNER approves it from the inbox and finds both steps in the audit trail; invites a colleague (a privileged
  role waits for another person, never the maker); searches for the customer and reveals their address with a reason
  (audited); acknowledges the data request; changes a setting with a reason; signs in to the website as the customer
  with the real token and ends it (both audited); puts a legal hold on the customer, which the erasure's dry run then
  names; SUPPORT answers the customer's ticket (seeded through the support app's own service), its first reply is
  recorded and the OWNER finds the reply in the ticket's audit trail; and the idle sign-out comes at SUPPORT's 30
  minutes, after which the API answers 401. Then the Orders module,
  on three books and an order of one of each paid online and sent: SALES makes a staff order (the rule's answer shown
  before saving; made at once within 20%), FINANCE finds it by the customer's email, and SUPPORT asks for a refund of
  two of its books, ₹1,900: the 202 and its change request. Finance: FINANCE opens Finance today and, from its
  refunds to approve, the refund of a seeded order (₹2,400, asked by SUPPORT through the approvals' own service). Then
  Home and reports, on a title at ₹1,234 and, of it, an
  order paid online with live keys and another made with test keys (₹999): the OWNER's Home counts the live order once
  (₹1,234, one order) and says test orders were left out, its card opens the sales report of the same days where the title
  is ₹1,234.00 and the whole period too, and the report's file holds the live order and who made it, no ₹999 and no
  email address. Then the Course module, on a learner who redeemed a book code of a print run made for the run: SUPPORT
  looks the code up (its plain text known to the seed alone), opens the learner's page from the answer, which says the
  view is logged, and the OWNER finds the `sensitive_read` in the learner's audit trail. Customers: the OWNER opens the
  customer's timeline (their order, its payment) and, opening it again, finds the logged view in the timeline's own rows
  and in the audit trail, then lists the children waiting.

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
  `policies_due` `[{policy, version}]`, `steps` (`passkey_required`: a dialog that holds the panel until a passkey is
  added on the website), `offer_end_sessions`); `POST session/reason/` (`{reason}`), `POST policies/ack/`
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
  `POST people/{id}/end-sessions/`, `reset-mfa/`, `offboard/`; `GET access-review/`. `GET people/roles/` (the role
  catalogue), `GET people/{id}/access/`, `POST people/{id}/roles/preview/` (`{role, action}`, as the grant form
  changes), `GET people/{id}/offboarding/` and `POST …/offboarding/tick/` (`{step, state, note}`),
  `GET people/{id}/erp/`; one's own sessions: `GET people/me/sessions/`, `POST people/me/sessions/{id}/end/`,
  `POST people/me/sessions/end-others/`.
- **Connections**: `GET connections/` and `connections/{provider}/` (the cards), `POST …/test/`, `…/credentials/`
  (`{mode, credentials, reason}`; a failed test is a 400 on `credentials`), `…/mode/`, `…/circuit/`;
  `GET …/webhooks/`, `POST …/webhooks/rotate/` (the token once); `GET …/events/` (`state`), `POST …/events/{id}/replay/`,
  `POST …/events/replay-failed/` (`{since}`); `GET …/calls/` (`operation`, `failed`); `GET …/failures/` (`state`,
  `operation`), `POST …/failures/{id}/replay/` and `discard/`. Each list has its own cursor in the page's address
  (`events_cursor`, `calls_cursor`, `failures_cursor`).
- **Templates**: `GET templates/` (`channel`, `language`, `approval_state`, `event`, `category`; not paged),
  `POST templates/`, `PATCH templates/{id}/` (always with its `event`, `channel` and `language`),
  `POST templates/{id}/test/` (`{variables}`: to one's own number or address).
- **Customers**: `GET users/` (`kind` students, parents or guests, `q`, filters: every row has its badges
  `age_band`, `consent_method`, `teacher`, `mfa_on` and `locked`; `kind=guests` answers another shape of row, orders
  by email address, which the console casts: `CustomerRow` is either), `GET users/{id}/` (opening it is audited; adds
  `parent_link` and `linked`), `GET users/{id}/timeline/` (`kind`, `before`: `{child, rows, next_before, withheld}`;
  a read of its own), `GET users/{id}/commerce/` (`shop.view_order`; a child's: counts only; a read of its own),
  `GET users/consent-pending/` (cursor), `POST users/{id}/consent/verify/` with `{method, evidence_ref, reason}`
  (`staff.verify_consent`, high), `POST users/{id}/reveal/` with `{show: ["email"], reason}` (answered `{email: …}`,
  audited and throttled), `suspend/`, `unsuspend/`, `unlock/`, `end-sessions/`, `reset-mfa/`, `password-reset/`,
  `resend-verification/` (429 beyond three links a day to one parent contact, 400 for a text out of hours);
  `POST users/{id}/impersonate/` with `{reason, ticket}` (answered `{token, expires_at}`: the console builds the
  website's link, `NEXT_PUBLIC_WEBSITE_URL/account/impersonate/?token=…`) and `POST users/{id}/impersonate/end/` with
  the token. The bulk actions are `POST jobs/` `{kind: "bulk_action", params: {action: "user.suspend" |
"user.unsuspend" | "user.end_sessions" | "user.resend_consent", targets: ["7101", …], payload: {}, reason},
dry_run}`: a dry run's `result` is `{outcomes: {valid, refused}, minors, approval}` (`approval`: the rule's words
  when the real run will wait for a second person, null otherwise).
- **Data protection**: `GET`/`POST data-requests/`, `GET`/`PATCH data-requests/{id}/`, `POST …/acknowledge/`,
  `verify-identity/`, `close/`, `GET …/response/`, `GET …/erasure-report/`, `POST …/erase/`, `POST …/export/`;
  `GET`/`POST incidents/`, `GET`/`PATCH incidents/{id}/`, `POST …/close/`; `GET`/`POST processors/`.
- **Legal and privacy** (`privacy/…`): `GET privacy/cockpit/` (every clock with the record behind it, the counts, the
  consents by the notice's version, the self-audit's state, the legal calendar), `GET privacy/retention/`;
  `GET`/`POST privacy/holds/` (`active`, `reason`, `target_type`, `user`; a hold on `user` or on `target_type` with
  `target_id`), `GET privacy/holds/{id}/`, `POST …/release/` with a reason; `GET privacy/nominees/{user}/` (the contact
  masked) and `POST …/reveal/` with a reason; `POST privacy/deletions/{id}/parent-confirmation/` with `evidence_ref`;
  `GET privacy/policies/`, `GET privacy/policies/{slug}/`, `GET …/versions/{number}/diff/`, `POST …/publish/`
  (`markdown`, `title`, `summary`, `effective_from`) and `POST …/cancel-scheduled/` with a reason;
  `GET`/`PUT privacy/disclosures/` (`{values: {KEY: value}, reason}`: the changed ones only);
  `GET`/`POST privacy/dark-pattern-audits/`, `PATCH …/{id}/` (the 13 `rows`, `certificate_text`, `effective_from`),
  `POST …/{id}/complete/`, `GET`/`POST …/{id}/file/` (the signed copy, multipart).
- **Notes**: `GET`/`POST notes/?target_type=&target_id=` (a record's notes, not paged; only on records the reader may
  see).
- **Tax** (the backend's `shop/staff_tax.py`): `GET tax/hsn/` (`q`, `kind`, `taxability`: the rate today, and
  `next_change`), `GET tax/hsn/{code}/` (`rates` oldest first with `until`, `linked` products with their `problem`),
  `POST tax/hsn/` (`{code, kind, description, uqc, first_rate}`: a nested rate's errors come as `first_rate.rate`),
  `POST tax/hsn/{code}/rates/` (a rate starts after the latest: the history is never rewritten); `GET tax/problems/`;
  `GET tax/documents/` (`kind` invoice or credit_note, `series`, `document_type`, `month`, `financial_year`,
  `cancelled`, `test`, `search`), `GET tax/documents/{number}/` (the number with dashes for its slashes, the row's
  `key`), `GET …/pdf/` (audited: it names the buyer), `POST …/cancel/` (`{reason}`, re-authenticated; refused for a
  document cancelled already and for an invoice whose credit notes stand); `GET tax/series/` (`financial_year`,
  `month`), `GET tax/thresholds/`, `GET tax/calendar/` (`month`); `POST tax/gstr1/` (`{month, months, dry_run}`,
  `months` 1 or 3: 202 with a `gstr1_export` job, followed through `jobs/`).
- **Orders** (API.md "Orders (staff)"): `GET orders/` (`tab`, `status`, `method`, `risk`, `hold`, `livemode`,
  `shipping`, `courier`, `tag`, `created_from`, `created_to`, `q`), `GET orders/{number}/` (the record: `actions` with
  the `primary` one, `refund` the dialog's facts, `timeline`; a number or an id), `POST orders/{number}/pack/`,
  `ship/`, `deliver/`, `release/`, `hold/`, `tags/`, `notify/`, `payment-link/`, `cancel/` and `offline-payment/` (a
  202 with a change request above the limit), `refunds/` (by line, by bank with the payee; 201 or 202, with an
  `Idempotency-Key`), `returns/`, `invoice/regenerate/` and `invoice/resend/`; its PDFs (`documents/packing-slip/`,
  `documents/label/`, `invoice/`, `credit-notes/{id}/`) opened as links; `GET orders/packing/`,
  `POST orders/pick-list/` (a PDF); `POST orders/` (a staff order: 201, or 202 and nothing made),
  `POST orders/preview/` and `GET orders/products/?q=` (its form); `GET orders/returns/`, `orders/returns/{id}/` and their moves (`approve/`,
  `decline/`, `label/`, `receive/`, `inspect/`, `photos/`); `POST orders/refunds/{id}/payee/` and `mark-paid/`
  (FINANCE); `GET orders/quotes/`, `orders/quotes/{id}/`, `POST orders/quotes/{id}/convert/`; bulk work as `POST jobs/`
  with `orders_pack`, `orders_print`, `orders_cancel` (250 at most) and `orders_export`. The saved views' `list_key`
  is `orders`.
- **Finance** (API.md "Finance (staff)"): `GET finance/today/`; `GET finance/payments/` (`status`, `method`, `stuck`,
  `created_from`, `created_to`, `livemode`, `q`), `GET finance/payments/{id}/`, `POST …/reconcile/` (Ask Razorpay
  again: `{paid, detail, changes, payment}`); `GET finance/offline-payments/` and `finance/refunds/` (`state`, `waiting`
  for the change requests; refunds' `method`); `GET finance/payment-links/` (`kind` order or invoice, `state`, `q`),
  `POST finance/payment-links/` (`{order | invoice, action: send | cancel}`),
  `POST finance/payment-links/invoices/{id}/reconcile/` and `…/posted/` (`{erp_name}`); `GET finance/settlements/`
  (`state`, `date_from`, `date_to`, `q`), `GET finance/settlements/{id}/`, `GET finance/settlements/{id}/lines/`
  (`matched`, `type`), `POST finance/settlements/{id}/match/` (`{line, payment | refund | accept, note}`),
  `POST finance/settlements/fetch/` (`{day, dry_run}`: 202 with a `settlement_fetch` job, followed through `jobs/`);
  `GET finance/documents/{number}/erp/` (the number with dashes for its slashes). The saved views' `list_key`s are
  `finance-payments`, `finance-refunds`, `finance-offline`, `finance-links` and `finance-settlements`.
- **The system**: `GET system/` (its `status` lines), `POST system/reconcile/` (an order's payment checked with
  Razorpay again), `GET system/sync/` and `system/sync/links/?q=`, `GET system/backups/`,
  `GET`/`POST system/backups/drills/`, `GET system/logs/`, `system/dependencies/`, `system/hardening/`,
  `system/scripts/`.
- **Settings' history**: `GET settings/{key}/history/`, `GET flags/{key}/history/`.
- **Content** (`content/…`, API.md "Content (staff)"; every list and record within the person's subjects):
  `GET content/summary/`; `GET`/`POST content/books/`, `GET`/`PATCH content/books/{id}/`; `GET content/papers/`,
  `GET`/`PATCH content/papers/{id}/`, `POST content/papers/{id}/publish/` (on the site or off, the open sample),
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
- **Support**: `GET support/tickets/` (`?tab`'s filters: `open`, `mine`, `unassigned`, `overdue`, `waiting`; and
  `q`, `category`, `priority`, `source`, `status`, `test`), `GET support/tickets/{number}/` (opening it is audited;
  its `sidebar` and `saved_replies` come with it), `POST support/tickets/` (log one), `PATCH support/tickets/{number}/`,
  `POST …/messages/` (`direction` `out` with its `channel`, or `note` with its `mentions`), `…/assign/`, `…/claim/`,
  `…/status/` (with the `closing_fields` it asks for), `…/reopen/`, `…/acknowledge/`, `…/reveal/` (`{show: ["email"],
reason}`), `…/refund/` and `…/cancel/` (with an `Idempotency-Key`; 202 a change request above the limit),
  `…/resend-invoice/`, `…/resend-confirmation/`, `…/extend-access/`, `…/book-code/`, `…/data-request/`;
  `GET support/tickets/{number}/attachments/{id}/` (a file, opened as a link); `GET support/summary/?days=30`,
  `GET support/agents/`; `GET POST support/saved-replies/` (`?bin=true`), `PATCH DELETE …/{id}/`, `POST …/{id}/restore/`;
  the grievance register as `POST jobs/` `{kind: "grievance_export", params: {from, until}}` and `GET
jobs/?kind=grievance_export&mine=true`.
- **Home and reports** (API.md "Home and reports (staff)"): `GET home/` (`?period=today|week|month`: the cards of the
  person's roles, each `{key, label, group, unit, value, definition, as_of, period, href, test_mode, comparison,
error}`), `GET reports/` (the index: `available`, `configured`), `GET reports/sales/` (`from`, `to`, `by`, `grain`),
  `reports/sales-by-place/` (`level`, `state`), `reports/codes/` (`batch`; `getCodesReport`),
  `reports/course-health/` (`subject`, `chapter`, `grain`), `reports/cod/`, `reports/settlements/` (`configured`, `note`), `POST reports/print-run/`
  (`{product, net_price, unit_cost, salvage}`); a report as a file is `POST jobs/` `{kind: "report_export", params:
{report, filters}}` (`staff.export_report`). The insights' own lists, which the reports draw and do not rebuild, are
  numbered pages (`count`, `?page=`) under `/api/v1/insights/` (`print-runs/`, `forecasts/?product=`, `cohorts/`) with
  `method`, `data_as_of`, `backtest` and `shown` beside the rows (the schema does not type those four: `InsightsAbout`
  in staff.ts); server components read them, the browser never does.
- **Catalogue** (API.md "Catalogue (staff)"): `GET catalogue/summary/`, `GET catalogue/options/` (the forms' choices;
  `hsn_codes` null for whoever may not read the master); `GET catalogue/products/` (`q`, `kind`, `published`,
  `stock`, `tax_problem`, `incomplete`, `category`, `collection`), `POST catalogue/products/` (201
  `{product, price_change}`), `GET`/`PATCH catalogue/products/{slug}/` (a slug or an id; a PATCH sends the changed
  fields alone, each part checked against its own permission; 200 the product, or 202 `{price_change, slug}` when the
  price waits, which the console reads from the answer, not as an error), `GET …/history/`, `GET …/prior-price/?price=`,
  `GET …/barcode.svg/` (an image on this origin), `PUT …/bundle/` (`{lines}`), `POST …/stock/`
  (`{stock, reason, expected}`), `POST …/pictures/` (multipart), `PATCH`/`DELETE …/pictures/{id}/`;
  `GET catalogue/stock/`, `GET catalogue/stock-alerts/`; `GET`/`POST catalogue/coupons/`, `GET`/`PATCH …/{code}/`
  (an `Idempotency-Key`; the change request: 201 or 200 when it ran, 202 `approval_required` when it waits),
  `GET …/{code}/codes/` (`used`), `GET …/{code}/history/`; the same for `catalogue/offers/` by id;
  `GET`/`POST catalogue/shipping-rates/`, `GET`/`PATCH …/{id}/`, `GET …/{id}/history/`; `GET`/`POST
catalogue/categories/` (the tree, not paged), `PATCH …/{slug}/`, `POST …/{slug}/move/` (`{target, position}`);
  `GET`/`POST catalogue/collections/`, `PATCH …/{slug}/`; `POST catalogue/import/` (multipart: 202 the dry run's job)
  and `POST jobs/` with `{kind: "product_import", params: {file, dry_run_job}}`, `{kind: "product_export", params:
{filters}}` or `{kind: "coupon_codes", params: {coupon, count, prefix, note}}`, each followed through `jobs/`.
- **Course** (`course/…`, API.md "Course (staff)"; within the person's subjects): `GET course/subjects/`,
  `GET course/subjects/{id}/outline/`, `PATCH course/chapters/{id}/` (`must_do`); `GET`/`PATCH course/revisions/{id}/`
  (`transitions`: the buttons), `POST …/submit/`, `approve/`, `needs-changes/` (`{comment}`), `publish/`
  (`{publish_at}`, null: now), `unpublish/` (`403 own_edit` for whoever submitted it); `GET`/`PATCH`/`DELETE
course/clips/{id}/`, `course/cards/{id}/`, `course/items/{id}/` (DELETE answers the bin's row), `POST …/move/`
  (`{to, target}`), `…/restore/`, `course/clips/{id}/retry/`; `GET course/bin/?kind=`; `GET course/items/` (the bank's
  filters), `GET course/items/{id}/history/`, `POST course/items/{id}/flag/` (`{note}`: `created` false when one is
  open); `GET`/`POST course/entitlements/` (`q`: a whole email address, recorded by its hash),
  `GET course/entitlements/{id}/`, `POST …/extend/` (`{days, reason}`), `…/revoke/` (`{reason}`);
  `GET`/`POST course/codes/batches/` (202 `{batch, job}`; `product` a slug, suggested by `orders/products/?q=`),
  `GET course/codes/batches/{key}/` (a label, or `~` and the id), `POST …/dispatched/` (`{at}`), `…/void/`
  (`{reason}`), `POST course/codes/void/` (`{code, reason}`), `POST course/codes/lookup/` (`{code}`; throttled),
  `GET course/codes/report/` (`getCourseCodesReport`: the Course module's own, whose columns differ from
  `reports/codes/`'s); `GET course/learners/{user}/` (a sensitive read: never prefetched),
  `POST …/devices/{id}/sign-out/`; bulk work as `POST jobs/` `{kind: "bulk_action", params: {action, targets,
payload, reason}, dry_run}` with `item_metadata`, `entitlement.grant`, `entitlement.extend` and `entitlement.revoke`,
  and a failed print run made again with `{kind: "code_batch", params: {batch}}`. The saved views' `list_key`s are
  `course-items`, `course-entitlements` and `course-batches`. The mock (`src/mocks/staff/course.ts`) holds every
  state these pages draw.
