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

One subsection per module of section 8. Each starts with the system that owns it and the roles that use it, then
a table of every capability the research marks must or should, and the notable later ones. The second column says
where the capability comes from: **exists** is backend behaviour the panel only has to surface (from `inventory.md`);
**adds** names the new model, service or job (section 7 has the fields); **ERPNext** names the doctype or feature
that does it, opened from the panel. References are to the research files by short name and section: `inv`
inventory.md, `lms` research-lms-crm-cms.md, `rbac` research-rbac-security.md, `gst` research-commerce-gst.md,
`b2b` research-b2b-predictive.md, `int` research-integrations.md, `erp` research-erpnext.md. Where two reports give
one item different priorities, the table takes the higher one and the report's own wording follows in brackets.

For the modules ERPNext owns, "must" means configured in ERPNext and used from the day ERPNext becomes the record
for that flow (the cut-over in Phase C, section 9); until then the platform's existing behaviour carries on (stock as
a number on the product, `reconcile_payments`, the GSTR-1 export, quotations by PDF).

Every list in every module follows section 3.6 (server-rendered, cursor pagination, filters in the URL, saved views,
column chooser, bulk actions as background jobs, export of what is shown, `j`/`k`/`enter`/`/`), and every record
has the header, timeline and danger section described there; the "Easy and smooth" notes say only what a module
needs beyond that.

### 5.1 Home

**Owner:** panel, over the platform's data, with summary cards pulled from ERPNext's API. **Used by:** everyone; the
cards depend on the role.

| Capability | Exists / adds / ERPNext | Priority | Reference |
|---|---|---|---|
| A home page per role with 4 to 8 cards: owner (net revenue, orders, codes redeemed, active learners), sales (to pack, quotes open), support (tickets due, breaches), content (reports open, flagged items) | exists: the admin index's "ExamLeaf at a glance", shop table, "Waiting" line and store stats (`ops/templatetags/dashboard.py`, `shop/templatetags/shop.py`); adds: cards drawn from the manifest, so a card shows only what the role may open (today's "Waiting" line is not gated and counts test orders) | must | lms 5.1; inv 2.2, 11.2 |
| One definition per metric (net revenue, active learner, completed clip, code redeemed), used everywhere and explained on hover | adds: `insights.metrics`, one function per metric, used by Home, Reports and exports | must | lms 5.1 |
| Test mode kept out of every number, and a TEST banner in a different colour whenever test data shows | exists: `Order.livemode`, the T-series; adds: the filter in every query and the banner | must | lms 6.4; inv 2.2 |
| "Data as of" on every card; cards computed overnight say so | adds | should | lms 5.1 |
| Comparisons with the previous period, the same weekday and last season, and annotations on exam dates, result day, print runs and price changes | adds: `insights.Annotation` | should | lms 5.1 |
| Season view: the default cards follow the trade's year (Apr to Jun close the season, Jul to Sep specimens and adoptions, Oct to Dec first orders and print runs, Jan to Mar reprints and collections) | adds | should | b2b 5 |
| ERPNext summary cards: receivables due and overdue, B2B quotes open, weeks of cover for the top titles | ERPNext: Accounts Receivable, Quotation and Bin through the REST API, cached | should | erp 5.1, 5.8; b2b 5 |
| Activity feed of recent staff actions | adds: from `staff.AuditLog` | should | lms 6.5 |
| System banners (yellow warning, red critical, each saying what to do; dismissed for the session): dead letters in the sync, a backup older than 26 hours, an integration's circuit open | adds | should | lms 6.5; rbac 3.6 |
| First-day checklist per role (five steps or fewer, ticked automatically) | adds | should | lms 6.6 |
| Weekly owner's email and threshold alerts (no orders in 24 hours in season, a refund spike, failed SMS, codes redeemed far above a printed run) | adds: Celery beat and SES | should | lms 5.7 |

**Easy and smooth:** every card is a link to the list it counts, already filtered; the page streams, so the cards
that are ready show first; on a phone the cards stack in one column with the packer's and support's queues first;
no chart needs a legend to be read.

### 5.2 Inbox

**Owner:** panel. **Used by:** everyone; items are routed by capability and scope, so a packer never sees a refund
approval.

