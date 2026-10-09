# ExamLeaf web

The backend of the ExamLeaf Sample Papers website and app: the REST API, allauth.headless, the admin, the webhooks and
the background tasks. The website's pages are the Next.js frontend's (`../examleaf-frontend/`), on the same origin
behind Caddy; Django serves no page of its own (see "Paths"). The solutions are not printed in the books: every
paper carries a QR code that opens `/s/<CODE>/` (e.g. `/s/PHY-E01/`), where a registered student reads the full
marking-scheme solutions for free and can save the marks scored (or anyone reads them, with
`SOLUTIONS_REQUIRE_LOGIN=0`: see "Open or registered solutions"). The same site sells the printed books and serves the
app's revision course. Now: Class 12, Assam board (ASSEB), Physics, Chemistry, Mathematics and Biology, 30 papers each
(E01–E10 Easy, M01–M10 Medium, H01–H10 Hard).

Django 6.1 · Python 3.14 · Django REST framework and allauth.headless for the website and the app · no trackers,
analytics or ads of our own · PostgreSQL, Redis and Celery in production, none of them needed in development.

Documents: [DEPLOYMENT.md](DEPLOYMENT.md) (first deployment on a VPS, every setting, the accounts to open),
[RUNBOOK.md](RUNBOOK.md) (backups, secrets, data requests, email and SMS failures, the shop, the revision course),
[API.md](API.md) (the REST API, for the app and other frontends), [CHANGELOG.md](CHANGELOG.md) (what changed, by phase)
and the security reviews, [SECURITY_REVIEW.md](SECURITY_REVIEW.md) (phases 1 to 4) and
[SECURITY_REVIEW_PHASE5_6.md](SECURITY_REVIEW_PHASE5_6.md) (phases 5 and 6).

## Contents

