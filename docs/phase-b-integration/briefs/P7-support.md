# Package P7: Support (model: Claude Opus 5.5)

Ports: Django 8117, console 3037 (`E2E_API_PORT=8117 E2E_WEB_PORT=3037`), the public site's dev server 3047 if you
run it. Read COMMON.md first.

Plan rows: section 5.14 (every row marked **must**), 5.0, section 7.10 (the new `support` app), section 9's dates (the
1 January 2027 E-Commerce Rules: a copy of the complaint as recorded in the acknowledgement; National Consumer
Helpline complaints with their docket), section 10.1 (Frappe Helpdesk not installed: a small helpdesk of our own).
Research: `research-lms-crm-cms.md` sections 0, 4.1 to 4.9, `research-commerce-gst.md` 6, `research-rbac-security.md`
4.6. The legal clocks in calendar time, never paused, across month ends, are an exit criterion of 9.2.

## What exists (read before building)

The contact form (`api/views.py` `ContactView`: emails the support address, stores nothing, 5 an hour, Turnstile),
`staff/models.py` `DataRequest` (the DPDP rights queue with its clocks: a grievance ticket may start one), the
customer record (`staff/api.py` `UserViewSet`: masked, revealed with a reason), the shop and learn services the
ticket's actions call (`shop.services.refund_order`, `cancel_order`; `shop.tasks` invoice and code emails;
`learn.models.Entitlement`, the book-code lookup in `learn`), `ops/sms.py` and `shop.services.notify`, the email
templates, `accounts/roles.py`, the website's account pages (`examleaf-frontend/src/app/(account)/account/`), the
inbox (`staff/signals.py`).

## Backend: a new app `support/` (models, services, clocks, api, tasks, tests, README), mounted at `/api/v1/staff/support/` (tag "support (staff)")

1. **Models** (section 7.10): `Ticket` (a customer-visible number of its own series `SR-YYYY-NNNNNN`, gapless under
   a row lock; source form | email | phone | whatsapp | nch with `nch_docket`; category order | payment | book_code |
   qr_solutions | content_error | school_order | privacy_request | grievance; priority; status new | open |
   waiting_customer | waiting_third_party | resolved | closed; requester as an account or an email or phone (hashed
   lookups, the plain value encrypted at rest with `integrations.crypto`, masked in answers, revealed with the
   existing reveal rules: a reason, step-up, a throttle, a `sensitive_read` event); assignee; the linked order,
   data request or record; received, acknowledged, first human response, resolved and closed times; the legal due
   times; breach flags; reopened count; `complaint_copy_sent_at`; CSAT later), `TicketMessage` (direction in | out |
   note, author, body, attachments in the private storage, sent at, mail headers for threading), `SavedReply` (title,
   language `as` | `bn` | `en`, body with variables and fallbacks; the refund reply carries Razorpay's expected days by
   method as variables). History on Ticket.
2. **The legal clocks** in `support/clocks.py`, pure functions with tests across month ends and the IST day:
   acknowledge within 48 hours and redress within one calendar month (E-Commerce Rules), an NCH complaint within
   30 days, a DPDP rights request within 90 days (from 13 May 2027; the SPDI Rules' one month until then: both
   computed, the earliest applies), the IT Rules' 24 hours and 15 days only when the setting
   `SUPPORT_INTERMEDIARY_RULES` is on (off: counsel's answer pending). The due time is the earliest clock that
   applies; breach flags set by a task every 15 minutes (`single_run`); inbox items for SUPPORT at 75 % of each clock
   and at breach, with `due_at`, and a red clock in the console.
3. **The inbox of sources**: the contact form now creates a ticket (and still emails the support address as a copy
   if `SUPPORT_COPY_TO_EMAIL` is set); email in: an inbound-mail endpoint `POST /api/hooks/support-mail/` taking the
   provider's parsed message (SES receipt through SNS or a forwarder: a signed body with a shared token in a header,
   compared in constant time, the raw body stored with its SHA-256, deduplicated on the Message-ID) with a loop guard
   (our own addresses, auto-replies) and threading by `[SR-…]` in the subject and the mail headers; "log a call" and
   WhatsApp as a staff form (`POST support/tickets/` with source); NCH complaints with their docket number in the
   same form. Spam quarantine for the form (Turnstile, honeypot, rate limits exist; a `spam` state purged after 30
   days by a nightly task, kept out of reports).
4. **Acknowledgement**: sent automatically with the ticket number by email (and SMS when only a phone is known), and
   from 1 January 2027 (`SUPPORT_COMPLAINT_COPY_FROM`, a date setting) including a copy of the complaint as recorded;
   only a human reply (`direction=out` by a person) sets the first response. Every outgoing message through SES as the
   site sends mail; threading headers set so replies come back to the ticket.
