# Runbook

Commands run in `/srv/examleaf/examleaf-web` on the server. `dj` below stands for
`docker compose exec web python manage.py`.

Most of what an operator does is a page of the Admin Control Panel (`https://admin.<domain>`, the console in
`../examleaf-admin/`). This runbook names the page, the button, what it asks and what it writes to the audit log; the
one-page guide of each role (`../docs/guides/roles/`) says who may use it. Where a shell recipe once did the job, it
stays as a short "If the panel is down" line: the break-glass way, which needs a shell on the server and is nobody's
daily tool. What waits for a person is in the panel's Inbox, and "The inbox" below says what each item asks of you.

## Contents

- [Backups and restore](#backups-and-restore): restoring the database, the restore drill and where it is recorded
- [Secrets and key rotation](#secrets-and-key-rotation)
- [Staff accounts](#staff-accounts): a new member of staff, a lost second factor, leaving, ending sessions, break-glass
  accounts
- [Data requests and privacy](#data-requests-and-privacy): a data request under the DPDP Act, purging old orders, the
  retention tasks, legal holds, policy versions, the disclosures and the dark-pattern self-audit
- [Email](#email): when email fails, bounces and complaints
- [SMS, phone numbers, passkeys and parental consent](#sms-phone-numbers-passkeys-and-parental-consent)
- [The shop](#the-shop): payments, refunds, Razorpay's settlements, invoices, shipping, GST returns, coupons, offers,
  staff orders and payment links (a B2B invoice's too), the catalogue
- [Connections](#connections): the page, a card's status, a test, new keys, the mode, the circuit, a webhook token,
  events, calls and dead letters
- [Couriers and integrations](#couriers-and-integrations): Shiprocket down, dead letters, failed deliveries, returns,
  COD remittances, weight disputes, parcels that stopped moving
- [Reviews, school orders and stock](#reviews-school-orders-and-stock)
- [The revision course](#the-revision-course): uploading, failed clips, book codes, access
- [Content](#content): importing papers, a wrong solution reported, a publish to undo, QR codes for print, legal
  deposits and their reminder
- [Insights](#insights): a job failed, a fraud spike, a number that looks wrong, the monthly review, a new season
- [ERPNext](#erpnext): ERPNext down, a refused document, the morning's differences, no doorbells, a flow
  switched off and on, ERPNext restored from a backup
- [Support](#support): the queue and its deadlines, logging a call or an NCH complaint, the support mailbox, spam,
  the grievance register
- [The system pages](#the-system-pages): the checkout's scripts changed, the dependency report, hardening, logs and
  time
- [Incidents](#incidents)
- [The inbox: what each item asks of you](#the-inbox-what-each-item-asks-of-you)
- [Reading the logs](#reading-the-logs): a request's lines, slow requests, a task's lines, gunicorn's restarts

## Backups and restore

### Restore the database from a backup

1. Pick the dump: `ls -lt backups/`, or download it from the backup bucket (`database/examleaf-….dump`, or
   `….dump.age` when `BACKUP_AGE_RECIPIENT` is set: decrypt it on the computer that holds the key,
   `age --decrypt -i examleaf-backup.key -o examleaf-….dump examleaf-….dump.age`, then copy the dump to `backups/`).
2. Keep the erasure ledger: restoring brings back the data of everyone erased since that dump. Every erasure is
   copied to the backups' bucket as it is made (`erasures/<id>.json`), which step 4 reads. If the database you are
   replacing can still be read, also write its ledger to a file first:
   `dj reapply_erasures --export /app/media/erasures.jsonl` (the `media` volume outlives the restore).

3. Stop everything that writes, restore, start again:

   ```sh
   docker compose stop web worker media-worker beat
   docker compose exec -T db pg_restore --clean --if-exists --no-owner --username examleaf --dbname examleaf < backups/examleaf-YYYYMMDD-HHMMSS.dump
   docker compose up -d
   ```

4. Erase them again, before anyone uses the site: `dj reapply_erasures --dry-run` says how many (counts only), then
   `dj reapply_erasures` (with `--ledger /app/media/erasures.jsonl` if you wrote one). An account is erased again only
   while its address still matches the ledger's hash, so nobody else is ever touched; each is an `account.erased` event
   with `reapplied`. Deletions that were still waiting are completed by the next daily purge (or run
   `dj shell -c "from accounts.tasks import purge_due_deletions; print(purge_due_deletions())"`).
   Students who asked for deletion after the dump was taken must ask again: tell them. Without a backups' bucket the
   ledger is only in the database: then step 2's file is the only record, so never skip it.
5. Check `/health/`
   (`curl -H "X-Health-Token: $(sed -n 's/^HEALTH_CHECK_TOKEN=//p' .env)" https://examleaf.in/health/`), log in to the
   admin, open a paper.

**A restore drill** (each quarter, and after a change to the backups): restore the newest dump into a scratch
database (`docker compose exec db createdb --username examleaf examleaf_drill`, then `docker compose exec -T db
pg_restore --no-owner --username examleaf --dbname examleaf_drill < backups/examleaf-….dump`), check that its newest
order and audit event are there, drop it (`dropdb`), and record it in the panel: System → Backups → "Record a restore
drill" (ADMIN, the owners; the day, what was restored, the backup, the result, the minutes it took and notes: "The system
pages", below). The page then says when the backups were last proven to work; it also says each source's newest backup,
its SHA-256 (compare it with `sha256sum` of the file you restored) and whether it is older than `BACKUP_STALE_HOURS` (an
inbox item `backup_stale` opens then: look at the backup job's logs, `docker compose logs backup` or the CronJob's last
run).

On a new server: follow DEPLOYMENT.md up to `docker compose up -d`, then restore as above (the empty database's tables
are replaced). The files are not in the dump: the `media` volume (DEPLOYMENT.md section 9) or the buckets (section 17)
must come across too.

## Secrets and key rotation

Change the value in `.env`, then `docker compose up -d` (it recreates the containers whose settings changed).

- **SECRET_KEY:** put the old key in `SECRET_KEY_FALLBACKS`, the new one in `SECRET_KEY`; remove the fallback after two
  weeks (sessions made with the old key keep working until then; a password-reset link lives an hour anyway). The hashes
  of the consent records' addresses and of the SMS log's numbers made with the old key can no longer be compared with an
  address or found by number (the SMS log's rows go after 90 days); the records themselves stay valid.
- **POSTGRES_PASSWORD:** `docker compose exec db psql -U examleaf -c "ALTER USER examleaf PASSWORD 'new'"`, then change
  `.env` and `docker compose up -d`.
- **Razorpay's and MSG91's keys** from the panel (Settings → Connections → the provider → Replace the keys, OWNER or
  ADMIN): create the new key with the provider, paste it there (it is tested before it is kept, and the old one stays
  in force if the test fails), check the card says Working, then revoke the old key with the provider. Once the
  panel holds keys, the `.env` ones are no longer read (`integrations/README.md` "Precedence"); with the panel down,
  the shell below still works only while no account holds keys, so keep a break-glass session for that case.
- **Provider keys** (email: `SES_*` or the `ANYMAIL_…` key; `MSG91_AUTHKEY`; `RAZORPAY_KEY_*`; `S3_*` and `PUBLIC_S3_*`;
  `AWS_*` of the backups; `GOOGLE_CLIENT_SECRET`; `TURNSTILE_SECRET_KEY`; `FCM_SERVICE_ACCOUNT_JSON`; `SENTRY_DSN`):
  create the new key with the provider, change `.env`, `docker compose up -d`, then revoke the old key. MSG91's new
  authkey needs the server's IP whitelisted too.
- **Webhook secrets** (`RAZORPAY_WEBHOOK_SECRET_TEST`, `RAZORPAY_WEBHOOK_SECRET`, `ANYMAIL_WEBHOOK_SECRET`): the
  provider holds the same secret (Razorpay's webhook settings; the user and password inside the SNS or provider
  webhook URL), so change both at the same moment. Events that arrive between are refused; Razorpay sends a webhook
  again for 24 hours, and `dj reconcile_payments` finds payments that were missed.
- **HEALTH_CHECK_TOKEN:** change it in `.env` and in the uptime monitor's header.
- **Staff passwords:** each person changes theirs on the website's Security page (`/account/security/`). For a person
  who left, an owner offboards them in the panel (People → the person → Offboard: "Staff accounts", below), which also
  takes their roles, ends their sessions and revokes their API keys.
- **JWT_SIGNING_KEY** (the app's tokens; SECRET_KEY while unset): a new value logs every app out at once; the website's
  sessions stay.
- **LEARN_CODE_SECRET:** never. Printed book codes work only with the key they were made under (DEPLOYMENT.md
  section 18). Without it a server does not start: `docker compose logs web` shows `learn.E001` at `migrate`.
- <a id="integration-keys"></a>**INTEGRATION_KEYS** (the key of the integration accounts' credentials and tokens): put
  a new key first, `INTEGRATION_KEYS=<new>,<old>`, `docker compose up -d`, then `dj rotate_integration_keys`
  ("Re-encrypted the secrets of N account(s)"), then remove the old key and `docker compose up -d` again. Never remove a
  key before the rotation has run: secrets encrypted with it can no longer be read (the admin shows "Cannot be read
  with INTEGRATION_KEYS", calls fail). Lost for good: paste the credentials of each account again (below) and make a
  new webhook token. Without any key a server with accounts does not start: `integrations.E001` at `migrate`.
- **Shiprocket's API user** (rotate by the account's `rotate_by`, 90 days, which its card counts down; or at once if
  it leaked): in Shiprocket, Settings → API → Add New API User (a new email address); in the panel, Settings →
  Connections → Shiprocket → Replace the keys with the new email and password (tested before they are kept); then
  delete the old API user in Shiprocket. The cached token goes with the old credentials. Break-glass fallback: the
  admin's account → "Replace the credentials" → Save → "Test the connection".
- **A webhook token** (the couriers', MSG91's delivery reports'): the connection's page → Webhooks → New token shows it
  once; paste it at the provider (Shiprocket: Settings → API → Webhooks, the security token; MSG91: the delivery
  report URL's `X-Webhook-Token` header) within 24 hours, while the previous one still works. Fallback: the admin's
  action "New webhook token".
- **Suspected breach:** rotate everything above, SECRET_KEY **without** a fallback (a leaked key would otherwise keep
  sessions valid for two weeks) and JWT_SIGNING_KEY (or SECRET_KEY, if it is unset) too, end all sessions (the panel
  ends one person's at a time, so for everyone at once the shell: "Staff accounts", "Ending sessions"; everyone logs in
  again, staff with their second factor), change `HEALTH_CHECK_TOKEN`, find out what was exposed, and inform the Data
  Protection Board of India and the people affected without delay (the DPDP Rules, 2025 ask for a detailed report to the
  Board within 72 hours). Keep notes of what happened and what was done.

## Staff accounts

Every member of staff signs in with a password (or Google) and a second factor: a code from an authenticator app, or a
passkey (SECURITY_REVIEW.md, H2). OWNER, ADMIN and FINANCE must hold a passkey or a security key
(`STAFF_PASSKEY_ROLES`). A session lasts 8 hours from the sign-in, and ends sooner after 15 minutes without a request
for OWNER, ADMIN, FINANCE and PACKER and after 30 minutes for the others. The work below is done in the panel's People
(`https://admin.<domain>/people/`; invitations, roles, offboarding and ending sessions are an owner's, permission
`staff.assign_role`); a person's page has the tabs Overview, Access (what they may do, and when they last used the risky
parts), Offboarding and ERPNext. Each role's guide is in `../docs/guides/roles/`.

1. **New member of staff.** An owner: People → "Invite a staff member" with their work email address, a role and the
   reason. An invitation to OWNER, ADMIN, FINANCE or AUDITOR waits for a second person (ADMIN or another owner) in
   Approvals. The audit log has `staff.invited` (and `staff.invite.requested` and `.approved` when it waited). The
   colleague gets an email with a link that works once,
   for 7 days (the console's form says 72 hours: the code's 7 days stand). **The page behind that link is not built.**
   The email points at `/invite/<token>/` on the panel's host, which neither `examleaf-admin` nor the website has; the
   API behind it (`POST /api/v1/staff/invites/accept/`) is there. Until the page is, give the role another way:
   - With Google for staff on (`STAFF_GOOGLE_DOMAIN`, DEPLOYMENT.md section 15) and `STAFF_GOOGLE_AUTO_STAFF=1`, the
     colleague signs in once with "Continue with Google" and a member of staff with no role is made for them. People
     lists them; an owner opens their page → Access → "Grant a role" (the role, an end date if it is temporary, the
     reason; the grant's preview says what they gain and lose before anything is asked). A privileged role waits for a
     second person, and two roles that separation of duties keeps apart (FINANCE with PACKER, MARKETING with FINANCE,
     AUDITOR with any other) are refused. The audit log has `authz_change`.
   - Otherwise a break-glass session makes the account in the Django admin (Users → Add, or the colleague registers on
     the site) and gives the role (Users → action "Give role …"; only superusers can); the rest is People's.
2. **First sign-in** at `https://admin.<domain>/sign-in/`: "Continue with Google" with the work address (where Google is
   on), or the email address and password (an address not yet confirmed first gets a code by email). With no second
   factor yet the console says "Set up two-step sign-in first" and links to the website's `/account/2fa/`: scan the QR
   code with Google Authenticator, Microsoft Authenticator, Aegis or 2FAS, type the 6-digit code, and the ten recovery
   codes appear. A passkey (the website's Security page) does instead of the app, as the step after the password:
   staff cannot sign in with a passkey alone. OWNER, ADMIN and FINANCE are held at "Add a passkey or a security key"
   until they have one. Then the console asks each policy to be read and acknowledged (`STAFF_POLICIES`, once per
   version; an audit event `policy.acknowledged`) and opens on Home.
3. **Recovery codes are kept offline:** download or write them down and keep them away from the phone (on paper in a
   safe place, or in a password manager). Each works once, instead of the app's code.
4. **Later sign-ins:** password, then the app's code (or a recovery code, or the passkey). The website's `/account/2fa/`
   shows how many recovery codes are left and makes new ones (the old ones then stop working).
5. **Lost phone, a second factor to reset.** The person signs in with a recovery code and sets the app up again
   (`/account/2fa/`: deactivate, then activate). No recovery code either: first check who is asking, by phone or in
   person, as strongly as when the factor was set up. Then People → the person → Danger zone → "Reset their two-step
   sign-in", which asks for the reason (ADMIN or an owner; it is a change request, so nothing has happened yet). A second person
   who may approve staff second-factor resets (ADMIN or another owner, never the one who asked) approves it in
   Approvals. When it runs, the person's authenticator apps, recovery codes and passkeys are deleted, every session of
   theirs ends and they are emailed ("Your second factor was reset"); their next sign-in sets a new one up (OWNER, ADMIN
   and FINANCE add a passkey first). The audit log has `user.reset_mfa.requested`, `.approved` and `.executed`. A
   customer's second factor is reset the same way from Customers → the customer → "Reset two-step sign-in", approved by
   another holder of that permission (SUPPORT, ADMIN or an owner). Only a break-glass account can change a break-glass
   account's factors, and an owner's are changed by an owner; if one of them is locked out, the shell:
   `dj shell -c "from allauth.mfa.models import Authenticator as A; A.objects.filter(user__email='x@example.com').delete()"`.
6. **Leaving:** an owner offboards them in one step (People → the person → Danger zone → "Offboard": their email
   address typed and the reason; the account is deactivated, roles and scopes gone, sessions, tokens and API keys
   ended, their requests withdrawn and tickets unassigned; `user.offboarded`), then works through the
   person's Offboarding tab: the ERPNext user disabled, their
   external accounts closed, the security keys collected, their last 90 days in the audit log read, each ticked (or
   "not needed") with a note (`offboarding.ticked`); the inbox item stays until the last one. A temporary role that
   ends by itself opens `role_expired` on the person. If the panel is down: in the Django admin, untick Active (the
   sessions stop working at once) and take the roles away, then do the Offboarding tab's steps when it is back.
7. **Passkeys:** OWNER, ADMIN and FINANCE (`STAFF_PASSKEY_ROLES`) add a passkey or a security key on the website's
   Security page before the panel opens for them (`passkey_required`). A lost one: they add another there with their
   authenticator app's code; none left at all: lost phone, above.
8. **A session they do not recognise:** the person ends it on the panel's My account page ("Sign out" beside a device,
   or "Sign out everywhere"). After a second factor is added, removed or reset the console offers once to end the other
   sessions ("Your two-step sign-in changed"); take it if it was not you.

**Ending sessions.** One member of staff's: People → the person → "End all their sessions" (an owner; every browser and
app, and the app's refresh tokens; the audit event `session_ended_by_staff` with the counts). One customer's:
Customers → the customer → "Sign them out everywhere" (`staff.end_user_sessions`: SUPPORT, ADMIN, owners), or the
Customers list's bulk bar for many (checked first; with a student under 18 among them a second person approves it).
There is no panel action that ends every session of everyone at once. If you must, the break-glass way ends them all,
and everyone signs in again, staff with their second factor:
`dj shell -c "from django.contrib.sessions.models import Session; Session.objects.all().delete()"`.

### Break-glass accounts

The superuser flag is only on one or two break-glass accounts, outside Google sign-in, each with a security key and a
backup key kept offline; the founder's daily account holds the OWNER role instead (DEPLOYMENT.md section 23). Use one
only when nothing else works (Google sign-in down, every owner locked out of their account):

1. Log in with it as any member of staff does, with its password and its security key (never Google). The owners are
   emailed at once ("Break-glass account #… signed in").
2. Say why before anything else: the panel asks (the manifest's `break_glass.reason_required`); without the panel,
   `POST /api/v1/staff/session/reason/` `{"reason": "…"}` on the admin host. Until then the staff API answers
   `403 {"code": "break_glass_reason_required"}`. The owners get the reason, and every audit event of the session
   carries `break_glass` and the reason (`details.break_glass_reason`). The Django admin does not ask: give the reason
   first, in the same browser on the admin host. The session ends after 15 idle minutes, and 2 hours after the log-in
   however busy (`STAFF_BREAK_GLASS_HOURS`); the owners are told when it ends.
3. Do what the emergency needs, nothing more, and log out.
4. Within 24 hours an owner or the auditor reads what it did: `GET /api/v1/staff/audit/?break_glass=true` (the staff
   API, as an AUDITOR or OWNER), and notes why in the incident or the access review.
5. Every quarter: log in with each one once (the keys still work), log out, review that event, and check who can
   reach the keys.

## Data requests and privacy

### A data request under the DPDP Act

Most requests are self-service on My account: Download my data, change the email address, Delete my account. A request
by email, letter or phone goes through the panel, Legal and privacy (staff/README.md "Data protection" and "Legal and
privacy"); the shell recipes below each step are the break-glass way, when the panel cannot be reached.

1. **Log it and check who is asking:** Data requests, Log a request (the clocks start from when it was received:
   acknowledge within 48 hours, answer within a month, 90 days for the DPDP rights from 13 May 2027; the cockpit shows
   them; SUPPORT, ADMIN, owners; the audit log has `data_request.created`, then one event for each step). Answer only to
   the account's email address, or, for a student under 18, to the parent's contact recorded at sign-up; record how the
   identity was checked (Record the identity check: the method, never the document).
2. **Access:** the request's "Email their data" sends Download my data's file to the account's own address, with who
   processes it for us (the processor register). It is ADMIN's and the owners' (`staff.export_personal_data`, which asks
   to confirm it's you): SUPPORT logs the request and checks the identity, then asks one of them. Break-glass:
   `dj shell -c "import json; from django.core.serializers.json import DjangoJSONEncoder; from accounts.models import User; from accounts.views import export_user_data; print(json.dumps(export_user_data(User.objects.get(email='x@example.com')), cls=DjangoJSONEncoder, indent=2))" > export.json`
   and send the file to that address; delete your copy afterwards.
3. **Correct:** edit the user in the admin (ADMIN role; the admin's history records the change).
4. **Erase or withdraw consent:** the request's erasure: its dry run first (what goes, and what stays and until when:
   the books by financial year, a year of processing logs, legal holds, a child's parent), then "Erase the account",
   which a second person approves (ADMIN). A legal hold on the account or a child whose parent has not confirmed keeps
   it waiting: release the hold when the case is over (Legal holds), or record the parent's confirmation (the
   parent's own link from their email, or, when they are reached by phone or letter, the cockpit's row "A child's
   deletion waits for the parent" with where the evidence is). Each processor that keeps personal data gets a task in
   the inbox once it is done ("ask SES to purge the address" …): do each, then mark it done. Quotation requests made
   with the address (admin → Shop → Quote requests) are not erased by the purge: delete them too (ADMIN).
   Break-glass, with the seven-day wait:
   `dj shell -c "from accounts.models import DeletionRequest, User; DeletionRequest.objects.create(user=User.objects.get(email='x@example.com'))"`;
   at once, add `.complete()` (it raises `DeletionRequest.Held` with the reasons while something holds it).
5. **Nominee:** the person records it themselves (`me/nominee/`; staff see it on the customer's record, the contact
   masked and revealed with a reason). A nomination by letter: log it as a data request of the kind nomination, with
   what it says in the notes. Act on the nominee's request only on proof of death or incapacity (the claim's flow in
   the panel comes in Phase C).
6. **Answer** with the request's text (its contact block is filled in from Legal and privacy, Disclosures), then close
   it with the outcome and the answer as sent. Consent records (admin → Consent records, CSV export) show what was
   agreed to, when, under which policy version, how and whether a parent gave it; the cockpit counts the consents by
   the privacy notice's version.

The parental consent is self-declared while `PARENTAL_CONSENT_MODE=declared` (a parent ticks the box). The DPDP Rules,
2025 ask for verifiable consent of a parent from May 2027: switch to `verified` before then ("Parental consent" below).

### Purging old orders

Nobody presses a button for this: it is two nightly tasks, and the panel shows what they keep and what they did.

- **In the panel:** Legal and privacy → Retention (`/privacy/retention/`; SUPPORT, ADMIN, the owners and the auditor)
  lists each kind of record with the law's minimum and the day it changes, what this site keeps and what deletes it.
  Each night's work is an audit event: `retention.trimmed` (04:10) and `retention.purged` (04:20), the counts of each
  rule and never a person; the owners and the auditor read them under Audit trail.
- **Every day (automatic):** the 04:30 clean-up strips the name, phone, address lines and email address ("deleted",
  in the order's history too, and staff's notes on the order go) from orders never paid or placed, 30 days after they
  were cancelled; it also clears the stored Razorpay webhook fields of payments older than 180 days.
- **Every night (automatic), orders past their books' period:** the retention schedule's clean-up (04:20,
  `ops.tasks.purge_expired`, at most 500 orders a night) forgets the customer's details of every order whose documents
  are all older than the oldest financial year still kept (8 financial years after the year, or 72 months after its
  annual return's due date, whichever is later: `examleaf/retention.py`) and deletes their invoices' and credit notes'
  PDFs; the order rows and their numbers stay, for the totals. A legal hold on the order, one of its documents or its
  customer keeps it as it is ("Legal holds", below). The backups age out on their own (30 days).
- **If the panel is down,** or a night's run did not happen (the task's lines in `docker compose logs worker`), the
  break-glass way does the same work:

  ```sh
  dj shell -c "from ops.tasks import purge_books; print(purge_books(), 'orders purged')"
  ```

  `purge_books` calls `forget_orders`, which itself passes by any order whose tax documents are within 72 months of
  their year's annual return (FY 2025-26: until 31 December 2032), whoever asks; then purge the same years from the
  off-site backups (bucket lifecycle) and note the date in the support mailbox.

### The retention tasks (every night)

What the nightly tasks remove or blank, so that a missing run is noticed. India's time; each is idempotent, so a
second delivery or a run by hand does no harm (RESILIENCE.md). The whole schedule is in README.md "Background tasks".

| When | Task | What it does | Where it shows |
|---|---|---|---|
| 03:00 | `accounts.tasks.purge_due_deletions` | carries out the account deletions whose seven days are over, but those a legal hold or a child's parent keeps waiting (an inbox item, `compliance`); erases the registration details the intermediary rule kept 180 days | `account.erased`, `account.registration_erased` |
| 03:05 | `accounts.tasks.copy_erasure_ledger` | copies each erasure's ledger line to the backups' bucket (`erasures/<id>.json`) | |
| 03:30, 03:45 | `ops.tasks.reset_failed_logins`, `clear_sessions` | forgets django-axes' failed log-ins; deletes expired sessions and the signed-in devices of ended ones | |
| 03:45 | `support.tasks.purge` | tickets moved to spam 30 days ago, with their messages, files and raw mail; saved replies 30 days in the bin | `support.spam_purged` |
| 04:00 | django-celery-beat's own | task results older than a week | |
| 04:10 | `ops.tasks.trim_expired` | blanks the SMS log's last four digits after 90 days | `retention.trimmed` |
| 04:10 | `content.tasks.purge_spam` | reported-mistake spam after 30 days | |
| 04:20 | `ops.tasks.purge_expired` | the SMS log's rows after a year; Razorpay's webhook records and the Celery task results after 7 days; the app's phones silent for 90 days; the orders past their books' period | `retention.purged` |
| 04:30 | `shop.tasks.clean_up` | cancels orders left unpaid (after asking Razorpay); queues lost refunds, invoices and credit notes again; deletes guest carts idle for 30 days, old stock alerts, webhook payloads and the details of cancelled unsold orders | |
| 04:30 | `learn.tasks.purge_bin` | deletes the clips, cards and quiz items 30 days in the bin, with a clip's video | `course.purged` |
| 04:45 | `integrations.tasks.purge_old_records` | the call log, inbound events and dealt-with dead letters older than `INTEGRATIONS_RETENTION_DAYS` (90) | |
| hourly :20 | `learn.tasks.purge_code_files` | the printers' files of book codes after their 24 hours | |
| monthly | `manage.py purge_audit` (the owner role's crontab, DEPLOYMENT.md section 23) | the audit log past its retention: two years for the general chain, eight financial years for the money chain | `audit.purged` |

A task that gave up is an inbox item (`failed_job`, "Task … failed", for `staff.view_system`) and a line in Sentry. To
run one by hand, call it in a shell, for example
`dj shell -c "from ops.tasks import trim_expired; print(trim_expired())"` (it prints the counts).

### Legal holds, policy versions, the disclosures and the self-audit

All in the panel's Legal and privacy (`/privacy/`; staff/README.md "Legal and privacy"), each step an audit event. The
compliance cockpit (`/privacy/`) is where to start: every clock the rules start, the late first, each opening its
record, and the legal calendar.

- **A chargeback, a dispute or a legal claim:** put a legal hold on the order (or the invoice, the payment …) or on the
  customer (Legal holds → "Add a hold": FINANCE, ADMIN, OWNER), with the case's reference and, when known, its last
  day. While it holds, the account is not erased and the records are left out of the retention clean-up. "Release the
  hold" with the reason once the case is over (or it lapses after its day). Events `legal_hold.created` and
  `legal_hold.released`.
- **A new privacy policy, terms or refund policy:** Policy versions (CONTENT_EDITOR, ADMIN, OWNER), the page, "Publish a
  new version": the text, a line on what changed, the day it is in force from (today, or a later day: then it waits and
  comes into force just after midnight, `policy.in_force`, and the website lists it as upcoming; "Cancel it"
  before then if needed, `policy.schedule_cancelled`). Consents given from then on keep its number. Change the
  Privacy Policy when the retention changes (the SMS log is now kept a year, the server logs about 180 days:
  DEPLOYMENT.md section 10).
- **The e-commerce disclosures** (before 1 January 2027, and whenever one changes): Disclosures (ADMIN, OWNER;
  `staff.manage_settings`): the legal name and addresses, customer care, the Grievance Officer with designation and
  contact, the nodal contact resident in India, the DPDP contact person, CERT-In's point of contact, the published text
  on rights requests, the National Consumer Helpline membership (how to join is a question for counsel: record "Applied"
  and "A member" with their dates). "Save the changes" saves them together with one reason, each value a
  `setting.changed` event; the website's footer and contact page show them within five minutes.
- **The dark-pattern self-audit** (every December, the inbox reminds from 1 December; OWNER and ADMIN keep it, the auditor
  reads it): Dark-pattern audit → "Start the self-audit for <year>": a finding and a fix for each of the 13 patterns
  ("Save the self-audit"), the certificate's text and the day it is shown from (1 January), then "Complete and sign"
  (the year typed; it cannot be changed afterwards) and "Keep the signed copy" (a PDF, PNG or JPEG of 5 MB at most).
  The website shows the certificate from its day; the cockpit turns red on 1 January without one. Events
  `dark_pattern_audit.created`, `.updated`, `.completed`, `.file_kept`.
- **The processors' tasks** (the inbox, kind "a processor to tell", for OWNER and ADMIN): after each erasure, ask each
  processor that keeps personal data to erase it (the processor register's "what to ask them"); after a marketing
  consent is withdrawn, tell each that holds marketing lists to stop. Keep the processor register's two ticks and that
  line right (Processors → "Add a processor").

## Email

### When email fails

Signs: students say the code never came; Sentry errors from `ops.tasks.send_email`; failed or retrying tasks under
Celery Results → Task results; `docker compose logs worker | grep send_email`.

1. Is the worker up? `docker compose ps worker`. (`/health/` pings the workers too, but with two workers it can say "No
   worker for Celery task queue celery" when the media worker answers first: ask again before restarting anything.) If
   it is down: `docker compose up -d worker` and look at its logs. While Redis is down, emails are sent directly by the
   web process, so sign-ups keep working.
2. Does the provider accept mail? `dj sendtestemail you@example.com` sends synchronously and shows the provider's
   error (wrong API key, quota, unverified sender domain, account suspended). Check the provider's dashboard and status
   page, and the SPF/DKIM records.
3. A failed email is retried five times with growing waits (25 minutes at most in all), then dropped. Once mail works,
   students log in again (an address not yet confirmed gets a new code at each log-in) or use "Log in with a code"
   again, or reset the password; a log-in code is limited to 3 an hour per address, a confirmation code to 5 an hour and
   10 a day. If Redis and the provider are down together, the web process tries once, logs "the email could not be sent
   here either" (Sentry) and the page goes on: the same answer.
4. To switch provider quickly: set `EMAIL_BACKEND` and the new provider's `ANYMAIL_…` key in `.env`
   (django-anymail supports Amazon SES, Mailgun, Postmark, SendGrid, Brevo and others), `docker compose up -d`, and
   send a test email.

### Email bounces and complaints

With `ANYMAIL_WEBHOOK_SECRET` set and the provider's webhook pointed at `/anymail/<esp>/tracking/` (DEPLOYMENT.md section
15), a hard bounce, an invalid address or a spam complaint puts the address in Admin → Ops → Email suppressions, and the
site sends it nothing more (allauth's codes included). Soft bounces (a full mailbox) do not.

- **"I get no emails from you":** search the address there. Reason "hard bounce" or "invalid address": the student
  corrects the address on My account, or confirms that the mailbox works again; then delete the row (SUPPORT may).
  Reason "complaint": the student marked an email as spam; delete the row only when they ask for emails again, in
  writing.
- SES keeps an account-level suppression list too (hard bounces and complaints), copied here every night at 05:50
  (`ops.tasks.sync_ses_suppressions`): remove the address there as well (SES → Account dashboard → Suppression
  list), or SES drops the email anyway. The connections page's SES card shows the week's bounce and complaint rates
  against SES's limits (5 % and 0.1 %): above them, look for a bad list before SES pauses the account.
- Many suppressions at once (a typo in a bulk import, a provider outage reported as bounces): check a few with the
  provider, then delete the rows in the admin.

## SMS, phone numbers, passkeys and parental consent

### SMS

The site texts through MSG91 (`ops/sms.py`, `SMS_BACKEND=msg91`): log-in codes, the code that confirms a mobile number,
order updates for students who asked for them on My account, and parents' consent links. Every SMS is a row in
Admin → Ops → SMS log (kind, status, MSG91's request id, last 4 digits; the number itself is kept only as a keyed
hash). Search there with the whole number ("98640 12345") to see what went to it. Rows go after 90 days.

**DLT, before the first SMS** (DEPLOYMENT.md section 15 has the steps): Principal Entity ID, header (e.g. `EXMLEF`),
one template per kind, the URL whitelisted, MSG91 bound as telemarketer, the server's IP whitelisted for the authkey.
The carriers compare a message with its template character by character and drop it silently if they differ, so
register these texts exactly (`{#var#}` holds at most 30 characters):

| Kind (`.env`) | Category | Template text | Variables sent |
|---|---|---|---|
| `MSG91_TEMPLATE_OTP` | Transactional | `{#var#} is your ExamLeaf code. It is valid for 5 minutes. Do not share it with anyone. -ExamLeaf` | the code (MSG91 OTP API) |
| `MSG91_TEMPLATE_ORDER_PLACED` | Service Implicit | `Your ExamLeaf order {#var#} is confirmed. We will text you when it ships. -ExamLeaf` | `var1` order number |
| `MSG91_TEMPLATE_ORDER_SHIPPED` | Service Implicit | `Your ExamLeaf order {#var#} has shipped: {#var#}. -ExamLeaf` | `var1` order number, `var2` courier and tracking number |
| `MSG91_TEMPLATE_ORDER_DELIVERED` | Service Implicit | `Your ExamLeaf order {#var#} has been delivered. Thank you. -ExamLeaf` | `var1` order number |
| `MSG91_TEMPLATE_PARENT_CONSENT` | Service Implicit | `{#var#} has registered at ExamLeaf and named you as parent or guardian. To agree, open https://examleaf.in/c/{#var#}/ within 7 days. -ExamLeaf` | `var1` the student's first name ("a student" when the name is not plain letters), `var2` the link's token |
| `MSG91_TEMPLATE_ORDER_ARRIVING` | Service Implicit | `Your ExamLeaf order {#var#} is out for delivery today. Please keep Rs {#var#} ready for the courier. -ExamLeaf` | `var1` order number, `var2` the cash to collect ("638.00"); cash on delivery only |
| `MSG91_TEMPLATE_ORDER_NOT_DELIVERED` | Service Implicit | `The courier could not deliver your ExamLeaf order {#var#}. See your order: https://examleaf.in/orders/t/{#var#}/ -ExamLeaf` | `var1` order number, `var2` the order link's token (22 characters) |

In MSG91 the DLT variables become `##var1##`, `##var2##` (the OTP template: `##OTP##`); keep those names. If the DLT
portal wants the link as a `{#url#}` variable rather than in the text, register it so and tell the developer: the
code then sends the whole link as `var2` (about 50 characters).

The one OTP template serves two codes: a log-in code by SMS is valid for 3 minutes and the code that confirms a mobile
number for 5 (allauth's `ACCOUNT_LOGIN_BY_CODE_TIMEOUT`, left at its default of 180 seconds, and
`ACCOUNT_PHONE_VERIFICATION_TIMEOUT`, set to 300), while the template text says 5 minutes.

**The limits and the daily cap.** Every SMS is counted in the database before it goes (allauth's own limits, 3 log-in
codes an hour per address or number and 30 an hour per client address, live in Redis and let everything through while it
is down): one number gets at most 5 SMS an hour and 10 a day, one account 20 a day, and each purpose has a share of the
day's cap (log-in codes 70 %, order updates 30 %, parents' links 10 %). An SMS over a limit is not sent: its row reads
"not sent: a limit was reached", the log says which limit, the website answers 429 "Too many messages have gone to this
number: try again tomorrow, or log in with your email." and the parent's link says that it was not sent. A row that
reads "queued" is waiting for the worker. Last come the `SMS_DAILY_CAP` (default 500) SMS sent from midnight to midnight
(India time): when it is reached the SMS gets the same "not sent" row and Sentry gets "SMS_DAILY_CAP reached" (the only
limit that reaches Sentry). Then: look at the SMS log for one number or kind repeating (a bot pumping SMS: put Turnstile
on, DEPLOYMENT.md section 15; block its addresses at Caddy); if it is real growth, raise `SMS_DAILY_CAP` in `.env` and
`docker compose up -d`. Students can still log in with the password or an emailed code.

**Templates in the panel.** Settings → Templates holds each DLT template as registered (its text, ids, header,
typed variables, approval state); an approved SMS template's MSG91 id is used before `MSG91_TEMPLATE_<KIND>`, so a
new template id is set there (ADMIN) without a deploy. Send a test to your own confirmed number first. The inbox
warns 15 days before DLT would deactivate a template unused for 90 days (`template_idle`) and when its yearly
self-certification is due (`template_certify`).

**Delivery reports.** With MSG91's delivery report URL set to `https://examleaf.in/api/hooks/sms-events/` and the
token from the connections page (MSG91 → Webhooks), each SMS log row gets delivered, pending, failed or rejected
with MSG91's words ("Template Id not found on DLT", DND).

**"My code never came".** SMS log: no row (the number is not confirmed on any account, or the student typed another one;
log-in codes go only to a confirmed number), "refused by the provider" (Sentry has MSG91's reason: template, IP
whitelist, balance), "not sent: a limit was reached" (see above) or "sent" (ask MSG91's report with the request id: DND,
a switched-off phone). The student can always use "Log in with a code" with the email address instead.

### Finding a customer, and what the panel records of it

Customers (`https://admin.<domain>/users/`): search by an email address (exactly), a mobile number or its last digits, or
three letters of a name; the tabs Students, Parents (adult accounts a student named as their parent, by a verified
email address or number: not proof of parenthood) and Guest buyers (people who bought without an account, one row for
each email address). Contact details stay masked until revealed with a reason. The panel records every search for a
person (an `customer.lookup` event: a hash of what was typed, never the words), opening a record, its timeline and its
spending summary (`sensitive_read`; a student under 18's is marked), and every reveal. A record's **Timeline** tab lists
what happened to the account (orders, payments, refunds, codes, course access and use, tickets, texts and emails sent,
consent, notes, and what staff did to it); for a student under 18 the course is a count and the last week active,
never what they watched or answered. Break-glass, the panel down: Admin → Users, and the shell steps in this section.

### Logging in as a customer (support)

Only when seeing the customer's own pages is the way to answer them ("my cart is empty", "the course does not open"),
never for a student under 18 or a member of staff (the panel refuses both):

1. In the panel, the customer's page → Actions → "Sign in as this customer": a reason and the ticket it answers
   (SUPPORT, ADMIN, owners; it asks to confirm it's you, and the owners are told). "Start" gives a token valid 15
   minutes, which opens one session, once.
2. "Open the website as them" takes the token to the website's page for it (`/account/impersonate/?token=…`, which
   posts it to `/api/v1/account/impersonate/`) in the same browser, still signed in to the panel. Every page shows the
   banner ("Staff … until 10:45"); orders, payments, addresses, passwords, second factors, consent and deletion are
   refused, and every request is in the audit log as yours on behalf of the customer. The customer's device list shows
   "Staff (support) until 10:45".
3. End it when done: the banner's "End" (`DELETE /api/v1/account/impersonate/`) or the panel's "End it now". It ends by
   itself at its time, or when you sign out of the panel.
4. Note on the ticket what you saw and did; the audit log has `user.impersonation_started`, `…_accepted`,
   `impersonation.request` events and `…_ended`, each with the customer's id.

### Phone numbers and passkeys: support cases

A mobile number for log-in is added and changed on My account (the app can do the same through allauth.headless), after
an SMS code; one number belongs to one account. Staff find it in Admin → Users (the section "Log-in by SMS"; the search
box takes the number as kept, `+919864012345`); SUPPORT sees it, ADMIN changes it. The account is emailed when a number
is added to it, and the account that held the number before when it moves away.

- **Lost or changed phone:** the student logs in with the email (password or emailed code) and changes the number on
  My account. Without access to the email either: the usual identity checks of "A data request under the DPDP Act",
  then in the admin empty "mobile number for log-in" and untick both boxes.
- **The number belongs to someone else now** (a recycled number, a sibling, a parent's phone shared by two children):
  the second account cannot confirm it ("A user is already registered with this phone number."). Call the number from
  the support phone: if the person who answers is the claimant, and the first account's owner agrees by email or does
  not answer within a week, empty the number on the old account in the admin; the claimant then adds it again. Never
  move a number without such a check: the number opens the account.
- **Order SMS unwanted:** My account → untick "Text me when an order is placed…", or staff untick "order updates by SMS".
- **Passkey lost (phone replaced):** the student logs in with the password or a code and removes the old passkey under
  My account → Passkeys. Staff: as "Staff accounts" (a superuser removes the authenticator in Admin → MFA).

### Parental consent

`PARENTAL_CONSENT_MODE=declared`: a parent ticks the box on the sign-up form. `verified` (switch before May 2027,
DEPLOYMENT.md section 14): a student under 18 gives a parent's email, the parent gets a link valid for 7 days (sent once
the student has confirmed their own address), and the account can read but not save marks or order books until the
parent presses "I agree". Admin → Consent records then shows the confirmation ("confirmed through the link emailed to
the parent", with the time).

- **Who is waiting:** the panel's Customers → **Waiting for a parent** (`https://admin.<domain>/users/consent-pending/`)
  lists the students under 18 whose parent has not confirmed, the first to register first: the parent's contact
  (masked, with whether the link goes by email or text), how many links were sent, when the last one went and when it
  stops working (7 days), how many went today of the day's 3, and whether the account only reads until a parent
  confirms. Opening a student's record there is recorded as a look at a child's data. After the switch to `verified`
  this includes students under 18 who registered before it; email them that a parent must confirm. The Legal and
  privacy cockpit lists the deletions that wait for a parent. Break-glass, when the panel is down:
  `dj shell -c "from accounts.models import User; print([u.pk for u in User.objects.filter(is_active=True, date_of_birth__isnull=False) if u.consent_pending])"`
  (the accounts' numbers; open each in the panel when it is back).
- **Sending the link again from the panel:** the student's record (or the list above) → "Send the link again". A text
  to a parent's mobile number goes from 08:00 to 21:00 India time only (the panel says so out of hours; an email goes at
  any hour), and one address or number gets 3 links a day, whichever students ask: the panel then says the parent has
  had their links for today. Each link sent is kept with who asked for it for a year (`parent_links` in the retention
  schedule).
- **A parent who cannot use the link (no email, a shared phone, a letter instead):** check the parent yourself first, by
  a call to the number on record (the panel masks it: reveal it with a reason), their own verified ExamLeaf account, or
  a DigiLocker token, then Customers → the student → "Record the consent by hand": how it was checked, **where the
  evidence is** (a ticket's number, the date of a letter: never the document, never an email address or a number, which
  the panel refuses), and why. It asks you to confirm it's you, clears the student's flag at once, tells the parent by
  email where the contact is one (so that a consent they never gave is noticed), and is in the audit trail
  (`user.consent_verified`) and in Admin → Consent records (the record's page shows who recorded it and the reference).
  It is refused for an adult, for a
  student whose deletion waits for the parent, and when a parent has confirmed already.
- **Many students at once** (a school's, after the switch): the list's bulk bar sends the parents' links again, signs
  students out everywhere, or suspends. Each is checked first (a count of what would change and what would be left
  alone, and why); with a student under 18 among them, whatever the number, a second person (ADMIN or an owner) approves
  it before it runs. Never a deletion.
- **"My parent never got the link":** the student checks the address and sends it again from My account (also to a
  corrected address; one link every 10 minutes; a link sent to an old address stops working). One parent address or
  number gets at most 3 links a day, whichever students ask: then the page says "The link was not sent: that address or
  number has had several today. Try again tomorrow." The message is fixed text; the student's name is in it only when it
  is plain letters (otherwise "a student").
- **A parent without email:** with SMS on (`SMS_BACKEND=msg91`), the student gives the parent's mobile number instead
  and the link goes by SMS (`/c/<token>/`; Consent records: "confirmed through the link texted to the parent"). Who
  receives a link, by email or SMS, is not proof that they are the parent: the DPDP Rules, 2025 (rule 10) ask for
  verification through reliable identity details or a token (such as DigiLocker), which the site does not do yet;
  record this limit in the consent assessment. Without SMS the account stays read-only.
- **A parent who does not agree:** delete the account on request ("A data request under the DPDP Act").

## The shop

Orders are found in the panel's Orders (`https://admin.<domain>/orders/`, shop/README.md): search by order number, an
invoice's or credit note's number, email, name, a phone's last digits, tracking number or book code (a search for a
person is recorded in the audit trail by its hash); the tabs To pack, Shipped, Returns, Cancelled and Drafts; an order's
record lists its books with what each was invoiced at, payments, refunds, documents, parcels, its hold and tags, and its
timeline. The Django admin (Shop → Orders) stays for superusers and break-glass sessions, with the shell steps below
as the fallback when the panel is down.

Who does what (`accounts/roles.py`, which every `migrate` syncs and `dj bootstrap_roles` does by hand; in words, each
role's guide in `../docs/guides/roles/`): SALES takes the orders (staff orders within 20% off, payment links, offline
payments within ₹5,000, refunds within ₹2,000, returns, notes), prices and stock, coupons and offers, reviews and
quotations; SALES_REP makes staff orders and quotations within 10% off and sends payment links, no more; PACKER has the
packing queue and nothing of the customer; FINANCE approves money above the makers' limits (refunds, offline payments,
prices, coupons and staff discounts), keeps the tax documents and Razorpay's settlements, and reads the orders; SUPPORT
sees orders and answers about them, asks for refunds within ₹1,000 and for returns, and opens courses by hand;
CONTENT_EDITOR keeps the product pages, shelves and pictures and the course content; MARKETING drafts coupons and offers
(beyond 20% off FINANCE approves); ADMIN everything except the superuser-only items, which it can view (periodic tasks,
task results, groups and permissions, second factors, Google sign-in), the owners' own (giving roles, API keys, the
audit log) and money's approvals, imports and exports included; the owners all but the superuser-only changes; the
AUDITOR reads.

The catalogue is kept in the panel's Catalogue (`https://admin.<domain>/catalogue/`, shop/README.md "Catalogue"): each
part of a product by its own people (the page CONTENT_EDITOR and SALES, the prices SALES through their approval, the
tax FINANCE, the stock SALES), coupons and offers by MARKETING and SALES through theirs (beyond the maker's discount
limit FINANCE approves from the inbox), delivery rates, shelves and collections. In the Django admin the prices, the
tax, new products, the product import, coupons and offers are a superuser's alone (a break-glass session's, when the
panel is down); everyone else reads them there.

### A stuck payment (the customer paid, the order still says "awaiting payment")

Razorpay's webhook normally completes an order within seconds, even when the customer never comes back from the payment
page. If it did not:

1. The panel: Finance (`https://admin.<domain>/finance/`) → "Payments stuck at Razorpay" lists them (an online payment
   started or authorised 15 minutes ago, `SHOP_STUCK_PAYMENT_MINUTES`, on an order still unpaid; or one captured on an
   order still pending), or Finance → Payments, searched by the order number or Razorpay's `pay_…` id. Open it and
   press "Ask Razorpay again" (FINANCE, ADMIN, the owners: `staff.replay_webhook`): the answer says what changed ("the
   order is paid now; payment 9101 recorded as captured", or "Razorpay has no captured payment for this order"). An
   authorised payment is captured first; the nightly run (02:30) does the same for every order still waiting.
2. Without the panel: Razorpay Dashboard → Payments: find the payment (the customer's UPI ID or phone, the amount). The
   receipt of its order is the order number. Note its status: captured, authorized or failed. Then
   `dj reconcile_payments` asks Razorpay about every online order still awaiting payment (older than 10 minutes; the
   staff orders' links included) and records the payments it took: `EL-2026-000123: paid now`. An authorized payment
   is captured first (when the amount matches). "no payment at Razorpay": it has none for that order (the customer did
   not pay, or paid another order). "Razorpay could not be asked": try again later.
3. Why did the webhook not arrive? Dashboard → Webhooks → the delivery log shows what the site answered. 400: the secret
   differs from `RAZORPAY_WEBHOOK_SECRET` (live) or `RAZORPAY_WEBHOOK_SECRET_TEST` in `.env` (correct it,
   `docker compose up -d`, resend the event). No attempts at all: the URL or the events are not set (DEPLOYMENT.md,
   section 12). Timeouts: the site was down.
4. Orders never paid within two days are cancelled by the 04:30 clean-up, which asks Razorpay first: a payment that was
   missed is recorded, not cancelled (an order that staff made, with a payment link, gets 16 days and the link is
   checked the same way). A payment that reaches an order already cancelled (or whose books or coupon are gone) is
   refunded in full by the site, and the customer is emailed.

### "I have not got my refund"

1. Admin → Refunds, find the order. *processed* with a date: Razorpay has refunded it; give the customer the Razorpay
   refund ID (`rfnd_…`) and the date (banks take 5–7 working days; UPI is often quicker). *requested*: the task is
   waiting (Razorpay was unreachable: it retries for up to about three hours and the daily clean-up queues it again).
   *failed*: Razorpay refused it, the reason is in the Refund's error (a payment too old to refund, a balance too low
   ...): fix the cause, then use the order's action "Refund through Razorpay" again (a failed refund does not block a
   new one; on a paid or packed order that action cancels the order). The admin's refund is the panel's: within your
   refund limit (`ROLE_LIMITS`: ADMIN ₹10,000) it runs at once; above it the message names a change request that
   FINANCE (or an owner) approves in the panel, and nothing is refunded until then. "Cancel" on an order paid online is
   the same refund.
2. Cash-on-delivery orders, and payments recorded offline, are refunded by bank transfer or UPI: the order's Refund in
   the panel, "By bank transfer or UPI", with the customer's UPI ID or account (kept encrypted, shown masked). It waits
   for FINANCE (an inbox item due in `SHOP_BANK_REFUND_DAYS`): on the order's Refunds, "Show the account" (with a
   reason, recorded), transfer it from the business account, then "Mark paid" with the UTR: the refund is made, the
   customer emailed with the reference and the credit note issued, once. An online payment goes to a bank account only
   when the customer agrees (tick it in the dialog), for instance a payment older than 6 months that Razorpay refuses.
3. Part of an order (a damaged book, a refused parcel less the shipping): the refund dialog's copies of each book (from 0)
   and the shipping, the amount from what each book was invoiced at (its share of the coupon and offers taken off), and
   whether the copies go back into stock. An order not yet sent is cancelled and refunded in full. Above your refund
   limit FINANCE approves it first (the dialog shows the change request).
4. A refund made in the Razorpay Dashboard is recorded when its webhook arrives ("Refunded in the Razorpay dashboard."):
   the order turns "refunded", the customer is emailed and the credit note is made. Stock is not put back by itself:
   correct it in Products.
5. Every refund of an invoiced order has a credit note (on the order's record, and admin → Credit notes), bank refunds
   included once marked paid. Without the panel: `dj shell -c "from shop import services; from shop.models import
   Refund; services.mark_bank_refund_paid(Refund.objects.get(pk=<id>), '<UTR>')"`.

A refund whose answer was lost (Razorpay slow) is never sent twice: each retry first asks Razorpay for the payment's
refunds and takes over the one that carries the site's refund number in its notes.

### A customer paid twice

Razorpay can capture a second payment for an order that is already paid (a late UPI approval, a second tab). The site
records it as a payment of its own and refunds it in full by itself: the error log (Sentry) says "Razorpay payment pay_…
is a second payment for order EL-…; refunding it", the order lists a second payment and a refund ("Paid twice: the
second payment is refunded."), and the customer gets the refund email. The order stays paid by the first payment.
Nothing to do, except to check in the Dashboard (Refunds) that the refund went through, and to reply to the customer
with the `rfnd_…` ID if they ask. If the refund failed (admin → Refunds, *failed*): refund that payment in the Razorpay
Dashboard (its webhook records it); do not use "Refund through Razorpay" on a paid or packed order for it, which
cancels the order.

### Test mode and live mode

Every payment and order records the mode of the Razorpay keys that made its Razorpay order (`livemode`). The panel
shows it: on a live site an order of the test keys has the chip "Test" and stays out of the lists, the counts and the
packing queue unless the Orders list's filter Mode asks for "Test orders"; on a site that runs on test keys the TEST
band is above every page and Home and Finance say that every number is of test orders. The site trusts only its own
mode: with live keys, a test-mode payment, its webhooks and its refunds change nothing (logged: "… (test mode)
ignored"), and a test-mode order cannot be packed or shipped ("Not possible for EL-… (a test order)"). Its invoice and
credit notes stay in the test series (`T/`, `TC/`) whenever they are made. Webhooks are checked with the secret of the
keys' mode: `RAZORPAY_WEBHOOK_SECRET_TEST` for `rzp_test_` keys, `RAZORPAY_WEBHOOK_SECRET` for live ones, or the
connection's own once the panel holds the keys ("Connections", below).

Going live (the steps are in DEPLOYMENT.md, section 12):
1. **In the panel** (ADMIN, OWNER), if Settings → Connections → Razorpay already holds the keys: "Replace the keys" for
   the mode Live with the live key id (it starts `rzp_live_`) and secret. They are tested first and kept only if the test
   passes (the old ones stay in force otherwise); the audit log has `connection.credentials_replaced` with the last four
   characters, and the owners are emailed. Then "Mode" → Live (`connection.mode_changed`: live takes real money and sends
   real messages; the owners are told), and "Rotate the token" under Webhooks, pasting the new secret into Razorpay's live
   webhook within 24 hours (`connection.webhook_rotated`). Then Settings → "The shop is open" on (`SHOP_OPEN`).
   If the panel holds no Razorpay keys yet, the first it takes must be of the mode `.env` runs (the test keys): give it
   those first, so that it takes over without stopping anything, and the live ones after that.
   **Or in `.env`:** the live keys and the live webhook's own secret (`RAZORPAY_KEY_ID=rzp_live_…`,
   `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`); keep `RAZORPAY_WEBHOOK_SECRET_TEST`. `SHOP_OPEN=1`.
   `docker compose up -d`.
2. Test orders still pending and older than two days are cancelled by the 04:30 clean-up (the live keys see no payment
   for them). Leave paid test orders as they are: they count nowhere in the tax series, and cancelling one would ask the
   live account to refund a test payment, which cannot work (the refund stays "requested" and is queued again every
   night).
3. Back to test keys (a rehearsal): the same in reverse (Mode → Test); live orders then show nothing special but their
   payments and webhooks are ignored until the live keys are back. Do not take real orders meanwhile: turn "The shop is
   open" off (`SHOP_OPEN=0`).

Orders made before this mode was recorded (the security release) count as test orders. If the shop had already taken
real payments before it, no panel page marks them live: this is a one-off for the shell, with the first live order's
number:
`dj shell -c "from shop.models import Order, Payment; o = Order.objects.filter(number__gte='EL-2026-000123', placed_at__isnull=False); Payment.objects.filter(order__in=o).update(livemode=True); print(o.update(livemode=True))"`.

### Razorpay settlements (every morning; the panel's Finance → Settlements)

Every morning at 03:15 the site fetches yesterday's settlements from Razorpay's settlement recon API (the keys in force:
live or test, never both), keeps each settlement and line once, matches each line to its payment, refund or B2B link
by Razorpay's id, and posts each settlement that matches to ERPNext once (a Journal Entry: Razorpay Clearing to the
bank, the fees an expense, the GST on them input credit; while `ERP_SYNC_SETTLEMENTS` is off the matched ones wait and
the next morning posts them). A payment Razorpay settled that the site never heard of (a lost webhook), on one of our
orders, is asked of Razorpay first and recorded. Razorpay unreachable: the run tries again for about three hours.

1. A settlement that does not match opens an inbox item for FINANCE ("Razorpay settlement setl_… of 09 Oct 2026: 2
   lines not ours yet", or "Razorpay's net … is not its lines' …"), and Finance today counts its lines. Open it
   (Finance → Settlements → "Does not match"): its lines, "Not matched" first.
2. A payment line: "Match", the payment's number (Finance → Payments: search the line's `pay_…` id or its receipt, the
   order number; ask Razorpay again first if the payment is stuck) and why. A refund line: the refund's number. An
   adjustment (a fee reversed, a dispute's hold): "Accept" with why. Each is an audit event with your note; once nothing
   is left the settlement turns "Matched" and is posted.
3. A net that differs with every line matched: Razorpay's figure and the lines disagree. Compare Razorpay Dashboard →
   Settlements → that settlement's transactions with the page's lines; write to Razorpay's support with the
   settlement id. Do not post by hand while it waits: once Razorpay has corrected it, fetch its day again (step 4),
   and the settlement takes Razorpay's latest figures and is evaluated anew.
4. A day the morning run missed (Razorpay was down for longer, the site was off): Finance → Settlements → "Fetch a day"
   (a dry run first if you like: it keeps nothing), or `dj fetch_settlements --day 2026-10-09` (`--dry-run`). Fetching a
   day twice changes nothing.
5. Posted settlements are never changed here: a line that turns up after its settlement was posted opens the inbox
   item again, and the Journal Entry is corrected in ERPNext by hand (ERPNext → Journal Entry, the settlement id is its
   reference).
6. Monthly, as a check: the settlements' net (Finance → Settlements, the month's days) against the bank account's
   credits by UTR. Disputes and chargebacks are not fetched yet ("Disputes: not set up" on Finance today): Razorpay
   Dashboard → Disputes, answered with the invoice, the tracking number and the delivery date from the order page.
7. Invoices and credit notes are numbered one after the other in each financial year (`EL/2026-27/00001`,
   `CN/2026-27/00001`; from FY 2027-28 one series a type: "Tax: rates, documents, series") and a number is never
   reused. Test-mode documents are in their own `T/` and `TC/` series: not for
   the tax return. Cash on delivery: the courier remits the cash it collected (less its fee) some days after delivery;
   match its report with the tracking numbers (the payment is recorded as captured when "Mark delivered" is pressed).

### An invoice or credit note is missing

The order page says "The invoice will appear here in a few minutes" for a paid online order (cash on delivery: the
invoice is made when the parcel is marked shipped). Look in `docker compose logs worker | grep -i invoice` (or Sentry).
The usual cause is the seller's details: while `SELLER_ADDRESS`, `SELLER_EMAIL` or `SELLER_PHONE` still hold their
`[placeholder]`, no real invoice is numbered ("SELLER_* still holds placeholders"): set them in `.env` and
`docker compose up -d`. The 04:30 clean-up then makes what is missing, or at once: the order's Actions in the panel,
"Make missing documents" (its invoice and credit notes; "Email the invoice again" sends its link). Without the panel:
`dj shell -c "from shop.tasks import generate_invoice; generate_invoice(<order id>)"` (the id is the number in the
order's address in the admin). WeasyPrint failing (fonts, Pango) is in the same log. A missing credit note is made the
same way: `dj shell -c "from shop.tasks import generate_credit_note; generate_credit_note(<refund id>)"` (the id is the
number in the refund's address in the admin); the 04:30 clean-up makes missing ones too. A credit note is never made
after 30 November following its invoice's financial year, nor against a cancelled invoice: the refund still went out,
and the inbox has a "No credit note for refund #…" item with the reason; record what the CA decides on the order as a
note.

### Guests and their order links

Every order email except the delivery one carries its link (`/orders/t/<22 characters>/`): it opens the order without an
account, read only, with its invoice and, until it is packed, a cancel button. A guest who lost the emails uses "Find
your order" (order number and email address): the link is emailed to the order's address, and the page always answers
"If an order matches, we have emailed you a link." (10 tries an hour per address, per email address and per order
number). Orders of accounts are not found there: their owners log in. Never send an order's link to any other address
than the order's.

### Shipping with tracking links

Packing, shipping and delivery need `staff.pack_order`: PACKER's, ADMIN's and the owners' (SALES no longer has them).
In the panel the packing room works from Orders → Packing (`/orders/packing/`, the orders to pack oldest first, what to
pick and the cash to collect): "Mark packed" (five seconds to undo; the bulk bar does many), then Print for the packing
slips (A4), the 4×6 labels of parcels sent by hand and the pick list. For a parcel that goes by hand (India Post, a
courier without our booking) open the order → "Send by hand": choose the courier, type the tracking number (AWB) and
leave the tracking address empty, then "Mark sent"; later "Mark delivered". The audit log has `order.packed` and the
order's own events; a booking with a courier through Shiprocket is not in the console yet (its pages are the next
phase's: `/shipping/` says so), so those use the staff API (API.md "Shipping (staff)").

The site fills the tracking address in: Delhivery, Blue Dart and Ekart open their own tracking page; India Post (its page
needs a CAPTCHA), DTDC, Xpressbees and "another courier" open 17TRACK with the number. The customer's email carries the
link (the SMS, when they asked for SMS, gives the courier and the tracking number), and the order page shows it. Type a
link yourself only for a courier whose page you know takes the number in the address. A wrong number: correct it in the
order's Shipments; correct the link too (empty is not refilled there). The first time each courier is used, open the
emailed link once with a real number to check it. If the panel is down, ADMIN does it in the Django admin: Orders →
select the packed orders → "Mark shipped", with the same fields.

This stays the way for India Post and any courier without an API. A parcel booked with a courier through Shiprocket
(`shipping/`) is shipped and delivered by the courier's own scans instead, and its row on the order's page is read
only: see "Couriers and integrations". A consignment above ₹50,000 needs an e-way bill.

### GST returns (GSTR-1 export)

Each month (or quarter under QRMP), for the accountant: the panel's **Tax → GSTR-1**, choose the month (or the quarter
ending with it) and Run (FINANCE, `staff.run_gstr1`); the job reads the period's documents and gives a zip of CSV
files in the GST Offline Tool's templates, through its download link (kept a week; above FINANCE's export limit ADMIN
approves first). **Tax** shows what is due this month (the calendar) and the threshold card; **Tax → Series** is table
13. The files:

- `…-b2cl.csv` (table 5): invoices above ₹1 lakh with taxed lines to another state, by rate.
- `…-b2cs.csv` (table 7): the other taxed sales by place of supply ("18-Assam") and rate, net of their credit notes.
- `…-cdnur.csv` (table 9B): credit notes against b2cl invoices.
- `…-exemp.csv` (table 8): exempt, nil-rated and non-GST supplies (the books and the shipping that follows them), intra-
  and inter-state, to unregistered buyers, net of their credit notes. Books go in "Exempted" until the CA says "nil
  rated" (plan 10.2).
- `…-hsn-b2c.csv` (table 12, B2C tab): quantity, value, taxable value and tax per HSN code (to `SHOP_HSN_DIGITS`
  figures) and rate, with the code's unit, net of credit notes; `…-hsn-b2b.csv` stays empty (no registered buyers on
  the storefront: they order through Sales in ERPNext).
- `…-docs.csv` (table 13): each series' first and last number, how many, how many cancelled.
- `…-credit-notes.csv`: every credit note of the period with its invoice, by rate, for the working.

Only the real series is exported, never test-mode documents; a cancelled document counts in table 13 only. Amounts are
those printed on the documents (prices include tax; the coupon, offers and a staff discount shared over the lines; the
shipping taxed with the goods it carries). Orders the site does not invoice (a school order paid outside the site and
never entered as a staff order) are not in the files; staff orders are.

Break-glass, without the panel:

    docker compose exec web python manage.py export_gstr1 --from 2026-10-01 --to 2026-10-31 --out /tmp/gstr1
    docker compose cp web:/tmp/gstr1 .

### Tax: rates, documents, series

All in the panel's **Tax** module (FINANCE; AUDITOR reads):

- **A rate changes** (a CBIC notification): Tax → HSN and SAC codes → the code → "A new dated rate": the rate, its
  taxability, the day it starts, the notification and its serial number. It starts after the code's latest rate (the
  history is never rewritten); orders from that day are taxed at it, older documents keep theirs. Products on the code
  take the new rate when next saved; until then their red chip says they disagree (Tax → HSN and SAC codes lists
  them). A new code: "Add a code" with its first rate.
- **A document issued in error**: Tax → Documents → the document → Cancel, with the reason, typing its number. It keeps
  its number (table 13 counts it cancelled), leaves the returns and its PDF is marked cancelled; cancel an invoice's
  credit notes first. The order and its refunds are not changed. A document already in a filed GSTR-1 is corrected by a
  credit note instead (ask the CA).
- **Before 1 April 2027**: the CA confirms the prefixes of the series each type gets from FY 2027-28
  (`SHOP_SERIES_PREFIXES`, DEPLOYMENT.md "Tax"); set them before the year's first document, and check ERPNext's B2B
  series use none of them. The `EL` series closes with FY 2026-27.
- **The threshold monitor's inbox items** (`tax_threshold`): turnover past ₹2 crore means GSTR-9 is due for the year;
  past ₹4 crore, plan e-invoicing and monthly returns with the CA; past ₹5 crore, set `SHOP_HSN_DIGITS=6` from the next
  year, leave QRMP (Settings, `SHOP_GST_QRMP`) and switch India Compliance's e-invoicing on. A large invoice to another
  state goes to table 5 (the export does it); a parcel of taxable goods above ₹50,000 may have needed an e-way bill.

### Coupons

Catalogue → Coupons in the panel. A coupon's uses are the paid or placed orders not cancelled or refunded; the list
shows how many. To stop one at once, open it and untick *Switched on*, with the reason (`coupon.change`, made at once;
switching one back on beyond your discount limit waits for FINANCE); orders already made keep their discount. A
coupon may cover chosen products or shelves (and leave some out), be for a first order, or not stack with the
automatic offers. Its code never changes: make a new coupon instead.

**A school's single-use codes**: make the coupon with *Single-use codes* ticked (its own code then no longer works at
the cart), open it, and under *Single-use codes* give how many, a prefix (the school's short name) and the school's
name: a job makes them (above your bulk limit an approver passes it first) and *Download the file* gives the school's
CSV (the link lasts 5 minutes; the file a week). Each code works for one order: the order made with it takes it, and
a cancelled order frees it for another. "This code has been used" at the cart is that rule.

When the panel is down, a superuser changes a coupon in the admin (Shop → Coupons); its codes are under Shop → Coupon
codes, read-only.

### Offers

Catalogue → Offers in the panel (the admin's Shop → Offers is a superuser's): automatic discounts, no code. A
countdown needs a real end date, and once shown its end can come sooner but never later; names and banners are checked
for false urgency and guilt-trip words (`SHOP_DARK_PATTERN_PHRASES`): the refusal names the pattern, so say what is
offered and the day it ends. Per cent or rupees off what the offer covers ("on": the whole cart, chosen
products, the products of chosen categories with their sub-categories, or of chosen collections), once those reach the
minimum copies and the minimum value (leave one at 0 to ignore it; after the coupon), between two dates, with limits of
orders in all and per customer. They apply after the coupon and show as their own line, under the offer's name, in the
cart, the checkout, the emails, the order and the invoice. "With coupons and other offers" off: the offer applies alone,
never with a coupon; without a coupon the customer gets whichever saves more, all the combinable offers together or the
best single one. The "used" column counts orders placed (paid, or cash on delivery placed); the limits are checked when
the order is made and again, under a lock, when it is paid or placed, so the order that comes second after the last use
is refused (an online payment is refunded and the customer emailed). Each order line keeps its share of every discount,
and invoices and credit notes print those shares (orders made before offers existed keep the split they were invoiced
with).

### Staff orders and payment links

For a phone order or a school's quotation accepted: the panel's Orders → New order (`/orders/new/`): how it came,
the books (found by title or ISBN), the customer's email and address, a discount in rupees and the shipping; what it
comes to and whether it is made at once (within your `discount_percent` of the books) or waits for FINANCE (above it,
or a ₹0 order: nothing exists until approved) show before you save. The payment link is sent, sent again or cancelled
from the order's Actions. The owners get the week's staff discounts, offline payments and ₹0 orders by email on Monday
at 08:00. The Django admin's way stays for superusers: Orders → "Add order" (the button reads "Add order"; it opens "New
phone or school order"): the customer's email (an account whose confirmed address it is gets the order: needed for a
course), the delivery address, the products and copies (rows left empty are skipped), a discount in rupees (after the
offers), the shipping (empty: the shipping rates'), an internal note. With "Email a Razorpay payment link now" ticked,
Razorpay makes a Payment Link for the total and we email it; the action "Email a Razorpay payment link" sends the same
link again. When the customer pays, Razorpay's `payment_link.paid` webhook pays the order: copies taken, confirmation
email, invoice, as for the website's orders (a book sold out meanwhile: cancelled and refunded, as there). A link
lives 15 days; a staff order not paid in 16 days is cancelled by the daily clean-up, which first asks Razorpay
whether its link was paid. The order list's filter "created by → not empty" lists the staff orders.

Every link, its state (open, paid, cancelled, expired), when it was sent and when it ends: Finance → Payment links.
SALES, ADMIN and the owners (`shop.change_order`) make one, send an open one again and cancel it, and copy its address
(SALES_REP does it from the order's own Actions); FINANCE and SUPPORT read the list, and FINANCE asks Razorpay again about
a B2B invoice's link and records its ERPNext entry (below).

A customer says the link was paid and the order still waits (the webhook was lost): open its payment (Finance →
Payments, the order number) and "Ask Razorpay again". Without the panel:
`dj shell -c "from shop import payments; from shop.models import Order; print(payments.reconcile(Order.objects.get(number='EL-2026-000123')))"`
records the payment if the link was paid (`True`), `False` means nothing was paid, `None` that Razorpay could not be
asked.

**A B2B invoice of ERPNext paid by link** (a school's or a bookshop's invoice, made in ERPNext and copied to the
platform while `ERP_PULL_B2B` is on): Finance → Payment links → Make a link → "A B2B invoice in ERPNext" and its name
(`ACC-SINV-2026-00007`): the link is made for what is outstanding and its address shown; copy it and send it to the
customer yourself (the platform keeps no B2B customer's contact). When it is paid (the webhook, or "Ask Razorpay
again" on its row) an inbox item "Post by hand in ERPNext: invoice … paid ₹…" waits for FINANCE: ERPNext's sync
cannot post a payment against an invoice it did not get from the platform, so in ERPNext make the Payment Entry
(Receive, the customer, the invoice, the amount, the reference `pay_…` and its date), submit it, then on the link's row
"Record the ERPNext entry" with its name (`ACC-PAY-2026-00012`): the item is done and the link shows "Posted". The
settlement that carries the payment matches it to the link by itself.

### Payments received offline (NEFT, IMPS, UPI)

1. Check on the bank statement that the whole total has arrived; note its reference (UTR or UPI reference).
2. The order's Actions in the panel → "Record a payment" → the reference and a reason (above your `offline_inr` FINANCE
   approves it first). In the Django admin: Orders → tick the order (one) → "Record a payment received offline" → type
   the reference → "Record the payment".
3. The order is paid (copies taken, the customer emailed, the invoice made with "bank transfer or UPI to our account,
   reference …"). Refused if the order is no longer waiting for payment or a book has sold out (nothing recorded).
4. Above the recorder's limit it waits for FINANCE: Finance → Offline payments → "To approve" (or Finance today's
   "Offline payments to approve") lists them with their UTR; open one, check the UTR and the amount against the bank
   statement, and approve it (or refuse it with why). The recorded ones are the same page's "Recorded".

Refunds of such payments go by bank transfer or UPI through the refund dialog ("I have not got my refund", above).

### Notes, the customer page, the dashboard

- **Notes** (an order's page, "internal notes"): what was promised on the phone, a school's purchase order. Signed with
  your name; the customer never sees them; changes to a note are kept in the database, but the admin shows no history
  page for them. They are deleted with the order's customer details (eight years on, or 30 days after an unpaid order's
  cancellation).
- **The customer page**: in the panel it is Customers (`/users/<id>/`, "Finding a customer", above): the record, its
  Timeline tab and what they bought, each part for staff allowed to see it. The Django admin's customer page (an
  order's "customer" link, accounts only) gathers the same for a break-glass session.
- **The dashboard** (admin home) adds sales by day for two weeks, the five most sold books of the last 30 days, the
  books running out (below `SHOP_LOW_STOCK`), and the reviews and quotation requests waiting. Stock alerts (who waits
  for which book) are under Shop → Stock alerts. Its numbers are the panel's Home's (`insights/metrics.py`), without
  test-mode orders, and each waiting item shows only to whoever may open its list.

### Categories, collections, attributes

- **Categories** (the panel's Catalogue → Categories; the admin's Shop → Categories too) form a tree: a new shelf
  under another or at the top, and *Move* (under a shelf, first or last, or just before or after one) takes its
  sub-categories along; in the admin, drag a row. A product is put on its shelves in its own form
  ("Shelves, type and related products"), several allowed; a category's page (`/shop/category/<slug>/`) shows the
  products of its sub-categories too. The shop's main page lists the top categories.
- **Collections** are hand-picked lists ("Board 2027 essentials"), in the panel's Catalogue → Collections (the
  products' addresses one a line, in their order) or the admin; the collection's own number gives the order of the
  collections. Untick "shown" to hide
  one (its page then answers 404).
- **Product types** say which attributes their products have (a printed book: edition year, language, board…). Each
  attribute has a code (the app's filter `?attr_<code>=`; do not change it once the app uses it) and a kind: text,
  number, one of a list (one choice per line) or yes/no. Give a product its type, save, then fill in the attribute
  rows; a value of the wrong kind, or an attribute of another type, is refused. They show under "Details" on its page.
- **Related products** (both ways) show as "You may also need" on each other's pages.
- **Changing a slug** (a product's address): the old address keeps working, redirecting (301) to the new one; the
  product's form lists its earlier addresses. Another product may take an old slug: then that address is its own.
  The slugs `category`, `collection` and `school-orders` are refused (pages of the shop).
- **Product pictures** keep their `position` numbers (no drag and drop: django-admin-sortable2 does not support Django
  6.1 yet).
- **Bulk actions** on Products in the admin: "Put on sale", "Take off sale", and "Set stock": type the copies in the
  box beside the action, tick the books, run it (bundles and digital products have no copies of their own and are
  skipped). The panel sets one product's copies with the reason (below, "Stock").
- **Spreadsheets (ADMIN):** the panel's Catalogue → Import and export. The import takes the admin's export format (with
  the courier's columns `length_cm`, `width_cm`, `height_cm`, `packaging`), matched by slug: *Run the dry run* says
  what each row would make, change or leave and why a row is refused, and *Apply* (within a day, the same file) saves
  each row through the panel's rules: a price beyond your discount limit waits for FINANCE, stock and the GST rate are
  never imported. The export takes the list's filters and escapes cells that would start a formula; above your export
  limit an approver passes it first. The admin's own product import is a superuser's now (its export stays, logged);
  Categories → Export/Import in the admin: one row per category, a parent before its children (`parent` is its slug);
  an import adds new categories and renames, it moves none. Every export is written to the admin log.
- **Weight and size for the courier**: a book or a bundle of books needs its weight (grams, one copy as posted) and a
  packaging kind (a flyer, the default) or its three dimensions; a box needs its dimensions. The panel's Products
  with *Courier data missing* (`?incomplete=true`), and the home's card, list those still to weigh.

### Digital products (the revision course)

A product of kind "Digital (in the app)" opens the course of the `learn` app in the buyer's account once paid ("The
revision course" below): a pass alone, or in a bundle with a book (the bundle's copies are the book's). Customers need
an account, pay online (no cash on delivery), buy one at a time and pay no shipping for it; an order of digital products
only is marked delivered at once (no packing). Cancelling a paid order, or refunding it in full, closes the course again
(a part refund does not). A bundle of digital products only (a pass for two subjects sold as one) is a course too: no
shipping, nothing to pack, delivered once paid. Set the SAC code and GST rate your accountant gives (the form refuses
4901, the books' HSN).

## Connections

Settings → Connections (`https://admin.<domain>/settings/connections/`; ADMIN and the owners act, FINANCE and the auditor
read; `integrations/README.md` "The connections page", API.md "Connections (staff)") has a card for each service
ExamLeaf calls or that calls it back: Razorpay, Shiprocket, the manual carrier, MSG91, WhatsApp (not before Phase D), Amazon
SES, the storage buckets, the error tracker, Google sign-in and ERPNext. A card opens to its own page, with the
provider's webhooks, the events received, the calls made and the dead letters.

**Reading a card.** Its status is "Working", "Trouble" (a fifth of the day's calls failed, of at least five), "Keys
refused" (the provider answered 401 or 403), "Switched off" or "Not set up". Beside it: the mode (Off, Test, Live);
where the keys come from ("Keys held here" or "Keys from the server's environment") and the last four characters of each;
"Rotate the keys within N days" (90 days after they were set: our policy); the last test; the circuit ("Calls go
through", "Calls wait", "One trial call"); the day's and the week's calls with the failures and the time 9 in 10 answered
within; and what the provider adds: Razorpay's last webhook, MSG91's texts sent today against the daily cap, SES's bounce
and complaint rates against its limits (5 % and 0.1 %), the buckets, ERPNext's rows waiting and dead letters.

**What the page does**, each an audit event and each telling the owners by email (`staff.manage_connections`: ADMIN and
the owners, who confirm it's them first):

- **Test the connection** (`connection.tested`): one harmless authenticated read with the keys in force, kept on the
  account with when and what it answered.
- **Replace the keys** (`connection.credentials_replaced`, or `connection.credentials_refused` when the test failed): the
  new keys are tested in the same step and kept only if the test passes, so a mistyped key never replaces a working one.
  The audit event holds their last four characters before and after, never the keys. For Razorpay the new key must start
  `rzp_test_` or `rzp_live_` to match the mode chosen; Razorpay may stop the old key at once, so replace it in the same
  minute you regenerate it.
- **Mode** (`connection.mode_changed`): Off, Test or Live, for the providers whose keys the panel holds (Razorpay,
  Shiprocket, MSG91, which has only Live and Off, and ERPNext: Test for the staging site, Live for production's); the
  account of that mode must hold its keys first. Live takes real money and sends real messages.
- **Hold the circuit open** and **Reset the circuit** (`connection.circuit_opened`, `connection.circuit_reset`), for
  Shiprocket and ERPNext, whose calls go through the integrations client: held open, every call waits until it is
  reset, for a provider's announced outage; reset, calls go through again and the failures counted are forgotten.
- **Rotate the token** under Webhooks (`connection.webhook_rotated`): a new token is shown once, the previous one keeps
  working for 24 hours, so paste the new one at the provider before then. SES's webhook is `ANYMAIL_WEBHOOK_SECRET`'s,
  changed in the environment.
- **Events received** (listed for `integrations.view_inboundevent`: ADMIN, the owners, the auditor): "Process again" for
  a failed one, or "Process the failed ones again" since a time (`connection.event_replayed`,
  `connection.events_replayed`; `staff.replay_webhook`). An event refused for a wrong token or signature is never
  processed: it was not ours to take.
- **Calls made**: the redacted call log ("Failed only"), kept `INTEGRATIONS_RETENTION_DAYS` (90) days.
- **Dead letters**: "Run again" once, or "Give up" with a reason (`connection.dead_letter_replayed`,
  `connection.dead_letter_discarded`; `staff.replay_webhook`, and for ERPNext's rows `erp.replay_sync`: ADMIN and the
  owners), which run through the sync's own replay and discard (`erp.replay`, `erp.discard`).

**The keys' precedence.** Razorpay and MSG91 read their keys from `.env` until the panel holds some; the first keys given
to the panel must be of the mode `.env` runs, take over at once with the environment's webhook secret carried over, and
nothing stops. Shiprocket and ERPNext have only the panel's keys. SES, the buckets, Google and the error tracker stay in
the environment: their cards are read-only ("Secrets and key rotation" says how to change them).

**What lands in the inbox from here:** `integration_down` (a circuit opened; done once it closes), `dead_letter`,
`failed_event` and `webhook_silent` (Razorpay's webhook fell silent for `INTEGRATION_WEBHOOK_SILENCE_HOURS` while
payments came in: look at the webhook in Razorpay's dashboard, which disables one after 24 hours of failures, and enable it
again; the item is done when one arrives). "The inbox", below, lists them all.

**If the panel is down,** the Django admin does it: Admin → Integrations → Integration accounts has the actions "Replace
the credentials", "Test the connection", "New webhook token", "Hold the circuit open" and "Reset the circuit"; Integration
failures has "Replay" and "Discard"; Inbound events has "Process again".

## Couriers and integrations

Parcels booked with a courier through Shiprocket (`shipping/README.md`), on the integrations framework
(`integrations/README.md`). The panel's Connections page (above) shows the Shiprocket account, its circuit, calls, dead
letters and webhooks. The shipping desk's own pages (parcels, exceptions, cash on delivery, booking) are the next phase's
in the console (`/shipping/` says so); until then the Django admin has Shop → Shipments (every parcel by status, courier
and last scan, each with its timeline, exceptions, charges and COD remittance) and Shipping → Shipping exceptions (the
to-do list, by deadline), and the staff API takes the actions (`/api/v1/shipping/`, API.md "Shipping (staff)").

### Shiprocket is unavailable (a circuit open)

After 5 failures in 5 minutes (no answer, 429, 5xx) the account's circuit opens: calls wait, tasks are put back in the
queue to try again after 5 minutes, one trial call goes every 5 minutes and closes it on success. Settings → Connections
→ Shiprocket says "Trouble" and "Calls wait" since when (and an inbox item `integration_down` opens);
`/health/integrations/` fails once it has been 30 minutes.

1. Look at the card's last error and the call log (its page → Calls made, "Failed only"): `HTTP 503` or
   `ConnectTimeout: no answer` is Shiprocket's side (check its status page and its emails); `HTTP 429` is its rate limit
   (wait); a run of `HTTP 401` is the token or the API user (below).
2. During an announced outage, "Hold the circuit open" stops the calls until "Reset the circuit".
3. Meanwhile a parcel can go by hand: the order's "Send by hand" in the panel (Orders), or book it with `courier` and
   `tracking_number` (API.md). Quotes show Shiprocket's last answer, marked stale.
4. Once it answers again the circuit closes by itself; the waiting tasks run; the 2-hourly poll reads the tracking
   missed meanwhile.

**401 after 401:** the API user's password changed, the user was deleted, or its modules were narrowed. Replace the
credentials ("Secrets and key rotation") and test the connection. The token is renewed by itself from day 9 and once
after a 401.

### Dead letters and failed webhooks

A task that gave up (8 tries over about four hours, or refused: a 422 with Shiprocket's reason) is a dead letter, and an
inbox item (`dead_letter`, "Dead letter #…: … gave up"): Settings → Connections → Shiprocket → Dead letters, with the
operation, its tries and last error; `/health/integrations/` fails while one waits. Read the error, fix the cause (a
pickup nickname Shiprocket does not know, a product without weight, a COD total that does not add up, the circuit), then
"Run again" (it runs once more; a new dead letter if it fails again), or "Give up" with the reason (e.g. "booked by hand
in Shiprocket's panel"). A webhook that could not be processed is an event marked failed (the same page → Events
received, an inbox item `failed_event`): "Process again" once the cause is fixed. Refused events (a wrong or missing
token) are kept without their body: many from one address are someone else's; many in a row after a token change mean
Shiprocket still sends the old one (paste the new one, "Secrets and key rotation"). If the panel is down: Admin →
Integrations → Integration failures ("Replay", "Discard") and Inbound events ("Process again").

**No webhook for a day while parcels move:** check Shiprocket's webhook settings (enabled, the URL, the token); the
poll every two hours keeps the parcels up to date meanwhile (`dj shipping_poll_tracking` at once).

### A failed delivery (NDR)

A "delivery failed" scan opens an NDR exception due in 24 hours, with the courier's reason and the attempt count; the
customer gets an email (and an SMS when they asked for SMS) with the order's link. Call the customer (note what was
said in the resolution), then act through `POST /api/v1/shipping/shipments/<id>/ndr-action/` (API.md): `re-attempt`
(with a date, a corrected phone number or address), `fake-attempt` (the courier claimed an attempt that was not made:
with the parcel's photograph as proof), or `return`. Couriers make up to three more attempts before returning it; a
later delivery closes the exception by itself.

### A parcel coming back (RTO), lost or damaged

"Returning" opens an RTO exception and emails the customer; "returned" brings it forward (2 days) and notes the order.
In the packing room: scan the parcel back in, check it, put the copies back in stock (Products → the product's stock)
or mark them damaged, and acknowledge the RTO in Shiprocket's panel (no API for it). Then the order: a cash-on-delivery
parcel back undelivered is cancelled from its record in the panel ("Cancel the order": its copies back into stock unless
damaged, its invoice credited with a credit note, no money moving); a prepaid order is sent again (book a new parcel: it
gets the reference `<order>-R1`) or refunded (the refund dialog). A lost or damaged parcel: claim it with Shiprocket
(up to ₹5,000 or the order's value), then reship or refund. Resolve the exception with what was done.

### COD remittances

A delivered cash-on-delivery parcel expects its cash 10 working days later (Shiprocket pays D+8 working days, on
Mondays, Wednesdays and Fridays). Each morning (05:15) the site asks Shiprocket about the awaited ones: remitted (with
the UTR), mismatched (another amount: an exception) or overdue (2 working days past the day: an exception). Match the
UTR with the bank statement; for a mismatch or an overdue one, raise it with Shiprocket's support with the AWB and the
order, and resolve the exception with their answer. `dj shipping_check_cod` asks at once. In the panel, Reports → Cash on
delivery (`/reports/cod/`) shows what the couriers owe by how late, what they remitted and by courier, and Finance today
counts the overdue ones (`cod_overdue`; FINANCE's inbox item `shipping_exception`).

### Weight disputes

Each morning (05:30) the courier's weight disputes become exceptions due 7 working days after they were raised (after
that the courier's weight is accepted for good), with our weight and whether the parcel's photograph exists. To
dispute: in Shiprocket's panel (no API), with the photograph (the parcel on the scale, label side up) and the
dimensions; resolve the exception with the outcome. To accept: resolve it as accepted. The charge itself comes with the
statement (05:00, Admin → Shipping → Shipment charges: "excess weight").

### A parcel that stopped moving

No scan for 5 days opens a "no movement" exception. Read its tracking (Admin → Shop → Shipments → the parcel → "Read the
tracking now"); then ask Shiprocket's support with the AWB. A parcel the courier reports lost becomes "lost or
damaged" (above).

## Reviews, school orders and stock

### Reviews

Only an account whose order of the book was delivered can review it, once (stars and up to 1,000 characters). Admin →
Shop → Reviews, filter "status → waiting for approval": read each, select, "Approve" (it shows on the product page as
"Verified buyer", never a name) or "Reject" (never shown). Reject anything with a phone number, an email address, a
name, a link, a complaint about an order (answer it instead: the customer's email is on the review's page) or abuse;
approve critical reviews that are about the book. A review's History shows who changed it. The star rating appears in
search results only from approved reviews. Reviews are deleted with the account.

### School and bulk orders

The form at `/shop/school-orders/` (linked from the shop; books only: a course opens in one account, so the pupils of a
school get book codes) emails the SALES role (the superusers while SALES has no member). In Admin → Shop → Quote
requests:

1. Open the request; check the GSTIN (it is validated, not looked up: search it on the GST portal for a large order)
   and the delivery PIN code. Set the discount (%) and the shipping (₹) for this order; save.
2. Select it → "Make the quotation PDF": today's prices, valid 15 days, stored in the private storage; status "quotation
   made". Download it from the request's page and email it to the contact with the bank details (NEFT) or the UPI ID,
   or a Razorpay Payment Link for the total.
3. When the school accepts: the panel's Orders → Quotes → the request → "Make the order", with the delivery address
   (the request has only a PIN code: ask for the rest): a staff order of its books with its discount and shipping, once
   (the request keeps its order and reads "ordered"; above your discount limit FINANCE approves it first). Then send the
   Payment Link or, when the money arrives by NEFT or UPI, "Record a payment". A request that comes to nothing:
   "closed" in the admin.

### Returns

A customer asks on the website's order page within `SHOP_RETURN_DAYS` (15) of delivery (staff for them by phone, at
any time: the order's "Ask for a return"). Each request is an inbox item due in 48 hours. In the panel's Orders →
Returns: approve (the customer is emailed how to send it back) or decline with the reason; send the return label (the
courier and AWB); the packing room marks it received, adds photographs and inspects it: back into stock (the copies
added, with the return as the reason) or damaged. Then "Refund it" refunds its books through the refund dialog (above
your limit FINANCE approves). Exchanges are not built: refund, and the customer orders again.

### Stock, stock alerts and the low-stock email

- Stock is taken when an online order is paid (cash on delivery: when it is placed) and given back when the order is
  cancelled. Books sold outside the site, or counted: the panel's Catalogue → the product → Stock → *Set the copies*,
  with the reason (audited); it is refused when orders changed the count since the page was read (read it again). The
  panel's Stock lists the copies, the fewest first, with what orders hold and what waits for payment. The admin's
  "Set stock" is the fallback. A bundle's books are fixed once orders have taken its copies: make a new bundle.
- A product out of stock shows "Email me when it is back" (signed-in accounts only; a visitor is asked to log in; the
  email goes to the account's address). Each address gets one email, within the hour after copies are back (the stock
  raised in Products, or a cancelled order's copies returned), and is then forgotten; alerts never sent are deleted
  after a year.
- Each morning at 8 the SALES role is emailed the books on sale with fewer copies than `SHOP_LOW_STOCK` (5). Nothing
  is sent when no book is low. Bundles and digital products have no stock of their own: their books are in the list.

## The revision course

Content editors (CONTENT_EDITOR) upload in the admin under **Revision course** and run the rest from the panel's
**Course** module (`learn/README.md`: the outline, review and publish, the bin, the quiz bank, access, book codes);
DEPLOYMENT.md section 18 has the set-up. The shell recipes below are the fallback for when the panel cannot be used.

### Uploading and publishing a revision

1. **Chapters** exist once `import_chapter_insights` has run (Board marks and past-paper counts; editors add the
   must-do note). Open the chapter, add its flash cards (front and back, Markdown, `$…$` maths) in the table below it.
2. **Revisions → Add:** the chapter, a title, the target minutes (12 by default; 1 to 60). Status stays draft.
3. In the clip rows: order (1, 2, 3 …), title, kind, the video (vertical 9:16 from the phone is best; landscape is
   letterboxed), "free preview" only for an extra free clip (the first clip is free anyway). With the bucket set, a
   chosen video goes up at once, straight to the bucket ("Uploading: 40 %", then "Uploaded: … Save to process it"; the
   Save buttons wait for it). Save. Each new video goes to the media worker: processing → ready (or failed) a minute or
   two later; reload the page.
4. On each clip (Clips, or the Change link beside the row): notes or transcript (Markdown), the Board questions it
   prepares for (by id; the search in Questions finds them by paper code and label), then **Preview**: the clip as the
   app plays it, both renditions (480p, 720p), the poster and the notes.
5. **Panel → Course → the subject → the chapter → its revision → "Submit for review"**: the subject's reviewers find
   it in their inbox. A REVIEWER who did not submit it approves it, sends it back with what to change, or publishes
   it now (it needs a ready clip) or at a date and time (India's): a task every 5 minutes publishes it then. The app
   shows it at once; "Back to draft" hides it again, and students keep their progress. (Fallback: the admin's
   Revisions → select → "Publish the selected revisions", with `staff.publish_course`.)
6. Order of clips, cards and quiz items: in the panel's outline, drag a row by its handle or use its "Move to…"
   (first, last, before or after another). A row deleted there goes into the bin for 30 days (Course → Bin →
   Restore); a clip's video goes for good with the nightly purge after that.
7. Quiz items: `build_quiz_items` made them from the papers; check a few per chapter in Course → Quiz bank (filtered by
   subject, with the item analysis: "N/A" under 30 learners) and correct what reads badly, alone on its page or the
   metadata of many at once (a dry run first). "Needs checking" sends one to the content triage. Running the command
   again adds only new ones and keeps edits.

### A clip that failed

The clip shows "failed" and its page (or Preview) the end of ffmpeg's messages. Usual causes: the file is not a video or
is cut short (re-export it from the phone and upload it again), a codec ffmpeg cannot read (export as H.264 mp4), or the
media worker ran out of time or memory (more than about 50 minutes of encoding: split the video). The worker accepts
only mp4, mov, m4v, webm or mkv with H.264, HEVC, VP9 or AV1 video and AAC, Opus or MP3 sound; anything else fails at
once with "Not a video we take". If the upload itself fails ("The upload was cut off", or "The bucket refused the video
(403)"), the bucket's CORS rule lacks PUT for the site's origin (DEPLOYMENT.md section 17) or the 15-minute link ran
out: choose the video again. After a new upload the clip is processed again by itself. To retry without a new upload
(the bucket or the worker was down): **panel → Course → the clip → Retry**, beside the reason in words (shown for a
failed clip and for one processing for over an hour). The fallback, for many clips at once or without the panel:

```sh
docker compose exec web python manage.py reprocess_clips            # the failed ones, and those "processing" for over an hour
docker compose exec web python manage.py reprocess_clips 12 15      # these clips
docker compose exec web python manage.py reprocess_clips --all      # every clip (after changing LEARN_PUBLIC_VIDEO)
```

or Clips → select → "Process the video again". Clips stuck in "processing" mean the queue lost the task (Redis or the
worker restarted): `docker compose ps media-worker`, then the first command.

### Printing book codes

Each book can carry a code that opens the course in the app (a sticker or a printed slip inside the cover). One print
run, one batch: **panel → Course → Book codes → "Make a print run's codes"** (SALES, ADMIN, OWNER; a recent sign-in):
its label (`PHY-2027-1`, never reused), the subject (or every subject, for a set of the four books), how many, the
book they go into and the printer's note. A job makes them (its progress on the page; the owners get an email), and
**Download the printer's file** gives the CSV (code, batch, subject): it is the only copy of the codes (the database
keeps a keyed hash), yours to download for 24 hours, then deleted. Send it to the printer over a private channel and
delete your copy once the print run is checked. Codes look like `7KQM-3XPA-9TRW` (no 0, O, 1 or I). When the books
leave the printer, open the print run and **Mark dispatched**: a code of a run not yet dispatched that gets redeemed
is read as a leak by the fraud rules. A run whose job failed shows "Not made" with **Make its codes again**.

Two reports read the print runs, and both stay. **Course → Report** (`/course/report/`; whoever reads the print runs:
SUPPORT, SALES, ADMIN, the owners, the auditor) works out the newest 200 runs when asked: the codes printed, the copies
of the run's book sold from the run's day until the next run of that book, the codes activated, the access taken back
("revoked"), the codes voided before use ("void"), the activation rate and the districts. **Reports → Book codes**
(`/reports/codes/`; `staff.view_insights` and the codes' own permission, so ADMIN, the owners and the auditor) is the
same by print run with the last 7 days and the districts the redemptions came from, counted each night (02:15, the job
`code_activation`), and its "revoked" is the codes voided before use. Both hide a district under 10 redemptions
("fewer than 10"), and neither names a person.

A print run printed by mistake, or leaked: its page → **Void the run** (ADMIN, OWNER; its label typed): every unused
code stops working at once, the codes already redeemed keep what they opened, the printer's file is deleted and the
owners are told. One code alone (a photo of it posted online): look it up, then **Void this code**.

Set `LEARN_CODE_SECRET` before the first batch and never change it (DEPLOYMENT.md section 18; nothing is made without
it and a server does not start without it). The fallback without the panel (the same digests, and the print run's row
for the panel, where it is then marked dispatched):

```sh
docker compose exec web python manage.py make_book_codes PHY 5000 --batch PHY-2027-1 --out /app/media/PHY-2027-1.csv
docker compose cp web:/app/media/PHY-2027-1.csv . && docker compose exec web rm /app/media/PHY-2027-1.csv
```

### Granting access

**Panel → Course → Access → "Give access"** (SUPPORT, ADMIN, OWNER): the account's number (the customer's page shows
it), the subject (or every subject), the last day (empty: no end), a reference (a ticket's or a school order's
number) and why. For a school's pupils, "Give access to many" takes their account numbers: a dry run checks each,
then Apply (above your bulk limit an approver is asked). Choose rows in the list to extend them (by days, from their
last day) or revoke them (access ends today); one at a time it happens at once, many as a job with a dry run.
Revoking never touches a student's progress: access given again picks up where it stopped. The app shows the subject
open at once. Purchases of a digital product in the shop grant themselves when paid; an entitlement is never needed
for the free previews. (Fallback: the admin's Entitlements → Add.)

### A lost code, or "my code says used already"

1. Ask for the code (a photo of the slip) and look it up: panel → Course → Book codes → the lookup box (typed or
   scanned; unused, redeemed when and by which account, void, or unknown, in one line; the code is never kept, and the
   lookup is in the audit trail by the code's hash), or from the customer's ticket ("Look up a book code"). Not found:
   a typo (0/O and 1/I are not used), or a code from another batch or a fake. The learner's page (from the ticket's
   sidebar or the lookup's answer) shows their access, codes and devices; opening it is logged.
2. **Found and not redeemed:** the student can type it again; after 5 tries an hour (right or wrong; per account, and
   separately per internet address) the app must wait.
3. **Redeemed by this student:** nothing to do (Entitlements, search by the email, shows it).
4. **Redeemed by someone else:** ask for proof of purchase (the book, the bill). If it holds, grant access as above with
   the note "code #<id> used by another account" and keep the other entitlement unless the code was clearly stolen (then
   revoke that entitlement in Course → Access, with why; its owner will contact you if it was theirs).
5. **No code at all** (lost slip): proof of purchase, then a grant until the end of the exam season.

## Content

The content module of the panel (`content/README.md`): Content in the panel's menu. Its actions are audited and need
the permissions named; the shell recipes stay for when the panel cannot be used.

### Importing papers after the books changed

1. Content → Imports (REVIEWER, or OWNER; a fresh authentication first): pick the subject, leave the commit empty for
   the books checkout as it is (or give a commit's hash), Run the dry run. It lists what would be new, changed, the
   same, not matched, and no longer in the books (taken off the site, never deleted).
2. Read the labels behind "Changed" and "No longer in the books"; if they are what the books' change meant, Apply. The
   apply refuses when the checkout moved since the dry run (pull, then a dry run again) or after 24 hours.
3. A "Not matched" solution label is a heading the parser could not place: fix it in the books repository, pull, run
   again.

Break-glass (the panel down): `docker compose exec web python manage.py import_papers --subject physics --dry-run`,
then without `--dry-run` (DEPLOYMENT.md section 11). The command and the panel share the same code.

### A reader reported a wrong solution

1. Content → Reported mistakes: the report shows the question and the solution as the site shows them now, the step,
   the printing the reader had, their note. Confirm it, or reject it with the reason (the reporter's address goes).
2. "Open the solution in the editor": correct the Markdown (the preview draws it as the site does; KaTeX names a
   formula it cannot draw before anything is saved), Save the draft, Submit for review.
3. A reviewer of the subject (never the person who edited it) opens it from their inbox and publishes it.
4. Back on the report: Fixed online, and Tell the reporter if they left an address (one email; the address is then
   deleted). Once the print run is corrected: Fixed in a printing, with the new print run's label.

### Undoing a publish

Within five seconds of Publish, Undo on the review. Later, the solution's editor (a reviewer): Undo the last publish
puts the text before it back live and the published text back into the draft. Once the text changed again (an import,
a later publish), restore a version from the editor's History instead (it comes back as a draft to review).

### QR codes for a print run

Content → Papers → the paper → QR code: type the print run's label (`PHY-2027-2`) and Show its code, then Download the
picture. The code then carries the print run, so a mistake reported from that book names it. The panel refuses while
`SITE_URL` is not the public https address. For a whole book at once: `manage.py export_qr --out qr/` (the codes without
a print run).

### Legal deposits

The Delivery of Books and Newspapers (Public Libraries) Act asks for a copy of each edition at four public libraries. A
published book (its publication day set on the book's page in Content → Books) has an inbox item `legal_deposit` until
the four libraries have its edition, due 30 days after publication (`CONTENT_LEGAL_DEPOSIT_DAYS`; the period is still to
be checked against the Act). A nightly task (07:00) makes or updates one item for each such book, so a book published
yesterday is in the inbox of CONTENT_EDITOR, ADMIN and the owners this morning. When a copy goes: Content → Legal
deposits → record it (the library, the day it went, the proof: the consignment number or the receipt's, and a scan if
there is one; `content.legal_deposit_recorded`). The item closes with the fourth library. The Content page's list of
what waits shows the books still missing deposits.

## Insights

The predictive jobs (`insights/README.md`) run at night from 01:00 to 03:15 and keep their rows in the admin under
Insights; staff read them in the panel's Reports (`/reports/`: sales, places, book codes, the course's use, cash on
delivery, Razorpay's settlements, cohorts, forecasts and print runs), in the admin, or through `/api/v1/insights/`. They
never name a student: what they say about learners is about groups of 5 or more (10 for places and cohorts).

### An insights job failed

1. Sentry reports it (after one retry ten minutes later). For the forecast, the backtest and the print runs the admin
   says so too: Insights → Forecast runs → status "failed", the error in the notes; the rows of the night before stay
   the newest, so the panel shows them with their older `data_as_of`.
2. Run it again by hand and read the line it prints: `dj insights_run forecast_demand` (or the job's name; `all` runs
   them in the night's order). "nothing to work on" with a reason is not a failure: the exam seasons are missing
   (enter the next season's and the last one's: Insights → Exam seasons), a line sold nothing last season, or a title
   has no print cost.
3. A job that fails again on the same data: copy the error into an issue with the run's id. The jobs only read the
   shop's and the course's tables, so both go on. Switch the task off meanwhile (Periodic tasks → the `insights-…`
   entry → untick Enabled, a superuser's change; the next start of beat puts the time back, not the switch).

### A fraud spike

The night's email (to `INSIGHTS_ALERT_EMAILS`) or Insights → Fraud signals (filter "acknowledged at: empty"):

1. **Failed book codes from one account or one IP address**, or an hour far above the usual: someone is guessing
   codes. The redeem throttle already stops each account and address after 5 tries an hour, and a 12-character code
   cannot be guessed at that rate; Insights → Redemption attempts (filter by date and outcome) shows the batches and
   how many accounts and addresses. Many accounts from a few addresses: lower `API_THROTTLE_LEARN_REDEEM_ADDRESS`, or
   block the addresses at Caddy; a classroom (one address, many accounts, real codes) is not an attack.
2. **One account redeeming many codes**: resale of codes. The signal's details list the batches and the codes' ids;
   Book codes → open one → "redeemed by" is the account. Ask before acting: a teacher may have redeemed for a class.
3. **One code tried by several accounts**: a photo of a code shared. The first redeemer keeps it; the others get "used
   already" ("A lost code, or my code says used already").
4. **Accounts sharing a phone number or an address** on COD or coupon orders: a family, a hostel, or one person
   making accounts to get round a coupon's per-customer limit or the two open COD orders. The details list the orders'
   numbers: Orders → search each. Cancel an order placed only to abuse a coupon (with a note on it), and stop the
   coupon (Coupons → untick active) if it is spreading.
5. Acknowledge what you looked at: Django admin → Insights → Fraud signals → select → "Acknowledge" (ADMIN and the owners,
   `staff.acknowledge_signal`; or `POST /api/v1/insights/signals/<id>/acknowledge/`, event `insights.signal_acknowledged`).
   It comes back only if it grows, and the inbox item `fraud_signal` closes with it. The console lists a print run's
   signals on its page (Course → Book codes → the print run) but has no button to acknowledge one, and marking the inbox
   item done only closes the item, not the signal. The subject is a keyed hash: the admin's tables match it, nobody can
   read it back.

### A number on Home or in a report looks wrong

Every number is defined once, in words, beside itself: Home's cards ("How this is counted"), each report's head and
column headings. Read the definition first; most surprises are the definition (a payment counts on the day it was
captured, a refund on the day it was processed, a day is a day in India, a test-mode order is in no number).

1. Open the card's link or the report with the same period: the list behind a card is the very filter it counts (the
   card "Orders to pack" opens Orders → "To pack", "Tickets due today" opens the Support queue filtered the same way),
   and a report says "Data as of" and its period.
2. A cell that says "fewer than 10" is hidden on purpose (`INSIGHTS_MIN_CELL`, `INSIGHTS_MIN_CELL_CLASS`); nothing in the
   panel shows a smaller group, and no total includes what is hidden.
3. Course health is worked out each night at 03:15 (`dj insights_run course_health`); "Data as of" is that night's. A
   report that says a source is "not set up" (the settlements) waits for that module.
4. A report to take away: Reports → the report → Export (a CSV job; above your limit ADMIN approves it first). The
   file ends with who made it and when, and the audit log has `report.exported`.

### The monthly review, in season

`dj insights_review` prints each title's last four complete weeks: the forecast made before each week, the copies
sold and the seasonal naive, with both errors (WAPE). Then insights/README.md, "The monthly review": the backtest's
summary, the print runs to act on, the fraud signals still open, and a note in the season of what changed.

### A new season

Enter its exam dates as soon as the board publishes them (Insights → Exam seasons: board, class, academic year, first
and last written paper; practicals do not count) and the print costs of the new titles (Insights → Print costs). The
forecasts move to the new season on the day of the old one's first paper.

### Deciding a print run

Reports → Forecasts and print runs shows each title's recommended run with its range, the method and last season's
error in one panel. Type the net price, the print cost and the salvage you expect and the sum is worked out again (the
newsvendor's quantile; net 195, cost 60, salvage 5 give the 71st percentile of the season's demand); nothing is saved.
A forecast that has not beaten the seasonal naive in the backtest is labelled untested: print by the last season, not
by the forecast.

## ERPNext

The platform's documents mirrored in ERPNext, its stock and B2B documents read back (`erp/README.md`). At a glance, in
the panel: System → ERPNext sync (`/system/sync/`; `erp.view_sync`: ADMIN, the owners, the auditor, and FINANCE by its
address, as the System entry is not in its sidebar) shows the outbox by flow, its dead letters, ERPNext's calls back in the last 7 days, each night's reconciliation with its
differences, and a search for a document by reference, ERPNext name or id; Settings → Connections → ERPNext (the
"Connections" section, above) has the account, its circuit, the webhook and the dead letters to run again or give up;
Settings → "The ERPNext sync" holds each flow's switch. Without the panel: `dj erp_status`, or Admin → ERPNext sync
(the outbox, the links, the cursors, the stock snapshots, the B2B mirrors and the reconciliation runs) and Admin →
Integrations. What waits for a person is in the staff inbox: a document ERPNext refused for good (`sync_failed`, for
those with `erp.replay_sync`: ADMIN, the owners) and a night's differences (`reconciliation`, for those with
`erp.resolve_difference`: FINANCE too).

### ERPNext is unreachable

After 5 failures in 5 minutes the account's circuit opens: the relay waits (no try counted), one trial goes every 5
minutes, and the outbox keeps growing; `/health/integrations/` fails after 30 minutes, and `erp_status` shows the
oldest row waiting. Nothing is lost: when ERPNext answers again the circuit closes and the relay sends the backlog in
order. Check the call log (Settings → Connections → ERPNext → Calls made, "Failed only"; or Admin → Integrations →
Integration calls): `HTTP 503` or `no answer`
is ERPNext's side (its pods, `bench doctor`); `HTTP 429` its rate limit (the relay waits as `Retry-After` says);
`HTTP 401` or `403` the token (below). The pull and the reconciliation try again at their next run
(`dj erp_reconcile --date <day>` for a night missed).

**401 or 403 from Frappe** (`AuthenticationError`, `PermissionError`): the sync user's key was regenerated (which
revokes the old secret), the user disabled, or the platform's address is not in `examleaf_sync_user_restrict_ip`.
Each try counts while the token is refused. Generate the key again in ERPNext (DEPLOYMENT.md section 24), replace the
credentials on the account, test the connection; `dj erp_replay --dead` for what died meanwhile. A `permission_denied`
refusal with examleaf_erp's own body is one step the EL Sync role may not do (report it to whoever keeps
`examleaf_erp`'s `SYNC_PERMISSIONS`); only that row waits.

### A document ERPNext refused (a dead letter)

The inbox item, `dj erp_status` ("dead 1"), or Admin → ERPNext sync → Outbox rows (state dead). The row's last error
is ERPNext's own code and words (its Sync Log row is in `response.log` of the attempt that answered):

- `conflict` on `upsert_item`: an Item with that code exists in ERPNext without the platform's reference (made by
  Data Import): set its `examleaf_ref` to the row's in ERPNext, then replay; a later save of the product replaces the
  dead row by itself.
- `invalid_request` with a `field`: the payload is wrong for examleaf_erp (a contract change on one side): fix the
  code (`erp/contract.py`), deploy, replay.
- `tax_template_mismatch` (retried, then dead): the item's GST rate in ERPNext on the invoice's day is not the line's.
  ERPNext dates a new rate from the day the product's upsert reached it, so invoices at the new rate issued before
  that day refuse: on the Item in ERPNext (its Taxes table), set the new row's Valid From to the day the rate changed
  on the platform, then replay.
- `no_tax_template`, `not_configured` (retried, then dead): the bootstrap has not made a template, a bank account or a
  mode of payment's account: run `bench --site <site> execute examleaf_erp.setup.bootstrap`, then replay what died.
- `total_mismatch`, `doc_kind_mismatch`: ERPNext computed another grand total or document kind than the platform's
  invoice: a bug in the mapping (`erp/contract.py`) or a changed template in ERPNext; report it with the row and its
  Sync Log row, and replay once fixed.
- `cancelled`, `amendment_refused`: staff cancelled the document in ERPNext: ask them; a number is never issued again,
  so discard the row with what was done (a credit note, a document made by hand).
- `overpayment`: a second payment of a paid order ("A customer paid twice" above): discard it with that reason; the
  refund that follows goes against its credit note.
- `nothing_to_deliver` for a re-shipment: the first parcel's delivery note took the copies; book the return of the
  first one in ERPNext (a return of its Delivery Note, the copies back in stock), then replay.
- `insufficient_stock` (retried for some hours, a minute doubling to six hours, then dead): ERPNext's print runs hold
  fewer copies than the parcel took: record the printer's receipt in ERPNext (a Stock Entry into Main), then replay.

Then replay it (Settings → Connections → ERPNext → Dead letters → "Run again"; or Admin → ERPNext sync → Outbox rows →
"Replay", or `dj erp_replay <id>`; `--dead` replays them all) or give it up with the reason (made by hand in ERPNext,
not ERPNext's business): a row given up frees its order's later rows. Both need `erp.replay_sync` (ADMIN, the owners; a
fresh sign-in check), are audit events (`erp.replay`, `erp.discard`) and close the inbox item.

### The morning's reconciliation differences

The email to `ERP_ALERT_EMAILS` and the inbox item list them (Admin → ERPNext sync → Reconciliation runs → the run):

- `document not in ERPNext invoice:EL/…: outbox: dead here` (or `pending`): the dead letter above, or the relay
  behind (ERPNext down overnight); `outbox: no row`: the flow was off when it was issued:
  `dj erp_initial_load --apply --invoices-from <that day>`.
- totals (`invoices total`, `payments and refunds receive razorpay amount` …) with nothing missing: a document changed
  or deleted in ERPNext by hand: find it (its number, the payment's reference), put it back as the platform has it.
- `invoices tax_total` or `taxable_value` beyond 0.01 a taxed invoice: a GST rate differs between the two.
- `stock invariant EL-00042: 16 here, 13 in ERPNext`: copies counted, written off or moved in ERPNext and not here (or
  the reverse): count the shelf, correct the side that is wrong (with `ERP_STOCK_PROJECTION` on, ERPNext's is the
  truth).

Resolve each with a note of what was done (Admin → Reconciliation differences → "Resolve", or
`POST /api/v1/staff/erp/differences/<id>/resolve/`; `erp.resolve_difference`, event `erp.resolve`); the inbox item closes
with the last. The console shows each night's run and its open differences (System → ERPNext sync) but has no button to
resolve one yet. A run that failed (ERPNext unreachable) is retried by its task, then a dead letter;
`dj erp_reconcile --date <day>` runs one by hand.

### No doorbell from ERPNext for a while

Stock and B2B documents still arrive through the pull every 15 minutes (Admin → ERPNext sync → Pull cursors: last
run and error). If doorbells are refused (Settings → Connections → ERPNext → Events received, "Refused (wrong token)";
or Admin → Integrations → Inbound events, state rejected), the webhook secret in ERPNext's site config is not the
account's: make a new one (Webhooks → "Rotate the token"; in the admin, "New webhook token" on the account) and set it
there (`examleaf_webhook_secret`) within 24 hours. `dj erp_pull --restart` reads every doctype from the start (the B2B
mirrors rebuilt).

### Switching a flow off (rollback) and on

Panel: Settings → "The ERPNext sync" lists each switch with the environment's value under it; open the one (for example
`ERP_SYNC_INVOICES`) → "Change": the new value (On or Off), the reason, and "Takes effect from" (empty: at once); ADMIN
and the owners (`staff.manage_flags`), event `flag.changed`, and the switch's history is on the same page (or
`PUT /api/v1/staff/flags/ERP_SYNC_INVOICES/` `{"value": false, "reason": "…"}`; or the environment's
`ERP_SYNC_INVOICES=0` and a restart). Its new events are not written and its waiting rows hold their orders; on again
("Back to the environment's value", which is `null`), they go, and `dj erp_initial_load --apply --invoices-from <the day it
went off>` writes what was missed (what the outbox has is never written twice). `ERP_ENABLED` off stops only the
talking: rows keep being written and wait. `ERP_STOCK_PROJECTION` off gives the copies for sale back to the
platform's own number (as the last projection left it): count the shelf.

### ERPNext restored from a backup

What the platform sent since the backup is sent again: `dj erp_replay --sent-since <the backup's time, e.g.
2026-10-09T06:00>` puts every row ERPNext answered since then back in the outbox, in order and with its keys (ERPNext
answers duplicates for what the backup kept; an audit event, `erp.resend`). The initial load would not do it: it
writes only what the outbox lacks. Then `dj erp_pull --restart` (the B2B mirrors and stock read again) and
`dj erp_reconcile --date <each day since>`. What only ERPNext held since the backup (purchases, journals, receipts and
counts, B2B documents) is entered again by hand from its paper trail.

## Support

Complaints and questions are tickets in the panel's Support module (`support/README.md`): the contact form, "My
requests" on the website, email to the support address and the calls and messages staff log all land there, each
with its number (`SR-2026-000123`) and its legal deadlines. The queue opens on the next deadline; what waits for a
person is in the staff inbox too: a deadline three quarters gone (`ticket_due`), a deadline missed (`ticket_breach`),
a colleague's note naming you (`ticket_mention`).

### Working the queue

1. Panel → Support, "Due soonest": the first rows are the nearest deadlines (red: late). Take one ("Take it"), read
   the conversation and the customer beside it (orders with the Razorpay ids, shipments, invoices, course access, the
   book codes redeemed, their other tickets).
2. Answer from the reply box (saved replies with Alt and their number, in the customer's language). An email goes in
   the customer's thread; a call or a WhatsApp message is recorded with "How". The first reply also acknowledges a
   ticket not acknowledged yet.
3. Act from the ticket: a refund (within your limit it runs; above it a change request waits for FINANCE in
   Approvals), cancelling an order, the invoice or the confirmation again, course access extended, a book code looked
   up, a data request started from a grievance or privacy request. Each is written on the ticket.
4. Move it on: waiting on the customer or on a courier or bank (its deadlines keep running), then resolved with what was
   done (an order ticket asks for its order, a content error for its paper, a privacy request for its data request). A
   resolved ticket closes by itself after 4 days; the customer's reply reopens it (counted).

The deadlines never pause: 48 hours to acknowledge and a calendar month to redress (E-Commerce Rules), 30 days for an
NCH complaint, a month (90 days from 13 May 2027) for a privacy request. A missed one stays missed in the grievance
register: say so to the customer and finish it.

### Logging a call, a WhatsApp message or an NCH complaint

Panel → Support → "Log a call or message": how it came, when (it may be earlier today or within the year: the
deadlines run from then), the number they called from or the address it came from, what they said. An NCH complaint
needs its docket number from NCH's portal; answer it on the portal too ("Answered on NCH's portal") and close it there
when it is closed here. The acknowledgement goes to the address or number given (by SMS only between 08:00 and 21:00).

### Setting up the support mailbox

The support address (`SUPPORT_EMAIL`) is forwarded to the site so that every email becomes or joins a ticket:

1. `INTEGRATION_KEYS` must be set (the requesters' details are encrypted with it; without it a server refuses to
   migrate: `support.E001`).
2. Admin → Integrations → Integration accounts → add one: provider `support_mail`, enabled; then its action "New
   webhook token" shows the token once (the same action rotates it: the previous one works for 24 hours).
3. The forwarder: an Amazon SES receipt rule for the address that sends the message to SNS (or S3) and a Lambda that
   POSTs the raw message (`message/rfc822`) to `https://examleaf.in/api/hooks/support-mail/` with the header
   `X-Support-Mail-Token: <token>`; or a Cloudflare Email Routing worker that does the same with `message.raw`.
   Messages above `SUPPORT_MAIL_MAX_BYTES` (10 MB) are refused (413): the forwarder should bounce them.
4. Send a test email: a ticket appears with source "Email" and the acknowledgement comes back with its number. While
   the forwarder is not ready, keep `SUPPORT_COPY_TO_EMAIL=1` so the mailbox still gets the contact form's messages.

**Mail not arriving as tickets:** Admin → Integrations → Inbound events, provider `support_mail`: a refused event is a
wrong token (the forwarder's header); an event with an error says why it was not a ticket ("Not for a ticket: an
auto-reply", our own mail coming back, a bounce, a list, more than 50 recipients, a flood of 20 an hour from one
sender). One that failed while it was read (an error, in the staff inbox as `failed_event` for ADMIN and the
owners) is marked failed: "Process again" there once the cause is fixed; an email is never made a ticket twice (its
Message-ID).

### Spam

Move a ticket to "Spam": it leaves the queue and every number, gets no acknowledgement, and is purged with its
messages and files after 30 days (the numbers purged are in the audit log). Back to "Open" if it was not spam: it is
acknowledged then.

### The grievance register

Panel → Support → Grievance register (ADMIN, the owners, AUDITOR): the days received, then the file once the job is
done (a dated CSV: numbers, categories, sources, NCH dockets, the times taken and whether in time; no personal data).
Above your export limit it waits for an approver. Break-glass fallback, on the server:
`dj grievance_register --from 2026-10-01 --until 2026-10-31 > register.csv`.

### Switches

`SUPPORT_INTERMEDIARY_RULES` (panel → Settings, with a reason; or the environment) adds the IT Rules' 24 hours and 15
days to grievance tickets: turn it on only once counsel says the reviews make ExamLeaf an intermediary.
`SUPPORT_COMPLAINT_COPY_FROM` (environment, 1 January 2027 by default) is the day from which the acknowledgement
carries a copy of the complaint as recorded.

## The system pages

System (`https://admin.<domain>/system/`; `staff.view_system`: ADMIN, the owners and the auditor read it) opens on "At a
glance": a line for each part of the platform (health checks, queues, webhooks, email, SMS, backups, the audit chain,
the ERPNext sync, dependencies, hardening, the checkout's scripts, logs and time), each "Good", "Look at it", "Act now"
or "Not set up", with since when it has been so. The same page has "A stuck online payment" (an order number and "Ask
Razorpay"; Finance → Payments does the same with the record beside it) and the maintenance switch ("Turn maintenance
mode on": `staff.toggle_maintenance`, ADMIN and the owners; visitors see the banner and changes close while the console
stays open; a `setting.changed` event, and the owners are told). The parts below have pages of their own. The roles'
guides say who may do what; recording a restore drill is `staff.manage_system` (ADMIN, the owners).

### Backups and restore drills

System → Backups (`/system/backups/`) shows the newest backup of each source in the backups bucket with its size and the
SHA-256 in its `.sha256` sidecar (compare it with `sha256sum` of the file you restore), how long they are kept
(`BACKUP_KEEP_DAYS`), and "Last proven to work on <day>, by restoring <engine>", or "Never proven by a restore". A source
whose newest backup is older than `BACKUP_STALE_HOURS` (26) opens the inbox item `backup_stale` (hourly check, the owners
alerted once) and the page says "Older than N hours": look at the backup job's logs (`docker compose logs backup`, or
the CronJob's last run) and run it. After each restore drill ("Backups and restore", above) press "Record a restore
drill": the day, what was restored (the platform's PostgreSQL, ERPNext's MariaDB and files, or both), the backup
restored, the result (It worked, In part, It failed), the minutes it took and notes; the audit event is
`backup.drill_recorded`. A drill each quarter, both engines, and the first before the cut-over rehearsal (plan 9.6).

### The checkout's scripts changed

Every day at 07:10 the site reads the checkout's page (`SITE_URL/checkout/`) and the console's sign-in page and lists
every script on each, by address or, for an inline script, by the SHA-256 of its text (PCI DSS 6.4.3 and 11.6.1). When a
page's list differs from the day before (a script added, changed or gone) the inbox gets one item `scripts_changed`
("The scripts of the checkout changed: 1 new or changed, 0 gone"; for whoever holds `staff.view_system`), the owners are
emailed and the audit log has `scripts.changed`. The first inventory alerts nobody, and a page that could not be read
(the site down) is shown as "The check failed" on System → Checkout scripts (`/system/scripts/`), never taken for a
change. What to do: open that page ("Changed" marks the page; the list shows each script's first and last seen and which
are "on the page now") and ask whether a deploy of ours explains it. If it does, mark the item done: tomorrow's check
starts from the new list. If nothing explains it, treat it as an incident ("Incidents", below, and the breach register in
Legal and privacy → Incidents: CERT-In's 6 hours run from when it was noticed).

### The dependency report

System → Dependencies (`/system/dependencies/`) shows CI's last pip-audit and npm audit: the open advisories by severity,
the versions that run, and for each critical one the day it must be fixed by (7 days after it was first seen; "Overdue"
once past). The deploy loads the latest report (`dj load_dependency_report dependency-report.json`, DEPLOYMENT.md section
25); older than 8 days or missing, the page says "Older than 8 days: load the latest CI run's" and the Monday check
(09:00) opens `dependencies_stale`, which the next Monday check closes once a fresh one is loaded. A critical advisory is
patched within 7 days (plan 9.6).

### Hardening

System → Hardening (`/system/hardening/`) lists the admin host's protections, each "In place", "Missing" or "Not testable
here", with what it found and how to fix it: the admin host set apart (`ADMIN_HOSTS`), the staff endpoints answering 404 on
every other host, HSTS of a year with subdomains, a Content-Security-Policy with `frame-ancestors 'none'`, staff answers
never cached, the console not indexed, `__Host-` cookies with SameSite Strict, `DEBUG` off, the secret keys set (each
shown by four digits of its hash, never the key), and the proxy dropping `X-Middleware-Subrequest` (only Caddy or the chart
can say). The cookies row reads "Missing" while one Django serves both hosts with one cookie name: that is known, and the
fix is a deployment of its own for the admin host (the row says how).

### Logs and time (CERT-In)

System → Logs and time (`/system/logs/`) lists what is logged, where, for how long and who reads it, against CERT-In's 180
days and the DPDP Rules' year ("Long enough": Yes, No, or "As the host keeps it"); the clock (this server's against the
database's, within a second; and `LOG_TIME_SOURCE`, where the host's clock is synchronised from: CERT-In asks for NTP to
NIC or NPL, or a cloud time service, DEPLOYMENT.md section 23); and CERT-In's point of contact, which is "Still the fresh
install's placeholder" until Legal and privacy → Disclosures has the registered contact (never shown on the website).
A new log is a new row in `examleaf/logs.py`.

## Incidents

- **/health/ returns 500:** the JSON (ask for it with
  `curl -H 'Accept: application/json' -H "X-Health-Token: $(sed -n 's/^HEALTH_CHECK_TOKEN=//p' .env)" https://examleaf.in/health/`;
  the results are up to 20 seconds old) names the failing part: database (`docker compose logs db`), cache (Redis),
  storage (disk full? `df -h`), Celery (worker; "No worker for Celery task queue celery" while
  `docker compose ps worker` shows it running means that the media worker answered the ping first: ask again). With
  Redis down the site keeps working without its cache (rate limits are off meanwhile; log-in, sign-up and password reset
  work) and sends emails itself; the shop's own limits refuse instead (Find your order, checkout, place order, coupon
  codes, reviews, back-in-stock alerts and school quotations answer "Too many tries" (coupon codes: "Too many codes
  tried: please try again in an hour.") until the cache Redis is back; online payments already started still complete).
  The cache is `redis-cache` and the queue `redis`: `docker compose up -d redis redis-cache`, then the daily clean-up
  queues again the invoices, credit notes and refunds that could not be queued. A web container that will not start
  prints the failing check (`docker compose logs web`): the database or a migration (its readiness check needs nothing
  else; the site starts without its cache). A cache Redis that stops answering (rather than refusing) costs each web
  process one second, then five seconds of misses at once: a warning "every cache call a miss for 5 seconds" in the logs.
- **/health/web/ returns 500** (the chart's readiness: the pod gets no traffic): the database does not answer, or a
  migration of this code is not applied ("N migrations not applied": `dj migrate`; on Kubernetes the init container
  runs it, so look at its log). It never fails for the cache or the buckets.
- **/health/integrations/ returns 500:** its JSON names what waits: a provider unavailable for 30 minutes (a circuit
  open), dead letters, failed webhooks ("Couriers and integrations"). The site itself is not down for it.
- **The queue's Redis (`redis`) is down:** emails and SMS are sent inside the request; the AVIF and WebP sizes of a
  product picture that staff upload are made inside the request too (slower, not an error), and so is a quotation's PDF;
  a clip video stays "processing" until `dj reprocess_clips` queues it again.
- **Razorpay (or MSG91) slow or down:** a payment page answers "The payment service could not be reached" within 10 to
  13 seconds, or at once once half of a web process's threads already wait on a provider (the bulkhead,
  RESILIENCE.md); the rest of the site keeps its threads. Customers try again; check https://status.razorpay.com; the
  webhook and `dj reconcile_payments` complete payments made meanwhile (The shop, "A stuck payment").
- **A task failed with `LostTooOften`** (Sentry, the task results in the admin): its process died under three runs
  in a row (killed for its memory, a crash), so it is not run again. Look for the worker's "exited with signal 9"
  lines and what the task was given (a huge PDF, a broken clip); raise the worker's memory limit or fix the input,
  then queue it again (the task's own admin action, or `celery -A examleaf call <task> --args '[…]'`).
- **Errors "canceling statement due to statement timeout"** (Sentry, logs): a statement ran past `DB_STATEMENT_TIMEOUT`
  (15 s in the web, 600 s in Celery). The request answered 500 and its transaction was rolled back; find the query
  (the log line's `request_id`, Sentry's breadcrumbs), and `EXPLAIN` it before raising the limit.
- **A panel job stays "running"** long after its start: past its soft limit (25 minutes) a job ends failed with the
  reason; one whose worker was lost (a pod killed, out of memory) stays running. "Cancel the job" (My account → Your
  background jobs; only whoever started it) asks a live worker to stop at its next row, so it does nothing for a lost
  one. Mark it failed
  by hand:
  `dj shell -c "from staff.models import Job; Job.objects.filter(pk=ID, state='running').update(state='failed')"`, and
  start it again from the panel.
- **Disk full:** `docker system df`; old images (`docker image prune`), backups beyond `BACKUP_KEEP_DAYS`; logs are
  rotated already; the clips' videos are in the `media` volume unless the buckets are set.
- **Certificate problems:** `docker compose logs caddy`; DNS must point at the server and ports 80/443 be open.
- **Someone locked out by django-axes** (10 failed log-ins): it lifts after 15 minutes. A customer's, at once, in the
  panel: Customers → the customer (the list shows "Locked") → Actions → "Unlock sign-in" (`staff.unlock_user`: SUPPORT,
  ADMIN, the owners; event `user.unlocked` with the attempts cleared). A member of staff's lock-out has no panel
  action (the Customers pages show customers only): wait the 15 minutes, or run `dj axes_reset_username x@example.com`,
  which also does a customer's with the panel down. The owners are emailed when a staff account is locked.

## The inbox: what each item asks of you

The panel's Inbox (`https://admin.<domain>/inbox/`; every member of staff has one) holds what waits for a person: items
given to you, and those given to nobody that your permissions let you act on. "Mark done" closes an item for everyone,
"Snooze" hides it until a time, "Assign to me" takes it (only someone who may act on it can be assigned), and the filters
are Only mine, Show (open, snoozed, done) and Kind. An item's title names a number or a code, never a person. Many close
themselves when the cause goes (a circuit closes, a settlement matches, a backup is recent again); the rest wait for a
person to mark them done. In this table "the owners" are OWNER and "the auditor" reads only what `staff.view_system`
shows.

| Kind | Who sees it | What it asks |
|---|---|---|
| `approval` | the checker: FINANCE and the owners for money; ADMIN and the owners for roles, a member of staff's second factor, erasures, exports and bulk jobs; SUPPORT, ADMIN and the owners for a customer's second factor | Open it in Approvals, read the payload, approve with the hash you read or reject; never your own request. It expires after `STAFF_CHANGE_REQUEST_HOURS` (24). staff/README.md "Approvals" |
| `teacher_request` | SUPPORT, ADMIN, the owners | A teacher asked for access: Django admin → Teacher profiles → "Verify" or "Revoke" (the teachers' pages in the panel come with Phase C) |
| `deletion_request`, `data_request` | SUPPORT, ADMIN, the owners | An account deletion waits its seven days by itself. A data request is acknowledged within 48 hours and answered within a month: "A data request under the DPDP Act" |
| `compliance` | ADMIN and the owners (the dark-pattern self-audit, from 1 December); SUPPORT, ADMIN and the owners (a deletion a legal hold or a child's parent keeps waiting) | The self-audit: "Legal holds, policy versions, the disclosures and the self-audit". A held deletion: release the hold or record the parent's confirmation |
| `processor_task` | ADMIN, the owners | Ask the processor to erase or stop (same section, last bullet) |
| `incident` | ADMIN, the owners | CERT-In within 6 hours and the Board within 72: Legal and privacy → Incidents |
| `failed_job` | a clip: CONTENT_EDITOR, ADMIN, the owners; a revision to publish with no ready clip: REVIEWER, ADMIN, the owners; a task that gave up: ADMIN, the owners, the auditor | "A clip that failed"; "Uploading and publishing a revision"; a task: its lines in `docker compose logs worker` ("The retention tasks", "Reading the logs") |
| `failed_webhook`, `failed_event` | ADMIN, the owners, the auditor | A provider's webhooks refused (the secret differs: "Secrets and key rotation") or an event not processed: Settings → Connections → the provider → Events received → "Process again" |
| `integration_down`, `dead_letter` | ADMIN, the owners, the auditor | A circuit is open, or a task gave up: "Connections" and "Couriers and integrations" |
| `webhook_silent` | ADMIN, the owners | Razorpay's webhook is silent while payments come in: enable it again in Razorpay's dashboard ("Connections") |
| `sync_failed`, `reconciliation` | ADMIN and the owners; FINANCE too for `reconciliation` | ERPNext refused a document, or a night's differences: "ERPNext" |
| `shipping_exception` | SALES, ADMIN, the owners; FINANCE for cash on delivery overdue | A failed delivery, a parcel back or lost, a weight dispute: "Couriers and integrations" |
| `tax_threshold`, `credit_note_missing` | FINANCE, ADMIN, the owners | A turnover or count line crossed; a refund without its credit note: "Tax: rates, documents, series", "An invoice or credit note is missing" |
| `order_hold` | SALES, SALES_REP, ADMIN, the owners | A cash-on-delivery order scored high waits for a payment check: Orders → the order → "Release the hold", or cancel it |
| `return_request` | SALES, SUPPORT, ADMIN, the owners | A return was asked for, due in 48 hours: "Returns" |
| `bank_refund` | FINANCE, the owners | A refund to transfer by bank or UPI: "I have not got my refund", step 2 |
| `settlement`, `b2b_payment` | FINANCE, ADMIN, the owners | A Razorpay settlement that does not match; a B2B invoice paid by link whose ERPNext entry is to post: "Razorpay settlements", "Staff orders and payment links" |
| `ticket_due`, `ticket_breach`, `ticket_mention` | SUPPORT, ADMIN, the owners, and SALES for order, payment and school-order tickets; given to the ticket's assignee, or to the colleague named in a note | A legal clock three quarters gone, or missed; you were named: "Support" |
| `review`, `error_report` | REVIEWER, ADMIN, the owners (a paper's review); CONTENT_EDITOR, REVIEWER, ADMIN, the owners (a reported mistake); each narrowed to the person's subjects | A draft to review and publish; a mistake to triage: "Content" |
| `legal_deposit` | CONTENT_EDITOR, ADMIN, the owners | A book's copies are due at the four libraries: "Legal deposits" |
| `fraud_signal` | ADMIN, the owners | A rule found something: "A fraud spike" |
| `role_expired`, `offboarding` | the owners | A temporary role ended; steps of a departure to tick by hand: "Staff accounts" |
| `template_idle`, `template_certify` | ADMIN, the owners | A message template unused for 75 days (DLT deactivates one at 90), or due for its yearly self-certification: Settings → Message templates |
| `backup_stale`, `dependencies_stale`, `scripts_changed` | ADMIN, the owners, the auditor | No recent backup; the dependency report is old; the checkout's or the sign-in's scripts changed: "The system pages" |

## Reading the logs

Every line is a JSON object on stdout (`docker compose logs -f web worker`, or the cluster's log store): `time`,
`level`, `logger`, `message`, and `request_id`, the id Caddy gave the request (`X-Request-ID`, sent back in the
answer, and in Caddy's access log). A Celery task's lines carry the request id of the request that queued it, and their
own `task_id` and `task_name`.

- **A request:** one line from `examleaf.requests` when it is answered: `method`, `route` (the URL pattern, e.g.
  `/api/<version>/orders/t/<slug:token>/`: an order link's token or a consent link never reaches the logs), `status`,
  `duration_ms` and `user_id` (the account's id, null when signed out; never an email address). Everything else that
  request logged has the same `request_id`:
  `docker compose logs web | grep 4c6a4b317a694c15aed3a359fa453e1d`.
- **Slow requests:** the same line at WARNING with "(slow)" past `SLOW_REQUEST_SECONDS` (2 s):
  `docker compose logs web | grep '"level": "WARNING", "logger": "examleaf.requests"'`. A slow payment page is
  Razorpay (`shop.payments` "not created"); a slow API page with "statement timeout" is a query.
- **A task:** `docker compose logs worker | grep '"task_name": "shop.tasks.refund_payment"'`; Celery's own lines say
  `received`, `succeeded in …s`, `retry: Retry in …s` or `raised …` for each task id.
- **gunicorn's processes:** `gunicorn.error` lines: "Booting worker", "Autorestarting worker after current request"
  (the recycling after `GUNICORN_MAX_REQUESTS`: normal), "Worker exiting", and the ones that matter: "WORKER TIMEOUT"
  and "worker … timed out: the stacks of its threads follow" (a process stuck as a whole: the stacks after it show
  where), "was sent SIGKILL! Perhaps out of memory?". Count them a day:
  `docker compose logs --since 24h web | grep -c 'WORKER TIMEOUT\|Perhaps out of memory'`.
- **The cache Redis silent:** `examleaf.cache` "every cache call a miss for 5 seconds", one a pause per process.
- **The providers' bulkhead:** "Half of this process's threads are waiting on providers already" in a Razorpay or
  MSG91 error: the provider is slow, and calls beyond the share are answered at once (Incidents).
