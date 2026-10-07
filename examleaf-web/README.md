# ExamLeaf web

The website behind the ExamLeaf Sample Papers books. The solutions are not printed in the books: every paper carries a
QR code that opens `/s/<CODE>/` (e.g. `/s/PHY-E01/`), where a registered student reads the full marking-scheme
solutions for free and can save the marks scored (or anyone reads them, with `SOLUTIONS_REQUIRE_LOGIN=0`: see "Open or
registered solutions"). Now: Class 12, Assam board (ASSEB), Physics, Chemistry,
Mathematics and Biology, 30 papers each (E01–E10 Easy, M01–M10 Medium, H01–H10 Hard).

Django 6.1 · Python 3.14 · server-rendered templates · one hand-written CSS file (`static/css/site.css`), no build step ·
KaTeX from jsDelivr for the `$…$` maths · no trackers, analytics or ads · PostgreSQL, Redis and Celery in production,
none of them needed in development.

Operations: [DEPLOYMENT.md](DEPLOYMENT.md) (first deployment on a VPS) and [RUNBOOK.md](RUNBOOK.md) (backups,
secrets, data requests, email failures).

## Set up and run (development)

```sh
cd examleaf-web
make install                              # .venv with the pinned requirements
cp .env.example .env                      # DEBUG=1, SQLite, console email, tasks inline; every variable is explained
make migrate                              # migrate + bootstrap_roles (the role groups)
.venv/bin/python manage.py import_papers --all
.venv/bin/python manage.py createsuperuser
make run                                  # http://localhost:8000 · admin at /admin/
```

`make help` lists the other tasks (tests, lint, formatting, the docker-compose stack, backups). In development the
verification codes and every other email are printed in the runserver console, and the debug toolbar is on.

### Background tasks (Celery)

Emails (verification codes, password resets, account notices) are sent by a Celery task, and celery beat runs the daily
jobs: purge account deletions whose seven days are over (03:00), forget failed log-ins (03:30), delete task results
older than a week (04:00). Without `CELERY_BROKER_URL`, and always in tests, tasks run inline in the web process
(`CELERY_TASK_ALWAYS_EAGER`), so development needs no broker and no worker. To try the real thing locally:

```sh
brew install redis && brew services start redis   # or any Redis 7
echo CELERY_BROKER_URL=redis://localhost:6379/0 >> .env
make worker                               # threads pool: Celery's prefork pool fails on macOS
make beat                                 # the schedule is in settings.py and editable in the admin (Periodic tasks)
```

If the broker cannot be reached, an email is sent synchronously instead, so that a sign-up never fails because Redis
is down.

## Importing the papers

```sh
.venv/bin/python manage.py import_papers --root "/Users/chinmoybhuyan/Desktop/Personal/Book/Class 12" --subject physics
.venv/bin/python manage.py import_papers --all          # --root defaults to the folder above examleaf-web (BOOK_ROOT)
```

The command creates the board ASSEB (Assam), Class 12, the subject and its book, and reads
`production/<subject>/papers_md/<CODE>-<T><NN>.md` and `-solutions.md` with `parse_paper`, `parse_solutions` and
`split_marks` from `production/build/book.py` (imported by path, not copied). Question labels are derived from the
paper's structure the way the solutions file names them: `9`, `1(a)`, `9 OR`, `B9(a)`/`Z3 OR` (Biology's Botany and
Zoology parts), and the plain numbered sections of Mathematics papers 08–10. A lettered line under a numbered
question that is not a group heading is a sub-part of that question (Chemistry table questions). Chapter and textbook
section tags come from the work orders (`production/<subject>/orders/ch*.md`).

It reports, per subject, papers, questions, solutions matched, tags, created/updated/unchanged records, and lists every
solution label it could not match and every question without a solution (it exits with an error if there are any).
Re-running it changes only what changed in the Markdown, so the edit history stays meaningful.
Current result: 30 papers per subject; Physics 1650, Chemistry 1260, Mathematics 1383, Biology 1590 questions,
every one with its solution and tags; 0 unmatched.

## QR codes

- `/qr/<CODE>.png` — the QR image for a paper; it encodes `SITE_URL + /s/<CODE>/`.
- `.venv/bin/python manage.py export_qr --out qr/` — all papers as `<CODE>.png` and `<CODE>.svg` (37 mm square in the SVG).

Set `SITE_URL` to the real domain before exporting codes for print: `export_qr` refuses to write codes for `localhost`
or a plain-http address (a printed book cannot be corrected), unless you pass `--force` for a test run.
`/s/phy-e01/` redirects to `/s/PHY-E01/`.

