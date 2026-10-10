# Package P9: Staff, Settings and integrations, System (model: Claude Opus 5.5)

Ports: Django 8119, console 3039 (`E2E_API_PORT=8119 E2E_WEB_PORT=3039`). Read COMMON.md first.

Plan rows: section 5.17 (every row marked **must** that is not already built: the role catalogue page, the Access
tab, role changes with a diff preview and conflict check, passkeys for OWNER, ADMIN and FINANCE, the device list with
"end this session" and "end all", an offer to end other sessions after a factor change, the lockout alert and
per-staff throttles, the offboarding checklist recorded step by step, the ERPNext role mirror by hand, service accounts
never staff), section 5.18 (every **must** row: the settings page with history, the connections page with test
connection, credentials masked and replaced with expiry countdowns, inbound webhooks page with rotation and replay,
the outbound call log and dead letters with Replay and Discard, the circuit breaker's force open and reset, test mode
per integration, Razorpay's webhook health, SES SNS signature verification and bounce rates, MSG91's secret header and
deduplication, the Google `hd` and `email_verified` checks (exist: verify), ERPNext's sync health), section 5.19 (every
**must** row: the audit viewer with saved views, the sync monitor page, backups with the last restore test, the log
inventory and NTP, errors, mail and SMS, dependencies, the admin host's hardening checks, the checkout script check,
liveness probes), 7.11's MessageTemplate row. Research: `research-rbac-security.md` 1.8, 2.1 to 2.9, 3.5, 6, 7;
`research-integrations.md` 3.3, 3.10, 4.1 to 4.4, 4.9, 4.10, 5.2; `research-erpnext.md` 5.5, 6.1, 6.2.

## What exists (read before building)

`staff/api.py` (you are the only agent editing this file: `PeopleViewSet`, `AccessReviewView`, `SystemView`,
`SettingsView`, `FlagsView`, `ApiKeyViewSet`, the manifest), `staff/services.py` (roles, scopes, invitations,
sessions, offboarding), `staff/models.py` (RoleGrant, StaffScope, StaffInvite, ApiKey, SiteSetting and FeatureFlag
through `Switch` with `effective_from`), `staff/config.py`, `staff/permissions.py` (throttles), `staff/signals.py`
(lockout), `accounts/roles.py`, `accounts/adapter.py` (Google `hd`), `integrations/` (IntegrationAccount with
MultiFernet credentials, IntegrationCall, IntegrationFailure, InboundEvent, the circuit breaker, `health.py`),
`shipping/carriers/` (the Shiprocket client and its smoke test), `shop/payments.py` (Razorpay), `ops/sms.py` (MSG91),
`ops/models.py` (EmailSuppression, SmsLog), the anymail settings and webhooks, `erp/tasks.py` `status()` and
`erp/api.py`, `examleaf/health.py`, `scripts/backup.sh` and `upload_backup`, `.github/workflows/ci.yml` (pip-audit,
npm audit), `examleaf/middleware.py` (security headers, CSP), the console's `/people/`, `/settings/`, `/system/`
pages and `src/components/modules/{people,settings,system}/`.

## Backend

### Staff (in `staff/api.py`, `staff/services.py`, `staff/models.py`)

1. **Role catalogue** `GET people/roles/` (`staff.view_staff`): each role with its capabilities grouped by area with
   risk badges, limits, scopes, conflicts and the member count; role cards from `accounts/roles.py`'s docstrings
   ("for people who need to…", "they can't…": write them as two lines per role in a `ROLE_CARDS` dict there; English
   only now, the keys ready for `as` and `bn`).
2. **The Access tab** `GET people/{id}/access/`: roles with who granted them, when and until when (RoleGrant),
   scopes and limits, the effective permissions by area, pending change requests about the person, the last use of
   each high or critical permission from the audit log (bounded query).
3. **Role changes with a preview**: `POST people/{id}/roles/preview/` answers the permissions gained and lost, the
   limits and scopes that change, and the conflicts (`SOD_CONFLICTS`) before anything is asked; the grant itself
   (exists) accepts an optional `expires_at` (temporary grants end by a nightly task that revokes expired RoleGrants,
   audited, with an inbox note to the owner).
