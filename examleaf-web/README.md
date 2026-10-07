# ExamLeaf web

The website behind the ExamLeaf Sample Papers books. The solutions are not printed in the books: every paper carries a
QR code that opens `/s/<CODE>/` (e.g. `/s/PHY-E01/`), where a registered student reads the full marking-scheme
solutions for free and can save the marks scored. Now: Class 12, Assam board (ASSEB), Physics, Chemistry,
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
| `/s/<CODE>/` | QR landing page: register / log in (returning here via `next`) for visitors, the solutions for students |
| `/account/signup/` (`/account/register/` redirects), `/account/login/`, `/account/logout/`, `/account/email/`, `/account/password/change/`, `/account/password/reset/` | django-allauth |
| `/account/` | My account: details, change email or password, teacher access, Download my data, Delete my account |
| `/account/record/` | My record: attempts, filter by subject and tier, average per tier; add from a solutions page, edit from here |
| `/account/teacher/` | request teacher access (school, district, subject); staff verify it in the admin |
| `/account/data/` | Download my data (a JSON file; asks for the password again) |
| `/account/delete/` | Delete my account (seven days to change one's mind; `/account/delete/cancel/` keeps it) |
| `/privacy/`, `/terms/`, `/refunds/`, `/shipping/`, `/contact/` | legal pages, edited in the admin (Pages) |
| `/about/`, `/sitemap.xml`, `/admin/` | |
| `/health/`, `/health/web/` | health checks (JSON with `Accept: application/json`); see Production |

Registration asks for full name, email, password, class, board, district (optional) and date of birth, and a consent
box (agreement to the privacy notice, linked beside it) that everyone must tick; its time is stored in `consent_at` and
the event in a `ConsentRecord`. Under 18 it also requires a parent's or guardian's name and phone or email, and the
parent ticks the box; for adults no parent data is asked, validated or kept. The email address is confirmed with a code
typed on the same page, then the student lands back on the paper whose QR code was scanned. The consent is
self-declared: nothing verifies that the person who ticked it is the parent (see RUNBOOK.md).

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
| SALES | orders (shop phase) | view books; the shop phase adds its order, payment, invoice, shipment and product permissions |
| SUPPORT | helps students | view users, email addresses, attempts, consent records, deletion requests; view/change teacher profiles (verifies teachers) |
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
  consent records and deletion requests as JSON, after allauth's re-authentication (password, if none was entered in
  the last five minutes).
- **Delete my account:** a `DeletionRequest` due seven days later; the student gets an email, can log in and cancel
  until then; the daily purge (`accounts.tasks.purge_due_deletions`) anonymises the user row (name, email, phone,
  date of birth, district, parent data, notes cleared; answer-sheet photos, email addresses, teacher profile and
  failed log-ins deleted; consent records kept as proof without the address hash; admin log entries renamed;
  password unusable, so every session ends) and emails a confirmation to the old address. The marks stay as
  anonymous statistics.
- **Changing the email address:** allauth's `ACCOUNT_CHANGE_EMAIL` keeps one address; a new one replaces it only after
  the emailed code is confirmed, after re-authentication, and the old address is notified.
- **Logs:** no personal data in them by design (no logs of good log-ins; Celery's task arguments, which hold email
  texts, are left out of the JSON log lines; Sentry runs with `send_default_pii=False`).

## Admin

django-admin-interface gives the admin ExamLeaf's colours and name (theme set by `ops/migrations/0001_admin_theme.py`;
the related-object pop-up stays a window because the CSP forbids frames). The index page
(`templates/admin/dashboard.html`, `admin.site.index_template`) shows registrations, registrations with a confirmed email
and saved attempts today and in the last 30 days, and the teacher requests and account deletions waiting.
Books, papers, questions, solutions and legal pages keep a full edit history (django-simple-history); users, attempts
and consent records export to CSV (django-import-export); periodic tasks and task results are under Celery.

## Tests

```sh
make test                                 # pytest: 52 tests, about 35 s (imports all four subjects once)
make cov                                  # the same with a coverage report (91 %)
make lint                                 # ruff, as in CI
make check                                # manage.py check and missing migrations
```