## Pages

| URL | Page |
|---|---|
| `/` | the four books |
| `/books/<slug>/` | a book's 30 papers by tier (`physics-2027`, `chemistry-2027`, `mathematics-2027`, `biology-2027`) |
| `/s/<CODE>/` | QR landing page: register / log in (returning here via `next`) for visitors, the solutions for students; with `SOLUTIONS_REQUIRE_LOGIN=0` the solutions for everyone (saving marks still needs an account) |
| `/account/signup/` (`/account/register/` redirects), `/account/login/`, `/account/logout/`, `/account/email/`, `/account/password/change/`, `/account/password/reset/` | django-allauth |
| `/account/` | My account: details, change email or password, My record and My orders, the address book, teacher access, Download my data, Delete my account |
| `/account/addresses/add/`, `/account/addresses/<id>/` | the address book: add or change a saved address (Delete is a button on My account) |
| `/account/record/` | My record: attempts, filter by subject and tier, average per tier; add from a solutions page, edit from here |
| `/account/teacher/` | request teacher access (school, district, subject); staff verify it in the admin |
| `/account/data/` | Download my data (a JSON file; asks for the password again) |
| `/account/delete/` | Delete my account (seven days to change one's mind; `/account/delete/cancel/` keeps it) |
| `/privacy/`, `/terms/`, `/refunds/`, `/shipping/`, `/contact/` | legal pages, edited in the admin (Pages) |
| `/shop/`, `/shop/<slug>/` | the books on sale; a book's page (price, stock, what's inside, a sample paper, add to cart) |
| `/cart/`, `/checkout/` | cart (copies, coupon); checkout (log in or a guest email, address, payment choice) |
| `/checkout/<number>/pay/` | review and pay: Razorpay Checkout, or "place order" for cash on delivery; `…/done/` thanks |
| `/account/orders/`, `/account/orders/<number>/` | My orders; an order's timeline, tracking, invoice and credit notes (`…/invoice/`, `…/credit-notes/<id>/`) and Cancel (also for guests who looked it up) |
| `/orders/lookup/` | Find your order: number and email, for guests |
| `/shop/webhooks/razorpay/` | Razorpay's webhooks (signed) |
| `/about/`, `/sitemap.xml`, `/admin/` | |
| `/health/`, `/health/web/` | health checks (JSON with `Accept: application/json`); see Production |

Registration asks for full name, email, password, class, board, district (optional) and date of birth, and a consent
box (agreement to the privacy notice, linked beside it) that everyone must tick; its time is stored in `consent_at` and
the event in a `ConsentRecord`. Under 18 it also requires a parent's or guardian's name and phone or email, and the
parent ticks the box; for adults no parent data is asked, validated or kept. The email address is confirmed with a code
typed on the same page, then the student lands back on the paper whose QR code was scanned. The consent is
self-declared: nothing verifies that the person who ticked it is the parent (see RUNBOOK.md).

## Open or registered solutions

`SOLUTIONS_REQUIRE_LOGIN` (environment, default `1`) decides who reads the solutions behind the QR codes, on the website
(`/s/<CODE>/`) and in the API (`papers/<code>/solutions/`):

