# ExamLeaf web: security review of phases 5 and 6

**Date:** 8 October 2026. **Scope:** what phases 5 A, 5 B, 6 D and 6 E added to `examleaf-web/` (commit 4e30e59, plus
the working tree's `ops/tasks.py`, which now builds an HTML part for every text email), with
`.github/workflows/ci.yml` and `.github/dependabot.yml`. Templates only for what the Python feeds them.
**Method:** read-only code review against OWASP ASVS 4.0 level 2; every finding was checked against the code and the
line is quoted. Library behaviour was checked in the installed source (`.venv`): Django 6.1.2, django-allauth 65.19.7,
fido2 2.2.1, django-anymail 15.2, django-storages 1.14.6, django-pictures 1.8.0, django-treebeard 7.0.2,
firebase-admin 7.7.0, DRF 3.18.3. The vendored hls.js was compared with the npm release's published SHA-256 (jsDelivr).
Nothing was run against a server and no other project file was changed. The findings of `SECURITY_REVIEW.md` (all fixed or
decided there) and its "Checked and sound" list are not repeated.

## Summary

| Severity      | Count |
|---------------|-------|
| Critical      | 0     |
| High          | 1     |
| Medium        | 5     |
| Low           | 12    |
| Informational | 10    |

Top three:

1. **H1:** `GUNICORN_CMD_ARGS=--timeout 600` gives every request of the site ten minutes, on sync workers, behind a
   Caddy that streams request bodies. One slow POST per worker (to the CSRF-exempt Razorpay webhook, for example) stops
   the whole site for ten minutes, with no account; before phase 6 it lasted 30 seconds.
2. **M1:** every code is now 6 digits (allauth's default is 8 letters). Email verification of an unconfirmed account
   can be guessed about 1,080 times an hour from one client address, so an attacker can "confirm" an address that has
   no ExamLeaf account yet (2.6 % a day, even odds in about four weeks). Staff phone and school orders for that
   address, and the courses they open, then go to the attacker's account.
3. **M2:** one daily SMS budget (500) covers every SMS, with no limit per number, per account or per purpose. Throwaway
   accounts adding mobile numbers, or, in `verified` consent mode, anonymous sign-ups through the API (no Turnstile),
   use it up. After that no log-in code, phone confirmation, consent link or order SMS reaches anyone until midnight,
   and the pages still say "a code has gone to …".

What holds up: OTP checks are constant-time, three tries, short-lived and enumeration-safe; unknown numbers get no
SMS; the passkey relying party and Google sign-in are set up safely (no linking by email); the consent token is a
salted, expiring HMAC; Payment Link webhooks go through the same signature, replay and amount checks as the rest of
Razorpay; course access is checked on the server for every clip, quiz item and card; HLS file names are allow-listed;
ffmpeg runs without a shell; only staff-written text is rendered as Markdown. See "Checked and sound".

---

## High

### H1. A 10-minute gunicorn timeout on sync workers behind a streaming proxy: one slow request per worker stops the site

**Where:** `docker-compose.yml:79-81`; `Caddyfile:9-16, 26`; `Dockerfile:31`; `.env.example:198`;
`shop/views.py:579-588`.

```yaml
# docker-compose.yml:80-81
# Clip uploads in the admin are read inside the request: a 10-minute worker timeout (gunicorn reads this variable).
GUNICORN_CMD_ARGS: ${GUNICORN_CMD_ARGS:---timeout 600}
```
```text
# Caddyfile:9-12, 26
@clip_upload path /admin/learn/clip/* /admin/learn/revision/*
request_body @clip_upload {
	max_size 500MB
}
reverse_proxy web:8000
```

- gunicorn runs its default sync workers (no `--worker-class`); there is one unless `.env` sets `WEB_CONCURRENCY`
  (3 in `.env.example`). A sync worker that reads a request body waits until the body arrives or the arbiter kills it
  after `--timeout`: now 600 s for every request of the site, not only clip uploads (gunicorn's default was 30 s).
- Caddy passes request bodies through as they arrive: `reverse_proxy` has no `request_buffers`, and the Caddyfile
  sets no server `read_body` timeout. A slow client therefore holds a gunicorn worker, not just a Caddy goroutine.
- Any view that reads the body will do. `razorpay_webhook` reads `request.body` (`shop/views.py:585`) with no
  account and no CSRF check; every DRF endpoint and every form POST read it too. Django refuses bodies over 1 MB by
  `Content-Length` before reading, so the attacker announces 1,000,000 bytes and sends one every few seconds.
- `/admin/learn/clip/*` and `/admin/learn/revision/*` take 500 MB bodies from anyone: the path matcher knows nothing
  of log-ins, and Django's CSRF middleware parses a multipart body (files over 2.5 MB to `/tmp`) before the admin
  checks the log-in, as soon as the request carries any CSRF cookie and a matching `Origin`.

**Scenario:** an anonymous client opens as many connections as there are workers and trickles a POST to
`/shop/webhooks/razorpay/` on each. Log-in, checkout and the Razorpay return page time out for ten minutes; a few
requests every ten minutes keep the site down (before phase 6, one every 30 seconds per worker). Parallel 500 MB posts
to `/admin/learn/clip/add/` also fill the web container's `/tmp`.

**Fix:**
- In Caddy, buffer bodies before they reach gunicorn on every route except the clip upload
  (`reverse_proxy web:8000 { request_buffers 10MB }` behind a `not path /admin/learn/*` matcher), and set server
  timeouts (`{ servers { timeouts { read_header 10s read_body 60s } } }`).
- Put the site's gunicorn back on the 30 s default and give it threads (`--worker-class gthread --threads 4`), so a
  slow client holds a thread, not a process.
- Take clip uploads off the site's workers: best, the admin uploads the video straight to the private bucket with a
  presigned POST and Django records only its key; or a second gunicorn service (`web-upload`, long timeout, 500 MB)
  that Caddy routes `/admin/learn/*` to, on its own site or port so the short `read_body` above stays for the rest.

**Status (2026-10-08):** fixed — gunicorn runs `--worker-class gthread --threads 8 --timeout 60` (docker-compose.yml): a
slow request holds one of a worker's threads, not the process. Caddy reads each body (up to 10 MB) before proxying
(`request_buffers 10MB`) and gives a client `read_header 10s` and `read_body 5m`, so a trickled POST holds a Caddy
connection, not gunicorn. With a bucket, clip videos go from the editor's browser straight to the private bucket:
`ClipAdmin`'s `upload-url/` (staff who may add or change clips; POST with CSRF) signs a PUT for
`learn/sources/<uuid>.<ext>` for 15 minutes with the file's Content-Length (at most `LEARN_MAX_UPLOAD_MB`) and a
Content-Type chosen from the extension as signed headers; `static/learn/upload.js` sends it with its progress and puts
the signed key into the form, which checks that the object exists and runs the model's type and size validators on it
(`learn/uploads.py`). The bucket's own origin joins `connect-src` on the clip pages only (I3). Without a bucket
(development) the upload stays in the form: Caddy's 500 MB on the clip pages stays for that fallback, and
`learn.uploads.LargeBodyGuard` refuses a body above `DATA_UPLOAD_MAX_MEMORY_SIZE` (or without a length) there, before
the CSRF check could read it, from anyone but signed-in staff. Tests: `learn/test_uploads.py`. Founder: the private
bucket's CORS rule needs PUT (DEPLOYMENT.md section 17).

---

## Medium

### M1. Every code is now 6 digits: an address without an account can be "confirmed" by guessing, about 1,080 tries an hour

**Where:** `examleaf/settings.py:185, 192`; `api/auth.py:319-337`; allauth `account/app_settings.py:278-279`,
`core/internal/cryptokit.py:16, 32-33`; consequences in `shop/admin.py:631, 640` and `learn/services.py:101-114`.

```python
ALLAUTH_USER_CODE_FORMAT = {"length": 6, "numeric": True, "dashed": False}  # settings.py:185: every code
confirm_email_rl = "1/10s/key"  # allauth app_settings.py:279: one new verification code per 10 s per address
confirmed = (
    EmailAddress.objects.filter(email__iexact=email, verified=True).select_related("user").first()
)  # shop/admin.py:631
```

- allauth's default code is 8 letters from an alphabet of 20 (2.6 × 10^10). The setting makes every code one of
  10^6: email verification, log-in codes by email and SMS, phone confirmation.
- Log-in by code stays at 9 guesses an hour per account (3 requests × 3 tries), within ASVS 2.2.1. Email
  verification of an unconfirmed account has no hourly or daily cap: each password log-in of that account mints a new
  code with 3 tries (the API's `LoginSerializer.validate` returns a fresh `verification_token`; the website's
  verification stage does the same), limited only by `confirm_email`, one code per 10 s per address.
- 6 codes a minute × 3 tries = 1,080 guesses an hour per address, from one client address (24 API requests a minute,
  under the `dj_rest_auth` throttle of 30). That is about 2.6 % on the first day and even odds in about four weeks;
  with 8 letters it was centuries.

**Scenario:** a school buys by phone, and its address `accounts@school.example` has no ExamLeaf account. An attacker
registers that address with a password of their own and loops: API log-in → `verification_token` → three guesses. The
school's mailbox gets a code every 10 seconds (or none once the address is suppressed after complaints; the codes
are still minted). When a guess lands the address is "confirmed". From then on staff orders for that address are
attached to the attacker's account (the order page shows the school's delivery address and phone; a paid digital
product opens its course there, `grant_for_order` uses `order.user_id`), and cash on delivery and teacher requests
treat the address as verified.

**Fix:**
- Cap new verification codes per address per day, one setting: `ACCOUNT_RATE_LIMITS["confirm_email"] =
  "1/10s/key,10/d/key"` (allauth accepts `d`): 30 guesses a day per address instead of 25,920. The six-box code
  widget (`static/js/account.js`) stays as it is.
- If longer emailed codes are wanted later, set `ACCOUNT_EMAIL_VERIFICATION_BY_CODE_FORMAT` and
  `ACCOUNT_LOGIN_BY_CODE_FORMAT` apart from the SMS one (`ACCOUNT_PHONE_VERIFICATION_CODE_FORMAT`, which also makes
  the phone log-in codes); the widget keeps digits only, so it would need to accept letters.
- In the staff order form, show which account the order will be attached to (email, created) before saving.

**Status (2026-10-08):** fixed — the three tries per code are said outright (`ACCOUNT_*_MAX_ATTEMPTS = 3`); email
confirmation codes are limited to 5 an hour and 10 a day per address (`email_code_hour`, `email_code_day`, spent in
`AccountAdapter.send_confirmation_mail` before allauth keeps the code: over them a 429 and no code). allauth keeps one
history per action and kind of key, so the suggested `"1/10s/key,10/d/key"` would have let every code through (checked:
six codes 11 s apart all passed); each second window is therefore an action of its own. Log-in codes: `30/h/ip,3/h/key`;
the log-in code page has no "send a new code" (allauth 65.19 answers it with a server error for an unknown number, a way
to tell registered ones). Tries are also counted per code in the cache under allauth's lock (`code_try`: 3 per code, 60
an hour per client address; `accounts.forms.spend_try`) on the website's three code forms (ACCOUNT_FORMS) and the API's
verify-email and phone/confirm, so tries sent together cannot pass three (I7). allauth's 429 reaches the API as a JSON
429 with its reason (`api.views.exception_handler`). Open: the staff order form naming the account an order will attach
to (admin template work). Tests: `accounts/test_codes.py` (the 6th and the 11th code refused; the 4th try refused even
when the session lags).

