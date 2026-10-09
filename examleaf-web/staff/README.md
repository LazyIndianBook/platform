# staff: the Admin Control Panel's backend

The rules behind every button of the panel (`../docs/examleaf-admin-control-panel-plan.md`, its research in
`../docs/research/2026-10-09-admin-control-panel/research-rbac-security.md`): who may do what to which objects, what
needs a second person, what was done by whom, and the registers the data-protection law asks for. The panel draws
what this API answers and decides nothing itself. The endpoints are in [API.md](../API.md) "Staff API".

| File | What |
|---|---|
| `../accounts/roles.py` | the roles (Django groups) and their permissions, `ROLE_LIMITS`, `ROLE_SCOPES`, `SOD_CONFLICTS`, `PRIVILEGED_ROLES`, `OWNER_ONLY`, `MONEY_APPROVALS`, `ADMIN_SITE_ROLES` |
| `apps.py` | the roles synced after every `migrate` (a post_migrate receiver) |
| `catalogue.py` | every permission's label, area, risk and what the risk triggers |
| `models.py` | `StaffPermissions` (the action permissions), `StaffScope`, `RoleGrant`, `AuditEvent` and `AuditHead`, `ChangeRequest` and `Approval`, `Job`, `InboxItem`, `SavedView`, `SiteSetting`, `FeatureFlag`, `ApiKey`, `Note`, `PolicyAcknowledgement`, `Impersonation`, `StaffInvite`, `DataRequest`, `Incident`, `ProcessorRecord`, `DarkPatternAudit` |
| `jobs.py` | background jobs from the panel: `start()`, `cancel()`, `run()` with its Progress, the runners (`audit_export`, `bulk_action`), the result file's signed link |
| `backends.py` | `scoped(queryset, user, perm)` and `ScopeBackend` (`user.has_perm(perm, obj)`) |
| `audit.py` | `record()`, the hash chains, `verify()`, `export_day()`, retention (`purge()`), `alert()` |
| `approvals.py` | maker-checker: `ask()`, `approve()`, `reject()`, `execute()`, the actions and their rules |
| `services.py` | roles, scopes, invitations, sessions, offboarding; the customers' account actions; impersonation |
| `privacy.py` | the data requests' clocks, the erasure's dry run and its holds, the processors' tasks, the answer's text with the contact block, the erasure ledger's hash, the masks |
| `compliance.py`, `privacy_api.py` | Legal and privacy: the cockpit's clocks and calendar; its staff API (`/api/v1/staff/privacy/`) |
| `config.py` | `site_setting()` and `feature_flag()`: the panel's switches over the environment's |
| `permissions.py` | `IsStaff`, `StaffPermission`, API keys (`ApiKeyAuthentication`), the per-staff throttle |
| `api.py`, `serializers.py`, `urls.py` | `/api/v1/staff/` |
| `middleware.py` | the staff's endpoints and the Django admin on the admin host only (404 elsewhere), `authz_fail` for every refusal of the staff's endpoints, refused webhooks to the inbox, a website session as a customer: its end, its limits, its requests audited |
| `signals.py` | the audit log and the inbox fed from the rest of the site |
| `tasks.py`, `management/commands/` | the beat tasks and `run_job`; `verify_audit_chain`, `purge_audit`, `staff_api_reference` (API.md's generated reference) |
| `tests/` | the authorization matrix and the rest (`pytest staff`) |

## The model

A request is allowed only if all of these hold (research 1.1); anything else is refused (deny by default):

1. **A member of staff** on the panel's session, active, with an authenticator app or a passkey (`StaffMFAMiddleware`
   sends the others to set one up), or an integration's **API key**. Never the app's JWT: it has no session, so no
   re-authentication and no idle limit.
2. **The permission** the endpoint names for the action (`StaffView.permissions`; an action not named is refused).
   Roles give permissions; the action permissions are `staff.<codename>` (`StaffPermissions.Meta.permissions`), next to
   Django's own `view_`, `add_`, `change_` and `delete_` of each model. GET always names a `view_` permission, but for
   two reads of the packing room's, `staff.book_parcel`: the courier's quote for an order and a parcel's label (the
   customer's address on it). The shipping app's and the insights' staff endpoints are on the same rules
   (`StaffAppView`, their own pages and filters).