pytest with pytest-django runs the old Django `TestCase` classes and the newer pytest functions (factories in
`accounts/factories.py`, factory_boy); `manage.py test` still runs the `TestCase` classes. CI
(`.github/workflows/ci.yml` at the repository root) runs ruff, the migration check and the tests with coverage on
PostgreSQL 17. They cover the import of the four subjects (30 papers each, every solution matched, re-import changes
nothing), the QR landing redirect, the gated solutions page and log-in returning to it (and never to another site), the
QR image and export guard, registration (parent details and consent under 18, none kept for adults; the STUDENT role
and the consent record), the Markdown renderer, query counts, the Content-Security-Policy and private caching of the
paper page, axes, recording attempts; the role groups' permissions, bootstrap_roles, role actions in the admin (and
that support staff cannot use them), the teacher request and verification; Download my data, deletion with its
grace period and cancellation, the purge task and what it erases, email change re-verification; the legal pages and
their history, the health endpoint, request IDs, the email fallback, the admin dashboard and the backup upload.

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
Errors go to Sentry when `SENTRY_DSN` is set. Uploaded files (answer-sheet photos, later) go to `media/`, never served
publicly, or to a private bucket with `MEDIA_BUCKET`; the upload view must check the file size when it is built.

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

**Shop** (printed books: orders, Razorpay payments, invoices, shipments). Ready for it: the SALES group (add the shop's
permissions to `ROLES[SALES]` in `accounts/roles.py`, then `bootstrap_roles`); the Refund, Shipping, Terms and Contact
pages Razorpay asks for; Celery for order emails (`ops.tasks.queue_email` / `queue_text_email`) and for webhook
follow-up work; beat for reconciliation jobs; `CELERY_RESULT_BACKEND` for task results; the request ID in logs to trace
a payment; `.env.example` and DEPLOYMENT.md to extend with `RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET`/webhook secret. The
CSP must then allow Razorpay's checkout script and frame (`script-src`/`frame-src https://checkout.razorpay.com`,
`connect-src`/`img-src` as Razorpay documents), and the Privacy Policy already describes order data and Razorpay.
Order and invoice records must survive account deletion (tax law): keep them on `DeletionRequest.complete()`'s
anonymised user, or detach them, rather than cascading.

**REST API** (Django REST Framework, dj-rest-auth, drf-spectacular) for the apps. Ready for it: roles map to DRF
permissions (`DjangoModelPermissions` uses the same group permissions; `user.has_role()` for custom ones), allauth is
the account backend dj-rest-auth builds on (registration must keep the consent and parent rules of
`accounts.forms.SignupForm` and call `ConsentRecord.record`), Download my data and deletion are plain functions to
expose as endpoints, `CSRF_TRUSTED_ORIGINS`/proxy settings are environment-driven, and Redis is there for DRF
throttling. The app stores will ask for the Privacy Policy and an in-app account deletion, both of which exist.

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
| redis, django-redis | Redis client; Redis cache backend for `CACHE_URL=redis://…` |
| sentry-sdk | error reports when `SENTRY_DSN` is set (server side only, no personal data) |
| python-json-logger | JSON log lines on stdout |
| django-guid | request IDs: from the proxy's `X-Request-ID` or new, in every log line (also in Celery tasks) and in the response |
| django-health-check | `/health/` and `/health/web/`: database, cache, storage, Celery workers |
| django-admin-interface (django-colorfield) | the admin theme |
| django-model-utils | `TimeStampedModel` (created/modified) and `StatusModel` for the answer-sheet status |
| django-simple-history | audit trail of edits to books, papers, questions, solutions and legal pages (admin History button) |
| django-taggit | chapter and textbook-section tags on questions |
| django-widget-tweaks | template-level attributes for the My record filter form |
| django-phonenumber-field (phonenumberslite) | phone field and validation of Indian numbers (region IN) for the parent's contact |
| django-import-export | CSV export of users, attempts and consent records from the admin |
| django-filter | the subject/tier filter on My record |
| django-qr-code (segno) | generates the QR images (PNG for `/qr/<code>.png`, PNG and SVG for `export_qr`) |
| django-storages[s3] (boto3) | optional private S3-compatible buckets for uploaded answer sheets and for database backups |
| django-debug-toolbar | development only, when `DEBUG=1` |
| markdown-it-py | Markdown (with tables) to HTML for questions, solutions and legal pages |
| Pillow | image support for the answer-sheet `ImageField` |
| pytest, pytest-django, pytest-cov, factory_boy | tests, coverage and test data (development and CI) |
| ruff | lint and formatting (`pyproject.toml`) |
| KaTeX 0.19 (jsDelivr CDN, with SRI) | renders the `$…$` maths in the browser |

Docker images: python:3.14-slim, postgres:17, redis:7-alpine, caddy:2. django-crispy-forms was considered but has no
plain-CSS template pack (only Bootstrap/Tailwind/Bulma add-ons); forms are rendered by Django's own form templates and
allauth's elements instead.