### M2. One daily SMS budget for everything, which anyone can spend: then no code reaches anybody until midnight

**Where:** `ops/sms.py:66-85`; `examleaf/settings.py:170-171, 186-191`; `accounts/forms.py:116-124, 257-260`;
`accounts/views.py:296-303, 336-350`; allauth `account/internal/flows/phone_verification.py:46-52, 136-138`,
`account/internal/flows/login_by_code.py:173-177`.

```python
if (
    SmsLog.objects.filter(created__gte=midnight, status=SmsLog.Status.SENT).count() >= settings.SMS_DAILY_CAP
):  # sms.py:74
    log.status = SmsLog.Status.CAPPED
```

`SMS_DAILY_CAP` (500) counts every kind together, with no limit per number, per account or per purpose. What can fill
it:
- Parental-consent SMS from sign-ups (M3, `PARENTAL_CONSENT_MODE=verified`): the API's sign-up has no Turnstile, 30 a
  minute per client address, each one texting any Indian number: 500 in about 17 minutes.
- Phone confirmation from throwaway accounts (an email confirmed on any catch-all domain): each account may change
  its number 3 times an hour (`change_phone` 3/h/user), each change with 2 resends, to any Indian mobile number,
  limited per number (one a minute) and per client address (10 an hour) only.
- Log-in codes to registered numbers: 3 requests an hour per number, plus 2 resends each on the website: 9 SMS an
  hour to one person, all day.

**Scenario:** at 09:00 a script spends the day's 500. Until midnight "Log in with a code" by SMS, adding a mobile
number, the parent's consent link by SMS and order SMS all fail silently: `send_sms` records CAPPED and logs an
error, while the page says the code has gone. Students who log in by phone are locked out for the day. The same paths
let one number receive dozens of codes an hour (harassment, complaints to MSG91 about the DLT sender). The cost stays
capped (a few hundred rupees a day); the damage is availability.

**Fix:**
- Per recipient: in `send_sms`, refuse once the number's `phone_hash` has a few SMS today (e.g. 5); the hash is
  already in `SmsLog`. One number can then be neither bombed nor used to drain the budget.
- Per purpose: reserve most of the cap for `otp` (e.g. 70 %) so that consent links and order SMS cannot starve log-in
  codes; report to Sentry at 50 % and 80 %.
