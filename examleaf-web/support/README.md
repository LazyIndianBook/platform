# support: tickets and their legal clocks

A small helpdesk of our own (plan 5.14; 10.1: Frappe Helpdesk is not installed), behind the Admin Control Panel's
Support module and the website's "My requests": every complaint or question becomes a **ticket** with a number the
customer can quote (`SR-2026-000123`), the deadlines the law sets counted from when it came, the conversation (email
in and out, calls and WhatsApp messages recorded, internal notes), and the actions support takes on the customer's
orders and course from the ticket itself. The research behind it is
`../docs/research/2026-10-09-admin-control-panel/research-lms-crm-cms.md` sections 4.1 to 4.9, `research-commerce-gst.md`
6 and `research-rbac-security.md` 4.6. The rules live here; the panel draws what the API answers. The endpoints are in
[API.md](../API.md) "Support (staff)" and "My requests".

| File | What |
|---|---|
| `models.py` | `Ticket` (with history), `TicketMessage`, `TicketAttachment`, `SavedReply`, `TicketSeries` |
| `clocks.py` | the legal clocks, pure functions: what each rule allows from the moment a complaint is received |
| `services.py` | everything that happens to a ticket: making it, the acknowledgement, messages and mentions, statuses, assignment, the clocks' watch, the actions, saved replies, spam, an erased account |
| `mail.py` | email out (the acknowledgement, replies, the support address's copy) and in (parsing, the loop guard, threading) |
| `views.py` | "My requests" (`/api/v1/me/tickets/`) and the support mailbox's hook (`/api/hooks/support-mail/`) |
| `api.py`, `serializers.py`, `sidebar.py` | the staff API under `/api/v1/staff/support/`; the sidebar beside a ticket |
| `register.py`, `management/commands/grievance_register.py` | the grievance register (a background job, and its break-glass command) |
| `tasks.py` | the clocks' watch every 15 minutes, the nightly purge, the acknowledgement, an email forwarded |
| `signals.py`, `checks.py`, `admin.py` | an erased account's tickets forgotten; the encryption key's check; the Django admin (read-only) |
| `tests/` | `pytest support` |

## The model

| Model | What it is |
|---|---|
| `Ticket` | `number` (`SR-YYYY-NNNNNN`, India's calendar year, gapless: `TicketSeries` under a row lock, a ticket rolled back gives its number back), `source` (form, email, phone, whatsapp, nch with `nch_docket`), `category` (order, payment, book_code, qr_solutions, content_error, school_order, privacy_request, grievance; empty while not sorted), `priority`, `status`, `language` (`as`, `bn`, `en`: guessed from the script, changed by staff; the saved replies follow it), `subject`; the requester as an account (`user`, SET_NULL), a name, an email address and a mobile number (each encrypted at rest with `integrations.crypto` and found by a keyed hash, `requester_*_hash`); `assignee`; the linked `order`, `data_request` or record (`record_type`, `record_id`: a paper); `received_at`, `acknowledged_at`, `first_response_at` (a person's reply only), `resolved_at`, `closed_at`; the legal due times (`ack_due_at`, `due_at`, `next_due_at`, and each rule's: `redress_due_at`, `nch_due_at`, `dpdp_due_at`, `it_due_at`), the breach flags and the 75 % warnings' times and flags; `reopened_count`, `complaint_copy_sent_at`, `resolution`, `spam_at`. History (simple_history) without the requester's details, the subject or the resolution. |
| `TicketMessage` | `direction` (in, out, note), `channel` (web, email, phone, whatsapp, sms, nch, panel), `author`, `automatic` (written by the site), `body`, `sent_at`; an email's `message_id` (unique: a message forwarded twice is kept once) and `headers` (threading, and the files not kept and why); a note's `mentions`; the `inbound_event` it came in. |
| `TicketAttachment` | a file of a message in the private storage (`support/<uuid>.<ext>`: never the customer's file name), its name, type, size and SHA-256; images, PDF and text only, 10 files of 10 MB each at most. |
| `SavedReply` | `title`, `language`, `body` with variables (`{name}`, `{order}`, `{refund_days}`, `{number}`; `{name\|there}` gives a fallback); deleting one puts it in a bin for 30 days. |

## The legal clocks

`clocks.clocks()` gives every clock that applies, each from the moment the complaint was received, in calendar time
in India, never paused (a ticket waiting on its customer keeps running), across month ends (31 January 14:00 is due 28
February 14:00, 29 February in a leap year; 31 March is due 30 April):

| Clock | Rule | Applies to | Due |
|---|---|---|---|
| ack | E-Commerce Rules 4(4) | every ticket | 48 hours |
| redress | E-Commerce Rules 4(5) | every complaint but a privacy request | one calendar month |
| nch | the National Consumer Helpline's convergence programme | a complaint NCH forwarded | 30 days |
| dpdp | SPDI Rules 5(9) before `STAFF_DPDP_RULES_FROM` (13 May 2027), DPDP Rules 14(3) from it | a privacy request | the earlier of a month and 90 days before; 90 days from |
| it_ack, it_resolve | IT Rules 3(2) | a grievance, while `SUPPORT_INTERMEDIARY_RULES` is on | 24 hours, 15 days |

The ticket stores the earliest of each kind (`ack_due_at` for acknowledging, `due_at` for resolving) and the next one
it runs on (`next_due_at`: the queue's order). An acknowledgement clock stops at the acknowledgement, the others at
the resolution; a reopened ticket's run on from where they were, so a reopening past its due time is a breach at
once. A new category or source sets them again from `received_at`. Every 15 minutes `tasks.watch_clocks` opens an
inbox item (`ticket_due`, for whoever handles tickets, its assignee's once assigned) at three quarters of a running
clock and flags a breach once at its due time (`support.clock_breached` in the audit log, a `ticket_breach` item);
a second run finds the flags and does nothing.

## Where tickets come from

- **The contact form** (`/api/v1/contact/`, the website's `/contact/`): `services.from_contact_form` makes a form
  ticket, linked to the account whose confirmed address sent it and to the order its text names when that order was
  placed with the same address. While `SUPPORT_COPY_TO_EMAIL` is on, the support address also gets the message, with
  Reply-To the sender (as before this app).
- **My requests** (`/api/v1/me/tickets/`): a signed-in customer with a confirmed email address asks from their
  account (10 an hour); the list shows their account's tickets and those sent from one of its confirmed addresses
  before, never staff's notes or who works on them.
- **Email**: the support address is forwarded to `POST /api/hooks/support-mail/` (an SES receipt rule's Lambda or
  Cloudflare's Email Routing worker), with the webhook token of the `support_mail` integration account in
  `X-Support-Mail-Token` (constant time; the previous token too for 24 hours after a rotation). The raw body is kept
  once per SHA-256 (`integrations.InboundEvent`) and read by `tasks.process_inbound_mail`. `mail.guard` drops our own
  mail coming back, auto-replies (RFC 3834's `Auto-Submitted`, `X-Autoreply` …), bounces and no-reply senders,
  lists and bulk mail, a message to more than 50 people and a sender flooding (20 an hour); the event says why.
  `mail.thread` finds the ticket: the thread id in the headers (it holds a secret, so naming it means having seen our
  email), a stored Message-ID, then the number in the subject only from the requester's own address. A reply to a
  closed ticket starts a follow-up ticket (a note says which); a ticket waiting on the customer is open again; a
  resolved one is reopened (counted).
- **Staff log the rest** (`POST support/tickets/`, the panel's "Log a call or message"): a phone call, a WhatsApp
  message, an NCH complaint with its docket, a letter or an email to a personal address; received when it was (never
  ahead, within a year), audited (`support.ticket_logged`).
- **Spam**: a ticket moved to spam is quarantined (no acknowledgement, out of the queue and of every number) and
  purged with its messages, files and raw mail after 30 days by the nightly task; the numbers purged are in the audit
  log (`support.spam_purged`), so the series' gaps are explained. Out of spam, it is acknowledged then.

## The acknowledgement

Sent by itself once the ticket is committed (`services.acknowledge`, under the ticket's row lock: once): by email
with the number, else by SMS when only a mobile number is known (`ticket_ack`, its DLT template
`MSG91_TEMPLATE_TICKET_ACK`; held between 21:00 and 08:00 and sent at 08:00). From `SUPPORT_COMPLAINT_COPY_FROM`
(1 January 2027) the email carries a copy of the complaint as recorded (`complaint_copy_sent_at`). Staff may send it
again (an address added) or record that it was given another way (on the call). Only a person's reply sets the first
response; a reply acknowledges a ticket not acknowledged yet. Every email goes through the site's email (SES, the
suppression list) with the number in the subject, Reply-To the support address and the threading headers
(`mail.headers_for`), so the customer's answer comes back to the same ticket.

## Statuses

| From | To |
|---|---|
| new | open, waiting on the customer, waiting on a third party, resolved, closed, spam |
| open | waiting on the customer, waiting on a third party, resolved, closed, spam |
| waiting on the customer, on a third party | open, the other waiting, resolved, closed, spam |
| resolved | closed (by staff, or by itself after 4 days without news); reopen/ takes it back to open |
| closed | nothing; reopen/ takes it back to open |
| spam | open |

Resolving or closing asks for the category, the resolution and what the category needs (`services.CLOSING`, the
ticket's `closing_fields`): the order of an order or payment ticket, the paper of a content error, the data request
of a privacy request; each missing one is a field error. A resolution past `due_at` is a breach.

## Actions from a ticket

Each keeps its own permission, is written on the ticket as an automatic note and audited (`support.action`), and works
on the requester's own orders (their account's, and a guest's placed with their address) within the person's scope:

- **Refund** (`staff.refund_order`): through the shop's refund action (`staff.approvals`' `order.refund`, the payload
  `order`, `amount`, `cancel`): within the person's `refund_inr` it runs (201), above it a change request waits for
  FINANCE (202). An order not shipped is cancelled and refunded in full; a shipped one by an amount or by its lines'
  copies, each from zero (the sidebar warns when the payment is older than Razorpay's 180 days).
- **Cancel** (`shop.change_order`): one paid online through its refund (as above), any other at once.
- **The invoice or the confirmation again** (`staff.handle_ticket`): the shop's own emails to the order's address.
- **Course access extended** (`learn.change_entitlement`): N days (1 to 365) from its end or from today, the reason
  kept on the entitlement.
- **A book code looked up** (`learn.view_bookcode`): by its digest, never kept nor logged; one line to answer with
  (its batch and subject, redeemed by this requester or by another account, never whose).
- **A data request started** (`staff.handle_data_request`) from a grievance or privacy ticket: `staff.DataRequest`
  with its own clocks from when the ticket came, linked both ways (the ticket in its `details`).

## Saved replies

`GET support/saved-replies/` (`support.view_savedreply`: SUPPORT and SALES read and insert them), the changes
`support.add_`, `change_`, `delete_savedreply` (ADMIN and the owners). A ticket's record carries them filled for it
(`saved_replies`), those in its language first: `{name}` the requester's first name, `{order}` the linked order,
`{refund_days}` the days Razorpay usually takes for its payment's method (UPI 2 to 7 working days, net banking 2 to
10, cards and EMI 5 to 10), `{number}` the ticket's. An unknown variable is refused when it is saved.

## Who sees what

| Permission | Risk | Who |
|---|---|---|
| `support.view_ticket` | low (a view) | SUPPORT, SALES (order, payment and school-order tickets), CONTENT_EDITOR (content errors), ADMIN, OWNER, AUDITOR |
| `staff.handle_ticket` | medium | SUPPORT, SALES (their tickets), ADMIN, OWNER |
| `support.note_ticket` | low | SUPPORT, SALES, CONTENT_EDITOR (notes only, on content errors), ADMIN, OWNER |
| `staff.export_grievances` | high (a re-authentication) | ADMIN, OWNER, AUDITOR |

The scope kind `ticket_category` (`accounts.roles.ROLE_SCOPES`) narrows SALES and CONTENT_EDITOR; a `StaffScope` row of
that kind narrows one person. Opening a ticket is a `sensitive_read` (of the account's record when there is one, a
child's said so), and so are revealing the requester's email address or mobile number (a reason, re-authenticated,
`staff_reveal`'s rate), downloading a file, and looking a person up by email or phone in the queue (the query's keyed
hash only). The audit log and the inbox name tickets by number and category, never the requester.

**The pages, by role** (for the per-role guides): SUPPORT works the queue (due soonest, mine, unassigned, overdue,
waiting, all), opens a ticket with the customer beside it, replies (saved replies a keystroke away in the customer's
language), notes and names colleagues, moves the status on, logs calls and NCH complaints, and refunds within ₹1,000
(above it, FINANCE approves in Approvals). SALES does the same for order, payment and school-order tickets. A content
editor reads the content errors and writes notes on them. ADMIN and the owners do everything, change the saved replies
and export the grievance register; the AUDITOR reads every ticket and exports the register, and writes nothing.
FINANCE sees no ticket: it approves the refunds asked from them.

## The grievance register

A job (`Job.Kind.GRIEVANCE_EXPORT`, `POST /api/v1/staff/jobs/` with `{"kind": "grievance_export", "params": {"from",
"until"}}`, the days received in India, both optional): a dated CSV
(`grievance-register-<from>-to-<until>-made-<day>.csv`) of each complaint's number, category, source, NCH docket,
received, acknowledge-by and acknowledged (hours taken, in time or not), first response, resolve-by and resolved (days
taken, in time or not), closed, status and reopenings; no personal data beyond the number and the category. Spam and
a test order's tickets are left out. Above the starter's `export_rows` it waits for an approver (`job.run`). The
break-glass fallback: `manage.py grievance_register --from YYYY-MM-DD --until YYYY-MM-DD > register.csv`.

## Erasure, test mode

When an account is erased (`accounts.DeletionRequest` done), `services.forget_requester` keeps its tickets' numbers,
categories, dates and clocks (the register) and removes what identifies the person: the requester's details, the
subject, the messages' text and files, the raw mail. A ticket about a test order (`Order.is_test` on a live site) is
left out of the queue (but with `test=true`), the summary and the register, and marked as such where it shows.

## Settings

`SUPPORT_COPY_TO_EMAIL`, `SUPPORT_COMPLAINT_COPY_FROM`, `SUPPORT_INTERMEDIARY_RULES` (also a panel setting, which
wins), `SUPPORT_MAIL_MAX_BYTES`, `MSG91_TEMPLATE_TICKET_ACK`, `API_THROTTLE_SUPPORT_MAIL`, `API_THROTTLE_SUPPORT_REQUEST`
(DEPLOYMENT.md). The requesters' details need `INTEGRATION_KEYS`: without them a server refuses to migrate
(`support.E001`, a database check, as `integrations.E001`). The mailbox needs the `support_mail` integration account
and the forwarder (RUNBOOK.md "Support").

## Not built yet

Customer satisfaction scores (CSAT: plan 5.14, later), WhatsApp messages in (logged by hand until the WhatsApp
Business API is connected), the help centre, and answering from the website ("My requests" lists and asks; the answers
come by email).
