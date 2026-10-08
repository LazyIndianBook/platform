# Runbook

Commands run in `/srv/examleaf/examleaf-web` on the server. `dj` below stands for
`docker compose exec web python manage.py`.

## Restore the database from a backup

1. Pick the dump: `ls -lt backups/`, or download it from the backup bucket (`database/examleaf-….dump`, or
   `….dump.age` when `BACKUP_AGE_RECIPIENT` is set: decrypt it on the computer that holds the key,
   `age --decrypt -i examleaf-backup.key -o examleaf-….dump examleaf-….dump.age`, then copy the dump to `backups/`).
2. Note the account deletions completed since that dump was taken, because restoring brings those people's data back:

   ```sh
   dj shell -c "from accounts.models import DeletionRequest as D; print(list(D.objects.filter(status='done', closed_at__gte='2026-10-08 02:15+05:30').values_list('user_id', flat=True)))"
   ```

3. Stop everything that writes, restore, start again:

   ```sh
   docker compose stop web worker beat
   docker compose exec -T db pg_restore --clean --if-exists --no-owner --username examleaf --dbname examleaf < backups/examleaf-YYYYMMDD-HHMMSS.dump
   docker compose up -d
   ```

4. Erase the noted accounts again:
   `dj shell -c "from accounts.models import DeletionRequest as D, User; [(u.pending_deletion or D.objects.create(user=u)).complete() for u in User.objects.filter(pk__in=[…])]"`.
   Deletions that were still waiting are completed by the next daily purge (or run
   `dj shell -c "from accounts.tasks import purge_due_deletions; print(purge_due_deletions())"`).
   Students who asked for deletion after the dump was taken must ask again: tell them.
5. Check `/health/` (`curl -H "X-Health-Token: $HEALTH_CHECK_TOKEN" https://examleaf.in/health/`), log in to the admin,
   open a paper.

On a new server: follow DEPLOYMENT.md up to `docker compose up -d`, then restore as above (the empty database's tables
are replaced).

## Rotate secrets

Change the value in `.env`, then `docker compose up -d` (it recreates the containers whose settings changed).

- **SECRET_KEY:** put the old key in `SECRET_KEY_FALLBACKS`, the new one in `SECRET_KEY`; remove the fallback after
  two weeks (sessions and password-reset links made with the old key keep working until then). Consent records'
  address hashes made with the old key can no longer be compared with an address; the records themselves stay valid.
- **POSTGRES_PASSWORD:** `docker compose exec db psql -U examleaf -c "ALTER USER examleaf PASSWORD 'new'"`, then change
  `.env` and `docker compose up -d`.
- **Email provider, Sentry, bucket keys:** create the new key with the provider, change `.env`, `docker compose up -d`,
  then revoke the old key.
- **Staff passwords:** each person changes theirs at `/account/password/change/`; take roles away from people who left
  (Users → "Take away role …", and untick Active).