- Per account and day: `change_phone` "3/h/user,6/d/user", `verify_phone` "…,20/d/ip".
- Close the anonymous path (M3) and put a bot check or app attestation on the API's phone code.
- When a cap stops an SMS, say so on the page and offer the email code.

**Status (2026-10-08):** fixed — `ops.sms.queue_sms` writes the SmsLog row first (status "queued"; the row now names the
account) and refuses (status "capped", logged) past 5 SMS an hour or 10 a day to one number, 20 a day to one account, or
the purpose's share of `SMS_DAILY_CAP` since midnight (codes 70 %, order updates 30 %, parents' links 10 %);
`SMS_DAILY_CAP` stays the last line in the task. `queue_sms` returns whether the SMS went: allauth's SMS codes raise
`TooManyCodes` before the code is kept (429 "Too many messages have gone to this number…", JSON in the API), the parent
link's resend says "The link was not sent", and the API's phone code says "If this number is on an account, we have
texted it a code." only when nothing was refused. Anonymous code requests are capped per client address for the website,
the API and allauth.headless alike (`request_login_code` `30/h/ip`: allauth's form serves all three); the anonymous
consent path is closed by M3. Accepted, as decided: past 10 codes in a day a registered number gets a 429 where an
unknown one does not. Tests: `ops/test_sms_limits.py`.

### M3. Parental-consent links: an anonymous sign-up makes ExamLeaf email or text any address or number, with attacker-written text

**Where:** `accounts/forms.py:257-260`; `accounts/views.py:296-313, 316-331, 336-350`; `api/auth.py:115-122,
133-145`; `ops/tasks.py:29-45`; `templates/parent_consent.html:18`.

```python
if user.consent_pending:  # accounts/forms.py:257: at sign-up, before the student's own email is confirmed
    send_parent_link(user)
queue_sms(
    "parent_consent", user.parent_contact, {"var1": user.full_name.split()[0][:30], "var2": token}
)  # views.py:302
f"{user.full_name} has registered at ExamLeaf, for the free solutions of the ExamLeaf sample papers, and gave "  # :307
self.form.fields.pop("turnstile", None)  # api/auth.py:117: the app's sign-up has no bot check
```

- With `PARENTAL_CONSENT_MODE=verified` (needed by May 2027) every under-18 sign-up sends the link at once, before
  the student's email is confirmed, to whatever number or address the form names.
- `POST /api/v1/auth/registration/` needs only a new email address per request (free with a catch-all domain): 30 a
  minute per client address; nothing limits messages per recipient. A confirmed account can also resend every 10
  minutes, each time to a new contact (`parent_consent_resend`).
- The email carries the attacker's `full_name` (120 characters) from ExamLeaf's domain, and the new HTML part makes
  any web address in it a link (`urlize`, `ops/tasks.py:41`). The SMS carries a 30-character word under ExamLeaf's
  DLT sender.
- Whoever gets the link sees the student's name and email address (`parent_consent.html:18`) and can press "I agree",
  which is recorded as verified consent.

**Scenario:** a script signs up "students" whose `full_name` is "Your parcel is held: pay ₹49 at examleaf-help.in",
with `parent_contact` set to a list of victims' addresses or numbers. Each victim gets a genuine ExamLeaf email (SPF
and DKIM pass) or SMS. Complaints raise the SES complaint rate (SES may pause sending around 0.5 %, which also stops
verification and reset emails) and spend the SMS budget (M2). A mistyped parent number sends a child's name and email
address to a stranger.

**Fix:**
- Send the parent's link only once the student's email is confirmed (a receiver on allauth's `email_confirmed`
  signal), so each link costs a real inbox.
- Limit links per recipient (e.g. 3 a day per number or address; `ratelimit.consume(..., key=contact)`) and per
  account.
- Put no free text in the messages ("A student has registered at ExamLeaf and named you as parent or guardian …");
  show the name on the consent page only, and mask the student's email there.
- Keep a bot check on the API's sign-up while `verified` is on (Turnstile's widget runs in a WebView; or Play
  Integrity / App Attest).

**Status (2026-10-08):** fixed — the link goes once the student has confirmed their own address (allauth's
`email_confirmed`; `user_signed_up` when Google confirmed it), never from an anonymous sign-up on the website, the API
or allauth.headless; afterwards only from My account or `me/parent-consent/` (one each 10 minutes per account, and now
at most 3 a day to one address or number from all accounts together). The email and the SMS are fixed text; the
student's name appears only when `accounts.views.shown_name` allows it (letters of any script with their marks, single
spaces, a hyphen inside a word, a dot ending a word, at most 60 characters), otherwise "a student": no web address can
pass (a dot must end its word). Open: the consent page still shows the student's whole email address (template; the
parent uses it to recognise the account). Tests with hostile names and a hostile sign-up through the app:
`accounts/test_parent_link.py`.

### M4. Offer limits are checked when an order is made, against placed orders only: pending orders each keep the offer

**Where:** `shop/models.py:551-562`; `shop/cart.py:164`; `shop/services.py:298, 307-321`.

```python
# ponytail: checked when the order is made, not again under a lock when it is placed (as coupons are): a few
# orders paid at the same moment may pass a limit; an automatic offer is ours to give, so that is acceptable
used = Order.objects.counted().filter(discount_lines__offer=self)  # shop/models.py:554-556: placed orders only
claim_coupon(order)  # shop/services.py:311: mark_paid checks the coupon again, never the offers
```

- `apply_offers` (`cart.py:164`) drops an offer whose limit is reached while totals are computed: on the cart, at
  checkout and when the order is made. Nothing checks again at payment: `mark_paid` claims only the coupon, and
  `record_capture` cancels and refunds only for `OutOfStock` and `CouponUsedUp`.
- Pending orders do not count as uses, so the gap is not "a few orders paid at the same moment": it is every order
  made before the first one is paid. This is the first review's M1, fixed for coupons, now back for offers.
- Per-customer limits key on the account or the email; a guest uses a new email each time.

**Scenario:** "₹100 off your first order, one per customer". A customer checks out five times from the same cart
(10 checkouts per 10 minutes are allowed), gets five pending orders each ₹100 off, and pays all five.
"20 % off the first 100 orders": every order still pending when the 100th is paid keeps its 20 %.

**Fix:** claim offers like coupons. In `mark_paid`, lock the order's offers (`select_for_update`), run
`limit_problem` again and raise an `OfferUsedUp(ShopError)` that `record_capture` handles like `CouponUsedUp` (cancel
and refund) and the offline-payment action reports. Or count pending orders younger than `UNPAID_ORDERS_EXPIRE` as
uses. Give per-customer offers to signed-in accounts only.

**Status (2026-10-08):** fixed — `shop.services.claim_offers` locks the order's offers (`select_for_update`, in id
order) and runs `limit_problem` again in `mark_paid` (online and offline payments) and `place_cod`, after
`claim_coupon`; `OfferUsedUp(ShopError)` is cancelled and refunded by `record_capture` like `CouponUsedUp`, and refused
for cash on delivery and by the offline-payment action. The discount split is unchanged. Open: per-customer offers for
signed-in accounts only (a guest can still give a new address per order). Tests with two pending orders:
`shop/test_offer_limits.py`.

