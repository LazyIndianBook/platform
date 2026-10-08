# Changelog

What changed in the ExamLeaf web platform, newest first, by phase. Phases 0 to 3b are the repository's commits (all of
8 October 2026); phase 4 is the QA pass, the working tree on top of phase 3b until it is committed. Details of each
feature are in README.md; the numbers of the tests are those of `pytest` at the end of the phase.

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