5. **The queue and the record**: `GET support/tickets/` (sorted by due time, filters status, category, priority,
   source, assignee, `mine`, overdue, `q` on the number, order number, email hash or phone hash: a lookup event),
   `GET support/tickets/{number}/` (the messages, the sidebar data: the requester's orders with Razorpay ids and
   status, shipments, invoices, entitlements with source and valid until, codes redeemed, devices, past tickets,
   consents, all from the existing models and masked as the customer record is; opening a minor's ticket is a
   `sensitive_read`), `POST support/tickets/{number}/messages/` (reply out, internal note with @mentions that open an
   inbox item for the person named), `assign/` and `claim/`, status transitions with the fields each category requires
   at closing (refused with field errors otherwise), `reopen/` (count), solved tickets closed after 4 days by the
   15-minute task.
6. **Actions from the ticket**, each logged on the ticket and audited: refund full or partial (through the shop's
   refund action: the quantities start at zero; a 202 when it waits), cancel the order, resend the invoice, resend the
   code email, extend access by N days with a reason, look up a book code (by hash) and answer in one line, start a
   data request from a grievance ticket (`DataRequest` with the ticket linked). Permissions: the actions keep their
   own (`staff.refund_order` and so on); the ticket endpoints `staff.handle_ticket` (new, medium: SUPPORT, SALES for
   order tickets, ADMIN) and `support.view_ticket`; CONTENT_EDITOR note-only on content_error tickets (a permission
   `support.note_ticket`, new).
7. **Saved replies**: CRUD (`support.change_savedreply`: SUPPORT leads = ADMIN; SUPPORT reads and inserts), variables
   `{name}`, `{order}`, `{refund_days}` with fallbacks, the customer's language chosen from the account (`as`,
   `bn`, `en`; default `en`).
8. **"My requests"** on the site: `GET /api/v1/me/tickets/` (the signed-in customer's tickets: number, category,
   status, the dates; never staff notes) and `POST /api/v1/me/tickets/` (a new request from the account); the page
   `/account/requests/` in `examleaf-frontend` in the Answer Script design listing them with the status and a form
   (its Vitest test; the account navigation gains the entry; `noindex`). Guests use the contact form and get the
   number by email.
9. **The grievance register export**: `Job.Kind.GRIEVANCE_EXPORT` (`staff.export_grievances`, new, high; ADMIN,
   FINANCE? No: ADMIN and OWNER; AUDITOR too): a dated CSV of complaints received, acknowledged and resolved with the
   days taken, the NCH docket, no personal data beyond the ticket number and category; capped by `export_rows` with
   approval above.
10. **Reports** `GET support/summary/`: volume by category, first response and resolution medians, backlog,
    breaches, for the module's home (test tickets of test orders excluded).

## Tests the exit criteria need

The clocks across a month end (received 31 January 14:00 IST: redress due 28 February 14:00 IST; 31 March → 30 April;
a leap year), never paused by waiting states, 48 hours across the IST midnight; the earliest clock applies; the
breach task flags once; the number series gapless; the contact form makes a ticket and the acknowledgement carries the
complaint copy from the setting's date and not before; inbound mail threads by number and header, loops guarded,
duplicates ignored; every endpoint in the matrix; the reveal rules on the requester's contact; the note-only
permission; a refund from a ticket waits above the cap; "My requests" shows only the customer's own; the export's job
and its cap; query counts on the queue; spam purged after 30 days.

## Console

`/support/` (the queue opening on "due soonest" with each ticket's legal clock as a countdown; tabs mine, unassigned,
overdue, waiting, all; filters in the URL), `/support/tickets/[number]/` (the conversation, the reply box with saved
replies inserted by one keystroke in the customer's language, internal notes, the sidebar with the customer's orders
and course without a click, the actions, assign and claim, status with the closing fields, the clocks), `/support/new/`
(the log-a-call and NCH form), `/support/replies/` (saved replies), `/support/export/` (the grievance register job).
Mock fixtures for every state including an overdue ticket and a breached one. Mock journey: queue → ticket → saved
reply inserted → reply sent → status changed; new NCH ticket. Real journey (`real.spec.ts` + seed): SUPPORT opens a
seeded ticket, replies, the first response time is set, the audit trail shows it.

## Boundaries

The DPDP rights queue itself (data requests, incidents) exists and is extended by Legal (P8): you link to it and start
one from a ticket through the existing `DataRequest` model only. Refunds are P1's action (call `approvals.ask` with the
existing `order.refund` name and the payload it takes today; if P1 extends the payload, the merge keeps your call
valid: use only `order`, `amount`, `cancel` and `reason`). Do not edit `staff/api.py`.