### M5. ffmpeg parses uploaded videos with every demuxer and protocol, in a worker that holds every production secret

**Where:** `learn/media.py:31-49, 52-60, 75-79`; `learn/models.py:96-101`; `docker-compose.yml:6-11, 106-109`;
`Dockerfile:11-15`; `accounts/roles.py:46`.

```python
info = json.loads(
    run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path])
)  # :45
args = ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-i", source, "-filter_complex", ";".join([split, *scale])]  # :60
```
```yaml
x-app: &app          # docker-compose.yml:6-10: web, worker, beat and media-worker all use it
  env_file: .env
media-worker:        # :106-108
  <<: *app
```

- The upload is checked by extension and size only (`FileExtensionValidator`, `max_upload`). ffprobe and ffmpeg pick
  the demuxer by content, so the file may be any format FFmpeg reads (HLS and concat playlists included: what they may
  read from disk is limited by FFmpeg's own extension checks, not by this code), and its bytes reach FFmpeg's
  decoders, a code base with a steady stream of memory-safety CVEs. The command itself cannot be injected (an argument
  list, no shell, a uuid file name): the content is the risk.
- The media worker gets the whole `.env`: SECRET_KEY, the database password, Razorpay keys and webhook secrets,
  MSG91, SES, both S3 keys and the Firebase Admin key, with network access to the database, Redis and the internet.
- Uploads come from CONTENT_EDITOR accounts (`roles.py:46`), and the videos usually come from outside creators.

**Scenario:** a crafted clip, delivered as a creator's file, hits an FFmpeg decoder bug when the media worker
processes it. Code runs as uid 1000 in the worker and reads the environment: it can sign Razorpay webhooks (orders
marked paid), forge sessions with SECRET_KEY, read every student's data from the database, and send SMS and email
as ExamLeaf.

**Fix:**
- Let FFmpeg open only what a clip is: `-protocol_whitelist file -format_whitelist mov,matroska` before `-i` on
  ffprobe and on both ffmpeg runs (covers mp4, mov, m4v, mkv and webm), and a `-codec_whitelist` of the decoders
  expected. Refuse what ffprobe reports outside the plan (e.g. longer than 30 minutes, above 4K, more than one video
  stream).
- Run FFmpeg where there are no secrets: a media worker with an env file of its own (the storage key, and a database
  user that can only update `learn_clip`), `read_only: true`, `cap_drop: [ALL]`,
  `security_opt: [no-new-privileges:true]`, memory and CPU limits, and no network but the bucket and the database.
- Rebuild the image when Debian ships FFmpeg fixes (I9: nothing watches the base image).

**Status (2026-10-08):** fixed — `learn/media.py`: the stored name must end in mp4, mov, m4v, webm or mkv and the object
be within `LEARN_MAX_UPLOAD_MB` before it is fetched; ffprobe (60-second limit) runs with `-protocol_whitelist file
-format_whitelist matroska,mov -codec_whitelist` (every FFmpeg decoder of H.264, HEVC, VP9, AV1, AAC, Opus and MP3) and
its report must show the mov or matroska demuxer and only those codecs, or the clip fails ("Not a video we take…")
before ffmpeg runs; both ffmpeg runs carry the same input options with `-nostdin`, `-hide_banner`, `-threads 2` and
their wall-clock timeout (no pipes are used, so `file` only). docker-compose.yml: `x-media-env` gives the media worker
the database, the queue, the bucket variables, `LEARN_*`, `LOG_LEVEL` and `SECRET_KEY` from `.env` and nothing else (no
`env_file`: no Razorpay, MSG91, SES, Google, Sentry or Firebase keys), with `cap_drop: [ALL]` and `no-new-privileges`.
Open: a database user limited to `learn_clip`, a read-only filesystem and egress limits for that container (deployment
work). The commands are tested with ffmpeg mocked (`learn/test_media.py`); `test_a_real_ffmpeg_run` runs them where
ffmpeg is installed.

---

## Low

### L1. The API's checkout accepts the staff-only payment method "offline"

**Where:** `api/shop.py:608-610`; `shop/services.py:160-182`; `shop/payments.py:42-46, 68`.

```python
payment_method = serializers.ChoiceField(choices=Order.Method.choices)  # api/shop.py:610: razorpay, cod and offline
payment = order.payments.filter(method=Order.Method.RAZORPAY, razorpay_payment_link_id=None).first()  # payments.py:68
```

- The website's form offers online payment and (when on) cash on delivery; the API lists every `Order.Method`, and
  `create_order` checks only the cash-on-delivery rules. `"offline"` makes an order with an OFFLINE payment.
- Paying it then fails with a 500 (`razorpay_order_id(None)` reads `None.razorpay_order_id`, payments.py:45), on the
  payment page and on `orders/<number>/payment/`. Staff see a customer's order "bank transfer or UPI to our account,
  awaiting payment".

**Scenario:** a customer makes such an order and emails support a made-up UTR. "Record a payment received offline"
asks only for a reference, so one hurried click ships the books (or opens the course).

**Fix:** `choices=[(m.value, m.label) for m in (Order.Method.RAZORPAY, Order.Method.COD)]`, and refuse any other
method in `create_order`.

**Status (2026-10-08):** fixed before this pass (redesign checkpoint ba0b9dd) — the API's `payment_method` lists
`CUSTOMER_METHOD_CHOICES` only and `create_order` refuses any other method; test in `shop/test_api.py`.

### L2. `?attr_<code>=`: a number that overflows answers 500, and every parameter costs a query

**Where:** `api/shop.py:202-211, 238-243`; `shop/models.py:363-374`.

```python
number = Decimal(value)                     # shop/models.py:369
return format(number.normalize(), "f")      # :374
for name, value in self.request.query_params.items():  # api/shop.py:240
```

- For an attribute of kind "number", `Decimal("1e999999999").normalize()` raises `decimal.Overflow` (checked on
  Python 3.14), which `attribute_match` does not catch (it catches `ValidationError`): an anonymous 500 and a Sentry
  event per request.
- `1e999999` passes and becomes a 1,000,000-character string, sent to PostgreSQL in an `UPPER(...) = UPPER(%s)`
  comparison.
- Each `attr_` parameter costs an `Attribute` query; Django allows 1,000 parameters, the anonymous throttle 200
  requests a minute.

The codes and values are only ever values in fixed lookups: no ORM injection.

**Fix:** in `normalise`, refuse exponents (`abs(number.adjusted()) > 12`) and catch `ArithmeticError`; take at most a
few `attr_` parameters (e.g. 5) and fetch their attributes in one query.

**Status (2026-10-08):** fixed — `Attribute.normalise` catches `ArithmeticError` and refuses exponents beyond ±12; the
API takes at most 5 `attr_` parameters (400 above) and fetches their attributes in one query. Test:
`shop/test_review_lows.py`.

### L3. "Email me when it is back": any address, no confirmation, no cap

**Where:** `shop/views.py:269-286`; `shop/tasks.py:152-163`; `templates/shop/email/back_in_stock.txt`.

```python
if not request.POST.get("website") and product.available < 1:  # shop/views.py:283
    StockAlert.objects.get_or_create(email=email.lower(), product=product)
```

- A visitor subscribes any address to any product out of stock (a honeypot field and 10 an hour per client address
  only). At the reprint every address on the list is emailed within the hour: one email per address and product, to
  people who never asked for it.

**Scenario:** a script with a few hundred client addresses subscribes thousands of strangers; the reprint sends
thousands of unwanted emails from ExamLeaf's domain, complaints follow, and SES may pause the account (verification
and reset emails included).

