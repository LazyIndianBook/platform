# Changelog

What changed in the ExamLeaf web platform, newest first, by phase. Every phase below was built on 8 October 2026; the
commits are in `git log` (phase 4: abffe6f and e5abda5; phase 5 A and B with the redesign's stage 1: f8e4e5f; phase 6 D
and E: 4e30e59; the redesign's stage 2 so far: ba0b9dd). Details of each feature are in README.md; the numbers of the
tests are those of `pytest` at the end of the phase.

## Phase B, Tax (9 October 2026)

The storefront's GST was a rate typed on each product, its documents numbered by looking for the last serial in one
EL series, and the shipping taxed at the cart's highest rate. Plan 5.9 and research 5 ask for what decides the tax to
live in data with dates, for documents of the right type in series, and for FINANCE to see what is due; the panel gets
a Tax module for it (`shop/README.md` "Tax" has the rules, API.md "Tax (staff)" the endpoints). 1,086 backend tests
pass on SQLite (12 skipped, 1,793 subtests), 44 of them new in `shop/test_tax.py` and `shop/test_staff_tax.py`, which
also pass on PostgreSQL (two invoices numbered at once by two threads take consecutive numbers there); the
authorization matrix covers every new endpoint.

- **The HSN and SAC master** (`HsnCode`, `HsnRate`): each code's rates are its history, dated and citing the
  notification that set them, never rewritten; the migration seeds eleven codes (books exempt from 22 September 2025
  under 10/2025-Central Tax (Rate)). A product points to its code and its GST is the code's rate on the day of the
  order; one that disagrees gets the red chip (`Product.tax_problem`) and a line on the panel's list.
- **Bundles** are invoiced by their treatment: split into their components (the default), composite or mixed.
- **The place of supply** is the billing state the checkout now asks for (`Order.billing_state`): a course or an e-book
  alone where the buyer says, else the parcel's state, else Assam.
- **Documents**: a tax invoice, a bill of supply or, for a mixed cart, an invoice-cum-bill of supply (Rule 46A),
  numbered gapless under a row lock from 1 each April (`DocumentSeries`); EL and CN until FY 2026-27, one series a type
  from `SHOP_SERIES_FROM_FY` (`SHOP_SERIES_PREFIXES`); the test series T and TC kept out of every number and return.
  Shipping follows the goods it carries (exempt with books, shared by value on a mixed cart), a coupon is allocated
  pro rata, the HSN codes print to `SHOP_HSN_DIGITS`, and Rule 46's checks are listed. A cancelled document keeps its
  number and its PDF is marked so.
- **Credit notes** are refused after 30 November of the year after the invoice's (CGST s.34(2)): the refund still goes
  out and FINANCE's inbox says so (`credit_note_missing`).
- **GSTR-1** (`shop/gstr1.py`): b2cl, b2cs, cdnur, exemp, hsn-b2b, hsn-b2c and docs in the Offline Tool's templates;
  `manage.py export_gstr1` still streams, and the panel runs it as a job (`gstr1_export`, above `export_rows` approved
  first).
- **The threshold monitor** (every night at 01:45): ₹2, 4, 5 and 10 crore of turnover, invoices above ₹1 lakh to
  another state, taxable goods above ₹50,000 in a parcel; the first crossing in a year opens one inbox item
  (`tax_threshold`). **The calendar** of a month comes from the law's dates and the QRMP switch (`SHOP_GST_QRMP`, a
  panel setting).
- **Records**: an order with a real-series document keeps its customer's details 72 months after its year's annual
  return (`forget_orders` skips it).
- **The staff API** (`/api/v1/staff/tax/`): the master and its rates (`shop.view_hsncode`, `shop.change_hsncode`), the
  products that disagree, the documents with their PDF (audited) and cancelling one (`staff.cancel_document`, high),
  table 13 (`shop.view_documentseries`), the threshold card and the calendar (`shop.view_taxthreshold`), the GSTR-1 job
  (`staff.run_gstr1`). FINANCE, ADMIN and OWNER hold them; AUDITOR reads.
- **The console's Tax module** (`/tax/`, under Shop): the month's dates, the threshold card and table 13; the master,
  a code's history and a new dated rate behind a save bar; the documents, one with its lines and checks, cancelled with
  its number typed; table 13 by year or month; the GSTR-1 export with its progress and file. The save bar (`ActionForm`
  `saveBar`: Save and Discard once something is typed, a warning before leaving) is new and shared. Console: Vitest
  98 (11 new), Playwright 6 in mock mode, every tax page checked with axe at 1280, 390 and 320 px and the tax journey
  at both widths.
## Phase B, Legal and privacy (9 October 2026)

