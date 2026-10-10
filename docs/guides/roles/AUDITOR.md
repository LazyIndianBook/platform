# Auditor (AUDITOR)

Role guide. Written from `accounts/roles.py` and `staff/catalogue.py` at the merge of Phase B; the panel's People → Roles
page (`/people/roles/`) is the running truth. The index is [README.md](README.md).

## Who this is for

For an accountant or a lawyer who reviews: everything read-only, the audit log and its export. Your role may be given
until a date (People → Grant a role has an end date), and it then ends by itself.

## What you can do

- **Read every module:** orders, finance, the tax documents and series, the catalogue, content, the course, support
  tickets, customers, the compliance cockpit and its registers (data requests, incidents, processors, legal holds, the
  retention schedule, the disclosures, policy versions, the dark-pattern self-audit), people and their roles, a person's
  access with the last use of the risky permissions, the quarterly access review, the API keys (never their secrets), the
  settings and each switch's history, the connections' cards, the message templates and the system's pages. Every read of
  a customer's record is logged as a `sensitive_read`, a child's marked, and personal details stay masked.
- **Audit trail** (`/audit/`): read it, newest first, filtered by who did it, the start of the action's name, the type
  and id of the record it was about, the change request, the outcome, or "Break-glass only". Each read of the log is
  itself an event (`audit.read`, with your filters).
- **Export:** the audit log as a file (up to 5,000 rows at once; more is a background job that an ADMIN approves first),
  any report as a file, and the grievance register (a dated CSV of numbers and categories, no personal data).
- **Review break-glass sessions:** within 24 hours of one, filter the log for break-glass events and read what it did.
- **Reports** (`/reports/`): every report, read only.

## What you cannot do, and who to ask

| You cannot | Who does it |
|---|---|
| Change anything: no approval, no edit, no reveal of a masked contact, no sign-in as a customer | the role that does it; ask an owner or ADMIN |
| Hold any other role as well | separation of duties: the panel refuses |
| Approve a bigger export | ADMIN (`staff.approve_export`) |
| Give or end your own access | an owner |

## Your limits

| What | Up to |
|---|---|
| Rows in an export | 5,000 (above: ADMIN approves) |
| Refunds, offline payments, discounts, bulk actions | none (0) |

My account → "Your limits" shows them.

## How long you stay signed in

30 minutes without a request, and 8 hours after you sign in. An authenticator app or a passkey does.

## The pages you use

| Page | Path | What it is for |
|---|---|---|
| Audit trail | `/audit/` | the log, filtered; the export |
| People, Roles, Access review | `/people/`, `/people/roles/`, `/people/access-review/` | who holds what, last log-ins, unused permissions |
| Compliance cockpit and registers | `/privacy/` and its pages | the clocks, requests, incidents, holds, retention |
| System | `/system/` and its pages | health, backups and drills, dependencies, hardening, scripts, logs |
| Settings, Connections, API keys | `/settings/`, `/settings/connections/`, `/settings/api-keys/` | switches and their history, providers, keys |
| Reports | `/reports/` and its tabs | the numbers, and files of them |
| Every other module | `/orders/`, `/finance/`, `/tax/`, `/catalogue/`, `/content/`, `/course/`, `/users/`, `/support/` | read only |

## Your first day

1. Sign in at `https://admin.<domain>/sign-in/` with your work Google account, or with the email and password an owner
   gave you ([README.md](README.md) "Before a person's first day"); if the console says "Set up two-step sign-in first",
   follow its link, scan the QR code with an authenticator app and keep the ten recovery codes offline.
2. Read and acknowledge each policy the console shows.
3. Open My account: your role (and the date it ends, if it does) and where you are signed in.
4. Open the Audit trail and tick "Break-glass only": that is the review the RUNBOOK asks for within 24 hours of any
   break-glass session.
5. Open People → Access review: the quarterly review of who holds what and what they have not used in 90 days.

## In RUNBOOK.md

"Staff accounts" ("Break-glass accounts": the 24-hour review), "The system pages", "Data requests and privacy" ("The
retention tasks"), "The inbox", and any section for a module you review.
