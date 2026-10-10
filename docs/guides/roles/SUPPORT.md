# Support (SUPPORT)

![For staff](../../assets/badges/audience-staff.svg) ![Component](../../assets/badges/component-console.svg) ![Phase B](../../assets/badges/phase-b-merged.svg)

The one-page guide for a member of staff who holds SUPPORT: what the role can and cannot do, its limits, the pages it
uses and its first day. It is written from `accounts/roles.py` and `staff/catalogue.py` at the merge of Phase B; the
panel's People → Roles page (`/people/roles/`) is the running truth, and the index of every role is
[README.md](README.md).

| Refund | Offline payment | Discount | Export | Bulk action | Signed out after | Second factor |
|---|---|---|---|---|---|---|
| ₹1,000 | ₹0 | 0% | 100 rows (no export permission yet) | 50 rows | 30 minutes idle, 8 hours in all | an authenticator app or a passkey |

## Who this is for

For support agents: customers (masked, revealed with a reason), account help, data requests, and refunds asked for. You
answer every complaint and question, and you help students, parents and teachers who are stuck.

## What you can do

- **Support** (`/support/`): every ticket, the queue by the next legal deadline (due soonest, mine, unassigned, overdue,
  waiting, all). Reply from the box (saved replies a keystroke away, in the customer's language), write notes that name
  colleagues, assign, move the status on and close with what the category asks for. Log a call, a WhatsApp message or a
  National Consumer Helpline complaint (`/support/new/`). From a ticket: refund an order inside your limit, cancel one, send
  the invoice or the confirmation again, extend course access, look up a book code, and start a data request.
- **Customers** (`/users/`): find a person (an email address exactly, a mobile number or its last digits, or three letters
  of a name; every search is recorded by a hash, never the words), open the record, its timeline and what they bought. A
  student under 18's record carries the banner "Under 18: every view is logged" and shows counts, not trails.
  Account help: unlock sign-in, sign them out everywhere, send a password reset link, send a parent's consent link again
  (a text only from 08:00 to 21:00; three links a day to one parent contact), record a parent's consent by hand (the
  method and where the evidence is, never the document), reset two-step sign-in (a second person approves), and sign in as
  the customer for 15 minutes with a reason and a ticket (never staff, never a student under 18; the owners are told).
  "Waiting for a parent" (`/users/consent-pending/`) lists the students whose parent has not confirmed.
- **Reveal:** a masked email address or mobile number is shown for 60 seconds, with a reason, after you confirm it's you
  (30 an hour); the reveal is logged.
- **Data requests** (`/privacy/requests/`): log a request that came by email, letter or phone (its clocks start from
  when it came), acknowledge it, record how the identity was checked, close it with the answer sent, and start an
  erasure (after its dry run); a second person approves the erasure. The compliance cockpit (`/privacy/`) shows every
  clock; you read the retention schedule, the processors and the legal holds.
- **Course** (`/course/`): give, extend and revoke access (one at a time or many with a dry run; a student's progress is
  never touched), look up a book code (one line, logged by its hash; 120 an hour), and open a learner's page from a
  ticket (logged; a child's is a summary). You read the print runs.
- **Orders** (`/orders/`) and **Finance** (`/finance/`): read orders, payments and refunds to answer "where is my
  parcel?" and "where is my refund?"; ask for a refund inside your limit, and for a return, and decide returns.
- **Elsewhere:** read the reported mistakes (Content) to answer "did you get my report?". In the Django admin, which your
  role may open: verify teachers and delete an email suppression so a student gets emails again.

## What you cannot do, and who to ask

| You cannot | Who does it |
|---|---|
| Approve a refund above ₹1,000 | FINANCE (or an owner) in Approvals |
| Approve an erasure or send a person their data by email | ADMIN or an owner |
| Suspend or reactivate an account | ADMIN or an owner |
| Approve a second-factor reset you asked for | another holder of that permission: SUPPORT, ADMIN or an owner |
| Receive and inspect a returned parcel | PACKER |
| Change settings, see staff, read the audit log, export the grievance register | ADMIN, an owner, the auditor |
| Change a price, a coupon, stock or the course's content | SALES, CONTENT_EDITOR |

## Your limits

| What | Up to |
|---|---|
| A refund you make | ₹1,000 (above: FINANCE or an owner approves) |
| Rows in a bulk action | 50 (the Customers list's bulk bar: sign out everywhere, send links again) |
| Rows in an export | 100 (your role holds no export permission yet) |
| Offline payments, discounts | none |

My account → "Your limits" shows them. A bulk action with a student under 18 among the accounts waits for a second person
whatever the number.

## How long you stay signed in

30 minutes without a request, and 8 hours after you sign in. An authenticator app or a passkey does.

## The pages you use

| Page | Path | What it is for |
|---|---|---|
| Support | `/support/`, `/support/tickets/<number>/`, `/support/new/`, `/support/replies/` | the queue, a ticket, logging a call, the saved replies (read) |
| Customers | `/users/`, `/users/<id>/`, `/users/<id>/timeline/`, `/users/consent-pending/` | a person, their history, the children waiting for a parent |
| Data requests, cockpit | `/privacy/requests/`, `/privacy/` | requests and every legal clock |
| Course | `/course/entitlements/`, `/course/codes/`, `/course/learners/<id>/` | access, a code looked up, a learner |
| Orders, Finance | `/orders/`, `/finance/payments/`, `/finance/refunds/` | an order, its payment and refund |
| Approvals, Inbox | `/approvals/`, `/inbox/` | refunds you asked for; tickets due, data requests, returns |

## Your first day

1. Sign in at `https://admin.<domain>/sign-in/` with your work Google account, or with your email address and the
   password you chose when you accepted the invitation ([README.md](README.md) "Before a person's first day"); if the
   console says "Set up two-step sign-in first", follow its link, scan the QR code with an authenticator app and keep
   the ten recovery codes offline.
2. Read and acknowledge each policy the console shows. What they say about children's data matters most to you.
3. Open My account: your role, "Your limits" and where you are signed in.
4. Open the Inbox and Home: the tickets due and breached, the data requests, the returns due in 48 hours.
5. Open one ticket with a colleague: the customer beside it, the deadlines (they never pause), the saved replies.
6. Look up a test customer: the search is recorded in the audit trail by a hash, with no name (the owners and the
   auditor read the trail; your role does not).

## In RUNBOOK.md

"Support" (all of it); "Data requests and privacy" ("A data request under the DPDP Act"); "SMS, phone numbers, passkeys
and parental consent" ("Finding a customer", "Logging in as a customer", "Phone numbers and passkeys", "Parental
consent"); "Email" ("Email bounces and complaints"); "The revision course" ("Granting access", "A lost code"); "The shop"
("A stuck payment", "I have not got my refund"); "The inbox".

## Related documents

- [Role guides](README.md): every role, who can do what by module, and the first day.
- [RUNBOOK.md](../../../examleaf-web/RUNBOOK.md): the procedures this page names.
- [The staff app](../../../examleaf-web/staff/README.md): the approvals, who asks and who approves.
- [Decisions register](../../decisions.md): the limits above are placeholders until the owner sets them.
- [The support app](../../../examleaf-web/support/README.md): tickets, the legal clocks and saved replies.