The Admin Control Panel's Legal and privacy module (plan 5.15): the compliance cockpit, legal holds that the erasure
obeys, the retention schedule in code with its nightly clean-up, numbered policy versions, the e-commerce disclosures,
the yearly dark-pattern self-audit, nominees, marketing consent withdrawn as easily as given, and the one audience
function that keeps children out of marketing. Staff endpoints in `staff/privacy_api.py` (API.md "Legal and privacy
(staff)"); the console's pages under `/privacy/`; the website's footer, contact page, versions and parent link.
1,083 backend tests pass on SQLite (12 skipped, 1,913 subtests), 53 of them new. Console: Vitest 96, Playwright 6 in
mock mode (the day's work gains legal and privacy) and 10 against this backend (`E2E_STAFF_API=real`: a legal hold the
dry run names); website: Vitest 213.

- **The erasure obeys its holds and leaves a ledger.** The dry run (`staff.privacy.erasure_report`) says what stays,
  why and until when, a sentence each: the books by financial year (8 financial years, or 72 months after the year's
  annual return, whichever is later: `examleaf.retention.books_until`), a year of processing logs by the account's
  number only, each legal hold, the intermediary rule's 180 days when `SUPPORT_INTERMEDIARY_RULES` is on, the consents.
  `DeletionRequest.complete()` waits for a legal hold on the account and for a child's parent's confirmation (their
  own link, `POST parent-consent/<token>/ {"confirm": "deletion"}`, or staff with the evidence); the nightly purge files
  the wait in the inbox. Each erasure stays as a ledger line (the address's keyed hash), copied to the backups' bucket;
  `manage.py reapply_erasures` erases again what a restore brought back. Once done, one inbox task per processor that
  keeps personal data (`ProcessorRecord.holds_personal_data`, `erasure_action`), and the confirmation email says what
  stays and until when, with the contact block. Access requests list who else processes the data.
- **Legal holds** (`accounts.LegalHold`: an account or one record, a reason, an end or a release) with
  `staff.manage_holds` (new, high: FINANCE, ADMIN, OWNER); the retention clean-up leaves held orders as they are.
- **The retention schedule in code** (`examleaf/retention.py`): each kind of record's minimum in law with its source
  and the day it changes, what this site keeps, what deletes it; read by `ops.tasks.trim_expired` and `purge_expired`
  (nightly, `single_run`, idempotent). Fixed: the SMS log keeps its rows a year and blanks the last digits at 90 days,
  webhook records and task results go at 7 days, the app's phones silent for 90 days are deleted, the orders past their
  books' period lose the customer's details, and Docker keeps 50 MB × 10 files of logs a service.
- **The compliance cockpit** (`GET privacy/cockpit/`): every clock the rules start (data requests' 48 hours and month,
  complaints' when the support app is there, breaches' 6 and 72 hours, parents' confirmations, the self-audit), the
  consents by the privacy notice's version, the legal calendar.
- **Policy versions**: a legal page's version is numbered with the day it is in force from and a line on what changed;
  published now or for a later day (`pages.tasks.publish_due` at 00:01), diffed against the one before; public
  `GET pages/<slug>/versions/`.
- **The e-commerce disclosures** (16 site settings in the group `disclosures`, saved together with one reason) in
  `config/`'s `disclosures` (never CERT-In's contact); **the dark-pattern self-audit** (`staff.DarkPatternAudit`, the 13
  patterns, completed once; `staff.manage_compliance`, new, high), a reminder from 1 December, and its certificate in
  `config/` from its day.
- **Nominees** (`accounts.Nominee`, `me/nominee/`, the staff read masked), **marketing consent withdrawn**
  (`me/consent/withdraw/`, the processors told to stop), the consent ledger's channel and parental methods, and
  `accounts.audiences.marketable`: never anyone under 18, an unknown age only on a verified consent.
- **The console** (`../examleaf-admin/`): `/privacy/` is the cockpit; legal holds, the retention schedule, the policy
  versions with their diffs and publishing, the disclosures as one form with a save bar, the self-audit completed with
  the year typed; the erasure's dry run lists what is kept as sentences; a customer's page shows their nominee.
  **The website** (`../examleaf-frontend/`): © the legal name, the Grievance Officer and the certificate in the footer,
  the whole block on the contact page, "Version N, in force from …" with `/<page>/versions/`, and a parent's
  confirmation of their child's deletion on their own link.
## Phase B, Orders (9 October 2026)

The Admin Control Panel's Orders module (plan 5.3; [shop/README.md](shop/README.md), API.md "Orders (staff)"): staff
find, act on, refund, take back, make and pack orders in the panel instead of the Django admin and the shell, every
rule the shop's own and every money step through the approvals. 1,101 backend tests pass on SQLite (11 skipped),
31 of them new (`shop/test_staff_orders_api.py`, two in `insights/tests/test_risk.py`), with 40 rows for the module's
endpoints in the authorization matrix. Console: Vitest 97 (10 new), Playwright 8 in mock mode (2 new) and 10 against
this backend (`E2E_STAFF_API=real`, the Orders journey new); website: Vitest 210 (3 new).

- **Orders for staff** (`/api/v1/staff/orders/`, `shop/staff_orders.py`): the list with its tabs (to pack, shipped,
  returns, cancelled, drafts), filters and saved views, test orders out unless asked; a search by number, document,
  email, phone digits, AWB, book code or name, a search for a person being a `customer.lookup` event with the query's
  keyed hash; the record with what each book was invoiced at, payments, refunds, documents, parcels, the customer
  masked, risk, hold, tags, its ERPNext documents, the moves the state machine allows for the person (and the one
  next step) and a timeline of its history, payments, parcels, messages, notes, returns and, for the log's readers,
  its audit events. A child's order opened is a `sensitive_read`. Moves: pack, send by hand, deliver, cancel, hold,
  release, tags, a message again, the invoice made or sent again, payment links, offline payments.
- **Refunds by line or by bank**: the lines' invoiced values (their share of the coupon and offers off) and the
  shipping, the copies back into stock or not, to the source through Razorpay (normal or optimum) or by bank or UPI
  (cash on delivery and transfers; an online payment with the customer's agreement): the payee encrypted and masked,
  FINANCE marking the transfer paid with its UTR, which makes the credit note once. The 6-month warning, the
  Idempotency-Key and the change request kept on the refund. A cash-on-delivery parcel back undelivered is cancelled
  with its invoice credited and no money moving (no `returned` state, the plan's 10.1).
- **Returns** (`ReturnRequest`): asked for on the website within `SHOP_RETURN_DAYS` of delivery
  (`POST /api/v1/orders/<number>/returns/`; the order shows `returns`, `can_return`, `return_until`) or by staff;
  approved or declined, the label sent, received and inspected (back into stock or damaged), refunded; an inbox item
  due in 48 hours, the customer emailed at each step. Deciding (`staff.handle_return`) is apart from receiving
  (`staff.receive_return`).
- **Staff orders and quotes**: `order.staff_discount`: within the maker's `discount_percent` made at once, beyond it or
  at ₹0 the order does not exist until FINANCE approves; `POST orders/preview/` shows the price and the rule's answer
  before saving; quotes made into orders once. The owners' weekly email (Mondays 08:00, once) lists staff discounts,
  offline payments and ₹0 orders by who gave them.
- **The packing room**: the queue oldest first (PACKER's scope now includes cash-on-delivery orders placed), the A4
  packing slip with a QR code, the 4×6 label for parcels sent by hand, the pick list; bulk jobs `orders_pack`,
  `orders_print`, `orders_cancel` (250 at most) and `orders_export` (a CSV line per book with the GST split).
- **Cash-on-delivery risk** (`insights/jobs/risk.py`): the PIN code's and district's returned parcels from the shipping
  app's outcomes, the customer's past returns by keyed hashes, a first COD order, its value
  (`SHOP_COD_HIGH_VALUE_INR`), an address no courier could find; a high score holds the order for a payment check
  while `SHOP_COD_HIGH_RISK_HOLD` is on. Nothing about a person is stored.
- **Messages**: every status message recorded with its SMS sent, held or dropped; an SMS due between 21:00 and 08:00
  sent at 08:00 if still true; a "packed" email; bank refunds and returns emailed.
- **The console** (`../examleaf-admin/`): `/orders/`, `/orders/<number>/`, `/orders/packing/`, `/orders/returns/`,
  `/orders/new/`, `/orders/quotes/`; DataTable's fixed views, chosen rows with a bulk bar, and Space to look at a row.
  **The website** (`../examleaf-frontend/`): the order page's return form and each return's state.
## Phase B, Staff, settings and integrations, system (9 October 2026)

The panel's People, Settings and System modules held what Phase A built: roles given and taken, switches with a
reason, a status page. Plan 5.17 to 5.19 and 7.11 and the research (RBAC 1.8, 2.9, 3.5, 4.8 and 7; integrations
3.3, 3.10, 4.2 and 5.2) ask for more: what a role may do before it is given, a person's access with its last use, offboarding
as a checklist, passkeys for the privileged roles, the integrations' keys, webhooks and dead letters handled from the
panel rather than the shell, the templates DLT registers, and the system's backups, logs, dependencies, hardening and
scripts in one place. 1,131 backend tests pass on SQLite (11 skipped, 2,104 subtests), 63 of them new; the
authorization matrix covers every new endpoint, and every call to another service in the tests is a recorded answer.
Console: Vitest 97, Playwright 9 in mock mode and 10 against this backend (`E2E_STAFF_API=real`).

- **People** (`staff/services.py`): the role catalogue (`people/roles/`: each role's two lines from
  `accounts/roles.py` `ROLE_CARDS`, its capabilities by area with their risk, limits, scopes, conflicts, ERPNext role
  profiles, passkey, idle limit and members); a person's Access tab (`people/<id>/access/`: roles with who gave them,
  when, why and until when, every permission by area with the last use of the high and critical ones from a year of
  the audit log, open change requests, second factors); a role change previewed before it is asked
  (`people/<id>/roles/preview/`: gains, losses, limits, scopes, idle limit, separation of duties, the approval and
  checker, the passkey to come, the ERPNext profiles); the ERPNext user a person should have (`people/<id>/erp/`,
  applied by hand: ERPNext's role sync is not built).
- **Offboarding as a checklist** (`StaffOffboarding`, `OffboardingStep`): what the panel did at once, with its counts
  (deactivated, sessions ended, tokens blacklisted, roles, scopes and temporary grants gone, requests withdrawn,
  tickets unassigned, API keys revoked), and what an owner ticks by hand (the ERPNext user, external accounts,
  security keys, the last 90 days reviewed), with an `offboarding` inbox item until the last one. A temporary role
  that ends opens `role_expired` on the person.
- **Passkeys and sessions**: a member of `STAFF_PASSKEY_ROLES` (OWNER, ADMIN, FINANCE) without a passkey or security
  key is asked for one before anything else (`403 passkey_required`, the manifest's `steps`; the Django admin sends
  them to the website's security page). Each member sees and ends their own sessions (`people/me/sessions/`), and
  after a second factor changes is offered once to end the others (`offer_end_sessions`).
- **Settings**: grouped (`staff/config.py` `group`), each setting's and flag's history (`…/history/`), a known
  switch (the ERPNext ones) true or false only and back to the environment's with null. Bulk actions have their own
  rate (`STAFF_THROTTLE_BULK`) rather than the exports'.
- **Connections** (`integrations/connections.py`, `integrations/api.py`; API.md "Connections (staff)"): a card per
  integration (Razorpay, Shiprocket, manual payments, MSG91, WhatsApp, SES, the buckets, the error tracker, Google,
  ERPNext): status, mode, where the keys come from and their last four characters, the last test, the calls' errors
  and p90, the circuit, and what the provider adds (Razorpay's webhook health, SES's bounce and complaint rates from
  the new `ops.EmailStat`, the buckets, ERPNext's sync). A test is one harmless read; new keys are kept only once
  they pass it (audited with their last four characters, the owners emailed); modes switched; circuits held open or
  reset; webhook tokens rotated (shown once, the previous one valid 24 hours); events, calls and dead letters listed,
  replayed or discarded. Razorpay and MSG91 read their keys from the panel once it holds some, the environment's until
  then (`integrations/README.md` "Precedence"). Razorpay's webhook silent for `INTEGRATION_WEBHOOK_SILENCE_HOURS`
  opens `webhook_silent`.
- **Messaging** (`ops/README.md`): the template registry (`MessageTemplate`: DLT and MSG91 ids, header and suffix,
  typed variables, category, approval, last use, self-certification; `staff/templates/`, a test sent to oneself),
  which `ops.sms` sends with before `MSG91_TEMPLATE_<KIND>`; nightly `template_idle` and `template_certify` items;
  MSG91's delivery reports (`POST /api/hooks/sms-events/`, its token from the connections page, kept once) written
  on the SMS log; SES's SNS messages' signatures verified (`ops/ses.py`, `SES_SNS_TOPIC_ARN`) and its account
  suppression list copied each night.
- **System** (`staff/system_api.py`): a status line per subsystem with when it came to its state; the sync monitor
  and a link search; the backups (each source's newest object and its SHA-256 from the `.sha256` sidecar
  `upload_backup` now writes, `backup_stale` after `BACKUP_STALE_HOURS`) and the restore drills (`RestoreDrill`); the
  log inventory (`examleaf/logs.py`) against CERT-In's 180 days, the clock and `LOG_TIME_SOURCE`; CI's pip-audit and
  npm audit report (`scripts/dependency_report.py` in the `dependency-audit` job, `manage.py
  load_dependency_report`); the admin host's hardening, each check with its fix; the checkout's and the console's
  sign-in's scripts inventoried each day (`ScriptInventory`, PCI DSS 6.4.3 and 11.6.1). On Mondays the owners get the
  week's high-risk audit events by email.
- **The console**: the role catalogue, a person's Access, Offboarding and ERPNext tabs, a grant previewed in its form,
  one's own sessions on the account page, the passkey and end-the-others dialogs, grouped settings with their history,
  the connections and each connection's page, the templates, and the system's six pages; its mock answers each state.
## Phase B, Content (9 October 2026)

The Admin Control Panel's content module (content/README.md; API.md "Content (staff)"): the text of a question or a
solution changes as a draft that a second person reviews and publishes, readers report mistakes from the website,
imports from the books repository run from the panel, and the books' legal deposits are tracked. 1,134 backend tests
pass on SQLite (11 skipped, 2,249 subtests), 53 of them new in content/ beside the matrix's content rows; the console's
Vitest 118 and Playwright 8 in mock mode (the content journey also against this backend), the website's Vitest 213.

- **Drafts and their review.** `Question` and `Solution` gain a state (published, draft, in review), a JSON `draft`,
  who drafted it and who published it, when; a question also `is_published`. The panel's saves go to the draft after
  the LaTeX check (`content/latex.py`: delimiters, braces, environments, forbidden commands, raw HTML, pictures'
  alt text; no false alarm on the books repository's 23,217 texts), and the site keeps the live text. `ReviewTask`:
  submit, approve, ask for changes, publish (approving on the way), never by whoever edited or submitted the draft
  (`403 own_edit`, owners included); a publish keeps the text it replaced, so it can be rolled back; any version comes
  back from the history (a text into the draft). The Django admin shows the texts read-only to all but superusers.
- **Reported mistakes.** `POST /api/v1/reports/` (Turnstile, a honeypot, 5 an hour and 20 a day per address; spam
  set apart and purged after 30 days), an inbox item per report for whoever triages the subject, the triage
  (confirmed, rejected with a reason, fixed online, fixed in a printing; reopened), the reporter told once and their
  address deleted then (or at a rejection); the quiz's item-analysis flags join the queue nightly; errata per book and
  printing (`GET /api/v1/errata/?book=`). The website: "Report a mistake" under every solution and revision clip, with
  the print run its QR code carries (`?printing=`; the panel makes a print run's code).
- **Imports as staff jobs** (`content_import`, `staff.import_content`, high): a dry run, then its apply within 24
  hours for the same commit (refused once the repository moved), each paper in its own transaction and only the fields
  that changed; a question gone from the books is unpublished, not deleted. `import_papers` shares the code and gains
  `--dry-run`.
- **Books, papers, deposits.** A book's ISBN (its check digit checked when set or changed, as the shop product's),
  format and publication day; the copies sent to the four public libraries, with an inbox item until all four have the
  edition (`CONTENT_LEGAL_DEPOSIT_DAYS`, 30, to be verified against the Act). A paper is published, unpublished or made
  its book's open sample by `POST …/papers/<id>/publish/` (`staff.publish_paper`, so a REVIEWER can), the sample moving
  from the book's other paper; the editor's PATCH and the admin leave publication to publishers.
- **Permissions.** `staff.triage_report` (medium) and `staff.import_content` (high) join the catalogue; CONTENT_EDITOR
  and REVIEWER gain the module's queues (reviews, reports, deposits), REVIEWER the imports, SUPPORT reads the reports;
  inbox items of a subject are narrowed by it. Three beat tasks: `content-flag-items`, `content-purge-spam`,
  `content-legal-deposits`.
## Phase B, Support (9 October 2026)

A small helpdesk of our own (plan 5.14; Frappe Helpdesk is not installed), so that every complaint has a number, the
deadlines the law sets and an answer on record: the new `support` app (`support/README.md`), the panel's Support
module (`../examleaf-admin/`, `/support/`) and "My requests" on the website (`../examleaf-frontend/`,
`/account/requests/`). 1,129 backend tests pass on SQLite (12 skipped, 1,961 subtests), 73 of them the support app's
(its concurrency test on PostgreSQL, where the support, matrix, contract and roles tests pass too: 244); the
console's Vitest 119 (32 new), its Playwright 6 in mock mode and 10 against this backend; the website's Vitest 211
(4 new) and its My requests journey with the 320 px checks.

- **Tickets** (`Ticket`, `TicketMessage`, `TicketAttachment`, `SavedReply`): a number of their own series
  (`SR-2026-000123`, gapless under a row lock), a source (the website's form, email, a call, WhatsApp, a complaint the
  National Consumer Helpline forwarded with its docket), a category, a status, the requester as an account or an email
  address and a mobile number (encrypted at rest with `INTEGRATION_KEYS`, found by keyed hashes, masked in every
  answer, revealed with a reason), the linked order, data request or paper, and history.
- **The legal clocks** (`support/clocks.py`) in calendar time in India, never paused and across month ends: 48 hours
  to acknowledge and a calendar month to redress (E-Commerce Rules), 30 days for an NCH complaint, a month then 90 days
  for a privacy request (SPDI, then DPDP Rules), the IT Rules' 24 hours and 15 days behind `SUPPORT_INTERMEDIARY_RULES`
  (off: counsel's answer pending). Every 15 minutes the inbox hears at three quarters of a clock (`ticket_due`) and a
  breach is flagged once (`ticket_breach`, `support.clock_breached`); resolved tickets close after 4 days.
- **Where tickets come from**: the contact form now makes one (its number in the acknowledgement; the support address
  still gets a copy while `SUPPORT_COPY_TO_EMAIL` is on); "My requests" (`GET`/`POST /api/v1/me/tickets/`); email to
  the support address forwarded to `POST /api/hooks/support-mail/` (the `support_mail` account's token, the raw body
  kept once, a loop guard, threading by a secret thread id, the headers and the number); staff log calls, WhatsApp
  messages and NCH complaints. Spam is quarantined and purged after 30 days.
- **The acknowledgement** by email, or SMS when only a phone is known (`ticket_ack`, held at night); from
  `SUPPORT_COMPLAINT_COPY_FROM` (1 January 2027) with a copy of the complaint as recorded. Only a person's reply sets
  the first response.
- **The staff API** under `/api/v1/staff/support/` (API.md "Support (staff)"): the queue by the next deadline (lookups
  by email or phone logged as hashes), a ticket with its sidebar (orders with Razorpay ids, payments, refunds,
  shipments, invoices, entitlements, codes, devices, past tickets, consents; each part by the reader's permissions)
  and the saved replies filled for it in its language, replies and notes with mentions (`ticket_mention`), statuses
  with what closing asks for, reopening, assignment, the requester's details revealed, and the actions: a refund
  through `order.refund` (lines from zero; 202 above the limit), cancel, the invoice and the confirmation again,
  course access extended, a book code looked up by its digest, a data request started. The summary and the agents.
  Opening a ticket is a `sensitive_read`; every change an audit event naming the ticket's number only.
- **Permissions**: `staff.handle_ticket` (medium: SUPPORT, SALES on order, payment and school-order tickets, ADMIN),
  `support.note_ticket` (a content editor's notes on content errors), `support.view_ticket`, the saved replies' model
  verbs (changes ADMIN's), `staff.export_grievances` (high: ADMIN, OWNER, AUDITOR); the scope kind `ticket_category`.
- **The grievance register**: the job `grievance_export` (a dated CSV, no personal data; above `export_rows` it waits
  for an approver) and `manage.py grievance_register`. An erased account's tickets keep their numbers and dates and
  lose the person; a test order's tickets stay out of the queue, the summary and the register on a live site.
- **The console's Support module**: the queue with its tabs and countdowns and the module's numbers, the ticket (the
  conversation, the reply box with saved replies a keystroke away, internal notes naming colleagues, the deadlines, the
  status with its closing fields, the actions, assignment, sorting and correcting, the acknowledgement; the customer
  and the audit trail beside it), logging a call or an NCH complaint, the saved replies (a delete undone within 5
  seconds) and the grievance register's job; its mock, its Vitest tests and a journey in each Playwright project.
- **The website**: `/account/requests/` lists the account's requests with their number, status and the latest answer
  date, and asks a new one; "My requests" in the account's navigation.

## The staff console on the staff API as built, and the website's side of an impersonation (9 October 2026)

No backend change. The console (`../examleaf-admin/`) and the website (`../examleaf-frontend/`) now speak the staff
API and the impersonation endpoints as this backend has them. Console: Vitest 74, Playwright 6 in mock mode and 9
against this backend (`E2E_STAFF_API=real`); website: Vitest 188.

- **The console's types come from this schema** (`manage.py spectacular --format openapi-json` into the console's
  `openapi.json`, then `npm run api:types`), and every call goes through `openapi-fetch` on those paths, so a renamed
  path, parameter or field is a type error there. Its permissions are the catalogue's codenames (`staff/catalogue.py`,
  the shipping desk's and the insights' included, and the ERPNext sync's `erp.*`), and it acts on the codes as sent: a
  202 change request (its number, state and checker's permission), `session_idle` and `session_expired`,
  `reauthentication_required`, `break_glass_reason_required`, `impersonating`, a 404 that is "not found, or not
  yours", and a refused staff Google sign-in's `?error=staff_google_*`. Notes beside every record, a break-glass
  session's reason and the policies due before anything else; jobs cancelled and their files fetched by a fresh signed
  link; the audit export as a file or a job; maintenance through `PUT settings/MAINTENANCE_MODE/`. Its mock answers the
  same contract with fixtures for every state; a production build compiles its switch off, as before. Its README's "The
  contract this console speaks" lists every call.
- **The website's side of an impersonation**: `/account/impersonate/?token=…` sends the console's token once
  (`POST /api/v1/account/impersonate/`) and opens the account, or says the link is not valid, expired or used. While
  allauth's session user carries `impersonation`, a band that cannot be dismissed names the colleague (masked) and the
  time, with End (`DELETE /api/v1/account/impersonate/`), and the payment, address, password, email, mobile number,
  two-step, consent and deletion actions are drawn disabled with the reason. Its README's "Impersonation"; its
  Playwright spec (`e2e/impersonation.spec.ts`) skips on a backend without the endpoint.

## Resilience: nothing waits without a limit (9 October 2026)

The backend audited for hangs, crashes and state kept in a process, then measured under load (RESILIENCE.md: the
checklist item by item, the load test, every knob, what the Kubernetes chart must change, what is deferred). Each fix
left a test that fails without it where one could. 1,028 backend tests pass on SQLite (11 skipped, 1,637 subtests) and
1,038 on PostgreSQL (1 skipped), 36 of them new. Two fail, as they do on design/answer-script itself (84a3e8d: COD
reconciliation made medium risk), untouched here:
`shipping/tests/test_money.py::test_finance_reconciles_a_remittance_with_the_banks_credit` and
`staff/tests/test_impersonation.py::test_while_it_lasts_money_passwords_and_the_account_are_refused_and_each_request_is_audited`.

- **Timeouts on every outbound call.** Razorpay 3 s to connect and 10 s per read (was 10 s for both); MSG91 the same;
  the buckets and SES through boto3 3 s and 20 s (SES 10 s) with three tries in standard mode (were boto3's 60 s, 60 s
  and five legacy tries); anymail's HTTP backends (3, 10); Firebase 20 s (was 120 s); PostgreSQL 5 s to connect. A
  statement may run 15 s in gunicorn and 600 s in Celery (none in `manage.py`), a transaction sit idle 60 s and 600 s
  (`DB_*`).
- **A slow provider no longer stalls the site.** Razorpay's and MSG91's calls share half of a gunicorn process's threads
  (`examleaf/bulkhead.py`); beyond that a call answers at once with the provider's "could not be reached". Under load
  with Razorpay and MSG91 answering after 10 s, the fast endpoints' slowest 1% fell from 8 s (13 s on kept-alive
  connections) to about 2 s.
- **gunicorn from one config file** (`gunicorn.conf.py`) in the image, compose and the chart: workers and threads from
  the environment, its timeouts, recycling after 5000 requests with a jitter of 2500 (1000 and 100 restarted every
  process at once under load), the site imported once in the master (`preload_app`: a recycled process serves at
  once), `/dev/shm`, JSON logs, a stuck process's thread stacks. Compose stops web in 40 s and the workers in 5 minutes
  (was Docker's 10 s).
- **Celery**: tasks acknowledged once run and put back when their process dies (with every task checked for a second
  run: an SMS or an email is not sent twice, the reminder and the data export stay acknowledged early), one that kills
  its process every time failing after three runs (`examleaf.celery.Task`); one task at a time per process;
  processes replaced after 200 tasks or 300 MB; time limits by kind (270/300 s, PDFs 60/90, the long jobs 1500/1800);
  Redis's visibility timeout two hours; the broker retried at start-up. The periodic jobs that send or alert take a
  lock for their run (`single_run`), and the stock alerts and held SMS claim each message: overlapping runs sent them
  twice. The quotation PDF is made by the worker, not in the admin's request. The staff and erp apps' tasks follow the
  same rules.
- **Health**: `/health/live/` for liveness (no database, no Redis); `/health/web/`, readiness, is the database and the
  migrations (`examleaf.health.Migrations`): a cache or bucket outage no longer takes every pod out of traffic, and a web
  container starts without its cache; `/health/` keeps everything for the monitor. Compose's container check is the
  liveness one.
- **The cache's Redis silent**: after a failed call a process asks it nothing for five seconds (a request makes 4 to 14
  cache calls, each was a second).
- **In-cluster webhooks**: ERPNext's (`/api/hooks/erp-events/`, HMAC-signed) are no longer redirected to https when
  they come to web's Service over plain http; through PgBouncer (values-ha.yaml) no startup options are sent.
- **Checkout**: one checkout of a cart at a time, so the same cash-on-delivery checkout sent twice at once places one
  order (two before). `refund_payment` locks its refund alone and skips one another worker holds.
- **Bounds**: a search of five words of 50 characters; a product's newest 200 reviews; tests that every collection is
  paginated at 200 and that the storefront's hot paths run no query per row; `export_gstr1` streams.
- **Logs**: one JSON line per request (URL pattern, status, milliseconds, account id; never the address's secrets), a
  warning past `SLOW_REQUEST_SECONDS`, the task's id and name inside Celery tasks; RUNBOOK.md "Reading the logs".
- **The chart** must move its liveness probe to `/health/live/` (RESILIENCE.md "What the Kubernetes chart must
  change", with the new variables and the database's connections).

## The Admin Control Panel's backend, the rest of Phase A (9 October 2026)

The apps that came before the staff app now follow its rules, and the plan's last staff pieces are in
(`../docs/examleaf-admin-control-panel-plan.md` sections 3.5, 5.7, 5.16, 6, 7.1 and 9.1). 994 backend tests pass on
SQLite (8 skipped, 1,637 subtests; 933, 8 skipped and 1,181 before), 1,001 on PostgreSQL (1 skipped; 940 before).

- **Shipping and the insights on the staff app's permissions.** The placeholders that let any member of staff in, on
  every host, are gone: both apps' staff endpoints run on `staff.api.StaffAppView` (the panel's session or an API key,
  never the app's JWT), name a catalogued permission per action and reach their objects through `scoped()` (a
  PACKER's parcels are those of the orders to pack and on their way). New: `staff.view_parcels`, `book_parcel`,
  `act_on_exception`, `view_cod`, `reconcile_cod` (high: a re-authentication), `manage_pickup_locations`,
  `view_insights`, `acknowledge_signal`; PACKER books, SALES acts on failed deliveries and sees COD, FINANCE
  reconciles COD and reads the insights, MARKETING reads them, AUDITOR has the views. They answer on the admin host
  only, their refusals are `authz_fail`, and every change is an audit event targeting the order. New endpoints:
  `shipping/cod/<id>/reconcile/` (the bank's credit matched by its UTR; `payment.cod_reconciled`, the money chain) and
  `insights/fraud-signals/<id>/acknowledge/`. The role × endpoint matrix and the generated API.md reference cover both.
- **The inbox** files a parcel's exception (due when it is, FINANCE's for COD), an integration's dead letter, a failed
  provider event and an open circuit, and closes each once settled (new signals: `shipping.exceptions_closed`,
  `integrations.dead_letter_closed`).
- **The Django admin** answers on the admin host only (`ADMIN_HOSTS`) and signs in through the console there. Its
  refund action, and "Cancel" on an order paid online, are the panel's refund: the maker's limit, a change request for
  FINANCE above it. The pack, ship and deliver actions are tested against `staff.pack_order`.
- **Google Workspace sign-in for staff** (`STAFF_GOOGLE_DOMAIN`): the ID token's `hd` and a confirmed address checked
  by the server, no break-glass account through Google, a new account only with `STAFF_GOOGLE_AUTO_STAFF`, refusals
  audited; the admin host can have the Workspace's own client with an Internal consent screen
  (`STAFF_GOOGLE_CLIENT_ID`); the second factor still follows. The Google scope asks `openid`.
- **Break-glass sessions** give their reason before anything (`staff/session/reason/`, the manifest's `break_glass`),
  carry it in every audit event, end 2 hours after their log-in (`STAFF_BREAK_GLASS_HOURS`), and alert the owners at
  their start and end.
- **Logging in as a customer, on the website**: `account/impersonate/` takes the panel's token once, for a session
  marked as staff's that ends at its time, by either side or with the panel's session; money, passwords, second
  factors, addresses and deletion refused; every request audited as the member of staff's on behalf of the customer;
  the website's `auth/session` carries the banner and the customer's device list names it.
- **Notes** on any record its readers may see (`staff/notes/`), and **policy acknowledgements** per version
  (`staff/policies/ack/`, `STAFF_POLICIES`, the manifest's `policies_due`).
## The ERPNext sync: the erp app (9 October 2026)

ERPNext keeps the books and the warehouse behind the platform; a new app, `erp/` (`erp/README.md`), keeps the two in
step: the platform's documents mirrored in ERPNext, ERPNext's stock and B2B documents read back, a nightly
reconciliation of the two (the plan's sections 3.1, 3.2, 7.5 and 9.3; the ERPNext side is `../examleaf-erp`, whose
`API.md` is the contract). No business rule of the shop, the course or the shipping changed: the app listens to their
saves and to two new signals. Every flow is behind a switch, off by default. 933 backend tests pass on SQLite
(8 skipped, 1,181 subtests; 831, 8 skipped and 1,025 before), 940 on PostgreSQL (1 skipped; 838 before).

- **The outbox.** A document's row (`ErpOutbox`) is written in the transaction that makes the document, so neither
  goes without the other, its payload built then (one that cannot be built is built again at the send). Rows are
  numbered per order, product or settlement and sent in that order; a document is written once, an item again only
  when it changed. What hangs on an invoice (its payments, delivery notes, credit notes, refunds, COD settlement) is
  written after it, also when it came first, as a COD parcel that leaves before its bill.
- **The relay** (every minute, and nudged after each commit that wrote rows): the first open row of each order, under
  a lease; ERPNext's answer kept on the row and an `ErpLink` written; the ERPNext account's circuit breaker; a delay
  that doubles from a minute to six hours, jittered, or what `Retry-After` says on a 429. A refusal that cannot
  succeed unchanged, or the tenth failure, makes a dead letter (`IntegrationFailure`) that holds its order's later
  rows until staff replay or discard it. A row's idempotency key is its id (after `ERP_INSTANCE_PREFIX`), so an answer
  lost on the way is asked again safely.
- **The contract in one module**, `erp/contract.py`: each examleaf_erp method's fields as API.md has them (the
  shipping address as city, district, state and PIN only; the walk-in B2C customer; the payment modes; references as
  `kind:id`), its answers and refusals. `erp/fake.py` is an in-memory ERPNext that keeps the same rules (unknown
  fields refused, duplicates answered, Frappe's own 401 and 403, GST rounded as ERPNext rounds it) for the tests and
  `ERP_MODE=fake`.
- **From ERPNext**: its webhook `POST /api/hooks/erp-events/` (the HMAC-SHA256 of the body with the account's secret,
  or the previous one for 24 hours, in constant time; kept once per SHA-256; answered at once; the document read again
  over REST); a pull every 15 minutes of what changed (`ErpCursor`); stock snapshots per item (`ErpStockSnapshot`) and,
  with `ERP_STOCK_PROJECTION`, the copies for sale set from ERPNext's stock less what is sold here and not yet
  shipped; B2B quotations, customers and invoices kept read-only (`ErpMirror`).
- **The nightly reconciliation** at 03:30 IST (`erp_reconcile --date`): the day's invoices, credit notes, payments and
  refunds by mode, settlements and delivery notes against ERPNext's `daily_totals` (counts and totals exactly, taxes
  within 0.01 an invoice: ERPNext rounds once an invoice), every document ERPNext has not answered for, and the stock
  per item. Each difference is a row (`ErpReconciliationDifference`) and a signal; the morning's email goes to
  `ERP_ALERT_EMAILS`, and an inbox item waits until the last one is resolved.
- **Commands**: `erp_status`, `erp_replay <id> | --dead | --sent-since` (the last for an ERPNext restored from a
  backup), `erp_initial_load` (a dry run unless `--apply`; `--invoices-from`), `erp_reconcile`, `erp_pull`.
- **In the staff app**: `/api/v1/staff/erp/` (the status, the outbox, dead letters with replay and discard, the
  reconciliation runs, differences with resolve, the cursors: API.md "ERPNext sync (staff)") on the staff API's rules;
  four catalogued permissions in the area "ERP sync" (`erp.view_sync`, `erp.replay_sync`, `erp.resolve_difference`,
  `erp.run_initial_load`: FINANCE views and resolves, AUDITOR views, OWNER and ADMIN everything); two inbox kinds
  (`sync_failed`, `reconciliation`); the initial load as a staff job; each switch a feature flag; audit events for a
  replay, a discard, a resolve, a resend and the initial load. The admin's pages are under "ERPNext sync".
- **Seams elsewhere**, no rule changed: `shop.signals.order_shipped` and `shipping.signals.parcel_left`; invoices,
  credit notes and COD remittances saved in a transaction (their receivers' rows with them); in integrations,
  `Retry-After` read on a 429 or 503, `webhook_secrets()` for a provider that signs its webhooks, `InboundEventTask`
  and `dead_letter()` shared.
- **Personal data**: none of a B2C customer's goes to ERPNext, the outbox, the call log or the mirrors (a test checks
  every payload); the mirrors keep no contact's email address or phone number.

## Admin Control Panel, Phase A (9 October 2026, in progress)

The plan is `docs/examleaf-admin-control-panel-plan.md`; the research behind it is in
`docs/research/2026-10-09-admin-control-panel/`. Platform changes so far:

- `/health/` no longer flaps: the Celery ping waits for every worker (two seconds at most) and checks that the default
  and the media queue each have one (`examleaf.health.WorkerPing`, `CELERY_HEALTH_QUEUES`). Before, `limit=1` took the
  first worker's answer, and when that was the media worker the check reported the default queue as unserved. Found by
  the Kubernetes packaging's smoke test (`deploy/kubernetes/TESTING.md`).

## The Admin Control Panel's backend (9 October 2026)

The foundation of the staff console (`../docs/examleaf-admin-control-panel-plan.md` sections 3.5, 3.6, 4, 6, 7.1 and
9.1; the research in `../docs/research/2026-10-09-admin-control-panel/research-rbac-security.md`): a new app `staff/`
(`staff/README.md`) and its API under `/api/v1/staff/` (API.md "Staff API", with every endpoint and field generated
from the schema). No business rule of the shop, the content or the course changed: the panel's actions call
`shop.services` and the accounts' own functions. 831 backend tests
pass on SQLite (8 skipped, 1,025 subtests; 627 and 7 skipped before), 838 on PostgreSQL (1 skipped; 626 passed
and 7 failed there before, faults of the tests themselves, fixed here).

- **Roles.** OWNER (the founder's: every catalogued permission; the superuser flag is left to one or two sealed
  break-glass accounts, whose log-in alerts the owners and every audit event of whose sessions is marked
  `break_glass`), FINANCE, PACKER (the packing queue only), REVIEWER, MARKETING, AUDITOR and SALES_REP join the six.
  CONTENT_EDITOR, SALES and SUPPORT keep their permissions and gain the panel's, except that SALES no longer packs,
  ships or refunds in the admin: packing is `staff.pack_order` (PACKER's, and ADMIN's in the admin), and SALES asks for
  refunds in the panel. ADMIN keeps everything but the owners' own (`OWNER_ONLY`: giving roles, API keys, the override,
  the audit log) and money's approvals (`MONEY_APPROVALS`): FINANCE approves money, ADMIN roles and exports, REVIEWER
  content. `ROLE_LIMITS` (refund, offline payment, discount, export and bulk thresholds: placeholders for the owner),
  `ROLE_SCOPES` and `SOD_CONFLICTS` sit beside `ROLES`. The roles are synced after every `migrate` by a post_migrate
  receiver (no role migration), which warns about anyone holding two roles kept apart. The panel's roles do not open
  the Django admin (its lists are not scoped). 33 action permissions (`staff.refund_order` … `staff.view_inbox`) in a
  catalogue with a label, an area and a risk that decides re-authentication, approval and alerts.
- **Scopes.** `StaffScope` (subject, board and class, order status, warehouse, school, work queue), `scoped()` in every
  staff queryset and `staff.backends.ScopeBackend` for `has_perm(perm, obj)`; a PACKER sees the orders to pack and on
  their way only.
- **The audit log.** `AuditEvent`, written by `staff.audit.record` in the caller's transaction: who (id, type, roles),
  for whom, whether by a break-glass account, what, which permission, on what, the outcome and reason, the request ID,
  address, browser and session hash, `{field: [before, after]}` with personal data masked; two hash chains (money
  apart, kept 8 financial years; the rest 2 years) under one lock; a PostgreSQL trigger refuses UPDATE, DELETE and
  TRUNCATE; verified nightly (`verify_audit_chain`, an alert on a break), copied daily as JSON lines with the chains'
  heads to the backups' bucket, purged by `purge_audit` as the table's owner. Fed by staff log-ins (each emails the
  person), log-outs, failed log-ins and lock-outs, role changes from anywhere, admin exports, refunds and offline
  payments, impersonation, every refusal of the staff API and every reveal of personal data. Read by AUDITOR and OWNER
  only, each read logged.
- **Approvals.** `ChangeRequest` (django-fsm-2: pending, approved or rejected or expired, executed or failed) with the
  payload's SHA-256, which the approver sends back and the executor checks before it runs the stored payload once; the
  approver is never the maker nor the person the change is about, unless an owner overrides with a reason (alerted,
  marked break-glass). Refunds above the maker's cap (then `shop.services.refund_order`, which calls `start_refund`),
  offline payments above a value or of ₹0, prices and coupons beyond the discount limit, privileged roles and roles
  for oneself, invitations to them, second factor resets, erasures and jobs above the export or bulk limit wait for a
  second person; within the limits they run at once. Idempotency keys on every request.
- **Jobs.** `Job`: an audit-log export or a bulk action (an action of `change-requests/` on many targets, each run as
  its own request) in the background, with its progress, each row's error, a dry run, its approval above the limit,
  cancelling by its starter, and its file behind a link signed for 5 minutes (kept a week). `audit/export/` answers 202
  with a job above 5,000 rows, and refuses unknown filters.
- **Work and settings.** `InboxItem` from approvals, teachers' requests, deletions, data requests, incidents, failed
  clips, tasks, refunds and webhooks; `SavedView`; `SiteSetting` (`SHOP_OPEN`, `SHOP_COD_ENABLED`,
  `PARENTAL_CONSENT_MODE`, `WEB_COURSE`, maintenance mode and its banner: the environment's value unless the panel set
  one, from now or a time to come, with their history; `config/` and the server's own checks read them; `config/` gains
  `maintenance`); `FeatureFlag`; `ApiKey` (hashed, shown once, view permissions only, expiry, address allowlist, its own
  authentication); `StaffInvite` (7 days); `RoleGrant` (who, why, until when; expired roles and scopes go nightly); the
  access review with the action permissions unused for 90 days.
- **Data protection.** `DataRequest` with its clocks (48 hours to acknowledge; a month, then 90 days for the DPDP rights
  from 13 May 2027), the answer's contact block, the erasure's dry run (holds, blocks, a child's parent) and its
  approval, an access request's data emailed to the account's own address; `Incident`, the breach register with its 6-
  and 72-hour clocks; `ProcessorRecord`; masked customers with logged openings and rate-limited, re-authenticated
  reveals; impersonation tokens of 15 minutes (never staff or a child) and a guard for when the website accepts them.
- **Sessions and the API's edges.** Staff sessions end after 15 minutes without a request for OWNER, ADMIN, FINANCE and
  PACKER, 30 for the others (`STAFF_IDLE_TIMEOUT`, `STAFF_IDLE_TIMEOUTS`), and 8 hours after the log-in. The staff API
  answers 404 on any host but `ADMIN_HOSTS`; its manifest carries the person's idle limit, `impersonating` and
  `flags.test_mode`; every error answer has a `code` beside its `detail`, a step-up its allauth `flows`.
- **New settings** (DEPLOYMENT.md sections 13 "Staff" and 23): `ADMIN_HOSTS`, `STAFF_IDLE_TIMEOUT`, `STAFF_TEST_MODE`,
  `STAFF_PANEL_URL`, `STAFF_ALERT_EMAILS`, `STAFF_CHANGE_REQUEST_HOURS`, `STAFF_DORMANT_DAYS`,
  `STAFF_AUDIT_RETENTION_DAYS`, `STAFF_AUDIT_MONEY_RETENTION_FY`, `STAFF_DATA_REQUEST_ACK_HOURS`,
  `STAFF_DPDP_RULES_FROM`, `STAFF_DPDP_RESPONSE_DAYS`, `DATA_PROTECTION_OFFICER`, `CERT_IN_POINT_OF_CONTACT` and the
  `STAFF_THROTTLE*` rates. Migrations: `staff` 0001 and 0002. RUNBOOK.md has a "Break-glass accounts" section.
- **Outside the app.** The shop admin's pack, ship and deliver actions need `staff.pack_order`; the root conftest runs
  the transactional tests that restore the database's snapshot before the other transactional ones, and an insights
  test no longer counts on a run's id (both failed on PostgreSQL).

## Insights: the Admin Control Panel's predictive jobs (9 October 2026)

A new app, `insights/` (its README: every job's inputs, method, output and how to read it), built from
`docs/research/2026-10-09-admin-control-panel/research-b2b-predictive.md` section 4. No new dependency: the methods
are a few lines of standard Python each, checked against numbers worked out by hand. 476 backend tests pass (7
skipped), 54 of them new; before: 422.

- **Demand and print runs.** `forecast_demand`: weekly copies per printed title and district to the exam, seasonal
  naive by week of the season × a damped growth factor, P10 to P90 from last season's errors, a new edition taking its
  line's curve, "email me when it is back" requests counted as demand. `backtest`: rolling origin across last season,
  WAPE and seasonal MASE against the seasonal naive, and `shown` only when it beats it (a losing growth factor is
  dropped). `advise_print_run`: the newsvendor's quantile at Cu ÷ (Cu + Co), the reprint trigger, weeks of cover and
  leftovers, with "act" and "watch" alerts. Staff enter exam seasons and print costs in the admin.
- **Learners, aggregate only.** The quiz's item analysis (p, corrected point-biserial, TIMSS's flags, once 30 learners
  answered), chapter accuracy and its trend, cohort retention and churn; groups under 5 show their size only, and no
  insights model has a key to an account or a learner (a test asserts it), for the DPDP Act's rule on children.
- **Codes, parcels, offers, fraud.** Book codes per batch and district; transit days per courier and district with
  `is_late`; what each coupon and offer did beside the same weeks last season, with an interval and "not conclusive"
  below 30 orders, never a winner; fraud rules (failed book codes per account, address and hour, spikes, resale,
  shared codes, shared phones and addresses on COD or coupon orders) as signals to acknowledge, and a nightly email to
  `INSIGHTS_ALERT_EMAILS`. Rules waiting for data: COD return risk (`rto_risk`, for the shipping app's parcel
  outcomes) and the school and distributor score (for ERPNext's accounts).
- **Running it.** One Celery task per job between 01:00 and 03:00, retried once and then raised; `insights_run` and
  `insights_review` (the monthly review); read-only admin pages with a summary per run; `/api/v1/insights/` for staff,
  every answer with its method, data time, last backtest and `shown` (API.md, "Insights (staff)"); the permission is
  a placeholder for the staff app's.
- **Outside the app** (two hooks): `learn.QuizAttempt.chosen` keeps the multiple-choice option a student chose (the quiz
  endpoint records it; Download my data lists it), and the redeem endpoint records each book code tried as hashes.
  New settings: `INSIGHTS_ALERT_EMAILS`, `INSIGHTS_HASH_SALT` (DEPLOYMENT.md sections 13 and 21; RUNBOOK.md "Insights").

## Couriers: the integrations framework and the shipping app (9 October 2026)

The courier integration of the Admin Control Panel research (`docs/research/2026-10-09-admin-control-panel/`
`research-integrations.md`, section 3), as two apps; no change to payments, Razorpay, the checkout, sign-in or the
Order state machine's rules. 573 backend tests pass (7 skipped; 422 before): 41 for `integrations`, 110 for
`shipping`, against a recorded double of Shiprocket; two migrations, both new apps' own (none in shop).

- **`integrations/`** (`integrations/README.md`), the base for every connection to a service others run for us:
  `IntegrationAccount` (one provider in one mode, at most one enabled; credentials, the cached token and the webhook
  tokens encrypted with MultiFernet over the new `INTEGRATION_KEYS`, shown by their last four characters only;
  `rotate_integration_keys` re-encrypts every row; the previous webhook token accepted 24 hours; a circuit breaker:
  open after 5 failures in 5 minutes, one trial after 5 minutes, held open or reset by staff), `IntegrationCall` (every
  request, with a redacted excerpt: no secrets, phones to their last 4 digits, emails masked, names dropped, addresses
  to their PIN; 90 days), `IntegrationFailure` (the dead-letter list: replay once, discard with a reason),
  `InboundEvent` (webhooks raw, once per SHA-256). A base HTTP client (5 s to connect, 20 s to read; typed failures:
  unavailable, rejected, authentication), `IntegrationTask` (the refund task's backoff; requeued while the circuit is
  open; a dead letter when it gives up), connection tests per provider, signals for the staff inbox, the admin with
  its actions, `/health/integrations/` for a second monitor, `integrations.E001` (a server with accounts and no keys
  does not start), `integrations_retention`.
- **`shipping/`** (`shipping/README.md`): a carrier interface with a manual carrier (today's counter flow) and
  Shiprocket (API v1: the API user's token, renewed from day 9 and after a 401; refusals inside a 200), and a recorded
  double of Shiprocket for test mode and the tests. `ShipmentDetail` (a shipment's courier side, one to one: shop's
  model and migrations unchanged), `ShipmentEvent` (the timeline, a scan kept once by its digest), `PickupLocation`,
  `ShipmentCharge`, `CodRemittance`, `ShippingException` (`exception_opened`), `PinServiceability`, `PostalTariff`
  (empty; `loaddata postal_tariffs`, the published tariff marked "verify at the counter"). The quote (3 s, kept 10
  minutes, the last answer while Shiprocket is down; ranked by the research's rule; India Post beside it for prepaid
  orders), booking (idempotent; refused when the cash to collect is not the order's total; `-R1` for a re-shipment),
  label kept by us, pickup, manifest, cancellation before pickup, NDR actions; our status machine (the research's
  code table, forward only, the return branch its own); the first scan that says the parcel left ships the order and a
  confirmed delivery delivers it (their existing transitions), COD remittances expected and checked, statement lines,
  weight disputes, no-movement and NDR exceptions. The webhook `POST /api/hooks/parcel-events/` (the token compared in
  constant time, the raw body kept, 200 at once, a claim of delivery read again first; throttled). Tasks and beat:
  tracking every 2 hours, the statement, COD, disputes, the token, the PIN survey, the SMS held through the night.
  Commands: `shipping_smoke_test` (live only, with `--yes`), `shipping_poll_tracking`, `shipping_sync_statement`,
  `shipping_check_cod`, `shipping_check_discrepancies`, `shipping_survey_pins`.
- **The staff API** `/api/v1/shipping/` (API.md "Shipping (staff)"): quote, book (with a courier, or by hand), parcels
  with their timeline, label, pickup, manifest, cancel, NDR action, photograph, exceptions, COD, charges, pickup
  locations, behind a placeholder permission (`shipping.permissions.StaffOnly`) for the staff app to replace.
- **The shop**: `notify` and `deliver_order` can leave the SMS to the shipping app (quiet hours: none from 21:00 to
  08:00), `ship_order`'s follow-up is `shipped()`; two emails (`delivery_failed`, `returning`) and two SMS kinds
  (`order_arriving`, COD out for delivery; `order_not_delivered`; DLT texts in RUNBOOK.md). A courier's parcel is read
  only on the order's admin page and appears on the customer's order page once it has left. The frontend's proxy
  passes `/api/hooks/` to Django as Caddy does.
- **New settings**: `INTEGRATION_KEYS`, `INTEGRATIONS_CONNECT_TIMEOUT`, `INTEGRATIONS_READ_TIMEOUT`,
  `INTEGRATIONS_RETENTION_DAYS`, `SHIPPING_PACKING_GRAMS`, `SHIPPING_PARCEL_CM`, `SHIPPING_QUOTE_TIMEOUT`,
  `SHIPPING_MIN_RATING`, `SHIPPING_MAX_DAYS`, `SHIPPING_GYAN_POST`, `SHIPPING_SURVEY_BATCH`,
  `API_THROTTLE_PARCEL_EVENTS`, `MSG91_TEMPLATE_ORDER_ARRIVING`, `MSG91_TEMPLATE_ORDER_NOT_DELIVERED`
  (DEPLOYMENT.md sections 13 and 22; RUNBOOK.md "Couriers and integrations", "Secrets and key rotation").

## The Answer Script redesign (9 October 2026)

The frontend restyled to "Direction A, Answer Script" (`implementation/design/*.dc.html`; the report with the
before and after screenshots, the test numbers and what is verified, unverified or blocked is
`docs/design/answer-script-implementation.md`). Presentation only: no API contract, business rule, permission or
entitlement changed. Backend: `GET config/` gains `web_course` (new setting `WEB_COURSE`, off by default), which
switches on the revision course's pages on the website (`/revision/<subject>/<chapter>/`, its flash cards and quiz,
`/account/learning/revise-again/`, all 404 while off); the HTML frame of every email, the order emails and the
invoice, bill of supply, credit note and quotation PDFs carry the paper look, with every word, link and figure as
before (one test assertion follows the code's new colour). 422 backend tests pass (7 skipped); Vitest 89 → 180.

## Phase 8F review fixes (8 October 2026)

The fixes of the Next.js frontend review (`docs/design/audit-nextjs-security.md`, `-accessibility.md`,
`-lighthouse.md`, `-parity.md`), in the review's order. 422 backend tests pass (7 skipped), Vitest 86/86, Playwright
26/26 the CI way (a fresh SQLite database, production build); no migration. New setting: `INTERNAL_API_TOKEN`.

- **Open redirect (S1).** `safeNext()` takes only a relative path that starts with one `/` and has no `//`, `\`, `.` or
  `..` segment (plain or `%2e`), `@`, whitespace or control character, and that stays on the origin through the URL
  parser; `/..//host` and the other vectors now land on `/`. The backend has no `next` of its own: allauth's
  `is_safe_url` (admin log-in, a provider's `callback_url`) refuses another host, `//`, `\` and other schemes (pytest).
- **Razorpay (S2, S3).** Its hosts are in the CSP of the two pay pages only, and those pages are always their own
  document: the checkout form goes there with `location.assign`, an order's Pay now is a plain `<a>`, and `PayButton`
  reloads once a pay page whose document began elsewhere (the navigation entry names the document's URL).
  `checkout.js` is inserted with the page's nonce when Pay is pressed, not before. The privacy draft says what
  Razorpay's window keeps in the browser.
- **One throttle bucket (S4).** Every server-side call of the frontend sends the visitor's `X-Forwarded-For` and
  `User-Agent` and `X-Internal-Token`; `examleaf.middleware.FrontendClientMiddleware` makes that address the request's
  `REMOTE_ADDR` only when the token matches, so throttles, axes, allauth's limits and the device list count each
  visitor and never the frontend as one client. Public answers are kept 60 s by URL alone (`unstable_cache`, only a
  200), so visitors still share them. compose passes the token to the frontend (required); DEPLOYMENT.md, API.md.
  Fewer calls: `PaperBrief` carries `full_marks` and `time_text`, so the home page asks 3 endpoints instead of 7
  (the book and product pages one fewer).
- **An outage is not a log-out (S5).** The session check tells signed out (401, 403, 410) from unknown; `requireUser()`
  throws the "cannot be reached" error instead of redirecting to log in; a whole page that cannot be shown is a thrown
  error with its own words in `error.tsx` (a 500, never a 200 page); the visitor's own pages answer **503** with
  `Retry-After: 30` and a self-contained page while Django's `/health/web/` fails (asked at most every 5 s). Public
  pages still render from Next's data cache.
- **Accessibility.** No sideways scroll on `/shop/` (the tabs' fieldset, F2) or the home page at 320 px (F5); the Menu
  button comes before the menu in the page, and leaving the menu closes it (F3); busy buttons are `aria-disabled`, not
  disabled, so focus stays on the cart's stepper, Save and the rest (F1); dialogs are the browser's own `<dialog>`,
  open on the safe button, give focus back and fit a 400 % zoom (F6); the toaster is ours: 6 s, paused on hover and
  focus, a 44 px Dismiss, outlives the navigation it was raised for (F4, F13); focus goes to the new form or button
  when the account forms swap and to the list after a removal; paper cards are named by what they show (F7); table
  boxes are focusable regions (F10); the cart's summary wraps at 320 px (F11). axe again on the review's pages: the
  only violations left are the solutions pages' scroll boxes (F10's false positive, kept: without them axe misreads
  KaTeX as dark on navy).
- **Performance.** sonner and Radix Dialog removed; the sign-in client, the clip player and Turnstile load when used:
  6 to 21 KB less JavaScript per route (home 167.9 → 155.4 KB, `/account/` 199.5 → 186.1 KB); 120 KB is below the
  framework's own 131 KB. `/account/` no longer shifts (CLS 0.343 in 1 of 8 runs → 0 in 8 of 8). KaTeX renders HTML
  only (it reads better than the browsers' MathML in Chrome and Safari), each formula with spoken words for screen
  readers: the open sample's HTML 92.2 → 81.1 KiB. The home and tile covers come at 240 px (`build_covers`): home
  414 → 349 KiB. Lighthouse before and after: `docs/design/audit-nextjs-lighthouse.md`, "After the fix pass".
- **Parity.** `/account/2fa/webauthn/reauthenticate/` is a 404, anonymous pay and done pages a real 307,
  `/sitemap-django.xml` gone from the parity document and script.
- **Still open.** LCP stays 2.7 to 3.1 s on the budget pages (the framework's bytes); the solutions page's RSC payload
  repeats its markup (81 KiB against 60); from the review, S6 (Back after Log out), S7 (Caddy's 400 for broken
  escapes), S8 to S10, F8, F9, F12, F14 and L6 to L10.

## Phase 9: repository split (8 October 2026)

The platform has its own repository, `LazyIndianBook/platform`; the books (questions, solutions, the Typst build) stay
in the private `LazyIndianBook/Class-12-Assam`. Nothing here needs a checkout of the books any more, except importing
the real papers. 412 tests pass (7 skipped); the 24 Playwright journeys pass on the test papers; no migration.

- **Parser vendored.** `content/papers_parser.py` is a copy of `parse_paper`, `parse_solutions` and `split_marks` (and
  the subjects' codes and edition years) from the books repository's `production/build/book.py` at 0e64cdf, which
  stays the source of truth; `import_papers` no longer loads `book.py` by path. On the books' 120 papers the copy
  parses exactly as the original, and importing them again changes no record.
- **`PAPERS_ROOT`** (was `BOOK_ROOT`): a checkout of the books repository; by default `Class 12` beside this
  repository when it is there, otherwise `import_papers` and `import_chapter_insights` stop with a message naming
  `--root`, `PAPERS_ROOT` and `--fixtures`, which both commands now take. Compose sets `PAPERS_ROOT=/book` and mounts
  `BOOK_SOURCE` there (default `../../Class 12`); DEPLOYMENT.md section 4: the books on the server through a second
  read-only deploy key or a tarball, and re-importing is safe.
- **Test papers.** `content/fixtures/papers/` holds byte-for-byte copies in the books' layout (its README: from which
  commit, and how to refresh them): E01, M01 and H01 of each subject and PHY-E02, 13 papers and 637 questions with
  their solutions, the work orders (chapter tags), the four `format.json` and `pyq/ch01.md` of each subject.
  `content/tests.py` imports them (papers per subject and tier, every solution matched, the tags; a second
  `import_papers --all --fixtures` creates and updates nothing; no papers root is said in words), and
  `learn/test_imports.py` takes them through `import_papers`, `import_chapter_insights` and `build_quiz_items`
  (51 chapters, 69 quiz items).
- **CI.** `examleaf-frontend/scripts/e2e-backend.sh` seeds the Playwright backend with `import_papers --all --fixtures`;
  the workflow runs on pushes to main and on pull requests that touch `examleaf-web/`, `examleaf-frontend/` or the
  workflow (no more `production/**`).

## Phase 8E learning dashboard (8 October 2026)

A Learning page in the account (examleaf-frontend `/account/learning/`) and the endpoint behind it. 471 tests pass
(7 skipped); no migration.

- **`GET me/learning/`** (`learn/dashboard.py`, `api.learn.LearningView`, typed `Learning` in the schema): what is open
  today; per subject and chapter the clips watched of the processed ones, minutes watched, quiz answers and the share
  right, the latest activity; the next unwatched clip of the revision watched last, with its revision and chapter
  (`free`, `locked`); the revise-again counts due today and later; the plan's first three days for the saved exam
  date (empty, with a `hint`, without one); the streak of days with a clip, a quiz answer or a card review (a clip
  counts on the day it was last watched: `Progress` keeps one row per clip); `consent_pending`, `has_app_links`. Only
  the user's rows, `private, no-store`, readable while a parent's confirmation is awaited (API.md "Learning").
- `learn.plan.default_subjects` (the subjects open to the user, or all) is shared by `learn/plan/` and the dashboard;
  the plan reads each clip's revision in the same query (it made one query per clip).
- Tests: `learn/test_dashboard.py` (a student with an open subject, watching and answers; one with nothing; a free
  clip watched and a locked next clip; a student waiting for a parent's consent).

## Phase 8: Django pages removed (8 October 2026)

The Next.js frontend (`../examleaf-frontend/`) serves the website at the same addresses
(`../docs/design/parity-nextjs.md`), so Django's own pages are gone, as the plan's last step and the founder decided.
406 tests pass (7 skipped), from 467: the page tests went, the rules they checked are tested through the API and
allauth.headless instead.

- **Removed:** 41 page views and 57 URL patterns (home, books, `/s/<code>/`, the shop, cart, checkout and payment, the
  orders and the lookup, quotations, reviews and stock-alert forms, the account pages, My record and its forms, teacher
  access, the parent's consent page, the legal pages and About, `/revision/`, `robots.txt`, the sitemap, the web app's
  manifest, service worker and offline page, the favicon redirect), 12 page-only forms, `shop/seo.py`, the
  `web` template tags and the site context processor, 84 templates (the pages, partials and allauth's, MFA's and
  socialaccount's overrides) and 86 static files (the site's CSS and scripts, KaTeX, the icons, the 240 px cover
  sizes, the pay page's script); `django-widget-tweaks`, `django.contrib.sitemaps` and `django.contrib.humanize`.
- **allauth headless only** (`HEADLESS_ONLY = True`): no allauth page; Google's callback stays at
  `/account/google/login/callback/`. The website's log-in keeps the site's rules there: `auth/login` takes a mobile
  number as typed, and `auth/code/confirm`, `auth/email/verify` and `auth/phone/verify` count three tries per code in
  the cache (I7), as the old pages did. `LOGIN_URL` is the website's log-in (the admin sends there with `?next=`); a
  member of staff without an authenticator app is sent to the website's `/account/2fa/`; the API's reset link is built
  from `HEADLESS_FRONTEND_URLS`.
- **Stays:** the API and its docs, allauth.headless, the admin with its dashboard, the staff clip player (now on the
  admin's layout), the webhooks, `/shop/media/`, `/qr/<code>.png`, health, the emails, the invoice, credit-note and
  quotation PDFs (with their fonts), the book covers and `og-default.jpg` the website shows (`build_covers` makes the
  320 and 480 px sizes), every management command. Staff download invoices and credit notes from the admin
  (`<id>/pdf/`), no longer through the customer's order page.
- **Error pages** (400, 403, CSRF, 404, 429, 500) are plain HTML for Django's own paths; JSON under `/api/` as before.
  The CSP lost what only the pages needed (manifest, worker, Turnstile, Google's form address).
- **Caddy:** `PAGES_UPSTREAM` defaults to `frontend:3000`; Django's prefixes are unchanged.
- **Models:** `get_absolute_url` of books, papers, products, shelves, collections, orders and legal pages, and the
  order link, are the website's paths written out (no Django route any more); the QR codes still encode
  `SITE_URL/s/<CODE>/`.

## Phase 8 backend, account part (8 October 2026)

What the account and revision pages (8C) asked of the API, docs/examleaf-phase8-nextjs-plan.md "Backend gaps found
by 8C". 467 tests pass (7 skipped); allauth's migration `usersessions.0001_initial`, none of ours.

- **Every chapter:** `learn/chapters/` lists the whole syllabus, not only chapters with a published revision:
  `has_revision`, `revision_status` (`published` or `none`; a revision in draft shows as none, without its clips,
  minutes or free cards) and `free_preview` (the id of the chapter's free clip, so a preview plays without fetching the
  chapter), with `weight`, `frequency` and the filters as before; `learn/chapters/<id>/` still answers published
  chapters only.
- **My record in figures:** `GET me/record/` (`?subject=&tier=` as `attempts/`): the average per tier as My record
  rounds it, per subject, and per paper the best and the latest attempt, with counts.
- **What Download my data holds:** `GET me/export/summary/`: each part's key, the website's words and its count,
  without the file or the password.
- **App store links:** `config/` `app_links` (`android`, `ios`) from the new settings `APP_LINK_ANDROID` and
  `APP_LINK_IOS` (empty: null).
- **Signed-in devices:** `allauth.usersessions` with its middleware and `USERSESSIONS_TRACK_ACTIVITY`;
  allauth.headless's `GET`/`DELETE /_allauth/<client>/v1/auth/sessions` list them (address, browser, first and last
  request, the current one marked) and sign out the others, so the API has no endpoint of its own for it. The rows are
  in Download my data (`sessions`, without the keys), deleted with the account, and dropped the night after their
  session ends (`ops.tasks.clear_sessions`); the admin shows them read-only (allauth's own admin searched
  `user__username`, which this User has not).
- **Export and deletion without a password:** `me/export/` and `me/deletion/` take the password or, without one, a
  browser session that logged in or re-authenticated through allauth (`auth/reauthenticate`, `auth/2fa/reauthenticate`,
  or Google again) in the last 5 minutes; otherwise `403 {"detail": ..., "code": "reauthentication_required"}`. A
  password sent is still checked and counted (L6). Not allauth's `did_recently_authenticate`, which lets an account
  with neither a password nor a second step through at any time.
- **Typed answers:** `learn/plan/` (`Plan`, the same JSON as before) and `me/record/` (`Record`) in the OpenAPI schema,
  for the generated TypeScript; `spectacular --validate --fail-on-warn` clean.
- Tests: `api/test_account.py` and the chapters test; two page query-count tests (`content`, `practice`) make one
  request first, as the first request after `force_login` records the device.

## Phase 8 backend, second part (8 October 2026)

The four API gaps the shop frontend (8B) found, docs/examleaf-phase8-nextjs-plan.md "Backend gaps found by 8B". 461
tests pass (7 skipped); no migration.

- **Picture sizes in the API:** `cover` and each of `images` on `products/` and `products/<slug>/` are now
  `{sources, src, width, height, alt}`: the AVIF and WebP sizes django-pictures makes (`sources["image/avif"]["400"]`,
  absolute URLs; a cover's 2/3 cut), the uploaded original as `src` with its size, and `alt` ("Cover of <title>" for a
  cover). This replaces `cover` as a URL and `images[]` as `{url, alt}`. Built from the field's `aspect_ratios`
  (`api.shop.picture`), not `pictures.contrib.rest_framework.PictureField`, which nests the sizes by ratio with
  relative URLs and lets `?cover_ratio=`/`?cover_container=` raise a server error on a wrong value.
- **Renamed products:** `GET products/<old slug>/` answers 301 to `products/<new slug>/` with
  `{"redirect_to": "<new slug>"}` for clients that do not follow redirects, as the website's page redirects by
  `SlugHistory`; 404 once the product is off sale.
- **Orders say what they ship:** `is_digital` (courses only, a bundle of courses included) and `has_shipping` (its
  opposite) on `orders/`, `orders/<number>/`, `orders/t/<token>/` and the checkout's answer, read from the order's
  lines (the list now fetches their products with them).
- **Product SEO fields:** `meta_title` and `meta_description` (the admin's "page title" and "meta description", `""`
  when not written) and `og_image` (the link preview's absolute URL, null until the worker has made it) on products;
  the OpenAPI schema has a product's response example.

## Phase 8 backend (8 October 2026)

What the Next.js frontend (docs/examleaf-phase8-nextjs-plan.md) needed from the API, with the website's rules. 459
tests pass (7 skipped).

- **Guest cart and checkout through the API:** `cart/`, `cart/items/…` and `cart/coupon/` serve visitors too: a browser
  on the site's origin by the session cookie (the CSRF token on every change; DRF checks it only for signed-in
  sessions, so `api.shop.GuestOrCustomer` does), a client without cookies by `X-Cart-Token`, issued once by
  `POST cart/` (`Cart.token`: its SHA-256, 30 days; migration `shop.0020_cart_token`; `CORS_ALLOW_HEADERS` lists it).
  Signed-in callers are unchanged (a confirmed email address). A visitor's coupons ask for Turnstile and count 10 an
  hour per client address with the website's cart page. `POST orders/` takes a visitor's `email`, `shipping_address`
  (the rules of `addresses/`, the PIN code's state included), `payment_method` and `turnstile`: cash on delivery
  refused (M8), a course needs an account, 10 checkouts per 10 minutes per address (shared); the answer is the order
  as its link shows it with the link's `token`, once. `POST orders/t/<token>/payment/` and `…/payment/confirm/` pay a
  guest's order (an account's: 404) and empty the visitor's cart; `can_pay` of `orders/t/<token>/` is true for a
  guest's pending order. The guest cart joins the account's at log-in: the session's by the existing signal
  (`shop.cart.merge_carts`, now shared), a token's on the first signed-in cart call carrying it. While the shop is
  closed visitors get 403 "The shop opens soon." like everyone.
- **The order's link without Django's pages:** `POST orders/t/<token>/cancel/`, `GET orders/t/<token>/invoice/` and
  `…/credit-notes/<id>/`; the link's `invoice.url` and `credit_notes[].url` point there (the frontend serves
  `/orders/t/…` once Caddy switches).
- **Contact form:** `POST contact/` (name 80, message 2,000 characters, Turnstile, honeypot, 5 an hour per address with
  the website's form), emailed by `pages.views.send_contact` (now shared) with Reply-To the sender, nothing stored; 503
  while the support address is a `[placeholder]`. New setting `SUPPORT_EMAIL` (empty: `SELLER_EMAIL`), which
  `config/`'s `support.email` now follows.
- **Shipping:** `GET shipping/` (the rates and the lowest fee and free-delivery value), `GET shipping/quote/` (the fee
  to a PIN code or state for the caller's cart or an amount, with the PIN code's states and districts: the frontend's
  PIN autofill), and `shipping` in `config/` for "delivery from ₹40". `ShippingRate.rate_for` and `.summary`.
- **Frontend development:** README.md "The Next.js frontend in development" (Django on 8100 with
  `SITE_URL=http://localhost:3000`, `CSRF_TRUSTED_ORIGINS`, `USE_X_FORWARDED_HOST=1`; no CORS: one origin) and
  DEPLOYMENT.md section 20; `HEADLESS_FRONTEND_URLS`' fallback for a failed Google log-in is `/account/login/` (it shows
  `?error=`), the other entries and every email link are paths the frontend serves.
- Tests: `shop/test_api_guest.py` (browse, cart, coupon, order, mocked payment, confirm, the status page, cancel and
  PDFs by the link; the token client and its merge; CSRF and the merge at a headless log-in; the website's checks),
  and in `api/test_contract.py` (contact) and `shop/test_api_contract.py` (shipping).

## Phase 7 journeys (8 October 2026)

The user-journey gaps of docs/design/coverage-matrix.md closed where they were contained; what needs a founder's
decision or a missing feature is under its new "Open journeys" heading. 453 tests pass (7 skipped).

- **A sample with no wall (G1):** `Paper.is_sample`, one per book (a constraint; the data migration ticks each book's
  E-01; the admin's change form edits it): its solutions open without an account even with `SOLUTIONS_REQUIRE_LOGIN`
  on, on the website and in the API (`is_sample` in the paper serializers), cached publicly for 5 minutes. The home
  page's "See a sample paper", the book page, the product page and the wall of every other paper link to it.
- **Log in where you were (G15):** the header's Log in and Register carry `?next=` for the page (on the log-in pages,
  the `next` they were given), paths of this site only (`url_has_allowed_host_and_scheme` with no host allowed).
- **Guest orders join the account (G16):** an address confirmed (allauth's `email_confirmed`) or a log-in with confirmed
  addresses attaches the orders placed without an account under that address, any case, through `save` (history kept);
  My orders lists them.
- **From the order to the papers (G20):** the order's page and the delivered email link each book to its page ("Scan
  the QR code on each paper for its solutions") and a course to `/revision/`.
- **`/revision/` (G6):** the revision course on the website: what it is, each subject's chapters with the Board's marks
  and past questions, the free clips, the app (store links still `[placeholders]`), the student's entitlements and a
  book code form with the app's rules and limits (the same throttle counts as `api/v1/learn/redeem/`). My account,
  the footer and the sitemap link it.
- **Dead ends:** password reset sent, link expired, password changed (with Log in), account switched off, Google log-in
  cancelled or failed, the password asked again, the email and passkey pages: the site's words and a next step (G2, G4,
  G23). An expired parent's link names the student (as its SMS does) and offers Contact (G5). `/contact/` has a form that
  emails `SUPPORT_EMAIL` (else `SELLER_EMAIL`; no form while it is a `[placeholder]`), with Turnstile, a honeypot and 5
  an hour per address, storing nothing (G7). The 404 helps with an old order link (G19); a book without papers says so
  (G8); a missing invoice file is a 404 (G25).
- **Forms:** every form shows its button busy and is sent once (`site.js`, G9); a PIN code the directory lacks is said
  in its help (G12); the marks form saves back to the paper's `#record` and shows its errors there (G11), and a student
  whose parent has not confirmed sees why instead of a form (G17); My record names an empty filter with Show all (G10);
  the shop and its shelves get kind links for `?kind=` (G13); Download my data first lists what the file holds (G21).
  The address, sign-up, marks, checkout, lookup and contact forms say what each box needs, and every error summary
  names its field and links to it (a radio group at its first button).
- **Courses alone** are never called books, copies, shipping or delivery in the cart, checkout, order page and summary,
  or on the product page (`totals.digital_only`, the new `totals.has_digital`, `order.is_digital`,
  `product.digital_only`).
- **Platform:** KaTeX 0.19.0 served from `static/katex/` with its fonts and licence (checked byte for byte against the
  npm release; MAT-M02 draws its 397 formulas with no error), and jsDelivr gone from the CSP; 240 px covers for the
  home page's phone stage (`build_covers` run again); the four Latin fonts preloaded; messages inline on phones under
  600 px; product pictures cached for a year (`immutable`) and the product admin says while their sizes are made; a
  failed clip on the admin dashboard; signed-out PUT, PATCH and DELETE on `/_allauth/*/v1/account/phone` get allauth's
  401 instead of a server error; the privacy draft names the mobile number, the SMS log (90 days), reviews, stock
  alerts, quotations, the course's data, reminder devices and the parent's link; the design tokens copied to
  `docs/design/tokens.css`. The fonts were not re-subset: their originals have no tabular figures (Open journeys, T1).

## Phase 7 security (8 October 2026)

SECURITY_REVIEW_PHASE5_6.md: the High and the five Medium findings fixed, the Low and informational ones fixed or
decided; each has its status under it. 53 tests more (`learn/test_uploads.py`, `accounts/test_codes.py`,
`ops/test_sms_limits.py`, `accounts/test_parent_link.py`, `shop/test_offer_limits.py` and `test_review_lows.py` in
accounts, shop and learn; `learn/test_media.py` grew).

- **Slow requests (H1):** gunicorn runs threads (`--worker-class gthread --threads 8 --timeout 60`; it was a 10-minute
  timeout on sync workers). Caddy reads a body (up to 10 MB) before gunicorn sees it, and gives a client 10 seconds for
  its headers and 5 minutes for its body. Clip videos go from the editor's browser straight to the private bucket on a
  PUT link signed for 15 minutes with their size and type (`learn/uploads.py`, `static/learn/upload.js`), and the form
  carries only their signed name; without a bucket (development) they still come with the form, Caddy's 500 MB on the
  clip pages stays for that, and only signed-in staff may send such a body there (`LargeBodyGuard`).
- **Codes (M1, I7):** three tries per code, now also counted in the cache under a lock (parallel requests read the same
  count in the session); 5 email confirmation codes an hour and 10 a day per address, as actions of their own: allauth
  keeps one history per action and kind of key, so the review's `1/10s/key,10/d/key` would have capped nothing. Log-in
  codes: 3 an hour per address or number and 30 per client address; no "send a new code" on the log-in code page
  (allauth answered it with a server error for an unknown number). The API answers a refused code with a JSON 429.
- **SMS (M2):** limits in the SMS log before the daily cap: 5 an hour and 10 a day per number, 20 a day per account, and
  each purpose its share of the day (codes 70 %, order updates 30 %, parents' links 10 %). A refused SMS is never
  reported as sent: 429 "Too many messages have gone to this number…" (website and API), and the parent's link says it
  was not sent. The SMS log keeps the account (for the limits, Download my data and the deletion).
- **Parents' links (M3):** sent once the student has confirmed their own address (or at once after Google), never from
  an anonymous sign-up; fixed text, with the student's name only when it is plain letters (otherwise "a student"); at
  most 3 links a day to one address or number.
- **Offers (M4):** their usage limits are checked again under a lock when an order is paid or placed, as coupons are
  (`OfferUsedUp`: cancelled and refunded at capture, refused for cash on delivery and offline payments).
- **ffmpeg (M5):** a clip must be mp4/mov/m4v/webm/mkv with H.264, HEVC, VP9 or AV1 and AAC, Opus or MP3, checked by
  name and size before it is fetched and by ffprobe before ffmpeg decodes it; ffprobe and ffmpeg open local files only,
  those two demuxers and the decoders of those codecs, with two threads. The media worker has an environment of its own
  (`x-media-env`: the database, the queue, the buckets and `SECRET_KEY`), drops every capability and cannot gain any.
- **Smaller:** attribute filters refuse huge numbers and take 5 at most (L2); back-in-stock alerts for signed-in accounts
  only, to their own address (L3); API log-ins with a password or a code alone refused for staff and accounts with a
  second step (L4); staff cannot log in with a passkey alone (L5); a mobile number added or moved is emailed to both
  accounts (L6); a server does not start without `LEARN_CODE_SECRET`, nor does `make_book_codes` run (L7); 5 devices and
  1,000 quiz answers or card reviews a day per account, reminders sent 500 at a time by id, tokens Firebase calls invalid
  deleted (L8); the API's code sessions last 15 minutes and the PIN lookup is no longer kept in the server's cache (L9);
  deletion takes the SMS log and failed phone log-ins, Download my data has the SMS log, the email suppression and staff
  notes (L10); no staff order for a student whose parent has not confirmed (L11); the public bucket's storage keeps its
  key out of the picture tasks (L12); Turnstile is checked first and sent the client's address (I1); email subjects lose
  line breaks (I2); category imports check each slug (I4); revise-again lists only what the student may still open
  (I5); hls.js's hashes next to its licence (I8); Dependabot watches the Docker base image and no `.json` file reaches
  the image (I9).
- **To do before the next deployment:** set `LEARN_CODE_SECRET` in `.env` (the web container stops at `migrate`
  without it); add PUT to the private bucket's CORS rule (DEPLOYMENT.md section 17); for the reminders, a Firebase
  service account with the "Firebase Cloud Messaging API Admin" role only; a key for the public bucket alone in
  `PUBLIC_S3_*`.
- Open (decided in the review): refunds of offline payments (L11), Turnstile's hostname check (I1), staff discount and
  grant controls (I6), headless code confirmations counted in the session only (I7), firebase-admin's size and a
  blocking pip-audit (I9), clip links as bearer links (I10).

## QA pass of phases 5 and 6: every new flow walked (8 October 2026)

Every flow that phases 5 and 6 added was walked with the Django test client, with `curl` and a script against a
development server (sign-up, mobile number and codes by SMS and by email, the app's log-in by SMS, passkey pages,
parental consent by SMS, SES bounces and a send that they block, pictures, JSON-LD, the web app files, PIN codes,
tracking links, reviews, quotations, stock alerts, GSTR-1, the course API with and without access, book codes, the
plan, digital products, offers, staff orders, payment links, offline payments, every admin page for each role) and on
PostgreSQL 17, besides the unreliable cases (no ffmpeg, a corrupt or empty video, buckets that cannot be reached, Redis
and the broker down, Turnstile and FCM unset or out of reach, two redemptions of a code at the same instant). The
failures below were reproduced first; each has a test that fails without its fix. 439 tests, all passing on
SQLite and on PostgreSQL (the thread tests and `test_a_real_ffmpeg_run` skip where they cannot run); `manage.py check
--deploy` shows only W005 and W021 (with `LEARN_CODE_SECRET` set).

### Fixed

- **Orders:** the app's checkout accepted the staff-only payment method `offline` and made an order whose payment page
  failed with a server error: checkout takes `razorpay` or `cod` (the service, the serializer and the OpenAPI schema).
  A part refund (a goodwill amount, or a refused parcel refunded less its shipping) closed the course of an order with
  a course in it: only a refund in full does (`services.refunded_in_full`). A bundle of courses only was "out of
  stock", would have been charged shipping and left to be packed: it is a course (`Product.digital_only`, also
  `Totals.digital_only` for the pages).
- **Server errors:** `?attr_<text attribute>=%00` crashed on PostgreSQL; Google's three addresses answered 500 on a
  server without its keys (now 404); a member of staff who may only view products (SUPPORT) got a 500 on a product's
  page; a product picture saved while the broker was down ended in a 500 (its AVIF and WebP sizes are now made in the
  request, as emails and SMS are sent); the reminder task's batches had no order (a failure on PostgreSQL).
- **Privacy:** "Delete my account" now deletes the "email me when it is back" requests kept under the address; a student
  under 18 whose parent has not confirmed (`PARENTAL_CONSENT_MODE=verified`) reads the course but saves nothing in it
  (progress, quiz answers, card reviews, codes, settings, devices answer 403; taking a device off is allowed).
- **Shop:** the school quotation form lists books only (a course opens in one account; pupils get book codes); a
  quotation follows a book renamed since the request; the sitemap lists the shop page, the school-orders page, the
  shelves and the collections.
- **Admin:** the dashboard counts the clips that failed to process (`clips_failed`, for `templates/admin/dashboard.html`).
  `import_chapter_insights` says what is wrong when `--root` is (an error message, not a traceback).

### Added

- Tests: `ops/test_no_server_errors.py` (every address of the site and of the API answers an empty request without a
  server error, signed in or not: it finds the Google 500), a book code redeemed by two students, or twice by one, at the
  same instant (PostgreSQL), and the regression tests of the list above, beside the tests they belong to.

## Phase 7: API contract (8 October 2026)

18 tests more (`api/test_headless.py`, `api/test_contract.py`, `shop/test_api_contract.py`). Any frontend (the app, or
a web frontend of its own) can now do through documented JSON what the website's pages do; the server keeps every rule.

- **allauth.headless** at `/_allauth/` (clients `app` and `browser`; the website's pages stay): codes by email or SMS,
  passwords, passkeys, Google, the second step, sign-up, email, phone and password changes; its OpenAPI file at
  `/_allauth/openapi.json`. `POST /api/v1/auth/exchange/` turns an app's session token (`X-Session-Token`) into the JWT
  pair, so API v1 keeps its Bearer tokens; dj-rest-auth's endpoints stay, legacy-compatible. Emails link to the
  website's pages whichever client asked (`HEADLESS_FRONTEND_URLS`).
- **The site's rules hold there too:** every sign-up form is built on `accounts.signup.StudentDetailsForm`
  (`ACCOUNT_SIGNUP_FORM_CLASS`: the student details, the consent record, the STUDENT role, the parent's link, no phone
  at sign-up, Turnstile; after Google too); headless's code request and phone change take the website's forms
  (Turnstile; "wait a minute" rather than a server error); staff without an authenticator app get a JSON 403 from
  `/api/` with a session (it was a redirect) and from the exchange, while `/_allauth/` stays open for the set-up; no
  `/_allauth/` answer is cached.
- **New in API v1:** `me/teacher/`, `me/parent-consent/`, `me/` fields `consent_pending`, `login_phone`,
  `login_phone_verified` and `sms_updates`; `products/<slug>/reviews/` and `products/<slug>/stock-alert/`, `quotes/`
  (Turnstile while it is on), `orders/t/<token>/` (the emails' link, read-only), `config/` (what is switched on) and
  `pages/` (the legal pages).
- **OpenAPI:** operations tagged by area (auth, account, catalogue, record, shop, learn, site; `api/schema.py`) and
  examples on the main requests; `spectacular --validate --fail-on-warn` clean. API.md has the new endpoints and a
  "Frontend integration guide"; DEPLOYMENT.md section 20 the settings. JSON clients send Turnstile's token as
  `turnstile` (the widget's own field still works).
- Open: guest checkout through the API (it keeps no session carts: guests buy on the website); the app's passkey
  association files (`/.well-known/`); a teacher's view of their students.

## Website redesign (8 October 2026): stage 1 done, stage 2 in progress

Work package C of `../docs/examleaf-phase5-plan.md`, from the design canvas (`../docs/design/direction.md`,
`components.md`, `tokens.css`).

- **Stage 1** (commit f8e4e5f): self-hosted subset fonts (Poppins and Hind Siliguri), one stylesheet
  (`static/css/site.css`), the base layout and the public pages.
- **Stage 2** restyles the shop, account and allauth templates, the emails and the staff player. In progress; its first
  part is in commit ba0b9dd.

## Phase 6 E: store flexibility (8 October 2026)

26 tests more, in `shop/`. Work package E of `../docs/examleaf-phase6-plan.md`; its Status section has a line per item.
Our shop grows the ideas of django-oscar and Saleor that matter for a publisher (neither is installed).

- **Catalogue:** a category tree (django-treebeard, drag and drop in the admin), products on several shelves, category
  pages `/shop/category/<slug>/` with their sub-shelves' products, collections in the staff's order
  (`/shop/collection/<slug>/`), the shop page listing both and filtering by `?kind=`; product types with attributes
  (text, number, list, yes/no; values checked by kind) shown under "Details"; related products ("You may also need");
  a renamed product's old address redirects (301, `SlugHistory`); `GET /api/v1/categories/`, `/collections/`, and
  product filters `?category=`, `?collection=`, `?attr_<code>=`.
- **Digital products:** kind "Digital (in the app)", alone or in a bundle with a book: no shipping, stock or cash on
  delivery, one per order, an account needed; paid, it opens the course (`learn.services.grant_for_order`) and an order
  of digital products only is delivered at once; cancelled or refunded in full, it closes it (`revoke_for_order`). No
  "Book" or shipping in its JSON-LD; the form refuses the books' HSN code for it.
- **Offers:** automatic discounts (per cent or rupees; on the cart, products, categories or collections; minimum copies
  or value; dates; limits in all and per customer; combinable or alone) applied after the coupon and shown as their own
  lines everywhere ("savings" in the API). Each order line keeps its share of the discounts (`OrderItem.discount`,
  `OrderDiscount` lines), which invoices and credit notes print; orders made before keep their old split.
- **Staff orders:** "Add order" in the admin for phone and school orders (offers, a staff discount, shipping set by
  hand, a note), Razorpay Payment Links emailed by us and completed once by the `payment_link.paid` webhook (and by the
  clean-up's check of the link), payments received offline recorded with their bank or UPI reference (printed on the
  invoice), internal order notes with history, the order's timeline, and a customer page (orders, addresses, reviews,
  quotations, stock alerts, courses).
- **Admin:** filters and search on every store model, stock alerts listed, bulk "Put on sale", "Take off sale" and
  "Set stock", product and category import and export for ADMIN only (logged), inline attribute values, and the
  dashboard's store section (sales by day, most sold, running out, reviews and quotations waiting).
  django-admin-sortable2 2.3.1 was left out (no Django 6.1 templates): pictures keep position numbers.
- **Roles:** CONTENT_EDITOR the catalogue and the course content; SALES offers, staff orders, offline payments, notes,
  reviews, quotations and stock alerts; SUPPORT course entitlements and book codes (migration 0019 and
  `bootstrap_roles`).
- **Download my data** adds reviews, quotation requests, stock alerts and the course's data.

## Phase 6 D: revision course (8 October 2026)

35 tests more, in `learn/`. Work package D of `../docs/examleaf-phase6-plan.md`; its Status section has a line per item.
A new app, `learn`, for the mobile app's short-video revision (the app itself is a separate project).

- **Content:** chapters (subject, number, Board marks, previous-year questions, must-do note), one revision per
  chapter (target 10 to 15 minutes, draft or published, order), clips (order, kind: concept, trick, shortcut, formula,
  pattern, mistake, previous-year question; the video; notes in Markdown; free preview; linked questions; tags), flash
  cards and one-mark quiz items (multiple choice, true or false, fill in the blank). Admin: clips inline on the
  revision with their processing status and a Preview link, Move up / Move down, publish and back to draft, "Process
  the video again". django-admin-sortable2 2.3.1 was left out: it has no Django 6.1 templates or actions script.
- **Video:** ffmpeg (Dockerfile) on a `media` queue (docker-compose.yml `media-worker`, one at a time) makes each
  upload into HLS for low-end phones: 480×854 at about 700 kbps and 720×1280 at about 1.5 Mbps, AAC 64 kbps, 4-second
  segments, a poster at 1 s; a bad file fails with the end of ffmpeg's messages, storage trouble is tried 3 times;
  `manage.py reprocess_clips`. Files in the private storage behind links signed for 10 minutes (`/learn/hls/…`,
  segments redirected to the bucket), or the public bucket with `LEARN_PUBLIC_VIDEO=1`; uploads up to
  `LEARN_MAX_UPLOAD_MB`.
- **Data:** `manage.py import_chapter_insights` (marks per chapter from `format.json`, question counts from `pyq/`;
  51 chapters, 70/70/80/70 marks) and `manage.py build_quiz_items` (664 quiz items from the one-mark questions whose
  options and answer parse unambiguously; the rest counted and skipped).
- **Access:** entitlements per subject or all (book code, purchase, staff grant; a code or a purchase lasts a year);
  book codes of 12 characters without 0/O/1/I, kept as a keyed hash (`LEARN_CODE_SECRET`), redeemed once, 5 tries an
  hour per user and per address, logged; `manage.py make_book_codes` writes the printer's CSV;
  `learn.services.grant_for_order` and `revoke_for_order` for the shop's digital products. Free: the first clip of every
  revision and the first chapter's flash cards (`LEARN_FREE_PREVIEW`).
- **Pass plan:** chapters by Board marks × past-paper questions × (1 + share of wrong quiz answers), unwatched clips
  packed into the student's minutes a day until the exam, the minimum to pass (most marks per minute up to 1.5 times
  the pass marks); revise-again with wrong answers back after 1, 3 and 7 days.
- **API** (`api/learn.py`, API.md "Revision course"): chapters, clips with signed links and progress, quiz checked on
  the server, flash cards, plan, revise-again, redeem, entitlements, settings, devices. Throttles `learn_redeem`,
  `learn_redeem_address` (5 an hour), `learn_quiz` (600 an hour).
- **Reminders:** a daily push (18:00) through Firebase Cloud Messaging with firebase-admin 7.7.0, to students who turn
  it on, only with `FCM_SERVICE_ACCOUNT_JSON`; addressed to the app's Firebase installation ID.
- **Privacy:** progress, quiz answers, card reviews, settings, entitlements and devices are deleted with the account
  (receiver on the deletion request); `learn.services.export_learning` for Download my data. No video analytics.
- **Staff player:** `/learn/preview/<clip>/` with hls.js 1.7.3 served by the site (`static/learn/`, its licence beside
  it); CSP `media-src 'self' blob:` and, with buckets, the bucket hosts.

## Phase 5 B: storage, media, shop and web platform (8 October 2026)

21 tests more. Work package B of `../docs/examleaf-phase5-plan.md`; its Status section has a line per item.

- **Two buckets** (Cloudflare R2; DEPLOYMENT.md sections 15 and 17): a private one for invoices, credit notes,
  quotations and answer sheets, reached by links signed for 5 minutes, and a public one for product pictures on
  `PUBLIC_MEDIA_DOMAIN`, cached a year as immutable; keys `S3_*` of their own (`PUBLIC_S3_*` for a private bucket on
  AWS S3 Mumbai); the boto3 checksum variables R2 needs; the CSP allows the media domain. Without buckets (development,
  tests, one server) both stay in `media/`, and `/shop/media/` serves only the public folders.
- **Pictures:** covers and product pictures get AVIF and WebP sizes on the worker (django-pictures 1.8.0, covers
  cropped 2:3) and pages use `<picture>`; their widths and heights are stored, so no page opens the files. The four
  static covers have committed AVIF and WebP copies at 320 and 480 px (`manage.py build_covers`).
- **Search engines and link previews:** canonical link and Open Graph tags on every page (`templates/_head_meta.html`,
  included by base.html), a default preview picture and one per product (cover and title, made on save by the worker),
  JSON-LD for products (Product and Book: price, stock, ISBN/GTIN, shipping, returns; the rating only from approved
  reviews), breadcrumbs and the publisher. No FAQ markup (retired by Google).
- **Web app:** manifest, maskable icons drawn with Pillow, a service worker that keeps only the static files and a
  standalone offline page (never a page, so nothing of an account outlives a log-out), registered from the new
  `static/js/site.js` (`templates/_body_end.html`); CSP `manifest-src` and `worker-src 'self'`.
- **PIN codes:** `manage.py import_pincodes <csv>` loads India Post's directory (data.gov.in); the address forms fill in
  the district and state, and the website, the checkout and the API refuse a state that does not match the PIN code.
- **Shipping:** a courier list on shipments; the tracking link is filled in when staff leave it empty (Delhivery, Blue
  Dart, Ekart, 17TRACK for India Post and the rest).
- **Reviews** from buyers whose order was delivered, one per book, approved in the admin, shown as "Verified buyer";
  honeypot and rate limit; deleted with the account.
- **School and bulk orders:** a public form (`/shop/school-orders/`, GSTIN checked with python-stdnum, Turnstile when
  on), staff emailed, a quotation PDF valid 15 days from the admin, kept in the private bucket. The coupon form takes
  Turnstile too.
- **Stock:** "Email me when it is back" on products out of stock (one email, hourly check), a daily email of the books
  running low to the SALES role (`SHOP_LOW_STOCK`).
- **GST:** `manage.py export_gstr1 --from --to` writes the B2C, HSN summary and credit-note CSVs for the accountant.
- **Order SMS** go out from the shop's notifications through `ops.sms.send_order_sms` (phase 5 A).
- **Supply chain:** Dependabot (pip and GitHub Actions, weekly); DEPLOYMENT.md notes Jazzband's wind-down.
- Upgrading: `MEDIA_ENDPOINT_URL` is gone (`S3_ENDPOINT_URL`), and `MEDIA_BUCKET` now needs `PUBLIC_MEDIA_BUCKET` and
  `PUBLIC_MEDIA_DOMAIN`; product picture URLs change with the buckets (API.md). The first migration records the size of
  every product picture and queues its AVIF and WebP sizes for the worker: until the worker has made them (seconds), a
  product page may show no cover. Beat gets two new schedules (stock alerts hourly, the low-stock email daily). SALES
  got its permissions for reviews, quotations and stock alerts in Phase 6 E (`accounts/roles.py`).

## Phase 5 A: sign-in and communications (8 October 2026)

32 tests more. Work package A of `../docs/examleaf-phase5-plan.md`; its Status section has a line per item.

- **Phone log-in.** A student adds a mobile number on My account (never at sign-up) and confirms it with an SMS code;
  then it logs in with the password or a code by SMS ("Log in with a code", email or number). Numbers are taken as
  people type them ("98640 12345") and kept as +91…; one account per number. Every code, emailed or texted, is now 6
  digits (was `ABCD-EFGH`). Failed password log-ins by phone are limited per number (allauth keyed them all on one
  empty key). An empty "send me a code" form and a second code to the same number within a minute no longer end in a
  server error. Phone log-in exists only where SMS are sent (`SMS_BACKEND=msg91`, or development).
- **Passkeys** for everyone (My account → Passkeys, "Use a passkey" on the log-in page; Passwordless ticked by
  default), one relying party for the host of `SITE_URL`; staff may use a passkey instead of the authenticator app.
- **Google sign-in** when `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are set: a new student fills in the student
  details after Google (one form mixin with the sign-up form); PKCE; `form-action` allows Google only then.
- **App API:** `POST auth/phone/code/` and `auth/phone/confirm/` (API.md): log-in by SMS code, the same JWT pair.
- **SMS gateway** (`ops/sms.py`): one Celery task, `console` or `msg91` (OTP and Flow APIs), retries on network
  errors, an SMS log without whole numbers (Admin → Ops), at most `SMS_DAILY_CAP` a day counted in the
  database. Order SMS (placed, shipped, delivered) for students who ask for them on My account, through
  `ops.sms.send_order_sms(order, kind)`.
- **Parental consent by SMS** (`verified` mode): a parent's Indian mobile number gets the link by SMS; links are now
  short (`/c/<token>/`, email too: links sent before this release stop working) and record how they were confirmed.
- **Email:** Amazon SES as the documented production backend, bounce and complaint webhooks (`/anymail/…`, only with
  `ANYMAIL_WEBHOOK_SECRET`), an email suppression list that stops sends to bad addresses (staff delete a row to send
  again).
- **Cloudflare Turnstile** on sign-up and code requests when its keys are set (fails open, logged).
- Data export and account deletion include the new data (log-in number, passkeys, Google accounts); Sentry filters SMS
  variables; DEPLOYMENT.md sections 13, 15 and 16, RUNBOOK.md "SMS", "Phone numbers and passkeys", "Email bounces and
  complaints".
- Upgrading: `migrate` adds the SMS log, the email suppression list and the Google tables; `bootstrap_roles` gives SUPPORT
  the right to view the SMS log and to delete suppressions (both run on every deploy).

## Phase 4 security, shop (8 October 2026)

16 tests more, in `shop/test_security.py`. The shop's findings of SECURITY_REVIEW.md; each finding there has its status line.

- **Order links (M2).** Each order has an unguessable token, and every email about it links to `/orders/t/<token>/`:
  the order read only, its invoice and credit notes, and a cancel button while it is pending or paid. "Find your
  order" (website and API) no longer opens the order: for a guest order it emails that link to the order's address,
  and it answers "If an order matches, we have emailed you a link." either way. 10 lookups an hour per client address,
  per email address and per order number; refused while they cannot be counted. API: `POST orders/lookup/` no longer
  returns the order.
- **Test and live mode (M3).** Payments and orders record the mode of their Razorpay keys. Payments, webhooks and
  refunds of the other mode change nothing; invoice and credit-note series follow the order's mode; once live, test
  orders are marked TEST and cannot be packed or shipped. One webhook secret per mode (`RAZORPAY_WEBHOOK_SECRET_TEST`,
  `RAZORPAY_WEBHOOK_SECRET`). `SHOP_OPEN=0` leaves buying to staff during Razorpay's review ("Shop opens soon").
- **Webhook data (M6).** Only the payment's id, order, status, method, amount, currency, error and time are kept (the
  stored payloads are stripped by a migration), not shown in the admin, and cleared after 180 days.
- **Cash on delivery (M8).** Only for accounts with a confirmed email address, orders up to `SHOP_COD_MAX_VALUE`
  (₹1,500) and two on their way per account. Checkout and place order: 10 per 10 minutes per client address.
- **Retention (M10).** Orders never paid or placed lose the customer's details 30 days after they were cancelled; the
  yearly purge of invoiced orders past eight years is in RUNBOOK.md.
- **Refunds (L1, L3).** A retried refund first looks for the one Razorpay already made; a second payment captured for
  a paid order is recorded and refunded by itself, and a cancellation still refunds the first one.
- **Coupons (L4).** One answer for every code that cannot be used; 10 tries an hour per client address (website) and
  per user (API, `API_THROTTLE_COUPON`).
- **Redis (L8).** The cache has a Redis of its own (`redis-cache`: 256 MB, least used keys evicted); the queue's never
  evicts. The shop's limits refuse while the cache cannot be read; Razorpay's webhooks go on.
- **Hardening (I4, I6, M5).** Products and addresses sort only by the fields named; invoice PDFs fetch only static files
  and data: URLs; the orders export needs `export_order` (ADMIN) and is logged.
- Migrations `shop` 0005 to 0008.

## Phase 4 security, accounts, API and operations (8 October 2026)

23 tests more, 227 in all. The security review's other findings (SECURITY_REVIEW.md, each with its status line), one
test or more each in `accounts/test_security.py`, `api/test_security.py` and `ops/test_security.py`.

### Staff and roles

- **Two-factor authentication for staff** (H2): `allauth.mfa`, an authenticator app with ten recovery codes; staff
  without one are sent to set it up before anything else opens; the admin's log-in is allauth's (its per-account limit,
  the code); staff sessions end 8 hours after the log-in. RUNBOOK.md "Staff accounts".
- **ADMIN can no longer** edit periodic tasks, task results, groups, permissions or second factors, nor make anyone
  superuser or change a superuser; only superusers give roles (I7).
- **Admin exports** need an `export_…` permission (ADMIN only), leave out dates of birth and parents' contacts, are
  written to the admin log, and escape a leading `=` (M5, L7).

### Log-ins, passwords and the API

- The API's log-in counts failures per account like the website (5 in 5 minutes); allauth now sees the client's address
  behind Caddy instead of Caddy's (M7).
- Password reset emails: 5 a minute per address, API and website together (L5); five wrong passwords in an hour on the
  API's password checks revoke the user's refresh tokens and answer 429 (L6).
- Passwords: 10 characters at least, none found in data breaches (Pwned Passwords); reset links last an hour (L11).
- At most 20 new attempts of a paper a day; notes 2,000 characters (L12). Boards and subjects sort by id and name only
  (I4); the public API's cache keys ignore unknown query parameters (L8).
- `JWT_SIGNING_KEY`: the app's tokens can have their own key (I5).

### Operations and privacy

- `/health/` and `/health/web/` answer only the uptime monitor (Caddy, `X-Health-Token`) and keep their results 20 s;
  `/api/v1/health/` is gone (H1).
- Sentry gets no stack-frame variables and no email text (M4).
- Verifiable parental consent behind `PARENTAL_CONSENT_MODE=verified`: a link emailed to the parent, the account
  read-only until they agree, how and when recorded (M9); to switch before May 2027 (DEPLOYMENT.md section 14).
- Expired sessions are deleted daily; uploaded backups can be encrypted with age, with a 30-day bucket rule; the
  privacy draft says how logs are really kept (M10).
- The site refuses to start with development settings on a server (I1); a Permissions-Policy header (I6); QR images
  only for published papers, cached a day (I3).
- CI: read-only permissions, a pip-audit job (not blocking yet); test and lint tools in `requirements-dev.txt`, not in
  the image (L10).

## Phase 4: QA pass (8 October 2026)

60 tests more, 188 in all. Every flow of the site was walked on a development server (visitor, cart, log-in, both
checkouts, cancellation, guest lookup, registration under 18, data export, deletion, teacher access, every admin page,
every API endpoint and error), the failures below were reproduced first, and each fix has a test that fails without it.

### Fixed: money and orders

- **Coupon limits** ("one per customer", "at most N uses") were checked only when an order was made, so several open
  orders could each take the last use. They are checked again, under a lock on the coupon, when an order is paid or
  placed (`services.claim_coupon`): the first wins; a cash-on-delivery order that loses goes back to the cart with a
  message, an online payment that loses is refunded and the customer told why. The payment page and the API stop
  before taking money for a coupon that is gone.
- **A payment Razorpay took but the site never heard about** (the customer never came back and the webhook was lost) was
  left charged without an order when the order expired after two days. Before cancelling, the daily clean-up now asks
  Razorpay (`payments.reconcile`); a Razorpay that cannot be asked leaves the order for the next run;
  `manage.py reconcile_payments` does the same by hand.
- The clean-up could cancel an order that was paid in the same moment: the order is checked again under its lock.
- After a payment that could not be used (books sold out, coupon gone) the thank-you page said "placed" and emptied the
  cart; it now says the order could not be completed and is being refunded, and the cart is kept (website and API).
- Refunds made in the Razorpay dashboard were ignored; they are recorded from their webhook (the order, the customer's
  email and the credit note follow).
- Cash-on-delivery review pages that nobody finished stayed pending for ever; they are cancelled after two days, like
  online orders.
- Invoices: no invoice of the real series is numbered while a `SELLER_*` setting still holds a `[placeholder]` (the numbers
  cannot be reissued); the "Amount" column is what is payable after the discount; "MRP-inclusive" became "prices include
  tax"; the Docker image carries Noto fonts, so a name or address in Assamese prints (it would have been empty boxes).
- The admin's revenue is net of refunds (a refused parcel refunded less the shipping brought in nothing).
- Admin: saving a product page that was opened before a sale put the old copy count back; pictures over 2 MB are
  refused with a reason.

### Fixed: availability

- **Redis down: nobody could log in, register or reset a password** (allauth's rate-limit lock treated django-redis's
  fail-soft `add` as "locked" and answered 429; the old test only opened pages). `examleaf.cache.SoftRedisCache`
  fixes it.
- A broker that accepts connections and never answers hung the request for ever; Celery now gives up after about 4
  seconds and the email is sent from the web process. If the email provider is down as well, the failure is logged and
  the page goes on (it was a 500). The old test of the broker fallback never reached the broker: fixed (`broker` fixture).
- `/health/` held a gunicorn worker for 3 seconds on every call (the Celery ping waited out its timeout): `limit=1`.
- A `%00` in an address gave a 500 on PostgreSQL (`/s/AB%00C/` among them): 404.
- Double clicks ended in a 500 for the second request: "Add to cart" (a unique row made twice), "Delete my account" and
  "Ask for teacher access" (one waiting request or profile per user).

### Fixed: privacy

- A sign-up with an address that already has an account answered faster than one with a new address (no password
  hashing): the same work is done, so the timing does not tell.
- Account deletion left the user's email in the admin history of their attempts and the name and PIN code in that of
  their addresses.
- Download my data now also holds the roles, the cart, each order's payments and status timeline.
- The delete page says that orders and invoices stay (tax law); the notes of an attempt are limited to 2000 characters.
- Pages seen by a signed-in user were kept by the browser: after Log out on a shared computer (a cyber café) the Back
  button showed the account, record and orders; they now carry `Cache-Control: no-store`.

### Fixed: front end and copy

- The header is one row at every width: on a phone the name, the cart and a Menu button (CSS only, a hidden checkbox:
  no JavaScript, the CSP is unchanged), instead of three lines; keyboard operable.
- Text colours that missed 4.5:1 (stock, saving, paid-status) darkened; the brand link has an accessible name.
- Every page has its own title and meta description; the private ones are `noindex`; `robots.txt`, a favicon and touch
  icon were added.
- Branded 400, 403, 403 for an expired form, 404, 429 and 500 pages (the 400 and 500 pages need no layout or database;
  the API answers JSON); the 429 of the guests' order lookup was plain text.
- "Log in" and "Register" everywhere (allauth said Sign In and Sign Up), emails greet from ExamLeaf instead of the
  host name, the words about registering follow `SOLUTIONS_REQUIRE_LOGIN`, the About page names the publisher and
  points to Contact, dispatch and delivery times are no longer promised outside the Shipping Policy (product page,
  emails), the empty home page no longer says `manage.py import_papers`.
- `[placeholders]` in the legal pages are marked yellow on the site, counted in the Pages list and on the admin index.

### Added

- Tests: error pages and metadata (`ops/test_errors.py`), the admin crawl (`ops/test_admin_pages.py`, every list, add,
  change, history and delete page), Redis half-open (`ops/test_resilience.py`), copy (`ops/test_copy.py`), orders and
  coupons at the same instant, stuck payments and the admin (`shop/test_robustness.py`: four of them run threads against
  PostgreSQL and are skipped on SQLite), export and sign-up (`accounts/test_export_and_signup.py`).
- Docs: environment variable reference in DEPLOYMENT.md, the shop in RUNBOOK.md (a stuck payment, refund disputes,
  reconciling settlements, a missing invoice, coupons and stock), API.md matched to the routes, this file.

## Phase 3b: shop on the API, credit notes, privacy of the shop (8 October 2026)

Shop REST endpoints (products, cart, addresses, orders, payment through Razorpay's mobile SDK, cancellation, invoice
and credit note PDFs, guests' lookup); credit notes (own number series, GST reversed per line); orders in Download my
data; Sentry scrubbing of secrets and personal data; the `SOLUTIONS_REQUIRE_LOGIN` switch (open or registered
solutions); webhook replay protection; a readiness check before gunicorn starts; the CI builds the Docker image; tests
isolated so that they pass in any order on SQLite and PostgreSQL. 128 tests.

## Phase 3: REST API v1 (8 October 2026)

DRF with dj-rest-auth and JWT (short access token, rotated and blacklisted refresh token, ended by a password change),
sign-up and the email code on the website's own form and rules, drf-spectacular schema with Swagger UI and Redoc served
by the site, CORS for listed origins on `/api/` only, throttles counted in the cache, API.md.

## Phase 2: the shop (8 October 2026)

Catalogue and product pages; the cart (a guest's joins the account's at log-in); checkout with Indian address checks
and saved addresses; Razorpay payments and signed webhooks; cash on delivery; the order and payment state machines
with a customer timeline; stock under row locks; coupons; shipping rates by state; shipments with tracking; refunds
(also partial); GST invoices as PDFs (bill of supply while every book is exempt); order management in the admin (pack,
ship, deliver, cancel, refund, export); Refund and Shipping policy pages; SALES and SUPPORT roles.

## Phase 1: production (8 October 2026)

PostgreSQL, Redis cache and Celery with beat; Sentry and JSON logs with request IDs; roles and permissions; teacher
access requests and their verification; DPDP self-service (Download my data, Delete my account with seven days to
change one's mind, consent records); legal pages with history; the branded admin with its dashboard; the Docker and
Caddy stack; backups; CI; DEPLOYMENT.md and RUNBOOK.md.

## Phase 0: the site (8 October 2026)

Books, papers, questions and solutions imported from the Markdown of the four subjects (30 papers each); the QR code
of every paper opening its solutions; registration with parental consent under 18 and an emailed code; My record of
attempts; a Markdown renderer that keeps the maths for KaTeX and escapes everything else; a strict Content-Security-
Policy; private caching of the gated pages; failed log-ins only in the lock-out records. A first QA pass fixed an XSS in
the renderer and the consent logic. 33 tests.