- **JWT_SIGNING_KEY** (the app's tokens; SECRET_KEY while unset): a new value logs every app out at once; the website's
  sessions stay.
- **Suspected breach:** rotate everything above, SECRET_KEY **without** a fallback (a leaked key would otherwise keep
  sessions and reset links valid for two weeks) and JWT_SIGNING_KEY (or SECRET_KEY, if it is unset) too, end all
  sessions (`dj shell -c "from django.contrib.sessions.models import Session; Session.objects.all().delete()"`; everyone
  logs in again, staff with their authenticator app), change `HEALTH_CHECK_TOKEN`, find out what was
  exposed, and inform the Data Protection Board of India and the people affected without delay (the DPDP Rules, 2025
  ask for a detailed report to the Board within 72 hours). Keep notes of what happened and what was done.

## A data request under the DPDP Act

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
   records (shop phase) stay as tax law requires.
5. **Nominee:** record the nominee in the user's support notes; act on their request on proof of death or incapacity.
6. **Answer** within the time the Privacy Policy states (the DPDP Rules allow at most 90 days for grievances). Consent
   records (admin → Consent records, CSV export) show what was agreed to, when, under which policy version and whether
   a parent gave it.

The parental consent is self-declared while `PARENTAL_CONSENT_MODE=declared` (a parent ticks the box). The DPDP Rules,
2025 ask for verifiable consent of a parent from May 2027: switch to `verified` before then ("Parental consent" below).

## When email fails

Signs: students say the code never came; Sentry errors from `ops.tasks.send_email`; failed or retrying tasks under
Celery → Task results; `docker compose logs worker | grep send_email`.

1. Is the worker up? `/health/` says so (Celery ping). If not: `docker compose up -d worker` and look at its logs.
   While Redis is down, emails are sent directly by the web process, so sign-ups keep working.
2. Does the provider accept mail? `dj sendtestemail you@example.com` sends synchronously and shows the provider's
   error (wrong API key, quota, unverified sender domain, account suspended). Check the provider's dashboard and status
   page, and the SPF/DKIM records.
3. A failed email is retried five times over about 25 minutes, then dropped. Once mail works, students press "send the
   code again" (or reset the password), which sends a new one. If Redis and the provider are down together, the web
   process tries once, logs "the email could not be sent here either" (Sentry) and the page goes on: the same answer.
4. To switch provider quickly: set `EMAIL_BACKEND` and the new provider's `ANYMAIL_…` key in `.env`
   (django-anymail supports Amazon SES, Mailgun, Postmark, SendGrid, Brevo and others), `docker compose up -d`, and
   send a test email.

## The shop

Orders are found in the admin (Shop → Orders): search by order number, email, name, phone or tracking number. An order's
page lists its payments, refunds and shipments, and its History button shows every change of status.

### A stuck payment (the customer paid, the order still says "awaiting payment")

Razorpay's webhook normally completes an order within seconds, even when the customer never comes back from the payment
page. If it did not:

1. Razorpay Dashboard → Payments: find the payment (the customer's UPI ID or phone, the amount). The receipt of its order
   is the order number. Note its status: captured, authorized or failed.
2. `dj reconcile_payments` asks Razorpay about every online order still awaiting payment (older than 10 minutes) and
   records the payments it took: `EL-2026-000123: paid now`. An authorized payment is captured first (when the amount
   matches). "no payment at Razorpay": it has none for that order (the customer did not pay, or paid another order).
   "Razorpay could not be asked": try again later.
3. Why did the webhook not arrive? Dashboard → Webhooks → the delivery log shows what the site answered. 400: the secret
   differs from `RAZORPAY_WEBHOOK_SECRET` in `.env` (correct it, `docker compose up -d`, resend the event). No attempts at
   all: the URL or the events are not set (DEPLOYMENT.md, section 12). Timeouts: the site was down.
4. Orders never paid within two days are cancelled by the 04:30 clean-up, which asks Razorpay first: a payment that was
   missed is recorded, not cancelled. A payment that reaches an order already cancelled (or whose books or coupon are
   gone) is refunded in full by the site, and the customer is emailed.

### "I have not got my refund"

1. Admin → Refunds, find the order. *processed* with a date: Razorpay has refunded it; give the customer the Razorpay refund
   ID (`rfnd_…`) and the date (banks take 5–7 working days; UPI is often quicker). *requested*: the task is waiting
   (Razorpay was unreachable: it retries for about four hours and the daily clean-up queues it again). *failed*: Razorpay
   refused it, the reason is in the Refund's error (a payment too old to refund, a balance too low ...): fix the cause,
   then use the order's action "Refund in full through Razorpay" again (a failed refund does not block a new one).
2. Cash-on-delivery orders are refunded by bank transfer or UPI, outside the site: pay it from the business account and
   note it in your support mailbox.
3. A refused parcel is refunded less the shipping: the same action with an amount (shipped orders only; an order not yet
   shipped is cancelled and refunded in full whatever amount is typed). A part-refunded order then reads "refunded".
4. A refund made in the Razorpay Dashboard is recorded when its webhook arrives ("Refunded in the Razorpay dashboard."):
   the order turns "refunded", the customer is emailed and the credit note is made. Stock is not put back by itself:
   correct it in Products.
5. Every refund of an invoiced order has a credit note (admin → Credit notes, and on the order page).

### Reconciling Razorpay settlements (monthly)

1. Razorpay Dashboard → Reports: download the month's transactions and settlements as CSV.
2. Admin → Orders (the ADMIN role: exports need it, and each is logged): select the month's orders and export them
   (CSV or XLSX). Match on the order number: it is the "receipt"
   of every Razorpay order and in its notes.
3. Per order, paid online means captured; the settlement is what was captured, less the refunds, less Razorpay's fee and
   the GST on the fee (the fees are not in the site). The admin index shows revenue net of refunds.
4. Differences to look at: a captured payment whose order is cancelled and has no refund (it should not happen: see
   Payments and Refunds in the admin, and `dj reconcile_payments`); a refund at Razorpay that the site does not know (the
   webhook was lost: resend it from the Dashboard); disputes and chargebacks (Dashboard → Disputes: answer with the
   invoice, the tracking number and the delivery date from the order page; the site does not record chargebacks).
5. Invoices and credit notes are numbered one after the other in each financial year (`EL/2026-27/00001`,
   `CN/2026-27/00001`) and a number is never reused. Test-mode documents are in their own `T/` and `TC/` series: not for
   the tax return. Cash on delivery: the courier remits the cash it collected (less its fee) some days after delivery;
   match its report with the tracking numbers (an order turns paid when "Mark delivered" is pressed).

### An invoice or credit note is missing

The order page says "The invoice will appear here in a few minutes" for a paid online order (cash on delivery: the
invoice is made when the parcel is marked shipped). Look in `docker compose logs worker | grep -i invoice` (or Sentry).
The usual cause is the seller's details: while `SELLER_ADDRESS`, `SELLER_EMAIL` or `SELLER_PHONE` still hold their
`[placeholder]`, no real invoice is numbered ("SELLER_* still holds placeholders"): set them in `.env` and
`docker compose up -d`. The 04:30 clean-up then makes what is missing, or at once:
`dj shell -c "from shop.tasks import generate_invoice; generate_invoice(<order id>)"` (the id is the number in the
order's address in the admin). WeasyPrint failing (fonts, Pango) is in the same log.

### Coupons and stock

- A coupon's uses are the paid or placed orders not cancelled or refunded; the Coupons list shows how many. Untick *is
  active* to stop a coupon at once; orders already made keep their discount.
- Stock is taken when an online order is paid (cash on delivery: when it is placed) and given back when the order is
  cancelled. A stock typed in Products is set as typed; saving a product page for any other reason keeps the copies
  customers bought meanwhile. Books sold outside the site: lower the stock by hand.
- Test mode to live mode: DEPLOYMENT.md, section 12, and "Test mode and live mode" below.

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
2. Test orders still pending are cancelled by the next 04:30 clean-up (the live keys see no payment for them). Paid test
   orders: cancel them in the admin if they clutter the lists (their test refund fails at Razorpay: harmless), or
   leave them; they count nowhere in the tax series.
3. Back to test keys (a rehearsal): the same in reverse; live orders then show nothing special but their payments and
   webhooks are ignored until the live keys are back. Do not take real orders meanwhile: `SHOP_OPEN=0`.

Orders made before this mode was recorded (the security release) count as test orders. If the shop had already taken
real payments before it, mark those live by hand, with the first live order's number:
`dj shell -c "from shop.models import Order, Payment; o = Order.objects.filter(number__gte='EL-2026-000123', placed_at__isnull=False); Payment.objects.filter(order__in=o).update(livemode=True); print(o.update(livemode=True))"`.

### A customer paid twice

Razorpay can capture a second payment for an order that is already paid (a late UPI approval, a second tab). The site
records it as a payment of its own and refunds it in full by itself: the error log (Sentry) says "Razorpay payment pay_…
is a second payment for order EL-…; refunding it", the order lists a second payment and a refund ("Paid twice: the second
payment is refunded."), and the customer gets the refund email. The order stays paid by the first payment. Nothing to
do, except to check in the Dashboard (Refunds) that the refund went through, and to reply to the customer with the
`rfnd_…` ID if they ask. If the refund failed (admin → Refunds, *failed*): refund that payment in the Razorpay Dashboard
(its webhook records it) or fix the cause and use "Refund in full" on the order.

A refund whose answer was lost (Razorpay slow) is never sent twice: each retry first asks Razorpay for the payment's
refunds and takes over the one that carries the site's refund number in its notes.

### Guests and their order links

Every email about an order carries its link (`/orders/t/<22 characters>/`): it opens the order without an account, read
only, with its invoice and, until it is packed, a cancel button. A guest who lost the emails uses "Find your order"
(order number and email address): the link is emailed to the order's address, and the page always answers "If an order
matches, we have emailed you a link." (10 tries an hour per address, per email address and per order number). Orders of
accounts are not found there: their owners log in. Never send an order's link to any other address than the order's.

### Purging old orders

- **Every day (automatic):** the 04:30 clean-up strips the name, phone, address lines and email address ("deleted",
  in the order's history too) from orders never paid or placed, 30 days after they were cancelled; it also clears the
  stored Razorpay webhook fields of payments older than 180 days.
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

## Other incidents

- **/health/ returns 500:** the JSON (`curl -H 'Accept: application/json' -H "X-Health-Token: $HEALTH_CHECK_TOKEN"
  https://examleaf.in/health/`; the results are up to 20 seconds old) names the
  failing part: database (`docker compose logs db`), cache (Redis), storage (disk full? `df -h`), Celery (worker).
  With Redis down the site keeps working without its cache (rate limits are off meanwhile; log-in, sign-up and password reset
  work) and sends emails itself; the shop's own limits refuse instead (Find your order, checkout, place order and
  coupon codes answer "Too many requests" until the cache Redis is back; online payments already started still
  complete). The cache is `redis-cache` and the queue `redis`:
  `docker compose up -d redis redis-cache`, then the daily clean-up queues again the invoices, credit notes and refunds
  that could not be queued. A web container that will not start prints the failing check (`docker compose logs web`).
- **Disk full:** `docker system df`; old images (`docker image prune`), backups beyond `BACKUP_KEEP_DAYS`; logs are
  rotated already.
- **Certificate problems:** `docker compose logs caddy`; DNS must point at the server and ports 80/443 be open.
- **Someone locked out by django-axes** (10 failed log-ins): it lifts after 15 minutes, or `dj axes_reset_username x@example.com`.

## Staff accounts

Every member of staff logs in with a password and a code from an authenticator app (SECURITY_REVIEW.md, H2). A
session lasts 8 hours from the log-in.

1. **New member of staff.** A superuser makes the account (admin → Users → Add, or the person registers on the site)
   and gives the role (Users → action "Give role …"; only superusers can).
2. **First log-in** at `/admin/` (it opens the site's log-in): email and password, then the code emailed to them the
   first time. The site then asks for an authenticator app before anything else opens: scan the QR code with Google
   Authenticator, Microsoft Authenticator, Aegis or 2FAS, type the 6-digit code, and the ten recovery codes appear.
3. **Recovery codes are kept offline:** download or write them down and keep them away from the phone (on paper in a
   safe place, or in a password manager). Each works once, instead of the app's code.
4. **Later log-ins:** password, then the app's code (or a recovery code). My account → "Two-factor" shows how many
   recovery codes are left and makes new ones (the old ones then stop working).
5. **Lost phone:** log in with a recovery code, then set the app up again (My account → Two-factor → deactivate,
   activate). No recovery code either: a superuser checks who is asking (by phone or in person) and deletes the
   person's authenticator (admin → Authenticators); the next log-in asks for a new one. A superuser locked out alike:
   `dj shell -c "from allauth.mfa.models import Authenticator as A; A.objects.filter(user__email='x@example.com').delete()"`.
6. **Leaving:** untick Active (the sessions stop working at once) and take the roles away.

When this is first deployed, staff sessions made before it carry on until they expire (up to two weeks). To make
everyone log in again, with the second factor: `dj shell -c "from django.contrib.sessions.models import Session; Session.objects.all().delete()"`.

## Parental consent

`PARENTAL_CONSENT_MODE=declared`: a parent ticks the box on the sign-up form. `verified` (switch before May 2027,
DEPLOYMENT.md section 14): a student under 18 gives a parent's email, the parent gets a link valid for 7 days, and the
account can read but not save marks or order books until the parent presses "I agree". Admin → Consent records then
shows the confirmation ("confirmed through the link emailed to the parent", with the time).

- **Who is waiting:** `dj shell -c "from accounts.models import User; print([u.email for u in User.objects.filter(is_active=True, date_of_birth__isnull=False) if u.consent_pending])"`.
  After the switch this includes students under 18 who registered before it; email them that a parent must confirm.
- **"My parent never got the link":** the student checks the address and sends it again from My account (also to a
  corrected address; one link every 10 minutes; a link sent to an old address stops working).
- **A parent without email:** the site has no other way to verify yet; the account stays read-only.
- **A parent who does not agree:** delete the account on request ("A data request under the DPDP Act").