- [What it does](#what-it-does)
- [Set up and run (development)](#set-up-and-run-development) · [Commands](#commands)
- [Importing the papers](#importing-the-papers) · [QR codes](#qr-codes)
- [Paths](#paths) · [Open or registered solutions](#open-or-registered-solutions)
- [Sign-in, SMS and email](#sign-in-sms-and-email) · [Roles and permissions](#roles-and-permissions)
- [Personal data (DPDP Act)](#personal-data-dpdp-act) · [Admin](#admin) · [REST API](#rest-api)
- [Shop](#shop) · [Revision course](#revision-course) · [Web platform](#web-platform) · [Insights](#insights)
- [Tests](#tests) · [Production](#production)
- [Data model](#data-model) · [Planned extensions (not built)](#planned-extensions-not-built) ·
  [Phases to come](#phases-to-come) · [Libraries](#libraries)

## What it does

- **Solutions behind the QR codes.** `/s/<CODE>/` shows a paper's marking-scheme solutions to a signed-in student
  (everyone, with `SOLUTIONS_REQUIRE_LOGIN=0`). **My record** keeps the marks a student scored per paper and tier.
- **Student accounts.** Sign-up with an email address confirmed by a 6-digit code typed on the next page (no link to
  open). Log-in with the password, a code by email, a code by SMS to a mobile number confirmed on My account (where SMS
  are sent), a passkey, or Google (when its keys are set). Parental consent for students under 18: a ticked box, or,
  with `PARENTAL_CONSENT_MODE=verified`, a link emailed or texted to the parent. Download my data, Delete my account
  (seven days to change one's mind), an address book, teacher access requests.
- **Staff.** Roles (content editor, sales, support, admin, and the Admin Control Panel's owner, finance, packer,
  reviewer, marketing, auditor and sales rep), the branded admin with a dashboard and edit histories, and a second
  factor for every member of staff: an authenticator app with recovery codes, or a passkey. The Admin Control Panel's
  backend (`staff/`, API.md "Staff API"): scopes, limits and separation of duties, an append-only hash-chained audit
  log, approvals by a second person, an inbox, the site's switches and feature flags, API keys, staff invitations and
  offboarding, the data requests queue, the breach register and the processor register; Legal and privacy: the
  compliance cockpit with every legal clock, legal holds and the erasure that obeys them, the retention schedule in code,
  the legal pages' versions, the e-commerce disclosures and the yearly dark-pattern self-audit (staff/README.md); the
  tax desk (`shop/README.md` "Tax"): the HSN and SAC master with dated rates, the documents and their series, the
  threshold monitor, the calendar and the GSTR-1 job.
  Phase B adds the role
  catalogue, a person's access with its last use and a role change previewed, offboarding as a checklist, passkeys
  for the privileged roles and one's own sessions; the integrations' connections (keys tested before they are kept,
  modes, circuits, webhook tokens, events, calls and dead letters), the message templates DLT registers with MSG91's
  delivery reports, and the system's backups, logs, dependencies, hardening and checkout scripts
  (`integrations/README.md`, `ops/README.md`, `staff/README.md` "Phase B").
- **Content in the panel** (`content/README.md`, API.md "Content (staff)"). A question's or a solution's text changes
  as a draft that a second person reviews and publishes (the site keeps the live text until then; a publish can be
  rolled back); readers report mistakes from each solution and clip (Turnstile, limits, spam set apart), triaged into
  errata per print run; imports from the books repository run as a dry run, then its apply; the legal deposits are
  recorded per library, with an inbox item until all four have the book; ISBNs and LaTeX are checked.
- **The shop.** The printed books sold across India: cart, coupons, checkout with Razorpay (UPI, cards, net banking) or,
  when `SHOP_COD_ENABLED` is on (it is off by default), cash on delivery, stock under row locks, shipping rates by
  state, PIN code autofill from India Post's directory, order emails (and SMS), courier tracking links, GST invoices and
  credit notes as PDFs (a tax invoice, a bill of supply or an invoice-cum-bill of supply by their lines, the GST rate
  read by date from the HSN and SAC master, the shipping taxed with the goods it carries), refunds, a test mode and a
  live mode, order links for guests, reviews from buyers, "email me when it is back", school quotations, the GSTR-1
  files for the accountant in the GST Offline Tool's templates.
- **Store features.** A category tree and collections, product types with attributes, digital products (the course),
  automatic offers, staff orders for phone and school buyers with Razorpay payment links or offline payments, order
  notes, a customer page, import and export of products and categories, and the roles that run it.
- **Orders for staff** (the Admin Control Panel's Orders module, [shop/README.md](shop/README.md)): the list with its
  tabs and searches (a search for a person audited by its hash), an order's record with its next step and timeline,
  refunds by line or by bank transfer with their approval above the maker's limit, returns asked for on the website or
  by staff, staff orders with the discount rule's answer shown before saving, quotes made into orders, the packing
  queue with its slips, 4×6 labels and pick list, bulk jobs (pack, print, cancel, export), the cash-on-delivery risk
  hold, status messages held overnight, and the owners' weekly email of what staff gave away.
- **Finance for staff** (the panel's Finance module, [shop/README.md](shop/README.md) "Finance"): Finance today (what
  waits for FINANCE, a line a duty), payments with the stuck ones asked of Razorpay again, refunds and offline payments
  with the approvals waiting, payment links for staff orders and for ERPNext's B2B invoices, and Razorpay's settlements
  fetched every morning, matched to the payments and refunds by Razorpay's id (the rest by hand, with a note) and
  posted to ERPNext once with the fee and the GST on it.
- **The revision course** for the mobile app, through the REST API: per chapter a revision of a target length (12
  minutes by default) in short clips (ffmpeg makes HLS for low-end phones), one-mark quiz items, flash cards, a
  day-by-day pass plan, book codes printed in the books, entitlements, and a daily reminder through Firebase Cloud
  Messaging.
- **Web platform.** Product pictures in AVIF and WebP, a public and a private storage bucket, a link-preview picture
  per product (the website's SEO tags, JSON-LD and installable web app are the frontend's).
- **ERPNext** (`erp/`, `erp/README.md`): the platform's items, invoices, credit notes, payments, delivery notes and
  COD settlements mirrored in ERPNext through an outbox written with each document, in order and once (keys,
  retries, dead letters); ERPNext's stock and B2B documents read back by webhook and a 15-minute pull; a nightly
  reconciliation of the day's totals. Every flow behind a switch, off by default; no customer's personal data goes.
- **Insights for staff** (`insights/`): nightly demand forecasts per title and district with their backtest against
  the seasonal naive, print-run advice (the newsvendor's quantity, reprint triggers), the quiz's item analysis,
  cohorts, code activation, delivery times, fraud signals and what offers did; learner data only as aggregates.
- **Home and reports for staff** (`insights/`, `insights/README.md` "Home and Reports"): every number of the panel's
  Home defined once (`metrics.py`: net revenue, orders, codes redeemed, active learners, the queues that wait for a
  person), test-mode orders left out by construction, the cards of each role with the previous period beside them;
  reports of sales by product, subject, class, board, edition and period, sales by state, district and PIN code, book
  codes by batch, the course's use by subject and chapter, cash on delivery and Razorpay's settlements, the print-run
  sum recomputed from typed inputs, each report saying how it counts; cells under 10 people hidden; any report exported
  as a file; no row names a person.
- **Support** (`support/`, `support/README.md`): every complaint a ticket with a number the customer can quote
  (`SR-2026-000123`), from the contact form, "My requests" on the account, email to the support address (forwarded,
  threaded, loops guarded), or logged by staff (calls, WhatsApp, National Consumer Helpline complaints with their
  docket); the legal clocks in calendar time in India (48 hours to acknowledge and a month to redress, NCH's 30 days,
  the privacy rights' deadlines, the IT Rules' behind a switch), watched every 15 minutes; the acknowledgement with the
  number (and, from 1 January 2027, a copy of the complaint); the queue, the conversation, saved replies in English,
  Assamese and Bengali, and the actions on the customer's orders and course from the ticket; the grievance register as
  a CSV.
- **Messages and protection.** An SMS gateway (MSG91, under India's DLT rules) with a daily cap and a log, email through
  Amazon SES with a suppression list fed by bounce and complaint webhooks, Cloudflare Turnstile on public forms,
  passwords of 10 characters that are not in breaches, rate limits, a strict Content-Security-Policy, error reports
  to Sentry with personal data scrubbed.
- **REST API v1** for the app and other frontends ([API.md](API.md)): sign-up and log-in (JWT, or allauth.headless), the
  catalogue, solutions, attempts, data rights, the shop, the store catalogue, the revision course, and the site's
  switches and legal pages.
- **Operations.** One Docker image for the site, two Celery workers (the second for the clip videos) and beat, behind
  Caddy; PostgreSQL and two Redis; database backups, encrypted with age and uploaded off-site when
  `BACKUP_AGE_RECIPIENT` and `BACKUP_BUCKET` are set; health checks for an uptime monitor; JSON logs with a request ID.

## Set up and run (development)

```sh
cd examleaf-web
make install                              # .venv with the pinned requirements and the test tools (requirements-dev.txt)
cp .env.example .env                      # DEBUG=1, SQLite, console email and SMS, tasks inline; every variable is explained
make migrate                              # migrate + bootstrap_roles (the role groups)
.venv/bin/python manage.py import_papers --all   # the books checked out beside this repository; or --root, --fixtures
.venv/bin/python manage.py createsuperuser
make run                                  # http://localhost:8000: the API; the admin at /admin/ logs in on the website
```

The website and its log-in page are the frontend's: to use the admin in development, run Django for the frontend and
open http://localhost:3000/admin/ (below, "The website (Next.js) in development").

`make help` lists the other tasks (see "Commands"). In development the verification codes, every other email and every
SMS are printed in the runserver console, and the debug toolbar is on. Invoice PDFs need Pango (`brew install pango` on
a Mac) and the revision course's videos need ffmpeg (`brew install ffmpeg`); without ffmpeg a clip shows "failed:
ffmpeg is not installed". To run the whole stack in Docker on a laptop, set `DOMAIN=localhost`, `POSTGRES_PASSWORD`
and `HEALTH_CHECK_TOKEN` in `.env` and run `make up`; Caddy then uses its own certificate, which
`docker compose exec caddy caddy trust` makes your browser accept (once).

### The website (Next.js) in development

The website (`../examleaf-frontend/`, its README) runs on http://localhost:3000 and passes Django's paths (`/api/`,
`/_allauth/`, `/admin/`, `/static/` …) to Django on port 8100, so the browser sees one origin, as behind Caddy. Run
Django for it with the frontend's origin and host:

```sh
SITE_URL=http://localhost:3000 CSRF_TRUSTED_ORIGINS=http://localhost:3000 USE_X_FORWARDED_HOST=1 \
  .venv/bin/python manage.py runserver 8100
```

`SITE_URL` makes every email link (password reset, the parent's link, orders) point at the frontend, which serves the
website's paths; `CSRF_TRUSTED_ORIGINS` accepts its `Origin`; `USE_X_FORWARDED_HOST` lets its server-side calls name
the site's host (`X-Forwarded-Host`), as Caddy does. No CORS: open only http://localhost:3000, never 8100, so that the
session and CSRF cookies stay on one origin (`CORS_ALLOWED_ORIGINS` stays empty). The frontend's typed API client is
made from `/api/schema/?format=json` of this server (`npm run api:snapshot` there).

### Background tasks (Celery)

Emails (verification codes, password resets, order mails), SMS, invoices and refunds, picture sizes and the clip videos
are handled by Celery tasks, and celery beat runs these on a schedule (India time). Beat writes the entries of
`settings.py`, and django-celery-beat's own 04:00 clean-up of task results, into the database each time it starts, so a
time changed in the admin (Periodic tasks) is put back at the next start and only switching an entry off lasts; the
04:30 flush of the API's tokens was made once by the migration `api/migrations/0001_flush_expired_tokens_daily.py` and
can be edited in the admin:

| When | Task |
|---|---|
| 00:01 | a legal page's version published for that day put in force (`pages.tasks.publish_due`) |
| 01:45 | `shop.tasks.watch_tax_thresholds`: the tax threshold monitor (the year's turnover against ₹2, 4, 5 and 10 crore, large invoices to another state, parcels needing an e-way bill; an inbox item when a line is crossed: `shop/README.md` "Tax") |
| 01:00 to 03:00, every 15 minutes | the insights jobs, one task each: backtest, demand forecast, print-run advice, item analysis, cohorts, code activation, delivery times, offer effects, fraud rules and their email (`insights/README.md`; DEPLOYMENT.md section 21) |
| 03:00 | purge the account deletions whose seven days are over (but those a legal hold or a child's parent keeps waiting), and the registration details the intermediary rule kept 180 days |
| 03:05 | copy the erasure ledger's lines not yet there to the backups' bucket |
| 03:15 | `insights.tasks.course_health`: how the course is used by subject and chapter, counted for the course-health report (`insights/README.md` "Course health") |
| 03:30 | forget failed log-ins (django-axes) |
| 03:45 | delete expired sessions |
| 04:00 | delete task results older than a week |
| 04:10, 04:20 | the retention schedule's clean-up (`ops.tasks.trim_expired`, `purge_expired`): the SMS log's last digits after 90 days and its rows after a year, webhook records and task results after 7 days, the app's phones silent for 90 days, the orders past their books' period |
| 04:30 | `shop.tasks.clean_up`: cancel orders never paid or placed (after asking Razorpay), queue again lost refund, invoice and credit note tasks, delete guest carts idle for 30 days, old webhook records and payloads, old stock alerts and the customer details of cancelled unsold orders |
| 04:30 | forget expired refresh tokens of the API |
| every hour (at :15) | send the "back in stock" emails |
| 08:00 | email the SALES role the books running out |
| 18:00 | send the revision course's reminders (only with `FCM_SERVICE_ACCOUNT_JSON`) |

Without `CELERY_BROKER_URL`, and always in tests, tasks run inline in the web process (`CELERY_TASK_ALWAYS_EAGER`), so
development needs no broker and no worker. To try the real thing locally:

```sh
brew install redis && brew services start redis   # or any Redis 7
echo CELERY_BROKER_URL=redis://localhost:6379/0 >> .env
make worker                               # threads pool: Celery's prefork pool fails on macOS
make beat                                 # the periodic tasks of the table above
```

The clips are processed on a queue of their own, `media`, by a second worker (`celery -A examleaf worker --queues media`;
in compose, the `media-worker` service); in development they are processed in the web process when the clip is saved.

If the broker cannot be reached (refused at once, or no answer within a few seconds), an email or SMS is sent from the
web process instead, so that a sign-up never fails because Redis is down; if the email provider is down as well, the
failure is logged (Sentry) and the page goes on: the student asks for a new code.

## Commands

Make targets (`make help` prints them; they use `.venv`, and `up`, `down`, `logs`, `shell`, `import` and `backup` the
docker-compose stack):

| Target | What it does |
|---|---|
| `install` | create `.venv` and install `requirements-dev.txt` (the pinned requirements and the test and lint tools) |
| `run` | development server on http://localhost:8000 |
| `migrate` | `migrate`, then `bootstrap_roles` |
| `worker`, `beat` | Celery worker (threads pool) and beat for local testing; need `CELERY_BROKER_URL` |
| `test`, `cov` | the test suite (pytest), also with a coverage report |
| `lint`, `format` | ruff: lint and formatting check as in CI; fix and format |
| `check` | `manage.py check` and `makemigrations --check --dry-run` |
| `deploy-check` | `DEBUG=0 manage.py check --deploy` (with the production `.env`, only W005 and W021 remain) |
| `up`, `down`, `logs`, `shell` | start the compose stack (migrates and bootstraps roles on start), stop it, follow its logs, a Django shell in the web container |
| `import` | `import_papers --all` in the running stack |
| `backup` | `scripts/backup.sh`: dump the stack's database to `backups/` and upload it when `BACKUP_BUCKET` is set |

`manage.py` commands of the project (in the stack: `docker compose exec web python manage.py …`):

| Command | What it does |
|---|---|
| `import_papers --all` (or `--subject physics`; `--root`, `--fixtures`) | read the Markdown papers and solutions of the books repository's `production/` (`PAPERS_ROOT`) into the database; changes only what changed |
| `export_qr --out qr/` | write every paper's QR code as PNG and SVG; refuses `localhost` and http addresses unless `--force` |
| `bootstrap_roles` | create the role groups and set their permissions from `accounts/roles.py`; run it after every `migrate` |
| `seed_shop [--stock N]` | create the starting catalogue: the books, the Physics bundle, coupon WELCOME10, three shipping rates |
| `reconcile_payments [--older-than MINUTES]` | ask Razorpay about online orders still awaiting payment (staff orders' links included) and record payments the site never heard about |
| `fetch_settlements [--day YYYY-MM-DD] [--dry-run]` | a day's Razorpay settlements (yesterday by default) fetched, matched and posted to ERPNext, as the 03:15 run and the panel's "Fetch a day" do |
| `import_pincodes <csv>` | replace the PIN code table with India Post's directory from data.gov.in |
| `export_gstr1 --from DATE --to DATE [--out DIR]` | the accountant's GSTR-1 files in the GST Offline Tool's CSV templates: b2cl, b2cs, cdnur, exemp, hsn-b2b, hsn-b2c, docs, and the credit notes' register (the panel runs it as a job: Tax, GSTR-1) |
| `build_covers` | draw the AVIF and WebP sizes of the four covers and the default link-preview picture into `static/img/` (the website shows them); run it after a cover changes and commit the files |
| `import_chapter_insights [--root] [--fixtures] [--subject]` | fill the course's chapters with the Board's marks and the number of past-paper questions from the books repository's `production/<subject>/` |
| `build_quiz_items` | make quiz items from the imported one-mark questions whose options and answer parse; keeps edited items |
| `make_book_codes <PHY\|CHE\|MAT\|BIO\|ALL> <count> --batch NAME [--out FILE]` | make book codes for a print run as a CSV; the only copy of the codes |
| `reprocess_clips [ids] [--all]` | queue clips for ffmpeg again (the failed and the stuck ones by default) |
| `upload_backup <file>` | upload a backup file to the backup bucket (`scripts/backup.sh` calls it); does nothing without `BACKUP_BUCKET` |
| `insights_run <job>\|all [--date YYYY-MM-DD]` | run an insights job now, as its nightly task does (`all`: in the night's order); `--date` works out the forecasts as on another day |
| `insights_review` | the monthly review: each title's last four weeks of forecasts beside the copies sold and the seasonal naive |

Django's and the libraries' own commands that the documents rely on: `migrate`, `createsuperuser`,
`check` (`--deploy`), `makemigrations --check --dry-run`, `sendtestemail`, `collectstatic` (at image build),
`shell`, `clearsessions` and `axes_reset` (what the daily tasks call), `axes_reset_username <email>` (lift a lock-out),
`health_check health_web --no-http` (django-health-check: the web container's readiness check, the database and the
migrations),
`flushexpiredtokens` (simplejwt), and `spectacular --validate --fail-on-warn --file schema.yml` (checks the OpenAPI
schema).

## Importing the papers

```sh
.venv/bin/python manage.py import_papers --root "/Users/chinmoybhuyan/Desktop/Personal/Book/Class 12" --subject physics
.venv/bin/python manage.py import_papers --all             # --root: PAPERS_ROOT, else "Class 12" beside the repo
.venv/bin/python manage.py import_papers --all --fixtures  # the test papers of content/fixtures/papers/
```

The papers live in the books repository `LazyIndianBook/Class-12-Assam` (private), not in this one: `--root` (or the
setting `PAPERS_ROOT`) is a checkout of it, the folder that holds `production/`. Without either, the command uses
`Class 12` beside this repository's folder when it is there (the founder's machine), and otherwise stops and says so.
On a server: DEPLOYMENT.md section 4. `--fixtures` imports the copies in `content/fixtures/papers/` instead: E01, M01
and H01 of each subject and PHY-E02, 13 papers and 637 questions with their solutions, the chapter tags, the four
`format.json` and one `pyq/` file each (its README says from which commit); the tests and the Playwright backend use
them, so CI needs no second repository.

The command creates the board ASSEB (Assam), Class 12, the subject and its book, and reads
`production/<subject>/papers_md/<CODE>-<T><NN>.md` and `-solutions.md` with `parse_paper`, `parse_solutions` and
`split_marks` from `content/papers_parser.py`: a copy of those functions of the books repository's
`production/build/book.py`, which stays the source of truth (copy them again when it changes how a paper is written,
and refresh the test papers). Question labels are derived from the
paper's structure the way the solutions file names them: `9`, `1(a)`, `9 OR`, `B9(a)`/`Z3 OR` (Biology's Botany and
Zoology parts), and the plain numbered sections of Mathematics papers 08–10. A lettered line under a numbered
question that is not a group heading is a sub-part of that question (Chemistry table questions). Chapter and textbook
section tags come from the work orders (`production/<subject>/orders/ch*.md`).

It reports, per subject, papers, questions, solutions matched, tags, created/updated/unchanged records, and lists every
solution label it could not match and every question without a solution (it exits with an error if there are any).
Re-running it changes only what changed in the Markdown, so the edit history stays meaningful; a question no longer in
the books is taken off the site, not deleted, and a draft saved in the panel is left alone. `--dry-run` compares and
writes nothing. The panel does the same per subject (Content → Imports: a dry run, then its apply, `staff.import_content`;
content/README.md "Imports"): the command is the shell's way, for a whole repository at once or when the panel is down.
Current result on the books: 30 papers per subject; Physics 1650, Chemistry 1260, Mathematics 1383, Biology 1590
questions, every one with its solution and tags; 0 unmatched. On the test papers: 220, 126, 132 and 159 questions;
then `import_chapter_insights --fixtures` makes the 51 chapters and `build_quiz_items` 69 quiz items.

## QR codes

- `/qr/<CODE>.png` — the QR image for a published paper; it encodes `SITE_URL + /s/<CODE>/`.
- `.venv/bin/python manage.py export_qr --out qr/` — all papers as `<CODE>.png` and `<CODE>.svg` (37 mm square in the SVG).

Set `SITE_URL` to the real domain before exporting codes for print: `export_qr` refuses to write codes for `localhost`
or a plain-http address (a printed book cannot be corrected), unless you pass `--force` for a test run.
The website answers `/s/<CODE>/` in any case (`/s/phy-e01/` goes to `/s/PHY-E01/`). The panel's page of a paper shows
its code and gives the picture, also for a print run (`?printing=PHY-2027-2` in the address the code prints, which the
website's "Report a mistake" then sends with a report).

## Paths

The website's pages (the home page, the books, `/s/<CODE>/`, the shop, cart and checkout, the orders, the account
pages, `/c/<token>/`, `/revision/`, the legal pages, `robots.txt`, `sitemap.xml`, the web app's manifest and service
worker, and the error pages) are the Next.js frontend's, at the addresses Django's pages had
(`../docs/design/parity-nextjs.md`). Caddy sends Django only its own paths (the Caddyfile's list, and
`DJANGO_PREFIXES` in the frontend):

| URL | What |
|---|---|
| `/api/…` | the REST API ([API.md](API.md)), which the website and the app use; `/api/schema/`, `/api/docs/`, `/api/redoc/` |
| `/_allauth/browser/v1/…`, `/_allauth/app/v1/…`, `/_allauth/openapi.json` | allauth.headless: log-in, sign-up, codes, passkeys, MFA and account flows as JSON, for the website (same origin) and the app ([API.md](API.md) "Frontend integration guide"); `openapi.yaml` is the same description |
| `/account/google/login/callback/` | Google's return to the site after its sign-in (only with its keys); the sign-in starts with a POST to `/_allauth/browser/v1/auth/provider/redirect` |
| `/qr/<CODE>.png` | a published paper's QR code |
| `/shop/webhooks/razorpay/` | Razorpay's webhooks (signed) |
| `/shop/media/…` | the public pictures when there are no buckets (only `products/` and `og/`) |
| `/learn/preview/<clip>/`, `/learn/hls/<token>/<file>` | the staff player for a clip (on the admin's layout); the HLS playlists, segments and poster behind signed links |
| `/health/`, `/health/web/`, `/health/integrations/` | health checks (JSON with `Accept: application/json`); through Caddy only with the `X-Health-Token` header; see Production; the last one for a second monitor: the integrations (`integrations/README.md`) |
| `/api/hooks/parcel-events/` | Shiprocket's tracking webhook (its token in `x-api-key`; `shipping/README.md`), under Caddy's `/api/` |
| `/api/hooks/erp-events/` | ERPNext's webhook (signed: `X-Frappe-Webhook-Signature`; `erp/README.md`), under Caddy's `/api/` |
| `/api/hooks/support-mail/` | email to the support address, forwarded (its token in `X-Support-Mail-Token`; `support/README.md`), under Caddy's `/api/` |
| `/anymail/<provider>/tracking/` | the email provider's bounce and complaint webhooks; exist only while `ANYMAIL_WEBHOOK_SECRET` is set |
| `/admin/` | the admin; signed out it sends to the website's log-in (`LOGIN_URL`, then back with `?next=`) |
| `/static/…` | the admin's and the staff player's files, the fonts of the invoices and the book covers the website shows |

What a signed-in user gets from Django carries `Cache-Control: no-store` unless the view sets its own (the API's
solutions and cached catalogue). Django's error pages (`templates/400.html`, `403.html`, `403_csrf.html`, `404.html`,
`429.html`, `500.html`) are plain: they answer only Django's own paths (the 400 and 500 pages need no static file or
database; the 500 page shows the request ID as a reference for support), and under `/api/` the same errors are JSON.

Registration asks for full name, email, password, class, board, district (optional) and date of birth, and a consent box
(agreement to the privacy notice, linked beside it) that everyone must tick; its time is stored in `consent_at` and the
event in a `ConsentRecord`. Under 18 it also requires a parent's or guardian's name and phone or email, and the parent
ticks the box; for adults no parent data is asked, validated or kept. The email address is confirmed with a code typed
on the next page (the website's `/account/verify-email/`), then the student lands back on the paper whose QR code was
scanned. With
`PARENTAL_CONSENT_MODE=declared` the consent is self-declared: nothing verifies that the person who ticked it is the
parent (see RUNBOOK.md "Parental consent"). With `verified` the parent gets a link (valid 7 days) by email, or by SMS
when the contact is a mobile number, once the student has confirmed their own address (at once after Google); the
message is fixed text, with the student's name only when it is plain letters (otherwise "a student"); one contact gets
at most 3 links a day, and the student can ask for it again every 10 minutes. Sign-up asks for no mobile number: a
student adds one later on My account.

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

The research (`../docs/examleaf-platform-plan.md`, "Open solutions") recommends open: a registration wall weakens the
feedback that makes practice work, most for weak students; it makes ExamLeaf the keeper of many children's data under
the DPDP Act, with identity-checked parental consent, from May 2027; and in rural Assam many students use a parent's
phone. The cost of open is that the solutions can be copied without an account (no evidence that this hurts sales). The
QR codes point at `/s/<CODE>/` either way, so the switch needs no reprint.

## Sign-in, SMS and email

- **Codes.** Sign-up, "Log in with a code" and a new email address are confirmed with a 6-digit code (allauth; three
  tries a code, then a new one is needed; valid 15 minutes for an address, 3 minutes for a log-in code and 5 for a
  mobile number). An address or number gets 3 log-in codes an hour (30 an hour per client address); an address gets an
  email confirmation code at most every 10 seconds, 5 an hour and 10 a day; a mobile number's confirmation code goes out
  once a minute at most. The tries of one code are counted in the cache too (3 per 15 minutes, 60 an hour per client
  address), so parallel requests cannot get more. The log-in code page has no "Send a new code" button: asking again
  gives a new code within these limits. Mail goes out through a Celery task: printed in the console in development, in
  production through django-anymail (Amazon SES in Mumbai is the documented choice; Brevo and Postmark work through
  their own `EMAIL_BACKEND`).
- **Mobile number.** Added and changed on My account (the app can do the same through allauth.headless), kept once its
  SMS code is confirmed (`User.login_phone`), one account per number; it then logs in with the password (the number as
  typed: "98640 12345") or a code by SMS. Phone log-in, order SMS and SMS consent links exist only where SMS are sent:
  `SMS_BACKEND=msg91` on a server (`console` only prints them, in development). The account is emailed when a number is
  added to it, and the account that held the number before when it moves away.
- **Passkeys** for everyone (My account; "Use a passkey" on the log-in page), with one relying party, the host of
  `SITE_URL`; staff use one as their second step after the password, never alone (a passkey-only log-in of a member of
  staff is refused). No sign-up by passkey. **Google** when both `GOOGLE_*` keys are set (PKCE; a new student fills in
  the student details after Google).
- **Cloudflare Turnstile** when both its keys are set: sign-up (not after Google), "Log in with a code", the coupon and
  quotation forms. If Cloudflare cannot be reached within 5 seconds the form goes through and the log says so. The app
  sends the token as `turnstile` to allauth.headless's sign-up and code request and to `quotes/`; the older
  `auth/registration/` and `auth/phone/code/` have no widget (API.md "Turnstile").
- **SMS gateway** (`ops/sms.py`): one Celery task, backends `console` and `msg91` (its OTP and Flow APIs, 10 second
  timeout, retried on network errors), five kinds (codes, order placed, shipped, delivered, parent consent) each with a
  DLT template. Every SMS is a row of the SMS log (a keyed hash of the number, its last four digits, status; 90 days).
  Before one is queued it is counted against limits: 5 an hour and 10 a day to one number, 20 a day to one account, and
  each purpose's share of the day's cap (log-in codes 70 %, order updates 30 %, parent consent links 10 %). A refused
  SMS is logged "not sent: a limit was reached" and the page does not say it was sent (a code request is answered 429:
  "Too many messages have gone to this number: try again tomorrow, or log in with your email."). At most `SMS_DAILY_CAP`
  go out a day, the last line, counted in the database because the cache-based limits fail open while Redis is down.
  Order SMS go only to accounts with a confirmed number that switched them on.
- **Email suppression.** With `ANYMAIL_WEBHOOK_SECRET` set, the provider's webhooks put hard bounces, invalid addresses
  and spam complaints in a suppression list (admin, Ops); nothing more is sent to those addresses until staff delete
  the row. Soft bounces are ignored.
- **Passwords**: at least 10 characters, none found in data breaches (Pwned Passwords: only the first 5 characters of
  the password's SHA-1 leave the server). django-axes locks an account for 15 minutes after 10 failed log-ins from one
  address; allauth limits failed log-ins per account (5 in 5 minutes) and per client address (10 a minute).

## Roles and permissions

Roles are Django groups; `accounts/roles.py` lists each group's model permissions and is the only place to change them.
Migration `accounts.0004_roles` creates the groups; after every `migrate` the staff app sets every group to exactly
its permissions, including those of apps migrated later (a post_migrate receiver, `staff/apps.py`), and
`manage.py bootstrap_roles` (idempotent; `make migrate`, the docker web container and DEPLOYMENT.md still run it)
does the same by hand.

| Group | Who | Permissions now |
|---|---|---|
| STUDENT | every registration (added at sign-up) | none: uses the site, not the admin |
| TEACHER | teachers whose `TeacherProfile` staff verified | none yet |
| CONTENT_EDITOR | prepares papers, pages, the catalogue and the course | view/add/change books, papers, questions, solutions; view boards, classes, subjects; view/change legal pages; view/add/change products; view/add/change/delete categories, collections and their items, product types, attributes and their values, product images and bundle items; view slug history; view/add/change/delete the course's chapters, revisions, clips, flash cards and quiz items |
| SALES | runs the shop | view books; view/add/change products, coupons, shipping rates, orders (staff orders; the cancel and payment link actions: cancelling an order paid online is its refund, within its ₹2,000 limit, FINANCE approving above it), order notes; view/add/change/delete product images, bundle items and offers; view/add payments (a payment received offline); view/change reviews and quotation requests; view shipments, refunds, order items, discounts, invoices, credit notes, stock alerts, addresses and the catalogue structure. It does not pack, ship or refund in the admin: refunds it asks for in the panel (FINANCE approves those above its limit), packing is PACKER's |
| SUPPORT | helps students and customers | view users, email addresses, attempts, consent records, deletion requests, the SMS log; view/change teacher profiles (verifies teachers); view/delete email suppressions; view orders and everything on them (items, discounts, notes, payments, shipments, refunds, invoices, credit notes), products, addresses, reviews, quotation requests, stock alerts; view/add/change course entitlements; view book codes |
| ADMIN | runs the site | every permission, except that periodic tasks, task results, groups and permissions, second factors and the Google sign-in apps are the superusers' (ADMIN may view them), the owners' own (giving roles and making API keys, which ADMIN sees; the override; the audit log) and money's approvals (FINANCE's); approves roles, staff second factors, erasures and exports; packs and ships in the admin (`staff.pack_order`); imports and exports are ADMIN only |
| OWNER | the founder; the superuser flag is only on the sealed break-glass accounts | every catalogued permission: all but the changes to periodic tasks, groups, second factors and the Google sign-in apps, which stay the superusers' |
| FINANCE, PACKER, REVIEWER, MARKETING, AUDITOR, SALES_REP | the Admin Control Panel's roles | money and tax documents, approving refunds, offline payments, prices and coupons above the limits; the packing queue only; publishing content; coupons and reviews; everything read-only with the audit log; school orders and quotations: `accounts/roles.py`, `staff/README.md` |

The roles of the panel (`staff/`, the plan's 4.1) come with limits (`ROLE_LIMITS`: a refund, an offline payment, a
discount or an export above them waits for a second person), scopes (`ROLE_SCOPES`, `StaffScope`: a subject, an order
status, a school …) and separation of duties (`SOD_CONFLICTS`); every permission is labelled in
`staff/catalogue.py`. CONTENT_EDITOR, SALES and SUPPORT keep their permissions and gain the panel's (SUPPORT reveals
masked contacts, unlocks accounts, handles data requests …). The newer roles do not open the Django admin: they work
through the staff API, whose lists are scoped.

`user.is_student`, `is_teacher`, `is_editor`, `is_sales`, `is_support`, `is_admin` (ADMIN or superuser), `is_owner`
(OWNER or superuser) and `user.has_role(name)` read the groups. In the admin, Users has actions "Give role …" and
"Take away role …" (only for those who may change groups); giving a staff role also sets `is_staff`, and taking away
the last of them clears it. Teacher profiles have "Verify" (adds TEACHER, records who and when) and "Revoke". Only a
superuser changes a superuser's account or gives roles in the admin; in the panel (`people/`) an owner gives them, a
privileged one with a second person's approval, with an audit trail. A superuser is a break-glass account: its log-in
alerts the owners and each of its audit events is marked (`staff/README.md`, RUNBOOK.md "Break-glass accounts").

## Personal data (DPDP Act)

- **Consent records:** `ConsentRecord` (event given/withdrawn, purpose, privacy-policy version, by a parent or not, how:
  ticked on the form or confirmed through the link emailed or texted to the parent, time, HMAC of the client's IP
  address, keyed with `SECRET_KEY`). Sign-up records one; asking for deletion records a withdrawal and cancelling it a
  new consent. Read-only in the admin, exportable as CSV.
- **Download my data:** `/account/data/` returns the profile (with the log-in number and the roles), email addresses,
  passkeys and authenticators, Google accounts, teacher profile, attempts, answer sheets, consent records, deletion
  requests, saved addresses, the cart and orders (items, address copy, shipments, payments, refunds, the status
  timeline, and the invoice and credit notes by number: the PDFs stay on the order pages), reviews, quotation requests
  and stock alerts (by email address), the staff's notes on the orders, the texts sent to the account (kind, status,
  last four digits) and whether its address is suppressed after bounces, the signed-in devices (address, browser, first
  and last seen; allauth.usersessions, without the session keys), and the revision course's data (settings,
  entitlements, redeemed book codes, progress, quiz answers, flash card reviews, devices without their IDs) as JSON,
  after allauth's re-authentication (password, if none was entered in the last five minutes). The API's `me/export/`
  gives the same file (the password, or a log-in or re-authentication of the session in the last five minutes, which
  is the way for an account without a password).
- **Delete my account:** a `DeletionRequest` due seven days later (`accounts.views.request_deletion` and `keep_account`,
  used by the website and the API alike); the student gets an email, can log in and cancel until then; the daily purge
  (`accounts.tasks.purge_due_deletions`) anonymises the user row (name, email, phones, date of birth, district and
  parent data cleared; the notes on attempts cleared; roles and permissions removed; the account made inactive;
  answer-sheet photos, email addresses, passkeys and authenticators, Google accounts, teacher profile, the nominee,
  failed log-ins and the signed-in devices deleted; the SMS log's rows kept their year as processing logs without the
  account or the last digits; consent records kept as proof without the address hash; admin log entries of the user,
  teacher profile, attempts, answer sheets and addresses renamed; password unusable, so every session ends), deletes the
  saved addresses, the cart, the reviews, the course data (progress, quiz answers, card reviews, settings, devices,
  entitlements) and the "email me when it is back" requests for the old address, and emails a confirmation to the old
  address. The marks stay as anonymous statistics; orders and invoices stay (tax records) with their copy of the
  address, on the anonymised user. Quotation requests made with the address are not erased: staff delete them on request
  (RUNBOOK.md "A data request under the DPDP Act"). The erasure obeys its holds (staff/README.md "Legal and privacy"):
  a legal hold on the account, or a student under 18 whose parent has not confirmed through their link, keeps it
  waiting; with `SUPPORT_INTERMEDIARY_RULES` on, the registration details stay 180 days more. The deletion request stays
  as the erasure ledger, copied to the backups' bucket, which `manage.py reapply_erasures` applies again after a
  restore.
- **Legal and privacy** (the panel's module, staff/README.md): the compliance cockpit with every legal clock, legal
  holds, the retention schedule in code (`examleaf/retention.py`, its clean-up nightly), the legal pages' numbered
  versions with their days in force and diffs, the e-commerce disclosures (shown by the website's footer and contact
  page), the yearly dark-pattern self-audit and its certificate, nominees (`me/nominee/`), marketing consent withdrawn
  as easily as given (`me/consent/withdraw/`), and the one audience function for marketing
  (`accounts.audiences.marketable`: never anyone under 18).
- **Changing the email address:** allauth's `ACCOUNT_CHANGE_EMAIL` keeps one address; a new one replaces it only after
  the emailed code is confirmed, after re-authentication, and the old address is notified.
- **Mobile numbers and SMS:** the SMS log holds a keyed hash and the last four digits, never the number; the last
  digits are blanked after 90 days and the rows deleted after a year (processing logs, `examleaf/retention.py`); an
  erased account's rows stay their year without the account.
- **Insights:** aggregates only (DPDP Act s. 9(3) forbids tracking or behavioural monitoring of children): no insights
  row points to an account or a learner (a test checks it), groups of learners under 5 show their size only, and
  nothing there feeds marketing, prices or offers. The fraud rules count accounts, IP addresses, phone numbers,
  addresses and book codes by keyed hashes (`INSIGHTS_HASH_SALT`), and keep each book code tried in the app for 180
  days as hashes, its batch and its outcome. A quiz answer keeps the multiple-choice option chosen (for the item
  analysis), which Download my data lists with the other answers.
- **Logs:** the application adds no personal data by design (no logs of good log-ins; Celery's task arguments, which
  hold email texts, are left out of the JSON log lines). The exceptions: django-axes logs each failed log-in and
  lock-out with the email or number as typed, the client address and the browser, and Caddy's access log holds client
  addresses, browsers and URLs (an order link's token too); Docker keeps both in rotated files (DEPLOYMENT.md section
  10). Sentry runs with `send_default_pii=False` (no cookies, users or client addresses) and `examleaf/sentry.py`'s
  `before_send`, which replaces, anywhere in an event (request body, headers, breadcrumbs, extra), passwords, codes,
  verification and JWT tokens, SMS variables, Razorpay signatures, emails, names, address and card- or phone-like
  fields, and card numbers, Indian mobile numbers and email addresses inside any text, with `[Filtered]`; stack-frame
  variables are not sent, and an email's text is replaced whole.
- **Retention:** orders never paid or placed lose the customer's details 30 days after they were cancelled; invoiced
  orders keep them eight years (RUNBOOK.md "Purging old orders"); a Razorpay payment keeps only the fields it needs for
  180 days. Also: "email me when it is back" requests go after 365 days, guest carts after 30 days idle, Razorpay's
  webhook records and the Celery task results after 7 days, the SMS log's last digits after 90 days and its rows after a
  year, the app's phones silent for 90 days, a signed-in device's address and browser the night after its session
  ended, local database dumps after `BACKUP_KEEP_DAYS` (30), and Docker keeps 50 MB in 10 files of logs per service.
  The whole schedule, with each minimum in law: `examleaf/retention.py` (the panel's Legal and privacy, Retention).

## Admin

django-admin-interface gives the admin ExamLeaf's colours and name (the theme is set by migrations, the first
`ops/migrations/0001_admin_theme.py`; the related-object pop-up stays a window because the CSP forbids frames). Log-in
is the site's own (allauth: the emailed code confirms the address the first time, then staff need their second factor).
The index page (`templates/admin/dashboard.html`, set as `admin.site.index_template`; the shop's numbers extend it in
`templates/shop/admin/index.html`) shows registrations, registrations with a confirmed email and saved attempts today
and in the last 30 days, the teacher requests and account deletions waiting, how many legal pages still hold a
[placeholder] (the Pages list counts them for each page; on the site they are marked yellow), and, for those who may
view orders, the shop: orders and revenue today and in 30 days (revenue net of refunds), orders to pack, parcels on the
way, reviews and quotation requests waiting, sales by day for two weeks, the books sold most and the books running out.

The sections: Accounts (Users, Teacher profiles, Consent records, Deletion requests, Email addresses), Content (boards,
class levels, subjects, books, papers, questions, solutions), Practice (Attempts, Answer sheet uploads), Pages, Shop
(see "Shop"), Revision course (see there), Insights (see there: read-only but for the exam seasons and print costs,
each forecast run with a summary of its numbers, an action to acknowledge fraud signals), Ops (SMS log, Email
suppressions), MFA (Authenticators), Authentication and
Authorization (Groups), Periodic Tasks, Celery Results, and the libraries' own: Admin Interface (Themes), Axes, Social
Accounts, Tags and Token Blacklist. Books, papers, questions, solutions, legal pages, orders and reviews have a History
button (django-simple-history); payments and order notes keep a history in the database that the admin does not show.
Exports are CSV (django-import-export; orders, products and categories also XLSX), need an `export_…` permission that
only ADMIN holds, leave out dates of birth and parents' contacts, escape a cell that starts with `=`, and are written to
the admin log; imports of products and categories need `import_…` permissions, also ADMIN only.

## REST API

`/api/v1/`, for the app. The guide is [API.md](API.md): authentication from the app, token lifetimes, a table of every
endpoint, request and answer examples, the error format, rate limits and the versioning policy. OpenAPI schema at
`/api/schema/`, Swagger UI at `/api/docs/`, Redoc at `/api/redoc/` (both served by the site, so the CSP stays strict).

- Code in `api/` (`auth.py` sign-up and log-in, `views.py` the catalogue and the account, `shop.py`, `learn.py`,
  `serializers.py`, `schema.py` the OpenAPI tags), settings in `examleaf/api_settings.py` (imported by `settings.py`
  before its revision-course and store sections), URLs in `examleaf/api_urls.py` and `api/urls.py`.
- JWT for the app (15-minute access, 30-day refresh, rotated, blacklisted on log-out, all ended by a password change, a
  reset or the deletion purge); the session for the site's own pages. Log-in, log-out, refresh and passwords are
  dj-rest-auth's; sign-up, the email code and the code by SMS run on `accounts.forms.SignupForm` and allauth's code
  flows, so the parent and consent rules, the STUDENT role, the consent record and the emails are the website's. A
  password or an SMS code alone gives no tokens to staff, nor to an account with a second step (an authenticator app or
  a passkey): those log in through allauth.headless, which asks for it. The app can also sign in through
  allauth.headless (`/_allauth/app/v1/…`: codes, passkey, Google, a second step) and trade that session for the JWT pair
  at `auth/exchange/`; a web frontend on the same origin uses `/_allauth/browser/v1/…` with the session cookie and
  `X-CSRFToken`. The sign-up is the website's form in all of them (`accounts/signup.py`: student details, consent,
  Turnstile). `GET config/` tells a frontend what the server has switched on; API.md has the "Frontend integration
  guide".
- The catalogue is public, read-only and cached for 15 minutes; solutions (unless open, `SOLUTIONS_REQUIRE_LOGIN=0`) and
  attempts need a confirmed email address; Download my data and Delete my account reuse the website's functions and ask
  for the password; teacher access (`me/teacher/`), the parent's link again (`me/parent-consent/`) and the legal pages
  (`pages/`) are there too.
- The shop (`api/shop.py`): products with their categories and attributes, categories and collections (public), the
  delivery rates and a quote by PIN code (`shipping/`), and for a confirmed account the cart, saved addresses and orders:
  checkout, payment with Razorpay's mobile SDK (`orders/<number>/payment/` gives the SDK its options,
  `…/payment/confirm/` checks the signature), cancellation, the invoice and credit note PDFs. Visitors have a guest cart
  (the session cookie with the CSRF token, or `X-Cart-Token` from `POST cart/`), check out as guests with an address
  typed in and pay through the order's link (`orders/t/<token>/payment/`); the guest cart joins the account's at
  log-in. Guests ask for an order's link by number and email (its own rate limit), and the link in an order's email
  opens it (`orders/t/<token>/`); the contact form is `contact/`; reviews, "email me when it is back" and school quotations
  (`quotes/`) work as on the website. Everything runs through `shop.services`, `shop.cart` and `shop.payments`, and the
  Razorpay webhook stays `/shop/webhooks/razorpay/`.
- The revision course (`api/learn.py`): chapters (public), clips, progress, the quiz, flash cards, the plan, book
  codes, entitlements, settings and the app's devices.
- The insights (`insights/api.py`, `staff.view_insights`, on the admin host): the newest rows of each predictive job,
  each answer with its method, data time, last backtest and whether the method beats the seasonal naive (API.md,
  "Insights (staff)").
- JSON only; page-number pagination (50, at most 200), filters, search and ordering; DRF's error format (a JSON 404
  for unknown `/api/` paths); throttles counted in the cache; CORS only for `CORS_ALLOWED_ORIGINS` and only on `/api/`;
  `X-Request-ID` as on the site. Beat deletes expired refresh tokens daily (`api.tasks.flush_expired_tokens`).

## Shop

The printed books, sold online across India, and the store around them: `shop/` (models; `services.py`, every flow;
`payments.py`, Razorpay; `cart.py`; `tasks.py`; `invoices.py`), its API in `api/shop.py`; templates only for the
emails (`templates/shop/email/`), the PDFs (`templates/shop/invoice.html` …) and the admin (`templates/shop/admin/`).
The staff side, the Admin Control Panel's Orders module (`staff_orders.py`, `order_jobs.py`), its Tax module
(`staff_tax.py`) and its Finance module (`staff_finance.py`, `settlements.py`), is described in
[shop/README.md](shop/README.md).

### Set up

```sh
.venv/bin/python manage.py seed_shop --stock 50   # the 8 books, the Physics bundle, coupon WELCOME10, 3 shipping rates
```

- `seed_shop` is idempotent and never overwrites what the admin changed. Its prices are placeholders (Sample Papers
  ₹299, Solutions ₹249, bundle ₹499), ISBN blank, stock 0 without `--stock`. The Sample Papers and the bundle get the
  covers from `static/img/`; Solutions get none (those images are the Sample Papers' covers) until one is uploaded.
- Razorpay (`.env`; steps in DEPLOYMENT.md section 12): `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` (test keys
  `rzp_test_…` until going live; the payment page then says "Test mode"), and the webhook secrets
  `RAZORPAY_WEBHOOK_SECRET_TEST` and `RAZORPAY_WEBHOOK_SECRET` for `https://<domain>/shop/webhooks/razorpay/` (events
  `payment.captured`, `payment.failed`, `order.paid`, `payment_link.paid`, `refund.processed`, `refund.failed`; the secret
  of the keys' mode is checked). Without keys the payment page says online payment is not set up; without the secret
  every webhook is refused. Payments and orders record their keys' mode: once live, test orders are marked TEST and
  change nothing (RUNBOOK.md "Test mode and live mode"). `SHOP_OPEN=0` leaves the cart, checkout and payment to staff
  ("Shop opens soon"), for Razorpay's review. In development the return from Checkout is enough to complete an order;
  to try webhooks, expose the port (e.g. `ngrok http 8000`) and point a test-mode webhook at it.
- `SHOP_COD_ENABLED=1` offers cash on delivery, to accounts with a confirmed email address only: two orders on their
  way per account, each worth at most `SHOP_COD_MAX_VALUE` rupees (1500). The seller printed on invoices is
  `SELLER_LEGAL_NAME`, `SELLER_ADDRESS`, `SELLER_GSTIN` (empty: "not registered"), `SELLER_STATE` (two letters: the same
  state as the buyer = CGST + SGST, otherwise IGST), `SELLER_STATE_CODE`, `SELLER_EMAIL`, `SELLER_PHONE`.
- Invoice PDFs are made by WeasyPrint, which needs Pango: `brew install pango` on a Mac; the Dockerfile installs it
  with the DejaVu fonts (₹ sign) and the Noto fonts (a name or address typed in Assamese, Bengali or Devanagari prints
  on the invoice instead of empty boxes).

### How it works

- **Money**: django-money, INR. `cart.totals` is the one place money is added up, from today's prices, on the cart
  page, at checkout and when the order is made; per-cent discounts round half up to the paisa; Razorpay gets paise.
- **Checkout**: log in (saved addresses) or a guest email; the address needs a state from the list, a 6-digit PIN code
  and a 10-digit Indian mobile number (django-localflavor, django-phonenumber-field). Once the PIN directory is loaded,
  the form fills in the district (when empty) and the state (when the PIN lies in one state) from the PIN code and
  refuses a state that is not one of the PIN's (a border PIN can have two); a PIN missing from the directory is neither
  filled in nor checked (the state decides CGST + SGST or IGST). A pending order is made with a copy of the address and
  of each book's title, HSN, GST rate, price and share of the discounts; the review-and-pay page shows the total.
- **Payment**: the Razorpay order is created server-side for the order's total (on the payment page; Razorpay
  unreachable: a friendly message, the order stays pending, "Try again"). Checkout's answer is posted back, its
  signature checked by the SDK, the payment fetched and, if only authorized, captured: the order is paid. The webhooks
  do the same, so a lost redirect still completes the order; repeats and either order of arrival change nothing (row
  locks and the state machines). Each webhook is recorded (`WebhookEvent`: Razorpay's event id and the hash of the
  signed body) and handled once, in one transaction with what it changes; a replay, even under another event id, is
  acknowledged and ignored, and events signed more than seven days ago are not handled. A payment that cannot pay its
  order (cancelled meanwhile, sold out, a coupon or an offer whose last use went to another order, wrong amount) is
  refunded automatically. A refund made in the Razorpay dashboard is recorded from its webhook (the order, the
  customer's email and the credit note follow). A customer who paid and never came back, with a lost webhook, is not
  left charged without an order: before the daily clean-up cancels an order never paid (two days; staff orders 16) it
  asks Razorpay (`payments.reconcile`; a Razorpay that cannot be asked leaves the order for the next run, and
  `manage.py reconcile_payments` does the same by hand, RUNBOOK.md). Cash on delivery: "place order"; the courier's cash
  captures the payment at delivery.
- **Stock** is taken on payment (cash on delivery: when placed) under `select_for_update`, in product-id order, and
  checked first, so the last copy sells once; it goes back on cancellation. A bundle sells its books' copies; a digital
  product has no stock.
- **States** (django-fsm-2, guarded transitions, `status` writable only through them): order pending → paid → packed →
  shipped → delivered, cancelled (pending or paid by the customer, packed by staff) and refunded (a cash-on-delivery
  order goes from pending straight to packed; an order of digital products only from paid to delivered); payment created
  → authorized → captured, failed or refunded. django-simple-history keeps every change: the customer's timeline.
- **Customers**: emails for confirmation, shipping (courier, tracking number and link), payment links, delivery,
  cancellation and refund (`shop.services.notify`: the first three have a drawn HTML part, the others are text with an
  HTML part made from it; all go through `ops.tasks.queue_email`), and SMS for those who asked for them. Saved addresses
  in My account (add, change, delete, the default one). My orders: timeline, tracking, invoice and credit note
  downloads, Cancel while pending or paid (refund through Razorpay by a Celery task, retried for hours while Razorpay is
  down; a refusal shows as a failed refund in the admin). Guests find an order by number and email (10 tries an hour per
  address, per email address and per order number). The guest cart joins the account's cart at log-in.
- **Invoices**: numbered in their series per financial year under the series' lock (`EL/2026-27/00001`, 16
  characters at most; from FY 2027-28 one series a type, `TI`, `BS`, `IB`: `shop/README.md` "Tax"), made by a task
  when the order is paid (cash on delivery: when shipped), retried on failure; the link appears once the PDF exists.
  A bill of supply when no line is taxed (books, HSN 4901), a tax invoice when every line is, an invoice-cum-bill of
  supply for both (Rule 46A), with each line's code and rate as the HSN and SAC master gave them on the day of the
  order, taxable value and CGST + SGST or IGST by the order's billing state; prices include tax; the coupon, the offers
  and a staff discount are shared out over the lines (`OrderItem.discount`); the shipping follows the goods it carries
  (exempt with books); a bundle sold split shows its components; goods carry three copies; an invoice paid offline
  prints the bank or UPI reference. A cancelled one keeps its number.
- **Credit notes**: a refund of an invoiced order, in full or in part, gets a credit note (`CN/2026-27/00001`, its own
  series per financial year; `T/…` and `TC/…` with test keys), made by a task once Razorpay has refunded (or once the
  invoice is made, when the refund came first). No invoice or credit note of the real series is numbered while a
  `SELLER_*` setting still holds a [placeholder] (the task is retried; the numbers cannot be reissued). It credits the
  books first, over the invoice's lines in proportion, then the shipping with what is left (a refused parcel refunded
  less the shipping credits the books only), reversing each part's GST at the invoice's rates and place of supply.
  None after 30 November following the invoice's financial year, nor against a cancelled invoice: the refund goes out
  regardless and FINANCE's inbox says which note is missing. Linked next to the invoice in My orders, the API and the
  admin (order page, Credit notes).
- **Coupons**: per cent or rupees off, minimum order, dates, a total and a per-customer limit (by account and by
  email), any case. A use is a paid (or placed cash-on-delivery) order not cancelled or refunded. The limits are checked
  when the order is made and again, under a lock on the coupon, when it is paid or placed (`services.claim_coupon`):
  orders awaiting payment are not uses, so the first to be paid or placed gets the last one; the other is not placed
  (cash on delivery: back to the cart with a message) or its payment is refunded, with an email saying why.
- **Offers**: automatic discounts, no code (per cent or rupees; on the cart, chosen products, categories or collections;
  a minimum of copies or value; dates; limits in all and per customer; combinable with coupons and other offers or
  alone). They apply after the coupon, show as their own lines in the cart, the checkout, the emails, the order, the
  invoice and the API (`savings`), and each order line keeps its share, which invoices and credit notes print; orders
  made before offers existed keep the split they were invoiced with. The usage limits are checked when the order is made
  and again, under a lock on each offer, when it is paid or placed (`services.claim_offers`, as for coupons): the order
  that comes second is refused or its payment refunded, with an email saying why.
- **Catalogue**: categories in a tree (django-treebeard; a category's page lists its sub-categories' books too),
  products on several shelves, hand-picked collections in the staff's order, product types with attributes (text,
  number, one of a list, yes or no; values checked by kind; shown under "Details" and filterable in the API), related
  books ("You may also need"), SEO fields per product, and a renamed product's old address redirecting (301). The
  address words `category`, `collection` and `school-orders` are reserved.
- **Digital products**: the kind "Digital (in the app)", alone or in a bundle with a book, opens the revision course in
  the buyer's account once paid (`learn.services.grant_for_order`). No stock, shipping or cash on delivery; one per
  order; an account is needed. An order of digital products only (a bundle of digital products counts) is delivered at
  once; cancelling a paid order, or refunding it in full, closes the course again, a part refund does not. The product
  form refuses the books' HSN code 4901 for it.
- **Staff orders**: "Add order" in the admin for a phone or school order: offers, a staff discount, shipping typed or
  from the rates, a note. A Razorpay Payment Link (valid 15 days) is emailed by us and completed by the
  `payment_link.paid` webhook (or by the clean-up's check of the link); or a payment received offline (NEFT, IMPS,
  UPI) is recorded with its reference, which the invoice prints. Internal order notes keep their history. A staff
  order not paid in 16 days is cancelled by the daily clean-up.
- **Shipping**: a flat fee per group of states (one rate without states covers the rest), free from an order value
  (after the discount). Shipments name a courier (India Post, Delhivery, Blue Dart, Ekart, DTDC, Xpressbees, other);
  an empty tracking link is filled with the courier's tracking page (17TRACK for those without one). Parcels can also be
  booked with a courier through Shiprocket (`shipping/README.md`): quote, AWB, label, pickup and manifest, the
  courier's scans (its webhook and a poll) shipping and delivering the order, failed deliveries, returns, COD
  remittances, the statement's charges and weight disputes, on the `integrations` framework (`integrations/README.md`:
  encrypted credentials, a call log, a circuit breaker, dead letters).
- **Buyers' reviews**: stars and up to 1,000 characters, only from accounts with a delivered order of the book, one
  each, approved by staff, shown as "Verified buyer" (no names: many buyers are minors); the star rating goes into the
  JSON-LD only from approved reviews.
- **School and bulk orders**: `/shop/school-orders/` (books only: a course opens in one account, so a school's pupils
  get book codes instead; GSTIN checked, Turnstile when on) emails SALES; staff make a quotation PDF (valid 15 days,
  kept in the private storage) and enter the order as a staff order when it is accepted.
- **Stock alerts and the low-stock email**: "email me when it is back" (for signed-in accounts, to their own address;
  one email, then the row goes) and a morning email to SALES of the books below `SHOP_LOW_STOCK`.
- **GST returns**: the panel's Tax module (or `manage.py export_gstr1`) writes the month's or the quarter's GSTR-1
  files in the Offline Tool's templates for the accountant; the tax calendar and the threshold monitor say what is due.
- **Admin** (Shop): products, categories (a tree: drag a row to move it), collections, product types, coupons, offers,
  shipping rates; orders with filters and search (number, email, name, phone, tracking number) and the actions Mark
  packed, Mark shipped (courier and tracking number per order), Mark delivered, Cancel, Refund (in full, which cancels
  an order not yet shipped; shipped or delivered orders also by an amount, e.g. a refused parcel less shipping), Email a
  Razorpay payment link, Record a payment received offline and "Add order"; a customer page; reviews, quotation
  requests, stock alerts; bulk Put on sale, Take off sale and Set stock; imports and exports (ADMIN); payments, refunds,
  invoices and credit notes read-only. The shop's numbers are on the admin index. A product's pictures over 2 MB are
  refused, and saving a product page that was open while customers bought keeps the copies left (only a stock typed on
  purpose is set).
- **Security**: Razorpay's script, frames and API calls are allowed by the CSP on the payment page only, with
  `Cross-Origin-Opener-Policy: same-origin-allow-popups` for the banks' windows; the webhook is CSRF-exempt but signed
  and rate-limited; order pages are visible to their account, to the browser session that placed the order, or by the
  secret link in the order's emails; invoices to those and to staff with `shop.view_invoice` (credit notes:
  `shop.view_creditnote`). Product pictures are served by `/shop/media/…` only (without buckets) for files in
  `products/` and `og/`.

## Revision course

For the mobile app, through the REST API ([API.md](API.md) "Revision course"); `learn/`, `api/learn.py`. The app is a
separate project.

- **Content.** `Chapter` (subject, number, title, the Board's marks, how many questions the Board asked on it in past
  papers, a must-do note), one `Revision` per chapter (a target length, 12 minutes by default; draft or published), its
  `Clip`s (concept, trick, shortcut, formula, question pattern, common mistake, previous-year question; a video; notes
  in Markdown; linked Board questions; tags), `FlashCard`s and one-mark `QuizItem`s (multiple choice, true or false,
  fill in the blank). Editors work in the admin under Revision course.
- **Video.** An editor uploads a clip's video in the admin (at most `LEARN_MAX_UPLOAD_MB`; mp4, mov, m4v, webm or mkv,
  with H.264, HEVC, VP9 or AV1 video and AAC, Opus or MP3 sound: ffprobe checks this before ffmpeg runs, and anything
  else fails at once). With the private bucket set, the browser sends the video straight to the bucket on a link the
  site signs for 15 minutes, so it never goes through Caddy or gunicorn (the bucket needs a CORS rule that allows PUT:
  DEPLOYMENT.md section 17); without a bucket (development) it comes with the form. The `media-worker` makes it into HLS
  with ffmpeg: two vertical renditions (480×854 at about 700 kbps, 720×1280 at about 1.5 Mbps), AAC sound, 4-second
  segments, a poster. The files stay in the private storage and the app gets links signed for 10 minutes
  (`LEARN_PUBLIC_VIDEO=1`: the public storage). `/learn/preview/<clip>/` is the staff player (hls.js, served by the
  site).
- **Data.** `import_chapter_insights` fills the 51 chapters with the Board's marks (from `format.json`) and past-paper
  question counts (from `pyq/`); `build_quiz_items` makes 664 quiz items from the imported one-mark questions that parse
  unambiguously.
- **Access.** Entitlements per subject or for all, from a book code or a purchase of the digital product (each for a
  year, `LEARN_ACCESS_DAYS`), or a staff grant (until the day staff type, or no end). Book codes are 12 characters,
  printed in the books (`make_book_codes`), kept only as a keyed hash (`LEARN_CODE_SECRET`, required on a server),
  redeemed once, 5 tries an hour. Free for any signed-in student (`LEARN_FREE_PREVIEW`): the first clip of every
  revision, any clip an editor marked as a free preview, and the flash cards of each subject's first chapter; the quiz
  is for entitled students only. Staff see everything. While a parent's confirmation is awaited
  (`PARENTAL_CONSENT_MODE=verified`), nothing is saved: no progress, answer, card review, code, setting or device.
- **Study aids.** Progress per clip; quiz answers checked on the server; flash cards ("I knew it" or not); a pass plan
  (`learn/plan/`): from today to the exam, the unwatched clips packed into the student's minutes a day, chapters by
  Board marks × past-paper questions × weakness, and the "minimum to pass" (the chapters with the most marks per minute
  until they are worth 1.5 times the pass marks); "revise again" brings a wrong answer back after 1, 3 and 7 days. An
  account saves at most 1,000 quiz answers and 1,000 card reviews a day and keeps its 5 newest devices.
- **Reminders.** A daily push at 18:00 through Firebase Cloud Messaging (firebase-admin), to students who turned it on,
  only with `FCM_SERVICE_ACCOUNT_JSON`; addressed to the app's Firebase installation ID.
- **Privacy.** Progress, quiz answers, card reviews, settings, entitlements and devices are in Download my data and go
  with the account; no video analytics.

## Web platform

- **Pictures and storage.** A product's cover and pictures are saved with AVIF and WebP sizes (django-pictures, queued
  after the save and made by the worker, or in the request when the broker is down) and given by the API for the
  website's `<picture>`; the four book covers have copies committed in `static/img/` (`build_covers`). Two S3-compatible buckets
  through django-storages (Cloudflare R2 is the pick; AWS S3 Mumbai may hold the private one): the private one for
  invoices, credit notes, quotations, answer sheets and the course's videos (links signed for 5 minutes; the course's
  videos for 10), the public one for product pictures and link-preview pictures on `PUBLIC_MEDIA_DOMAIN` (cached a year,
  immutable). Without `MEDIA_BUCKET` both are the `media/` folder and the public files are served under `/shop/media/`.
- **Link previews.** A link-preview picture per product (1200×630, made on save by the worker), with the product's
  search-engine title and description, in the API (`og_image`, `meta_title`, `meta_description`); the website writes
  the tags, JSON-LD, the sitemap and `robots.txt`, and is the installable web app.
- **Fonts and scripts.** Poppins and Hind Siliguri (OFL, in `static/fonts/`) for the invoice and quotation PDFs, hls.js
  1.7.3 for the staff player (`static/learn/`, with its licence); the website has its own copies of the fonts and of
  KaTeX.

## Insights

The predictive jobs of the Admin Control Panel, in `insights/` ([insights/README.md](insights/README.md): each job's
inputs, method, output and how to read it, the monthly review, when a method graduates). At night, one Celery task
each: the demand forecast per title and week (seasonal naive by week of the season × a damped growth factor, P10 to
P90, split top-down by district) and its backtest against the seasonal naive (WAPE, seasonal MASE; a method that does
not beat it is not shown), the print-run advice (the newsvendor's quantile at Cu ÷ (Cu + Co), the reprint trigger,
weeks of cover, leftovers), the quiz's item analysis (p, point-biserial, TIMSS's flags, once 30 learners answered),
cohorts, book codes per batch and district, transit days per courier and district, what coupons and offers did (an
interval, never a winner) and the fraud rules (failed book codes, resale, shared codes, shared phones and addresses)
with an email of the night's signals. Rules for COD return risk and for school and distributor scores wait for their
data (the shipping app's parcel outcomes, ERPNext's accounts). Staff enter the exam seasons and the print costs in the
admin (Insights); every other table there is read-only, and staff read the same rows at `/api/v1/insights/`. No
library beyond Python's own; no row points to an account, and learner numbers come in groups of 5 or more (DPDP Act s.
9(3)).
Since Phase B the panel's Home and reports are built on the same package: one definition per number
(`insights/metrics.py`), the reports (`insights/reports.py`), the minimum cell (`insights/cells.py`: districts, PIN
codes, states and cohorts under `INSIGHTS_MIN_CELL`, 10; a chapter's or a class's learners under
`INSIGHTS_MIN_CELL_CLASS`, 5) and their export as a job (`insights/exports.py`).

## Tests

```sh
make test                                 # pytest: 831 tests (imports all four subjects once)
make cov                                  # the same with a coverage report
make lint                                 # ruff, as in CI
make check                                # manage.py check and missing migrations
```

pytest with pytest-django runs the old Django `TestCase` classes and the newer pytest functions (factories in
`accounts/factories.py` and `shop/factories.py`, factory_boy); `manage.py test` still runs the `TestCase` classes. Every
test module passes on its own and in any order, on SQLite and PostgreSQL (no test relies on ids or on rows made by
another); six tests run threads against PostgreSQL (the last copy, a coupon's last use, a webhook and the return page,
two clicks on Add to cart, a book code redeemed by two students and by one student twice, each at the very same instant)
and are skipped on SQLite. The tests keep off the network: in the shop's tests `shop/conftest.py` makes any real
`requests` call fail and Razorpay's calls are mocked while signatures are checked for real; MSG91, Turnstile and Pwned
Passwords are replaced in the tests that touch them. Invoice PDFs are a stand-in unless a test is marked `real_pdf`, and
the tests that need Pango or ffmpeg are skipped without them.

CI (`.github/workflows/ci.yml` at the repository root) runs on every push and pull request that touches the site, the
papers or the workflow: job `test` (ruff, the migration check, the tests with coverage on PostgreSQL 17), job
`docker-build` (builds the Docker image; Django's `check --deploy --fail-level ERROR` and WeasyPrint must load in it;
nothing is pushed) and job `dependency-audit` (pip-audit on the pinned packages, reported, not yet blocking). The
workflow can only read the repository (`permissions: contents: read`). Dependabot (`.github/dependabot.yml`) opens
weekly pull requests for the pip requirements and the GitHub Actions.

What the test modules cover:

- **accounts/** (the website's sign-in through allauth.headless, the account pages through the API): `tests.py`
  sign-up (parent details and consent under 18, none kept for adults) and django-axes;
  `test_roles.py` role permissions, `bootstrap_roles`, the admin's role actions, teacher requests; `test_privacy.py` and
  `test_export_and_signup.py` Download my data, deletion and the purge, email change, an existing address signing up,
  double clicks; `test_security.py` staff second factor, 8-hour sessions, exports for ADMIN only, password rules, marks
  waiting for a parent's consent; `test_phone.py` mobile numbers, log-in by SMS code, limits; `test_passkeys.py`;
  `test_google.py` the redirect to Google and its callback through headless (Google mocked); `test_parent_sms.py`;
  `test_turnstile.py`; `test_codes.py` codes per address and day, three tries a code also when they come together; `test_parent_link.py` the parent's link with hostile input, its limits and when it
  goes; `test_review_lows.py` API log-ins of staff and of accounts with a second step, staff passkeys, notices when a
  number moves, deletion and Download my data.
- **api/**: `tests.py` the public catalogue, the solutions gate, sign-up and the JWT cycle, attempts, the profile, data
  rights, throttles, body limits, CORS, request IDs, the OpenAPI schema; `test_phone.py` log-in by SMS code;
  `test_security.py` limits per account, wrong passwords, sort fields, cache keys; `test_headless.py` allauth.headless
  under the site's rules and the exchange for the JWT pair; `test_contract.py` `config/`, the legal pages, teacher
  access, the parent's link again, SMS updates.
- **content/, pages/**: `content/tests.py` the import of the four subjects (30 papers each, every solution matched,
  re-import changes nothing), the Markdown renderer, the QR code and who reads the solutions, `export_qr`;
  `content/test_emails.py` every email's HTML part; `pages/tests.py` the legal pages, their history and placeholders
  (attempts and My record: `api/tests.py`).
- **learn/**: `tests.py` answers by kind, publishing, the admin pages; `test_access.py` entitlements, free previews,
  book codes, digital products opening and closing the course; `test_api.py` the course endpoints, locks, signed links,
  quiz, plan, redeeming and its limits, devices; `test_imports.py` chapter insights and quiz items; `test_media.py` the
  ffmpeg pipeline (mocked, plus one real run); `test_plan.py` plan order and repetition; `test_preview.py` the staff
  player; `test_privacy.py` export and deletion of the course data; `test_uploads.py` the direct upload of clip videos
  to the bucket (the signed link, the form, the CSP, the large-body guard); `test_review_lows.py` the book codes' key,
  what one account may add, the reminder's batches, revise-again within what is open.
- **insights/tests/** (helpers in `helpers.py`, three exam seasons in `conftest.py`): `test_stats.py` the arithmetic
  against numbers worked out by hand (the growth factor and its damping, a backtest's WAPE and MASE, the newsvendor's
  P71, the point-biserial, the interval); `test_demand.py` forecasts that repeat last season at a growth of 1, the
  damping, the district split adding up, a new title's borrowed curve, hidden demand, the backtest and the print-run
  advice; `test_learning.py` item analysis worked out by hand, the 30-learner gate and each flag, the option chosen,
  chapter accuracy and cohorts with groups under 5 hidden; `test_codes_delivery.py`, `test_risk.py`, `test_offers.py`;
  `test_fraud.py` each rule on a case and on ordinary use, tries kept as hashes, the email; `test_api.py` the staff
  app's permissions, acknowledging a signal, and the answers' method, backtest and n; `test_admin.py` every page with rows; `test_commands.py` every job and the
  review on an empty database, a failure retried and kept; `test_privacy.py` no key to an account or a learner.
- **ops/**: `tests.py` health checks, the site with Redis down, request IDs, email fallback, the dashboard,
  `upload_backup`, Sentry scrubbing; `test_resilience.py` a broker that never answers; `test_security.py` the security
  review's operations fixes (health results, sessions, the backup script, development settings refused on a server);
  `test_errors.py` the error pages (plain, JSON under `/api/`), what the browser keeps; `test_copy.py` the emails' words;
  `test_admin_pages.py` every admin page opens; `test_sms.py` the SMS gateway and its cap; `test_sms_limits.py` the
  limits per number, account and purpose; `test_suppression.py` bounces and complaints; `test_no_server_errors.py` no
  address of Django or the API answers an empty or odd request with a server error.
- **shop/** (helpers in `shop/factories.py`, `shop/conftest.py`): `test_money.py` rounding, coupons, shipping zones;
  `test_orders.py` checkout, stock and bundles, cash on delivery, state machines, cancellation, refunds, invoices and
  credit notes, guest links, the daily clean-up; `test_razorpay.py` Checkout's signature, webhooks, automatic refunds;
  `test_robustness.py` coupon limits at payment (and at the very same instant), stuck payments and `reconcile_payments`,
  the dashboard, the product page in the admin; `test_security.py` the security review's shop fixes; `test_api.py` the
  shop's REST endpoints; `test_admin.py` SALES and SUPPORT in the admin, the order actions, `seed_shop`;
  `test_catalogue.py` categories, collections, attributes, slug redirects, digital products; `test_offers.py` offers and
  the discount split on documents; `test_staff_orders.py` staff orders, payment links, offline payments, notes;
  `test_settlements.py` Razorpay's settlements (fetched once, matched, the inbox, the ERPNext hook once and never for
  test keys) through a double of Razorpay's recorded answers; `test_staff_finance.py` the Finance module's API (the
  stuck payments, Ask Razorpay again, B2B links, the manual match, Finance today);
  `test_store_admin.py` bulk actions, imports and exports, the store dashboard, roles; `test_commerce.py` tracking
  links, reviews, quotations, stock alerts, the GSTR-1 export, order SMS; `test_platform.py` the buckets, pictures, link
  previews, JSON-LD, the web app, the PIN directory; `test_api_contract.py` reviews, back in stock, quotations and the
  order's link through the API; `test_offer_limits.py` offer limits with several pending orders; `test_review_lows.py`
  attribute filters, the PIN lookup's caching, staff orders for a student awaiting a parent, category imports, email
  subjects from forms.
- **staff/tests/** (the Admin Control Panel's backend; helpers in `staff/tests/conftest.py`): `test_matrix.py` every
  role against every staff endpoint and method, the shipping app's and the insights' too (a 403 and an `authz_fail`
  event without the permission, never a 403 with it), every endpoint naming a catalogued permission;
  `test_catalogue.py`; `test_scopes.py` each scope kind;
  `test_audit.py` an event's fields and masks, the chains, the PostgreSQL trigger, the daily copy, retention, the
  nightly check, the flows that feed it, who reads it; `test_approvals.py` maker-checker and the refund flow;
  `test_people.py` roles, SSD, invitations, offboarding, the access review; `test_users.py` customers, reveals,
  impersonation's token; `test_impersonation.py` the website's side: once, its limits, its audit, its end;
  `test_privacy.py` data requests' clocks, erasure, incidents, processors; `test_settings.py` the panel's switches over
  the environment's; `test_api_keys.py`; `test_session.py` the manifest, the idle limits by role, the absolute limit,
  break-glass sessions, the admin host (the staff API and the Django admin); `test_inbox.py` the inbox (parcels'
  exceptions and the integrations' failures too) and the system page; `test_jobs.py` the background jobs (exports,
  bulk actions, their approval, cancelling, the result's link); `test_notes.py` notes and policy acknowledgements.
  `accounts/test_google.py` also has the staff's Google Workspace sign-in.

## Production

See [DEPLOYMENT.md](DEPLOYMENT.md). Settings come from the environment (`.env.example` documents each one but
`GUNICORN_CMD_ARGS`; DEPLOYMENT.md section 13 lists them all). [RESILIENCE.md](RESILIENCE.md) is what keeps a slow or
failed dependency from hanging a request or a worker: every timeout and limit, the load test, the operators' knobs.

- **The stack.** docker-compose.yml runs PostgreSQL 17, two Redis 7 (`redis`, the Celery queue, which never evicts;
  `redis-cache`, the cache, 256 MB with the least used keys evicted), the site (gunicorn from `gunicorn.conf.py`:
  `WEB_CONCURRENCY` processes of 8 threads, WhiteNoise for static files, non-root), the Celery worker, a second worker
  for the clips
  (`media-worker`: queue `media`, one video at a time; it gets only the database, the queue, the buckets and
  `SECRET_KEY` from `.env`, has no Razorpay, SMS, email, Google, Sentry or Firebase secret, and drops all Linux
  capabilities), beat, the website (`frontend`, the Next.js server of `../examleaf-frontend/`), and Caddy (https with
  automatic Let's Encrypt certificates; Django's paths to `web`, every other path to the website, `PAGES_UPSTREAM`,
  `frontend:3000` by default; a request ID per request, bodies over 10 MB refused, a client has 10 seconds for its
  headers and 5 minutes for its body, and Caddy reads the body before gunicorn sees the request).
- **https and the CSP.** With `DEBUG=0` the session and CSRF cookies are `Secure`, `SECURE_SSL_REDIRECT` is on and HSTS
  is sent for a year; `SECURE_HSTS_INCLUDE_SUBDOMAINS` and `SECURE_HSTS_PRELOAD` stay off until every subdomain is on
  https, which is why `check --deploy` prints W005 and W021 (and nothing else with a real email backend). A
  Content-Security-Policy on Django's pages (the admin, the staff player, the API docs; the website sends its own)
  allows scripts, styles and fonts only from the site, and inline styles (the admin needs them) but never inline
  scripts; the public media domain for images; the private bucket's own
  address only on the staff player and the clip admin pages (the video, the direct upload); in development it is
  report-only. django-axes keeps only failed log-ins (address and browser, for the 15-minute lock-out), and beat clears
  them daily.
- **Health checks.** `/health/` checks the database, the migrations, the cache, file storage and, when a broker is set,
  that a Celery worker answers for each queue; it returns 500 if one fails (for an uptime monitor). `/health/web/` is
  readiness: the database answers and no migration is waiting (the cache and the buckets left out: the site runs
  without them, and their outage must not take every pod out of traffic). `/health/live/` is liveness: the process
  answers, neither the database nor Redis asked (docker-compose.yml's container check). Caddy answers them with 404
  unless the request carries the `X-Health-Token` header with `HEALTH_CHECK_TOKEN` (the uptime monitor), and each
  process keeps the first two's results for 20 seconds.
- **Logs and errors.** JSON lines on stdout with `request_id` (from Caddy's `X-Request-ID`, also sent back in the
  response): one per request (`examleaf.requests`: the URL pattern, status, milliseconds, the account's id; a warning
  past 2 s), `task_id` inside Celery tasks, gunicorn's own lines; RUNBOOK.md "Reading the logs". Errors go to Sentry
  when `SENTRY_DSN` is set (scrubbed: see "Personal data").
- **Files.** Uploaded files (invoices, credit notes, quotations, answer-sheet photos, the clips' videos) go to `media/`,
  never served publicly, or to the private bucket with `MEDIA_BUCKET`; an upload view must check the file's size when it
  is built.

Running without surprises:

- **Readiness**: the image build collects the static files (hashed, compressed); the web container migrates, brings the
  roles up to date and runs django-health-check's `manage.py health_check health_web --no-http` (the database, no
  migration waiting) before gunicorn starts; if it fails the container stops and Docker restarts it.
- **Timeouts**: every call to another service has a connect and a read timeout and a bounded retry (Razorpay 3 s and
  10 s, MSG91 the same, the buckets and SES through boto3 3 s and 20 s with three tries, Firebase 20 s, the integrations
  client 5 s and 20 s), PostgreSQL 5 s to connect and a statement 15 s in the web, 600 s in Celery; Razorpay and MSG91
  share at most half of a web process's threads (a bulkhead). RESILIENCE.md has them all.
- **Redis down**: the cache fails soft (django-redis with one-second timeouts and `IGNORE_EXCEPTIONS`: every call counts
  as a miss, and after a call that failed a process asks Redis nothing for five seconds), so pages keep working while
  rate limits and throttles let requests through (sessions and
  axes are in the database); log-in, sign-up and password reset keep working too (allauth takes `cache.add` answering
  nothing for a lock held by somebody else, and would answer 429 to all of them, so `examleaf.cache.SoftRedisCache` says
  "stored" instead); emails and SMS are sent from the web process when the broker cannot be reached (at once when it
  refuses, a few seconds when it accepts connections and never answers: `CELERY_BROKER_TRANSPORT_OPTIONS`); invoice,
  credit note and refund tasks lost meanwhile are queued again by the daily clean-up; `/health/` reports the cache. The
  shop's own limits (order lookup, checkout, place order, coupon codes, reviews, "email me when it is back", school
  quotations) refuse instead, and the SMS daily cap is counted in the database for the same reason.
- **Request sizes**: Caddy refuses bodies over 10 MB and reads the whole body before gunicorn sees the request (headers
  within 10 seconds, body within 5 minutes). Clip videos go from the editor's browser to the private bucket and never
  through gunicorn; without a bucket (development) the admin's clip and revision pages take up to 500 MB, and only from
  signed-in staff (`learn.uploads.LargeBodyGuard`). Django refuses more than 1 MB of form or JSON data
  (`DATA_UPLOAD_MAX_MEMORY_SIZE`; the API answers 413 in its JSON format) and more than 10 files in one request.
- **Database connections** persist between requests (`CONN_MAX_AGE`, default 60 s, health-checked before reuse) rather
  than in a pool: each gunicorn thread serves one request at a time (3 workers × 8 threads), so a pool would hold as
  many connections. PostgreSQL's `max_connections` must hold every thread and Celery process (RESILIENCE.md).
- **Celery** acknowledges a task once it has run (a worker that dies with it leaves it to another), takes one at a time
  per process, replaces a process after 200 tasks or 300 MB, gives each kind of task its time limits, and the periodic
  jobs that send take a lock for their run (RESILIENCE.md "Celery, task by task").
- **Transactions** are explicit, with row locks (`shop/services.py`): checkout (the order and the address saved with
  it), payment, refunds, each webhook together with its record; `ATOMIC_REQUESTS` stays off.
- **Static files** are collected into the image at build time (hashed and compressed, WhiteNoise); the CI's
  `docker-build` job builds that image on every push.

## Data model

- `accounts.User` — email login; full name, phone (optional, contact data only), the mobile number for log-in
  (`login_phone`, stored once confirmed by SMS, one account per number) with `login_phone_verified` and `sms_updates`
  (order updates by SMS), class (10/12), board, district, date of birth, parent's name and contact (under 18 only),
  `consent_at`; created/modified; role properties from its groups.
- `accounts.TeacherProfile` (school, district, subject, verified, verification note, verified by/at),
  `accounts.ConsentRecord` (event, purpose, policy version, by a parent, how it was given, when the parent confirmed,
  address hash), `accounts.DeletionRequest` (pending/cancelled/done, due seven days after the request).
- `content` — `Board` and `ClassLevel` → `Subject` (PHY/CHE/MAT/BIO) → `Book` → `Paper` (code, tier E/M/H, number,
  marks, time, `header_json` with the instruction lines and allotment tables, `is_published`) → `Question` (order,
  label, part and group headings, `text_md`, `options_json`, `marks_text`, `is_alternative`, `table_md`, tags) →
  `Solution` (`body_md`, the solution block as written: step table, Final answer, Also accepted, Diagram expected). The
  Markdown is stored and rendered at display time by the `markdown` template filter (markdown-it-py, cached). Book,
  Paper, Question and Solution keep a full edit history (django-simple-history).
- `practice.Attempt` — a student's marks, time and notes for a paper. `practice.AnswerSheetUpload` — photo, status
  (pending/processing/checked/failed) and `result_json`; model and admin only, no checking logic yet.
- `pages.Page` — the five legal pages (slug = URL, title, Markdown text, version, history). First drafts in
  `pages/drafts/*.md`, loaded by a migration; the words in square brackets (address, GSTIN, phone, email, Grievance
  Officer, delivery times, a refund rule to confirm) must be filled in before the shop opens.
- `shop` — the catalogue: `Product` (kind sample-papers/solutions/bundle/digital, subject and book links, ISBN, pages,
  cover and its sizes, link-preview picture, MRP and price, GST rate, HSN, weight, stock, SEO, product type, categories,
  related products), `ProductImage`, `BundleItem`, `SlugHistory` (earlier addresses), `Category` (a tree),
  `Collection` and `CollectionItem`, `ProductType` → `Attribute` → `AttributeValue`, `PinCode`. Selling: `Coupon`,
  `Offer`, `ShippingRate`, `Address`, `Cart` and `CartItem`, `Order` (EL-2026-000123, a secret link token, address
  copy, money, coupon, method online/cash on delivery/offline, status machine, live or test mode, who made it when
  staff did, history), `OrderItem` (copies of title, HSN, GST rate, prices and the line's share of the discounts),
  `OrderDiscount` (each saving as the customer saw it), `OrderNote` (staff's, with history), `Payment` (Razorpay ids,
  payment link, bank or UPI reference, signature, status machine, history, the last webhook's allowed fields),
  `Refund`, `Shipment` (courier, tracking number and link), `Invoice` (number per financial year, PDF), `CreditNote` (a
  refund of an invoiced order: its own number series, PDF), `WebhookEvent` (webhooks handled: Razorpay's event id and
  the body's hash). Around the shop: `Review` (with history), `StockAlert`, `QuoteRequest`.
- `learn` — `Chapter`, `Revision`, `Clip` (with its processing state machine), `FlashCard`, `QuizItem`, `BookCode`
  (a keyed hash, never the code), `Entitlement`, `Learner` (exam date, minutes a day, reminders), `Progress`,
  `QuizAttempt` (right or not, and the multiple-choice option chosen), `CardReview`, `Device` (the app's Firebase
  installation ID).
- `ops` — `SmsLog` (a keyed hash of the number, its last four digits, kind, status, the account), `EmailSuppression`;
  the Celery email and SMS tasks, the admin dashboard, the admin theme, the `upload_backup` command.
- `api` — no models of its own; simplejwt's token blacklist tables hold the refresh tokens.
- `insights` — what staff enter: `ExamSeason` (a board's exam for a class and year), `PrintCost` (per title: cost and
  salvage per copy, copies on order, reprint lead time); what the jobs write: `ForecastRun` (method, parameters, data
  time, code version, status) with its `Forecast`, `Backtest` and `PrintRunAdvice` rows, `ItemStat`, `ChapterStat`,
  `CohortStat`, `CodeActivationStat`, `DeliveryStat`, `OfferStat`, `FraudSignal`, `RedemptionAttempt` (book codes
  tried, as hashes) and `AccountScore` (schools and distributors; no rows yet). None points to an account.
- `staff` — the Admin Control Panel's: `StaffScope`, `RoleGrant`, `AuditEvent` (append-only, hash-chained) and
  `AuditHead`, `ChangeRequest` and `Approval`, `Job`, `InboxItem`, `SavedView`, `SiteSetting`, `FeatureFlag`, `ApiKey`,
  `StaffInvite`, `DataRequest`, `Incident`, `ProcessorRecord`; `StaffPermissions` holds the action permissions
  (`staff/README.md`).

- `erp` — `ErpOutbox` (what goes to ERPNext, in order per order, product or settlement), `ErpLink` (the platform's
  reference and ERPNext's document), `ErpCursor` (the pull's place per doctype), `ErpStockSnapshot`, `ErpMirror` (B2B
  documents read back), `ErpReconciliationRun` and `ErpReconciliationDifference` (`erp/README.md`).
- `integrations` — `IntegrationAccount` (a provider in a mode: encrypted credentials and tokens, the circuit breaker),
  `IntegrationCall` (the redacted call log), `IntegrationFailure` (the dead-letter list), `InboundEvent` (webhooks as
  they came) (`integrations/README.md`).
- `shipping` — `ShipmentDetail` (a shipment's courier side, one to one), `ShipmentEvent` (its timeline),
  `PickupLocation`, `ShipmentCharge`, `CodRemittance`, `ShippingException`, `PinServiceability`, `PostalTariff`
  (`shipping/README.md`).

## Planned extensions (not built)

- **Question banks**: questions already carry chapter and section tags; a bank is a filtered list of `Question`s
  (by subject, chapter tag, marks), and new bank-only questions can live in papers that are not published.
- **AI checking of photographed answer sheets**: an upload view creating `AnswerSheetUpload`, a Celery task that
  reads the photo, compares each answer with the `Solution` step table and writes marks per step to `result_json`,
  and a result page; the status field already models the queue.
- **Class 10 and other boards**: new `Board`/`ClassLevel`/`Subject`/`Book` rows; the importer takes the board from
  its arguments once a second board exists.
- **Teacher tools**: nothing links a student to a teacher yet (`TeacherProfile` has no students; the TEACHER role has
  no permissions), so teachers cannot see their students' attempts.
- **More couriers** (Delhivery direct, India Post's bulk API: a carrier of `shipping/carriers/`), 17TRACK's tracking of
  parcels sent by hand, WhatsApp updates (a hook: `shipping.messages.notify_whatsapp`), the customer's own NDR page.
  Weight-based shipping rates for the checkout.
- **The mobile app** is a separate project; the REST API is ready for it.
- **Left out on purpose** (`../docs/examleaf-phase5-plan.md`): abandoned-cart emails (DPDP s. 9(3)), third-party
  analytics, site search, a second live SMS provider, WhatsApp OTP, sign-up by passkey.

## Phases to come

Built, phase by phase in CHANGELOG.md: the site, production setup and roles, the shop, the REST API, security, sign-in
and communications (phase 5 A), storage, pictures, search engines, the web app and commerce extras (5 B), the revision
course (6 D), the store (6 E), the API contract for frontends (phase 7) and the website in Next.js (phase 8), after
which Django's own pages were removed. Open:

- **Founder decisions** (`../docs/examleaf-phase6-plan.md`): the price of the Revision Pass and whether book buyers get
  it free (book codes support both); where the exam date comes from until ASSEB publishes a timetable (students enter it
  now); whether clips are public (no sign-in) or entitled (today the first clip of each revision is free to signed-in
  students); the Firebase project for push; the mobile app project itself.
- **Before opening**: the real PIN code directory loaded (`import_pincodes`), one real tracking number per courier tried
  against its link, the legal pages and the seller's details filled in (DEPLOYMENT.md section 12).
- **Small gaps**: refunds of payments recorded offline are made by hand; a quotation is not turned into a staff order by
  itself (staff type the address).

## Libraries

Pinned in `requirements.txt` (what the Docker image installs) and `requirements-dev.txt` (tests, lint, debug toolbar).

| Library | Purpose |
|---|---|
| Django 6.1 | the framework: ORM, admin, auth, groups and permissions, forms, messages, mailers, security middleware, CSP |
| django-environ | settings from environment variables / `.env`: `DATABASE_URL`, `CACHE_URL`, lists and booleans |
| whitenoise | serves static files, hashed and compressed, in production |
| gunicorn | WSGI server for production |
| psycopg[binary] | PostgreSQL driver (production database) |
| django-allauth | registration, log-in by email, by a code (email or SMS) or by passkey, email and phone verification by code, email change with re-verification, re-authentication, password change and reset, built-in rate limits; `allauth.mfa`: an authenticator app (TOTP), recovery codes and passkeys (WebAuthn), required for staff; `allauth.socialaccount` with its Google provider; `allauth.headless`: the same flows as JSON for the app and a separate frontend (`/_allauth/`, API.md) |
| fido2 | WebAuthn for `allauth.mfa` (passkeys); allauth imports it |
| pwned-passwords-django | refuses passwords found in data breaches (Pwned Passwords; only the first 5 characters of the password's SHA-1 are sent) |
| django-axes (with django-ipware) | records failed logins and locks an account for 15 minutes after 10 failures from one address; its client-address logic also feeds the consent records |
| django-anymail | sends email through Amazon SES (or Brevo, Postmark …) in production, console in development; receives their bounce and complaint webhooks |
| httpx | the HTTP client for MSG91 (SMS), Cloudflare Turnstile's check and Pwned Passwords, always with timeouts |
| celery | background tasks: email, SMS, invoices, refunds, picture sizes, clip videos (queue `media`), the daily jobs |
| django-celery-beat | the periodic-task schedule, stored in the database and editable in the admin (pinned to an upstream commit until a release supports Django 6.1) |
| django-celery-results | task results in the database, cleaned up by beat after a week |
| redis, django-redis | Redis client; Redis cache backend for `CACHE_URL=redis://…`, failing soft (a miss) while Redis is down |
| sentry-sdk | error reports when `SENTRY_DSN` is set (server side only, no personal data: `examleaf/sentry.py` scrubs secrets, card and phone numbers) |
| python-json-logger | JSON log lines on stdout |
| django-guid | request IDs: from the proxy's `X-Request-ID` or new, in every log line (also in Celery tasks) and in the response |
| django-health-check | `/health/` and `/health/web/`: database, cache, storage, Celery workers; its `health_check` command is the web container's readiness check |
| django-admin-interface (django-colorfield) | the admin theme |
| razorpay (requests) | the official Razorpay SDK: orders (also for the app's mobile SDK, through the API), payment links, payment fetch and capture, refunds, signature checks |
| django-money (py-moneyed, babel) | INR money fields and ₹ formatting |
| django-localflavor | Indian states and PIN code validation |
| python-stdnum | checks a school's GSTIN on the quotation form (localflavor uses it too) |
| django-fsm-2 | the order, payment and clip-processing state machines (guarded transitions) |
| WeasyPrint | invoice, credit note and quotation PDFs from HTML templates (needs Pango) |
| openpyxl | XLSX files of the admin's imports and exports (django-import-export) |
| django-model-utils | `TimeStampedModel` (created/modified) and `StatusModel` for the answer-sheet status |
| django-simple-history | audit trail of edits to books, papers, questions, solutions, legal pages, orders, payments, order notes and reviews (an admin History button for all but payments and order notes) |
| django-taggit | chapter and textbook-section tags on questions; tags on clips, flash cards and quiz items |
| django-phonenumber-field (phonenumberslite) | phone fields and validation of Indian numbers (region IN): the parent's contact, delivery addresses (website and API) |
| django-import-export | the admin's CSV exports (users, attempts, consent records), orders as CSV and XLSX, product and category import and export |
| django-filter | the subject/tier filter on My record and the API's list filters |
| django-qr-code (segno) | generates the QR images (PNG for `/qr/<code>.png`, PNG and SVG for `export_qr`) |
| django-storages[s3] (boto3) | the two S3-compatible media buckets (private and public) and the backup bucket |
| django-pictures | AVIF and WebP sizes of the product pictures, made by Celery, and the `<picture>` tag |
| django-treebeard | the shop's category tree (materialised path) and its admin |
| firebase-admin | Firebase Cloud Messaging for the course's daily reminder (only with `FCM_SERVICE_ACCOUNT_JSON`) |
| markdown-it-py | Markdown (with tables) to HTML for questions, solutions, notes and legal pages |
| Pillow | images: the answer-sheet `ImageField`, the pictures (AVIF and WebP are bundled), the link-preview pictures and app icons it draws |
| djangorestframework | the REST API (`api/`, API.md): views, serializers, versioning, pagination, throttles |
| dj-rest-auth | the API's log-in, log-out, token refresh, password change and reset, user details |
| djangorestframework-simplejwt | JWT access and refresh tokens for the app; rotation and blacklist |
| drf-spectacular (drf-spectacular-sidecar) | the OpenAPI 3 schema, Swagger UI and Redoc (their files served by the site) |
| django-cors-headers | CORS for web clients on other origins, `/api/` only |
| ruff | lint and formatting (`pyproject.toml`) |
| pytest, pytest-django, pytest-cov, factory_boy | tests, coverage and test data (development and CI; requirements-dev.txt, not in the image) |
| django-debug-toolbar | development only, when `DEBUG=1` (requirements-dev.txt) |
| hls.js 1.7.3 (vendored in `static/learn/`) | plays the clips in the staff player |
| Poppins, Hind Siliguri (in `static/fonts/`) | the site's fonts, subsets served by the site (SIL Open Font Licence) |
| ffmpeg (a system package in the image) | makes the clips into HLS |

Docker images: python:3.14-slim, postgres:17, redis:7-alpine, caddy:2. django-crispy-forms was considered but has no
plain-CSS template pack (only Bootstrap/Tailwind/Bulma add-ons); forms are rendered by the site's `_field.html` partial
and allauth's overridden elements instead.