**Fix:** double opt-in (a confirmation link; unconfirmed alerts kept apart and expired), or alerts for signed-in
accounts only; Turnstile on the form; a cap per run.

**Status (2026-10-08):** fixed — alerts for signed-in accounts only, to their own address: the website asks a visitor to
log in (the product page has no email box any more), and `products/<slug>/stock-alert/` needs a signed-in user (401; an
address in the body is ignored). Tests: `shop/test_commerce.py`, `shop/test_api_contract.py`.

### L4. API log-ins skip the second factor: a password or an SMS code alone gives tokens for MFA-enabled accounts, staff included

**Where:** `api/auth.py:280-309, 319-337`; `examleaf/middleware.py:54-68`; `learn/services.py:28-29`;
`api/shop.py:54-55`.

- On the website allauth's MFA stage asks for the authenticator app or a passkey after a password or code log-in
  (`mfa/stages.py:28-39`). The API mints JWTs right after `authenticate()` or the SMS code, so a student who added a
  passkey (MFA on) and every member of staff can be logged in through the app with one factor. `StaffMFAMiddleware`
  sees session requests only.
- A staff JWT opens every course (`entitled_subjects`: staff → every subject) and the shop while `SHOP_OPEN` is off.
  No admin function is in the API, which keeps this Low.

**Scenario:** a SIM swap of a SALES member's number (phone code) or a phished password → API tokens as that member →
every paid course, free.

**Fix:** refuse API log-ins (password and phone code) for `is_staff` users; for accounts with MFA, answer "log in on
the website" or add the second step (allauth's headless API has one).

**Status (2026-10-08):** fixed — `api.auth.one_step_allowed`: the API's password log-in, verify-email and phone/confirm
give no tokens to staff or to an account with any authenticator (`is_mfa_enabled`): 403 pointing to `/_allauth/app/v1/`,
which asks for the second step, then `auth/exchange/`. Test: `accounts/test_review_lows.py`.

### L5. Staff may log in with a passkey alone, and user verification is only "preferred"

**Where:** `examleaf/settings.py:206-215`; `accounts/forms.py:127-133`; allauth
`mfa/webauthn/internal/auth.py:143-148`, `mfa/stages.py:35-36`; fido2 `server.py:361`.

```python
request_options, state = server.authenticate_begin(
    ..., user_verification=UserVerificationRequirement.PREFERRED
)  # auth.py:145-148
if did_use_passwordless_login(request):
    return False  # mfa/stages.py:35-36: no second step after a passkey log-in
```

- A passkey log-in is the whole log-in, and the settings say staff may use one instead of the authenticator app.
  fido2 enforces the user-verified flag only when the state asks for REQUIRED (`server.py:361`); registration asks for
  it (passwordless), log-in does not, and allauth requests no `credProtect`. Whether a key will then sign without its
  PIN depends on the authenticator and the platform.

**Scenario:** a staff member's lost or borrowed security key → a hostile client asks for an assertion without user
verification → admin access with neither the password nor the key's PIN, on authenticators that allow it.

**Fix:** for staff, refuse passwordless log-ins (a `user_logged_in` receiver: `is_staff` and
`did_use_passwordless_login(request)` → log out with a message), so staff use the password and then TOTP or a
passkey; or require user verification for every passkey log-in.

**Status (2026-10-08):** fixed — `AccountAdapter.pre_login` refuses a passkey-only log-in for staff and drops its record
(so the password log-in that follows is not taken for one): staff log in with the password, then the authenticator app
or a passkey. User verification stays "preferred" for students (allauth fixes it). Test: `accounts/test_review_lows.py`.

### L6. Adding a log-in mobile number, or taking one over, notifies nobody

**Where:** `accounts/adapter.py:46-50`.

```python
others.update(login_phone="", login_phone_verified=False, sms_updates=False)  # the previous holder loses it silently
self.set_phone(user, phone, True)
```

- allauth emails on password, email, passkey and authenticator changes; it has no phone notice and the adapter adds
  none. A confirmed number is a complete way to log in (an SMS code).
- When a recycled number is confirmed by its new owner, the old account loses phone log-in and order SMS without a
  word.

**Scenario:** someone with a student's unlocked phone a few minutes after the student logged in (reauthentication
accepts a password typed in the last 5 minutes) adds their own number and from then on logs in by SMS code; the
student is never told.

**Fix:** in `set_phone_verified`, email the account (`send_notification_mail`, a `phone_changed` template with the
masked number) and the account that lost the number.

**Status (2026-10-08):** fixed — `set_phone_verified` emails the account a number was added to and the account that lost
it (last four digits only), and not again at each log-in by SMS code. Test: `accounts/test_review_lows.py`.

### L7. LEARN_CODE_SECRET is optional; without it book codes are hashed with a key printed in the source

**Where:** `learn/models.py:203-206`; `examleaf/settings.py:529-531`; `learn/management/commands/make_book_codes.py:22-30`.

```python
key = (settings.LEARN_CODE_SECRET or "examleaf-book-codes").encode()  # learn/models.py:205
```

- Nothing stops a production start or `make_book_codes` without the secret. Codes have 60 bits; with N unredeemed
  codes, a copy of the database (a backup, a dump) yields one in about 2^60 / N HMACs: with 100,000 codes, about 10^13,
  under an hour on one GPU.
- The key cannot be added later: printed codes would stop matching.

**Fix:** refuse to start with `DEBUG` off and an empty `LEARN_CODE_SECRET` (as for `SECRET_KEY`), and make
`make_book_codes` refuse without it.

**Status (2026-10-08):** fixed — system check `learn.E001`: with `DEBUG` off an empty `LEARN_CODE_SECRET` is an error,
so `migrate`, and with it the web container, stops; `make_book_codes` refuses without the key; CI's image check sets
one. The key in the source remains for development and tests only. Tests: `learn/test_review_lows.py`,
`learn/test_access.py`.

### L8. Unbounded rows per user in the course API; the reminder task loads every device

**Where:** `api/learn.py:280-289, 331-339, 494-516`; `learn/tasks.py:78-80, 93-95`.

- Card reviews (`flash-cards/<id>/review/`, only the user throttle of 600 a minute), quiz answers (600 an hour) and
  devices (600 a minute, no cap per user) are inserted without limit. `revise_again` reads all of a user's answers on
  every call, and Download my data loads them all.
