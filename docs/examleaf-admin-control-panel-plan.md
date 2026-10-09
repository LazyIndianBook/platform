# ExamLeaf Admin Control Panel: the plan

Date: 9 October 2026. Status: planned; the build starts with Phase A (section 9). The research behind the module
inventories is in `docs/research/2026-10-09-admin-control-panel/`; the inventory of what the backend already does
for staff is in section 2.

## 1. What it is, and the one rule

One console for the whole business, at `admin.examleaf.in`, where every member of staff does their work: orders
and parcels, books and papers, the revision course, students and schools, money and GST, support, marketing,
the law's paperwork, and the system itself. It replaces the themed Django admin as the place staff live in; the
Django admin stays underneath as the raw-data escape hatch for superusers.

The one rule: **the backend decides everything.** Every button in the panel calls an API that checks the person's
role, capability and scope, writes an audit event, and answers with the truth. The panel draws what the API
answers and never decides on its own (as the public site never decides what is open). A capability the API
would refuse is not drawn.

"Easy and smooth" means, concretely:
- one navigation, one search (`⌘K`), one inbox of things that wait for a person, one audit trail;
- every list has saved views, filters, a column chooser, bulk actions with progress and undo where undo is
  possible, keyboard navigation and export;
- every record has a timeline (what happened, who did it, what they wrote), notes, and the related records one
  click away (the order's customer, the customer's course, the course's book code);
- every dangerous action is reversible, or asks for a typed confirmation, or needs a second person;
- nothing waits on a page reload: edits save as you go, long jobs run in the background and report in the inbox;
- it works on a phone in the packing room (barcode scan, big buttons, offline-tolerant), and it reads in Assamese,
  Bengali and English;
- it is fast (lists stream, pages render on the server, interactions answer under 200 ms) and accessible (WCAG
  2.2 AA, the same bar as the public site).

## 2. What exists today (the floor we build on)

The backend (`examleaf-web`, Django 6.1, DRF, allauth with MFA/passkeys/usersessions, axes, simple_history, Celery,
Razorpay, WeasyPrint invoices) already carries most of the business logic a panel needs:

- **Roles** are Django groups set from `accounts/roles.py` by `manage.py bootstrap_roles`: STUDENT, TEACHER,
  CONTENT_EDITOR, SALES, SUPPORT, ADMIN (ADMIN is everything but what only superusers may change: periodic tasks,
  groups, second factors, social apps). Staff must set up an authenticator app or a passkey before anything opens
  (`StaffMFAMiddleware`); staff sessions end after 8 hours; failed log-ins are counted by axes; every signed-in
  request is tracked by allauth.usersessions (the device list).
- **The Django admin**, themed, with an ops dashboard ("ExamLeaf at a glance": registrations, attempts, what
  waits, orders to pack, sales by day, stock running out), custom pages (the customer page, the Add order form for
  phone and school orders, the shipping and offline-payment action forms, the quotation PDF, the clip preview) and
  actions (mark packed/shipped/delivered, cancel, refund in full, email a payment link, record an offline payment,
  approve/reject reviews, verify/revoke teachers, put on/take off sale, set stock, publish/unpublish a revision,
  reprocess a clip, CSV exports of users, consent records and attempts).
- **Models**: 57 across accounts (User, TeacherProfile, ConsentRecord, DeletionRequest), content (Board, ClassLevel,
  Subject, Book, Paper, Question, Solution), shop (30: products, bundles, categories, collections, attributes,
  coupons, offers, shipping rates, PIN codes, addresses, carts, orders, items, discounts, payments, notes, refunds,
  shipments, reviews, invoices, credit notes, stock alerts, quote requests, webhook events), learn (12: chapters,
  revisions, clips, flash cards, quiz items, book codes, entitlements, learners, progress, attempts, reviews,
  devices), ops (email suppression, SMS log), practice (attempts, answer-sheet uploads), pages (legal pages with
  history).
- **Commands and jobs**: `export_gstr1`, `reconcile_payments`, `make_book_codes`, `export_qr`, `import_papers`,
  `build_covers`, `import_pincodes`, `seed_shop`, `upload_backup`, `reprocess_clips`, `build_quiz_items`,
  `import_chapter_insights`, `clean_old_history`; Celery for email (Anymail/SES with a suppression list), SMS
  (MSG91 with a daily cap), pictures, clips, backups, the 7-day account deletion.
- **Compliance already in the code**: GST tax invoices and bills of supply with financial-year series, credit
  notes, HSN per product, the seller's details from settings, GSTR-1 export, DPDP consent records with the privacy
  policy's version, verifiable parental consent by link, data export, deletion with a grace period, no third-party
  trackers.

What the panel adds is not business logic but **workflow, oversight and the missing modules**: a work inbox,
approvals, audit, scopes, saved views, search, dashboards, support tickets, CRM, campaigns, tax masters with
effective dates, settlements and accounting exports, DPDP requests, staff management, and the system views.

## 3. Architecture

### 3.1 A separate app on its own host

`examleaf-admin/`: a Next.js 16 app in this repository, built like `examleaf-frontend/` (TypeScript strict,
Tailwind 4, the Answer Script tokens in a denser "console" variant, the same lint/typecheck/Vitest/Playwright
pipeline), served by Caddy at `admin.examleaf.in` from its own container (`admin` service in docker-compose), with
`noindex`, a strict CSP, and an optional IP allowlist at Caddy. Why a separate app and host, not a route group of
the public site:
- a security boundary: its own origin, cookies and CSP; an allowlist or VPN can gate it; a bug in the public site
  cannot reach it and the panel's bundles never ship to the public;
- Django's own admin already occupies `/admin/` on the main host;
- the panel needs richer UI (data grids, editors, charts) and denser type that the public site's budgets forbid.

It talks to the same backend: allauth.headless for sign-in (`/_allauth/browser/v1/` proxied on the admin host),
and a new staff API (`/api/v1/staff/…`). The Django session cookie is scoped to the host, so a staff member signs
in on the admin host (passkey or authenticator app required, as today).

### 3.2 The staff API and the `staff` app

A new Django app `staff/` holds everything that is about running the business rather than the business itself:

- `staff/permissions.py`: **capabilities** (fine-grained, UI-meaningful: `orders.view`, `orders.pack`,
  `orders.refund`, `orders.refund.approve`, `catalogue.price`, `content.publish`, `course.entitle`,
  `customers.impersonate`, `finance.export`, `staff.roles`, …), **scopes** (an editor for Physics only; a packer
  for the Guwahati warehouse; a support agent for tickets only), **limits** (a refund up to ₹2,000 without
  approval), and the mapping from roles (Django groups) to capabilities. Django's model permissions stay the
  base layer; capabilities are checked by DRF permission classes on every staff endpoint; object scopes by
  queryset filters, never by hiding in the UI.
- `staff/audit.py` + `AuditEvent`: append-only (database rules forbid update and delete), hash-chained, with
  actor, action, target, before/after diff, reason, request id, IP, user agent, approval reference; written by
  every staff mutation through one service function, exported nightly to the backup bucket, searchable in the
  panel, kept 7 years for finance and never less than 180 days for anything.
- `Approval`: maker-checker for refunds above a limit, price changes, bulk deletions, role grants, exports of
  personal data, tax-rate changes; the approver is a different person; the inbox shows it; expiry after 7 days.
- `InboxItem` / `Notification`: everything that waits for a person (approvals, tickets, reviews, teacher
  requests, deletion requests, error reports, low stock, failed jobs, webhooks that failed, NDR parcels), with
  assignment, snooze and done; email digests.
- `SavedView`: a list's filters, columns and sort, per person or shared with a role.
- `SiteSetting` and `FeatureFlag`: effective-dated, audited, with history and a reason; what `config/` answers
  reads them (the shop open, cash on delivery, consent mode, the web course, maintenance mode, banners).
- `ApiKey`: per integration, scoped capabilities, expiry, last used, rotation.
- `StaffInvite`, `AccessReview`: invitations with a role and an expiry; quarterly reviews that list each person's
  capabilities and last use.
- Module models that do not exist yet (section 5): tickets, leads/deals/activities, campaigns, tax masters,
  purchase orders and stock movements, expenses and settlements, data requests and the breach register.

Every staff endpoint: `IsStaff` + the capability + the scope; cursor pagination; filters as query parameters
that saved views store; CSV export streamed; idempotency keys on mutations that money depends on; rate limits per
staff member; the audit event inside the same transaction as the change.

### 3.3 Sign-in and sessions for staff

Unchanged where it is already right (allauth: email or Google Workspace sign-in on an allowlisted domain, the
authenticator app or a passkey required, 8-hour sessions, the device list, reauthentication before sensitive
actions), plus: an absolute session limit of 12 hours and an idle limit of 30 minutes on the admin host; a login
alert email with device and place; "log in as a customer" only with a reason, a 15-minute window, a banner, no
access to payment or password actions, and an audit event the customer can see on their own device list; API keys
with scopes instead of a person's session for integrations; offboarding that revokes sessions, keys and the role in
one action.

### 3.4 The panel's frontend

- Shell: the sidebar of modules the person may use (from the capability manifest the session endpoint returns),
  the inbox count, `⌘K` search across orders, customers, products, papers, chapters, tickets and settings, the
  person's menu with their sessions and the "log in as" banner.
- Lists: server-rendered with cursor pagination, filters in the URL, saved views, column chooser, bulk selection
  with actions that run as a background job with progress, export; keyboard: `j`/`k`, `enter`, `/`.
- Records: a header with the status chip and the primary actions, a timeline (audit events, notes, emails sent,
  payments, shipments), tabs for related data, inline editing with autosave for the fields that are safe to edit,
  a "danger" section at the end.
- Forms: the public site's field components; validation from the API (the error summary that links each field);
  busy states that send once; drafts kept in sessionStorage across a session that ends.
- Jobs: an imports/exports/bulk page with dry runs, progress, result files and errors per row.
- Motion: none beyond the public site's rules; the panel is dense and still.

### 3.5 Observability and operations

Celery queues and failed tasks with retry, the webhook log (Razorpay, SES, MSG91) with signature status and
replay, outbound email and SMS deliverability (sent, bounced, suppressed, daily caps), health (database, cache,
storage, Razorpay, email, SMS), backups (last run, size, restore test date), errors (Sentry link), the status page.
The panel shows them; it never replaces them.

## 4. Roles, capabilities, scopes

### 4.1 Role templates (groups)

| Role | Who | May |
|---|---|---|
| OWNER (superuser) | the founder | everything, including roles, keys, settings' history, the breach register |
| ADMIN | the operations head | everything except roles and keys (view only), approves what others ask |
| FINANCE | the accountant | payments, settlements, refunds (approve), invoices and credit notes, GST and tax masters, expenses, exports, read-only orders and customers |
| SALES | sales and school orders | orders (place, edit, pack, ship, cancel; refunds up to the limit), quotes, coupons and offers, prices and stock, customers, leads and deals |
| PACKER | the packing room | the packing queue: pick, pack, print slips and labels, hand over to the courier; scan codes; nothing else |
| SUPPORT | support agents | tickets, customers (view, verify, unlock, resend emails, reset 2FA with approval), orders (view, request a refund), entitlements (open a course), data requests (queue), impersonate with a reason |
| CONTENT_EDITOR | authors and editors | books, papers, questions, solutions, errata, legal pages (draft), course content (draft); scoped by subject |
| REVIEWER | senior editors | publish and roll back content, approve edits, resolve error reports; scoped by subject |
| MARKETING | marketing | campaigns, coupons (draft), reviews moderation, banners, SEO fields, analytics |
| TEACHER_PARTNER | verified teachers with a school link (later) | their students' progress only (a public-site feature, not the panel) |
| AUDITOR | an accountant or lawyer, read-only | everything read-only, exports with approval |
| INTEGRATION | API keys | the capabilities the key names, no sign-in |

Separation of duties: the person who requests a refund, a price change or a role grant is never the person who
approves it; FINANCE approves money, ADMIN approves roles and exports, REVIEWER approves content.

### 4.2 Capabilities and scopes

Capabilities are named for the UI ("Can refund an order up to ₹2,000", "Can publish Physics content") and grouped
by module. Scopes narrow a capability to a subject, a board/class, a warehouse, a ticket queue or a customer
segment. Limits are numbers on a capability (refund amount, discount percent, export rows). The session endpoint
returns the person's manifest `{ capabilities: [...], scopes: {...}, limits: {...} }`; the panel draws from it; the
API enforces it on every call (`staff/permissions.py` is the single source, with tests that every endpoint names a
capability).

## 5. Modules (the inventory)

Each module lists what the panel does. "Exists" marks what the backend already has and the panel surfaces;
"adds" marks new logic (models, services, jobs). Priorities: **must** (Phase A/B), **should** (Phase C/D), **later**
(Phase E or when the business needs it). The research reports give the competitor references behind each line.

RESEARCH_MODULES

## 6. Security

- Sign-in: passkeys or an authenticator app for every staff member (phishing-resistant first), Google Workspace
  SSO on an allowlisted domain, NIST 800-63B password rules (length, breach check, no composition rules, no forced
  rotation), lockout by axes, login alerts.
- Sessions: 30-minute idle and 12-hour absolute limits on the admin host, the device list with remote log-out,
  reauthentication before money, roles, keys, exports and impersonation.
- Network: HTTPS only, HSTS, a strict CSP (scripts by nonce, no third-party hosts except Razorpay's dashboard
  links), `frame-ancestors 'none'`, an optional IP allowlist or VPN at Caddy, separate cookies from the public site.
- Authorization: capability and scope on every endpoint (deny by default), object-level filters in querysets,
  approvals for the dangerous actions, limits, rate limits per person, idempotency keys, no mass assignment (explicit
  serializers), typed confirmations for deletions.
- Audit: append-only hash-chained events with before/after, exported offsite nightly, searchable, alerts on
  sensitive actions, 7-year retention for finance, CERT-In's 180 days as the floor for logs, clock sync.
- Data protection (DPDP Act 2023 and its Rules): consent records with the policy version, verifiable parental
  consent, the data-principal rights queue (access, correction, erasure, grievance) with timelines, retention holds
  for finance and legal, erasure jobs that leave the audit trail intact, the breach register and the 72-hour
  notification playbook, children's data never used for tracking.
- Operations: backups with restore tests, secrets rotation, dependency scanning in CI, error tracking, feature
  flags with audit, maintenance mode, webhooks verified and replayable, outbound mail/SMS caps.
- Testing: every capability has a test that the API refuses it to a role without it; every money action has a
  test for the approval path; the audit chain is verified by a nightly job.

## 7. Data model additions (summary)

RESEARCH_DATA_MODEL

## 8. The panel's information architecture

Home (today, what waits, money, parcels, learners) · Inbox · Orders (all, to pack, shipped, returns, cancelled,
drafts) · Customers (students, parents, teachers, schools, segments) · Catalogue (products, bundles, shelves,
collections, prices and offers, coupons) · Inventory (stock, print runs, purchase orders, movements, counts) ·
Shipping (couriers, rates, labels, NDR/RTO, COD remittance) · Finance (payments, settlements, refunds, invoices,
credit notes, expenses, receivables, exports) · Tax (HSN and rates, effective dates, GST returns, updates, calendar)
· Content (books, papers, questions, solutions, errata, error reports, QR and print runs, legal pages, FAQ,
banners, media, redirects) · Course (chapters, clips, flash cards, quiz bank, entitlements, book codes, learners,
teachers, schools) · Marketing (campaigns, templates, segments, referrals, reviews, analytics) · Support (tickets,
contact messages, grievances, knowledge base) · Legal and privacy (consents, data requests, policy versions,
breach register, retention) · Reports · Staff (people, roles, invitations, access reviews, API keys, sessions) ·
Settings (site, flags, integrations, notifications, couriers, payment) · System (jobs, webhooks, mail and SMS,
health, backups, logs, status).

## 9. Phases

RESEARCH_PHASES

## 10. Risks and decisions for the founder

RESEARCH_DECISIONS