| Capability | Exists / adds / ERPNext | Priority | Reference |
|---|---|---|---|
| One work inbox of what waits for a person: approvals, teacher requests, deletion requests, failed refunds, failed clips, the SMS cap reached, NDR cases, weight disputes, COD overdue, sync dead letters and reconciliation differences, low stock, quotes waiting, sale-or-return lines at five months, renewals due | adds: `staff.InboxItem` filled by signals and jobs (today staff hear of none of these; only SALES gets low-stock and quote emails) | must | inv 11.6; int 3.2, 3.8, 3.9; b2b 1.2, 2.2 |
| Approvals: each pending ChangeRequest shows the exact stored payload and its diff; approve or reject after step-up; expiry (24 hours by default) | adds: `staff.ChangeRequest` | must | rbac 1.5 |
| Owner alerts at once by email or SMS (privileged role grants, a new staff account, a staff MFA reset, break-glass, an impersonation, a refund or payout above the threshold, any export of children's data or of more than N rows, a break in the audit chain, a staff lockout, a spike in refused requests or webhook signature failures, maintenance mode on, no backup for 26 hours); everything else in a daily digest | adds | must | rbac 3.6 |
| Deadlines on items, sorted by due time (an NDR in 24 hours, a weight dispute in 7 working days, the legal clocks of Support and Legal) | adds | must | int 3.8, 3.9; lms 4.3 |
| Long jobs report here when they finish (imports, exports, bulk actions), with their result files | adds: `staff.Job` | must | lms 6.3 |
| Assignment and claim; an offboarded person's items reassigned in the same step | adds | must | rbac 2.9 |
| Mentions in notes, subscriptions to records one created or was assigned, snooze, an email digest only of unread items | adds | should | lms 6.5 |
| Bulk resolve, assign and snooze | adds | should | lms 6.3 |

**Easy and smooth:** fixed views per role from the first day (packer: paid, not packed; support: due today;
content: reports to triage; sales: quotes awaiting reply), personal views later (lms 6.2); the inbox count sits in
the shell; `g` then `i` opens it; each item opens its record in a side panel with the action buttons, and
resolving it moves to the next; a red clock on anything with a legal deadline.

### 5.3 Orders

**Owner:** platform: the storefront's order state machine, payments, refunds, invoices and credit notes. ERPNext
receives the mirrored documents; B2B orders for schools and distributors are ERPNext Sales Orders and open there
(section 5.12). **Used by:** SALES (orders, quotes), PACKER (to pack), SUPPORT (view, request refunds), FINANCE
(refund approval), ADMIN; AUDITOR reads.

| Capability | Exists / adds / ERPNext | Priority | Reference |
|---|---|---|---|
| Order list with saved views as tabs (all, to pack, shipped, returns, cancelled, drafts) and filters by status, payment method (Razorpay, COD, offline), courier, date, state and tag | exists: `OrderAdmin`, the Order state machine (pending → paid → packed → shipped → delivered; cancelled; refunded); adds: the staff API and the views | must | gst 1; lms 6.2; inv 3.8 |
| Universal search by order number, name, last digits of a phone, email, AWB, invoice number and book code; each lookup of a person written to the access log | adds: `⌘K` over the staff API | must | gst 1; lms 6.2 |
| Bulk actions: mark packed, print slips, invoices and labels, book a courier, export, cancel (at most 250 at once), with progress and undo where the action allows it | exists: the admin actions mark packed, shipped and delivered, and cancel; adds: bulk jobs | must | gst 1; inv 2.4 |
| Timeline and internal notes: events, staff comments with mentions and attachments, emails and SMS sent, shipments, the ERPNext documents; customer-facing notes kept apart | exists: `OrderNote` (signed), simple_history on Order and Payment (not viewable today); adds: the merged timeline | must | gst 1; inv 3.9, 11.3 |
| Staff orders by phone, WhatsApp or for a school, with a payment link or an offline payment | exists: `create_staff_order`, `send_payment_link` (15 days), `record_offline_payment`, the Add order form | must | gst 1; inv 4.1 |
| Controls against "one person can give goods away": a cap on staff discounts, approval of offline payments above a value and of ₹0 orders, a weekly list of grants for the owner | adds: limits on the capability and ChangeRequests | must | inv 10 (I6); rbac 1.5 |
| Drafts and quotes for the storefront, converted to an order and then invoiced | exists: `QuoteRequest` (QT-YYYY-NNNNN, GSTIN, discount, shipping) and `make_quotation`, with no conversion; adds: convert to a staff order; B2B quotes move to ERPNext | must | gst 1; inv 4.6, 11.7 |
| Cancellation before dispatch: void or refund, restock, reason, the customer's request; no cancellation fee unless ExamLeaf bears the same when it cancels | exists: `cancel_order`, stock released | must | gst 1, 6 |
| Refunds full or partial by line, with a shipping refund and a restock switch; to the original method (Razorpay normal or optimum) or, for COD and offline payments, to the bank account or UPI ID the customer chose, recorded; a reason; the customer told; the credit note issued automatically | exists: `start_refund` (Razorpay only), `Refund`, `CreditNote`, the refund webhooks; adds: partial lines, the COD and offline path (L11 is open), the `X-Refund-Idempotency` header, a warning on payments older than 6 months | must | gst 1, 6; lms 4.6; int 4.1; inv 10 |
| Refund requests: requested → approved or declined → initiated → processed or failed, with a second approver above the maker's cap; refund quantities start at zero | adds: a ChangeRequest kind | must | lms 4.5, 4.6; rbac 1.5 |
| Returns (RMA): request by the customer or staff, reason code, approve or decline, return label, receive and inspect, restock or damaged, refund or exchange; the duty to take back defective, deficient or late goods | adds: `shop.ReturnRequest`; ERPNext: the credit note's return Sales Invoice and the stock coming back into the sellable or damaged warehouse | must | gst 1, 6 (Rule 7(4)) |
| Exchanges: a credit note and a new invoice, or a zero-value swap with the stock movement recorded | adds | should | gst 1 |
| Order editing (lines, quantities, discount, shipping, collect the balance or refund it); once invoiced, a change is a credit or debit note | adds | should | gst 1 |
| Risk flags for COD: past RTOs by phone or address, the PIN code's RTO rate, first COD order, high value, a junk address; high risk means prepaid only or a confirmation first | adds: `insights` rules stored on the order | must | gst 1; b2b 4.8 |
| Address validation: PIN to district and state, phone required, landmark | exists: `PinCode`, `state_problem`; adds: the checks at checkout and on staff orders | must | gst 1 |
| COD confirmation hold until the buyer confirms by SMS or WhatsApp; duplicate-order detection (same phone or email and items within N hours, several open COD orders) | adds | should | gst 1 |
| Tags ("school", "awaiting reprint") and a fulfilment hold with a reason ("address issue", "payment check") | adds: tags through django-taggit (installed), hold fields | should | gst 1 |
| Partial fulfilment and backorders, several shipments per order | exists: `Shipment` is one-to-many; adds: the UI | should | gst 1 |
| Invoice from the order: the PDF emailed and a printed copy in the parcel (the carrier must hold an invoice or bill of supply when no e-way bill is needed) | exists: `generate_invoice` (on pay; COD on ship), WeasyPrint PDFs; adds: "regenerate" as a button (a RUNBOOK shell step today) | must | gst 1, 5.3; inv 10 |
| Mirror to ERPNext: the invoice under the same name, the payment, the Delivery Note at dispatch, the credit note; the order page shows each ERPNext document's link and sync state | ERPNext: Sales Invoice, Payment Entry, Delivery Note, return Sales Invoice, through the outbox | must | erp 5.6, 5.8 |
| Status messages (placed, paid, packed, shipped with the AWB, out for delivery, delivered, delivery failed, refunded, cancelled) by email, SMS and opted-in WhatsApp, never between 21:00 and 08:00, never with marketing | exists: `notify`, the SMS module, the tracking page `/orders/t/<token>/`; adds: the shipping events | must | gst 1; int 3.7 |
| SLA timers: unshipped after N days, a refund pending, a quote unanswered | adds | should | gst 1 |
| Back-in-stock requests | exists: `StockAlert`, emailed hourly | must | gst 1; inv 4.5 |
| Pre-orders for the next edition or a reprint (no stock taken, notified on arrival); a course pre-sale is taxed on the advance (section 5.9) | adds | should | gst 1, 5.7 |
| School and gift bulk orders on the storefront (many copies to one address, split by class, codes per student) | ERPNext for schools that order through Sales; the platform issues the codes | should | gst 1 |
| Order export with the GST fields | exists: `shop.export_order`, logged | must | gst 1; inv 1.2 |
| Packing queue with a pick list grouped by book and a packing slip (title, ISBN, quantity, school or class) | adds: print templates beside the existing invoice PDF (A4 invoice, packing slip, pick list; the 4×6 inch label comes from the carrier) | must | gst 1; lms 6.8 |
| Packer mode on a phone: one column, large targets, the scanner first, no sideways scrolling | adds | must | lms 6.7 |
| Scan to pack: the order's QR code on the slip, then each book's ISBN barcode (EAN-13); a wrong or extra book shows an error; then mark packed | adds: `BarcodeDetector` on Android Chrome, a JavaScript decoder on iPhones, or a USB or Bluetooth scanner that types | should | lms 6.8 |
| Abandoned-checkout reminders, only for adult accounts with marketing consent | adds | later (gst 1 says should; lms 3.5 records the decision against it because buyers may be minors) | lms 3.5; gst 1 |

**Easy and smooth:** the order page's header carries the one next action (Pack, Book, Refund) and the status chip;
mark packed is undoable for 5 seconds instead of asking "are you sure"; `x` selects, Shift extends, the bulk bar
sits at the bottom; Space peeks at an order without leaving the list (support on a call); a refund dialog shows the
Razorpay rules and the expected days by method before the agent confirms; the packer's phone view opens straight
on the scanner with large targets; a COD risk badge and an "awaiting reprint" tag show in the row,
not only on the record.

### 5.4 Customers

**Owner:** platform: students (mostly under 18), parents and guest buyers. They are never copied to ERPNext (section
3.1); schools and distributors are partners (section 5.12). **Used by:** SUPPORT, SALES, ADMIN; MARKETING sees
segments of consenting adults only; AUDITOR reads, masked.

| Capability | Exists / adds / ERPNext | Priority | Reference |
|---|---|---|---|
| One person page with a merged timeline: orders, payments, code redemptions, a course-use summary, tickets, emails and SMS sent, consent events, staff notes, staff actions on the account; for a minor a usage summary, not a trail of behaviour | exists: the customer page (`OrderAdmin.customer_view`), `ConsentRecord`, `SmsLog`; adds: the staff API and the timeline from `AuditLog` and history | must | lms 3.1; rbac 5 |
| Badges: email verified, phone verified, age band, parental consent state and method, teacher verification, MFA on, status (active, suspended, locked, pending deletion, erased) | exists: allauth `EmailAddress`, `login_phone_verified`, `is_minor`, `consent_pending`, `pending_deletion`, `TeacherProfile.verified` | must | rbac 5 |
| Contact details masked by default; reveal of contact, date of birth or parent contact with a reason, step-up, a throttle and a `sensitive_read` event | adds: `accounts.reveal_contact` | must | rbac 5 |
| Access log of who viewed a person, including `⌘K` lookups; opening a child's record or timeline is a `sensitive_read` | adds: `AuditLog` read events | must | lms 0, 6.2; rbac 4.3 |
| Account actions, each with its permission, step-up where the research says, a notification and an audit event: suspend and reactivate (ends sessions), unlock (axes), reset 2FA (owner approval when the target is staff), force a password reset (staff never set or see one) with "end all sessions", end sessions and devices | exists: axes, `allauth.usersessions`, the JWT blacklist, RUNBOOK shell recipes for unlock and MFA reset; adds: the actions | must | rbac 5, 2.3; inv 10 |
| Change email (a code to the new address, the old one told) | adds | should | rbac 5 |
| Parent consent: resend the link, the list of children waiting for a parent, verify by hand with a method and an evidence reference | exists: `send_parent_link` (7 days, 3 a day), a shell recipe for the pending list; adds: the actions and the list | must | inv 7, 10; rbac 5 |
| Personal-data export for an access request, sent only to a verified address | exists: `export_user_data` | must | rbac 5 |
| Notes on a person (personal data: they go into access exports; no health or other sensitive details; edit history) | adds: `staff.Note` | must | rbac 5 |
| Commerce summary for adult buyers: orders, lifetime value, average order, refunds and RTOs, addresses, tags | exists: the customer page | must | gst 3 |
| Bulk operations: asynchronous, a dry-run count first, row caps per role, approval above N, one audit event per row and one for the batch, never a bulk deletion of children's data without approval | adds | must | rbac 5 |
| Merge duplicates: a dry-run diff, orders, consents and entitlements moved, an id map kept, irreversible; never merged on a phone number alone, because siblings share a parent's | adds | should | lms 3.1; rbac 5 |
| "View as" a customer, read-only; full impersonation only with the guards of section 3.5 | adds | should | lms 6.4; rbac 2.7 |
| Device list per learner (last seen, platform) with "sign this device out" | exists: `learn.Device` (five newest kept), no staff view | should | lms 1.2 |
| Customer type (student, parent, teacher, guest) and tags | adds | should | gst 3; lms 3.1 |
| No predictive lifetime value, RFM groups or churn scores on students | a rule, not a feature | must (as a decision) | lms 5.3; b2b 4.1 |

**Easy and smooth:** search by email or the last four digits of a phone; tabs for students, parents and guest
buyers; a minor's page carries a banner "Under 18: every view is logged"; a masked field reveals in place after the
reason is typed, and stays revealed for the step-up window only; the actions sit in the danger section with the
consequence written beside each.

### 5.5 Catalogue

**Owner:** platform: products, bundles, storefront prices, coupons and offers, the tax treatment of each product.
Items sync to ERPNext; B2B price lists and pricing rules live in ERPNext. **Used by:** SALES (prices, stock levels),
CONTENT_EDITOR (product pages, SEO), MARKETING (coupon and offer drafts), FINANCE (tax fields, approval of large
price changes).

| Capability | Exists / adds / ERPNext | Priority | Reference |
|---|---|---|---|
| Products, bundles that take stock from their components, categories, collections, attributes, shelves | exists: `Product` kinds (sample papers, solutions, bundle, digital), `BundleItem`, `Category`, `Collection`, `ProductType`, `Attribute` | must | gst 2; inv 3 |
| MRP and selling price, shown as "MRP (incl. of all taxes)" with the saving; the total price with its breakup (delivery, tax) before checkout | exists: `mrp`, `price`, `ShippingRate`; adds: the breakup check | must | gst 2, 6 (Rule 7(1)(e)) |
| Price history per product and, from 1 January 2027, the "prior price" (the lowest price in the 30 days before a reduction was announced) beside every reduced price | adds: simple_history on Product (missing today) and the prior-price query | must | lms 0, 3.5; inv 3.9 |
| Price changes above a set percentage or below cost, and coupons or offers above a set discount, need an approver | adds: ChangeRequest kinds | must | rbac 1.5 |
| Coupon rules: percent or fixed, minimum spend, products and categories in or out, per-customer and total limits, first order, stacking; bulk single-use codes per school | exists: `Coupon` (percent or fixed, minimum order, dates, maximum uses, per customer); adds: bulk single-use codes | must | gst 2; lms 3.5 |
| Scheduled prices and automatic offers, combinable or not | exists: `Offer` with dates and a combinable flag | should | gst 2 |
| Shipping rules by zone, weight and PIN, a free-shipping threshold, any COD fee shown before checkout | exists: `ShippingRate` (states, fee, free above) | must | gst 2; lms 0 |
| HSN or SAC chosen from the master; taxability and rate come from the master by date; a warning when a product disagrees with it | exists: `hsn_code` as free text (default 4901) and `gst_rate` per product; adds: the master of section 5.9 | must | gst 2, 5.15 |
| Tax treatment per bundle: split lines with apportioned prices (recommended), composite at the principal supply's rate, or mixed at the highest rate, with the CA's decision recorded | adds: `Product.tax_treatment` | must | gst 0.2, 5.2 |
| ISBN-13 with a checksum, one per format, and an EAN-13 barcode | exists: the `isbn` field; adds: validation and barcode output | must | gst 2, 6 |
| Weight and dimensions for every physical product (a flyer by default), which the courier quote needs | exists: `weight` (defaults to 0); adds: required non-zero weight, dimensions | must | int 3.4 |
| Dark-pattern guardrails in the tools: "only N left" only from real stock, a countdown only with a real end date, no pre-ticked add-ons, every fee shown before checkout, no guilt-trip copy | adds: validation in offers and banners | must | lms 0; gst 6 |
| History on coupons, offers and shipping rates | adds: simple_history (missing today) | must | inv 3.9, 11.3 |
| Import and export of products with a preview and a confirm step | exists: django-import-export (ADMIN only) | must | lms 6.3; inv 1.2 |
| Sync to ERPNext: item code, HSN, Item Tax Template, Product Bundle, idempotent by `examleaf_ref` | ERPNext: Item, Product Bundle, Item Tax Template | must | erp 5.8 |
| B2B price lists and trade discounts (distributor, school and teacher tiers, quantity slabs, validity) | ERPNext: Price List, Pricing Rule, Promotional Scheme | must | b2b 1.2; erp 4.3; lms 3.7 |
| Spreadsheet-style editing of price and stock levels (arrow keys, ranges, invalid values block saving; about 30 products a screen) | adds | should | lms 6.3 |
| Editions (2026-27 against 2027-28) with a successor and clearance of the old one | adds: `Product.edition` | should | gst 2 |
| SEO fields with a search-result preview (warnings past 70 and 320 characters) | exists: SEO fields; adds: the preview | should | lms 2.7 |
| MRP and "Country of origin: India" on the page; the Legal Metrology declarations if the rules apply to sets (to be verified) | adds | should | gst 6 |

**Easy and smooth:** the product page groups its fields into sections (more than five inputs means sections) with a
contextual save bar rather than autosave; the tax panel shows the rate the master gives for today's date and the
next change if one is scheduled; editing a price shows the prior-price rule's effect before saving; bulk price
edits run as a dry run first.

### 5.6 Inventory [ERPNext]

**Owner:** ERPNext: warehouses, one Batch per print run, receipts, transfers, counts, damaged stock, valuation,
purchases from printers. The platform's `available` is a projection. The panel shows cover, reprint alerts and the
projection's health, and opens ERPNext for everything else. **Used by:** SALES and PACKER (levels, receipts,
counts), FINANCE (valuation), ADMIN; ERPNext's Stock User and Stock Manager.