- `1` (registered, today's choice): visitors get the register / log-in page and come back to the paper. Every reader is
  an account, which means a parent's consent for each under-18 student, personal data kept for each, and a sign-up
  step between a stuck student and the answer.
- `0` (open): everyone reads the solutions; accounts stay optional, for saving marks (the record form appears only for
  a signed-in student, visitors see a log-in link instead), orders and the app. The page is then the same for every
  visitor and is sent `Cache-Control: public, max-age=300`; for a signed-in student it stays private (the form carries
  a CSRF token).

The research (`docs/examleaf-platform-plan.md`, "Open solutions") recommends open: a registration wall weakens the
feedback that makes practice work, most for weak students; it makes ExamLeaf the keeper of many children's data under
the DPDP Act, with identity-checked parental consent, from May 2027; and in rural Assam many students use a parent's
phone. The cost of open is that the solutions can be copied without an account (no evidence that this hurts sales). The
QR codes point at `/s/<CODE>/` either way, so the switch needs no reprint.

## Roles and permissions

Roles are Django groups; `accounts/roles.py` lists each group's model permissions and is the only place to change them.
Migration `accounts.0004_roles` creates the groups, and `manage.py bootstrap_roles` (idempotent; `make migrate`, the
docker web container and DEPLOYMENT.md run it after every `migrate`) sets every group to exactly its permissions,
including those of apps migrated later.

| Group | Who | Permissions now |
|---|---|---|
| STUDENT | every registration (added at sign-up) | none: uses the site, not the admin |
| TEACHER | teachers whose `TeacherProfile` staff verified | none yet |
| CONTENT_EDITOR | prepares papers and pages | view/add/change books, papers, questions, solutions; view boards, classes, subjects; view/change legal pages |
| SALES | runs the shop | view books; view/add/change products (and their images and bundle items), coupons, shipping rates, shipments; view/change orders (the pack, ship, deliver and cancel actions); view/add refunds (the refund action); view order items, payments, invoices |
| SUPPORT | helps students | view users, email addresses, attempts, consent records, deletion requests; view/change teacher profiles (verifies teachers); view orders, order items, payments, shipments, refunds, invoices, products, addresses |
| ADMIN | runs the site | every permission |

`user.is_student`, `is_teacher`, `is_editor`, `is_sales`, `is_support`, `is_admin` (ADMIN or superuser) and
`user.has_role(name)` read the groups. In the admin, Users has actions "Give role …" and "Take away role …" (only for
those who may change groups); giving CONTENT_EDITOR, SALES, SUPPORT or ADMIN also sets `is_staff`, and taking away the
last of them clears it. Teacher profiles have "Verify" (adds TEACHER, records who and when) and "Revoke".

## Personal data (DPDP Act)

- **Consent records:** `ConsentRecord` (event given/withdrawn, purpose, privacy-policy version, by a parent or not, time,
  HMAC of the address keyed with `SECRET_KEY`). Sign-up records one; asking for deletion records a withdrawal and
  cancelling it a new consent. Read-only in the admin, exportable as CSV.
- **Download my data:** `/account/data/` returns the profile, email addresses, teacher profile, attempts, answer sheets,
  consent records, deletion requests, saved addresses and orders (items, address copy, shipments, refunds, and the
  invoice and credit notes by number: the PDFs stay on the order pages) as JSON, after allauth's re-authentication
  (password, if none was entered in the last five minutes). The API's `me/export/` gives the same file.
- **Delete my account:** a `DeletionRequest` due seven days later (`accounts.views.request_deletion` and
  `keep_account`, used by the website and the API alike); the student gets an email, can log in and cancel
  until then; the daily purge (`accounts.tasks.purge_due_deletions`) anonymises the user row (name, email, phone,
  date of birth, district, parent data, notes cleared; answer-sheet photos, email addresses, teacher profile and
  failed log-ins deleted; consent records kept as proof without the address hash; admin log entries renamed;
  password unusable, so every session ends) and emails a confirmation to the old address. The marks stay as
  anonymous statistics.
- **Changing the email address:** allauth's `ACCOUNT_CHANGE_EMAIL` keeps one address; a new one replaces it only after
  the emailed code is confirmed, after re-authentication, and the old address is notified.
- **Logs:** no personal data in them by design (no logs of good log-ins; Celery's task arguments, which hold email
  texts, are left out of the JSON log lines). Sentry runs with `send_default_pii=False` (no cookies, users or client
  addresses) and `examleaf/sentry.py`'s `before_send`, which replaces, anywhere in an event (request body, headers,
  stack-frame variables, breadcrumbs, extra), passwords, codes, verification and JWT tokens, Razorpay signatures,
  emails, names, address and card- or phone-like fields, and card numbers, Indian mobile numbers and email addresses
  inside any text, with `[Filtered]`.

## Admin

django-admin-interface gives the admin ExamLeaf's colours and name (theme set by `ops/migrations/0001_admin_theme.py`;
the related-object pop-up stays a window because the CSP forbids frames). The index page
(`templates/admin/dashboard.html`, `admin.site.index_template`) shows registrations, registrations with a confirmed email
and saved attempts today and in the last 30 days, and the teacher requests and account deletions waiting.
Books, papers, questions, solutions and legal pages keep a full edit history (django-simple-history); users, attempts
and consent records export to CSV (django-import-export); periodic tasks and task results are under Celery.

## REST API

`/api/v1/`, for the app. The guide is [API.md](API.md): authentication from the app, token lifetimes, the endpoints
with curl examples, the error format, rate limits and the versioning policy. OpenAPI schema at `/api/schema/`, Swagger
UI at `/api/docs/`, Redoc at `/api/redoc/` (both served by the site, so the CSP stays strict).

