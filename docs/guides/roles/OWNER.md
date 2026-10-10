# Owner (OWNER)

![For staff](../../assets/badges/audience-staff.svg) ![Component](../../assets/badges/component-console.svg) ![Phase B](../../assets/badges/phase-b-merged.svg)

The one-page guide for a member of staff who holds OWNER: what the role can and cannot do, its limits, the pages it
uses and its first day. It is written from `accounts/roles.py` and `staff/catalogue.py` at the merge of Phase B; the
panel's People → Roles page (`/people/roles/`) is the running truth, and the index of every role is
[README.md](README.md).

| Refund | Offline payment | Discount | Export | Bulk action | Signed out after | Second factor |
|---|---|---|---|---|---|---|
| no limit | no limit | no limit | no limit | no limit | 15 minutes idle, 8 hours in all | a passkey or a security key |

## Who this is for

For the founder: everything, including giving roles, making API keys, the audit log and the override when nobody else can
approve. Your daily account is an OWNER, not a superuser: the superuser flag is only on the one or two sealed
break-glass accounts that sign in without Google, for the days when nothing else works.

## What you can do

You hold every catalogued permission, with no refund, payment, discount, export or bulk limit. In words, by module:

- **Orders, Finance, Catalogue, Tax, Content, Course, Customers, Support, Reports:** everything the other roles do in
  them, each as its own guide describes. You refund and record payments yourself, change prices, publish papers, make a
  print run of book codes, void a code or a whole run, reveal a customer's masked contact (with a reason), sign in as a
  customer for 15 minutes (never as staff or a student under 18) and export reports.
- **Approvals:** you approve money above the makers' limits (refunds, offline payments, prices, coupons, offers, staff
  discounts) as FINANCE does, and roles for a privileged role, a staff member's lost second factor, erasures, exports and
  bulk jobs as ADMIN does. You never approve your own request, with one exception below.
- **Override:** when nobody else can approve (a team of one), you may approve your own request with a reason
  (`staff.break_glass`). The other owners are emailed, the event is marked break-glass, and it is reviewed within 24 hours.
- **People:** invite staff, give and take away roles (a role for yourself, or OWNER, ADMIN, FINANCE or AUDITOR for
  anyone, waits for a second person), set scopes, end a person's sessions, reset a second factor, offboard and tick the
  steps of a departure. Make and revoke API keys (critical: you confirm it's you first).
- **Audit trail:** read and export it (OWNER and AUDITOR only); each read is itself logged.
- **Settings and connections:** the shop open or closed, cash on delivery, the parent's consent mode, maintenance mode
  and its banner, the ERPNext switches, the disclosures; the connections (keys tested before they are kept, mode,
  circuit, webhook tokens); the message templates DLT registers.
- **System and Legal and privacy:** backups and restore drills, dependencies, hardening, the checkout's scripts, logs;
  the compliance cockpit, data requests and erasures, the breach register, the processor register, legal holds, policy
  versions and the dark-pattern self-audit.
- **What reaches you:** an email at once for a break-glass sign-in, a privileged role given or taken away, an API key
  made, a customer signed in as, maintenance mode on, an incident filed, a staff lock-out or offboarding, a connection's
  keys, mode or circuit changed, a broken audit chain or a failed export; and on Mondays two emails, 08:00 the week's
  staff discounts, offline payments and ₹0 orders by who gave them, 08:30 the week's high-risk events.

## What you cannot do, and who to ask

| You cannot | Who does it |
|---|---|
| Change the periodic tasks, groups and permissions, second factors or the Google sign-in apps (you may view them) | a break-glass session, in the Django admin |
| Approve your own request | another owner (or ADMIN for roles and exports, FINANCE for money); alone, only the override |
| Give yourself a role without a second person | another owner or ADMIN approves it in Approvals |
| Change another owner's access | only an owner; a break-glass account's, only a break-glass account |
| Sign in as a member of staff or a student under 18 | nobody: the panel refuses |

## Your limits

None: a refund, an offline payment, a discount, an export and a bulk action of any size go through at once. The
approvals that need a second person do not come from a number but from the action (a privileged role, a second factor, an
erasure, the override).

## How long you stay signed in

15 minutes without a request, and 8 hours after you sign in. You must hold a passkey or a security key; the panel
stays closed until you add one.

## The pages you use

| Page | Path | What it is for |
|---|---|---|
| Home | `/` | your numbers (net revenue, orders, codes redeemed, active learners) and every queue |
| Inbox, Approvals | `/inbox/`, `/approvals/` | what waits, and what others ask you to approve |
| Audit trail | `/audit/` | who did what, filtered and exported |
| People, Roles, Access review | `/people/`, `/people/roles/`, `/people/access-review/` | invitations, roles, sessions, offboarding, the quarterly review |
| API keys | `/settings/api-keys/` | keys for integrations |
| Settings, Connections, Message templates | `/settings/`, `/settings/connections/`, `/settings/templates/` | switches with their history, the providers, the DLT templates |
| System | `/system/` and its pages | health, backups, the ERPNext sync, scripts, logs |
| Compliance cockpit and its registers | `/privacy/` | every legal clock, data requests, incidents, holds, disclosures |
| The business modules | `/orders/`, `/finance/`, `/catalogue/`, `/tax/`, `/content/`, `/course/`, `/users/`, `/support/`, `/reports/` | as each role's guide describes |

## Your first day

1. Sign in at `https://admin.<domain>/sign-in/` with the account the break-glass session made for you
   ([README.md](README.md) "Before a person's first day"), then set up the authenticator app on the website's page the
   console links to, and keep the ten recovery codes offline.
2. Add a passkey or a security key when the console asks for one (it asks before anything else opens).
3. Read and acknowledge each policy the console shows.
4. Open My account: check your roles, "Your limits" (none) and where you are signed in.
5. Open the Inbox, then Home. Check People → Access review and the System page's lines once, so you know what "good"
   looks like.
6. Make sure the owners' alert emails reach you (`STAFF_ALERT_EMAILS`, or every active OWNER).

## In RUNBOOK.md

"Staff accounts" (invitations, a lost second factor, leaving, ending sessions, break-glass accounts), "Secrets and key
rotation", "Connections", "The system pages", "The inbox", "Incidents", "Data requests and privacy", "ERPNext", and the
shop sections for the money you approve.

## Related documents

- [Role guides](README.md): every role, who can do what by module, and the first day.
- [RUNBOOK.md](../../../examleaf-web/RUNBOOK.md): the procedures this page names.
- [The staff app](../../../examleaf-web/staff/README.md): the approvals, who asks and who approves.
- [Decisions register](../../decisions.md): the other roles' limits are placeholders until you set them.
- [Handover](../../HANDOVER.md): where the work stands and the decisions only the owner can take.
