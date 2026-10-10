# Role guides

One page for each role of the Admin Control Panel: who it is for, what it can do and cannot do, its limits, the pages it
uses, its first day and the parts of [RUNBOOK.md](../../../examleaf-web/RUNBOOK.md) that concern it. They are written
from the code, not from memory: `examleaf-web/accounts/roles.py` (the roles, `ROLE_CARDS`, `ROLE_LIMITS`,
`ROLE_SCOPES`, `SOD_CONFLICTS`), `examleaf-web/staff/catalogue.py` (what each permission is, its risk) and the console's
modules (`examleaf-admin/src/lib/modules.ts`). The panel's own page, People → Roles (`/people/roles/`), draws the same
facts from the running system. If a page here and the panel differ, the panel is right: tell the person who keeps these
guides.

| Role | Page | For |
|---|---|---|
| Owner | [OWNER.md](OWNER.md) | the founder |
| Admin | [ADMIN.md](ADMIN.md) | the operations head |
| Finance | [FINANCE.md](FINANCE.md) | the accountant |
| Sales | [SALES.md](SALES.md) | sales and school orders |
| Sales representative | [SALES_REP.md](SALES_REP.md) | phone and school orders, quotations |
| Packer | [PACKER.md](PACKER.md) | the packing room |
| Support | [SUPPORT.md](SUPPORT.md) | support agents |
| Content editor | [CONTENT_EDITOR.md](CONTENT_EDITOR.md) | authors and editors |
| Reviewer | [REVIEWER.md](REVIEWER.md) | senior editors |
| Marketing | [MARKETING.md](MARKETING.md) | coupons, offers and the insights |
| Auditor | [AUDITOR.md](AUDITOR.md) | an accountant or lawyer who reviews |

STUDENT and TEACHER are customers, not staff, and have no guide here. The plan's INTEGRATION role is an API key with the
permissions it names (People → API keys), not a person.

## Who can do what, by module

The columns are the console's modules (`https://admin.<domain>`, the sidebar). "Acts" means the role can change things
there, inside its limits; "Reads" means lists and records only; "Part" means a named part of the module, which the
role's page spells out; a dash means the module is not drawn for the role.

| Module | OWNER | ADMIN | FINANCE | SALES | SALES_REP | PACKER | SUPPORT | CONTENT_EDITOR | REVIEWER | MARKETING | AUDITOR |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Home and Inbox | Acts | Acts | Acts | Acts | Acts | Acts | Acts | Acts | Acts | Acts | Reads |
| Approvals | Acts | Acts | Acts | Acts | Acts | - | Acts | Acts | Acts | Acts | Reads |
| Orders | Acts | Acts | Part | Acts | Part | Part | Part | - | - | - | Reads |
| Finance | Acts | Acts | Acts | Part | - | - | Reads | - | - | - | Reads |
| Catalogue | Acts | Acts | Part | Acts | Reads | Reads | Reads | Part | - | Part | Reads |
| Tax | Acts | Acts | Acts | Part | - | - | - | Part | - | - | Reads |
| Content | Acts | Acts | - | Part | Part | - | Part | Acts | Acts | - | Reads |
| Course | Acts | Acts | - | Part | - | - | Acts | Acts | Part | - | Reads |
| Customers | Acts | Acts | Reads | - | - | - | Acts | - | - | - | Reads |
| Support | Acts | Acts | - | Part | - | - | Acts | Part | - | - | Reads |
| Legal and privacy | Acts | Acts | Part | - | - | - | Part | Part | - | - | Reads |
| Reports | Acts | Acts | Acts | Part | - | - | - | - | - | Part | Reads |
| People, Roles, Access review | Acts | Part | - | - | - | - | - | - | - | - | Reads |
| API keys | Acts | Reads | - | - | - | - | - | - | - | - | Reads |
| Settings | Acts | Acts | - | - | - | - | - | - | - | - | Reads |
| Connections | Acts | Acts | Reads | - | - | - | - | - | - | - | Reads |
| Message templates | Acts | Acts | - | - | - | - | - | - | - | Reads | Reads |
| System | Acts | Acts | - | - | - | - | - | - | - | - | Reads |
| Audit trail | Reads | - | - | - | - | - | - | - | - | - | Reads |
| In ERPNext (GST returns, Inventory, Purchases, CRM) | Links | Links | Links | - | - | - | - | - | - | - | Links |

