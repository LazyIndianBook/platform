# Package P10: Customers (model: Claude Sonnet 5.5)

Ports: Django 8120, console 3040 (`E2E_API_PORT=8120 E2E_WEB_PORT=3040`). Read COMMON.md first. Your worktree is a
checkout of the `phase-b` integration branch, which already holds batch A: Support added `support.Ticket` (by
account); Legal and privacy added `ConsentRecord.channel`, `purpose`, the methods `adult_account`, `digilocker` and
`staff_manual` with `verified_by` and `evidence_ref`, and `accounts.LegalHold`; Orders added the orders staff API
(`/api/v1/staff/orders/`) with its lookup event; Staff/Settings/System edited `staff/api.py` (`UserViewSet` is there:
you do not edit that file; your endpoints go in `staff/customers_api.py`). Read `examleaf-web/CHANGELOG.md`'s Phase B
entries and API.md's Staff API section before building.

Plan rows: section 5.4 (every row marked **must** not already built), 5.0, section 7.9's ConsentRecord row.
Research: `research-lms-crm-cms.md` 3.1, `research-rbac-security.md` 5, `inventory.md` 7, 10.

## What exists (read before building)

`staff/api.py` `UserViewSet` (list with `q`, retrieve as a `sensitive_read`, reveal with a reason and a throttle,
suspend, unsuspend, unlock, resend-verification, end-sessions, password-reset, reset-mfa, impersonate),
`staff/serializers.py` (the customer serializers: masked), `staff/privacy.py` (masks), `staff/services.py` (the
account actions), `shop/admin.py` `customer_view` (the admin's customer page: what it shows), `accounts/models.py`
(User with `is_minor`, `consent_pending`, `pending_deletion`, `login_phone_verified`, TeacherProfile, ConsentRecord,
DeletionRequest; `send_parent_link`), `accounts/tasks.py` (`export_user_data`), `ops/models.py` SmsLog, `learn/models.py`
(Entitlement, Progress, Device), `staff/jobs.py` `bulk_action` (which actions it runs), the console's `/users/` pages
and `src/components/modules/users/`, RUNBOOK "Parental consent", "Logging in as a customer", "Phone numbers and
passkeys".

## Backend: `staff/customers_api.py`, mounted from `staff/urls.py` as `path("users/", include("staff.customers_api"))` placed before the router's `users` routes (so `users/<id>/timeline/` and the other new paths resolve first; verify the order in `staff/urls.py`)

1. **The merged timeline** `GET users/{id}/timeline/` (`accounts.view_user`; a `sensitive_read` like the record, with
   `child: true` when the account is a minor): one ordered list of orders (number, state, total), payments, code
   redemptions, a course-use summary (for a minor: chapters opened as a count and the last active week; for an adult
   the same plus clip completions by week), support tickets (number, status), emails and SMS sent (what the models
   record for the account: `SmsLog` by account where it keeps one, the order emails by order), consent events
   (ConsentRecord: event, method, version, channel), staff notes (`Note`), staff actions on the account (`AuditEvent`
   by target), each row `{at, kind, label, href}`; bounded (the newest 200, `?before=` for older); no query per row.
2. **Badges** on the list and the record (extend `staff/serializers.py`'s customer serializers in place, additively):
   email verified, phone verified, age band (under 13, 13 to 17, adult, unknown), parental consent state and method,
   teacher verification, MFA on, status (active, suspended, locked by axes, pending deletion, erased).
3. **The commerce summary** `GET users/{id}/commerce/` for adult buyers (orders, lifetime value, average order,
   refunds, RTOs from the shipping outcomes, addresses masked, the orders' tags); for a minor only the counts.
4. **Parental consent**: `GET users/consent-pending/` (children waiting for a parent, oldest first, with the link's
   expiry and the resends used; replaces the RUNBOOK shell recipe), `POST users/{id}/consent/verify/`
   (`staff.verify_consent`, new, high: SUPPORT, ADMIN; a method from `staff_manual` and the others Legal added, an
   `evidence_ref` required, a reason; writes the ConsentRecord with `verified_by`, clears `consent_pending`, audited),
   `POST users/{id}/consent/resend/` is the existing `resend-verification/` (link it).
5. **Account actions** exist; add `POST users/{id}/change-email/` (`staff.change_email`, new, high: a code sent to the
   new address, the old one told; the change completes when the customer confirms through allauth's email
   verification, never by staff alone) — the plan marks it should: build it only if the existing allauth flows make
   it a thin wrapper; otherwise leave it out and say so.
6. **Bulk operations** as jobs through `bulk_action` (add the actions suspend, unsuspend, end_sessions, resend_consent;
   never a deletion): a dry-run count first, row caps per role (`bulk_rows`), approval above them (exists), one audit
   event per row and one for the batch; a bulk action whose targets include a minor's account needs approval
   whatever the count (extend `approvals.bulk_rule` or the job's permission check).
7. **Tabs** on the list: `?kind=students|parents|guests`: students are accounts with a class level or a minor's age;
   parents are accounts that gave a parent's consent (`ConsentRecord.by_parent` through the parent link: find how the
   link records the parent) or hold an adult account linked to a child; guests are orders with `user=None`, listed
   from `shop.Order` by masked email with their order count (a separate serializer; still paged, still masked).
8. **The access log**: every lookup by name, email or phone in `users/?q=` writes one `customer.lookup` event with the
   query's keyed hash and the count (Orders did the same for its `q`: reuse the helper if Orders exported one, else
   add `staff.audit.lookup(request, query, count)` and use it in both places only if that is a one-line change in
   `shop/staff_orders.py`; otherwise add yours and note the duplicate for the tech lead).
9. No predictive lifetime value, RFM groups or churn scores on students (a rule: a test that the serializers carry no
   such field).

Permissions: `accounts.view_user` (exists), `staff.verify_consent` (new, high), `staff.reveal_contact` (exists for
the masked fields on the timeline and commerce pages), the bulk actions' own.

## Tests the exit criteria need

Every endpoint in the matrix; the timeline's `sensitive_read` and the minor's summary without a behaviour trail; the
commerce summary counts; the consent-pending list and a manual verification writing the record with its evidence and
clearing the flag; the bulk job's dry run, the caps and the minors' approval; the tabs; the lookup event with a hash;
query counts on the timeline and the list.

## Console

`/users/` gains the tabs (students, parents, guest buyers) and the badges in the row; `/users/[id]/` gains the
timeline, the commerce summary, the consent section with "verify by hand" (method, evidence reference, reason, a
confirm dialog), a minor's banner "Under 18: every view is logged", the bulk bar on the list with a dry-run count;
`/users/consent-pending/`. Mock fixtures for every state. Mock journey: list → a minor's record with the banner →
the timeline → verify consent by hand → the audit trail. Real journey (`real.spec.ts`, extending the existing
customer steps): the OWNER opens the seeded customer's timeline and the audit trail shows the logged view.

## Boundaries

Orders' pages, Support's tickets and the course's learner page exist: link to them. Do not edit `staff/api.py`;
extend `staff/serializers.py` additively.