- Code in `api/` (`auth.py` sign-up and log-in, `views.py`, `serializers.py`), settings in `examleaf/api_settings.py`
  (imported at the end of `settings.py`), URLs in `examleaf/api_urls.py`.
- JWT for the app (15-minute access, 30-day refresh, rotated, blacklisted on log-out, all ended by a password change,
  a reset or the deletion purge); the session for the site's own pages. Log-in, log-out, refresh and passwords are
  dj-rest-auth's; sign-up and the email code run on `accounts.forms.SignupForm` and allauth's code flow, so the parent
  and consent rules, the STUDENT role, the consent record and the emails are the website's.
- The catalogue is public, read-only and cached for 15 minutes; solutions (unless open, `SOLUTIONS_REQUIRE_LOGIN=0`)
  and attempts need a confirmed email address; Download my data and Delete my account reuse the website's functions
  and ask for the password.
- The shop (`api/shop.py`): products (public), and for a confirmed account the cart, saved addresses and orders:
  checkout, payment with Razorpay's mobile SDK (`orders/<number>/payment/` gives the SDK its options,
  `…/payment/confirm/` checks the signature), cancellation, the invoice and credit note PDFs; guests look an order up
  by number and email (its own rate limit). Everything runs through `shop.services`, `shop.cart` and `shop.payments`,
  and the Razorpay webhook stays `/shop/webhooks/razorpay/`.
- JSON only; page-number pagination (50, at most 200), filters, search and ordering; DRF's error format (a JSON 404
  for unknown `/api/` paths); throttles counted in the cache; CORS only for `CORS_ALLOWED_ORIGINS` and only on `/api/`;
  `X-Request-ID` as on the site. Beat deletes expired refresh tokens daily (`api.tasks.flush_expired_tokens`).

## Shop

The printed books, sold online across India: `shop/` (models; `services.py`, every flow; `payments.py`, Razorpay;
`cart.py`; `tasks.py`; `invoices.py`), templates in `templates/shop/`, static `shop/static/shop/checkout.js`.

### Set up

```sh
.venv/bin/python manage.py seed_shop --stock 50   # the 8 books, the Physics bundle, coupon WELCOME10, 3 shipping rates
```

- `seed_shop` is idempotent and never overwrites what the admin changed. Its prices are placeholders (Sample Papers
  ₹299, Solutions ₹249, bundle ₹499), ISBN blank, stock 0 without `--stock`. The Sample Papers and the bundle get the
  covers from `static/img/`; Solutions get none (those images are the Sample Papers' covers) until one is uploaded.
- Razorpay (`.env`, DEPLOYMENT.md "Shop: Razorpay"): `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` (test keys
  `rzp_test_…` until going live; the payment page then says "Test mode"), and `RAZORPAY_WEBHOOK_SECRET`, the secret of
  the webhook for `https://<domain>/shop/webhooks/razorpay/` with the events `payment.captured`, `payment.failed`,
  `order.paid`, `refund.processed`, `refund.failed`. Without keys the payment page says online payment is not set up;
  without the secret every webhook is refused. In development the return from Checkout is enough to complete an order;
  to try webhooks, expose the port (e.g. `ngrok http 8000`) and point a test-mode webhook at it.
- `SHOP_COD_ENABLED=1` offers cash on delivery.
- The seller on invoices: `SELLER_LEGAL_NAME`, `SELLER_ADDRESS`, `SELLER_GSTIN` (empty: "not registered"),
  `SELLER_STATE` (two letters: same state as the buyer = CGST + SGST, otherwise IGST), `SELLER_STATE_CODE`,
  `SELLER_EMAIL`, `SELLER_PHONE`.
- Invoice PDFs are made by WeasyPrint, which needs Pango: `brew install pango` on a Mac; the Dockerfile installs it
  with the DejaVu fonts (₹ sign).

### How it works

- **Money**: django-money, INR. `cart.totals` is the one place money is added up, from today's prices, on the cart
  page, at checkout and when the order is made; per-cent discounts round half up to the paisa; Razorpay gets paise.
- **Checkout**: log in (saved addresses) or a guest email; the address needs a state from the list, a 6-digit PIN
  code and a 10-digit Indian mobile number (django-localflavor, django-phonenumber-field). A pending order is made with
  a copy of the address and of each book's title, HSN, GST rate and price; the review-and-pay page shows the total.
- **Payment**: the Razorpay order is created server-side for the order's total (on the payment page; Razorpay
  unreachable: a friendly message, the order stays pending, "Try again"). Checkout's answer is posted back, its
  signature checked by the SDK, the payment fetched and, if only authorized, captured: the order is paid. The
  webhooks do the same, so a lost redirect still completes the order; repeats and either order of arrival change
  nothing (row locks and the state machines). Each webhook is recorded (`WebhookEvent`: Razorpay's event id and the
  hash of the signed body) and handled once, in one transaction with what it changes; a replay, even under another
  event id, is acknowledged and ignored, and events signed more than seven days ago are refused. A payment that cannot pay its order (cancelled meanwhile, sold out,
  wrong amount) is refunded automatically. Cash on delivery: "place order"; the courier's cash captures the payment
  at delivery.
