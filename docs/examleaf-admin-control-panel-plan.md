# ExamLeaf Admin Control Panel: the plan

Date: 9 October 2026. Status: planned; the build starts with Phase A (section 9). The research behind the module
inventories is in `docs/research/2026-10-09-admin-control-panel/`; the inventory of what the backend already does
for staff is in section 2.

## 1. What it is, and the one rule

Three systems, one console each, kept in step:

1. **The platform (`examleaf-web`, Django)** stays the system of record for the product: accounts and consent,
   students' records, the books' content and solutions, the revision course, the storefront with its cart,
   checkout and payments. It is what students, parents and teachers use.
2. **ERPNext (open source, Frappe)** becomes the system of record for the business: parties (customers, schools,
   distributors, suppliers and printers), items and stock across warehouses, purchase orders and print runs,
   sales invoices and credit notes with GST through India Compliance, accounting and bank reconciliation, staff
   and payroll (Frappe HR), leads and deals (Frappe CRM), support tickets with SLAs (Frappe Helpdesk), analytics
   (Frappe Insights). It is packaged for Kubernetes beside the platform and customised for ExamLeaf by a private
   Frappe app (`examleaf_erp`): the book catalogue, print runs, book-code batches, schools, distributors,
   territories, price lists, GST templates, print formats, workflows, roles and dashboards.
3. **The Admin Control Panel (`examleaf-admin`, Next.js, at `admin.examleaf.in`)** is the staff console for the
   product side that ERPNext cannot see: students, parents, teachers and the links between them, consent and the
   data-rights queue, the books' content and errata, the course's chapters, clips, cards and quiz bank, QR and
   print runs, site settings and feature flags, staff roles and the audit trail, the health of the sync and of
   the system. It links into ERPNext for money, stock, tickets and people, and ERPNext links back.

**The sync** between the platform and ERPNext is one-directional per entity (each fact has one owner), event-driven
through an outbox with idempotency keys, retries and a dead-letter queue, reconciled nightly, and visible in the
panel. Staff sign in to both with the same identity (Google Workspace, domain-restricted) and the panel keeps their
roles in step.

The one rule: **the backend decides everything.** Every button calls an API that checks the person's role,
capability and scope, writes an audit event, and answers with the truth. The panel draws what the API answers and
never decides on its own (as the public site never decides what is open).

"Easy and smooth" means, concretely:
- one navigation, one search (`⌘K`), one inbox of things that wait for a person, one audit trail, and one sign-in
  for the panel and ERPNext;
- every list has saved views, filters, a column chooser, bulk actions with progress and undo where undo is
  possible, keyboard navigation and export;
