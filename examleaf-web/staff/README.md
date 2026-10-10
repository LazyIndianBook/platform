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
| `models.py` | `StaffPermissions` (the action permissions), `StaffScope`, `RoleGrant`, `AuditEvent` and `AuditHead`, `ChangeRequest` and `Approval`, `Job`, `InboxItem`, `SavedView`, `SiteSetting`, `FeatureFlag`, `ApiKey`, `Note`, `PolicyAcknowledgement`, `Impersonation`, `StaffInvite`, `DataRequest`, `Incident`, `ProcessorRecord`, `DarkPatternAudit`; Phase B's `StaffOffboarding` and `OffboardingStep`, `RestoreDrill`, `ScriptInventory` |
| `jobs.py` | background jobs from the panel: `start()`, `cancel()`, `run()` with its Progress, the runners (`audit_export`, `bulk_action`), the result file's signed link |
| `backends.py` | `scoped(queryset, user, perm)` and `ScopeBackend` (`user.has_perm(perm, obj)`) |
| `audit.py` | `record()`, the hash chains, `verify()`, `export_day()`, retention (`purge()`), `alert()` |
| `approvals.py` | maker-checker: `ask()`, `approve()`, `reject()`, `execute()`, the actions and their rules |
| `privacy.py` | the data requests' clocks, the erasure's dry run and its holds, the processors' tasks, the answer's text with the contact block, the erasure ledger's hash, the masks |
| `compliance.py`, `privacy_api.py` | Legal and privacy: the cockpit's clocks and calendar; its staff API (`/api/v1/staff/privacy/`) |
| `customers.py`, `customers_api.py` | Customers: the list's tabs, the merged timeline, the spending summary, the children waiting for a parent, a parent's consent recorded by hand, the bulk actions on accounts; its endpoints (`users/…`, `CustomerViewSet`, which is `api.UserViewSet` with the module's paths added) |
| `services.py` | roles, scopes, invitations, sessions, offboarding; the customers' account actions; impersonation; the role catalogue, a person's access, a role change's preview, the ERPNext mirror, one's own sessions, the offboarding checklist |
| `config.py` | `site_setting()` and `feature_flag()`: the panel's switches over the environment's |
| `permissions.py` | `IsStaff`, `StaffPermission`, API keys (`ApiKeyAuthentication`), the per-staff throttle |
| `api.py`, `serializers.py`, `urls.py` | `/api/v1/staff/` |
| `system_api.py` | the system pages under `system/`: the status lines, the sync monitor, backups and drills, logs and time, dependencies, hardening, scripts |
| `middleware.py` | the staff's endpoints and the Django admin on the admin host only (404 elsewhere), `authz_fail` for every refusal of the staff's endpoints, refused webhooks to the inbox, a website session as a customer: its end, its limits, its requests audited |
| `signals.py` | the audit log and the inbox fed from the rest of the site |
| `tasks.py`, `management/commands/` | the beat tasks and `run_job`; `verify_audit_chain`, `purge_audit`, `staff_api_reference` (API.md's generated reference), `load_dependency_report` (CI's report into the private storage) |
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
   warehouse, school, work queue, ticket category) narrow them to those values; without any, a permission held only
   through scoped roles is narrowed to the roles' values (`ROLE_SCOPES`: a PACKER sees paid, packed and shipped
   orders; SALES the order, payment and school-order tickets; a content editor the content-error tickets); otherwise
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
Asked from a request (the panel, the admin), an action whose maker's permission is high or critical needs a log-in or
re-authentication in the last 5 minutes (`approvals.step_up`), whichever endpoint asks: cancelling an order paid online
is its refund, and steps up as one. A job whose rows ask for an action as their starter (`shop.order_jobs.ASKS`: a
bulk cancellation's refunds) steps it up when it starts; its dry run does not.

| Action | Maker | Checker | Waits when |
|---|---|---|---|
| `order.refund` (`shop.services.refund_order`; with lines, shipping, restock, a method or a return: `refund_with_details`) | `staff.refund_order` | `staff.approve_refund` | above the maker's `refund_inr` |
| `order.offline_payment` (`record_offline_payment`) | `staff.record_offline_payment` | `staff.approve_payment` | above `offline_inr`, or a ₹0 order |
| `order.staff_discount` (a staff order: `shop.services.create_staff_order`, the order made only when it runs) | `shop.add_order` | `staff.approve_discount` | more off the books (after the offers) than `discount_percent`, or a ₹0 total |
| `product.price` (a selling price, and the MRP with it when given; a new product's price below its MRP) | `staff.change_price` (Phase B: SALES; was `shop.change_product`) | `staff.approve_discount` | more off the MRP than `discount_percent`, whichever of the two moved |
| `coupon.create` | `shop.add_coupon` | `staff.approve_discount` | beyond `discount_percent` (a fixed one: of its minimum order) |
| `coupon.change` (its terms, never its code) | `shop.change_coupon` | `staff.approve_discount` | the discount made deeper (or the coupon switched back on) beyond `discount_percent` |
| `offer.create` | `shop.add_offer` | `staff.approve_discount` | beyond `discount_percent` |
| `offer.change` | `shop.change_offer` | `staff.approve_discount` | the discount made deeper (or the offer switched back on) beyond `discount_percent` |
| `staff.grant_role`, `staff.invite` | `staff.assign_role` | `staff.approve_role_change` | a privileged role, or a role for yourself |
| `user.reset_mfa` | `staff.reset_user_mfa` | the same (a customer's), `staff.approve_role_change` (staff) | always |
| `user.erase` (`DeletionRequest.complete`) | `staff.handle_data_request` | `staff.approve_erasure` | always (staff started it) |
| `user.suspend`, `user.unsuspend`, `user.end_sessions`, `user.resend_consent` (`customers.py`; named by a `bulk_action` job only, never by `change-requests/`) | `staff.suspend_user` (the first two), `staff.end_user_sessions`, `staff.resend_verification` | the job's: `staff.approve_export` (a row has no approval of its own) | the job above its starter's `bulk_rows`, or with a student under 18's account among its targets, however few |
| `job.run` (a job above its starter's limit: `jobs.start`) | `staff.view_job` (the job's own permission is checked first) | `staff.approve_export` | above the kind's own limit (`jobs.LIMITS`): an export's `export_rows` (the grievance register's too), a bulk action's `bulk_rows` |
| `entitlement.grant`, `entitlement.extend`, `entitlement.revoke` (`learn/approvals.py`: `learn.course.grant`, `extend`, `revoke`) | `learn.add_entitlement`; `learn.change_entitlement` | `staff.approve_export` | never on their own: they are the course's bulk actions, and the job waits above `bulk_rows` (`job.run`) |
| `item_metadata` (`learn.course.set_metadata`: topic, marks, difficulty, Bloom level, tags added and taken off) | `learn.change_quizitem` | `staff.approve_export` | as above |

The checkers' permissions: `approve_refund`, `approve_payment` and `approve_discount` are FINANCE's (and the owners');
`approve_role_change`, `approve_erasure` and `approve_export` ADMIN's (and the owners'). `approvals.bulk_rule(maker,
rows, minors=0)` is the rule for bulk actions: above `bulk_rows`, and whatever the count when a student under 18's
account is among the rows (`Action.children(targets)` counts them; the customers' actions do). When nobody else can approve, an owner with
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
above it a change request waits for FINANCE in the panel; each step is audited. Like the panel's, they need a
re-authentication in the last 5 minutes (made in the console: the admin shares its session), else nothing is refunded
and the admin says why. Packing, shipping and delivery in the admin need `staff.pack_order` (`shop/admin.py`).

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
`serializers.JobStartSerializer`. The customers' account actions (`user.suspend`, `user.unsuspend`, `user.end_sessions`, `user.resend_consent`: "Phase B:
customers") are `bulk_action`s, not a kind of their own.
The ERPNext sync (`erp/README.md`) adds the kind `erp_initial_load`
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
The content module (`content/README.md`) adds the kind `content_import`
(`staff.import_content`, high; no row limit and no approver: its own dry run comes first, and an apply names it) and
three kinds of inbox item, each narrowed to its subject (`data.subject`): `review` (a draft waiting for a reviewer),
`error_report` (a reported mistake to triage) and `legal_deposit` (a book's copies due at the libraries).
Support (`support/README.md`) adds the kind `grievance_export`
(`staff.export_grievances`, high; the `export_rows` limit; params `from` and `until`, the days received), the scope
kind `ticket_category`, three kinds of inbox item (`ticket_due`: a ticket's legal clock three quarters gone,
`ticket_breach`: past it, both for `staff.handle_ticket` and given to the ticket's assignee; `ticket_mention`: a
colleague named in a note, assigned to them and done once they open the ticket) and the permissions
`staff.handle_ticket` (medium) and `support.note_ticket`.
Finance (`shop/README.md` "Finance") adds the kind `settlement_fetch` (`staff.reconcile_settlements`, medium; no row
limit: one day; params `{"day": "YYYY-MM-DD"}`, from 2020 to today; its result the counts), the permission
`staff.reconcile_settlements` (area Payments; FINANCE, with ADMIN and the owners) and two kinds of inbox item, both for
`staff.reconcile_settlements`: `settlement` (a Razorpay settlement that does not match: done once it matches) and
`b2b_payment` (a B2B invoice paid by link: done once its ERPNext entry is recorded).
Home and Reports (`insights/README.md`) adds the kind `report_export` (`staff.export_report`, high: FINANCE, the auditor,
ADMIN and the owners; the `export_rows` limit; params `{"report": "sales", "filters": {...}}`, validated by
`insights.exports.clean_params` before anything is queued; the starter needs the report's own permissions too), its file
a CSV with the filters and the member of staff's number at the end.
The Catalogue module (`shop/catalogue_jobs.py`, `shop/README.md` "Catalogue") adds the kinds `coupon_codes`
(`shop.add_couponcode`, the `bulk_rows` limit; `{"coupon", "count", "prefix", "note"}`, its file the school's CSV),
`product_import` (`shop.import_product`, high; no row limit: its dry run comes first, started by
`catalogue/import/`, and its apply names it, the same bytes within 24 hours) and `product_export`
(`shop.export_product`, the `export_rows` limit; the list's `filters`), and the permissions `staff.change_price`,
`staff.set_stock` and `staff.change_product_tax` (each medium): a product's prices, stock and tax each their own.
The Course module (`learn/README.md`) adds the kind `code_batch` (`staff.make_book_codes`, high, the owners alerted;
no row limit and no approver: `count` codes of one print run, `{"batch": <id>}` to make again a run whose job failed;
its file, the codes once, is its starter's for 24 hours: `KEEP_FILES`, then `learn.tasks.purge_code_files` deletes
it), the bulk actions above, one kind of inbox item, `fraud_signal` (a fraud rule's signal on book codes or orders,
for `staff.acknowledge_signal`, closed when the signal is acknowledged), the `review` kind's reuse for a revision
waiting (for `staff.publish_course`) and `failed_job`'s for a clip that failed or a scheduled publish that waits, and
the permissions `staff.publish_course` (medium), `staff.make_book_codes` (high) and `staff.void_book_codes`
(critical).

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
## Phase B: people, sessions and the system

The People, Settings and System modules' backend (plan 5.17, 5.18 and 5.19; research-rbac-security 1.8, 2.9, 3.5,
4.8 and 7). The endpoints are in API.md "Staff API"; the connections and the templates have their own READMEs
(`../integrations/README.md` "The connections page", `../ops/README.md`).

**The role catalogue** (`services.role_catalogue`, `people/roles/`): each role's two lines (`accounts/roles.py`
`ROLE_CARDS`, English now; Assamese and Bengali join under the same keys), its capabilities grouped by the catalogue's
areas with their risk, its limits, scopes, conflicts (`SOD_CONFLICTS`), the ERPNext role profiles it maps to
(`services.ERP_ROLE_PROFILES`), whether it needs a passkey, its idle limit and its active members.

**A person's access** (`services.access`, `people/<id>/access/`): their roles with who gave them, when, why and until
when (a role given in the Django admin has no `RoleGrant`: `source` admin), scopes, limits, idle limit, every
permission by area with the last use of each high or critical one (`AuditEvent.permission`, a year back at most:
`LAST_USE_DAYS`), the open change requests about or by them, their second factors and whether they owe a passkey.
**A role change previewed** (`services.preview_role_change`, `roles/preview/`) changes nothing: what the person would
gain and lose by area, the limits, scopes and idle limit before and after, the conflicts (`blocked`: the grant would be
refused), the approval it needs and its checker, the passkey to come and the ERPNext profiles. **The ERPNext tab**
(`services.erp_mirror`, `people/<id>/erp/`) says which role profiles their ERPNext user should have; ERPNext's role
sync is not built, so they are applied by hand there (`erp_in_use`: the sync is on).

**Offboarding as a checklist** (`StaffOffboarding`, `OffboardingStep`; `services.OFFBOARDING_STEPS`). `offboard()`
records what the panel did at once (deactivated, sessions ended, refresh tokens blacklisted, roles and scopes removed,
temporary grants cancelled, pending requests withdrawn, tickets unassigned, API keys revoked: each with its count) and
what an owner ticks by hand (`people/<id>/offboarding/tick/`, `staff.assign_role`, re-authenticated: the ERPNext user
disabled, the external accounts closed, the security keys collected, their last 90 days of the audit log reviewed),
done or not needed with a note (`offboarding.ticked`, audited with the steps left). An `offboarding` inbox item
counts the steps left and closes with the last one; a step put back to do opens it again.

**Passkeys** (`STAFF_PASSKEY_ROLES`: OWNER, ADMIN, FINANCE; `examleaf/middleware.needs_passkey`): a member of those roles without a
passkey or security key gets `403 passkey_required` from every staff call but the manifest, `catalogue/` and their own
sessions (`permissions.PasskeyRequired`; the manifest's `steps`), and the Django admin sends them to the website's
`/account/security/` (`examleaf/middleware.py`). A break-glass account is exempt (its keys are its own). **One's own
sessions** (`people/me/sessions/`, any member of staff): each with its browser and system read from the user agent,
the address cut short, when it started and was last seen; one ended, or every other one with the app's refresh tokens.
Adding, removing or resetting a second factor (allauth's signals, `signals.py`) offers that once, for 7 days
(`offer_end_sessions`).

**Settings**: each `config.Spec` has a `group` (the page's sections); `settings/<key>/history/` and
`flags/<KEY>/history/` list every value; a known switch (the ERPNext ones, `config.KNOWN_FLAGS`) takes true or false
only, and null puts it back to the environment's.

**The system pages** (`system_api.py`, mounted under `system/`): `system/`'s `status` lines (health, queues, webhooks,
email, SMS, backups, the audit chain, the sync, dependencies, hardening, scripts, logs), each with when it came to its
state; the sync monitor (`erp.view_sync`) and a link search; the backups (`BACKUP_SOURCES`: each prefix's newest object
in the backups bucket with its size and the SHA-256 of its `.sha256` sidecar, which `upload_backup` now writes;
`BACKUP_STALE_HOURS`) and the restore drills (`RestoreDrill`, recorded with `staff.manage_system`); the log inventory
(`../examleaf/logs.py`, a table in code: a new log is a new row there) against CERT-In's 180 days and the DPDP Rules'
year, the clock compared with the database's and `LOG_TIME_SOURCE`; CI's dependency report
(`../scripts/dependency_report.py` in the `dependency-audit` job, loaded by `manage.py load_dependency_report`:
advisories by severity, a critical one due in 7 days, stale after 8); the admin host's hardening (each check `ok`, or
null where it cannot be tested from here, with its fix); the checkout's and the console's sign-in's scripts
(`ScriptInventory`, PCI DSS 6.4.3 and 11.6.1).

**New inbox kinds and their targets** (the console opens each where it is dealt with): `role_expired` (`staff.person`,
the person's Access tab), `offboarding` (`staff.offboarding`, their Offboarding tab), `webhook_silent`
(`integrations.connection`, the connection's page), `template_idle` and `template_certify` (`ops.messagetemplate`),
`backup_stale` and `dependencies_stale` (`system`, the backups and dependencies pages), `scripts_changed`
(`staff.scriptinventory`, the scripts page).

**What each role sees.** OWNER: everything here, the passkey first, the offboarding ticks. ADMIN: the catalogue, a
person's access and previews, the connections and templates (changing them), the system pages and the drills; the
passkey first. FINANCE: the connections' cards read-only (the payment settings), the sync monitor; the passkey first.
AUDITOR: every page read-only. MARKETING: the templates read-only. Everyone: their own sessions.

## Phase B: customers

The Customers module's backend (plan 5.4; research-lms-crm-cms 3.1, research-rbac-security 5). `customers.py` holds the
rules, `customers_api.py` the endpoints (`CustomerViewSet`: `api.UserViewSet`, which stays as it was, with the module's
paths added; `urls.py` mounts it as `users/` in place of the router's registration, the URL names `staff:user-*`
unchanged) and `serializers.py` the badges. The endpoints are in API.md "Customers (staff)"; the console's pages are
`/users/`, `/users/<id>/`, `/users/<id>/timeline/` and `/users/consent-pending/`.

**What a read leaves in the log.** Opening a record, its timeline and its spending summary are each one
`sensitive_read` event (`details.what`: `record`, `timeline`, `commerce`; `details.child`: true for a student under 18),
as a reveal is, with its reason. A search for a person by name, email address or mobile number (`users/?q=`, the guest
buyers' too, and the Orders list's) is one `customer.lookup` event: `kind` (email, phone, name), the query's keyed hash
(`audit.lookup`, one helper for every list that takes a person in its search box), how many it found and `list`; never
the words. Fewer than three letters finds nobody and is no lookup; browsing the tabs is none. Personal data is in no
event's details, label or error: accounts are named by their number, orders by theirs, a consent's evidence by where it
is (a ticket's number), never what it says.

**The tabs** (`?kind=`). *Students*: accounts with a class level, or under 18 by their date of birth. *Parents*: adult
accounts whose verified email address or verified log-in number is the parent contact a student named. A parent's
consent is recorded on the child's account (`ConsentRecord.by_parent`, through the link sent to that contact), and most
parents have no account, so this tab finds those who have one; it is a lookup, not proof of parenthood, and the console
says so. *Guest buyers*: orders without an account, one row for each email address (lower case) with the number of its
orders and the newest one; another row shape (`CustomerGuest`), masked as everywhere, readable by whoever may read orders
(an order of an account holder is no guest's). A test-mode order is in none of them on a live site.

**Badges** (on the list's rows and the record, no query per row; the page's lock-outs come in one): `email_verified`,
`login_phone_verified`, `age_band` (`under_13`, `13_17`, `adult`, `unknown`: a date of birth not known), `consent` and
`consent_method` (`declared`, `email_link`, `sms_link`, `adult_account`, `digilocker`, `staff_manual`; empty for an
adult), `teacher`, `mfa_on` (an authenticator app or a passkey: recovery codes alone are no factor), `status` and
`locked` (django-axes' lock-out, apart from the status). No lifetime-value prediction, RFM group or churn score exists
for anyone, and a test says the serializers carry none.

**The timeline** (`customers.timeline`): twelve parts, each one query of its newest rows however many it holds (`order`,
`payment`, `refund`, `code`, `access`, `course`, `ticket`, `sms`, `email`, `consent`, `note`, `staff`), merged newest
first, 200 at most, the older ones by `before` (the last answer's `next_before`: the row's time to the microsecond, its
kind and id, so that rows of one instant are neither lost nor shown twice at the page's edge). A part is shown to a
reader who may see its records (`PARTS`: the permission of each) and the rest are named in `withheld`; a row's `href` is
the console's page for the thing. The `staff` part is the audit log's events about the account, so only for whoever reads
the log, and reading it is itself an `audit.read` event. A student under 18's course is **one row** in counts (the
chapters opened so far and the last week they were active): no clip, no quiz answer, no day; an adult's adds the clips
completed in each of the last 26 weeks (`Progress.updated`); an age not known is taken for a child's. SMS rows are
`SmsLog` by account (the log keeps no number), email rows the order emails by order.

**Spending** (`customers.commerce`): the counts of their live orders (placed and kept, cancelled, returns asked for, parcels
that came back undelivered by the shipping outcome), and for an adult the money (spent, refunded, spent less refunded,
the average order), the first and the latest order, up to ten saved addresses (the phone masked) and the tags of their
orders. A student under 18: the counts only, the rest null. It is a record of what happened, not a forecast.

**Parental consent.** `waiting_children` are the active students under 18 with no consent a parent verified and no
deletion of their own under way (that one waits for the parent too, and the cockpit lists it apart). Each link that went
is a `ParentLinkSend` (the account, `email` or `sms`, when, and which member of staff sent it again: kept 365 days by the
retention rule `parent_links`), recorded by `send_parent_link`; the list says how many went, the last one's time and when
it stops working (`PARENT_LINK_DAYS`), how many today of `PARENT_LINKS_PER_DAY` (3, to one address or number whichever
students ask), and whether the account only reads until a parent confirms (`blocking`: `PARENTAL_CONSENT_MODE` is
`verified`). `users/<id>/resend-verification/` sends the link again; a text goes from 08:00 to 21:00 India time only
(`shipping.messages.quiet`, as the order texts do), an email at any hour. `users/<id>/consent/verify/`
(`staff.verify_consent`: high, so re-authenticated; SUPPORT, ADMIN and OWNER) records a consent by hand under a lock on
the account's row: `method` `staff_manual` (staff checked it), `adult_account` (the parent's own verified account) or
`digilocker`; `evidence_ref` says where the evidence is (a ticket's number, a letter's date; one that is, or holds, an
email address or a mobile number is refused, but not ten digits inside a longer number: the document and the contact
never come into the panel); `reason`. It writes the
`ConsentRecord` (`by_parent`, `verified_at`, `verified_by`, `evidence_ref`), which clears the account's flag, tells the
parent by email where their contact is one (so that a consent never given is noticed; a mobile number gets nothing, as no
text is registered with DLT for it) and writes `user.consent_verified` (the record's number, the method, `parent_told`;
never the evidence's words). It is refused for an adult, an erased account, a student whose deletion waits for the
parent, and a consent a parent confirmed already (also when a second member of staff, or the parent's link, was first).

**Bulk actions on accounts.** `user.suspend`, `user.unsuspend`, `user.end_sessions` and `user.resend_consent` are
approvals Actions (`bulk=True`, `generic=False`: only a `bulk_action` job names them, with the accounts' ids as
`targets`, no payload and a reason), each under its maker's permission and scope, and never a deletion. A dry run
(`dry_run`) validates every row and changes nothing; its result counts the rows it would change (`outcomes.valid`), those
it would refuse with the reason (`errors`), the students under 18 among them (`minors`) and says whether the real run
will wait for an approver (`approval`: the rule's words, or null). Above the starter's `bulk_rows`, or with any
student under 18's account among the targets whatever the count, the job waits as a whole for `staff.approve_export`
(`jobs.start`); each row then runs as its own request and writes its own event (`user.suspended`, `user.unsuspended`,
`user.sessions_ended`, `user.verification_resent`, with the starter as the actor and the job's reason), and the batch's
`job.*` events name the action.

**Left out.** `users/<id>/change-email/` (`staff.change_email`): allauth's code-by-email verification keeps its state in
the session of the request that started it, so a change started by staff cannot be completed by the customer, and a
change must never be completed by staff alone. It is not a thin wrapper over the existing flows, so it is not built; a
customer changes their address from their account page.

**What each role sees.** OWNER: everything here. ADMIN: the same but the timeline's staff part, which is the audit log's
(the owners' and the auditor's). SUPPORT: the list and its tabs (the guest buyers through the orders), the record, the timeline
without the staff part, the spending summary, the children waiting, the link again and a consent by hand, signing a
customer out everywhere (alone or in bulk), but not suspending. FINANCE: the list, the record and the parts of the
timeline their orders, payments and refunds permissions open. AUDITOR: the same reads. SALES, PACKER, the content roles:
no customer list (the orders show what they need).

## The jobs

| When (India time) | Task |
|---|---|
| 00:01 | `pages.tasks.publish_due`: a legal page's version published for that day put in force |
| 02:00 | `staff.tasks.verify_audit_chain` |
| 02:30 | `shop.tasks.reconcile_payments`: online orders still awaiting payment, and B2B links still open, asked of Razorpay (`single_run`) |
| 03:15 | `shop.tasks.fetch_settlements`: yesterday's Razorpay settlements fetched, matched and posted (`single_run`; Razorpay out of reach: tried again for about three hours) |
| 03:05 | `accounts.tasks.copy_erasure_ledger`: the erasure ledger's lines not yet in the backups' bucket |
| 03:15 | `staff.tasks.expire_access`: roles given until a time, scopes past their time, change requests expired |
| 04:10, 04:20 | `ops.tasks.trim_expired` and `purge_expired`: the retention schedule's clean-up |
| 06:00 | `staff.tasks.export_audit_log`: the last 7 UTC days not yet in the bucket |
| 07:00 | `staff.tasks.remind_dark_pattern_audit`: from 1 December, the coming year's self-audit (once a year) |
| every hour (:05) | `staff.tasks.expire_change_requests` |
| every hour (:35) | `staff.tasks.watch`: refunds Razorpay refused, filed in the inbox (and done once refunded) |
| every hour (:50) | `staff.tasks.check_backups`: the backups bucket read again; `backup_stale` while a source has nothing newer than `BACKUP_STALE_HOURS` |
| 07:10 | `staff.tasks.check_scripts`: the checkout's and the console's sign-in's scripts compared with the day before (`scripts_changed`, the owners alerted) |
| Mondays 08:30 | `staff.tasks.weekly_audit_skim`: the owners' email of the week's high-risk events, counted by action |
| Mondays 09:00 | `staff.tasks.check_dependency_report`: `dependencies_stale` while CI's report is older than 8 days |

## Not built yet

The panel itself (Next.js); the orders, catalogue and course modules' own endpoints (their permissions are in the
catalogue); bulk actions beyond the change requests' (a
bulk job runs those: refunds, offline payments, prices, coupons); replaying a Razorpay webhook from its body (the
site keeps only the event's id and hash: `system/reconcile/` asks Razorpay again instead); ERPNext's role sync (the
person's ERPNext tab says what to apply by hand); the
Django admin's own step for a break-glass session's reason; the website's page that posts an impersonation token, and
its banner (examleaf-frontend); notes in a data request's access export, and their edits; changing a customer's email address on their behalf ("Phase B: customers" says why); holding the panel shut
until the policies due are acknowledged (the manifest says which; the console decides).