- Junk device tokens stay: only `UnregisteredError` and `SenderIdMismatchError` delete a row. `send_reminders` loads
  every device with reminders on into memory and works through them 500 at a time, under Celery's 300 s limit.

**Scenario:** one account posts 800,000 made-up device tokens a day; the 18:00 reminder runs out of time before it
reaches real students, every day, and the tables grow by millions of rows.

**Fix:** keep the newest few devices per user (e.g. 5); delete tokens FCM rejects as invalid; a daily cap per user on
card reviews and quiz answers (as `check_can_save` does for attempts); send reminders in batches by id.

**Status (2026-10-08):** fixed — 5 devices per account (the newest kept), 1,000 quiz answers and 1,000 card reviews a
day per account (429 above); the reminder reads devices 500 at a time by id and deletes the tokens Firebase refuses as
invalid (`InvalidArgumentError`) as well as the unregistered ones. Tests: `learn/test_review_lows.py`.

### L9. Anonymous requests that write: a two-week session per phone-code request, and a day-long cache entry per query string

**Where:** `api/auth.py:47-54`; `shop/views.py:335-341`.

```python
request.session = SessionStore()   # api/auth.py:50
send()
request.session.save()             # saved with Django's default expiry: two weeks
@cache_page(86400)                 # shop/views.py:335, the PIN lookup
```

- `email_code` saves a database session for every `auth/phone/code/` call, for any number, registered or not, kept
  two weeks although the code dies in 3 minutes (sign-ups and unconfirmed log-ins too).
- `pin_lookup` caches by full URL: `/shop/pin/781001/?x=1` … `?x=n` each store a copy for a day in the 256 MB LRU
  cache that also holds the rate-limit counters. The first review's L8, fixed for the API, is back for this view; the
  view has no rate limit.

**Fix:** `request.session.set_expiry(900)` in `email_code`; cache the PIN answer by the PIN alone (drop the query
string first) or only with `Cache-Control` (the lookup is a primary-key read).

**Status (2026-10-08):** fixed — the API's code sessions expire after 15 minutes (`email_code`); the PIN lookup is
cached by browsers only (`Cache-Control: public, max-age=86400`), not in the server's cache. Test:
`shop/test_review_lows.py`.

### L10. Account deletion and Download my data miss some of the new records

**Where:** `shop/models.py:963-978, 1259-1272`; `shop/tasks.py:130, 152-163`; `shop/services.py:528-541`;
`ops/models.py:60-82`; `accounts/models.py:225-263`; `accounts/views.py:154-185`.

- Stock alerts under the account's address survive the deletion (`forget_shop_details` leaves them): the "back in
  stock" email still goes to the deleted student, and the row stays up to a year.
- Staff notes on the user's orders, with their history (`OrderNote` keeps `HistoricalRecords`), stay as long as the
  orders (eight years); the export does not show them.
- The SMS log keeps the number's keyed hash and last four digits for 90 days, findable by the whole number; it is
  neither exported nor deleted. Failed phone log-ins (axes rows keyed by the number) are not deleted with the
  account (the daily `axes_reset` clears them).

**Fix:** delete `StockAlert.objects.filter(email__iexact=old_email)` in `DeletionRequest.complete()`; export the
user's SMS log rows (kind, day, status) and say whether the address is suppressed; export the order notes, or keep
in them only what the tax record needs.

**Status (2026-10-08):** fixed — the deletion removes the account's SMS log rows and the failed log-ins under its mobile
number (stock alerts were already removed); Download my data adds the SMS log (kind, status, last four digits, time),
the address's suppression and each order's staff notes. The notes' history stays with the order for the tax period.
Test: `accounts/test_review_lows.py`.

### L11. Bookkeeping around the new payment types and the course

**Where:** `shop/services.py:185-196, 402-417, 420-442, 452-469`.

```python
captured = order.payments.filter(method=Order.Method.RAZORPAY, status=Payment.Status.CAPTURED)  # services.py:406
```

- An order paid offline and then cancelled becomes "cancelled", its course closes and its copies go back, but no
  Refund or credit note is made (`start_refund` ignores OFFLINE payments) although its invoice exists: the money owed
  back is recorded nowhere, and GSTR-1 shows an invoice without its credit note.
- Any processed refund, partial included, marks the payment refunded and, with no other captured payment, the order
  refunded, and closes the course (`refund_processed` → `revoke_course`): ₹50 back for a damaged book in a book and
  course bundle ends the course.
- `create_staff_order` does not check `consent_pending`: staff can sell to, and open a course for, an under-18 account
  whose parent has not confirmed, which the website and the API refuse.

**Fix:** record offline refunds (a Refund with a bank reference, marked processed by staff, with its credit note);
close the course only when what was paid for its lines is refunded; refuse staff orders for a `consent_pending` user.

**Status (2026-10-08):** fixed in part — `create_staff_order` refuses a student whose parent has not confirmed (test:
`shop/test_review_lows.py`); a part refund already left the course open (`refunded_in_full`, before this pass). Open:
refunds of offline payments (a Refund with a bank reference, marked processed by staff, with its credit note) need a new
admin flow, more than a contained change; until then such a refund is paid by bank transfer and its credit note made by
hand.

### L12. Secrets travel further than they need to

**Where:** `learn/tasks.py:49-59`; `DEPLOYMENT.md:578-580`; `docker-compose.yml:10`; django-pictures
`pictures/models.py:177, 192`; `examleaf/settings.py:471-474`.

```python
storage = (self.storage.deconstruct(),)  # pictures/models.py:177: sent to Celery with every picture
_public_s3 = {**_s3}  # settings.py:471: the public storage defaults to the private bucket's key
```

- FCM: DEPLOYMENT.md asks for the Firebase Admin SDK key ("Service accounts → Generate new private key"), which
  administers the whole Firebase project (its users, databases, storage, and pushes to every install of the app), and
  puts it in the `.env` that every container reads, the FFmpeg worker included (M5). Only beat's `send_reminders`
  needs it.
- `S3Storage.deconstruct()` returns its constructor arguments, `secret_key` included (checked with django-storages
  1.14.6), and django-pictures puts that in every picture task message in Redis. Unless `PUBLIC_S3_*` is set, the key
  is the private bucket's: invoices, answer sheets, quotations and course videos.

**Fix:** a service account with only the "Firebase Cloud Messaging API Admin" role, in beat's environment alone; a
key limited to the public bucket in `PUBLIC_S3_*`, and a public storage class whose `deconstruct()` names only the
class and reads its options from settings, so no key goes into the queue.

**Status (2026-10-08):** fixed in part — `examleaf.storage.PublicS3Storage` keeps the key out of the picture tasks (its
`deconstruct()` names only the class and it reads its options from settings; test: `shop/test_review_lows.py`); the
media worker no longer receives the Firebase key or any other (M5). `send_reminders` runs on the worker (beat only
queues it), so the key stays in `.env` for web, worker and beat. Founder: a Firebase service account with the "Firebase
Cloud Messaging API Admin" role only, and a key limited to the public bucket in `PUBLIC_S3_*` (DEPLOYMENT.md section
15).