| Capability | Exists / adds / ERPNext | Priority | Reference |
|---|---|---|---|
| Stock on hand per warehouse and batch; the platform's available stock as ERPNext's bin less copies reserved and not yet shipped | exists: `Product.stock` (one number, reserved under `select_for_update`), `set_stock`; ERPNext: Bin, Warehouse; adds: the projection and its pull | must | erp 5.8; gst 2 |
| Print runs as batches: batch number, edition or reprint, printer, print date, quantity, unit cost; the base for valuation and recalls | ERPNext: Batch with custom fields | must | gst 2; erp 4.3 |
| The print run's book-code batch label (e.g. PHY-2027-1) on the ERPNext Batch; the codes themselves never leave the platform | exists: `BookCode.batch`; ERPNext: a custom field | must | erp 4.3, 5.8; lms 1.7 |
| Adjustments with reasons (count, damaged, specimen or promotion, received, return restock, theft or loss, correction) and full history; the GST stock account includes free samples and losses | ERPNext: Stock Entry and Stock Reconciliation with reasons | must | gst 2, 5.16 (Rule 56(2)) |
| Stock movement ledger, every movement with its source document | ERPNext: Stock Ledger | must | gst 2 |
| Damaged and returned stock in its own bucket, written off with a reason | ERPNext: a damaged warehouse | must | gst 2 |
| Valuation, FIFO or weighted average (the CA chooses), at each period end | ERPNext: the item's valuation method | must (at year end) | gst 2 |
| Nightly stock invariant (bin less reserved equals the platform's available) with differences in the inbox | adds: `erp` reconciliation | must | erp 5.8 |
| Inventory report: on hand by batch and location, valuation, movements, ageing, sell-through, days of cover before the exams | ERPNext: Stock Balance, Stock Ageing; adds: cover from `insights` | must | gst 7 |
| Purchase orders to the printer and the paper supplier, partial receipts, matched to the bill | ERPNext: Purchase Order, Purchase Receipt, Purchase Invoice | should | gst 2; erp 4.3 |
| Landed cost (freight, and the GST that cannot be claimed back on exempt books) in the unit cost | ERPNext: Landed Cost Voucher | should | gst 0.1, 2; erp 4.3 |
| Job work: paper sent to the printer on a delivery challan, books received, wastage; inter-state job work needs an e-way bill whatever the value | ERPNext: Subcontracting Order or Stock Entry with a challan; India Compliance e-way bill | should | gst 2, 5.10 |
| Cycle counts with variances reviewed and approved | ERPNext: Stock Reconciliation | should | gst 2 |
| Reorder points tuned to the exam season, and weeks-of-cover alerts | exists: `low_stock_report` at 08:00, `SHOP_LOW_STOCK`; ERPNext: reorder levels; adds: alerts from the forecast (section 5.16) | should | gst 2; b2b 4.2 |
| Inventory states: available, committed, unavailable, incoming | ERPNext: Stock Reservation, Purchase Order; the projection | should | gst 2 |
| Stock held by distributors on sale or return | ERPNext: one warehouse per distributor | should | b2b 1.2 |
| Specimen copies and legal-deposit copies issued as free-sample movements on a delivery challan | ERPNext: Delivery Note or Stock Entry from a Specimen Request, with the challan print format | should (b2b 2.2 makes specimens must, section 5.12) | gst 2, 5.6, 6 |
| Stock by location (at the printer, a school depot, in transit) | ERPNext: warehouses | later | gst 2 |
| No Serial Nos for book codes (each copy would carry a serial bundle on every stock line) | a rule | must (as a decision) | erp 4.3 |

**Easy and smooth:** the panel's Inventory entry opens a summary page (cover per title against the exam date,
reprint triggers, the last reconciliation, links into ERPNext's stock pages) rather than a copy of ERPNext's
screens; receiving a print run and counting stock happen in ERPNext on a phone (Stock Entry by barcode); an
invariant difference opens an inbox item that names the batch and the order lines involved.

### 5.7 Shipping

**Owner:** platform: the `shipping` app (in progress) drives the couriers through one carrier interface with a
manual implementation (which covers India Post) and a Shiprocket one; Delhivery comes later. ERPNext receives the
Delivery Note when a parcel leaves and the stock that comes back. **Used by:** PACKER, SALES, SUPPORT (cases),
FINANCE (COD and costs).

| Capability | Exists / adds / ERPNext | Priority | Reference |
|---|---|---|---|
| One carrier interface (quote, book, label, schedule pickup, manifest, cancel, track, NDR action, parse webhook) with `manual` and `shiprocket` implementations from the first day | exists: the counter flow (staff type the courier and the number; tracking URL templates; 17TRACK fallback); adds: `shipping.carriers` | must | int 0, 3.1 |
| Shipment data: carrier, our shipment status, external order and shipment ids, courier id, our stored label, weight and charged weight, dimensions, quoted rate, COD amount, last event, pickup location, outcome and RTO reason | exists: `Shipment` (courier, tracking number and URL, shipped and delivered times); adds: the fields | must | int 3.2; b2b 4.8 |
| The parcel's timeline: each scan stored once under a digest of AWB, code, date and activity | adds: `shipping.ShipmentEvent` | must | int 3.2, 3.6 |
| Courier choice: serviceability for the PINs and weight, couriers without COD dropped for COD orders and blocked or ODA ones dropped, the cheapest courier rated 4 or more within N days first, the top three shown with rate, ETD, rating, COD and RTO charge, staff override, the chosen quote stored; India Post's price beside them for prepaid orders | adds | must (gst 1 says should for multi-courier) | int 3.4; gst 1 |
| The packing room: scan the order, weigh, one photograph on the scale with the label side up, Book (idempotent: external ids are never created twice); the label fetched once and kept; pickups grouped by date with the courier's cut-off; the manifest and a handover scan of every parcel; cancel until "Out for Pickup", after that only an RTO | adds | must | int 3.5 |
| Tracking by webhook first: the `x-api-key` token compared in constant time (current and previous), the raw body stored with its SHA-256, 200 at once, processing in a task; tracking re-read by AWB before delivered, returned or lost, because the webhook is unsigned; mapping on the shipment status table, never the order table | adds: `/api/hooks/parcel-events/` (no "shiprocket", "sr" or "kr" in the URL) | must | int 0, 1.7, 3.6 |
| Polling as the net: every 2 hours, open shipments without an event for 6 hours, in batches of 50; five days without movement opens an inbox item | adds | must | int 3.6 |
| Customer messages per event by email, SMS (DLT template) and opted-in WhatsApp, linking to our own tracking page; COD "keep ₹X ready" on out-for-delivery; no marketing; nothing between 21:00 and 08:00 | exists: the tracking page; adds | must | int 3.7 |
| Failed deliveries (NDR): an inbox item with the reason, the attempts and a 24-hour deadline; the customer's link to pick a date, fix the phone or address, or cancel; staff call (outcome logged), re-attempt, dispute a fake attempt with proof, or return | adds | must (gst 1 says should) | int 3.8; gst 1 |
| RTO: "returning" warns; "returned" means scan the parcel back in, judge it sellable or damaged, restock through the stock movement, refund a prepaid order or reship it, record the cost (forward freight, RTO freight, the COD charge reversed) | adds; ERPNext: the return into the sellable or damaged warehouse | must (with COD) | int 3.9; gst 1 |
| COD remittance: an expected row on delivery (the order total, delivered plus 10 working days, or D+2 to D+4 with Early COD less its fee), checked daily against `remittance_status`, overdue by 2 working days or a different amount to the inbox; the bank credit matched by UTR | adds: `shipping.CodRemittance`; ERPNext: the remittance as a Payment Entry or Journal Entry | must (with COD) | int 3.9; gst 1, 4 |
| Serviceability survey before launch: every PIN of the North-East districts asked once, a table of PINs with no COD courier and with no courier at all (those go by India Post) | exists: `PinCode` with districts; adds: a job and the table | must | int 2.4 |
| Reliability: retries with backoff and jitter, errors returned with a 200 treated as failures, a circuit breaker per account, a dead-letter list with Replay and Discard, timeouts (5 s connect, 20 s read, 3 s for the live quote with the last good answer cached 10 minutes) | adds: the `integrations` app (section 5.18) | must | int 3.1, 3.10 |
| Test mode: a fake carrier answering from recorded fixtures for CI and staging (Shiprocket has no sandbox), and a live smoke test that books a prepaid parcel to our own address, fetches the label, cancels before pickup and checks the reversal; test orders never reach a courier | adds | must | int 0, 3.10 |
| Weight disputes: fetched daily, an inbox item due 7 working days after it was raised, our weight and photograph beside the courier's | adds | should (gst 1 says later) | int 3.9; gst 1 |
| Cost per order and per courier from the wallet statement, the wallet balance with a low-balance alert | adds: `shipping.ShipmentCharge` | should | int 3.9 |
| Delivery-time statistics (median and P90 days by courier and district), the median as the expected date at checkout, "late" past P90 | adds: `insights` | should | b2b 4.9 |
| India Post tariff table with effective dates (Book Post; Gyan Post once the postal division confirms in writing) | adds: `shipping.CarrierTariff` | should | int 2.2, 3.4 |
| PIN directory page (last import, rows, PINs added and removed, the delivery flag next to serviceability) and blocked PINs pushed to Shiprocket | exists: `import_pincodes`; adds: the page | should | int 4.8, 2.4 |
| Returns and exchanges booked as carrier return orders; until they are frequent, created in Shiprocket's panel with the return AWB recorded on the order | adds | should | int 3.9 |
| Courier performance report (days to deliver by courier and state, NDR and RTO rates, cost per parcel) | adds | should | gst 7; int 3.8 |
| 17TRACK registration for parcels sent by hand; Delhivery direct; India Post's bulk-customer API | adds | later | int 2.2, 2.7, 3.6 |
| Shiprocket's Engage 360, Fastrr checkout, Sense and its MCP server are not used | a rule | must (as a decision) | int 1.12 |

**Easy and smooth:** five screens that follow the parcel (to book, pickups and manifests, on the way, exceptions,
COD), with costs and couriers behind them (int 3.11); the booking screen pre-selects the recommended courier so
the common case is one tap; the packer's phone screen is scan, weigh, photograph, Book; when Shiprocket's circuit
is open the screen says "Shiprocket unavailable since 10:42, 7 calls waiting" and offers the manual flow; every
exception carries its deadline and the customer's latest answer.

### 5.8 Finance [both]

**Owner:** both. The platform owns payments (Razorpay, COD, offline), refunds, the storefront's invoices and credit
notes, payment links and the Razorpay feeds; ERPNext owns the books: the chart of accounts, settlements and COD
remittances as entries, bank reconciliation, purchases and expenses, receivables and payables, B2B statements and
dunning, period close, the audit trail. **Used by:** FINANCE, ADMIN, OWNER; AUDITOR reads; SUPPORT sees payments and
can accept a dispute but not refund.

| Capability | Exists / adds / ERPNext | Priority | Reference |
|---|---|---|---|
| Payments list with Razorpay ids, method and status, the late-authorised case (a "failed" payment can turn authorised for up to 3 days), offline references; stuck payments found | exists: the Payment state machine, `reconcile(order)`, `reconcile_payments --older-than 10`, `WebhookEvent` idempotency | must | int 4.1; inv 4.2 |
| Offline payments recorded, with approval above a set value | exists: `record_offline_payment`; adds: the limit and the ChangeRequest | must | inv 10 (I6); rbac 1.5 |
| Refund approvals: FINANCE approves above the maker's cap after step-up; refunds go to the original method unless the customer agrees to another (RBI); the site states its refund timelines | adds | must | rbac 1.5; gst 6 |
| Invoices and credit notes: PDF, resend, regenerate, the series and number, the ERPNext mirror's state | exists: `Invoice`, `CreditNote`, `pdf_view`, `generate_invoice`, `generate_credit_note`; ERPNext: Sales Invoice and its return under the same name | must | inv 2.3, 4.3; erp 5.6 |
| Razorpay settlement reconciliation: the recon API's payments, refunds and adjustments with fee, tax, settlement id and UTR, matched to orders; unmatched items to the inbox; the settlement posted as a Journal Entry (Razorpay Clearing to the bank, fees as an expense, the GST on fees as common input credit) | adds: the settlement fetch in `integrations`; ERPNext: Journal Entry through the outbox | must | gst 4; int 4.1; erp 4.3, 5.8 |
| Gateway fee accounting: 2% plus 18% GST on the fee | ERPNext: the settlement entry | must | gst 4 |
| COD remittance reconciliation: courier statement against AWBs, freight and COD-fee deductions, open COD receivable | adds: `shipping.CodRemittance`; ERPNext: Payment Entry | must (with COD) | gst 4; int 3.9 |
| Payment links: create, resend, cancel; for B2B invoices too, created by the platform because Razorpay stays there | exists: `send_payment_link`; adds: links for ERPNext invoices | must | int 4.1; erp 4.2 |
| Chart of accounts for a publisher: book sales (exempt) and course sales (18%), output and input CGST, SGST and IGST, ITC reversal, RCM payable, TDS payable, inventory of books and of paper at the printer, deferred course revenue, Razorpay clearing, COD in transit, courier payable | ERPNext: the India standard chart plus fixtures for the extra accounts | must | gst 4; erp 4.3 |
| Purchase and expense bills with the GST split, a Rule 42 tag per line (non-business, exempt only, blocked, taxable only, common), a reverse-charge flag and the bill attached | ERPNext: Purchase Invoice with India Compliance; the Rule 42 tag as a custom field if India Compliance has none (to be checked) | must | gst 4, 5.13 |
| An audit trail that cannot be switched off (Companies (Accounts) Rules from FY 2023-24; GST Rule 56(8) log of every edit or deletion) | ERPNext: India Compliance's audit trail, switched on at setup; the platform's `AuditLog` and history | must | gst 4, 5.16; erp 4.1 |
| Period lock and year close | ERPNext: Accounting Period, Period Closing Voucher | must | gst 4 |
| MSME vendor alerts: Udyam-registered micro and small suppliers paid by the agreed date (at most 45 days) or within 15 days without an agreement; a late payment is deductible only when paid | ERPNext: supplier custom field and an `examleaf_erp` job | must | gst 4, 6 |
| Payouts to authors or affiliates and changes to a payee's bank account: always two people, a cooling period, the payee told | ERPNext: Payment Entry with a workflow | must (once payouts exist) | rbac 1.5 |
| Automatic entries from events (sale, credit note, shipping, gateway fee, COD remittance, RTO cost) | ERPNext: the mirrored documents and entries | should | gst 4 |
| Bank reconciliation with statement import and matching rules | ERPNext: Bank Reconciliation Tool | should | gst 4; erp 4.3 |
| Receivables and payables ageing | ERPNext: Accounts Receivable and Payable | should | gst 4 |
| Disputes queue by deadline: accept, or contest with evidence before `respond_by` (the parcel's timeline is the shipping proof) | adds: Razorpay disputes in `integrations` | should | int 4.1 |
| Financial statements (profit and loss, balance sheet, cash flow, trial balance, day book) | ERPNext: v16's Schedule III templates | should | gst 4; erp 4.1 |
| Deferred course revenue recognised over the access period, with a roll-forward (the policy is the CA's) | ERPNext: Deferred Revenue on the course item | should | gst 4; erp 4.3 |
| TDS on vendor payments (printers, authors, professionals, rent), rates and thresholds configurable since s.393 of the Income-tax Act 2025 replaced the 194 series | ERPNext: Tax Withholding Category | should | gst 4, 6; erp 4.1 |
| Expense categories with receipts | ERPNext: Purchase Invoice or Journal Entry (Expense Claim if Frappe HR is installed) | should | gst 4 |
| Fixed assets and depreciation | ERPNext: Asset | later | gst 4 |
| A Tally or Zoho export for the accountant | none while ERPNext keeps the books; a Tally XML export only if the CA must keep Tally (section 10) | later | int 4.5; gst 4 |

**Easy and smooth:** Finance in the panel is a page of what needs FINANCE today (refunds to approve, unmatched
settlement items, COD overdue, disputes by deadline, sync differences) with links into ERPNext for the ledgers; an
order's page shows its fee, GST on the fee and settlement UTR once matched; every approval shows the stored payload
and asks for step-up once per window, not per click.

### 5.9 Tax [both]

**Owner:** both. The platform owns what decides the tax on a storefront document: the HSN and SAC master with dated
rates, the bundle treatments, the billing state, the document types and series, and the threshold and calendar
watch. ERPNext's India Compliance owns the returns and the government APIs after the cut-over. **Used by:**
FINANCE, OWNER; AUDITOR reads; the CA through ERPNext's Auditor role.

| Capability | Exists / adds / ERPNext | Priority | Reference |
|---|---|---|---|
| HSN and SAC master: code, description, taxability (taxable, nil, exempt, non-GST) and rate history (effective from and to, notification and serial number); products point to it and the rate is looked up by date, not typed | exists: `hsn_code` free text and `gst_rate` per product, copied onto each order line; adds: `shop.HsnCode` and `shop.HsnRate`; ERPNext: GST HSN Code and Item Tax Templates | must | gst 5.15, 2; erp 4.1 |
| The rates that apply seeded with their sources: printed books 4901, 4903 and maps 4905 exempt; notebooks 4820 exempt from 22 Sep 2025; e-books 5%; the revision course 18% (SAC 999293); job-work printing 5%; paper and board 18%; courier and gateway fees 18% | adds: fixtures | must | gst 0.1, 5.1 |
| Document type by content: tax invoice, bill of supply, or one invoice-cum-bill of supply (Rule 46A) for a mixed cart to an unregistered buyer; registered buyers buy through Sales in ERPNext, where a mixed sale becomes two documents | exists: "Tax invoice" whenever a line is taxed (`shop/invoices.py`); adds: the Rule 46A title and the rule; ERPNext: the `examleaf_erp` split | must | gst 0.3, 5.3 |
| Mandatory fields (Rule 46): recipient details for an unregistered buyer at ₹50,000 or on request, HSN digits by turnover (4 up to ₹5 crore), place of supply with the state, reverse charge yes or no | exists mostly; adds: the checks | must | gst 5.3 |
| One series per document type (tax invoice, bill of supply, invoice-cum-bill of supply, credit note, debit note, receipt and refund vouchers), each at most 16 characters, gapless under concurrent requests, rolled over on 1 April, never reused; a cancelled document keeps its number; the test series excluded; the Table 13 register (from, to, total, cancelled per series) | exists: one `EL` series for invoices and bills of supply, `CN` for credit notes, `T` and `TC` for tests, 16 characters; adds: `shop.DocumentSeries` and the register | must | gst 5.4; erp 8 |
| Billing state captured at checkout, so a course-only order has a place of supply (the address on record, else Assam) | adds: `Order.billing_state` | must | gst 0.4, 5.5 |
| Shipping follows the goods it carries: shipping on books is exempt like them, and a course has nothing to ship (today `export_gstr1.top_rate` taxes shipping at the cart's highest rate); a COD fee treated like shipping (to be verified) | adds: the allocation | must | gst 5.2 |
| A cart-level coupon allocated pro rata across lines and shown on each, which sets the taxable value of the course line in a mixed cart; per-line tax-inclusive arithmetic rounded to the paisa, any invoice round-off on its own line | exists: tax-inclusive per line; adds: the allocation | must | gst 5.6 |
| Credit notes: linked to the original invoice with its rate and place of supply; blocked after 30 November following the year; for registered buyers the tax falls only once the buyer reverses the credit, tracked in IMS | exists: credit notes linked to refunds; adds: the cut-off; ERPNext: IMS actions | must | gst 5.8 |
| GSTR-1 complete: B2B, B2C large, B2C small by state and rate, credit notes to registered and unregistered buyers, Table 8 exempt supplies, the HSN summary split B2B and B2C, Table 13 | exists: `export_gstr1` (B2C, HSN and credit-note CSVs); ERPNext: India Compliance's GSTR-1 (generate, compare with the portal, upload, file with OTP, lock after filing) over every mirrored and native document; until the cut-over, the export gains the missing sections in the Offline Tool's CSV templates | must | gst 5.11, 5.12; int 4.6; erp 4.1 |
| GSTR-3B, whose liability comes from GSTR-1 and cannot be edited since July 2025 (inter-state B2C by state locked too), with ITC from 2B through IMS less the Rule 42 reversal | ERPNext: India Compliance | must | gst 5.11 |
| Exempt against taxable turnover and the Rule 42 working: D1 and D2 every month, the annual true-up by the September return | ERPNext: a report in `examleaf_erp` over the tagged purchases | must | gst 5.13, 7 |
| Threshold monitor on rolling FY aggregate turnover, exempt book sales included: ₹2 crore (GSTR-9), ₹5 crore (e-invoicing, leaving QRMP, 6-digit HSN), ₹10 crore (the 30-day IRP limit); B2C large invoices at ₹1 lakh; consignments that may need an e-way bill at ₹50,000 | adds: a nightly job and a card | must | gst 0.5, 5.15 |
| Records and retention: stock account, advances, tax register, document registers, the edit log; no hard deletion of orders, invoices or credit notes for 72 months after the annual return's due date (FY 2025-26 to 31 Dec 2032), even on an erasure request | exists: PROTECT on tax records, no delete on orders, anonymisation on deletion; ERPNext: its registers and audit trail | must | gst 5.16; rbac 3.4 |
| GSTIN capture and check for schools and dealers (format and checksum offline; the GST portal's taxpayer search by a person; API autofill later, which spends credits) | exists: `validate_gstin`; ERPNext: India Compliance's offline check | must | gst 3; b2b 1.2; erp 4.1 |
| Rate changes: the time of supply across a change (invoice, supply and payment either side), credit notes at the original rate, open carts, staff drafts and quotes repriced on the effective date | adds: a job | should | gst 5.15 |
| Tax updates log: source (CBIC notification or circular, GST Council, GSTN advisory, IRP or e-way bill news, Assam SGST), issue and effective dates, affected HSNs or forms, a one-line summary, action, owner, status, linked product changes (there is no official feed, so it is a manual review) | adds: `shop.TaxUpdate` | should | gst 5.15 |
| Due-date calendar with reminders: GSTR-1 or IFF, GSTR-3B, PMT-06, GSTR-9, the 30 November cut-off, the Rule 42 true-up, quarterly TDS returns; QRMP dates if the CA chooses it (section 10) | adds | should | gst 5.11, 5.15 |
| ITC register and the 2B and IMS reconciliation (matched, missing, rejected) | ERPNext: India Compliance purchase reconciliation | should | gst 5.13, 7 |
| Reverse-charge register (royalties and copyright, goods transport, imported services, advocate fees, rent from an unregistered landlord) with self-invoices and payment vouchers (entries to be confirmed with the CA) | ERPNext: India Compliance reverse charge | should | gst 5.13 |
| E-way bills: none for 4901, 4903 or 4905 at any value; inter-state job work always; the exempt value left out of a mixed consignment; the bill of supply carries the exemption reason because couriers may still ask above ₹50,000 | ERPNext: India Compliance e-way bill, configured | should | gst 5.10; int 4.6 |
| Receipt and refund vouchers for course pre-sales (Rules 50 and 51), Table 11A and 11B | adds | later (only if pre-sales start) | gst 5.7 |
| E-invoicing (IRN and signed QR) for B2B tax invoices and notes once turnover passes ₹5 crore; never for B2C or bills of supply | ERPNext: India Compliance e-invoice, off until then | later | gst 5.9; erp 4.1; int 4.6 |
| GSTR-9 and 9C | ERPNext | later | gst 5.11 |

**Easy and smooth:** Tax opens on a calendar of what is due this month and what the threshold monitor says, with
the latest tax updates underneath; a product whose rate disagrees with the master shows a red chip in the catalogue
list; the GSTR-1 comparison (India Compliance's figures against the platform's export, table by table) is one page
that FINANCE signs off before filing during the first quarter after the cut-over.

### 5.10 Content

**Owner:** platform. **Used by:** CONTENT_EDITOR (scoped by subject), REVIEWER (publish, roll back, triage),
SUPPORT (reads error reports), MARKETING (banners, SEO), ADMIN.

| Capability | Exists / adds / ERPNext | Priority | Reference |
|---|---|---|---|
| Markdown and LaTeX editor with a live preview through the site's own KaTeX pipeline: bad LaTeX shown in red in the preview (`throwOnError: false`), refused on save (`true`), `trust: false`, error text escaped | exists: Markdown in stock admin textareas, a preview only for clips; adds | must | lms 2.1 |
| Diagrams with alt text required, or a "decorative" tick | adds | must | lms 2.1 |
| History with a readable side-by-side diff and restore | exists: simple_history on Book, Paper, Question, Solution and Page; adds: the diff on `diff_against` | must | lms 2.2 |
| Draft, published and "changed since publish" for questions and solutions (an edit goes live at once today) | exists: `Paper.is_published`; adds: a draft state | must | lms 2.2; inv 3 |
| Author → checker → publish: every change to a published solution goes through a second person, and the reviewer who publishes is not its last editor | adds: the review workflow and the REVIEWER role | must | lms 2.3; rbac 1.2 |
| "Report a mistake" on every solution, quiz item and clip: one tap, a category, an optional note and email, the paper, question, step and printing prefilled from the page or the QR route; Turnstile and rate limits | adds: `content.ErrorReport` | must | lms 2.4; b2b 3.2 |
| Triage queue: reported → confirmed or rejected → fixed online → fixed in printing N; items flagged by item analysis join the same queue; reports from verified teachers marked | adds | must | lms 2.4, 1.5; b2b 3.2 |
| Import from the books repository as a background job: pick the subject and the commit, a dry run with created, updated, unchanged and unmatched labels, then Apply; history kept because only what changed is written | exists: `import_papers` (command line; it hard-deletes removed questions); adds: the page and the job | must | lms 2.5, 2.2; inv 5 |
| QR codes print an address we control (`SITE_URL/s/<CODE>/`) that the site can redirect later | exists: `export_qr` refuses plain http and localhost | must | lms 2.6 |
| Legal deposit: one copy of every book and edition to the four public libraries named in the Delivery of Books Act (the 30-day deadline to be verified), recorded per title as a free-sample movement with a challan and proof of dispatch | adds: `content.LegalDeposit`; ERPNext: the stock movement | must | gst 6 |
| ISBN per format checked when a book or edition is created (a new ISBN for a substantial change, not for an unchanged reprint) | exists: `isbn` on the product; adds: the check | must | gst 6 |
| No FAQ or practice-problem rich-result editor (Google stopped showing both in 2026) | a rule | must (as a decision) | lms 2.7 |
| Accessible maths (HTML and MathML, never images) | exists: KaTeX's default output | should | lms 2.1 |
| Step-structured solutions, each step with its marks | exists: the marking-scheme steps in the text; adds: steps as blocks | should | lms 2.1 |
| Autosave for long text, and a soft lock with take-over when two editors open one solution | adds | should | lms 2.2 |
| Assignment queue per author; comments pinned to a field or a phrase, with resolve | adds | should | lms 2.3 |
| Scheduled release of a batch ("the 2027 solutions go live on launch day") | adds: Celery beat | should | lms 2.3 |
| Imports arrive as drafts when a page is already published | adds | should | lms 2.5 |
| Tell the reporter when the fix is published; named credit for verified teachers; a public errata page per book and printing | adds | should | lms 2.4; b2b 3.2 |
| QR registry: per paper the code, the target, the printings it appears in, scans per day as totals; error correction Q for codes near the spine | adds | should | lms 2.6 |
| Print-run view per book: codes printed and redeemed by week, QR opens per paper, the mistakes reported against that printing and the errata published for it, so a reprint decision is made on one page | adds: joins the ERPNext Batch label to the platform's codes and reports | should | lms 7, 2.6 |
| Question health: the share answered right, the discrimination, the reader reports and the edit history in one row | adds | should | lms 7 |
| Redirects table, filled automatically on a slug change and read by the Next.js proxy (no redeploy per redirect) | exists: `SlugHistory` in the shop; adds: `pages.Redirect` | should | lms 2.7 |
| SEO fields with a preview; a "hide from search" switch feeding the robots tag and the sitemap | exists: `robots.ts` and `sitemap.ts` in code; adds | should | lms 2.7 |
| Banners with start and end dates, the end date required so "sale ends Sunday" cannot outlive Sunday | adds: `pages.Banner` | should | lms 2.8, 0 |
| Media library with tags, a focal point, "used in" and replace everywhere | exists: product pictures (AVIF, WebP); adds | should | lms 2.8, 1.1 |
| Visual maths input, OCR of scanned back-catalogue papers, A/B tests of copy (adult-facing pages only) | adds | later | lms 2.1, 2.8 |

**Easy and smooth:** source on the left and the rendered solution on the right, refreshed as the editor types;
reviewers work from one queue of "waiting for me" with the diff open; reporting a mistake from the public page takes
one tap and lands in triage already linked to the question, the step and the printing; a typed confirmation guards
a deletion of an edition or a paper, an undo guards a publish.

### 5.11 Course

**Owner:** platform. Book codes and entitlements never leave it. **Used by:** CONTENT_EDITOR and REVIEWER (the
course's content, scoped by subject), SUPPORT (entitlements, codes, the learner page), SALES (code batches for
school orders), ADMIN.

| Capability | Exists / adds / ERPNext | Priority | Reference |
|---|---|---|---|
| Outline page per subject: chapter → revision → clips, cards and quiz items, with kinds, durations, status chips, free-preview badges, counts and row actions | exists: the models with `order` fields, edited in stock admin forms | must | lms 1.1 |
| Reorder without dragging: drag handles plus "Move to…" (first, before X, after X, last), because WCAG 2.5.7 needs a single-pointer path | adds | must | lms 1.1 |
| Draft, review and scheduled publish for a revision or a whole chapter | exists: `Revision.status` (draft or published); adds: the review and the date | must | lms 1.1 |
| Soft delete for clips: a 30-day bin that keeps the HLS files, because re-encoding costs worker time | adds | must | lms 1.1, 6.4 |
| Free-preview flag per clip | exists: `Clip.is_free_preview`, `LEARN_FREE_PREVIEW` | must | lms 1.1 |
| Processing status with a plain reason and Retry; poster and duration once ready | exists: the `Clip.processing` state machine, `process_clip`, `reprocess_clips` | must | lms 1.2; inv 6 |
| Short-lived signed playback | exists: links signed for 600 seconds | must | lms 1.2 |
| "Completed" written down per clip type | exists: the per-clip `completed` flag | must | lms 1.3 |
| One question bank for book questions and app items with fixed metadata (subject, chapter, topic, marks, difficulty, Bloom level, source, tags), all filters, all bulk-editable | exists: `QuizItem` with chapter and tags, book questions with chapter and section tags; adds: the bank page | must | lms 1.4 |
| Item types: multiple choice, true or false, fill in the blank with a list of accepted answers and one rule for case and spaces | exists: the three types with `is_right()` on the server | must | lms 1.4 |
| Item statistics overnight from the first attempt per learner: p and the corrected item-total correlation, flagged at discrimination below 0.10, p above 0.95, or p below 0.25 for multiple choice; "N/A" under 30 learners, n and "last calculated" shown | adds: `insights.ItemStat` | must | lms 1.5; b2b 4.7 |
| "Needs checking" flag, sent to the content triage queue | adds | must | lms 1.5 |
| Entitlements: grant, extend and revoke with a reason, in bulk | exists: `Entitlement` (source, reference, `valid_until`, note), SUPPORT may add and change | must | lms 1.7 |
| Progress kept when access ends, so a renewed pass picks up where it left off; progress goes only with the account | a rule | must (as a decision) | lms 1.7 |
| Book-code batches per print run on one page: generate a batch and export it for the printer, redeemed against printed by week, void a leaked code or batch (typed confirmation), look up a typed code by its hash and see unused, redeemed (when, by whom as a link) or void | exists: `make_book_codes` (digests only), `BookCode.batch`, the redemption throttle, a RUNBOOK shell step to print codes; adds: the page and voiding | must | lms 1.7; gst 2; inv 6 |
| Code fraud rules: failed redemptions per user, address and device per hour with an alert on spikes; redemptions from a batch not yet dispatched (a leak); one account redeeming many codes (resale); one code tried by many accounts (a shared photo) | adds: `insights` rules | must | b2b 4.10 |
| Learner page for support: entitlements, codes redeemed, devices, chapter progress, quiz accuracy per chapter, card reviews, tickets; every staff view logged | exists: all the data, which Download my data assembles for the student; adds: the page | must | lms 1.9 |
| No per-student "needs attention" or at-risk lists in the panel (behavioural monitoring of minors, s.9(3)) | a rule | must (as a decision) | lms 1.9; b2b 4.6 |
| Bulk actions on clips, cards and items (publish, unpublish, free preview, move, delete, with a count in the confirmation) | adds | should | lms 1.1 |
| Asset library with "used in" | adds | should | lms 1.1 |
| Captions per language as WebVTT, an "Uncaptioned" filter; Assamese and Bengali captions written by people (no machine captioning covers them) | adds: `learn.ClipCaption` | should | lms 1.2 |
| Device list per learner with "sign out" | exists: `learn.Device`; adds: the staff view | should | lms 1.2 |
| A moving account code over the player (never a minor's phone or email) | adds: in the app | should | lms 1.2 |
| Per-clip engagement as totals: starts, seconds watched and completions kept apart | adds: from `Progress` | should | lms 1.2 |
| Changing a completion rule safely, by versioning it | adds | should | lms 1.3 |
| Item status, history, usage and reviewer comments (QuizItem has no history today) | adds: simple_history on QuizItem | should | lms 1.4 |
| Re-mark past answers after an answer-key change, with a dry run, or a record that it did not | adds | should | lms 1.4 |
| Store the option given, kept a short time, for distractor analysis | adds: `QuizAttempt.given` | should | lms 1.5; b2b 4.7 |
| Import and export of items through a spreadsheet with preview | exists: `build_quiz_items`; adds | should | lms 1.4 |
| Practice-quiz settings: shuffle, random N by tags, feedback at once or at the end, a penalty off by default | adds | should | lms 1.4 |
| One card scheduler set by staff and explained to students, every interval capped at the days left to the exam; card health per chapter as totals | exists: "I knew it" reviews, wrong answers back after 1, 3 and 7 days; adds | should | lms 1.6 |
| Expiry reminders, a service message about something the student bought | adds | should | lms 1.7 |
| Announcements with a display window, and a one-off service push to the entitled learners of a subject with a count before sending (no marketing in push) | exists: the daily FCM reminder; adds | should | lms 1.11 |
| Unlock rules, drip schedules, timed chapter tests, certificates, leaderboards, a doubt queue, live classes, DRM, offline download, a course copy with a locked master | adds | later | lms 1.1 to 1.11 |

**Easy and smooth:** the outline is one tree page with the actions on each row and a keyboard path for every drag;
a clip's failure reason is written in words with Retry beside it; the code lookup accepts a typed or scanned code
and answers in one line; the learner page opens from a ticket's sidebar with one click and says at the top that the
view is logged.

### 5.12 Partners (distributors, schools, teachers) [both]

**Owner:** both. Distributors, schools and booksellers are ERPNext's: Customers in their groups, territories, price
lists, credit limits, payment terms, dunning, quotations, sales orders, delivery notes, invoices and the custom
DocTypes School Adoption, Distributor Agreement and Specimen Request. Teachers are the platform's (their accounts,
verification, classes and consent), as are school licences and the school codes of the parent-pays channel.
**Used by:** SALES (ERPNext Sales User and Manager), FINANCE (credit, collections), SUPPORT (teacher verification),
ADMIN.

| Capability | Exists / adds / ERPNext | Priority | Reference |
|---|---|---|---|
| **Distributors:** account and KYC: GSTIN (state code, PAN and check digit checked), PAN, cancelled cheque, optional trade licence, the agreement with a valid-until date, contacts; the GST portal's taxpayer search done by a person and recorded with who and when | exists: `validate_gstin`; ERPNext: Customer (group Distributor), Contacts, Distributor Agreement, attachments, India Compliance's GSTIN check | must | b2b 1.2 |
| Territories by district, with at most one exclusive distributor per district and line (written into the agreement too) | ERPNext: Territory and an `examleaf_erp` validation | must | b2b 1.2 |
| Price lists and trade discount: percent off MRP per product, quantity slabs, validity | ERPNext: Price List, Pricing Rule | must | b2b 1.2; erp 4.3 |
| Credit limit and payment terms: exposure is confirmed unbilled orders plus the outstanding balance; an order over the limit waits for the override role, logged | ERPNext: Credit Limit and its approver role, Payment Terms Template | must | b2b 1.2; erp 4.3 |
| Orders taken by staff: outright, sale or return, specimen; PO number and file; a bill of supply for outright sales, a delivery challan for sale-or-return and specimens | ERPNext: Sales Order → Delivery Note (challan print format) → Sales Invoice, in B2B series | must | b2b 1.2 |
| Sale-or-return ledger on its six-month clock: each line keeps its removal date, a nightly list at five months, billed when the distributor reports sales or at six months (s.31(7)), whichever is earlier | ERPNext: Delivery Notes into the distributor's warehouse and an `examleaf_erp` job | must (if the agreements allow sale or return; the trade sells firm with capped exceptions, gst 3 calls it later) | b2b 0.2, 1.2; gst 3 |
| Returns with the agreement's reasons, windows and cap (for example damaged within a month, misprints within 15 days, unsold within 12 months, all within 10% of gross invoiced, freight paid by the distributor): receive, inspect, restock or write off ("credit only"), credit note | ERPNext: Sales Return (credit note) and the Distributor Agreement's fields | must | b2b 0.2, 1.2 |
| Statement of account and ageing (0–30, 31–60, 61–90, 90+ days) as a PDF and by email | ERPNext: Process Statement of Accounts, Accounts Receivable | must | b2b 1.2; gst 3 |
| Collections: reminder levels by days overdue (for example 3 days before due, +7, +21, new orders held at +45); a Razorpay Smart Collect virtual account per distributor; payment links with a first instalment; cheques with number, bank and cleared date | ERPNext: Dunning, Payment Entry; the platform creates the Razorpay virtual accounts and links (Razorpay stays in the platform) | must | b2b 1.2; int 4.1; erp 4.2 |
| Stock at distributors on sale or return | ERPNext: one warehouse per distributor | should | b2b 1.2 |
| Sell-through without the distributor typing anything: a book-code batch or range allocated to each distributor shipment, weekly redemptions per batch; a monthly stock-statement upload as the fallback | exists: `BookCode.batch`, `redeemed_at`; adds: the allocation on the Delivery Note's batch | should | b2b 1.2, 4.4 |
| Schemes (an early-order discount, a slab bonus, free copies per N), accrued on orders and paid as a credit note when the season closes | ERPNext: Promotional Scheme, Pricing Rule; an accrual report | should | b2b 1.2 |
| Claims (transit damage, short supply, scheme payout, price difference) with photo evidence, approved into a credit note | ERPNext: a credit note with a reason and attachments through a workflow | should | b2b 1.2 |
| Sales reps and commission on the amount collected, net of returns; season targets with a variance report | ERPNext: Sales Person targets, Sales Partner commission for agents | should | b2b 1.2; erp 4.3 |
| Partner tier and activation state (first contact, ramp-up, fully operational) | ERPNext: custom fields on Customer | should | lms 3.7 |
| Dealer locator on the site (active dealers by district, tier, address, phone, map link) and a "Become a dealer" form that creates a prospect | ERPNext: Lead; the platform reads the active dealers | should | b2b 1.2 |
| A read-only distributor portal; beat plans and geo check-ins | the ERPNext portal stays closed, so on examleaf.in if ever built | later | b2b 1.2; erp 4.3 |
| **Schools:** account with UDISE code, board, management, medium, streams, classes, enrolment per class, district and PIN, GSTIN (usually none), contacts with roles; the platform's quote form linked to it | ERPNext: Customer (group School) with custom fields; the platform's `QuoteRequest` becomes an ERPNext Lead or Quotation draft | must | b2b 2.2 |
| Adoption pipeline: lead → sample sent → evaluating → recommended or prescribed → ordered → delivered → paid, with expected copies, who decided and when, and the lost reason | ERPNext: School Adoption | must | b2b 2.2; lms 3.2 |
| Specimen and inspection copies: one per subject taught per season, sent on a delivery challan, with a follow-up date that feeds the pipeline; requested by verified teachers on the site | ERPNext: Specimen Request → Delivery Note; the platform's request form posts it through the outbox | must | b2b 2.2, 3.2 |
| School orders with lines per class, PO, delivery to the school, a bill of supply, payment by NEFT, UPI or cheque, a virtual account or instalments; an annual commitment as a blanket order | ERPNext: Quotation → Sales Order → Delivery Note → Sales Invoice, Blanket Order | must | b2b 2.2; erp 4.3 |
| Parent-pays channel: a school's link or code applies the school's price in the shop, delivered home or to the school; the school sees counts per class, never names (schools must not coerce parents to buy from one vendor) | adds: `partners.SchoolCode` and a read-only copy of the school's price list | must | b2b 2.1, 2.2 |
| Renewals: at the start of each year last year's adoptions become "renewal due" with the new edition, an owner and a date | ERPNext: an `examleaf_erp` job on School Adoption | must | b2b 2.2 |
| Visits and follow-ups (call, visit, demo, webinar, email; outcome; next date); tasks with reminders and a daily digest | ERPNext: Event, ToDo and assignment on the Customer or Lead | must (visits); should (tasks) | b2b 2.2; lms 3.2 |
| Course access for a whole school: a licence for a year, subjects and seats that creates entitlements for rostered students, or a code batch per school; seats used reported | exists: `Entitlement` (sources code, purchase, grant); adds: `partners.SchoolLicence` and the source "licence" | should | b2b 2.2 |
| Roster import with parent consent at scale: a CSV of name, class, section and parent contact; each parent gets an itemised consent link in Assamese or English; the student's account is created only after consent | exists: `ConsentRecord` with email and SMS link methods; adds: the import | should | b2b 2.2; lms 1.7 |
| School dashboard of class aggregates (students activated, codes redeemed, self-reported marks labelled as such, weakest chapters), groups under 5 hidden | adds | should | b2b 2.2 |
| Teacher training and webinars: events, registrations, attendance, a certificate | adds: `partners.Event` and registrations on the platform (teachers are platform accounts) | should | b2b 2.2 |
| SIS or OneRoster sync | adds | later | b2b 2.2 |
| **Teachers:** verification, version 2: evidence (a school ID card, an appointment letter, or a principal's letter for the current academic year), the school's UDISE code, the staff phone check; states requested → checking → verified or rejected → expired or revoked; expiry at the end of the academic year; the evidence file deleted N days after the decision, its hash and the note kept | exists: `TeacherProfile` with a `verified` boolean, a note, `verified_at` and `verified_by`; adds: the states, evidence and expiry | must | b2b 3.2; inv 0, 3 |
| New teacher requests reach the inbox (no one is told today) | adds | must | inv 7, 11.6 |
| Gated teacher resources: answer keys, marking schemes and PDFs for verified teachers only, watermarked with the teacher's name and id, downloads logged, a daily limit, scoped to the teacher's subjects | adds: `content.TeacherResource` | must | b2b 3.2 |
| Revocation and offboarding: staff revoke with a reason, a teacher marks "left this school", class links end at once and classes move to another verified teacher at the school | adds | must | b2b 3.2 |
| The same evidence file's hash on two requests raises a flag | adds: `insights` rule | must | b2b 4.10 |
| Classes and consented links: a class with a join code; for an under-18 member the parent gets an itemised request ("saved marks, course progress and quiz results for Physics, shared with this teacher at this school until 31 March"); the teacher sees data only after consent; withdrawal in one tap; links expire at the end of the year | adds: `partners.TeacherClass`, `partners.ClassMembership` | should, after the founder's decision and counsel (lms 1.8 puts it later) | b2b 3.2; lms 1.8 |
| Teacher dashboard (class aggregates first; per-student rows only for consenting members) and assignments computed from attempts, quiz answers and progress | adds | should | b2b 3.2 |
| Teacher price list and the specimen allowance | ERPNext: Price List; the Specimen Request rule | should | b2b 3.2 |
| Ambassadors without cash: hand-picked verified teachers per district; benefits are new editions, early access, review panels, errata credit, webinar slots, a certificate; referral codes give the student a discount; no commission to a teacher on their own pupils' purchases | exists: `Coupon`; adds: an owner teacher on a coupon | should | b2b 3.2; lms 3.5 |
| Teacher activation report (requests, verified, time to verify, expired; verified teachers per school; consented links) | adds | should | b2b 5 |
| Teacher community and teacher-written content | adds | later | b2b 3.2 |

**Easy and smooth:** the panel's Partners page is a season board (specimens due, adoptions by stage, renewals due,
collections overdue, sale-or-return lines near six months) built from ERPNext's API, with every row opening its
ERPNext record; teacher verification is a queue with the evidence beside the school's UDISE record and two buttons;
the parent-pays code is generated from the school's ERPNext record in one step and printed on a one-page notice for
parents.

### 5.13 Marketing

**Owner:** platform. Two audiences, two rule sets: students (mostly minors) get service messages only; parents,
teachers, schools and dealers are adults to whom ordinary consented marketing applies (lms 3). **Used by:**
MARKETING (no exports of individuals, no targeting of under-18s), ADMIN; approvals by FINANCE or OWNER above the
discount threshold.

| Capability | Exists / adds / ERPNext | Priority | Reference |
|---|---|---|---|
| Minors suppressed by default: a fixed rule ahead of every marketing send excludes every account under 18 and every account whose age is unknown, unless the parent's verified consent covers marketing | adds: one audience function every send goes through | must | lms 3.3; rbac 4.3 |
| Consent ledger per channel and purpose: person, channel (email, SMS, WhatsApp), purpose, status, source, time, actor, evidence (form version, DLT consent template, parent link); no pre-ticked boxes | exists: `ConsentRecord` for sign-up consent; adds: a channel and evidence on it | must | lms 3.4; gst 6 (Rule 4(9)) |
| One message-template registry: per message (event, channel, language) the DLT template id, PE id, the header with its -P, -S, -T or -G suffix, the MSG91 id, the WhatsApp template name, the category and approval state, typed variables (`#numeric#`, `#url#` and so on since November 2025; at most three without justification; at least 30% fixed text), one header per template, URLs whitelisted, the last use (templates idle 90 days are deactivated, with an alert before), the yearly self-certification, a test send and delivery reports | exists: MSG91 templates in settings, `SmsLog`; adds: `ops.MessageTemplate` | must | lms 0, 3.4; int 4.2 |
| Testimonials and toppers only with written consent given after the result, with the rank, the course, paid or free, the disclaimer in the same size as the claim; no guaranteed ranks or marks; no false scarcity | adds: `pages.Testimonial` | must | lms 0, 3.5 |
| Reviews: delivered buyers only, moderation, no reviews written by staff posing as customers, a review audit log | exists: `Review` (pending, approved, rejected; history), `ReviewAdmin` approve and reject | must | lms 3.5; gst 6 (Rule 7(2)) |
| Coupons and automatic offers drafted here, approved above the discount threshold; banners and copy pass the dark-pattern checks of section 5.5 | exists: `Coupon`, `Offer`; adds: the approval | must | lms 3.5; rbac 1.5 |
| "Free" QR solutions behind a sign-up advertised as "free with a free account", or kept open (the CCPA fined an edtech platform for "free" courses that needed a phone number first) | a copy rule until counsel answers | must (as a decision) | lms 0 |
| Email campaigns to opted-in adults: a subscription type on every email, a send time, "Unsubscribe" and "Manage preferences" in the footer, one-click unsubscribe (RFC 8058) honoured within 2 days, the Gmail bulk-sender rules (SPF, DKIM, DMARC, spam under 0.3%) | adds: `marketing.Campaign` over SES | should | lms 3.4, 0 |
| Preference centre per topic | exists: SES and the suppression list; adds: SES contact lists with topics | should | lms 3.4 |
| Dynamic and static segments, built only from consented purposes, with versioned definitions | adds: `marketing.Segment` | should | lms 3.3; rbac 5 |
| Quiet hours and frequency caps | adds | should | lms 3.4 |
| NPS, CSAT and CES surveys to parents and teachers, or after support | adds | should | lms 3.5 |
| UTM builder and the last non-direct source stored on the order; QR codes and WhatsApp links tagged (WhatsApp otherwise arrives as "Direct") | adds: `Order.source` | should | lms 3.6, 5.5 |
| Campaign ROI ((revenue − spend) / spend) | adds | should | lms 3.6 |
| Review requests after delivery; a rating of 3 or less opens a ticket | adds | should | lms 3.5 |
| WhatsApp Business through MSG91 (opt-in naming the business, utility templates, per-message pricing, sending tiers) | adds | later (section 10) | lms 3.4; int 4.2 |
| Abandoned-cart reminders for adults with marketing consent; a referral programme (not researched); lead scores and sequences for schools and teachers only; multi-touch attribution; A/B tests on adult-facing pages | adds | later | lms 3.2, 3.5, 3.6, 2.8 |

**Easy and smooth:** the send screen shows the audience count after the minors' rule and the consent filter, and
names what was excluded and why; a template's DLT status and last use show in the list, with a warning before the
90-day lapse; a test send goes to the staff member's own number or address only.

### 5.14 Support

**Owner:** platform: a small `support` app, because a ticket number the customer can track is a legal duty, the
legal clocks join the DPDP queue, the agent's sidebar is platform data, and tickets carry minors' personal data that
the design keeps out of ERPNext. Frappe Helpdesk is not installed (section 10). **Used by:** SUPPORT, CONTENT_EDITOR
(notes only, on errata tickets), FINANCE (refund approvals), ADMIN.

| Capability | Exists / adds / ERPNext | Priority | Reference |
|---|---|---|---|
| One inbox for the contact form, email (the support address forwarded in, with a loop guard and threading by ticket reference and mail headers), a "log a call" form and National Consumer Helpline complaints with their docket number | exists: the contact form, which emails the support address and stores nothing (5 an hour); adds: `support.Ticket`, `support.TicketMessage`, inbound mail | must | lms 4.1; inv 5 |
| Acknowledgement with the ticket number, sent automatically; from 1 January 2027 it includes a copy of the complaint as recorded; only a human reply counts as the first response | adds | must | lms 0, 4.1; gst 6 |
| Legal clocks on every ticket, in calendar time and never paused: acknowledge within 48 hours and redress within one month (E-Commerce Rules), NCH complaints within 30 days, DPDP rights requests within 90 days; the SPDI Rules' one month until May 2027; the IT Rules' 24 hours and 15 days only if counsel says reviews make ExamLeaf an intermediary | adds | must | lms 4.2; rbac 4.6; gst 6 |
| Fields: statuses (new, open, waiting on customer, waiting on third party, resolved, closed), priorities, source, categories (order, payment, book code, QR solutions, content error, school order, privacy request, grievance), fields required when closing, solved tickets closed after 4 days | adds | must | lms 4.2 |
| Queues sorted by due time, shared and personal views | adds | must | lms 4.3 |
| Internal notes and @mentions, with content editors as note-only users | adds | must | lms 4.3 |
| Saved replies with variables and fallbacks, in Assamese, Bengali and English; the refund reply carries Razorpay's expected days by method | adds: `support.SavedReply` | must | lms 4.3, 4.6 |
| Sidebar: orders with Razorpay ids and status, shipments, invoices, entitlements (source, valid until), codes redeemed, devices, past tickets, consents | exists: all the data | must | lms 4.5 |
| Actions from the ticket, each logged: refund full or partial (quantities start at zero), cancel, resend the invoice, resend the code email, extend access by N days with a reason, look up a book code | exists: the shop and learn services | must | lms 4.5 |
| Spam quarantine, purged after 30 days and kept out of reports | exists: Turnstile, honeypot and rate limits on forms; adds | must | lms 4.1 |
| "My requests" on the site: each ticket's number and status for the customer | adds: a page on examleaf.in | must | lms 4.8; gst 6 (Rule 7(1)(f)) |
| Grievance register export: a dated CSV of complaints received, acknowledged and resolved, with the days taken, for an audit or an NCH query | adds | must | lms 4.9; gst 7 |
| Merge, split and link; a tracker that broadcasts one update to every linked ticket ("QR batch PHY-2027-1 misprinted") | adds | should | lms 4.2 |
| Collision detection (someone viewing, someone replying; a reply held when a newer customer message arrived) | adds | should | lms 4.3 |
| Assignment by round-robin among available agents, plus claim; snooze "if no reply" or "regardless"; automations on create, on update and hourly | adds: Celery beat | should | lms 4.3 |
| Keyboard shortcuts with the list on "?" (`g t`, `g n`, `/`) | adds | should | lms 4.3 |
| Internal SLA targets per priority in business hours (IST, Assam holidays, exam season), with reminders before a breach and an SLA report | adds | should | lms 4.4 |
| CSAT after resolution; a bad score reopens the ticket to a lead | adds | should | lms 4.7 |
| Help centre in three languages from the FAQ manager (categories, order, languages, "was this helpful"), suggested articles while the customer types (PostgreSQL full-text search), article feedback and searches with no result | adds: `pages.FaqEntry` | should | lms 4.8, 2.8 |
| Support numbers: volume by category, first response, resolution time, backlog, breaches, CSAT per agent, from fields stored on the ticket | adds | should | lms 4.9 |
| Side conversations with a printer, courier or Razorpay from inside the ticket | adds | later | lms 4.3 |

**Easy and smooth:** the queue opens on "due soonest" with each ticket's legal clock as a countdown; the sidebar
loads the customer's orders and course without a click; one keystroke inserts a saved reply in the customer's
language; an NCH complaint is logged with its docket in one form; closing asks only for the fields that the
category requires.

### 5.15 Legal and privacy

**Owner:** platform. **Used by:** OWNER (the breach register, the cockpit), ADMIN, SUPPORT (the rights queue),
AUDITOR (reads).

| Capability | Exists / adds / ERPNext | Priority | Reference |
|---|---|---|---|
| Compliance cockpit with every clock the Indian rules start: complaints unacknowledged at 48 hours and unresolved at one month, NCH complaints at 30 days, rights requests at 90 days, a breach's 6 hours (CERT-In) and 72 hours (the Board), parent confirmations awaited, the yearly dark-pattern self-audit and its certificate, the policy version each consent was given under | adds | must | lms 7; rbac 4.4 |
| DPDP rights queue: type (access, correction, erasure, grievance, nomination, consent withdrawal), channel, the identifiers asked for, the identity check, the due date as the earliest clock that applies, the assignee, holds, the response with the contact block, proof it was sent, the closure reason | adds: `accounts.DataRequest` | must | rbac 5, 4.2, 4.6 |
| Access requests answered with the export and the list of others the data went to, from the processor register | exists: `export_user_data`; adds: the recipients list | must | rbac 4.2 |
| Correction tasks with history; a nominee record verified when a claim is made | adds: `accounts.Nominee` | must (by 13 May 2027) | rbac 4.2 |
| Erasure with holds: a dry run of what is erased, what is held, why and until when; approval when staff started it; processor tasks (error tracker, email-provider logs, R2 media, analytics); a confirmation with the contact block; holds for tax and books (8 financial years or 72 months), a year of processing logs, open disputes and legal claims, the intermediary rule if it applies, and the parent's confirmation for a child; erased accounts never restored from a backup | exists: `DeletionRequest` (7-day grace, `complete()` anonymises), `purge_due_deletions` at 03:00, orders kept with the user set to null; adds: the dry run, holds and processor tasks | must | rbac 4.5; gst 5.16 |
| Legal holds on a person or a record (dispute, chargeback, claim) | adds: `accounts.LegalHold` | must | rbac 4.5 |
| Retention schedule in code with the minimum per category (books of account 8 financial years; security logs 180 days now and one year from 13 May 2027; processing records one year from the processing; consent while relied on plus the limitation period; staff audit 2 years and money events 8 years; backups 30 days) that the erasure job obeys | adds: one table in code | must | rbac 3.4, 4.2 |
| Retention settings that fall short fixed: Docker logs capped at 50 MB per service, Celery results and webhook records kept 7 days, the SMS log 90 days, device rows purged nightly; minimal metadata kept for the full period, payloads trimmed early | adds | must (CERT-In's 180 days apply today) | rbac 3.4, 4.9 |
| Breach register (`Incident`): detected at, noticed by, the CERT-In Annexure I type, systems and data categories, people affected and whether any are children, the CERT-In report time and reference, the Board's initial and detailed report times and any extension, the message sent to people and how many, actions, root cause, closure, timers from detection, links to the audit events | adds: `accounts.Incident` | must | rbac 4.4; lms 0 |
| The CERT-In point of contact, the DPDP contact person quoted in every rights reply, and the published text on how to make a request | adds: site settings | must | rbac 4.2, 4.4, 4.7 |
| Processor register: each processor's purpose, data categories, country or region and contract dates (India Compliance through Resilient Tech, Razorpay, SES, MSG91, Shiprocket, R2, Google, the error tracker) | adds: `accounts.Processor` | must | rbac 4.2; erp 4.1 |
| Consent ledger, append-only: version, method, time, IP hash, the parental evidence reference; withdrawal as easy as giving, with "cease" tasks for processors | exists: `ConsentRecord` | must | rbac 4.2; lms 0 |
| Policy versions: each publish of the privacy policy or terms creates a numbered version with an effective date and a diff, and consent rows point at the version accepted | exists: legal pages with history, `ConsentRecord.notice_version`; adds: the effective date and diff | must | lms 2.8; rbac 4.2 |
| Parental consent per child account: age band, state (none, declared, pending, verified, withdrawn, expired), method (declared tick, email link, SMS link, an existing verified adult account, a DigiLocker token, staff by hand with evidence), who verified and when, an evidence reference, the notice version; the identity and age step in place before 13 May 2027, storing the outcome and not the date of birth | exists: `ConsentRecord(by_parent, method, verified_at, notice_version)`, `PARENTAL_CONSENT_MODE=verified`; adds: the age check | must (by 13 May 2027) | rbac 4.3; int 4.7; lms 0 |
| Children's rules: under-18 accounts flagged and kept out of marketing segments, ad audiences, lookalike exports and experiments; no behavioural profiling beyond what the learning feature needs; every staff view of a child's record logged | adds: rules in the audience function and the access log | must | rbac 4.3; lms 0; b2b 0.4 |
| E-commerce disclosures as editable settings shown in the footer and on the contact page: legal name, addresses, customer care and grievance officer with designation, the nodal contact resident in India, return and refund terms | adds: site settings | must | gst 6; rbac 4.6 |
| Dark-pattern self-audit once a year against the 13 named patterns, with the certificate displayed prominently from 1 January 2027 | adds: a checklist record | must | lms 0; gst 6 |
| Membership of the National Consumer Helpline's convergence programme, mandatory from 1 January 2027 (how to join is a question for counsel) | a task | must | lms 0, 8 |
| Re-consent at the next sign-in when a policy changes materially | adds | should | lms 2.8 |
| Consent artefacts from a consent manager (rule 4, from about 13 November 2026); a watch on the significant-data-fiduciary notifications | adds | later | rbac 4.2 |

**Easy and smooth:** the cockpit is the module's home page and every clock on it opens the record behind it;
a rights request starts from a ticket in one click and carries its identity check and holds with it; the erasure
dry run reads as a plain list ("kept until 31 March 2034: 3 invoices, for GST and the Companies Act"); the breach
register's form starts the 6-hour and 72-hour timers the moment it is saved and keeps the drafted messages to people
beside it.

### 5.16 Reports and analytics (incl. predictions) [both]

**Owner:** both. The panel's `insights` app (in progress) holds the metric definitions, the forecasts, the scores
and the item statistics over the platform's data; ERPNext's reports cover accounting, stock, receivables and the
B2B pipeline and open there; Frappe Insights over both databases is a later option (section 10). No third-party
trackers, by decision: every number comes from ExamLeaf's own tables. **Used by:** OWNER, ADMIN, FINANCE, SALES,
CONTENT (item statistics), MARKETING (aggregates only), AUDITOR.

| Capability | Exists / adds / ERPNext | Priority | Reference |
|---|---|---|---|
| Sales by product, subject, class, board, edition and period (units, gross, discount, net; by day, week and month) | exists: `store_stats()` (14 days, top five, low stock); adds | must | gst 7; lms 5.4 |
| Sales by state, district and PIN, which doubles as the place-of-supply check; districts under the minimum cell hidden | exists: `PinCode` with districts; adds | must | gst 7; lms 5.5 |
| Codes: printed, sold, activated and revoked by batch, the activation rate, by district | exists: `BookCode` (`batch`, `redeemed_at`); adds | must | gst 7; b2b 4.6 |
| Course health, all aggregate by subject and chapter: active learners per day, week and month (smoothed over 7 or 28 days), clip completion, quiz accuracy, card reviews and lapses, codes redeemed by week | exists: `Progress`, `QuizAttempt`, `CardReview`; adds | must | lms 5.6, 1.9 |
| Learner analytics aggregate only: cohort retention by redemption month and by source (code, purchase, grant) as the weekly active share up to the exam; no per-student risk lists | adds | must | b2b 4.6 |
| Minimum cell size: any cell under k hidden (10 in the panel's district, school, cohort and search tables; 5 in a school's or teacher's class aggregates) | adds: one setting per kind of table | must | lms 5.8; b2b 2.2, 4.6 |
| Exports of any list as filtered, logged, with a row cap and formula cells escaped; dates of birth and parents' contacts left out | exists: ADMIN-only logged exports (`LoggedExportMixin`), `IMPORT_EXPORT_ESCAPE_FORMULAE_ON_EXPORT` | must | lms 5.7, 6.3; inv 1.2 |
| GST liability, the HSN summary and the document register | ERPNext: India Compliance; the platform's export as the cross-check | must | gst 7 |
| COD ageing and remittance; Razorpay settlements (gross, fees, GST, refunds, net, UTR per settlement) | adds: from `shipping` and `integrations` | must | gst 7 |
| Rules for every prediction: it beats a naive baseline in a backtest before it shows; the number comes with a range, the method, the last backtest error, the data's as-of time and the two or three signals behind it; probabilities calibrated; nothing individual about under-18 learners; no learning data in marketing, pricing or offers; rules, not machine learning, below about 200 labelled outcomes | a rule for the `insights` app | must | b2b 4.1 |
| Demand forecast and print runs: seasonal naive by week of season with a damped growth factor (a new title borrows the previous title's curve); B2B as the pipeline (expected copies × stage probability, plus orders placed); ETS only after two or three seasons; the run sized as a newsvendor problem at the critical ratio (for example net ₹195, print cost ₹60, salvage ₹5 gives 0.71, so print the 71st percentile); a reprint trigger when stock plus on order falls to the demand over the reprint lead time plus safety stock; backtests by WAPE and seasonal MASE, never MAPE; alerts at weeks of cover below lead time plus a week, and at a projected leftover above X% of the run | adds: `insights.ForecastRun`, `Forecast`, `Backtest`; inputs from order lines, ERPNext's B2B lines and School Adoptions, `StockAlert`, redemptions and the exam calendar | must | b2b 4.2 |
| B2B reports: territory sales (district × week × title, this season against last, B2B and B2C shares), distributor statement and ageing, collections due, returns and claims against the cap, the adoption pipeline, renewals due, print run and stock | ERPNext: statements, ageing, collections, returns and the pipeline; adds: territory sales and print runs across both systems | must | b2b 5 |
| Fraud and abuse rules (codes, shop accounts sharing a phone or address on coupon or COD orders, repeated COD refusals, teacher evidence reused, distributor returns above the cap and frequent claims) with alerts | adds: `insights` rules feeding the inbox | must | b2b 4.10 |
| COD RTO risk: the shipment outcome recorded now (the data fix), then a rule score from the PIN's RTO rate smoothed toward its district's, past RTOs, first COD, value and address problems; logistic regression only after about 200 RTOs | exists: `PinCode.state_problem`; adds: the outcome field (section 5.7) and the score | must (data); should (score) | b2b 4.8 |
| Sales by channel (website, staff and phone, school, distributor) | adds | should | gst 7 |
| Cohorts by the month of first purchase or code redemption, with cells under the minimum hidden | adds | should | lms 5.3; gst 7 |
| Two funnels from ExamLeaf's own tables: the shop (visit → sample paper → registers → buys) and the book (QR solution opened → registers → redeems a code → first clip), anonymous totals before sign-in | adds | should | lms 5.2 |
| Payment mix and success rate; refunds, returns and cancellations by reason; coupon and offer performance with intervals instead of winners (a fixed sample size before starting) | adds | should | gst 7; b2b 4.11 |
| Content performance as totals (solutions opened per paper, items by difficulty, clip completion, card lapses) | adds | should | lms 5.4 |
| Sales projections per subject split to districts by last season's share, P10 to P90 | adds | should | b2b 4.3 |
| Distributor stock and sell-through: expected returns as sale-or-return stock less the sales implied by redemptions, flagged by mid-January so stock moves before the exams | adds | should | b2b 4.4 |
| School and lead scoring by rules (ordered or adopted last year, verified teachers, redemptions from the school's area, samples followed up, Class 12 enrolment; less for days since contact), High, Medium or Low with the top three reasons; schools and distributors only, never students | adds: `insights.AccountScore` | should | b2b 4.5 |
| Delivery delay by courier and district (median and P90) | adds | should | b2b 4.9 |
| Deferred course revenue roll-forward; profit and loss by line (books against courses, with the GST that cannot be claimed) | ERPNext | should | gst 7 |
| Cookieless page counts: a server-side table of day, path and count, or Umami on PostgreSQL with a daily salt, only on public pages, never in the signed-in course area | adds | should | lms 5.8; int 4.11 |
| Short raw retention, long aggregates | adds | should | lms 5.8 |
| A monthly in-season review of forecasts against actuals and the baseline; methods that lose are retired | a task | should | b2b 4.12 |
| An opt-in "on track for your exam date" card for the student, built from their own plan, with no staff view, after counsel's review | adds | should | b2b 4.6 |
| Frappe Insights over ERPNext and a read-only role on the platform's roll-up views; Metabase-style embedded charts; a nightly warehouse export; device mix; search terms; multi-touch attribution | adds | later | erp 2.5, 4.2; lms 5.4, 5.5, 5.7 |

**Easy and smooth:** every report says how each number is defined and when it was computed; the forecast page shows
the recommended print run with its range, the method and last season's error in one panel, and the newsvendor
inputs as editable fields with the result recomputed; season views by default (b2b 5); a small cell shows "fewer
than 10" rather than a number.

### 5.17 Staff

**Owner:** platform (the `staff` app, in progress); identity from Google Workspace; roles mirrored to ERPNext.
**Used by:** OWNER, ADMIN; AUDITOR reads; every staff member sees their own sessions.

| Capability | Exists / adds / ERPNext | Priority | Reference |
|---|---|---|---|
| Role templates in code (section 4.1), synced to groups and undone if edited by hand | exists: `accounts/roles.py`, `sync_roles`, `bootstrap_roles` for STUDENT, TEACHER, CONTENT_EDITOR, SALES, SUPPORT, ADMIN; adds: the new roles | must | rbac 1.3; inv 1.1 |
| Action permissions beyond add, change, delete and view: refund, approve refund, record offline payment, publish, reveal contact, suspend, reset MFA, impersonate, export personal data, assign role, approve role change, view and export the audit log, manage API keys, replay webhooks, toggle maintenance, break glass | adds: `Meta.permissions` | must | rbac 1.4 |
| Permission catalogue in code: a UI label, an area, a risk level (low to critical) and what it triggers (step-up, approval, alert), so risk drives behaviour everywhere | adds | must | rbac 1.4 |
| Scopes (subject, board and class, order state, school) on one auth backend and one `scoped()` queryset helper used by every staff view; limits as attributes ("refund orders, up to ₹2,000 without approval") | adds: `staff.StaffScope`, `ROLE_LIMITS` | must | rbac 1.1, 1.9 |
| Separation of duties: static at grant time, dynamic per transaction; the owner-only override with a reason, an alert and a review | adds: `SOD_CONFLICTS` | must | rbac 1.2 |
| ChangeRequest approvals bound to a payload hash: the checker approves the exact stored payload, the server executes that payload after re-checking its preconditions, once, before it expires, atomically, with step-up for both people | adds: `staff.ChangeRequest` on django-fsm-2 (installed) | must | rbac 1.5 |
| Break-glass: one or two superuser accounts outside SSO with FIDO2 keys kept offline; a reason, alerts to the owner and admins, a 2-hour box, every action marked, a review within 24 hours, a test every quarter | adds | must | rbac 1.6 |
| The session manifest (`GET /api/staff/session`, `no-store`): roles with expiry, permissions, scopes, limits, flags, the step-up window, the idle and absolute limits, a version hash; kept in memory, refetched after any 403 | adds | must | rbac 1.7 |
| Role catalogue page (read-only): capabilities by area with risk badges, limits, scopes, conflicts, member count; role cards ("for people who need to…", "they can't…") in three languages | adds | must | rbac 1.8; lms 6.6 |
| A person's Access tab: roles with who granted them, when and until when, scopes and limits, the effective permissions, pending requests | adds: `staff.RoleGrant` | must | rbac 1.8 |
| Role changes: request → diff preview (permissions gained and lost) → conflict check → approval → effective, optionally with an expiry | adds | must | rbac 1.8, 6 |
| Invitations to the company domain with the role chosen in advance (privileged roles approved); a signed link, used once, valid 72 hours; MFA enrolled and the policies acknowledged before any page opens | adds: `staff.Invitation` | must | rbac 6 |
| Policy acknowledgements (acceptable use, children's data, confidentiality, incident reporting with "tell the owner at once"), versioned and asked again on change | adds: `staff.PolicyAcknowledgement` | must | rbac 6 |
| Sign-in and sessions as section 3.5: passkeys for OWNER, ADMIN and FINANCE, Google Workspace with the `hd` check, idle limits, step-up, the device list with "end this session" and "end all", an offer to end other sessions after a factor change | exists: `StaffMFAMiddleware`, 8-hour sessions, `allauth.usersessions`, reauthentication; adds | must | rbac 2.1, 2.3; int 4.4 |
| Per-staff throttles on reveals, exports, bulk actions and customer searches; the owner told when a staff account is locked | exists: axes; adds: scoped throttles and the lockout alert | must | rbac 2.5 |
| Offboarding checklist recorded step by step: deactivate, end sessions and refresh tokens, remove roles and scopes, cancel temporary grants, reassign pending requests, tickets and data requests, close external accounts (Workspace, Razorpay, MSG91, AWS, Cloudflare, the error tracker, GitHub, the registrar, SSH keys, shared passwords), revoke API keys, rotate the shared secrets they could read, collect security keys, review their last 90 days | adds; ERPNext: the user disabled, never deleted | must | rbac 2.9; erp 5.5; int 4.4 |
| ERPNext role mirror: User, role profiles and `enabled`, by hand under about 15 staff and by the outbox later | ERPNext: User, Role Profile (v16 allows several), User Permission | must | erp 5.5 |
| Quarterly access reviews: users × roles × scopes × last login × last use of each permission, each line kept, changed or revoked through the role-change flow; dormant accounts flagged after 45 days; the break-glass list checked | adds | must | rbac 6, 1.6 |
| Service accounts never sign in and never get staff status | a rule | must | rbac 2.6 |
| Temporary elevation: a role requested with a reason, approved by the owner, removed automatically at its expiry | adds | should | rbac 1.6 |
| "Who can…?" lookup, the last use of each permission, and the report of permissions unused for 90 days | adds: from `AuditLog` | should | rbac 1.8, 6 |
| Login alerts to the staff member (a new device and place, after 30 days dormant, MFA failures) and an owner's digest of logins outside usual hours | adds | should | rbac 2.8 |
| Concurrent sessions documented (for example two browsers) with an alert above that | adds | should | rbac 2.3 |
| API keys we issue to integrations: shown once, stored as a SHA-256 hash with a visible prefix, scopes, an expiry within 12 months, an optional IP allowlist, last use and address, two overlapping keys during rotation, a sponsor, revocation | adds: `staff.ApiKey` | should (when the first inbound integration needs one) | rbac 2.6 |
| Activity report per staff member with outliers flagged; access confirmed on a transfer | adds | should | rbac 6 |
| Staff language saved per account (Assamese, Bengali, English) | adds | should | lms 6.7 |
| Emergency contacts visible to the owner only | adds | should | rbac 6 |
| Packer shift windows | adds | later | rbac 6 |

**Easy and smooth:** inviting someone is one form (email, role, optional expiry) and the approval goes to the owner's
inbox; a role change shows in plain words what the person will gain and lose before anyone approves it; offboarding
is one button that runs the checklist and leaves a record with a tick per step, the external accounts as a list the
owner ticks off by hand.

### 5.18 Settings and integrations

**Owner:** platform: the site's settings and flags, and the `integrations` app (in progress) that holds credentials,
call logs, circuit breakers, dead letters and inbound events for every provider. ERPNext's own settings are fixtures
in `examleaf_erp`, never edited by hand in production. **Used by:** OWNER, ADMIN; FINANCE sees the payment settings.

| Capability | Exists / adds / ERPNext | Priority | Reference |
|---|---|---|---|
| Site settings in one record with history, so staff change them without a deploy: shop open, COD on, solutions need sign-in, the seller's details, the grievance and contact details of section 5.15 | exists: environment variables (`SHOP_OPEN`, `SHOP_COD_ENABLED`, `SOLUTIONS_REQUIRE_LOGIN`, `SHOP_SELLER` with `check_seller`); adds: `ops.SiteSettings` | must | lms 2.8, 6.5; inv 4.3 |
| Connections page, one card per integration (Razorpay, Shiprocket and the manual carrier, MSG91 SMS and WhatsApp, Amazon SES, R2, the error tracker, Google sign-in, ERPNext; later DigiLocker and an e-invoice provider): status (connected, degraded, expired, disabled, not configured), test or live in different colours, last success and last error, the error rate over 24 hours and 7 days, p90 latency | adds | must | int 5.2 |
| Test connection: one harmless authenticated read per integration (a payment, the wallet balance, the SMS balance, the sending quota, the bucket head), its result kept | adds | must | int 5.2 |
| Credentials encrypted with `MultiFernet` (keys rotated by a command), masked (last four characters, who set them, when), replaced and never shown; expiry countdowns (Shiprocket's 10-day token, our 90-day rotation policy); a warning where the provider gives no overlap (a new Delhivery token kills the old one; rolling an R2 token invalidates it); every reveal, roll or replace audited | adds: `integrations.IntegrationAccount` | must | int 3.3, 5.2, 4.10 |
| Inbound webhooks for every provider: our URL to paste, the secret or token rotatable with the previous one accepted for 24 hours, every received event stored raw and deduplicated (accepted, duplicate, rejected, failed), replay one or all failed since a time, a silence alarm | exists: `WebhookEvent` for Razorpay (signature, 7-day age, idempotency); adds: `integrations.InboundEvent` | must | int 5.2, 0; rbac 7 |
| Outbound call log per integration (operation, status, latency, the provider's request id, a redacted excerpt; 90 days), linked from the order or parcel that caused it; the dead-letter list with Replay and Discard with a reason | adds: `integrations.IntegrationCall`, `integrations.IntegrationFailure` | must | int 3.10, 5.2 |
| Circuit breaker per integration account: open after 5 failures in 5 minutes, one trial call after 5 minutes, closed on success; staff can force it open or reset it | adds | must | int 3.10 |
| Test mode per integration (off, test, live) with separate credentials | adds | must | int 3.10, 5.2 |
| Razorpay: keys seen only by OWNER and ADMIN; webhook health from our own rows (Razorpay disables a webhook after 24 hours of failures and someone must re-enable it); the refund idempotency header; settlements; Smart Collect for schools on request | exists: `handle_webhook` verifies and deduplicates; adds | must | int 4.1 |
| Amazon SES: SNS signatures verified (django-anymail does not) or basic auth over HTTPS as the control, the topic ARN restricted; configuration-set events; bounce and complaint rates against 5% and 0.1%; our suppression list kept in step with SES's | exists: `EmailSuppression`, anymail tracking; adds | must | int 4.3 |
| MSG91: a secret in a custom webhook header because its webhooks are unsigned, deduplication on its request id, delivery reports with failure reasons ("Template Id not found on DLT") | exists: `SmsLog`, the daily cap; adds | must | int 4.2 |
| Google sign-in: the `hd` and `email_verified` checks in the adapter, accounts keyed on `sub` | adds | must | int 4.4 |
| ERPNext: the integration user and its key, the webhook secret, the per-flow switches, the sync's health (outbox depth, dead letters, the last reconciliation) | adds | must | erp 5.5, 5.8 |
| Feature flags (key, state, audience, owner, notes) with history and audit; flags touching payments, sign-in or consent need an approval | adds | should | lms 6.5; rbac 7 |
| Maintenance mode for OWNER and ADMIN, with a reason, a banner and an automatic expiry; the admin host stays reachable | adds | should | rbac 7 |
| Scopes declared against what the panel needs (Shiprocket modules and buyer-details access, the R2 token's bucket, Razorpay roles) | adds | should | int 5.2 |
| Usage and cost (messages sent and their cost, the Shiprocket wallet and the month's freight, R2 storage against the free tier, the error tracker's quota) with alerts at a spend or balance threshold | adds | should | int 5.2 |
| Alert rules per integration (on the first failure or after retries, at once or as an hourly digest, auto-pause after sustained failure with an email to the owner) | adds | should | int 5.2 |
| Secrets inventory (the Django key, the JWT key, provider keys, webhook secrets, the health token): owner, last rotated, next due, never values | adds | should | rbac 7, 2.6 |
| Notification settings: which events email whom, each person's own choices | adds | should | lms 6.5 |
| DigiLocker through API Setu for parental age checks; a live Zoho sync; an e-invoice provider through India Compliance | adds | later | int 4.5, 4.7; erp 4.1 |

**Easy and smooth:** each card answers "is it working, since when, and what do I do if not" in one look; Replace
tests the new credential before saving it, in one sitting; a provider whose token cannot overlap gets a written
warning on the Replace screen; test and live never look alike.

### 5.19 System

**Owner:** platform; it shows ERPNext's health through its API and links to ERPNext's own System Health Report.
**Used by:** ADMIN, OWNER; AUDITOR reads the audit log; periodic tasks stay superuser-only.

| Capability | Exists / adds / ERPNext | Priority | Reference |
|---|---|---|---|
| Hash-chained, append-only `AuditLog`: the runtime database role may only insert and read it, a trigger refuses updates, deletes and truncation, a nightly job verifies the chain, and each day's rows go as JSONL with the chain head to a bucket-locked R2 bucket | adds: `staff.AuditLog` | must | rbac 3.3 |
| Audit log viewer: filters by actor, action, target, outcome, dates, request id and address, saved views ("all refunds above ₹5,000 this month"), OWNER and AUDITOR only, reading it is itself audited, exports with the chain hashes, a weekly skim of high-risk events | adds | must | rbac 3.5 |
| Sync monitor: the outbox per flow (pending, sent, failed, dead), replay of dead letters, ErpLink lookups, inbound ERPNext events, each night's reconciliation with its differences, ERPNext's job queue and Webhook Request Log | adds | must | erp 5.2, 5.8 |
| Imports, exports and bulk jobs with dry runs, progress, result files and errors per row | adds: `staff.Job` | must | lms 6.3 |
| Backups of both engines: CloudNativePG continuous to R2, mariadb-operator's physical backups, the ERPNext site and files every 6 hours, `site_config.json` kept apart; the last success with time, size, checksum, encryption and location; an alert past 26 hours; retention (30 days); the last restore test (date, who, result, duration); an immutable copy in a locked bucket against ransomware | exists: `scripts/backup.sh` from the host's crontab with `upload_backup`, `BACKUP_KEEP_DAYS=30`; adds | must | rbac 7; erp 6.1 |
| Restore drills every quarter into a scratch namespace, with the erasure ledger re-applied after any restore | adds: a runbook and a record | must | erp 6.1; rbac 4.5 |
| Logs kept 180 days rolling now (CERT-In) and one year from 13 May 2027, covering successful and failed events; a log inventory (what, where, how long, who reads); clocks synced by NTP to NIC or NPL servers or cloud time | adds | must | rbac 4.7, 3.4, 7 |
| Errors: the tracker's counts and links, never raw payloads, personal data scrubbed | exists: Sentry with `send_default_pii=False` and a scrubbing `before_send` | must | rbac 7; int 4.9 |
| Mail and SMS: sent, delivered, bounced and complaints; the suppression list; SPF, DKIM and DMARC status; the Postmaster spam rate under 0.3%; SMS status per kind with DLT ids and failure reasons, OTP volumes and daily-cap hits | exists: `EmailSuppression`, `SmsLog`; adds | must | rbac 7; int 4.3; lms 0 |
| Dependencies: the last pip-audit and npm audit runs, image scans, open advisories by severity with a 7-day target for critical ones, ERPNext and Frappe advisories checked weekly | adds: CI jobs and the page | must | rbac 7; erp 6.6, 3.2 |
| Hardening of the admin host: staff endpoints answer 404 on any other host; Django's `/admin/` only there and only for superusers; HSTS of at least a year with subdomains; a CSP with `frame-ancestors 'none'` and a report endpoint; `no-store` on staff responses; `noindex`; `__Host-` cookies with SameSite Strict; the `x-middleware-subrequest` header stripped at the proxy; every new Django path added to the proxy's list and `DJANGO_PREFIXES` | exists: CSP on Django pages, `secure_admin_login`; adds | must | rbac 2.4, 1.7; inv 1.4, 8 |
| Card data never shown or stored; the checkout page's scripts inventoried and their hashes checked daily, with an alert on change | adds | must | rbac 4.8 |
| Liveness probes that never test the database or Celery; readiness and the external check may | adds | must | int 4.9 |
| Jobs page: each scheduled job with its last run, next run and last error, a pause switch; Celery queues with active and failed tasks, retry and cancel audited | exists: the beat and results tables in the admin; adds | should | lms 6.5; rbac 7 |
| Health and a status page: database, cache, storage, Celery, Razorpay, email, SMS, Shiprocket, ERPNext's ping, MariaDB and Valkey; an external monitor and 90-day uptime | exists: `/health/` and `/health/web/` behind `X-Health-Token`; adds: an external monitor (Better Stack, UptimeRobot or Uptime Kuma) | should | lms 6.5; int 4.9 |
| Cron monitors for the beat jobs (check-ins or heartbeats) | adds | should | int 4.9 |
| Config view, masked: environment, DEBUG, headers, CSP, allowed hosts, versions, which secrets are set with a 4-character fingerprint | adds | should | rbac 7 |
| Abuse controls: throttle hits by endpoint, axes lockouts with unlock, Turnstile failures, blocklists with a reason, an expiry and audit; a honeytoken | adds | should | rbac 7, 2.4 |
| Launch-readiness page gathering the scattered signals (placeholders, `check_seller`, the support address, `learn.E001`, start-up guards, `live_mode()`, health, `check --deploy`, the DEPLOYMENT.md checklist) | adds | should | inv 0, 8, 11.1 |
| ERPNext's System Health Report, Error Log and Scheduled Job Log linked; queue depth from an exporter | ERPNext | should | erp 6.2 |

**Easy and smooth:** System opens on a single status line per subsystem (green, yellow, red, with the time of the
last change); a dead letter is replayed from the row that shows it; the backup row says in words when the last
restore was proven to work; nothing on this page writes without a reason and an audit event.

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
