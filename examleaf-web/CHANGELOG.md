# Changelog

What changed in the ExamLeaf web platform, newest first, by phase. Phases 0 to 3b are the repository's commits (all of
8 October 2026); phase 4 is the QA pass, the working tree on top of phase 3b until it is committed. Details of each
feature are in README.md; the numbers of the tests are those of `pytest` at the end of the phase.

## Phase 5 B — storage, media, shop and web platform (21 tests more)

Work package B of `docs/examleaf-phase5-plan.md`; its Status section has a line per item.

- **Two buckets** (Cloudflare R2; DEPLOYMENT.md sections 15 and 17): a private one for invoices, credit notes,
  quotations and answer sheets, reached by links signed for 5 minutes, and a public one for product pictures on
  `PUBLIC_MEDIA_DOMAIN`, cached a year as immutable; keys `S3_*` of their own (`PUBLIC_S3_*` for a private bucket on
  AWS S3 Mumbai); the boto3 checksum variables R2 needs; the CSP allows the media domain. Without buckets (development,
  tests, one server) both stay in `media/`, and `/shop/media/` serves only the public folders.
- **Pictures:** covers and product pictures get AVIF and WebP sizes on the worker (django-pictures 1.8.0, covers
  cropped 2:3) and pages use `<picture>`; their widths and heights are stored, so no page opens the files. The four
  static covers have committed AVIF and WebP copies at 320 and 480 px (`manage.py build_covers`).
- **Search engines and link previews:** canonical link and Open Graph tags on every page (`templates/_head_meta.html`,
  included by base.html), a default preview picture and one per product (cover and title, made on save by the worker),
  JSON-LD for products (Product and Book: price, stock, ISBN/GTIN, shipping, returns; the rating only from approved
  reviews), breadcrumbs and the publisher. No FAQ markup (retired by Google).
- **Web app:** manifest, maskable icons drawn with Pillow, a service worker that keeps only the static files and a
  standalone offline page (never a page, so nothing of an account outlives a log-out), registered from the new
  `static/js/site.js` (`templates/_body_end.html`); CSP `manifest-src` and `worker-src 'self'`.
- **PIN codes:** `manage.py import_pincodes <csv>` loads India Post's directory (data.gov.in); the address forms fill in
  the district and state, and the website, the checkout and the API refuse a state that does not match the PIN code.
- **Shipping:** a courier list on shipments; the tracking link is filled in when staff leave it empty (Delhivery, Blue
  Dart, Ekart, 17TRACK for India Post and the rest).
- **Reviews** from buyers whose order was delivered, one per book, approved in the admin, shown as "Verified buyer";
  honeypot and rate limit; deleted with the account.
- **School and bulk orders:** a public form (`/shop/school-orders/`, GSTIN checked with python-stdnum, Turnstile when
  on), staff emailed, a quotation PDF valid 15 days from the admin, kept in the private bucket. The coupon form takes
  Turnstile too.
- **Stock:** "Email me when it is back" on products out of stock (one email, hourly check), a daily email of the books
  running low to the SALES role (`SHOP_LOW_STOCK`).
- **GST:** `manage.py export_gstr1 --from --to` writes the B2C, HSN summary and credit-note CSVs for the accountant.
- **Order SMS** go out from the shop's notifications through `ops.sms.send_order_sms` (phase 5 A).
- **Supply chain:** Dependabot (pip and GitHub Actions, weekly); DEPLOYMENT.md notes Jazzband's wind-down.
- Upgrading: `MEDIA_ENDPOINT_URL` is gone (`S3_ENDPOINT_URL`), and `MEDIA_BUCKET` now needs `PUBLIC_MEDIA_BUCKET` and
  `PUBLIC_MEDIA_DOMAIN`; product picture URLs change with the buckets (API.md); SALES needs permissions for reviews and
  school orders in `accounts/roles.py` (not yet given).