- **Stock** is taken on payment (cash on delivery: when placed) under `select_for_update`, in product-id order, and
  checked first, so the last copy sells once; it goes back on cancellation. A bundle sells its books' copies.
- **States** (django-fsm-2, guarded transitions, `status` writable only through them): order pending → paid → packed
  → shipped → delivered, cancelled (pending or paid by the customer, packed by staff) and refunded; payment created →
  authorized → captured, failed or refunded. django-simple-history keeps every change: the customer's timeline.
- **Customers**: emails for confirmation, shipping (courier and tracking), delivery, cancellation and refund
  (`ops.tasks.queue_text_email`). Saved addresses in My account (add, change, delete, the default one). My orders:
  timeline, tracking, invoice and credit note downloads, Cancel while pending or paid
  (refund through Razorpay by a Celery task, retried for hours while Razorpay is down; a refusal shows as a failed
  refund in the admin). Guests find an order by number and email (10 tries per 10 minutes per address; Django's
  cache). The guest cart joins the account's cart at log-in.
- **Invoices**: numbered per financial year (`EL/2026-27/00001`, 16 characters at most), made by a task when the
  order is paid (cash on delivery: when shipped), retried on failure; the link appears once the PDF exists. A bill of
  supply while every item is 0 % (books, HSN 4901), with HSN, taxable value and CGST + SGST or IGST columns; prices
  include tax, the coupon is shared out over the lines.
- **Credit notes**: a refund of an invoiced order, in full or in part, gets a credit note (`CN/2026-27/00001`, its own
  series per financial year; `TC/…` with test keys), made by a task once Razorpay has refunded (or once the invoice
  is made, when the refund came first). It credits the books first, over the invoice's lines in proportion, then the
  shipping with what is left (a refused parcel refunded less the shipping credits the books only), reversing each
  line's GST. Linked next to the invoice in My orders, the API and the admin (order page, Credit notes).
- **Coupons**: per cent or rupees off, minimum order, dates, a total and a per-customer limit (by account and by
  email), any case. A use is a paid (or placed cash-on-delivery) order not cancelled or refunded.
- **Shipping rates**: a flat fee per group of states (one rate without states covers the rest), free from an order
  value (after the discount).
- **Admin**: products (images, bundle items), coupons, shipping rates; orders with filters and search (number,
  email, name, phone, tracking number), items, payments, shipments and refunds inline, actions Mark packed, Mark
  shipped (courier and tracking number per order), Mark delivered, Cancel, Refund (in full; shipped orders also by an
  amount, e.g. a refused parcel less shipping), export to CSV and XLSX; payments, refunds, invoices and credit notes
  read-only; the
  shop's numbers (orders and revenue today and in 30 days, orders to pack, parcels on the way) on the admin index.
- **Beat** (04:30, `shop.tasks.clean_up`): online orders unpaid for two days are cancelled (a late payment is
  refunded), refund, invoice and credit note tasks lost on the way (broker down) are queued again, guest carts idle
  for 30 days go, and so do webhook records older than seven days.
- **Security**: Razorpay's script, frames and API calls are allowed by the CSP on the payment page only, with
  `Cross-Origin-Opener-Policy: same-origin-allow-popups` for the banks' windows; the webhook is CSRF-exempt but signed
  and rate-limited; order pages are visible to their account, or to the browser session that placed or looked them
  up; invoices to those and to staff with `shop.view_invoice`. Product pictures are served by `/shop/media/…` only
  for files a product names (`media/` stays private).
- **Account deletion** deletes the saved addresses and the cart; orders and invoices stay (tax records) with their
  copy of the address, on the anonymised user.

## Tests

```sh
make test                                 # pytest: 128 tests, about 50 s (imports all four subjects once)
make cov                                  # the same with a coverage report (94 %)
make lint                                 # ruff, as in CI
make check                                # manage.py check and missing migrations
```

