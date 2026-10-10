# Admin (ADMIN)

Role guide. Written from `accounts/roles.py` and `staff/catalogue.py` at the merge of Phase B; the panel's People → Roles
page (`/people/roles/`) is the running truth. The index is [README.md](README.md).

## Who this is for

For the operations head: every module of the panel, and approving role changes, exports and erasures. You run the site
day to day and are the second person for what the owner or a colleague asks to change in people and data.

## What you can do

You hold every catalogued permission except the owners' own, money's approvals and the superusers' changes (below). In
words, by module:

- **Orders, Catalogue, Content, Course, Customers, Support, Reports:** everything the other roles do in them, each as
  its own guide describes, inside your limits. You alone import and export the products and categories (Catalogue →
  Import and export) and void a code or a print run of book codes (critical: you confirm it's you first).
- **Approvals (your checker's permissions):** you approve a privileged role or an invitation to one (OWNER, ADMIN,
  FINANCE, AUDITOR), a member of staff's lost second factor, an erasure, and any export or bulk action above its starter's
  limit (`job.run`, which carries the course's bulk access changes and the customers' bulk actions too). You never approve
  your own request.
- **People:** you see staff, their roles, scopes, access and last use of the risky permissions, and the role catalogue; you
  reset a second factor (a second person approves). Giving roles, ending someone's sessions and offboarding are the
  owners'.
- **Settings and connections:** the site's switches (shop open, cash on delivery, the parent's consent mode, maintenance
  mode and its banner), the ERPNext switches, the e-commerce disclosures; the connections (test, new keys, mode, circuit,
  webhook tokens, events and dead letters); the message templates and a test sent to yourself.
- **System:** the status lines, backups and restore drills (record one), dependencies, hardening, the checkout's scripts,
  logs and time; the ERPNext sync's dead letters and its switches.
- **Legal and privacy:** the compliance cockpit, data requests (including emailing a person their data and starting an
  erasure), the breach register, the processors and their tasks, legal holds, the dark-pattern self-audit, policy
  versions.
- **Fraud signals:** you acknowledge them (Django admin → Insights).

## What you cannot do, and who to ask

| You cannot | Who does it |
|---|---|
| Give roles, take them away, end a person's sessions or offboard (you see them) | an owner |
| Make or revoke an API key (you see them) | an owner |
| Approve refunds, offline payments, prices, coupons, offers or staff discounts above the makers' limits | FINANCE or an owner |
| Read or export the audit log | an owner, or the auditor |
| Override your own request when nobody else can approve | an owner (`staff.break_glass`) |
| Change the periodic tasks, groups and permissions, second factors or the Google sign-in apps (you may view them) | a break-glass session |
| Approve your own request | another ADMIN or an owner |

## Your limits

| What | Up to |
|---|---|
| A refund you make | ₹10,000 (above: FINANCE or an owner approves) |
| A payment recorded offline | ₹50,000 |
| A discount, on a price, coupon, offer or staff order | 50% |
| Rows in an export | 10,000 |
| Rows in a bulk action | 1,000 |

My account → "Your limits" shows them.

## How long you stay signed in

15 minutes without a request, and 8 hours after you sign in. You must hold a passkey or a security key.

## The pages you use

| Page | Path | What it is for |
|---|---|---|
| Home, Inbox, Approvals | `/`, `/inbox/`, `/approvals/` | your numbers and queues; what waits; what you approve |
| People, Roles, Access review | `/people/`, `/people/roles/`, `/people/access-review/` | who holds what, and when they last used it |
| Settings, Connections, Message templates | `/settings/`, `/settings/connections/`, `/settings/templates/` | switches, providers, DLT templates |
| System | `/system/` and its pages | health, backups and drills, the ERPNext sync, scripts, dependencies, hardening, logs |
| Compliance cockpit and registers | `/privacy/`, `/privacy/requests/`, `/privacy/incidents/`, `/privacy/processors/`, `/privacy/holds/`, `/privacy/disclosures/`, `/privacy/policies/`, `/privacy/retention/`, `/privacy/dark-pattern-audit/` | clocks, data requests, breaches, processors, holds, disclosures |
| Orders, Finance, Catalogue, Tax | `/orders/`, `/finance/`, `/catalogue/`, `/tax/` | as the guides of SALES, FINANCE and CONTENT_EDITOR describe |
| Content, Course, Customers, Support, Reports | `/content/`, `/course/`, `/users/`, `/support/`, `/reports/` | as the guides of CONTENT_EDITOR, SUPPORT and FINANCE describe |

## Your first day

1. Sign in at `https://admin.<domain>/sign-in/` with your work Google account, or with the email and password an owner
   gave you ([README.md](README.md) "Before a person's first day"); if the console says "Set up two-step sign-in first",
   follow its link, scan the QR code with an authenticator app and keep the ten recovery codes offline.
2. Add a passkey or a security key when the console asks for one.
3. Read and acknowledge each policy the console shows.
4. Open My account: your role, "Your limits" and where you are signed in.
5. Open the Inbox: approvals waiting for you, data requests near their clocks, dead letters, anything the system pages
   flag. Then the compliance cockpit (`/privacy/`), which shows every legal clock, the late ones first.
6. Open System once, so you know what "Good" looks like on each line.

## In RUNBOOK.md

"Staff accounts" (what you approve), "Data requests and privacy" (a data request, purging old orders, the retention tasks,
legal holds, the disclosures), "Connections", "Couriers and integrations", "ERPNext", "The system pages", "The inbox",
"Incidents", "Insights" (acknowledging a signal).