## Phase 5 A — sign-in and communications (32 tests more)

Work package A of `docs/examleaf-phase5-plan.md`; its Status section has a line per item.

- **Phone log-in.** A student adds a mobile number on My account (never at sign-up) and confirms it with an SMS code;
  then it logs in with the password or a code by SMS ("Log in with a code", email or number). Numbers are taken as
  people type them ("98640 12345") and kept as +91…; one account per number. Every code, emailed or texted, is now 6
  digits (was `ABCD-EFGH`). Failed password log-ins by phone are limited per number (allauth keyed them all on one
  empty key). An empty "send me a code" form and a second code to the same number within a minute no longer end in a
  server error. Phone log-in exists only where SMS are sent (`SMS_BACKEND=msg91`, or development).
- **Passkeys** for everyone (My account → Passkeys, "Use a passkey" on the log-in page; Passwordless ticked by
  default), one relying party for the host of `SITE_URL`; staff may use a passkey instead of the authenticator app.
- **Google sign-in** when `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are set: a new student fills in the student
  details after Google (one form mixin with the sign-up form); PKCE; `form-action` allows Google only then.
- **App API:** `POST auth/phone/code/` and `auth/phone/confirm/` (API.md): log-in by SMS code, the same JWT pair.
- **SMS gateway** (`ops/sms.py`): one Celery task, `console` or `msg91` (OTP and Flow APIs), retries on network
  errors, an SMS log without whole numbers (Admin → Operations), at most `SMS_DAILY_CAP` a day counted in the
  database. Order SMS (placed, shipped, delivered) for students who ask for them on My account, through
  `ops.sms.send_order_sms(order, kind)`.
- **Parental consent by SMS** (`verified` mode): a parent's Indian mobile number gets the link by SMS; links are now
  short (`/c/<token>/`, email too: links sent before this release stop working) and record how they were confirmed.
- **Email:** Amazon SES as the documented production backend, bounce and complaint webhooks (`/anymail/…`, only with
  `ANYMAIL_WEBHOOK_SECRET`), an email suppression list that stops sends to bad addresses (staff delete a row to send
  again).
- **Cloudflare Turnstile** on sign-up and code requests when its keys are set (fails open, logged).
- Data export and account deletion include the new data (log-in number, passkeys, Google accounts); Sentry filters SMS
  variables; DEPLOYMENT.md sections 15 and 16, RUNBOOK.md "SMS", "Phone numbers and passkeys", "Email bounces and
  complaints".

## Phase 4 security — shop (16 tests more, in `shop/test_security.py`)

The shop's findings of SECURITY_REVIEW.md (8 October 2026); each finding there has its status line.

- **Order links (M2).** Each order has an unguessable token, and every email about it links to `/orders/t/<token>/`:
  the order read only, its invoice and credit notes, and a cancel button while it is pending or paid. "Find your
  order" (website and API) no longer opens the order: for a guest order it emails that link to the order's address,
  and it answers "If an order matches, we have emailed you a link." either way. 10 lookups an hour per client address,
  per email address and per order number; refused while they cannot be counted. API: `POST orders/lookup/` no longer
  returns the order.
- **Test and live mode (M3).** Payments and orders record the mode of their Razorpay keys. Payments, webhooks and
  refunds of the other mode change nothing; invoice and credit-note series follow the order's mode; once live, test
  orders are marked TEST and cannot be packed or shipped. One webhook secret per mode (`RAZORPAY_WEBHOOK_SECRET_TEST`,
  `RAZORPAY_WEBHOOK_SECRET`). `SHOP_OPEN=0` leaves buying to staff during Razorpay's review ("Shop opens soon").
- **Webhook data (M6).** Only the payment's id, order, status, method, amount, currency, error and time are kept (the
  stored payloads are stripped by a migration), not shown in the admin, and cleared after 180 days.
- **Cash on delivery (M8).** Only for accounts with a confirmed email address, orders up to `SHOP_COD_MAX_VALUE`
  (₹1,500) and two on their way per account. Checkout and place order: 10 per 10 minutes per client address.
- **Retention (M10).** Orders never paid or placed lose the customer's details 30 days after they were cancelled; the
  yearly purge of invoiced orders past eight years is in RUNBOOK.md.
- **Refunds (L1, L3).** A retried refund first looks for the one Razorpay already made; a second payment captured for
  a paid order is recorded and refunded by itself, and a cancellation still refunds the first one.
- **Coupons (L4).** One answer for every code that cannot be used; 10 tries an hour per client address (website) and
  per user (API, `API_THROTTLE_COUPON`).
- **Redis (L8).** The cache has a Redis of its own (`redis-cache`: 256 MB, least used keys evicted); the queue's never
  evicts. The shop's limits refuse while the cache cannot be read; Razorpay's webhooks go on.
- **Hardening (I4, I6, M5).** Products and addresses sort only by the fields named; invoice PDFs fetch only static files
  and data: URLs; the orders export needs `export_order` (ADMIN) and is logged.
- Migrations `shop` 0005 to 0008. Open: canonical cache keys for the public API lists (`api/views.py`).

## Phase 4 security — accounts, API and operations (23 tests more, 227 in all)

The security review's other findings (SECURITY_REVIEW.md, each with its status line), one test or more each in
`accounts/test_security.py`, `api/test_security.py` and `ops/test_security.py`.

### Staff and roles

- **Two-factor authentication for staff** (H2): `allauth.mfa`, an authenticator app with ten recovery codes; staff
  without one are sent to set it up before anything else opens; the admin's log-in is allauth's (its per-account limit,
  the code); staff sessions end 8 hours after the log-in. RUNBOOK.md "Staff accounts".
- **ADMIN can no longer** edit periodic tasks, task results, groups, permissions or second factors, nor make anyone
  superuser or change a superuser; only superusers give roles (I7).
- **Admin exports** need an `export_…` permission (ADMIN only), leave out dates of birth and parents' contacts, are
  written to the admin log, and escape a leading `=` (M5, L7).

### Log-ins, passwords and the API

- The API's log-in counts failures per account like the website (5 in 5 minutes); allauth now sees the client's address
  behind Caddy instead of Caddy's (M7).
- Password reset emails: 5 a minute per address, API and website together (L5); five wrong passwords in an hour on the
  API's password checks revoke the user's refresh tokens and answer 429 (L6).
- Passwords: 10 characters at least, none found in data breaches (Pwned Passwords); reset links last an hour (L11).
- At most 20 new attempts of a paper a day; notes 2,000 characters (L12). Boards and subjects sort by id and name only
  (I4); the public API's cache keys ignore unknown query parameters (L8).
- `JWT_SIGNING_KEY`: the app's tokens can have their own key (I5).

### Operations and privacy

- `/health/` and `/health/web/` answer only the uptime monitor (Caddy, `X-Health-Token`) and keep their results 20 s;
  `/api/v1/health/` is gone (H1).
- Sentry gets no stack-frame variables and no email text (M4).
- Verifiable parental consent behind `PARENTAL_CONSENT_MODE=verified`: a link emailed to the parent, the account
  read-only until they agree, how and when recorded (M9); to switch before May 2027 (DEPLOYMENT.md section 14).
- Expired sessions are deleted daily; uploaded backups can be encrypted with age, with a 30-day bucket rule; the
  privacy draft says how logs are really kept (M10).
- The site refuses to start with development settings on a server (I1); a Permissions-Policy header (I6); QR images
  only for published papers, cached a day (I3).
- CI: read-only permissions, a pip-audit job (not blocking yet); test and lint tools in `requirements-dev.txt`, not in
  the image (L10).

## Phase 4: QA pass (60 tests more, 188 in all)

Every flow of the site was walked on a development server (visitor, cart, log-in, both checkouts, cancellation, guest
lookup, registration under 18, data export, deletion, teacher access, every admin page, every API endpoint and error),
the failures below were reproduced first, and each fix has a test that fails without it.

### Fixed: money and orders

- **Coupon limits** ("one per customer", "at most N uses") were checked only when an order was made, so several open
  orders could each take the last use. They are checked again, under a lock on the coupon, when an order is paid or
  placed (`services.claim_coupon`): the first wins; a cash-on-delivery order that loses goes back to the cart with a
  message, an online payment that loses is refunded and the customer told why. The payment page and the API stop
  before taking money for a coupon that is gone.
- **A payment Razorpay took but the site never heard about** (the customer never came back and the webhook was lost) was
  left charged without an order when the order expired after two days. Before cancelling, the daily clean-up now asks
  Razorpay (`payments.reconcile`); a Razorpay that cannot be asked leaves the order for the next run;
  `manage.py reconcile_payments` does the same by hand.
- The clean-up could cancel an order that was paid in the same moment: the order is checked again under its lock.
- After a payment that could not be used (books sold out, coupon gone) the thank-you page said "placed" and emptied the
  cart; it now says the order could not be completed and is being refunded, and the cart is kept (website and API).
- Refunds made in the Razorpay dashboard were ignored; they are recorded from their webhook (the order, the customer's
  email and the credit note follow).
- Cash-on-delivery review pages that nobody finished stayed pending for ever; they are cancelled after two days, like
  online orders.
- Invoices: no invoice of the real series is numbered while a `SELLER_*` setting still holds a `[placeholder]` (the numbers
  cannot be reissued); the "Amount" column is what is payable after the discount; "MRP-inclusive" became "prices include
  tax"; the Docker image carries Noto fonts, so a name or address in Assamese prints (it would have been empty boxes).
- The admin's revenue is net of refunds (a refused parcel refunded less the shipping brought in nothing).
- Admin: saving a product page that was opened before a sale put the old copy count back; pictures over 2 MB are
  refused with a reason.

### Fixed: availability

- **Redis down: nobody could log in, register or reset a password** (allauth's rate-limit lock treated django-redis's
  fail-soft `add` as "locked" and answered 429; the old test only opened pages). `examleaf.cache.SoftRedisCache`
  fixes it.
- A broker that accepts connections and never answers hung the request for ever; Celery now gives up after about 4
  seconds and the email is sent from the web process. If the email provider is down as well, the failure is logged and
  the page goes on (it was a 500). The old test of the broker fallback never reached the broker: fixed (`broker` fixture).
- `/health/` held a gunicorn worker for 3 seconds on every call (the Celery ping waited out its timeout): `limit=1`.
- A `%00` in an address gave a 500 on PostgreSQL (`/s/AB%00C/` among them): 404.
- Double clicks ended in a 500 for the second request: "Add to cart" (a unique row made twice), "Delete my account" and
  "Ask for teacher access" (one waiting request or profile per user).

### Fixed: privacy

- A sign-up with an address that already has an account answered faster than one with a new address (no password
  hashing): the same work is done, so the timing does not tell.
- Account deletion left the user's email in the admin history of their attempts and the name and PIN code in that of
  their addresses.
- Download my data now also holds the roles, the cart, each order's payments and status timeline.
- The delete page says that orders and invoices stay (tax law); the notes of an attempt are limited to 2000 characters.
- Pages seen by a signed-in user were kept by the browser: after Log out on a shared computer (a cyber café) the Back
  button showed the account, record and orders; they now carry `Cache-Control: no-store`.

### Fixed: front end and copy

- The header is one row at every width: on a phone the name, the cart and a Menu button (CSS only, a hidden checkbox:
  no JavaScript, the CSP is unchanged), instead of three lines; keyboard operable.
- Text colours that missed 4.5:1 (stock, saving, paid-status) darkened; the brand link has an accessible name.
- Every page has its own title and meta description; the private ones are `noindex`; `robots.txt`, a favicon and touch
  icon were added.
- Branded 400, 403, 403 for an expired form, 404, 429 and 500 pages (the 400 and 500 pages need no layout or database;
  the API answers JSON); the 429 of the guests' order lookup was plain text.
- "Log in" and "Register" everywhere (allauth said Sign In and Sign Up), emails greet from ExamLeaf instead of the
  host name, the words about registering follow `SOLUTIONS_REQUIRE_LOGIN`, the About page names the publisher and
  points to Contact, dispatch and delivery times are no longer promised outside the Shipping Policy (product page,
  emails), the empty home page no longer says `manage.py import_papers`.
- `[placeholders]` in the legal pages are marked yellow on the site, counted in the Pages list and on the admin index.

### Added

- Tests: error pages and metadata (`ops/test_errors.py`), the admin crawl (`ops/test_admin_pages.py`, every list, add,
  change, history and delete page), Redis half-open (`ops/test_resilience.py`), copy (`ops/test_copy.py`), orders and
  coupons at the same instant, stuck payments and the admin (`shop/test_robustness.py`: four of them run threads against
  PostgreSQL and are skipped on SQLite), export and sign-up (`accounts/test_export_and_signup.py`).
- Docs: environment variable reference in DEPLOYMENT.md, the shop in RUNBOOK.md (a stuck payment, refund disputes,
  reconciling settlements, a missing invoice, coupons and stock), API.md matched to the routes, this file.

## Phase 3b: shop on the API, credit notes, privacy of the shop

Shop REST endpoints (products, cart, addresses, orders, payment through Razorpay's mobile SDK, cancellation, invoice
and credit note PDFs, guests' lookup); credit notes (own number series, GST reversed per line); orders in Download my
data; Sentry scrubbing of secrets and personal data; the `SOLUTIONS_REQUIRE_LOGIN` switch (open or registered
solutions); webhook replay protection; a readiness check before gunicorn starts; the CI builds the Docker image; tests
isolated so that they pass in any order on SQLite and PostgreSQL. 128 tests.

## Phase 3: REST API v1

DRF with dj-rest-auth and JWT (short access token, rotated and blacklisted refresh token, ended by a password change),
sign-up and the email code on the website's own form and rules, drf-spectacular schema with Swagger UI and Redoc served
by the site, CORS for listed origins on `/api/` only, throttles counted in the cache, API.md.

## Phase 2: the shop

Catalogue and product pages; the cart (a guest's joins the account's at log-in); checkout with Indian address checks
and saved addresses; Razorpay payments and signed webhooks; cash on delivery; the order and payment state machines
with a customer timeline; stock under row locks; coupons; shipping rates by state; shipments with tracking; refunds
(also partial); GST invoices as PDFs (bill of supply while every book is exempt); order management in the admin (pack,
ship, deliver, cancel, refund, export); Refund and Shipping policy pages; SALES and SUPPORT roles.

## Phase 1: production

PostgreSQL, Redis cache and Celery with beat; Sentry and JSON logs with request IDs; roles and permissions; teacher
access requests and their verification; DPDP self-service (Download my data, Delete my account with seven days to
change one's mind, consent records); legal pages with history; the branded admin with its dashboard; the Docker and
Caddy stack; backups; CI; DEPLOYMENT.md and RUNBOOK.md.

## Phase 0: the site

Books, papers, questions and solutions imported from the Markdown of the four subjects (30 papers each); the QR code
of every paper opening its solutions; registration with parental consent under 18 and an emailed code; My record of
attempts; a Markdown renderer that keeps the maths for KaTeX and escapes everything else; a strict Content-Security-
Policy; private caching of the gated pages; failed log-ins only in the lock-out records. A first QA pass fixed an XSS in
the renderer and the consent logic. 33 tests.
