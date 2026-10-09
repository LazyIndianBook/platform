# Runbook

Commands run in `/srv/examleaf/examleaf-web` on the server. `dj` below stands for
`docker compose exec web python manage.py`.

## Contents

- [Backups and restore](#backups-and-restore)
- [Secrets and key rotation](#secrets-and-key-rotation)
- [Staff accounts](#staff-accounts): break-glass accounts
- [Data requests and privacy](#data-requests-and-privacy): a data request under the DPDP Act, purging old orders
- [Email](#email): when email fails, bounces and complaints
- [SMS, phone numbers, passkeys and parental consent](#sms-phone-numbers-passkeys-and-parental-consent)
- [The shop](#the-shop): payments, refunds, invoices, shipping, GST returns, coupons, offers, staff orders, the catalogue
- [Couriers and integrations](#couriers-and-integrations): Shiprocket down, dead letters, failed deliveries, returns,
  COD remittances, weight disputes, parcels that stopped moving
- [Reviews, school orders and stock](#reviews-school-orders-and-stock)
- [The revision course](#the-revision-course): uploading, failed clips, book codes, access
- [Insights](#insights): a job failed, a fraud spike, the monthly review, a new season
- [Incidents](#incidents)

## Backups and restore

### Restore the database from a backup

1. Pick the dump: `ls -lt backups/`, or download it from the backup bucket (`database/examleaf-….dump`, or
   `….dump.age` when `BACKUP_AGE_RECIPIENT` is set: decrypt it on the computer that holds the key,
   `age --decrypt -i examleaf-backup.key -o examleaf-….dump examleaf-….dump.age`, then copy the dump to `backups/`).
2. Note the account deletions completed since that dump was taken (use the dump's own date and time), because restoring
   brings those people's data back:

   ```sh
   dj shell -c "from accounts.models import DeletionRequest as D; print(list(D.objects.filter(status='done', closed_at__gte='2026-10-08 02:15+05:30').values_list('user_id', flat=True)))"
   ```

3. Stop everything that writes, restore, start again:

   ```sh
   docker compose stop web worker media-worker beat
   docker compose exec -T db pg_restore --clean --if-exists --no-owner --username examleaf --dbname examleaf < backups/examleaf-YYYYMMDD-HHMMSS.dump
   docker compose up -d
   ```

4. Erase the noted accounts again:
   `dj shell -c "from accounts.models import DeletionRequest as D, User; [(u.pending_deletion or D.objects.create(user=u)).complete() for u in User.objects.filter(pk__in=[…])]"`.
   Deletions that were still waiting are completed by the next daily purge (or run
   `dj shell -c "from accounts.tasks import purge_due_deletions; print(purge_due_deletions())"`).
   Students who asked for deletion after the dump was taken must ask again: tell them.
5. Check `/health/`
   (`curl -H "X-Health-Token: $(sed -n 's/^HEALTH_CHECK_TOKEN=//p' .env)" https://examleaf.in/health/`), log in to the
   admin, open a paper.

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
- **Provider keys** (email: `SES_*` or the `ANYMAIL_…` key; `MSG91_AUTHKEY`; `RAZORPAY_KEY_*`; `S3_*` and `PUBLIC_S3_*`;
  `AWS_*` of the backups; `GOOGLE_CLIENT_SECRET`; `TURNSTILE_SECRET_KEY`; `FCM_SERVICE_ACCOUNT_JSON`; `SENTRY_DSN`):
  create the new key with the provider, change `.env`, `docker compose up -d`, then revoke the old key. MSG91's new
  authkey needs the server's IP whitelisted too.
- **Webhook secrets** (`RAZORPAY_WEBHOOK_SECRET_TEST`, `RAZORPAY_WEBHOOK_SECRET`, `ANYMAIL_WEBHOOK_SECRET`): the
  provider holds the same secret (Razorpay's webhook settings; the user and password inside the SNS or provider
  webhook URL), so change both at the same moment. Events that arrive between are refused; Razorpay sends a webhook
  again for 24 hours, and `dj reconcile_payments` finds payments that were missed.
- **HEALTH_CHECK_TOKEN:** change it in `.env` and in the uptime monitor's header.
- **Staff passwords:** each person changes theirs on the website's Security page (`/account/security/`); take roles
  away from people who left
  (Users → "Take away role …", and untick Active).
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
- **Shiprocket's API user** (rotate by the account's `rotate_by`, 90 days; or at once if it leaked): in Shiprocket,
  Settings → API → Add New API User (a new email address); in the admin, the account → "Replace the credentials" with
  the new email and password → Save → "Test the connection"; then delete the old API user in Shiprocket. The cached
  token goes with the old credentials.
- **The couriers' webhook token:** the account → the action "New webhook token" shows it once; paste it in Shiprocket
  (Settings → API → Webhooks, the security token) within 24 hours, while the previous one still works.
- **Suspected breach:** rotate everything above, SECRET_KEY **without** a fallback (a leaked key would otherwise keep
  sessions valid for two weeks) and JWT_SIGNING_KEY (or SECRET_KEY, if it is unset) too, end all sessions
  (`dj shell -c "from django.contrib.sessions.models import Session; Session.objects.all().delete()"`; everyone logs in
  again, staff with their second factor), change `HEALTH_CHECK_TOKEN`, find out what was exposed, and inform the Data
  Protection Board of India and the people affected without delay (the DPDP Rules, 2025 ask for a detailed report to the
  Board within 72 hours). Keep notes of what happened and what was done.

## Staff accounts

Every member of staff logs in with a password and a second factor: a code from an authenticator app, or a passkey
(SECURITY_REVIEW.md, H2). A session lasts 8 hours from the log-in.

1. **New member of staff.** An owner (the OWNER role) invites them with their role through the staff API
   (`people/invite/`, API.md "Staff API"); or a superuser makes the account (admin → Users → Add, or the person
   registers on the site) and gives the role (Users → action "Give role …"; only superusers can).
2. **First log-in** at `/admin/` (it opens the website's log-in): email and password, then the code emailed to them the
   first time, which confirms the address. The admin then sends them to the website's `/account/2fa/` before anything
   else opens: scan the QR code with Google Authenticator, Microsoft Authenticator, Aegis or 2FAS, type the 6-digit
   code, and the ten recovery codes appear. A passkey (the website's Security page) does instead of the app, as the
   step after the password: staff cannot log in with a passkey alone.
3. **Recovery codes are kept offline:** download or write them down and keep them away from the phone (on paper in a
   safe place, or in a password manager). Each works once, instead of the app's code.
4. **Later log-ins:** password, then the app's code (or a recovery code, or the passkey). The website's `/account/2fa/`
   shows how many recovery codes are left and makes new ones (the old ones then stop working).
5. **Lost phone:** log in with a recovery code, then set the app up again (`/account/2fa/`: deactivate, then
   activate). No recovery code either: a superuser checks who is asking (by phone or in person) and deletes the
   person's authenticator (admin → MFA → Authenticators); the next log-in asks for a new one. A superuser locked out
   alike:
   `dj shell -c "from allauth.mfa.models import Authenticator as A; A.objects.filter(user__email='x@example.com').delete()"`.
6. **Leaving:** an owner offboards them in one step (`people/<id>/offboard/`: deactivated, roles and scopes gone,
   sessions and API keys ended); in the admin, untick Active (the sessions stop working at once) and take the roles
   away.

To make everyone log in again, with the second factor:
`dj shell -c "from django.contrib.sessions.models import Session; Session.objects.all().delete()"`.

### Break-glass accounts

The superuser flag is only on one or two break-glass accounts, outside Google sign-in, each with a security key and a
backup key kept offline; the founder's daily account holds the OWNER role instead (DEPLOYMENT.md section 23). Use one
only when nothing else works (Google sign-in down, every owner locked out of their account):

1. Log in with it as any member of staff does. The owners are emailed at once ("Break-glass account #… signed in"),
   and every audit event of the session carries `break_glass`. Its session ends after 15 idle minutes.
2. Do what the emergency needs, nothing more, and log out.
3. Within 24 hours an owner or the auditor reads what it did: `GET /api/v1/staff/audit/?break_glass=true` (the staff
   API, as an AUDITOR or OWNER), and notes why in the incident or the access review.
4. Every quarter: log in with each one once (the keys still work), log out, review that event, and check who can
   reach the keys.

## Data requests and privacy

### A data request under the DPDP Act

Most requests are self-service on My account: Download my data, change the email address, Delete my account. For a
request by email or letter:

1. **Check who is asking.** Answer only to the account's email address, or, for a student under 18, to the parent's
   contact recorded at sign-up. Note the request (date, person, what was asked) in your support mailbox.
2. **See the data:** `dj shell -c "import json; from django.core.serializers.json import DjangoJSONEncoder; from accounts.models import User; from accounts.views import export_user_data; print(json.dumps(export_user_data(User.objects.get(email='x@example.com')), cls=DjangoJSONEncoder, indent=2))" > export.json`
   and send the file to that address; delete your copy afterwards.
3. **Correct:** edit the user in the admin (ADMIN role; the admin's history records the change).
4. **Delete or withdraw consent:** with the seven-day waiting period,
   `dj shell -c "from accounts.models import DeletionRequest, User; DeletionRequest.objects.create(user=User.objects.get(email='x@example.com'))"`;
   at once (when the person asks for that in writing), add `.complete()` to the created request. Order and invoice
   records stay as tax law requires ("Purging old orders" below). The "email me when it is back" requests under the
   address go with the account. Quotation requests made with the address (admin → Shop
   → Quote requests) are not erased by the purge: delete them too (ADMIN).
5. **Nominee:** record the nominee with the request in your support mailbox; act on their request on proof of death or
   incapacity.
6. **Answer** within the time the Privacy Policy states (the DPDP Rules allow at most 90 days for grievances). Consent
   records (admin → Consent records, CSV export) show what was agreed to, when, under which policy version, how (ticked,
   or confirmed through the link emailed or texted to the parent) and whether a parent gave it.

The parental consent is self-declared while `PARENTAL_CONSENT_MODE=declared` (a parent ticks the box). The DPDP Rules,
2025 ask for verifiable consent of a parent from May 2027: switch to `verified` before then ("Parental consent" below).

### Purging old orders

- **Every day (automatic):** the 04:30 clean-up strips the name, phone, address lines and email address ("deleted",
  in the order's history too, and staff's notes on the order go) from orders never paid or placed, 30 days after they
  were cancelled; it also clears the stored Razorpay webhook fields of payments older than 180 days.
- **Every April (by hand), invoiced orders past eight years:** the tax records are kept for eight years. Then the same
  details leave those orders and their PDFs are deleted (the order rows and their numbers stay, for the totals):

  ```sh
  dj shell -c "
  from datetime import timedelta
  from django.utils import timezone
  from shop.models import CreditNote, Invoice, Order
  from shop.services import forget_orders
  old = Order.objects.filter(placed_at__lt=timezone.now() - timedelta(days=8 * 365 + 2))
  for document in [*Invoice.objects.filter(order__in=old), *CreditNote.objects.filter(invoice__order__in=old)]:
      document.pdf.delete()
  print(forget_orders(old), 'orders purged')"
  ```

  Then purge the same years from the off-site backups (bucket lifecycle) and note the date in the support mailbox.

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
- SES keeps an account-level suppression list too (hard bounces and complaints): remove the address there as well
  (SES → Account dashboard → Suppression list), or SES drops the email anyway.
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

**"My code never came".** SMS log: no row (the number is not confirmed on any account, or the student typed another one;
log-in codes go only to a confirmed number), "refused by the provider" (Sentry has MSG91's reason: template, IP
whitelist, balance), "not sent: a limit was reached" (see above) or "sent" (ask MSG91's report with the request id: DND,
a switched-off phone). The student can always use "Log in with a code" with the email address instead.

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

- **Who is waiting:** `dj shell -c "from accounts.models import User; print([u.email for u in User.objects.filter(is_active=True, date_of_birth__isnull=False) if u.consent_pending])"`.
  After the switch this includes students under 18 who registered before it; email them that a parent must confirm.
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

Orders are found in the admin (Shop → Orders): search by order number, email, name, phone or tracking number. An order's
page lists its payments, refunds, shipments and internal notes, and its History button shows every change of status.

Who does what (`accounts/roles.py`; `dj bootstrap_roles` after a change): CONTENT_EDITOR keeps the catalogue (products,
categories, collections, product types and attributes, pictures) and the course content; SALES the orders (staff orders,
payment links, offline payments, notes), offers, coupons, prices and stock, reviews, quotations and stock alerts;
SUPPORT sees orders, notes and reviews and opens courses by hand (entitlements); ADMIN everything except the
superuser-only items, which it can view (periodic tasks, task results, groups and permissions, second factors, Google
sign-in), imports and exports included.

### A stuck payment (the customer paid, the order still says "awaiting payment")

Razorpay's webhook normally completes an order within seconds, even when the customer never comes back from the payment
page. If it did not:

1. Razorpay Dashboard → Payments: find the payment (the customer's UPI ID or phone, the amount). The receipt of its order
   is the order number. Note its status: captured, authorized or failed.
2. `dj reconcile_payments` asks Razorpay about every online order of the website's checkout still awaiting payment
   (older than 10 minutes; not the staff orders: see "Staff orders and payment links") and records the payments it
   took: `EL-2026-000123: paid now`. An authorized payment is captured first (when the amount
   matches). "no payment at Razorpay": it has none for that order (the customer did not pay, or paid another order).
   "Razorpay could not be asked": try again later.
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
   ...): fix the cause, then use the order's action "Refund in full through Razorpay" again (a failed refund does not
   block a new one; on a paid or packed order that action cancels the order).
2. Cash-on-delivery orders, and payments recorded offline, are refunded by bank transfer or UPI, outside the site: pay it
   from the business account and note it in your support mailbox (or on the order's internal notes). The refund action
   refunds nothing for them (on an order not yet shipped it still cancels the order, which puts its copies back and
   emails the customer).
3. A refused parcel is refunded less the shipping: the same action with an amount (shipped or delivered orders only; an
   order not yet shipped is cancelled and refunded in full whatever amount is typed). A part-refunded order then reads
   "refunded".
4. A refund made in the Razorpay Dashboard is recorded when its webhook arrives ("Refunded in the Razorpay dashboard."):
   the order turns "refunded", the customer is emailed and the credit note is made. Stock is not put back by itself:
   correct it in Products.
5. Every refund of an invoiced order that the site records has a credit note (admin → Credit notes, and on the order
   page); a refund paid outside the site (cash on delivery, an offline payment) has none: ask the accountant how to
   issue the credit note.

A refund whose answer was lost (Razorpay slow) is never sent twice: each retry first asks Razorpay for the payment's
refunds and takes over the one that carries the site's refund number in its notes.

### A customer paid twice

Razorpay can capture a second payment for an order that is already paid (a late UPI approval, a second tab). The site
records it as a payment of its own and refunds it in full by itself: the error log (Sentry) says "Razorpay payment pay_…
is a second payment for order EL-…; refunding it", the order lists a second payment and a refund ("Paid twice: the
second payment is refunded."), and the customer gets the refund email. The order stays paid by the first payment.
Nothing to do, except to check in the Dashboard (Refunds) that the refund went through, and to reply to the customer
with the `rfnd_…` ID if they ask. If the refund failed (admin → Refunds, *failed*): refund that payment in the Razorpay
Dashboard (its webhook records it); do not use "Refund in full" on a paid or packed order for it, which cancels the
order.

### Test mode and live mode

Every payment and order records the mode of the Razorpay keys that made its Razorpay order (`livemode`; the order's
page in the admin shows "Live mode"). The site trusts only its own mode: with live keys, a test-mode payment, its
webhooks and its refunds change nothing (logged: "… (test mode) ignored"), and a test-mode order shows **TEST** next to
its number and cannot be packed or shipped ("Not possible for EL-… (a test order)"). Its invoice and credit notes stay
in the test series (`T/`, `TC/`) whenever they are made. Webhooks are checked with the secret of the keys' mode:
`RAZORPAY_WEBHOOK_SECRET_TEST` for `rzp_test_` keys, `RAZORPAY_WEBHOOK_SECRET` for live ones.

Going live (the steps are in DEPLOYMENT.md, section 12):
1. Live keys and the live webhook's own secret in `.env` (`RAZORPAY_KEY_ID=rzp_live_…`, `RAZORPAY_KEY_SECRET`,
   `RAZORPAY_WEBHOOK_SECRET`); keep `RAZORPAY_WEBHOOK_SECRET_TEST`. `SHOP_OPEN=1`. `docker compose up -d`.
2. Test orders still pending and older than two days are cancelled by the 04:30 clean-up (the live keys see no payment
   for them). Leave paid test orders as they are: they count nowhere in the tax series, and cancelling one would ask the
   live account to refund a test payment, which cannot work (the refund stays "requested" and is queued again every
   night).
3. Back to test keys (a rehearsal): the same in reverse; live orders then show nothing special but their payments and
   webhooks are ignored until the live keys are back. Do not take real orders meanwhile: `SHOP_OPEN=0`.

Orders made before this mode was recorded (the security release) count as test orders. If the shop had already taken
real payments before it, mark those live by hand, with the first live order's number:
`dj shell -c "from shop.models import Order, Payment; o = Order.objects.filter(number__gte='EL-2026-000123', placed_at__isnull=False); Payment.objects.filter(order__in=o).update(livemode=True); print(o.update(livemode=True))"`.

### Reconciling Razorpay settlements (monthly)

1. Razorpay Dashboard → Reports: download the month's transactions and settlements as CSV.
2. Admin → Orders (the ADMIN role: exports need it, and each is logged): filter the list to the month (the date links
   above it), then Export (CSV or XLSX). Match on the order number: it is the "receipt" of every Razorpay order and in
   its notes.
3. Per order, paid online means captured; the settlement is what was captured, less the refunds, less Razorpay's fee and
   the GST on the fee (the fees are not in the site). The admin index shows revenue net of refunds.
4. Differences to look at: a captured payment whose order is cancelled and has no refund (it should not happen: see
   Payments and Refunds in the admin; refund it with the order's "Refund in full" action, which refunds a cancelled
   order without changing it, or in the Dashboard); a refund at Razorpay that the site does not know (the webhook was
   lost: resend it from the Dashboard); disputes and chargebacks (Dashboard → Disputes: answer with the invoice, the
   tracking number and the delivery date from the order page; the site does not record chargebacks).
5. Invoices and credit notes are numbered one after the other in each financial year (`EL/2026-27/00001`,
   `CN/2026-27/00001`) and a number is never reused. Test-mode documents are in their own `T/` and `TC/` series: not for
   the tax return. Cash on delivery: the courier remits the cash it collected (less its fee) some days after delivery;
   match its report with the tracking numbers (the payment is recorded as captured when "Mark delivered" is pressed).

### An invoice or credit note is missing

The order page says "The invoice will appear here in a few minutes" for a paid online order (cash on delivery: the
invoice is made when the parcel is marked shipped). Look in `docker compose logs worker | grep -i invoice` (or Sentry).
The usual cause is the seller's details: while `SELLER_ADDRESS`, `SELLER_EMAIL` or `SELLER_PHONE` still hold their
`[placeholder]`, no real invoice is numbered ("SELLER_* still holds placeholders"): set them in `.env` and
`docker compose up -d`. The 04:30 clean-up then makes what is missing, or at once:
`dj shell -c "from shop.tasks import generate_invoice; generate_invoice(<order id>)"` (the id is the number in the
order's address in the admin). WeasyPrint failing (fonts, Pango) is in the same log. A missing credit note is made the
same way: `dj shell -c "from shop.tasks import generate_credit_note; generate_credit_note(<refund id>)"` (the id is the
number in the refund's address in the admin); the 04:30 clean-up makes missing ones too.

### Guests and their order links

Every order email except the delivery one carries its link (`/orders/t/<22 characters>/`): it opens the order without an
account, read only, with its invoice and, until it is packed, a cancel button. A guest who lost the emails uses "Find
your order" (order number and email address): the link is emailed to the order's address, and the page always answers
"If an order matches, we have emailed you a link." (10 tries an hour per address, per email address and per order
number). Orders of accounts are not found there: their owners log in. Never send an order's link to any other address
than the order's.

### Shipping with tracking links

Packing, shipping and delivery need `staff.pack_order`: ADMIN's in the admin, PACKER's in the panel's packing queue
once it is built (SALES no longer has them).

Orders → select the packed orders → "Mark shipped": choose the courier, type the tracking number (AWB) and leave the
link empty. The site fills it in: Delhivery, Blue Dart and Ekart open their own tracking page; India Post (its page
needs a CAPTCHA), DTDC, Xpressbees and "another courier" open 17TRACK with the number. The customer's email carries the
link (the SMS, when they asked for SMS, gives the courier and the tracking number), and the order page shows it. Type a
link yourself only for a courier whose page you know takes the number in the address. A wrong number: correct it in the
order's Shipments; correct the link too (empty is not refilled there). The first time each courier is used, open the
emailed link once with a real number to check it.

This stays the way for India Post and any courier without an API. A parcel booked with a courier through Shiprocket
(`shipping/`) is shipped and delivered by the courier's own scans instead, and its row on the order's page is read
only: see "Couriers and integrations". A consignment above ₹50,000 needs an e-way bill.

### GST returns (GSTR-1 export)

Each month (or quarter), for the accountant:

    docker compose exec web python manage.py export_gstr1 --from 2026-10-01 --to 2026-10-31 --out /tmp
    docker compose cp web:/tmp/gstr1-20261001-20261031-b2c.csv .   # and -hsn.csv, -credit-notes.csv

- `…-b2c.csv`: the invoices' supplies by place of supply ("18-Assam") and GST rate: taxable value, IGST, CGST, SGST,
  the number of invoices and their shipping (in the row of each invoice's highest rate). Rows at 0 % are the exempt
  books (GSTR-1 table 8); taxed rows go to B2CS (table 7).
- `…-hsn.csv`: the HSN summary (table 12): quantity, total value, taxable value and tax per HSN code and rate.
- `…-credit-notes.csv`: each credit note dated in the period, by rate, with its invoice; refunds of a shipping charge
  in the last column.

Only the real series is exported (`EL/…`, `CN/…`), never test-mode documents. Amounts are those printed on the
invoices and credit notes (prices include tax; the coupon, offers and a staff discount are shared over the lines).
Orders the site does not invoice (a school order paid outside the site and never entered as a staff order) are not in
the files; staff orders are.

### Coupons

A coupon's uses are the paid or placed orders not cancelled or refunded; the Coupons list shows how many. Untick *is
active* to stop a coupon at once; orders already made keep their discount.

### Offers

Shop → Offers: automatic discounts, no code. Per cent or rupees off what the offer covers ("on": the whole cart, chosen
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

For a phone order or a school's quotation accepted: Orders → "Add order" (the button reads "Add order"; it opens "New
phone or school order"): the customer's email (an account whose confirmed address it is gets the order: needed for a
course), the delivery address, the products and copies (rows left empty are skipped), a discount in rupees (after the
offers), the shipping (empty: the shipping rates'), an internal note. With "Email a Razorpay payment link now" ticked,
Razorpay makes a Payment Link for the total and we email it; the action "Email a Razorpay payment link" sends the same
link again. When the customer pays, Razorpay's `payment_link.paid` webhook pays the order: copies taken, confirmation
email, invoice, as for the website's orders (a book sold out meanwhile: cancelled and refunded, as there). A link
lives 15 days; a staff order not paid in 16 days is cancelled by the daily clean-up, which first asks Razorpay
whether its link was paid. The order list's filter "created by → not empty" lists the staff orders.

A customer says the link was paid and the order still waits (the webhook was lost): ask Razorpay at once,
`dj shell -c "from shop import payments; from shop.models import Order; print(payments.reconcile(Order.objects.get(number='EL-2026-000123')))"`
records the payment if the link was paid (`True`), `False` means nothing was paid, `None` that Razorpay could not be
asked.

### Payments received offline (NEFT, IMPS, UPI)

1. Check on the bank statement that the whole total has arrived; note its reference (UTR or UPI reference).
2. Orders → tick the order (one) → "Record a payment received offline" → type the reference → "Record the payment".
3. The order is paid (copies taken, the customer emailed, the invoice made with "bank transfer or UPI to our account,
   reference …"). Refused if the order is no longer waiting for payment or a book has sold out (nothing recorded).

Refunds of such payments are made by bank transfer by hand ("I have not got my refund", above); cancelling the order
puts its copies back and emails the customer.

### Notes, the customer page, the dashboard

- **Notes** (an order's page, "internal notes"): what was promised on the phone, a school's purchase order. Signed with
  your name; the customer never sees them; changes to a note are kept in the database, but the admin shows no history
  page for them. They are deleted with the order's customer details (eight years on, or 30 days after an unpaid order's
  cancellation).
- **The customer page**: an order's "customer" link (accounts only) gathers the account's orders (and guest orders
  with its email address), saved addresses, reviews, quotation requests, stock alerts and courses, each part for staff
  allowed to see it.
- **The dashboard** (admin home) adds sales by day for two weeks, the five most sold books of the last 30 days, the
  books running out (below `SHOP_LOW_STOCK`), and the reviews and quotation requests waiting. Stock alerts (who waits
  for which book) are under Shop → Stock alerts.

### Categories, collections, attributes

- **Categories** (Shop → Categories) form a tree: "Add category" with its place (first child of a category, or a
  sibling), or drag a row to move it with its sub-categories. A product is put on its shelves in its own form
  ("Shelves, type and related products"), several allowed; a category's page (`/shop/category/<slug>/`) shows the
  products of its sub-categories too. The shop's main page lists the top categories.
- **Collections** are hand-picked lists ("Board 2027 essentials"): add the products in the collection's form; their
  `position` numbers give the order, the collection's own number the order of the collections. Untick "shown" to hide
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
- **Bulk actions** on Products: "Put on sale", "Take off sale", and "Set stock": type the copies in the box beside the
  action, tick the books, run it (bundles and digital products have no copies of their own and are skipped).
- **Spreadsheets (ADMIN):** Products → Export (all, or "Export selected" from the action list) and Import, matched by
  slug: change titles, prices, texts, categories (slugs separated by `|`) and import; a row whose price is above the MRP
  is refused, and stock is never imported (sales go on meanwhile: use "Set stock"). Categories → Export/Import: one row
  per category, a parent before its children (`parent` is its slug); an import adds new categories and renames, it
  moves none. Every export is written to the admin log.

### Digital products (the revision course)

A product of kind "Digital (in the app)" opens the course of the `learn` app in the buyer's account once paid ("The
revision course" below): a pass alone, or in a bundle with a book (the bundle's copies are the book's). Customers need
an account, pay online (no cash on delivery), buy one at a time and pay no shipping for it; an order of digital products
only is marked delivered at once (no packing). Cancelling a paid order, or refunding it in full, closes the course again
(a part refund does not). A bundle of digital products only (a pass for two subjects sold as one) is a course too: no
shipping, nothing to pack, delivered once paid. Set the SAC code and GST rate your accountant gives (the form refuses
4901, the books' HSN).

## Couriers and integrations

Parcels booked with a courier through Shiprocket (`shipping/README.md`), on the integrations framework
(`integrations/README.md`). Admin → Shop → Shipments lists every parcel by status, courier and last scan, each with
its timeline, exceptions, charges and COD remittance; Admin → Shipping → Shipping exceptions is the to-do list, by
deadline; Admin → Integrations has the accounts, the call log, the dead letters and the webhooks received. The admin
panel will show the same through `/api/v1/shipping/` (API.md "Shipping (staff)").

### Shiprocket is unavailable (a circuit open)

After 5 failures in 5 minutes (no answer, 429, 5xx) the account's circuit opens: calls wait, tasks are put back in the
queue to try again after 5 minutes, one trial call goes every 5 minutes and closes it on success. The account in Admin
→ Integrations shows "open: calls wait" and since when; `/health/integrations/` fails once it has been 30 minutes.

1. Look at the account's last error and the call log (Admin → Integrations → Integration calls, filtered by the
   account): `HTTP 503` or `ConnectTimeout: no answer` is Shiprocket's side (check its status page and its emails);
   `HTTP 429` is its rate limit (wait); a run of `HTTP 401` is the token or the API user (below).
2. During an announced outage, the action "Hold the circuit open" stops the calls until "Reset the circuit".
3. Meanwhile a parcel can go by hand: book it with `courier` and `tracking_number` (API.md), or the order's "Mark
   shipped" in the admin. Quotes show Shiprocket's last answer, marked stale.
4. Once it answers again the circuit closes by itself; the waiting tasks run; the 2-hourly poll reads the tracking
   missed meanwhile.

**401 after 401:** the API user's password changed, the user was deleted, or its modules were narrowed. Replace the
credentials ("Secrets and key rotation") and test the connection. The token is renewed by itself from day 9 and once
after a 401.

### Dead letters and failed webhooks

A task that gave up (8 tries over about four hours, or refused: a 422 with Shiprocket's reason) is a dead letter:
Admin → Integrations → Integration failures, with the operation, its arguments (ids), tries and last error;
`/health/integrations/` fails while one waits. Read the error, fix the cause (a pickup nickname Shiprocket does not
know, a product without weight, a COD total that does not add up, the circuit), then "Replay" (it runs once more; a new
dead letter if it fails again), or "Discard" with the reason (e.g. "booked by hand in Shiprocket's panel"). A webhook
that could not be processed is an inbound event marked failed (Admin → Integrations → Inbound events): "Process again"
once the cause is fixed. Rejected events (a wrong or missing token) are kept without their body: many from one
address are someone else's; many in a row after a token change mean Shiprocket still sends the old one (paste the new
one, "Secrets and key rotation").

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
order cannot be marked cancelled once shipped (its state machine has no such step, and no "returned" state: a decision
for the founder): it stays shipped, with the note; a prepaid order is sent again (book a new parcel: it gets the
reference `<order>-R1`) or refunded (the order's refund action). A lost or damaged parcel: claim it with Shiprocket
(up to ₹5,000 or the order's value), then reship or refund. Resolve the exception with what was done.

### COD remittances

A delivered cash-on-delivery parcel expects its cash 10 working days later (Shiprocket pays D+8 working days, on
Mondays, Wednesdays and Fridays). Each morning (05:15) the site asks Shiprocket about the awaited ones: remitted (with
the UTR), mismatched (another amount: an exception) or overdue (2 working days past the day: an exception). Match the
UTR with the bank statement; for a mismatch or an overdue one, raise it with Shiprocket's support with the AWB and the
order, and resolve the exception with their answer. `dj shipping_check_cod` asks at once.

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
3. When the school accepts, enter the order: Orders → "Add order" with the school's email, the delivery address (the
   request has only a PIN code: ask for the rest) and the books of the quotation ("Staff orders and payment links"),
   then either send the Payment Link or, when the money arrives by NEFT or UPI, "Record a payment received offline".
   The order is then paid, its copies taken, its invoice made by the site. Set the request's status to "ordered"; a
   request that comes to nothing, "closed". The site does not turn a request into an order by itself.

### Stock, stock alerts and the low-stock email

- Stock is taken when an online order is paid (cash on delivery: when it is placed) and given back when the order is
  cancelled. A stock typed in Products is set as typed; saving a product page for any other reason keeps the copies
  customers bought meanwhile. Books sold outside the site: lower the stock by hand (Products, or "Set stock").
- A product out of stock shows "Email me when it is back" (signed-in accounts only; a visitor is asked to log in; the
  email goes to the account's address). Each address gets one email, within the hour after copies are back (the stock
  raised in Products, or a cancelled order's copies returned), and is then forgotten; alerts never sent are deleted
  after a year.
- Each morning at 8 the SALES role is emailed the books on sale with fewer copies than `SHOP_LOW_STOCK` (5). Nothing
  is sent when no book is low. Bundles and digital products have no stock of their own: their books are in the list.

## The revision course

Content editors (CONTENT_EDITOR) work in the admin under **Revision course**; DEPLOYMENT.md section 18 has the set-up.

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
5. **Revisions → select → "Publish the selected revisions"**: only revisions with at least one ready clip are
   published. The app shows them at once. "Back to draft" hides one again; students keep their progress.
6. Order of clips: change the numbers, or Clips → select → "Move up" / "Move down".
7. Quiz items: `build_quiz_items` made them from the papers; check a few per chapter (Quiz items, filtered by subject)
   and correct or delete what reads badly. Running the command again adds only new ones and keeps edits.

### A clip that failed

The clip shows "failed" and its page (or Preview) the end of ffmpeg's messages. Usual causes: the file is not a video or
is cut short (re-export it from the phone and upload it again), a codec ffmpeg cannot read (export as H.264 mp4), or the
media worker ran out of time or memory (more than about 50 minutes of encoding: split the video). The worker accepts
only mp4, mov, m4v, webm or mkv with H.264, HEVC, VP9 or AV1 video and AAC, Opus or MP3 sound; anything else fails at
once with "Not a video we take". If the upload itself fails ("The upload was cut off", or "The bucket refused the video
(403)"), the bucket's CORS rule lacks PUT for the site's origin (DEPLOYMENT.md section 17) or the 15-minute link ran
out: choose the video again. After a new upload the clip is processed again by itself. To retry without a new upload
(the bucket or the worker was down):

```sh
docker compose exec web python manage.py reprocess_clips            # the failed ones, and those "processing" for over an hour
docker compose exec web python manage.py reprocess_clips 12 15      # these clips
docker compose exec web python manage.py reprocess_clips --all      # every clip (after changing LEARN_PUBLIC_VIDEO)
```

or Clips → select → "Process the video again". Clips stuck in "processing" mean the queue lost the task (Redis or the
worker restarted): `docker compose ps media-worker`, then the first command.

### Printing book codes

Each book can carry a code that opens the course in the app (a sticker or a printed slip inside the cover). Make them
for the print run, one batch per run, and send the CSV to the printer:

```sh
docker compose exec web python manage.py make_book_codes PHY 5000 --batch PHY-2027-1 --out /app/media/PHY-2027-1.csv
docker compose cp web:/app/media/PHY-2027-1.csv . && docker compose exec web rm /app/media/PHY-2027-1.csv
```

`ALL` instead of `PHY` makes codes that open every subject (a four-book set). The CSV is the only copy of the codes (the
database keeps a keyed hash): send it to the printer over a private channel and delete it once the print run is checked.
Codes look like `7KQM-3XPA-9TRW` (no 0, O, 1 or I). Set `LEARN_CODE_SECRET` before the first batch and never change it
(DEPLOYMENT.md section 18; the command refuses without it and a server does not start without it). A batch printed by
mistake: Book codes → filter by batch → delete them (ADMIN; a code already redeemed keeps its entitlement).

### Granting access

Entitlements → Add: the student (by id: find it in Users), the subject (empty: every subject), the last day (empty: no
end), and why in the note (a school order, a complaint, a reviewer). The app shows the subject open at once. Purchases
of a digital product in the shop grant themselves when paid; an entitlement is never needed for the free previews.

### A lost code, or "my code says used already"

1. Ask for the code (a photo of the slip) and look for it: Book codes → search with the whole code. Not found: a typo
   (0/O and 1/I are not used), or a code from another batch or a fake.
2. **Found and not redeemed:** the student can type it again; after 5 tries an hour (right or wrong; per account, and
   separately per internet address) the app must wait.
3. **Redeemed by this student:** nothing to do (Entitlements, search by the email, shows it).
4. **Redeemed by someone else:** ask for proof of purchase (the book, the bill). If it holds, grant access as above with
   the note "code #<id> used by another account" and keep the other entitlement unless the code was clearly stolen (then
   delete that entitlement: ADMIN; its owner will contact you if it was theirs).
5. **No code at all** (lost slip): proof of purchase, then a grant until the end of the exam season.

## Insights

The predictive jobs (`insights/README.md`) run at night from 01:00 to 03:00 and keep their rows in the admin under
Insights; staff read them there or through `/api/v1/insights/`. They never name a student: what they say about
learners is about groups of 5 or more.

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
5. Acknowledge what you looked at (Fraud signals → select → "Acknowledge"): it comes back only if it grows. The
   subject is a keyed hash: the admin's tables match it, nobody can read it back.

### The monthly review, in season

`dj insights_review` prints each title's last four complete weeks: the forecast made before each week, the copies
sold and the seasonal naive, with both errors (WAPE). Then insights/README.md, "The monthly review": the backtest's
summary, the print runs to act on, the fraud signals still open, and a note in the season of what changed.

### A new season

Enter its exam dates as soon as the board publishes them (Insights → Exam seasons: board, class, academic year, first
and last written paper; practicals do not count) and the print costs of the new titles (Insights → Print costs). The
forecasts move to the new season on the day of the old one's first paper.

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
  prints the failing check (`docker compose logs web`).
- **/health/integrations/ returns 500:** its JSON names what waits: a provider unavailable for 30 minutes (a circuit
  open), dead letters, failed webhooks ("Couriers and integrations"). The site itself is not down for it.
- **The queue's Redis (`redis`) is down:** emails and SMS are sent inside the request; the AVIF and WebP sizes of a
  product picture that staff upload are made inside the request too (slower, not an error); a clip video stays
  "processing" until `dj reprocess_clips` queues it again.
- **Disk full:** `docker system df`; old images (`docker image prune`), backups beyond `BACKUP_KEEP_DAYS`; logs are
  rotated already; the clips' videos are in the `media` volume unless the buckets are set.
- **Certificate problems:** `docker compose logs caddy`; DNS must point at the server and ports 80/443 be open.
- **Someone locked out by django-axes** (10 failed log-ins): it lifts after 15 minutes, or run
  `dj axes_reset_username x@example.com`.