3. **The object in scope** (`backends.py`): `scoped()` narrows every staff queryset, `ScopeBackend` answers
   `has_perm(perm, obj)` the same way. A person's `StaffScope` rows of a kind (subject, board and class, order status,
   warehouse, school, work queue) narrow them to those values; without any, a permission held only through scoped
   roles is narrowed to the roles' values (`ROLE_SCOPES`: a PACKER sees paid, packed and shipped orders); otherwise
   nothing narrows. Break-glass accounts (superusers) and API keys are not narrowed.
4. **The limits** (`ROLE_LIMITS`, the highest of a person's roles, `None` for none): above them the action becomes a
   `ChangeRequest` that waits for a second person.
5. **The conditions** the catalogue's risk sets: high and critical permissions need a log-in or re-authentication in
   the last 5 minutes (allauth's, `api.views.recently_authenticated`), which an API key never has; critical ones alert
   the owners.

Every refusal (403) is an `authz_fail` event; a step asked for (`reauthentication_required`, with allauth's `flows`;
a break-glass session's `break_glass_reason_required`) is not. Every error answer of the staff API has a `code` beside its `detail` (`api.coded`:
permission_denied, not_found, not_authenticated, throttled …; API.md "Staff API" lists them).

The roles (the plan's 4.1): STUDENT and TEACHER (no staff permissions), CONTENT_EDITOR, SALES, SUPPORT, ADMIN (as
before, each with the panel's own permissions added), and the panel's OWNER (the founder: every catalogued permission,
which is all but the changes the superusers' apps keep), FINANCE, PACKER (the packing queue only: the orders to pack,
their books, `staff.pack_order`, booking their parcels, the inbox), REVIEWER, MARKETING, AUDITOR (every `view_`
permission and the audit log, nothing that writes) and SALES_REP (school and phone orders, without refunds or
shipping). SALES no longer packs,
ships or refunds in the admin: packing, shipping and delivery (`staff.pack_order`, also the admin's three actions)
are PACKER's and ADMIN's, and SALES asks for refunds in the panel, where FINANCE approves those above the cap. ADMIN
has everything but the superusers' apps' changes, `OWNER_ONLY` (giving roles and making API keys, which ADMIN sees;
the override; the audit log) and `MONEY_APPROVALS`. Who approves: FINANCE money, ADMIN roles, staff second factors,
erasures and exports, REVIEWER content (it publishes), the owners anything. The newer roles do not open the Django
admin (its lists are not scoped): `ADMIN_SITE_ROLES` there, the staff API here.

**Break-glass.** The superuser flag is only on one or two sealed accounts outside Google sign-in (the Google sign-in
refuses them), for when nothing else works (research 1.6); the founder's daily account is an OWNER. A break-glass
account passes every check and has no limits; its log-in alerts the owners at once. Its session gives a reason before
anything else (`POST session/reason/`, once; the manifest's `break_glass.reason_required` until then, and every
other staff call `403 break_glass_reason_required`, a step like a re-authentication, not an `authz_fail`); the owners
get the reason. Every audit event of its sessions has `break_glass: true` and `details.break_glass_reason` (review
them within 24 hours: `audit/?break_glass=true`), and so does an owner's override of an approval. Its idle limit is
the shortest, and it ends `STAFF_BREAK_GLASS_HOURS` (2) after its log-in however busy
(`accounts.models.staff_session_limit`); its end alerts the owners too. The Django admin does not ask for the reason
(its tests run as superusers): give it in the panel first, in the same browser.

Separation of duties: `SOD_CONFLICTS` lists the roles one person may not hold (FINANCE and PACKER, MARKETING and
FINANCE, AUDITOR and every other); giving one through the panel is refused, and `sync_roles` (after every migrate,
and `bootstrap_roles`) warns about anyone who holds a pair (given in the admin). Per transaction: the approver is never
the maker, and never the person the change is about.

## Adding a permission

1. An action that is not a model's view/add/change/delete: a row in `catalogue.STAFF_ACTIONS` (codename, label, area,
   risk, approval, alert). It becomes `staff.<codename>` through `StaffPermissions.Meta.permissions`: run
   `manage.py makemigrations staff` (an AlterModelOptions); `migrate` then gives it to the roles.
   A permission of another app (an `export_` say) goes in `catalogue.OTHERS`. Django's own four verbs are catalogued
   by rule.
2. Give it to roles in `accounts/roles.py` (ADMIN and OWNER have it already, unless it joins `OWNER_ONLY` or
   `MONEY_APPROVALS`).
3. Name it on the endpoint: `permissions = {"action": "staff.codename"}`.
4. `pytest staff` checks that every permission a role or an endpoint names is catalogued and exists
   (`test_catalogue.py`, `test_matrix.py`); add the endpoint to `test_matrix.ENDPOINTS` (another app's staff endpoint:
   `APP_ENDPOINTS`, and its path to `middleware.STAFF_APIS`, which keeps it on the admin host, audits its refusals and
   puts it in API.md's generated reference).

## Adding a role

1. A constant and its list in `ROLES`; add it to `STAFF_ROLES` (members get `is_staff`), and, as fits,
   `PRIVILEGED_ROLES` (a second person approves it), `ADMIN_SITE_ROLES` (it opens the Django admin), `ROLE_LIMITS`,
   `ROLE_SCOPES`, `SOD_CONFLICTS`, and `STAFF_IDLE_TIMEOUTS` in settings.py for the 15-minute idle limit.
2. Nothing to migrate by hand: after every `migrate` the post_migrate receiver (`apps.py`) creates every app's
   permissions and syncs the roles (`bootstrap_roles` does the same by hand). No role sync in a migration: on a fresh
   database it would run before later apps' permissions exist.
3. A test of its permissions in `accounts/test_roles.py`; the matrix picks it up by itself.

## Approvals (maker-checker)

`approvals.ask(action, maker=…, target=…, payload=…, reason=…)` validates the payload, stores it with its SHA-256 and
applies the action's rule: within the maker's limits it is approved by the rule and run at once; otherwise it waits
(`pending`, an inbox item for those holding the checker's permission) until it is approved, rejected or expires
(`STAFF_CHANGE_REQUEST_HOURS`, 24). The checker sends back the hash of the payload they read (`payload_sha256`):
another payload is refused. `execute()` runs the stored payload, never one sent again, after checking its hash and the
action's preconditions (the order not shipped meanwhile, the price unchanged …), in one transaction; it fails rather
than do something else. Each step is an audit event `<action>.requested|approved|rejected|expired|executed|failed`
(`.overridden` for an owner's override), with the request's id. An `Idempotency-Key` answers the first request again.

| Action | Maker | Checker | Waits when |
|---|---|---|---|
| `order.refund` (`shop.services.refund_order`; with lines, shipping, restock, a method or a return: `refund_with_details`) | `staff.refund_order` | `staff.approve_refund` | above the maker's `refund_inr` |
| `order.offline_payment` (`record_offline_payment`) | `staff.record_offline_payment` | `staff.approve_payment` | above `offline_inr`, or a ₹0 order |
| `order.staff_discount` (a staff order: `shop.services.create_staff_order`, the order made only when it runs) | `shop.add_order` | `staff.approve_discount` | more off the books (after the offers) than `discount_percent`, or a ₹0 total |
| `product.price` | `shop.change_product` | `staff.approve_discount` | more off the MRP than `discount_percent` |
| `coupon.create` | `shop.add_coupon` | `staff.approve_discount` | beyond `discount_percent` (a fixed one: of its minimum order) |
| `staff.grant_role`, `staff.invite` | `staff.assign_role` | `staff.approve_role_change` | a privileged role, or a role for yourself |
| `user.reset_mfa` | `staff.reset_user_mfa` | the same (a customer's), `staff.approve_role_change` (staff) | always |
| `user.erase` (`DeletionRequest.complete`) | `staff.handle_data_request` | `staff.approve_erasure` | always (staff started it) |
| `job.run` (a job above its starter's limit: `jobs.start`) | `staff.view_job` (the job's own permission is checked first) | `staff.approve_export` | an export above `export_rows`, a bulk action above `bulk_rows` |

The checkers' permissions: `approve_refund`, `approve_payment` and `approve_discount` are FINANCE's (and the owners');
`approve_role_change`, `approve_erasure` and `approve_export` ADMIN's (and the owners'). `approvals.bulk_rule(maker,
rows)` is the rule for bulk actions above `bulk_rows`, for when they come. When nobody else can approve, an owner with
`staff.break_glass` approves their own request with `override` and a reason; the owners are told and the event is
marked `break_glass`. To add an action: a subclass of `approvals.Action` (`validate`, `rule`, `run`, the permissions)
in `ACTIONS`.

## The audit log

`audit.record(action, request=…, target=…, changes=…, details=…)` writes one `AuditEvent` in the caller's
transaction (an action rolled back leaves no event): time in UTC to the millisecond, the actor's id, type and roles
then, `on_behalf_of`, `break_glass`, the action, the permission exercised, the target's type, id and label (a number
or a code, never a person's details), the outcome, the reason, the change request, Caddy's `X-Request-ID`
(django-guid), the client
address, the browser (200 characters), a keyed hash of the session key, `changes` as `{field: [before, after]}` and
`details`, with personal values replaced by a keyed hash (comparable, not readable) and secrets by `[secret]`. The
flows it is fed from: staff log-ins (and the alert email), log-outs, failed log-ins and lock-outs of staff accounts,
role changes from anywhere, exports from the admin (`LoggedExportMixin`), refunds started and payments recorded
offline (whoever started them), impersonation, every refusal of the staff API, reveals and openings of a customer's
record (`sensitive_read`), and every action of the panel.

**Two chains.** Money events (`order.`, `payment.`, `refund.`, `product.price`, `coupon.`, `offer.`) chain apart from
the rest, so each can be kept for its own time. Each event stores `prev_hash`, the hash of the event before it in its
chain, and `hash = SHA-256(prev_hash || canonical JSON of its fields)`. `AuditHead`, one row locked while an event is
written, holds each chain's newest hash: writers queue on it until their transaction ends (fine at this volume; the
callers lock their own rows first and record last).

**Append-only.** On PostgreSQL migration `0002_audit_append_only` adds a trigger that refuses UPDATE, DELETE and
TRUNCATE of `staff_auditevent`. A DELETE or TRUNCATE passes only in a transaction that set
`examleaf.audit_maintenance = 'on'`, which only the retention purge does; an UPDATE never passes. Run the site as a
database role that does not own the table, with SELECT and INSERT on it only (DEPLOYMENT.md "Staff and the audit log"):
then the site cannot change the log even if it tried, and the owner role (the one migrations and the purge run as) is
the only way, whose DDL shows.

**Verified nightly.** `staff.tasks.verify_audit_chain` (02:00) and `manage.py verify_audit_chain` recompute both
chains: each event's hash, each link, the start (the genesis or a purge's anchor) and the end (the head). A break
records `audit.chain_broken`, files an inbox item and alerts the owners; an intact chain `audit.verified` (the system
page shows the latest).

**Copied off the server daily.** `staff.tasks.export_audit_log` (06:00) writes each UTC day not yet there to the
backups' bucket (`BACKUP_BUCKET`, the storage `upload_backup` uses) as `audit/YYYY/MM/YYYY-MM-DD.jsonl`: one event per
line with its hashes, the last line the chains' heads at the end of the day. A day already there is not written
again; give the bucket's `audit/` prefix an object lock (R2's bucket lock) so nothing there can be changed or deleted
for its retention. Each line verifies on its own: `audit.chain_hash(row["prev_hash"], row) == row["hash"]`.

**Retention.** The general chain is kept `STAFF_AUDIT_RETENTION_DAYS` (730: two years; never under 365: CERT-In's 180
days of logs and the DPDP Rules' year), the money chain `STAFF_AUDIT_MONEY_RETENTION_FY` financial years (8: the
current year and the eight before it, Companies Act s.128(5)). `manage.py purge_audit [--dry-run]` deletes each
chain's oldest events past their time, a whole prefix of the chain, and records `audit.purged` with the hash of the
last one gone, from which what stays still verifies. On PostgreSQL run it as the table's owner, monthly from the
host's crontab (as `scripts/backup.sh`), e.g.
`docker compose exec -e DATABASE_URL=postgres://examleaf_owner:…@db:5432/examleaf web python manage.py purge_audit`.

**Reading it.** AUDITOR and OWNER only (`staff.view_auditlog`, AU-9(4)); each read is itself an event (`audit.read`,
with the filters). The export (`staff.export_auditlog`) gives JSON lines with the hashes at once up to 5,000 rows
within the exporter's `export_rows`; more is a job (`jobs/`), approved first by ADMIN above `export_rows`, whose file
is linked to its starter for 5 minutes at a time and kept a week. Its filters are checked: an unknown or invalid one
is refused, so that an export never widens because of a typo.

**Alerts** (`audit.alert`, to `STAFF_ALERT_EMAILS`, else every active member of OWNER, not the sealed break-glass
accounts, once the transaction is committed): a break-glass log-in, a privileged role given or taken away, an owner's
override, an API key made, an impersonation started, maintenance mode switched on, an incident filed, a staff
lock-out, a staff member offboarded, a broken chain or a failed export.

## Sessions

A staff session (website, panel, admin) ends after its idle limit without a request, the shortest of the person's
roles' (plan 3.5: `STAFF_IDLE_TIMEOUTS`, 15 minutes for OWNER, ADMIN, FINANCE and PACKER; `STAFF_IDLE_TIMEOUT`,
1,800 seconds, for the others; a break-glass account's is the shortest), and 8 hours after its log-in (a break-glass
account's: 2), the absolute limit it is given (`accounts.models.staff_session_limit`). The manifest's
`idle_timeout_s` is the person's.

**Google Workspace** (`STAFF_GOOGLE_DOMAIN`, `accounts.adapter.SocialAccountAdapter.pre_social_login`; DEPLOYMENT.md
"Google sign-in for staff"): a staff Google sign-in (on the admin host, into a staff account, or by an account of
the domain) needs the ID token's `hd` to be the domain and its address confirmed, never reaches a break-glass account,
and makes an account only with `STAFF_GOOGLE_AUTO_STAFF` (a member of staff with no role); accounts are linked by
`sub`. A refusal is `authz_fail` and the console's `?error=staff_google_…`. allauth's second-factor stage follows
Google as any log-in.
`StaffMFAMiddleware` checks both before anything else; the time of the last request is written in the session at most
once a minute. An API call then gets `401 {"code": "session_idle"}` (or `"session_expired"`); the event is
`session_expired`. Every staff log-in sends the person an email with the time, the address and the browser. The panel
must not poll in the background, or an idle session never ends.

The manifest also carries `impersonating` (`{user_id, email (masked), until}` while the session's impersonation
token lasts, else null: the panel's banner) and `flags.test_mode` (true off production: `STAFF_TEST_MODE`, `DEBUG`'s
by default; absent on production: the panel's TEST band).

**The admin host.** With `ADMIN_HOSTS` set (the panel's host, `admin.examleaf.in`), everything under `/api/v1/staff/`,
the shipping app's staff endpoints (`/api/v1/shipping/shipments/` …, not the checkout's `shipping/` and
`shipping/quote/`), `/api/v1/insights/` and the Django admin (`/admin/`) answer 404 on any other host, signed in or
not, before any other check (`middleware.py`); empty, as in development, they answer on every host. Signed out, the
admin then sends to the console's `/sign-in/` (its session is the admin's: cookies are per host), not to the
website's. The admin host must also be in `ALLOWED_HOSTS`, and its `https://` origin in `CSRF_TRUSTED_ORIGINS`.

**The admin's refunds are the panel's.** The order's "Refund through Razorpay" action, and "Cancel" on an order paid
online (which is its refund), ask `approvals.ask("order.refund", …)`: within the maker's `refund_inr` they run at once,
above it a change request waits for FINANCE in the panel; each step is audited. Packing, shipping and delivery in the
admin need `staff.pack_order` (`shop/admin.py`).

## Notes and policies

**Notes** (`Note`, `notes/`): what staff keep on a record (an order, a customer, a parcel …), by the record's
`app_label.model` and id as the audit log names targets; a record's notes are listed pinned first (its timeline's).
`staff.view_note` and `staff.add_note` (every role of the panel; not PACKER), and only on a record the person may see:
its model's `view_` permission, in their scope (`scoped()`), else 404. The audit event `note.created` targets the
record and holds the note's number, never its body.

**Policy acknowledgements** (`PolicyAcknowledgement`, `policies/ack/`, research 6): each member of staff acknowledges
each version of the policies in `STAFF_POLICIES` (`{key: version}`) once; the manifest's `policies_due` lists what
they have not, and a new version asks everyone again. Their own by default; `?user=` someone else's with
`staff.view_staff`. Each acknowledgement is an audit event (`policy.acknowledged`).

## Jobs

Background work started from the panel (`jobs.py`, plan 3.6). `POST jobs/` with a `kind` and its `params` checks the
kind's own permission, the single action's (`staff.export_auditlog` for `audit_export`; the action's maker permission
for `bulk_action`), counts the rows, stores the `Job` and queues `staff.tasks.run_job`; above the starter's limit
(`export_rows`, `bulk_rows`) a change request `job.run` waits for ADMIN first (its payload shows the filters or the
targets). `run()` calls the kind's runner with a Progress, which counts the rows, keeps each failed row's error
(`{id, label, message}`, the first 1,000), saves them at most once a second and stops at the next row once the job is
cancelled. A bulk action runs each target as its own request through `approvals.ask` (its permission, scope, limits
and approval; an idempotency key per job and target, so a task run twice does nothing twice); `dry_run` validates each
row and changes nothing. An export's file goes to the private storage (`staff/jobs/<id>/`), linked to its starter only
by `result_url` (signed for 5 minutes; a bucket's own signed link behind it) and deleted after a week by the nightly
`expire_access`. Every step is an audit event (`job.requested`, `job.started`, `job.done`, `job.failed`,
`job.cancelled`, `job.stopped`, `job.result_downloaded`). To add a kind: a `Job.Kind`, its permission in
`jobs.permission`, its limit in `jobs.LIMITS`, its runner in `jobs.RUNNERS` and its params in
`serializers.JobStartSerializer`. The ERPNext sync (`erp/README.md`) adds the kind `erp_initial_load`
(`erp.run_initial_load`, the `bulk_rows` limit) and two kinds of inbox item: `sync_failed` (a dead letter) and
`reconciliation` (a night's differences). The tax desk (`shop/README.md` "Tax") adds the kind `gstr1_export`
(`staff.run_gstr1`, the `export_rows` limit; `{"month": "YYYY-MM", "months": 1 or 3}`, its file the GSTR-1 CSVs
zipped) and two kinds of inbox item: `tax_threshold` (a turnover line crossed, or a count grown) and
`credit_note_missing` (a refund past the credit notes' cut-off, or against a cancelled invoice).
The Orders module (`shop/order_jobs.py`, `shop/README.md`) adds
`orders_pack` and `orders_print` (`staff.pack_order`), `orders_cancel` (`shop.change_order`, 250 orders at most) and
`orders_export` (`shop.export_order`, the `export_rows` limit; the others `bulk_rows`), with `targets` (order numbers)
or `filters` (the list's, never a search) as their params, and three kinds of inbox item: `order_hold` (an order held:
`shop.change_order`), `return_request` (due in 48 hours: `staff.handle_return`) and `bank_refund` (a transfer to make,
due in `SHOP_BANK_REFUND_DAYS`: `staff.approve_refund`).

## Data protection

- **Data requests** (`DataRequest`): access, correction, erasure, nomination, grievance, complaint, by any channel,
  acknowledged within `STAFF_DATA_REQUEST_ACK_HOURS` (48, the E-Commerce Rules) and answered within a month (the SPDI
  and E-Commerce Rules), from `STAFF_DPDP_RULES_FROM` (13 May 2027) within `STAFF_DPDP_RESPONSE_DAYS` (90, DPDP r.14(3));
  a grievance or complaint keeps the month (the strictest clock that applies). The answer's text carries the contact
  block (`DATA_PROTECTION_OFFICER`). An access request's data goes by email to the account's own address, never to
  staff. An erasure is dry-run first (`privacy.erasure_report`: what goes, what stays and why, what stops it: an order
  on its way, a refund under way, an unverified requester, a child without the parent's confirmation, a member of
  staff) and approved by a second person.
- **The breach register** (`Incident`): the CERT-In clock (6 hours) and the Board's detailed report (72 hours) from
  detection, the reports' times and references, the notices to the people affected, children affected, actions,
  closure. A new one alerts the owners and opens an inbox item due at the nearest clock.
- **The processor register** (`ProcessorRecord`): who processes what, where, under which contract.
- **Personal data is masked** in the staff API (an email as `ra•••@example.com`, a phone as `••••••2345`); revealing it
  needs `staff.reveal_contact`, a reason and a re-authentication, is limited (`STAFF_THROTTLE_REVEAL`, 30 an hour) and
  is a `sensitive_read` event; so is opening a customer's record, with `child: true` for a student under 18.
- **Logging in as a customer** (research 2.7): `users/<id>/impersonate/` gives a token valid 15 minutes, never for
  staff or a student under 18, with a reason and a ticket, logged at its start and end, alerted; its `Impersonation`
  row binds it to the member of staff and to the panel's session it was asked from. The website's account API takes
  it once (`/api/v1/account/impersonate/`, `services.accept_impersonation`): a new session as the customer (not
  their log-in: no signal, their last log-in unchanged), marked `impersonating_staff_id`, `impersonation_until`,
  `impersonation_reason`, ending at `until`, when either side ends it (`DELETE` there, `…/impersonate/end/` here), or
  once that panel session no longer holds the member of staff (`middleware.py`: `401 impersonation_ended`). While it
  lasts, payments, passwords, email, second factors, consent, addresses and deletion are refused (`403
  impersonating`), `auth/session`'s user carries `impersonation` (the website's banner, `accounts.adapter.
  HeadlessAdapter`), the customer's device list names it "Staff (support) until …", and `audit.record` takes the
  member of staff for the actor and the customer for `on_behalf_of`, with one `impersonation.request` event per
  request.

## Legal and privacy

The panel's Legal and privacy module (plan 5.15; `privacy_api.py`, API.md "Legal and privacy (staff)") on top of the
registers above. What each part does, and the rule it keeps:

- **The cockpit** (`compliance.py`, `GET privacy/cockpit/`, `staff.view_datarequest`): every clock the Indian rules
  start, as rows with the record behind each, the overdue first: a data request's 48 hours and month (90 days from
  13 May 2027), a breach's 6 and 72 hours, a complaint's 48 hours, month and NCH 30 days (the support app's tickets,
  read lazily: the cockpit says when it is not installed), a parent's consent awaited, a child's deletion waiting for
  the parent, the year's dark-pattern self-audit; the consents counted by the privacy notice's version; the legal
  calendar (1 January and 13 May 2027, the self-audit's 1 December and 1 January, the quarterly access review, the
  restore drill: the system module's `RestoreDrill` when it is there). Numbers and codes only.
- **Legal holds** (`accounts.LegalHold`, `privacy/holds/`; `staff.manage_holds`, new and high: FINANCE, ADMIN, OWNER;
  `accounts.view_legalhold`: SUPPORT and AUDITOR read): an account, or one record (an order, an invoice, a credit note,
  a payment, a refund, a data request), held for a dispute, a chargeback, a claim or an investigation, until a day or
  until released (with a reason). A hold on the account stops its erasure; a hold on a record keeps it from the
  retention clean-up; both are lines of the erasure's dry run.
- **The erasure obeys its holds** (`privacy.erasure_holds`, `DeletionRequest.complete`): the dry run (`erasure_report`)
  lists each kept part with its `line`, "kept until 31 March 2035: 1 invoice of 2026-27 with the order behind it, for
  GST and the Companies Act": the books by financial year (`examleaf.retention.books_until`: 8 financial years after,
  or 72 months after the annual return's due date, whichever is later), a year of processing logs (the audit log's
  events naming the account by number, the SMS log's rows kept without the account or the last digits), the legal
  holds, the intermediary rule's 180 days for the registration details when `SUPPORT_INTERMEDIARY_RULES` is on, the
  consents. A legal hold on the account and a child without the parent's confirmation are `blocks`, and `complete()`
  raises `DeletionRequest.Held` for them (the nightly purge leaves such a deletion waiting, with an inbox item). A
  child's parent confirms through their own signed link (`/c/<token>/`, `POST parent-consent/<token>/ {"confirm":
  "deletion"}`: `parent_confirmed_at`), or staff record it with the evidence's reference
  (`privacy/deletions/<id>/parent-confirmation/`).
- **The erasure ledger**: a done `DeletionRequest` keeps a keyed hash of the address erased (`subject_hash`), copied to
  the backups' bucket at once (`erasures/<id>.json`; `accounts.tasks.copy_erasure_ledger`, and nightly for any missed).
  After a restore, `manage.py reapply_erasures` erases again every account the ledger names whose address still hashes
  to it (an id taken by someone else since is never touched; `--dry-run`, `--ledger`, `--export`). RUNBOOK.md has the
  step.
- **Processors' tasks**: the processor register says which processor keeps personal data (`holds_personal_data`),
  which holds marketing lists (`holds_marketing_data`) and what to ask of it (`erasure_action`). Each erasure done opens
  an inbox item (`processor_task`, for `staff.manage_compliance`: OWNER, ADMIN) per processor that keeps personal data;
  each marketing consent withdrawn (`POST /api/v1/me/consent/withdraw/`), one per processor that holds marketing lists.
  The answer to a person (`response_text`, the erasure's confirmation email, the access export's email) carries the
  contact block (the DPDP contact person, the Grievance Officer, the legal name and address) and, for access, who
  processes the data (s.11(1)(b)).
- **The retention schedule** (`examleaf/retention.py`, `privacy/retention/`): one table of each kind of record's least
  time in law (and the day it changes), what the site keeps and who deletes it. The nightly `ops.tasks.trim_expired`
  and `purge_expired` act on the rows that name a model: the SMS log's last digits blanked at 90 days and its rows gone
  after a year, Razorpay's webhook records and the tasks' results after 7 days, the app's phones silent for 90 days, and
  the orders past their books' period (their customer's details forgotten, the documents' PDFs deleted, a held one
  left as it is).
- **Policy versions** (`pages/versions.py`, `privacy/policies/`; `pages.view_page`, `pages.change_page`): each publish of
  a legal page is a numbered version with the day it is in force from and a line on what changed; one published for a
  later day waits in `Page.scheduled` until `pages.tasks.publish_due` (just after midnight) puts it in force; a diff of
  each against the one before. Consent rows keep the version they were given under.
- **The e-commerce disclosures** (`privacy/disclosures/`; the site settings of the group `disclosures`:
  `staff.manage_settings`): the legal name and the addresses, customer care, the Grievance Officer, the nodal contact,
  the page of the return terms, the DPDP contact person (`DATA_PROTECTION_OFFICER`), CERT-In's point of contact (never
  on the website), the published text on rights requests, the National Consumer Helpline membership. Saved together
  with one reason, each a `setting.changed` event; the website shows them from `config/`.
- **The dark-pattern self-audit** (`DarkPatternAudit`, `privacy/dark-pattern-audits/`; `staff.manage_compliance`, new
  and high: OWNER, ADMIN; `staff.view_darkpatternaudit`: AUDITOR reads): once a year a finding and a fix for each of the
  CCPA's 13 patterns, the certificate's text and its signed copy; completed once, then unchanged; shown on the website
  from its `effective_from`. `staff.tasks.remind_dark_pattern_audit` opens one inbox item a year from 1 December.
- **Nominees** (`accounts.Nominee`): the person's own `GET/PUT/DELETE /api/v1/me/nominee/`; staff read it on
  `privacy/nominees/<user>/` (`accounts.view_user`, a `sensitive_read`), the contact masked and revealed with a reason
  (`staff.reveal_contact`). The claim's flow (proving it) is Phase C's.
- **Children** (the rule for every module): an account under 18 is never marketed to, whatever any consent says, and
  one of unknown age only on a verified consent: every marketing send, segment, ad audience or export goes through
  `accounts.audiences.marketable(queryset, channel)` (exported for Phase D's Marketing; nothing sends marketing yet).
  Every staff view of a child's record is a `sensitive_read` event with `child: true`: opening a customer
  (`users/<id>/`), revealing a detail, reading a nominee; a module that adds a lookup of a person or a view of their
  record writes the same event with the same flag.
- **The consent ledger** is append-only in practice: no endpoint changes or deletes a `ConsentRecord`, the admin reads
  them, and only the erasure blanks their address hash. Consents carry their `channel` (marketing's email, SMS or
  WhatsApp), the parental methods of Rule 10 (`adult_account`, `digilocker`, `staff_manual`), `verified_by` and
  `evidence_ref` (where the evidence is, never the document).

What each role finds there: SUPPORT the cockpit's clocks, the requests, the holds (to read) and a child's deletion
confirmed by phone; FINANCE the holds (to put and release: chargebacks and disputes over money); CONTENT_EDITOR the
policy versions (to publish); ADMIN and OWNER everything, with the self-audit and the processors' tasks; AUDITOR reads
everything.

## The jobs

| When (India time) | Task |
|---|---|
| 00:01 | `pages.tasks.publish_due`: a legal page's version published for that day put in force |
| 02:00 | `staff.tasks.verify_audit_chain` |
| 03:05 | `accounts.tasks.copy_erasure_ledger`: the erasure ledger's lines not yet in the backups' bucket |
| 03:15 | `staff.tasks.expire_access`: roles given until a time, scopes past their time, change requests expired |
| 04:10, 04:20 | `ops.tasks.trim_expired` and `purge_expired`: the retention schedule's clean-up |
| 06:00 | `staff.tasks.export_audit_log`: the last 7 UTC days not yet in the bucket |
| 07:00 | `staff.tasks.remind_dark_pattern_audit`: from 1 December, the coming year's self-audit (once a year) |
| every hour (:05) | `staff.tasks.expire_change_requests` |
| every hour (:35) | `staff.tasks.watch`: refunds Razorpay refused, filed in the inbox (and done once refunded) |

## Not built yet

The panel itself (Next.js); the orders, catalogue, content and course modules' own endpoints (their permissions are
in the catalogue: `staff.publish_paper` waits for the content module); bulk actions beyond the change requests' (a
bulk job runs those: refunds, offline payments, prices, coupons); replaying a Razorpay webhook from its body (the
site keeps only the event's id and hash: `system/reconcile/` asks Razorpay again instead); ERPNext's role sync; the
Django admin's own step for a break-glass session's reason; the website's page that posts an impersonation token, and
its banner (examleaf-frontend); notes in a data request's access export, and their edits; holding the panel shut
until the policies due are acknowledged (the manifest says which; the console decides).