---

## Informational

- **I1. Turnstile details.** `turnstile_passed` sends no `remoteip` and does not compare the answer's `hostname` or
  `action` (`accounts/forms.py:39-46`). allauth spends the per-address and per-number limits in `clean_email` and
  `clean_phone` (allauth `account/forms.py:742-770`) before the Turnstile field, added last, is validated: a request
  that never solved the challenge still uses up a victim's 3 code requests an hour. The API's sign-up and phone code,
  phone changes and resends, the parent-link resend, stock alerts and password resets have no bot check (M2, M3, L3).
  Validate the Turnstile field first (put it first in `fields`), and send `remoteip` and check `hostname`.

  **Status (2026-10-08):** fixed in part — Turnstile is validated first (`TurnstileMixin` puts it first; the templates
  place the widget themselves) and a code request that failed it spends none of allauth's per-address or per-number
  limit; Cloudflare is sent `remoteip`. Open: checking the answer's `hostname` and `action` (the app's WebView host is
  not settled yet) and a bot check on the API's sign-up, phone code and password reset. Test:
  `accounts/test_review_lows.py`.
- **I2. Email subjects from form input.** `email_staff(f"Quotation asked for: {quote.school}", ...)`
  (`shop/views.py:302`): a school name with a line break (possible in a hand-made POST) makes Django refuse the header,
  `send_email` retries five times (`ops/tasks.py:15`) and drops it, so staff never hear of that request (it is still
  in the admin). Collapse whitespace in subjects built from input (`" ".join(text.split())`).

  **Status (2026-10-08):** fixed — `ops.tasks.queue_email` collapses the whitespace of every subject. Test:
  `shop/test_review_lows.py`.
- **I3. CSP for the bucket.** With the private bucket on AWS, `connect-src` and `media-src` allow
  `https://*.s3.ap-south-1.amazonaws.com`, any bucket in the region, on every page (`examleaf/settings.py:537-544`),
  for the staff player's sake. Name the bucket's own host, and add these sources only on `/learn/preview/`, as
  `allow_razorpay` does for the payment page.

  **Status (2026-10-08):** fixed — the bucket origins left the global CSP; `learn.uploads.allow_storage` adds the
  storage's own origin, taken from its signed link (on AWS `https://<bucket>.s3.amazonaws.com`, which the old
  `*.s3.<region>.amazonaws.com` pattern did not even match), to `connect-src`, `media-src` and `img-src` of the staff
  player and to `connect-src` of the clip pages only. Test: `learn/test_uploads.py`.
- **I4. Category import skips model validation.** `CategoryResource` has no `clean_model_instances`
  (`shop/admin.py:155-165`, unlike `ProductResource` at `:147`): a slug with a space or a slash is saved, then
  `reverse("shop:category", ...)` fails (500) on the shop page and in the API. ADMIN only. Set
  `clean_model_instances = True`.

  **Status (2026-10-08):** fixed — `CategoryResource.validate_instance` runs the model's checks on each row (the tree's
  own fields excepted: they are set when the row is placed). Test: `shop/test_review_lows.py`.