pytest with pytest-django runs the old Django `TestCase` classes and the newer pytest functions (factories in
`accounts/factories.py`, factory_boy); `manage.py test` still runs the `TestCase` classes. CI
(`.github/workflows/ci.yml` at the repository root) runs ruff, the migration check and the tests with coverage on
PostgreSQL 17, and builds the Docker image (job `docker-build`: `docker build`, then Django and WeasyPrint must load
in the image; nothing is pushed). Every test module passes on its own and in any order, on SQLite and PostgreSQL (no
test relies on ids or on rows made by another). They cover the import of the four subjects (30 papers each, every solution matched, re-import changes
nothing), the QR landing redirect, the gated solutions page and log-in returning to it (and never to another site), open
or registered solutions (both settings, website and API), the QR image and export guard, registration (parent details and consent under 18, none kept for adults; the STUDENT role
and the consent record), the Markdown renderer, query counts, the Content-Security-Policy and private caching of the
paper page, axes, recording attempts; the role groups' permissions, bootstrap_roles, role actions in the admin (and
that support staff cannot use them), the teacher request and verification; Download my data, deletion with its
grace period and cancellation, the purge task and what it erases, email change re-verification; the legal pages and
their history, the health endpoint and the readiness check, request IDs, the email fallback, Redis stopped (its
connections refused: pages, rate limits and throttles still answer, emails go out, the health checks fail), request
body limits, Sentry's scrubbing, the admin dashboard and the backup upload. The
shop's tests (`shop/test_*.py`, helpers in `shop/factories.py`; Razorpay's network calls are mocked and any real HTTP
call fails a test, while signatures are checked for real) cover the cart and coupon maths, checkout validation, a price
changed after the cart, stock and bundles, cash on delivery, the state machines, Checkout's signature, the webhooks'
signature, repeats, replays and order of arrival, the automatic refunds, refunds and their retries, the invoice and
the credit notes (real PDFs when Pango is installed; numbering, partial refunds, a refund before the invoice), guest
lookup and its rate limit, the cart merge at log-in, the address book, account deletion and Download my data with the
orders, the daily clean-up, SALES and SUPPORT in the admin, the order actions, the export, the dashboard and
`seed_shop`. `shop/test_api.py` covers the shop's REST endpoints: products, the cart, addresses, checkout, payment
through the SDK (and a bad signature), cancellation, invoice and credit note PDFs, other customers' orders (404),
cash on delivery, and the guests' lookup and its limit.

## Production

