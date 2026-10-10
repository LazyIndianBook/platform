# Package P13: Documentation of Phase B (model: Claude Sonnet 5.5)

No servers needed. Read COMMON.md sections 1, 2, 6 and 7 first. Your worktree is a checkout of the `phase-b`
integration branch with every Phase B module merged: Orders, Finance, Tax, Catalogue, Content, Course, Support,
Customers, Legal and privacy, Staff, Settings and connections, System, Home and Reports. Read
`examleaf-web/CHANGELOG.md`'s Phase B entries, every app README the modules wrote, API.md's Phase B sections and the
console's README before writing anything. Where a document and the code disagree, the code is right: fix the
document and name the disagreement in your report.

Plan section 9.2's documentation exit criteria are the deliverable:

1. **One-page guide per role** in `docs/guides/roles/<ROLE>.md` for OWNER, ADMIN, FINANCE, SALES, SALES_REP, PACKER,
   SUPPORT, CONTENT_EDITOR, REVIEWER, MARKETING, AUDITOR: who the role is for, what they can do (from
   `accounts/roles.py` and `staff/catalogue.py`: by module, in words), what they cannot do and who to ask (the
   approval table of `staff/README.md`), their limits (`ROLE_LIMITS`), their idle limit, the panel pages they use
   with the path of each, the first-day steps (sign in, two-step or a passkey, the policies, the inbox), and the
   RUNBOOK sections that concern them. One page each, plain sentences, no marketing. An index
   `docs/guides/roles/README.md` with a table of roles × modules. The language is English; the file layout ready for
   `as` and `bn` versions later (say so in the index).
2. **RUNBOOK.md**: every shell recipe that a panel action replaced is rewritten as the panel action (the page, the
   button, what it asks, what it writes to the audit log), keeping the shell as the break-glass fallback in a short
   "If the panel is down" line: staff onboarding and MFA reset, log everyone out, data requests by letter, the purge
   of 8-year-old orders, the consent-pending list, stuck payments, the test and live fix-up, regenerating an invoice,
   GSTR-1, reprocessing clips, printing book codes, axes unlock, and whatever else the modules replaced (grep the
   RUNBOOK for `manage.py shell` and `manage.py <command>` and check each against the panel). The "Contents" list
   kept in step. New sections for what Phase B added that an operator meets: the settlement fetch, support's inbound
   mail and the clocks, the retention tasks, the connections page, the script inventory alert, the restore drill
   record, the dark-pattern self-audit, the legal deposit reminder.
3. **The decisions register** `docs/decisions.md`: every decision of plan section 10.1 with its status (settled,
   built on the recommendation pending the owner, pending the CA, pending the lawyer), what the code does today
   (the setting or the default), and what changes when the answer comes (which setting, which page). The CA's
   questions on the document series prefixes and the bundle treatment, and the lawyer's on the National Consumer
   Helpline, the intermediary rules and the educational-institution question, each with the setting that carries
   the answer.
4. **README.md** (`examleaf-web/`), `docs/HANDOVER.md`'s section 2 table and section 3 (a new "What Phase B
   delivered" subsection in the style of section 3; leave sections 4 to 8 to the tech lead), `DEPLOYMENT.md`'s table
   (every new setting present once, with its default and whether required; the sections 21 to 24 pattern: add
   "25. Phase B settings by module" if the modules scattered theirs), `.env.example` in step with the table,
   `examleaf-admin/README.md` (routes, the contract section, the mock's cookies), `API.md`'s prose sections
   consistent in style and complete (every module's section present before the generated reference; the generated
   reference untouched).
5. **CHANGELOG.md**: a consolidated entry `## Phase B: the panel's own modules (9 October 2026)` at the top
   summarising every module in one paragraph each with the final test counts the tech lead gives you (ask for
   nothing: read them from the module entries and say "at merge" where a number is per module), keeping the module
   entries below it.
6. **The research index**: `docs/research/README.md` unchanged unless a report was added.

Rules: British English; sentences, not fragments; no emoji; file paths and commands in backticks; keep every existing
heading's anchor that other documents link to (grep for links before renaming a heading). Do not change code,
tests or fixtures; if you find a bug while reading, report it, do not fix it. Commit per document group with the
`Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` trailer. Your report: the files written or changed, the
disagreements between documents and code you found (file, line, what), and anything you could not resolve.

## Notes from the integration (the tech lead, 10 October 2026)

- Two codes reports exist and both stay: the Course module's `GET course/codes/report/` (`/course/report/`: printed,
  sold, activated, revoked and void by print run, for whoever reads the print runs) and the reports module's
  `GET reports/codes/` (`/reports/codes/`: the same by print run plus the districts the redemptions came from, for
  `staff.view_insights`). Say in `learn/README.md`, `insights/README.md` and the console README which is which, and
  that the reports' "sold" and "revoked" columns are filled now that the Course module records print runs and voids.
- The Customers page links the learner's page (`/course/learners/<id>/`) for whoever may read entitlements; the
  learner's page links back to the customer's record.
- The CHANGELOG's Phase B module entries are in merge order (Finance, ERPNext shadow, Home and reports, Catalogue,
  Course, Customers, Tax, Legal, Orders, Staff/settings/system, Content, Support); the consolidated entry goes above
  them in the plan's order (section 9.2).
- The console client's codes report functions: `getCodesReport` (reports) and `getCourseCodesReport` (course).
