# ExamLeaf Admin Control Panel: the plan

Date: 9 October 2026. Status: Phase A in progress in parallel worktrees (section 9). The research behind the module
inventories is in `docs/research/2026-10-09-admin-control-panel/`; the inventory of what the backend already does
for staff is in section 2.

## 1. What it is, and the one rule

Three systems, one console each, kept in step:

1. **The platform (`examleaf-web`, Django)** stays the system of record for the product: accounts and consent,
   students' records, the books' content and solutions, the revision course, the storefront with its cart,
   checkout and payments. It is what students, parents and teachers use.
2. **ERPNext v16 (open source, Frappe)** becomes the system of record for the business: the B2B parties
   (schools, distributors, booksellers, suppliers and printers) with their quotations, orders, invoices, credit
   limits, price lists, statements and dunning; items and physical stock across warehouses, with one Batch per
   print run; purchase orders and goods receipts; a mirror of every invoice and credit note the storefront issues,
   with the same number; payments and settlements; GST returns through India Compliance; accounting and bank
   reconciliation. It runs on MariaDB 11.8 (through mariadb-operator), because no supported ERPNext release runs
   on PostgreSQL (`research-erpnext.md` section 2); the platform, the panel and every new service stay on
   PostgreSQL 17, and the question is revisited when ERPNext v17 ships. It is packaged for Kubernetes beside the
   platform and customised for ExamLeaf by a private Frappe app (`examleaf_erp`): customer groups, territories,
   price lists, GST templates, the custom DocTypes (School Adoption, Distributor Agreement, Specimen Request,
   ExamLeaf Sync Log), custom fields, print formats, workflows, role profiles and the idempotent methods the sync
   calls. The apps are erpnext, india_compliance, offsite_backups and `examleaf_erp`; Frappe HR, Insights,
   Helpdesk and CRM are optional and decided in section 10.
3. **The Admin Control Panel (`examleaf-admin`, Next.js, at `admin.examleaf.in`)** is the staff console and the
   single front door. Its navigation lists every module (section 8). The modules the platform owns are built in
   the panel: students, parents, teachers and the links between them, consent and the data-rights queue, the
   books' content and errata, the course's chapters, clips, cards and quiz bank, book codes and QR, orders,
   shipping, support tickets, site settings and feature flags, staff roles and the audit trail, the health of
   the sync and of the system. The modules ERPNext owns open in ERPNext (deep links, the same Google identity),
   with summaries pulled through ERPNext's API where the research says that helps (section 5); ERPNext links
   back to the panel's records.

**The sync** between the platform and ERPNext is one-directional per entity (each fact has one owner), event-driven
through an outbox with idempotency keys, retries and a dead-letter queue, reconciled nightly, and visible in the
panel. Students' and parents' personal data stays in the platform: every storefront invoice goes to one ERPNext
customer, "Online Customers (B2C)", with the shipping state on the invoice. Book codes and course entitlements
never leave the platform. Staff sign in to both with the same identity (Google Workspace, domain-restricted) and
the panel's roles are mirrored to ERPNext role profiles.

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