See [DEPLOYMENT.md](DEPLOYMENT.md): docker-compose.yml runs PostgreSQL 17, Redis 7, the site (gunicorn, WhiteNoise for
static files, non-root), the Celery worker and beat, and Caddy (https with automatic Let's Encrypt certificates, a
request ID per request, 10 MB body limit). Settings come from the environment (`.env.example` documents each one).
With `DEBUG=0` the session and CSRF cookies are `Secure`, `SECURE_SSL_REDIRECT` is on and HSTS is sent for a year;
`SECURE_HSTS_INCLUDE_SUBDOMAINS` and `SECURE_HSTS_PRELOAD` stay off until every subdomain is on https, which is why
`check --deploy` prints W005 and W021 (and nothing else with a real email backend). A Content-Security-Policy allows
scripts, styles and fonts only from the site and from the KaTeX folder on jsDelivr (`KATEX_CDN` in `settings.py`;
change it together with `templates/solutions.html`); in development it is report-only. django-axes keeps only failed
log-ins (address and browser, for the 15-minute lock-out), and beat clears them daily. `/health/` checks the database,
the cache, file storage and, when a broker is set, that a Celery worker answers; it returns 500 if one fails (for an
uptime monitor). `/health/web/` leaves Celery out: it is the web container's own health check, which the worker waits
for.
Logs are JSON lines on stdout with `request_id` (from Caddy's `X-Request-ID`, also sent back in the response).
Errors go to Sentry when `SENTRY_DSN` is set (scrubbed: see "Personal data"). Uploaded files (answer-sheet photos,
later) go to `media/`, never served publicly, or to a private bucket with `MEDIA_BUCKET`; the upload view must check
the file size when it is built.

Running without surprises:

- **Readiness**: the web container migrates, brings the roles up to date and then runs django-health-check's
  `manage.py health_check health_web --no-http` (database, cache, a write to the media volume) before gunicorn starts;
  if it fails the container stops and Docker restarts it.
- **Redis down**: the cache fails soft (django-redis with one-second timeouts and `IGNORE_EXCEPTIONS`: every call counts
  as a miss and is logged), so pages keep working while rate limits and throttles let requests through (sessions and
  axes are in the database); emails are sent from the web process when the broker cannot be reached (about a second
  late); invoice, credit note and refund tasks lost meanwhile are queued again by the daily clean-up; `/health/`
  reports the cache.
- **Request sizes**: Caddy refuses bodies over 10 MB; Django refuses more than 1 MB of form or JSON data
  (`DATA_UPLOAD_MAX_MEMORY_SIZE`; the API answers 413 in its JSON format) and more than 10 files in one request.
- **Database connections** persist between requests (`CONN_MAX_AGE`, default 60 s, health-checked before reuse) rather
  than in a pool: gunicorn's sync workers serve one request at a time, so a pool would hold as many connections.
- **Transactions** are explicit, with row locks (`shop/services.py`): checkout (the order and the address saved with
  it), payment, refunds, each webhook together with its record; `ATOMIC_REQUESTS` stays off.
- **Static files** are collected into the image at build time (hashed and compressed, WhiteNoise); the CI's
  `docker-build` job builds that image on every push.

## Data model

- `accounts.User` — email login; full name, phone (optional), class (10/12), board, district, date of birth,
  parent's name and contact (under 18 only), `consent_at`; created/modified; role properties from its groups.
- `accounts.TeacherProfile` (school, district, subject, verified, verification note, verified by/at),
  `accounts.ConsentRecord`, `accounts.DeletionRequest` (pending/cancelled/done, due seven days after the request).
- `content` — `Board` → `ClassLevel` → `Subject` (PHY/CHE/MAT/BIO) → `Book` → `Paper` (code, tier E/M/H, number,
  marks, time, `header_json` with the instruction lines and allotment tables, `is_published`) → `Question` (order,
  label, part and group headings, `text_md`, `options_json`, `marks_text`, `is_alternative`, `table_md`, tags) →
  `Solution` (`body_md`, the solution block as written: step table, Final answer, Also accepted, Diagram expected).
  The Markdown is stored and rendered at display time by the `markdown` template filter (markdown-it-py, cached).
  Book, Paper, Question and Solution keep a full edit history (django-simple-history).
- `practice.Attempt` — a student's marks, time and notes for a paper. `practice.AnswerSheetUpload` — photo, status
  (pending/processing/checked/failed) and `result_json`; model and admin only, no checking logic yet.
- `pages.Page` — the five legal pages (slug = URL, title, Markdown text, version, history). First drafts in
  `pages/drafts/*.md`, loaded by a migration; the words in square brackets (address, GSTIN, phone, email, Grievance
  Officer, delivery times, a refund rule to confirm) must be filled in before the shop opens.
- `shop` — `Product` (kind sample-papers/solutions/bundle, subject and book links, ISBN, pages, cover, MRP and price,
  GST rate, HSN, weight, stock, SEO), `ProductImage`, `BundleItem`, `Coupon`, `ShippingRate`, `Address`, `Cart` and
  `CartItem`, `Order` (EL-2026-000123, address copy, money, coupon, method, status machine, history), `OrderItem`
  (copies of title, HSN, GST rate and prices), `Payment` (Razorpay ids, signature, status machine, history, last
  webhook), `Refund`, `Shipment`, `Invoice` (number per financial year, PDF), `CreditNote` (a refund of an invoiced
  order: its own number series, PDF), `WebhookEvent` (webhooks handled: Razorpay's event id and the body's hash).
- `ops` — no models: Celery email task, admin dashboard, admin theme, `upload_backup` command.

## Planned extensions (not built)

- **Question banks**: questions already carry chapter and section tags; a bank is a filtered list of `Question`s
  (by subject, chapter tag, marks), and new bank-only questions can live in papers that are not published.
- **15-minute revision videos**: a `Video` model linked to a subject and chapter tag, shown on the book page and
  next to tagged questions.
- **AI checking of photographed answer sheets**: an upload view creating `AnswerSheetUpload`, a Celery task that
  reads the photo, compares each answer with the `Solution` step table and writes marks per step to `result_json`,
  and a result page; the status field already models the queue.
- **Class 10 and other boards**: new `Board`/`ClassLevel`/`Subject`/`Book` rows; the importer takes the board from
  its arguments once a second board exists.

## Phases to come

**Shop**: built (see Shop), with credit notes, its data in Download my data and its REST endpoints for the app.
Open: weight-based shipping.

## Libraries

| Library | Purpose |
|---|---|
| Django 6.1 | the framework: ORM, admin, auth, groups and permissions, forms, generic views, messages, sitemaps, mailers, security middleware, CSP |
| django-environ | settings from environment variables / `.env`: `DATABASE_URL`, `CACHE_URL`, lists and booleans |
| whitenoise | serves static files, hashed and compressed, in production |
| gunicorn | WSGI server for production |
| psycopg[binary] | PostgreSQL driver (production database) |
| django-allauth | registration, email login, email verification by code, email change with re-verification, re-authentication, password change and reset, built-in rate limits |
| django-axes (with django-ipware) | records failed logins and locks an account for 15 minutes after 10 failures from one address; its client-address logic also feeds the consent records |
| django-anymail | sends email through a transactional email provider in production (console in development) |
| celery | background tasks: emails, the daily purge, clean-ups |
| django-celery-beat | the periodic-task schedule, stored in the database and editable in the admin (pinned to an upstream commit until a release supports Django 6.1) |
| django-celery-results | task results in the database, cleaned up by beat after a week |
| redis, django-redis | Redis client; Redis cache backend for `CACHE_URL=redis://…`, failing soft (a miss) while Redis is down |
| sentry-sdk | error reports when `SENTRY_DSN` is set (server side only, no personal data: `examleaf/sentry.py` scrubs secrets, card and phone numbers) |
| python-json-logger | JSON log lines on stdout |
| django-guid | request IDs: from the proxy's `X-Request-ID` or new, in every log line (also in Celery tasks) and in the response |
| django-health-check | `/health/` and `/health/web/`: database, cache, storage, Celery workers; its `health_check` command is the web container's readiness check |
| django-admin-interface (django-colorfield) | the admin theme |
| razorpay | the official Razorpay SDK: orders (also for the app's mobile SDK, through the API), payment fetch and capture, refunds, signature checks |
| django-money (py-moneyed, babel) | INR money fields and ₹ formatting |
| django-localflavor (python-stdnum) | Indian states and PIN code validation |
| django-fsm-2 | the order and payment state machines (guarded transitions) |
| WeasyPrint | invoice and credit note PDFs from HTML templates (needs Pango) |
| openpyxl | XLSX export of orders (django-import-export) |
| django-model-utils | `TimeStampedModel` (created/modified) and `StatusModel` for the answer-sheet status |
| django-simple-history | audit trail of edits to books, papers, questions, solutions and legal pages (admin History button) |
| django-taggit | chapter and textbook-section tags on questions |
| django-widget-tweaks | template-level attributes for the My record filter form |
| django-phonenumber-field (phonenumberslite) | phone fields and validation of Indian numbers (region IN): the parent's contact, delivery addresses (website and API) |
| django-import-export | CSV export of users, attempts and consent records from the admin |
| django-filter | the subject/tier filter on My record and the API's list filters |
| django-qr-code (segno) | generates the QR images (PNG for `/qr/<code>.png`, PNG and SVG for `export_qr`) |
| django-storages[s3] (boto3) | optional private S3-compatible buckets for uploaded answer sheets and for database backups |
| django-debug-toolbar | development only, when `DEBUG=1` |
| markdown-it-py | Markdown (with tables) to HTML for questions, solutions and legal pages |
| Pillow | image support for the answer-sheet `ImageField` |
| pytest, pytest-django, pytest-cov, factory_boy | tests, coverage and test data (development and CI) |
| djangorestframework | the REST API (`api/`, API.md): views, serializers, versioning, pagination, throttles; the catalogue, solutions, attempts, accounts and the shop |
| dj-rest-auth | the API's log-in, log-out, token refresh, password change and reset, user details |
| djangorestframework-simplejwt | JWT access and refresh tokens for the app; rotation and blacklist |
| drf-spectacular (drf-spectacular-sidecar) | the OpenAPI 3 schema, Swagger UI and Redoc (their files served by the site) |
| django-cors-headers | CORS for web clients on other origins, `/api/` only |
| ruff | lint and formatting (`pyproject.toml`) |
| KaTeX 0.19 (jsDelivr CDN, with SRI) | renders the `$…$` maths in the browser |

Docker images: python:3.14-slim, postgres:17, redis:7-alpine, caddy:2. django-crispy-forms was considered but has no
plain-CSS template pack (only Bootstrap/Tailwind/Bulma add-ons); forms are rendered by Django's own form templates and
allauth's elements instead.