- every record has a timeline (what happened, who did it, what they wrote), notes, and the related records one
  click away (the order's customer, the customer's course, the course's book code, the invoice in ERPNext);
- every dangerous action is reversible, or asks for a typed confirmation, or needs a second person;
- nothing waits on a page reload: edits save as you go, long jobs run in the background and report in the inbox;
- it works on a phone in the packing room (barcode scan, big buttons, offline-tolerant), and it reads in Assamese,
  Bengali and English;
- it is fast (lists stream, pages render on the server, interactions answer under 200 ms) and accessible (WCAG
  2.2 AA, the same bar as the public site).

Why ERPNext rather than building the ERP ourselves: accounting, GST filing, inventory valuation, purchase, payroll,
CRM and ticketing are solved problems with years of edge cases; ERPNext and its apps are open source (Frappe MIT,
ERPNext GPLv3), self-hosted, scriptable, with an India compliance app maintained for GST law as it changes. What
ERPNext cannot own is the product itself (the consent model, the content, the course, the storefront's checkout),
which stays where it is. The research behind the choice is `docs/research/2026-10-09-admin-control-panel/`.

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

### 3.1 The three systems and the boundaries

| Fact | Owner | Flows to | How |
|---|---|---|---|
| Accounts, consent, parental links, deletion requests, teachers' verification | platform | ERPNext (as Customers/Contacts, adults only; children appear as the parent's dependants without behavioural data) | outbox events |
| Content (books, papers, questions, solutions), the course (chapters, clips, cards, quiz) | platform | ERPNext knows only the saleable items | outbox events |
| Products' storefront presentation (slug, cover, description, SEO) | platform | ERPNext Item (code, HSN, GST template, price lists) | outbox events |
| Stock on hand per warehouse, purchase orders, print runs, goods receipts | ERPNext | the platform's `available` stock as a projection | ERPNext webhooks (Stock Ledger Entry) + nightly reconciliation |
| Checkout reservation while a payment is in flight | platform | not synced (released or sold within minutes) | existing `select_for_update` reservation |
| Orders, payments, refunds, shipments | platform (the storefront's state machine) | ERPNext Sales Order, Sales Invoice (the tax document), Payment Entry, Delivery Note, Credit Note | outbox events, idempotent by order number |
| GST invoice and credit note numbers and PDFs, e-invoice IRN, GSTR returns | ERPNext (India Compliance) after cut-over | the platform stores the number and the PDF for the customer's page | ERPNext webhook on submit |
| Quotes for schools and distributors | ERPNext (Quotation → Sales Order) | the platform shows the quote's status | webhook |
| Schools, distributors, territories, price lists, credit limits, statements | ERPNext | the platform's partner portals read them | REST, cached |
| Support tickets, grievances, SLAs | ERPNext Helpdesk (HD Ticket) | the platform's contact form creates the ticket and shows the number | REST at submit time, with a queued fallback |
| Staff identity, roles, 2FA | the platform (allauth) and Google Workspace | ERPNext Users and Role Profiles | the role-sync job |
| Accounting, bank reconciliation, payroll, expenses, assets | ERPNext | reports only | none needed |
| Analytics | ERPNext Insights over ERPNext's data; the panel over the platform's data; predictive jobs in the platform | each other through links | nightly exports |

### 3.2 The platform's `erp` app (the sync)

A Django app `erp/`: `ErpEvent` (the outbox: entity, key, payload, idempotency key, attempts, next try, state
pending/sent/failed/dead), a Celery worker that delivers events in order per entity through the ERPNext REST API
(token auth of a dedicated integration user, least privilege), exponential backoff, a dead-letter queue the panel
shows and can replay, `ErpLink` (the platform object ↔ the ERPNext document name), incoming webhooks from ERPNext
(signed, verified, idempotent by event id) for stock, invoice numbers and PDFs, quote and ticket status, and a
nightly reconciliation that compares both sides (customers, items, open orders, stock, invoices) and files
differences into the panel's inbox. A feature flag per flow (`ERP_SYNC_CUSTOMERS`, `ERP_SYNC_ORDERS`, `ERP_INVOICING`)
lets each cut over separately and roll back.

### 3.3 The ERPNext deployment and the custom app

ERPNext and its apps run from one custom image built with `frappe_docker` (`apps.json`: erpnext, india_compliance,
hrms, crm, helpdesk, insights, payments, print_designer, and the private `examleaf_erp`), deployed by the official
`frappe/helm` chart with its workers, scheduler, socketio and Redis, on the same Kubernetes cluster as the platform.
The database engine is decided by the facts in the research (section 3.6): ERPNext's own documentation and its India
app require MariaDB, so MariaDB runs beside the platform's PostgreSQL (both operated and backed up the same way);
the owner's wish for one engine is honoured where it can be (the platform, the panel and every new service stay on
PostgreSQL) and stated plainly where it cannot.

`examleaf_erp` carries, as fixtures and code: customer groups (Student's parent, Teacher, School, Distributor,
Bookseller), territories (Assam's districts, the North-East, the rest of India), item groups and the catalogue's
items with HSN 4901 (nil-rated printed books) and the taxable digital items, price lists (MRP, School, Distributor
tiers) and pricing rules, GST templates and the India Compliance settings for a single GSTIN in Assam, naming
series, the custom DocTypes (Book Title, Print Run, Book Code Batch, School, School Adoption, Distributor
Agreement), custom fields on Customer, Item, Sales Order and Sales Invoice (district, subject, print run, the
platform's ids), workflows (quotation approval, credit limit override, print-run approval), print formats (the GST
invoice, credit note, delivery challan, quotation, statement of account in the Answer Script look), Role Profiles
mirroring the panel's roles, webhooks to the platform, server scripts for validations, the Shiprocket connector
(courier accounts, AWB, labels, tracking webhooks, NDR, COD remittance) and Insights dashboards.

### 3.4 Kubernetes packaging

`deploy/kubernetes/`: one Helm umbrella chart (`examleaf-platform`) with the platform's Deployments (web, worker,
beat, media-worker, frontend, admin), PostgreSQL through the CloudNativePG operator (with continuous backups to
Cloudflare R2), MariaDB through the MariaDB operator for ERPNext (with scheduled backups to R2), Redis, the
`frappe/helm` `erpnext` chart as a dependency with our values and image, Ingress-NGINX with cert-manager, a
NetworkPolicy per namespace, PodDisruptionBudgets, resource requests and limits sized for one node to start,
Secrets through External Secrets (or SealedSecrets), CronJobs for backups and the reconciliation, and a `kind`
profile to run the whole stack on a laptop for tests. docker-compose stays for development.

### 3.5 Sign-in and sessions for staff

Unchanged where it is already right (allauth: email or Google Workspace sign-in on an allowlisted domain, the
authenticator app or a passkey required, 8-hour sessions, the device list, reauthentication before sensitive
actions), plus: Google Workspace SSO on ERPNext with the same domain restriction and its 2FA on; an absolute session
limit of 12 hours and an idle limit of 30 minutes on the admin host; a login alert email with device and place;
"log in as a customer" only with a reason, a 15-minute window, a banner, no access to payment or password actions,
and an audit event the customer can see on their own device list; API keys with scopes for integrations; offboarding
that revokes sessions, keys and the roles in both systems in one action.

### 3.6 The panel's frontend

- Shell: the sidebar of modules the person may use (from the capability manifest the session endpoint returns), the
  inbox count, `⌘K` search across students, orders, products, papers, chapters and settings and, through ERPNext's
  API, customers, invoices and tickets; the person's menu with their sessions and the "log in as" banner.
- Lists: server-rendered with cursor pagination, filters in the URL, saved views, column chooser, bulk selection with
  actions that run as a background job with progress, export; keyboard: `j`/`k`, `enter`, `/`.
- Records: a header with the status chip and the primary actions, a timeline (audit events, notes, emails sent,
  payments, shipments, the ERPNext documents), tabs for related data, inline editing with autosave for the fields
  that are safe to edit, a "danger" section at the end.
- Forms: the public site's field components; validation from the API (the error summary that links each field); busy
  states that send once; drafts kept in sessionStorage across a session that ends.
- Jobs: an imports/exports/bulk page with dry runs, progress, result files and errors per row.

### 3.7 Observability and operations

Celery queues and failed tasks with retry, the outbox and the dead-letter queue, ERPNext's own job queue, the webhook
logs (Razorpay, SES, MSG91, Shiprocket, ERPNext) with signature status and replay, outbound email and SMS
deliverability (sent, bounced, suppressed, daily caps), health (database, cache, storage, Razorpay, email, SMS,
ERPNext), backups (last run, size, restore test date, both engines), errors (Sentry), the status page. The panel
shows them; it never replaces them.

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