Notes on the cells. The Audit trail is read and exported, never changed, and each read is itself logged; only OWNER and
AUDITOR hold it. AUDITOR's "Reads" includes exporting a report, the audit log and the grievance register as files. SALES
makes and cancels payment links in Finance, and SUPPORT only reads them. SALES and CONTENT_EDITOR see Tax only as the HSN
and SAC master (to pick a product's code); SALES and SALES_REP see Content only as the books' list. MARKETING's reports
are the forecasts and cohorts, because the others need data its role does not hold. The console's Shipping, Marketing
and Partners entries are drawn for the roles that will use them and say they come in a later phase.

## Where each guide gets its facts

- **What a role can do**: the lists in `ROLES` (`accounts/roles.py`), read by module, with each permission's label and
  risk from `staff/catalogue.py`. OWNER holds every catalogued permission and ADMIN every one but the owners' own and
  money's approvals; both are computed, not listed.
- **What it cannot do, and who to ask**: the permissions it lacks, and the approval table of
  [staff/README.md](../../../examleaf-web/staff/README.md) "Approvals (maker-checker)": who asks, who approves and when
  the answer waits.
- **Limits**: `ROLE_LIMITS` (a person holds the highest of their roles' limits; none listed means 0). The numbers are
  placeholders until the owner sets them (the decisions register, [decisions.md](../../decisions.md)). A person sees
  their own under My account → "Your limits".
- **Idle limit**: `STAFF_IDLE_TIMEOUTS` in `examleaf-web/examleaf/settings.py`: 15 minutes for OWNER, ADMIN, FINANCE and
  PACKER, 30 minutes (`STAFF_IDLE_TIMEOUT`) for the rest, and 8 hours after sign-in for everyone.
- **Pages**: `examleaf-admin/src/lib/modules.ts` (which permission opens a module) and the console README's "Routes".

## Before a person's first day

An owner invites the person (People → "Invite a staff member": their work email address, the role and the reason; for
OWNER, ADMIN, FINANCE or AUDITOR a second person approves first). **The invitation email's link does not work yet:** it
points at a page, `/invite/<token>/` on the panel's host, that neither the console nor the website has, so a person
cannot accept an invitation by themselves. Until it is built, the role is given another way
([RUNBOOK.md](../../../examleaf-web/RUNBOOK.md) "Staff accounts", step 1): with Google for staff on and
`STAFF_GOOGLE_AUTO_STAFF=1` the person signs in once with their work Google account and an owner then grants the role
(People → the person → Access → "Grant a role"); otherwise a break-glass session makes the account in the Django admin
and gives the role. Either way the person then starts at the guide's "Your first day".

Separation of duties decides which roles one person may hold: FINANCE never with PACKER, MARKETING never with FINANCE,
and AUDITOR with no other role. The panel refuses a grant that breaks it.

## Language and the other languages

These guides are in English. The role cards in `accounts/roles.py` (`ROLE_CARDS`) already take a language key
(`en`, `as`, `bn`), and the console's words are objects of one shape so that Assamese and Bengali join them. The same is
ready for the guides: a translation keeps this layout, with the same file name in a folder named for the language:

```text
docs/guides/roles/README.md          this index, in English
docs/guides/roles/OWNER.md ...       the eleven guides, in English
docs/guides/roles/as/OWNER.md ...    Assamese, when written (the same eleven file names)
docs/guides/roles/bn/OWNER.md ...    Bengali, when written
```

Every guide uses the same headings in the same order, and keeps permission names, paths, button labels and audit event
names exactly as the panel shows them (those are in English until the console is translated), so a translator changes
the sentences and nothing else. The index would gain a row of links per language.

## Keeping them true

A guide is wrong the day a role's list in `accounts/roles.py`, a limit in `ROLE_LIMITS` or a module's permission in
`modules.ts` changes. When one does, change the guide in the same pull request. The facts above each guide's table are
quick to check against People → Roles.