4. **Passkeys for the privileged roles**: a member of OWNER, ADMIN or FINANCE without a passkey is sent to set one up
   before any page (the manifest's `steps` gains `passkey_required` with allauth's WebAuthn flow; the console's
   session gate handles it like the two-step setup; a setting `STAFF_PASSKEY_ROLES` with that default); the website's
   `/account/security/` already adds passkeys: link there.
5. **Sessions**: `GET people/me/sessions/` (allauth's `usersessions` for the person: device, place from the address's
   first octets, last seen), `POST people/me/sessions/{id}/end/` and `end-others/`; after a second-factor change the
   manifest carries `offer_end_sessions: true` once (a flag in the session set by allauth's signal).
6. **Throttles and the lockout alert**: per-staff throttle scopes on reveals (exists: check), exports, bulk actions and
   customer searches (`staff_search`), named in `REST_FRAMEWORK`'s rates with sensible defaults, each with a test;
   the owner told at once when a staff account is locked (exists in `signals.py`: verify and test).
7. **Offboarding checklist**: `services.offboard` records each step on a `StaffOffboarding` model (person, started by,
   steps as rows: deactivated, sessions ended, tokens blacklisted, roles and scopes removed, temporary grants
   cancelled, pending change requests reassigned, inbox items reassigned (and tickets and data requests where those
   apps exist: lazy imports), API keys revoked, the ERPNext user disabled (a note when ERPNext is off), with the
   external accounts as a list the owner ticks by hand: Workspace, Razorpay, MSG91, AWS, Cloudflare, the error tracker,
   GitHub, the registrar, SSH keys, shared passwords, security keys collected, the last 90 days reviewed) with `GET
   people/{id}/offboarding/` and `POST people/{id}/offboarding/tick/` (owner's ticks, audited). The ERPNext role
   mirror by hand: `GET people/{id}/erp/` answers the role profile the person should have in ERPNext from their
   roles (a table in `erp/contract.py` or a new mapping in `staff/services.py`) for the owner to apply by hand.
8. Service accounts: API keys never sign in and never get `is_staff` (a check in `ApiKeyAuthentication` and a test).

### Settings and integrations (`integrations/api.py`, mounted at `/api/v1/staff/connections/`, tag "connections (staff)"; `ops/staff_api.py` at `/api/v1/staff/templates/`, tag "templates (staff)")

9. **Settings with history**: `GET settings/{key}/history/` (SiteSetting rows with who, when, the reason, effective
   from) and the same for flags; the Settings page draws groups (the shop, consent, maintenance, the ERP flow
   switches with their environment value and the panel's override; the disclosures group is P8's and will appear by
   its keys: draw any key the API answers, grouped by a `group` the Spec gains in `staff/config.py`).
10. **The connections page**: `GET connections/` one card per integration: Razorpay, Shiprocket, the manual carrier,
    MSG91 SMS (and WhatsApp as "not before Phase D"), Amazon SES, R2 (the buckets), the error tracker (Sentry or
    GlitchTip: the DSN set or not), Google sign-in, ERPNext; status connected | degraded | expired | disabled |
    not_configured from the IntegrationAccount rows and the settings, test or live, last success and last error, the
    error rate over 24 hours and 7 days and the p90 latency from `IntegrationCall` (bounded aggregates), the circuit's
    state. `POST connections/{provider}/test/` (`staff.manage_connections`, new, high; OWNER, ADMIN): one harmless
    authenticated read per integration (Razorpay: fetch one payment or the account; Shiprocket: the wallet balance;
    MSG91: the balance; SES: the sending quota; R2: the bucket head; ERPNext: the ping; Google: the client id's
    presence) through the existing clients with the integrations call log, its result kept on the account (`last_test_at`,
    `last_test_ok`, `last_test_error`). `POST connections/{provider}/credentials/` replaces the credentials after a
    test of the new ones in the same call (never shown; masked to the last four; who set them and when; the expiry
    countdown: Shiprocket's 10-day token, the 90-day rotation policy as `rotate_by`; a written warning for providers
    with no overlap), `POST connections/{provider}/circuit/` (force open or reset), `POST
    connections/{provider}/mode/` (off | test | live with separate credentials per mode), each audited and alerting
    the owners (critical). Keys of Razorpay are seen by nobody (masked); the `RAZORPAY_*` environment keys stay the
    source until an IntegrationAccount row of provider `razorpay` exists (document the precedence).
11. **Inbound webhooks page**: `GET connections/{provider}/webhooks/` (our URL to paste, the token's rotation time and
    the 24-hour overlap, the events received by state over 7 days, a silence alarm when nothing came in
    `INTEGRATION_WEBHOOK_SILENCE_HOURS`), `POST connections/{provider}/webhooks/rotate/` (the new token answered once),
    `GET connections/{provider}/events/` (InboundEvent rows), `POST connections/{provider}/events/{id}/replay/` and
    `replay-failed/` (since a time), `GET connections/{provider}/calls/` (the call log, redacted), `GET
    connections/{provider}/failures/` with `replay/` and `discard/` (reason) (exist in part for the shipping desk:
    reuse `integrations/services.py`). Razorpay's webhook health from our own rows (the last event's age; Razorpay
    disables a webhook after 24 hours of failures: an inbox item for ADMIN when nothing came in 24 hours while orders
    were paid).
12. **SES hardening**: SNS signature verification on anymail's tracking webhook (anymail does not verify: a small
    verifier of the SNS `SigningCertURL` (the certificate fetched once from `sns.<region>.amazonaws.com` only, cached)
    and signature, or basic auth as the control when `ANYMAIL_WEBHOOK_SECRET` is set; the topic ARN restricted by
    `SES_SNS_TOPIC_ARN`), bounce and complaint rates over 7 days against 5 % and 0.1 % on the connections card, our
    suppression list kept in step with SES's (a daily task that reads SES's account-level suppression list through
    boto3 and adds what is missing, `single_run`).