- **I5. Revise-again outlives access.** `revise_again` (`learn/plan.py:112-126`, `api/learn.py:405-422`) returns the
  quiz items and flash cards a student got wrong with no entitlement or publication check: after the year of access,
  or after a revision goes back to draft, they are still served. Filter on `entitled_subjects` and published
  revisions.

  **Status (2026-10-08):** fixed — `revise_again` lists only items of published revisions in subjects the student may
  open (the free first chapter's cards too). Test: `learn/test_review_lows.py`.
- **I6. One person can give goods away.** SALES alone can make a staff order with a discount up to the whole
  subtotal (`shop/forms.py:108-114`, `shop/cart.py:151-152`) and record it paid offline with any reference
  (`shop/services.py:356-371`); SUPPORT can give any account every course for good (`accounts/roles.py:74`);
  CONTENT_EDITOR can change prices (`roles.py:42`). The admin log records who did it. Consider a cap on staff
  discounts, ADMIN approval of offline payments above a value and of orders at ₹0, and a weekly list of discounted
  staff orders and of grants.

  **Status (2026-10-08):** open — business controls rather than code (a cap on staff discounts, ADMIN approval of
  offline payments above a value and of orders at ₹0, a weekly list of discounted staff orders and of grants): for the
  founder to decide; the admin log keeps who did what meanwhile.
- **I7. Counters without locks.** A code's failed tries live in the session and the API saves it after each try
  (`api/auth.py:293-307`): concurrent guesses on one token can pass 3 by about the number of workers. `send_sms` counts
  the day's SMS, then sends (`ops/sms.py:74-79`): the cap can be passed by the number of concurrent senders. Both stay
  small with 2 or 3 workers.

  **Status (2026-10-08):** fixed for the website and the API — tries are counted per code in the cache under allauth's
  lock (`code_try`, M1), so tries sent together get three in all (gunicorn's threads made this matter more); the SMS
  cap's count-then-send gap is closed by writing the row before counting (M2). Open: allauth.headless's code
  confirmations still count in the session only; routing them to inputs with `CodeTriesMixin`, as `examleaf/urls.py`
  does for the code request, is a follow-up for the API pass.
- **I8. hls.js checked.** `static/learn/hls.min.js` (619,656 bytes, SHA-256 base64
  `3kn1owhPc8nj5OKZnW54n46lr/ASDSlWMey5vxSAs+o=`) is the npm release hls.js 1.7.3 `dist/hls.min.js` (619,692 bytes,
  `oS5+4c1kpp3NsxQVfkXa/LpwW/sLFEC3k1yyZdN0Qj4=` per jsDelivr) without its last line,
  `//# sourceMappingURL=hls.min.js.map`; adding that line back gives the published hash exactly. Write the hash and
  the source next to the licence so the next update can be checked the same way.

  **Status (2026-10-08):** fixed — the vendored file's size and SHA-256 and the release's are written next to the
  licence (`static/learn/hls.js-LICENSE.txt`).
- **I9. Supply chain and image.** firebase-admin brings grpcio, google-cloud-firestore, google-cloud-storage and
  protobuf (`requirements.txt:138-158`) for one HTTPS call; FCM's HTTP v1 needs only google-auth and httpx, both
  installed. FFmpeg, Pango and the fonts come from Debian at build time, unpinned, on the moving `python:3.14-slim` tag,
  and Dependabot watches pip and Actions only: add `package-ecosystem: docker` and rebuild on FFmpeg security updates.
  `.dockerignore` has no pattern for a service-account JSON, which DEPLOYMENT.md allows as "the path of the file
  inside the container": a key left in `examleaf-web/` would be baked into the image by `COPY . .`. The new libraries
  (django-treebeard 7.0.2, django-pictures 1.8.0, pwned-passwords-django 5.2.0, firebase-admin 7.7.0) and their
  dependencies are pinned; pip-audit still does not fail CI (first review, L10).

  **Status (2026-10-08):** fixed in part — Dependabot watches the Dockerfile's base image (`package-ecosystem: docker`)
  and `.dockerignore` leaves out every `.json` file. Open: firebase-admin replaced by google-auth and httpx, pinned
  Debian packages, and a blocking pip-audit (the first review's L10 decision stands: reported, not blocking).
- **I10. Clip links are bearer links.** `SIGNER.sign_object(clip.pk)` (`learn/views.py:33`) names the clip, not the
  student: whoever is given the link can watch for 10 minutes (segments for 20 minutes plus the clip's length). With
  `LEARN_PUBLIC_VIDEO=1` the links never expire (`examleaf/settings.py:525`; the folder is the clip's id and 32 random
  bits). Acceptable at the course's price; if sharing becomes a problem, put the user's id in the token and count
  links per user.

  **Status (2026-10-08):** open — accepted at the course's price, as the review says: links name the clip, not the
  student; if sharing becomes a problem, put the user's id in the token and count links per user.

---

## Checked and sound (phases 5 and 6)

- **Phone log-in.** Numbers are normalised to `+91…` before every lookup and limit; a verified number is unique
  (`uniq_verified_login_phone`) and moves only once its own code is confirmed; changing it needs reauthentication.
  Unknown numbers get the same answer and no SMS (`send_unknown_account_sms` is allauth's empty one). Codes are
  compared in constant time (`compare_user_code`, refusing an empty expected code), three tries, three minutes; the
  API's throwaway session is never set as a cookie and is deleted after use; on the website allauth's MFA stage still
  follows a code log-in. Failed password log-ins by phone are limited per number (adapter, axes username callable).
- **Passkeys and Google.** The relying party is SITE_URL's host; origins are checked (insecure ones only with DEBUG);
  the credential must belong to the user its handle names; adding a passkey emails the account (allauth). Google:
  no log-in or linking by email (`SOCIALACCOUNT_EMAIL_AUTHENTICATION` off), PKCE, POST to start, Google's
  `email_verified` decides, an address with an account must log in and connect, and the student-details and consent
  form applies.
- **Parental consent token.** Django's signer, HMAC cut to 96 bits, salted with the contact (a corrected contact voids
  older links), seven days, POST with CSRF.
- **Turnstile** refuses an empty or failed token; its script and frame are allowed only when the keys are set.
- **SMS and email plumbing.** Provider refusals are logged, not retried; the SMS log keeps a keyed hash and four
  digits; Sentry scrubs `otp`, `var1`, `var2`, `authkey` and Indian numbers; the JSON logs leave out Celery task
  arguments. Anymail's URLs exist only with `ANYMAIL_WEBHOOK_SECRET`, every ESP view checks basic auth in constant
  time, SES subscriptions are confirmed through boto3 (`ConfirmSubscription` in the topic's region, no URL fetched from
  the message), and only hard bounces, invalid addresses and complaints suppress.
- **Payment Links and offline payments.** `payment_link.paid` goes through the signature, freshness and
  de-duplication of every webhook; amount and currency are compared in `record_capture`; a link paid after checkout
  (or the reverse) is refunded as a second payment; links expire before their staff order (15 against 16 days);
  `reconcile` finds a paid link whose webhook was lost. Offline payments: row lock, only pending unplaced non-COD
  orders, `shop.add_payment`, coupon and stock claimed as online.
- **Prices.** Staff discount and shipping cannot be negative; offers and coupons never take more than what is left of
  the lines (percentages capped at 100); `split` shares each discount to the paisa without exceeding a line;
  invoices and credit notes use the shares kept on the lines.
- **Digital products.** No cash on delivery, an account required, one per cart, the course opened in the payment's
  transaction (so a failure is retried with the webhook), an order of digital products only delivered at once, the
  course closed on cancellation.
- **Course access.** Clips, quiz, flash cards and progress check the entitlement or the free preview on the server;
  quiz answers are never in the list and are checked on the server; draft revisions are hidden; plan, settings,
  entitlements and devices are per user, and a device is deleted only from its own user. Book codes: 60 bits, only a
  keyed hash stored, redeemed under a row lock, 5 tries an hour per user and per address, logged without the code.
- **HLS.** Token salted for its purpose with an expiry checked per file; file names must match a fixed pattern (no
  path traversal); private storage with presigned 10-minute segment links; the staff player needs `learn.view_clip`;
  hls.js runs without workers (no `blob:` scripts).
- **ffmpeg invocation.** Argument lists, no shell; the stored name is a uuid; output in a fresh temporary folder
  with fixed names; a timeout per run and a Celery time limit.
- **Files.** Product pictures are validated by Pillow (2 MB, 4096 px) and kept in the public bucket; invoices, credit
  notes, quotations, answer sheets and videos in the private one; `/shop/media/` sends only `products/` and `og/`
  and refuses `..`; the quotation download checks view permission; quotation PDFs use the static-only WeasyPrint
  fetcher; Open Graph images are drawn from staff data.
- **Output.** Markdown only for staff-written text (raw HTML off; markdown-it refuses `javascript:` links); JSON-LD
  escapes `<`, `>` and `&`; reviews, notes, quotation fields and attribute values are autoescaped; the new HTML email
  part escapes each paragraph (`urlize(autoescape=True)`) and its template escapes codes and links; the new admin
  columns use `format_html`.
- **Attribute filters.** Codes and values are only values in fixed lookups: no ORM injection (L2 is about errors).
- **Import and export.** Imports need the `import_` permissions (ADMIN) and are logged; product imports run model
  validation; exports are logged.
- **CSP and front end.** No inline script was added (the JSON block of the passkey page is not executable); Razorpay
  is allowed on the payment page only; the service worker handles same-origin GETs only, never pages, and caches
  static files with hashed names; the PIN autofill writes `.value` only; the admin customer page shows each section
  only with its view permission.
- **Data rights.** Download my data has the log-in number, passkeys (no keys), Google data, reviews, quotation
  requests and stock alerts by address, and the course data (device ids left out). Deletion removes passkeys, Google
  accounts, the course data and devices, reviews with their history, addresses and the cart, at the end of the grace
  period only. Reviews come only from accounts with a delivered order of the product, one each, approved by staff and
  shown without names. GSTINs are checked with python-stdnum, and the PIN code's state on every address form and in
  the API.
- **Infrastructure.** Queue and cache are separate Redis instances; media tasks run only on the media queue; the
  vendored hls.js matches its release (I8); CI reads only.

## Suggested order

1. H1 now: Caddy buffering and timeouts, gunicorn back to 30 s with threads, clip uploads off the site's workers.
2. M1: one rate-limit setting.
3. M2 and M3 before `SMS_BACKEND=msg91` and `PARENTAL_CONSENT_MODE=verified` go live.
4. M4 before the first offer with a usage limit.
5. M5 before the first video from outside.
6. L1, L2 and L7 (a few lines each), then the other Low items.