Why ERPNext rather than building the ERP ourselves: accounting, GST filing, inventory valuation, purchase, credit
control and B2B selling are solved problems with years of edge cases; ERPNext and its apps are open source (Frappe
MIT, ERPNext and India Compliance GPLv3), self-hosted, scriptable, with an India compliance app maintained for GST
law as it changes. A private app that runs only on our servers owes nothing under the GPL, because its duties start
on distribution (`research-erpnext.md` 1.3). What ERPNext cannot own is the product itself (the consent model, the
content, the course, the storefront's checkout, the parcel's journey, the customer's tickets), which stays where it
is. The research behind the choice is `docs/research/2026-10-09-admin-control-panel/`.

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
| Accounts, consent, parental links, deletion requests, teachers' verification and class links | platform | **nothing is copied** (data minimisation under DPDP): every storefront invoice goes to one ERPNext customer, "Online Customers (B2C)", with the shipping state, place of supply and order number on the invoice; names and phones stay in the platform | none |
| Content (books, papers, questions, solutions), the course (chapters, clips, cards, quiz) | platform | ERPNext knows only the saleable items | outbox events |
| Book codes and course entitlements | platform | never in ERPNext; an ERPNext Batch carries only the code batch's label (e.g. PHY-2027-1) | none |
| Catalogue: products and bundles, their HSN/SAC and tax treatment, storefront presentation (slug, cover, description, SEO) | platform | ERPNext Item, Product Bundle and Item Tax Template link | outbox events, idempotent by `examleaf_ref` |
| Physical stock: receipts from printers, counts, transfers, returns, damaged stock; one Batch per print run | ERPNext | the platform's `available` stock as a projection (ERPNext bin quantity less copies reserved and not yet shipped) | ERPNext webhook as a doorbell on Purchase Receipt, Stock Entry and Stock Reconciliation, then the platform pulls the bin; a pull every 15 minutes; the stock invariant checked nightly |
| Checkout reservation while a payment is in flight | platform | not synced (released or sold within minutes) | existing `select_for_update` reservation |
| Storefront orders, payments, refunds, shipments (courier booking, tracking, NDR, RTO, COD remittance) | platform (the storefront's state machine; the `shipping` app drives the couriers) | ERPNext Payment Entry (with the Razorpay payment id), a Delivery Note against the invoice when the parcel leaves (stock out of the print-run batch), Razorpay settlements and COD remittances as Journal Entries | outbox events, idempotent by `examleaf_ref`; test-mode orders never sync |
| Storefront invoice and credit-note numbers and PDFs (`EL/…`, `CN/…`, and one series per document type from section 7) | platform (the legal document, issued at payment or dispatch as today) | ERPNext mirrors each document with the same name, created by `examleaf_erp`'s idempotent methods with `set_name`; Print Heading "Bill of Supply" when every line is exempt; credit notes as return Sales Invoices | outbox events |
| GST returns (GSTR-1, GSTR-3B, 2B and IMS), e-invoice IRN for B2B above ₹5 crore, e-way bills | ERPNext (India Compliance) after the cut-over | the platform's `export_gstr1` stays as the cross-check for the first quarter (section 10) | none |
| B2B quotations, orders, invoices, credit, statements, dunning, price lists and credit limits | ERPNext (Quotation → Sales Order → Delivery Note → Sales Invoice) | the platform's quote form files the request; the platform shows status where the website needs it, and keeps a read-only copy of the price lists the parent-pays channel applies | outbox event at submit; ERPNext webhook as a doorbell, then a pull |
| Schools, distributors, booksellers, territories, adoptions, agreements, specimen requests | ERPNext (Customer groups and the custom DocTypes) | the platform's teacher and school pages read what they need | doorbell and pull, cached |
| Support tickets, grievances and their legal clocks | platform (`support` app; Frappe Helpdesk is not installed, section 10) | none | none |
| Staff identity, roles, 2FA | the platform (allauth and the `staff` app) and Google Workspace | ERPNext Users and Role Profiles | the role-sync job (by hand under about 15 staff) |
| Accounting, bank reconciliation, purchases and expenses, assets, payroll if Frappe HR is chosen | ERPNext | reports only | none needed |
| Analytics and predictions | the panel's `insights` app over the platform's data; ERPNext's reports over its own; Frappe Insights over both later if chosen (section 10) | each other through links | nightly jobs |

### 3.2 The platform's `erp` app (the sync)

A Django app `erp/`: `ErpEvent` (the outbox: entity, key, payload, idempotency key, attempts, next try, state
pending/sent/failed/dead), written in the same database transaction as the order, invoice or refund it describes;
a Celery relay that delivers events in order per entity (item → invoice → payment → delivery) to `examleaf_erp`'s
own whitelisted methods (token auth of a dedicated integration user, least privilege, `restrict_ip`), honouring
HTTP 429 and `Retry-After`, with exponential backoff and a dead-letter queue the panel shows and can replay;
`ErpLink` (the platform object ↔ the ERPNext document name); incoming webhooks from ERPNext (HMAC-signed,
verified) treated as doorbells only, because Frappe tries each webhook three times and then gives up: the platform
re-reads the document through the API, and a pull every 15 minutes catches anything a lost webhook missed (stock,
B2B documents, partner records); and a nightly reconciliation that compares, day by day, the number and total of
invoices, the taxable and exempt split, the credit notes, payments by method and shipped quantities, checks the
stock invariant, and files differences into the panel's inbox (`research-erpnext.md` 5.2, 5.8). A feature flag per
flow (`ERP_SYNC_ITEMS`, `ERP_STOCK_FROM_ERP`, `ERP_MIRROR_INVOICES`, `ERP_SYNC_PAYMENTS`, `ERP_SYNC_DELIVERIES`)
lets each cut over separately and roll back (section 9).

### 3.3 The ERPNext deployment and the custom app

ERPNext v16 and its apps run from one custom image built with `frappe_docker` v4 (`apps.json`, pinned to tags and
passed as a BuildKit secret, since the old base64 build-arg is gone: erpnext, india_compliance, offsite_backups and
the private `examleaf_erp`, plus any optional app section 10 adopts: hrms, insights, helpdesk, crm). LMS,
Education, Webshop, Payments, Print Designer, Drive and Books are not installed: they duplicate the course or the
shop, keep Razorpay out of the platform, are not offered for v16, or are archived (`research-erpnext.md` 4.2). The
image is deployed by the official `frappe/helm` chart (8.0.84) with its gunicorn, three worker queues, scheduler,
socketio and two Valkey instances, on the same Kubernetes cluster as the platform. Upstream's `latest` tag is
`develop`, so every tag is pinned.

The database is MariaDB 11.8, run by mariadb-operator, because no supported ERPNext release runs on PostgreSQL: on
4 July 2026 a Frappe maintainer closed a v16 Postgres bug saying Postgres is supported on `develop` only;
transaction isolation is still open there; HRMS, CRM, Helpdesk and Insights have no Postgres CI at all; and even on
Postgres, Frappe would create its own database and role per site (`research-erpnext.md` section 2). The owner's
wish for one engine is honoured where it can be: the platform, the panel and every new service stay on PostgreSQL
17, both engines are operated and backed up the same way, and the question is revisited when v17 ships with India
Compliance tested on Postgres.

`examleaf_erp` carries, as fixtures and code (no Server Scripts in production, which are off by default since
v15):
- **Masters:** customer groups (Online B2C, School, Distributor, Bookseller) and the one B2C customer "Online
  Customers (B2C)" with one address per state that holds only the state; territories (Assam's districts, the
  North-East, the rest of India); item groups; Item Tax Templates ("Exempted" at 0% for printed books, HSN 4901,
  subject to the CA's choice of Exempted or Nil-Rated; "Taxable" at 18% for the course, SAC 999293); price lists
  (MRP, School, Distributor tiers, Teacher) and pricing rules; payment terms and dunning types; warehouses (main
  godown, damaged, at the printer, one per distributor for sale-or-return stock); naming series for the B2B
  documents, with prefixes that never collide with the platform's series; the India Compliance settings for a
  single GSTIN in Assam, with the audit trail switched on at setup (it cannot be switched off) and the address
  tax category taken from the shipping address. The items themselves arrive from the platform through the sync.
- **Custom DocTypes:** School Adoption, Distributor Agreement, Specimen Request and ExamLeaf Sync Log (the
  finance-side mirror of the outbox, modelled on Frappe's Ecommerce Integration Log, with resync). Print runs are
  core Batches with custom fields (edition, print date, printer, quantity, unit cost, the book-code batch label);
  schools and distributors are Customers with custom fields.
- **Custom fields:** a unique `examleaf_ref` on every synced doctype (Customer, Address, Item, Sales Invoice,
  Payment Entry, Delivery Note, Journal Entry, Specimen Request); the order number and the platform's ids on Sales
  Invoice; UDISE code, board, medium and enrolment on school customers; Udyam status on suppliers.
- **Methods the sync calls:** whitelisted and idempotent (look up `examleaf_ref` first and return the existing
  document; `insert(ignore_if_duplicate=True)` against races): upsert an item, mirror an invoice with
  `insert(set_name="EL/2026-27/00001")` so that ERPNext's name equals the legal number (the 16-character rule
  passes India Compliance's check), set Print Heading "Bill of Supply" when every line is exempt, mirror a credit
  note as a return Sales Invoice (never cancel and amend a GST invoice, whose `-1` suffix breaks the 16
  characters), post a payment, post a Delivery Note from the print-run batches, post a settlement or a COD
  remittance as a Journal Entry, open a specimen request or a lead from the platform's forms.
- **Behaviour:** `doc_events` validations (a B2B invoice to a registered buyer with both exempt and taxable lines
  is split into a tax invoice and a bill of supply; at most one exclusive distributor per district and line; the
  specimen allowance), scheduled jobs (the sale-or-return list at five months, renewals at the start of the year,
  the MSME 45-day alerts), workflows (quotation approval, credit limit override, print-run approval), print
  formats for the B2B documents (tax invoice and bill of supply, credit note, delivery challan, quotation,
  statement of account) in the Answer Script look, Role Profiles mirroring the panel's roles, and webhooks to the
  platform with a secret (doorbells only, section 3.2).

The courier integration (Shiprocket, and the manual flow that covers India Post) lives in the platform's `shipping` app,
not in ERPNext: the storefront owns the order's state machine, the parcel's timeline and the customer's messages, and
the sync books the Delivery Note in ERPNext when a parcel leaves so that stock moves there (research:
`research-integrations.md`, section 3).

### 3.4 Kubernetes packaging

`deploy/kubernetes/` (in progress): one Helm umbrella chart (`examleaf-platform`) with the platform's Deployments
(web, worker, beat, media-worker, frontend, admin), PostgreSQL 17 through the CloudNativePG operator (continuous
backups to Cloudflare R2), MariaDB 11.8 through mariadb-operator for ERPNext (a standalone instance, not Galera;
physical backups to R2 on a schedule, with point-in-time recovery from archived binlogs available if the six-hour
recovery point is not enough; `utf8mb4`, a buffer pool of about 60% of the pod's memory), Valkey, the `frappe/helm`
`erpnext` chart 8.0.84 as a dependency with our values and image, ingress-nginx with cert-manager, a NetworkPolicy
per namespace (ERPNext reachable only from the platform's namespace and the admin ingress), PodDisruptionBudgets,
Secrets through External Secrets (or SealedSecrets), CronJobs for backups and the reconciliation, and a `kind`
profile to run the whole stack on a laptop for tests. docker-compose stays for development (`examleaf-erp/` has its
own dev compose).

The ERPNext chart is current but thin (`research-erpnext.md` 3.1), so the umbrella chart patches its gaps:

| Gap in the chart | What we do |
|---|---|
| Every component has `resources: {}` | requests and limits per component from the research's sizing (gunicorn 0.5 vCPU / 1 GiB → 2 GiB; workers 256–512 MiB; MariaDB 1 vCPU / 3–4 GiB) |
| Probes only check open ports; workers and the scheduler only wait for the database and Valkey | HTTP probes on `/api/method/ping` for gunicorn and nginx; workers and the scheduler keep the chart's checks; liveness never tests the database |
| The backup Job writes only to the sites volume (the offsite push was removed in 2023), and there is no CronJob | our CronJob every 6 hours runs `bench --site all backup --with-files` and copies the files to R2; `site_config.json`, which holds the key that decrypts every stored password, is kept separately as a secret |
| Nothing runs `bench migrate` on `helm upgrade` | the chart's `migrate` Job (maintenance mode on, migrate, off) then `clearCache`, run as a pre-sync hook or a CI step on every upgrade, after a backup |
| The gunicorn HPA targets `apps/v2` (a bug) | no gunicorn HPA; one node does not need one |
| The sites volume defaults to RWX | ReadWriteOnce on the single node (local-path, or `kind`'s default class), which the chart allows on one node; RWX storage (Longhorn or NFS) only when a second node is added |
| The built-in MariaDB defaults to 10.6 (end of life 6 July 2026); the Bitnami subcharts are frozen on legacy images | neither is used: mariadb-operator runs 11.8 |
| `runAsNonRoot` and `readOnlyRootFilesystem` are commented out | set where the images allow it, tested in `kind` |

Sizing: the research puts ERPNext alone at 4 vCPU / 8 GB as a floor and 8 vCPU / 16 GB as comfortable, and today's
platform at 2 vCPU / 4 GB (`research-erpnext.md` 3.6, an estimate), so one node of at least 8 vCPU / 16 GB carries
both to start, with room for patch-day migrations when two image versions run side by side.

### 3.5 Sign-in and sessions for staff

On the platform, unchanged where it is already right (allauth: the authenticator app or a passkey required before
anything opens, 8-hour absolute sessions, the device list, reauthentication before sensitive actions), plus:
- Google Workspace sign-in for staff, with the server checking the ID token's `hd` claim and `email_verified` in the
  social-account adapter (the `hd` request parameter is only a hint), accounts linked by `sub`, never by email;
  allauth's MFA stage still runs after a Google sign-in (`research-integrations.md` 4.4, `research-rbac-security.md`
  2.1).
- A passkey or security key for OWNER, ADMIN and FINANCE; TOTP accepted for the other roles; no "trust this
  browser" for staff; login by emailed code refused for staff accounts.
- An idle limit of 15 minutes for OWNER, ADMIN, FINANCE and PACKER and 30 minutes for the others, on top of the
  8-hour absolute limit; step-up reauthentication through allauth's 401 flow before money, roles, keys, exports,
  reveals and impersonation (`research-rbac-security.md` 2.3).
- A login alert email for a new device or place, after 30 days dormant, and on MFA failures; the owner is told at
  once when a staff account is locked.
- "View as" a customer (read-only, rendered from the staff session) before any real impersonation; if full
  impersonation is ever built, it needs a reason and a ticket, a 15-minute window, a banner, no password, email,
  MFA, consent, payment, address or deletion actions, staff accounts are never targets, an under-18 account needs
  the owner's approval, and the customer is told.
- API keys with scopes, expiry and a sponsor for integrations; break-glass accounts outside SSO (section 4 and
  `research-rbac-security.md` 1.6).

On ERPNext (`research-erpnext.md` 5.4, 6.5):
- Google Workspace through a Social Login Key whose Google OAuth client has an **Internal** consent screen, so only
  accounts in our Workspace organisation can authorise; `sign_ups: Deny`, with users created beforehand; password
  login disabled for staff once SSO works.
- Email-link login switched off (it is on by default); session expiry cut from the 170-hour default to 8 to 12
  hours; two-factor authentication required per role; the lockout and password policy tightened (score 3 of 4).
- `Administrator` sealed as a break-glass account; the integration user `erp-sync@` holds a custom role with only
  the doctypes it writes, an API key kept in a Kubernetes Secret and `restrict_ip` (v16.33.0 or later, where an
  API-key bypass of `restrict_ip` was fixed).
- No customer or supplier portal, and Desk reachable only through the admin ingress (SSO plus an IP allowlist or
  VPN), so every authenticated-user bug needs a staff account first.

Offboarding is one action in the panel that ends the person's platform sessions and refresh tokens, disables their
ERPNext user (never deletes it, so audit links survive), removes their roles in both systems and revokes their keys.
Suspending their Google Workspace account stops new sign-ins but does not end sessions already open, which is why
the panel's step still matters (`research-integrations.md` 4.4).

### 3.6 The panel's frontend

- Shell: the sidebar of modules the person may use (from the capability manifest the session endpoint returns, with
  the ERPNext-owned entries opening in ERPNext), the inbox count, `⌘K` search across students, orders, products,
  papers, chapters, tickets and settings and, through ERPNext's API, B2B customers, quotations and invoices; the
  person's menu with their sessions and the "view as" banner.
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
ERPNext's `/api/method/ping` and its System Health Report), backups (last run, size, restore test date, both
engines), errors (Sentry or GlitchTip, section 10), the status page. The panel shows them; it never replaces them.

## 4. Roles, capabilities, scopes

### 4.1 Role templates (groups)

| Role | Who | May |
|---|---|---|
| OWNER | the founder (the superuser flag only on the break-glass accounts) | everything, including roles, keys, settings' history, the breach register |
| ADMIN | the operations head | everything except roles and keys (view only), approves what others ask |
| FINANCE | the accountant | payments, settlements, refunds (approve), invoices and credit notes, GST and tax masters, expenses, exports, read-only orders and customers |
| SALES | sales and school orders | storefront orders (phone and school orders, edit, cancel, payment links, request refunds), quotes, coupons and offers (drafts), prices and stock levels, customers; B2B quotations, orders, leads and adoptions in ERPNext; packing and shipping belong to PACKER and refund approval to FINANCE |
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
Static separation is checked when a role is granted (FINANCE never with PACKER, AUDITOR never with a role that
writes, MARKETING never with the approver of large discounts); dynamic separation per transaction (no one approves
their own request, the reviewer who publishes is not the last editor). When no second person is available, only
the owner may override, with a reason, an alert and a review afterwards (`research-rbac-security.md` 1.2).

Each role maps to an ERPNext role profile, mirrored by the role-sync job (`research-erpnext.md` 5.5): OWNER to
System Manager with Accounts Manager; ADMIN to a custom "EL Admin" (System Manager without Accounts Manager);
FINANCE to Accounts User and Accounts Manager with the India Compliance pages; PACKER to Stock User (Delivery Note,
Pick List, Stock Entry); SALES to Sales User, Sales Manager and Stock User, with a User Permission per territory if
needed; AUDITOR to Auditor, time-bound in the panel; INTEGRATION to the `erp-sync@` user. CONTENT_EDITOR, REVIEWER,
MARKETING, SUPPORT and TEACHER_PARTNER have no ERPNext access.

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
- Sessions: a 15-minute idle limit for OWNER, ADMIN, FINANCE and PACKER and 30 minutes for the others, the
  8-hour absolute limit that exists today, the device list with remote log-out, reauthentication before money,
  roles, keys, exports and impersonation; ERPNext sessions cut to 8 to 12 hours (section 3.5).
- Network: HTTPS only, HSTS, a strict CSP (scripts by nonce, no third-party hosts except Razorpay's dashboard
  links), `frame-ancestors 'none'`, an optional IP allowlist or VPN at Caddy, separate cookies from the public site.
- Authorization: capability and scope on every endpoint (deny by default), object-level filters in querysets,
  approvals for the dangerous actions, limits, rate limits per person, idempotency keys, no mass assignment (explicit
  serializers), typed confirmations for deletions.
- Audit: append-only hash-chained events with before/after, exported offsite nightly, searchable, alerts on
  sensitive actions; staff-action events kept 2 years and money-related events 8 financial years (the Companies
  Act's books, longer than GST's 72 months); CERT-In's 180 days rolling as the floor for logs today and DPDP's one
  year from 13 May 2027; clocks synced by NTP (`research-rbac-security.md` 3.4).
- Data protection (DPDP Act 2023 and its Rules): consent records with the policy version, verifiable parental
  consent, the data-principal rights queue (access, correction, erasure, grievance) with timelines, retention holds
  for finance and legal, erasure jobs that leave the audit trail intact, the breach register and the 72-hour
  notification playbook, children's data never used for tracking.
- Operations: backups with restore tests, secrets rotation, dependency scanning in CI, error tracking, feature
  flags with audit, maintenance mode, webhooks verified and replayable, outbound mail/SMS caps.
- ERPNext: patched every week, because GitHub lists 87 ERPNext advisories (8 critical) and 53 Frappe advisories
  (2 critical) so far in 2026 and most fixes land in the Tuesday releases for both v15 and v16; critical and high
  fixes within 7 days, through backup, new image tag, `helm upgrade`, the migrate Job and a cache clear, majors
  only after a staging run (`research-erpnext.md` 6.3, 6.6). Desk stays off the public internet, with no portal,
  Server Scripts off and `Administrator` sealed (section 3.5).
- Processors: India Compliance sends every GST API call (GSTIN checks, returns, e-way bills, later e-invoices)
  through Resilient Tech's server `asp.resilient.tech`, which relays to a GSP, so invoice and party data pass
  through a third party; it is recorded as a processor in the DPDP processor register, beside Razorpay, Amazon SES,
  MSG91, Shiprocket, Cloudflare R2, Google and the error tracker (`research-erpnext.md` 4.1,
  `research-rbac-security.md` 4.2). The B2C invoices it sees carry a state, not a name.
- Offboarding: suspending a Google Workspace account stops new sign-ins, not open sessions, so offboarding also
  ends platform sessions, disables the ERPNext user and revokes keys in one action (section 3.5).
- Testing: every capability has a test that the API refuses it to a role without it; every money action has a
  test for the approval path; the audit chain is verified by a nightly job.

## 7. Data model additions (summary)

RESEARCH_DATA_MODEL

## 8. The panel's information architecture

One navigation for both systems. Entries marked **[ERPNext]** open in ERPNext's Desk (deep links, the same Google
identity); entries marked **[both]** mix panel pages with ERPNext pages and say on each link which one opens; the
rest are built in the panel. Section 5 lists what each module does and where.

Home (today, what waits, money, parcels, learners; ERPNext summary cards) · Inbox (work, approvals, mentions) ·
Orders (all, to pack, shipped, returns, cancelled, drafts) · Customers (students, parents, guest buyers) ·
Catalogue (products, bundles, shelves, collections, prices and offers, coupons; B2B price lists **[ERPNext]**) ·
Inventory **[ERPNext]** (stock by batch and warehouse, print runs, purchase orders and receipts, movements, counts,
damaged stock; the panel shows cover and reprint alerts) · Shipping (to book, pickups and manifests, on the way,
exceptions, COD, costs, couriers) · Finance **[both]** (payments, refunds, invoices and credit notes, payment links
in the panel; settlements, bank reconciliation, purchases and expenses, receivables and payables, period close,
statements **[ERPNext]**) · Tax **[both]** (HSN and SAC with dated rates, bundle treatments, document series,
thresholds, updates, calendar in the panel; GSTR-1, GSTR-3B, 2B and IMS, e-way bills, e-invoices **[ERPNext]**) ·
Content (books, papers, questions, solutions, review queue, error reports and errata, QR, legal deposit, banners,
media, redirects) · Course (chapters, clips, flash cards, quiz bank and item statistics, book codes, entitlements,
learners) · Partners **[both]** (distributors, schools, adoptions, specimens, agreements, B2B quotations and orders
**[ERPNext]**; teachers, classes, school licences and school codes in the panel) · Marketing (templates, consent
ledger, segments, campaigns, testimonials, reviews) · Support (tickets, grievances, saved replies, help centre) ·
Legal and privacy (compliance cockpit, consents, data requests, policy versions, breach register, processors,
retention and holds) · Reports and analytics **[both]** (sales, tax, codes, course health, forecasts and print
runs, scores, B2B reports; accounting, stock and receivables reports **[ERPNext]**) · Staff (people, roles,
invitations, access reviews, API keys, sessions, offboarding) · Settings and integrations (site, flags,
connections, notifications, couriers, payment, messaging) · System (jobs, sync, webhooks, mail and SMS, health,
backups, audit log, logs, dependencies, status).

## 9. Phases

RESEARCH_PHASES

## 10. Risks and decisions for the founder

RESEARCH_DECISIONS