13. **MSG91 hardening**: the delivery-report webhook `POST /api/hooks/sms-events/` with a secret in a custom header
    compared in constant time (current and previous), deduplication on MSG91's request id (InboundEvent), delivery
    reports with failure reasons written on `SmsLog` ("Template Id not found on DLT"), the daily cap hits counted.
14. **The template registry**: `ops.MessageTemplate` (event, channel email | sms | whatsapp, language, the DLT
    template id, PE id, the header with its suffix, the MSG91 id, the WhatsApp template name, category, approval
    state, typed variables, last used at, self-certified on) seeded from the SMS templates in settings by a data
    migration; `ops.sms` reads the id from the registry when a row exists (the environment's otherwise), writes
    `last_used_at`; `GET/POST/PATCH templates/` (`ops.change_messagetemplate`: ADMIN, MARKETING reads), a test send to
    the staff member's own number or address only (`POST templates/{id}/test/`), the 90-day idle warning as an inbox
    item (nightly), the yearly self-certification reminder.
15. **ERPNext**: the connections card shows the sync's health from `erp.tasks.status()` (outbox depth, dead letters,
    the last reconciliation, the integration user's key present, the webhook secret set); the per-flow switches are on
    the Settings page already.

### System (`staff/api.py` `SystemView` and new views in `staff/system_api.py` mounted from `staff/urls.py` as `path("system/", include("staff.system_api"))`)

16. **Audit viewer**: saved views for the audit list (`list_key="audit"`, exists? check), the filters the plan names
    (actor, action, target, outcome, dates, request id, address), exports with the hashes (exist); a weekly skim: a
    Monday 08:30 email to the owners with the week's high-risk events by action (counts, no personal data; `single_run`).
17. **Sync monitor**: `GET system/sync/` the outbox per flow (pending, sent, failed, dead), dead letters with replay
    and discard (the erp API exists: link and summarise), ErpLink lookups (`GET system/sync/links/?q=`), inbound
    ERPNext events, each night's reconciliation with its differences (summarise from the erp API).
18. **Backups**: `GET system/backups/` from the backups bucket (the last object's time, size, checksum if stored,
    the location; an alert past 26 hours exists? verify and add the inbox item), the retention (30 days), and
    `staff.RestoreDrill` rows (date, who, result, duration, notes) with `POST system/backups/drills/`
    (`staff.manage_settings`-class: `staff.manage_system`, new, high), shown in words ("last proven to work on …").
19. **Logs and time**: `GET system/logs/` the log inventory (what, where, how long, who reads) as a table in code
    (`examleaf/logs.py`), the retention in force (180 days now, a year from 13 May 2027), the NTP status (`ntpd`/
    `chronyd`/`timed` not available in a container: report the host's documented source from a setting
    `LOG_TIME_SOURCE` and the clock's offset against the database's `now()`), and the CERT-In point of contact from
    the disclosures settings when present.
20. **Dependencies**: `GET system/dependencies/`: the last pip-audit and npm audit results written by CI to a JSON
    the deploy copies into the private storage (`DEPENDENCY_REPORT_PATH`), with open advisories by severity and the
    7-day target for critical ones, and the installed versions of Django, Python, Next.js, ERPNext (from
    `examleaf-erp/image/` pins) read at start; a weekly inbox item when the report is older than 8 days.
21. **Hardening checks** `GET system/hardening/`: the admin host set (`ADMIN_HOSTS`), staff endpoints 404 elsewhere
    (a self-request), HSTS of a year with subdomains (the response header on the admin host), CSP with
    `frame-ancestors 'none'`, `no-store` on staff answers, `noindex` on the console (a fetch of `/robots.txt` from
    `STAFF_PANEL_URL` if reachable), `__Host-` cookies with SameSite Strict, DEBUG off, the secret keys set, the
    proxy's stripped header (documented, not testable from here), each as a row with ok, detail and the fix.
22. **The checkout script check**: a daily task (`single_run`) that fetches the storefront's checkout page
    (`SITE_URL/checkout/`) and the console's sign-in page, inventories the `<script src>` and inline script hashes,
    stores them on `staff.ScriptInventory` rows (page, url or inline hash, first seen, last seen, sha256), and opens
    an inbox item for ADMIN and alerts the owners on any change; `GET system/scripts/`.
23. Liveness probes never test the database or Celery (exists: `/health/live/`; a test asserting it makes no query).

Permissions: `staff.manage_connections`, `staff.manage_system` (new, high, OWNER and ADMIN), `ops.view_messagetemplate`,
`ops.change_messagetemplate`, `staff.view_restoredrill`, `staff.view_scriptinventory` by rule; `staff.view_system`
reads everything of the system; AUDITOR reads.

## Tests the exit criteria need

Every endpoint in the matrix; the preview's gains and losses and conflicts; a temporary grant revoked by the task once;
the passkey step for a FINANCE member without one and not for SUPPORT; sessions listed and ended; the throttles
answer 429 at their limits; the offboarding steps recorded and the external list ticked by the owner only; the test
connection through each client with the network mocked and the result kept; credentials replaced only after a passing
test and masked everywhere (audit `changes` included); the webhook token rotated with the previous accepted 24 hours;
the SNS verifier on a known-good and a tampered message; the MSG91 header compared in constant time and duplicates
ignored; the template registry read by `ops.sms` and `last_used_at` written; the SES suppression sync idempotent; the
script inventory alerting once on a change; the hardening rows; the dependency report read and the stale warning; the
weekly skim sent once; `/health/live/` makes no query.

## Console

`/people/[id]/` gains the Access tab, the role-change preview in the grant dialog (plain words: gains, loses,
conflicts), the offboarding checklist with the owner's ticks; `/people/roles/` the role catalogue; `/account/` the
session's devices with end buttons; `/settings/` grouped with history per key; `/settings/connections/` (one card per
integration answering "is it working, since when, what do I do if not"; Test, Replace with the test in the same
sitting, the circuit, the mode; test and live in different colours), `/settings/connections/[provider]/` (webhooks,
events, calls, failures with replay and discard), `/settings/templates/`; `/system/` opens on one status line per
subsystem, then sync, backups (with the drill record form), logs and time, dependencies, hardening, scripts. Mock
fixtures for every state. Mock journey: connections → test one → replace credentials → the audit trail; people → access
tab → preview a role change; system → hardening rows. Real journey (`real.spec.ts` + seed): the OWNER opens the
seeded SUPPORT member's Access tab and previews a role grant.

## Boundaries

The disclosures settings group and the retention table are P8's (draw them when present); the sync's own pages are
the erp app's (summarise and link); the shipping desk's dead letters exist (reuse). P9 is the only package editing
`staff/api.py` and `staff/services.py`; keep edits additive and in place.
