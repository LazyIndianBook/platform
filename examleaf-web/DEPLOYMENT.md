# First deployment

The whole stack runs on one Linux server with Docker: PostgreSQL 17, two Redis 7 (the Celery queue and the cache), the
Django backend (gunicorn: the API, sign-in, the admin), the website (`frontend`, the Next.js server of
`../examleaf-frontend/`), the Celery worker, a second worker for the revision course's videos, beat, and Caddy, which
serves https, renews the certificate by itself and sends Django's paths to `web` and every other path to the website. A 2 vCPU / 4 GB machine is plenty to start: e.g. Hetzner CX22, a
DigitalOcean 4 GB droplet, or an Indian provider (E2E Networks, AWS or Azure in Mumbai) if the data should stay in
India, as the Privacy Policy draft says ("servers in [India]": fill in what you choose).

Sections 1 to 12 are the first deployment, in order. After them: 13 every setting, 14 security, 15 the accounts to open
(with the steps for each), 16 what the sign-in, SMS and email settings switch on, 17 storage, pictures and the web app,
18 the revision course, 19 the store, 20 the frontends' sign-in (allauth.headless) and API contract, 21 the insights
(the predictive jobs), 22 shipping and the integration keys, 23 the staff and the audit log.

## 1. Accounts you need

Open them first: some take days or weeks (the DLT registration for SMS 1 to 2 weeks, Razorpay's activation, a new
Amazon SES account's production access). Section 15 lists every account and service with what it is for, how long it
takes, what it costs where these documents say so, and which variables it fills. To start you need a domain, a server,
a place for the code (GitHub) and an email provider; payments, SMS, Google sign-in, buckets, Sentry and the rest can
follow.

## 2. DNS

Create an `A` record (and `AAAA` for IPv6) for `examleaf.in` pointing at the server's address. Wait until
`dig +short examleaf.in` shows it: Caddy asks Let's Encrypt for the certificate on its first start, and that only
works once the name points at the server and ports 80 and 443 are open.

## 3. The server

As root on a fresh Ubuntu 24.04:

```sh
adduser examleaf && usermod -aG sudo examleaf   # sudo asks for the password you set; then log in as examleaf with an SSH key
apt update && apt install -y unattended-upgrades ufw git
ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443/tcp && ufw allow 443/udp && ufw enable
curl -fsSL https://get.docker.com | sh && usermod -aG docker examleaf   # Docker Engine and the compose plugin
```

Docker publishes ports past ufw; only Caddy publishes any (80, 443). PostgreSQL and Redis are reachable only inside
the compose network.

## 4. Code and settings

```sh
sudo mkdir -p /srv/examleaf /srv/books && sudo chown examleaf: /srv/examleaf /srv/books
git clone git@github.com:LazyIndianBook/platform.git /srv/examleaf          # this repository (deploy key 1)
git clone git@github-books:LazyIndianBook/Class-12-Assam.git /srv/books    # the papers (deploy key 2, below)
cd /srv/examleaf/examleaf-web
cp .env.example .env && chmod 600 .env
```

**The papers.** The questions and solutions are not in this repository: they live in the private books repository
`LazyIndianBook/Class-12-Assam`, and `import_papers` reads a copy of it on the server. Make the keys before the two
clones above: GitHub lets a deploy key open one repository only, so the server has two read-only keys (`ssh-keygen -t ed25519 -N "" -f ~/.ssh/examleaf_platform`,
the same for `~/.ssh/examleaf_books`), each added in its repository under Settings → Deploy keys without write access,
and `~/.ssh/config` says which is which:

```
Host github.com
  IdentityFile ~/.ssh/examleaf_platform
  IdentitiesOnly yes
Host github-books
  HostName github.com
  IdentityFile ~/.ssh/examleaf_books
  IdentitiesOnly yes
```

Without git access to the books, copy the files the import reads from a checkout instead (the same folders, so the
rest is unchanged): `tar czf papers.tgz production/{physics,chemistry,mathematics,biology}/{papers_md,format.json,orders,pyq}`
there, then `scp papers.tgz examleaf@<server>:/srv/books/ && ssh examleaf@<server> tar xzf /srv/books/papers.tgz -C /srv/books`.
Either way `.env` gets `BOOK_SOURCE=/srv/books`: compose mounts its `production/` read-only at `/book/production`
and sets `PAPERS_ROOT=/book`, so the command is `docker compose exec web python manage.py import_papers --all`
(outside compose: `manage.py import_papers --all --root /srv/books`).

Edit `.env` (each variable is explained there, and in section 13). At least:

```sh
DEBUG=0
SECRET_KEY=<python3 -c "import secrets; print(secrets.token_urlsafe(50))">
ALLOWED_HOSTS=examleaf.in
SITE_URL=https://examleaf.in
DOMAIN=examleaf.in
POSTGRES_PASSWORD=<python3 -c "import secrets; print(secrets.token_hex(24))">
BOOK_SOURCE=/srv/books               # the books checkout (above), mounted read-only for import_papers
HEALTH_CHECK_TOKEN=<python3 -c "import secrets; print(secrets.token_urlsafe(32))">   # the uptime monitor's (section 14)
EMAIL_BACKEND=anymail.backends.amazon_ses.EmailBackend   # Brevo for the first weeks: anymail.backends.brevo.EmailBackend
SES_ACCESS_KEY_ID=...                # with Brevo: ANYMAIL_BREVO_API_KEY=... instead (section 15, "Email")
SES_SECRET_ACCESS_KEY=...
DEFAULT_FROM_EMAIL=ExamLeaf <noreply@examleaf.in>
WEB_CONCURRENCY=3
LEARN_CODE_SECRET=<python3 -c "import secrets; print(secrets.token_urlsafe(50))">   # the book codes' key: set once, never change (section 18)

SENTRY_DSN=...                       # optional
BACKUP_BUCKET=examleaf-backups       # optional, with AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, BACKUP_ENDPOINT_URL
BACKUP_AGE_RECIPIENT=age1...         # with a bucket: the uploaded dumps are encrypted to this key (section 9)
```

With `DEBUG=0` the site refuses to start while `SECRET_KEY` is the example's (`dev-…`) or shorter than 50 characters,
and the web container stops at `migrate` (system check `learn.E001`) while `LEARN_CODE_SECRET` is empty; with `DEBUG=1`
it refuses any `ALLOWED_HOSTS` but `localhost`, `127.0.0.1`, `[::1]` and `*.localhost`. `.env.example` ships `DEBUG=1`:
a copy of it is a development file. Do not copy the `#` comments of the block above into `.env`: django-environ keeps
them as part of the value, and a key followed by a comment is no longer a key. `ALLOWED_HOSTS` must include `DOMAIN`:
the web container's health check sends it as the Host.

`DATABASE_URL`, `CACHE_URL`, `CELERY_BROKER_URL`, `PROXY_COUNT`, `PAPERS_ROOT` and the two `AWS_…_CHECKSUM_…` variables
are set by docker-compose.yml.

## 5. Start

```sh
docker compose up -d --build
docker compose ps                     # db, redis, redis-cache, web, frontend healthy; worker, media-worker, beat, caddy running
docker compose logs -f web caddy      # migrations, bootstrap_roles, gunicorn; Caddy obtaining the certificate
```

The static files were collected (hashed, compressed) when the image was built. The web container runs `migrate` and
`bootstrap_roles` on every start, in that order, then the readiness check
(`manage.py health_check health_web --no-http`: the database answers and no migration is waiting), then gunicorn
(`gunicorn.conf.py`); if the check fails the container stops, its log names the failing part, and Docker starts it
again. The cache and the buckets are not waited for: the site runs without them, and `/health/` (section 7) reports
them. To run them by hand:
`docker compose exec web python manage.py migrate && docker compose exec web python manage.py bootstrap_roles`. Worker,
media-worker and beat start once the web container is healthy (`/health/live/`: gunicorn answers).

## 6. Content and the first admin

```sh
docker compose exec web python manage.py import_papers --all      # reads /srv/books (BOOK_SOURCE), mounted read-only
docker compose exec web python manage.py createsuperuser
```

Log in at `https://examleaf.in/admin/`: the admin's log-in is the site's (the emailed code confirms the address the
first time), and every member of staff sets up an authenticator app (or a passkey) before anything else opens
(RUNBOOK.md, "Staff accounts"). In the admin: fill in the square-bracket placeholders of the five legal pages (Pages),
create staff accounts and give them roles (Users → action "Give role …"), and look at Periodic tasks (the daily jobs
run between 03:00 and 04:30 India time, the hourly stock alerts, the 08:00 low-stock email and the 18:00 revision
reminders; README.md lists them). The revision course's first content is section 18; the shop's is section 12.

## 7. Check

```sh
curl -s -H 'Accept: application/json' -H "X-Health-Token: $(sed -n 's/^HEALTH_CHECK_TOKEN=//p' .env)" https://examleaf.in/health/   # all "OK"
curl -s -o /dev/null -w '%{http_code}\n' https://examleaf.in/health/     # 404: without the header nobody gets an answer
docker compose exec web python manage.py check --deploy               # only security.W005 and security.W021 (with EMAIL_BACKEND set)
docker compose exec web python manage.py sendtestemail you@example.com   # the email provider works
```

Then register a test student from a phone, type the emailed code, open a paper's solutions, and delete the account from
My account (the purge erases it seven days later). Point the uptime monitor at `/health/` with the header
`X-Health-Token` (it returns 500 when the database, a migration, the cache or storage fails, or when the default or the
media queue has no Celery worker: the ping waits two seconds for every worker before it judges, so a 500 means a worker
is really gone). The other two are the probes': `/health/web/` (readiness: the database and the migrations) and
`/health/live/` (liveness: the process answers, nothing else asked); RESILIENCE.md says why each holds what it holds.

## 8. QR codes for print

Once `SITE_URL` is final (it is printed in the books and cannot be changed afterwards):

```sh
docker compose exec web python manage.py export_qr --out /tmp/qr && docker compose cp web:/tmp/qr ./qr
```

## 9. Backups

Add to the `examleaf` user's crontab (`crontab -e`):

```cron
15 2 * * * /srv/examleaf/examleaf-web/scripts/backup.sh >> /srv/examleaf/backup.log 2>&1
```

It writes `backups/examleaf-YYYYMMDD-HHMMSS.dump` (readable by the owner only), keeps `BACKUP_KEEP_DAYS` (30) days and
uploads each dump to `BACKUP_BUCKET` when set. Without a bucket the dumps stay on the same disk as the database: copy
them elsewhere. Try a restore once (RUNBOOK.md) before relying on them. The `media` volume holds the invoice PDFs (tax
records: keep them eight years) and, without buckets, the product pictures and the course's videos: back it up too, e.g.
`docker run --rm -v examleaf-web_media:/m -v /srv/examleaf/examleaf-web/backups:/b alpine tar czf /b/media-$(date +%F).tgz -C /m .`
(the volume name is `docker volume ls`'s; `backup.sh` deletes only old `examleaf-*.dump*` files, so delete old
`media-*.tgz` yourself); an invoice that is missing is made again by the daily clean-up, or by hand:
`docker compose exec web python manage.py shell -c "from shop.tasks import generate_invoice; generate_invoice(<order id>)"`.
With the buckets of section 17 the invoices, credit notes and quotations are in the private bucket instead, which these
backups do not cover.

The bucket also gets the erasure ledger, a small file per erased account under `erasures/` (a keyed hash of the
address, never the address: `manage.py reapply_erasures` erases those accounts again after a restore, RUNBOOK.md):
keep `erasures/` at least as long as the oldest backup, and longer is harmless. The bucket keeps what is uploaded
until it is deleted, so give it a lifecycle rule that deletes objects under
`database/` 30 days after they are uploaded (Cloudflare R2's object lifecycle rules, Backblaze B2's lifecycle rules, or
an S3 lifecycle configuration; with versioning on, old versions must expire too), as the Privacy Policy promises
("Backups: 30 days"). Encrypt the uploaded copies with [age](https://age-encryption.org) (`sudo apt install age`): on
your own computer run `age-keygen -o examleaf-backup.key`, keep that file off the server (a password manager and a
second safe place), and put the public key it prints (`age1…`) into `.env` as `BACKUP_AGE_RECIPIENT`. `backup.sh` then
uploads only `examleaf-….dump.age`; the local dumps stay plain on the server for a quick restore (RUNBOOK.md shows how
to decrypt). The script reads `BACKUP_KEEP_DAYS` and `BACKUP_AGE_RECIPIENT` from `.env` itself, so set them there.

## 10. Logs

- `docker compose logs -f web worker media-worker beat` — Django and Celery, one JSON object per line with `time`,
  `level`, `logger`, `message` and `request_id`: one line per request (`examleaf.requests`: method, URL pattern, status,
  `duration_ms`, `user_id`; a warning past `SLOW_REQUEST_SECONDS`), `task_id` and `task_name` inside a Celery task, and
  gunicorn's own lines (`gunicorn.error`: workers booting, exiting or timed out); RUNBOOK.md "Reading the logs";
- `docker compose logs -f caddy` — the access log (JSON, with the same `X-Request-ID` in the request headers);
- `docker compose logs db redis redis-cache`.

Docker keeps them in `/var/lib/docker/containers/<id>/<id>-json.log`, rotated at 50 MB, ten files per service (the
`json-file` driver's `max-size: 50m` and `max-file: "10"` of every service in docker-compose.yml: 500 MB a service).
CERT-In's Directions ask for 180 days of logs now, and the DPDP Rules a year from 13 May 2027 (the retention schedule,
`examleaf/retention.py` "security_logs", and the panel's Legal and privacy, Retention). Rotation is by size, not by
time (Docker's json-file driver has no age limit), so a fixed amount is kept: look at the oldest line of
`docker compose logs caddy` after a month of traffic, and if the 500 MB last less than 180 days raise `max-file`; put
the days they last in the Privacy Policy. What is kept on the server is a buffer: copy the logs off it daily (the log
copy of Phase B's System module, or a shipper of your choice) and keep that copy 180 days, a year from 13 May 2027.
For a hard limit in days use the journald driver instead (`logging: {driver: journald}` in docker-compose.yml and
`MaxRetentionSec=180day` in `/etc/systemd/journald.conf`). Celery task results are in the admin (Celery Results →
Task results) for a week; errors go to Sentry when it is set.

For the Kubernetes chart's next pass (not changed here): the kubelet rotates a container's log at
`containerLogMaxSize` (10Mi by default) and keeps `containerLogMaxFiles` (5): set `50Mi` and `10` in the nodes'
kubelet configuration (k3s: `--kubelet-arg=container-log-max-size=50Mi --kubelet-arg=container-log-max-files=10`), and
ship the pods' logs off the node (the same 180 days, a year from 13 May 2027).

## 11. Updates

```sh
cd /srv/examleaf && git pull
cd examleaf-web && docker compose up -d --build     # migrations and bootstrap_roles run on start
git -C /srv/books pull && docker compose exec web python manage.py import_papers --all   # when papers changed
```

Importing again is safe at any time: it changes only the questions and solutions whose Markdown changed (the rest are
left alone, so the admin's history shows real edits) and drops questions that left a paper; nothing else is touched.

The site is down for the few seconds the web container takes to restart: Docker gives it 40 seconds to stop, gunicorn's
30 for the requests in progress, and the Celery workers five minutes to finish their tasks (a task cut short anyway runs
again on the next worker: RESILIENCE.md). A new release can bring settings: compare `.env` with `.env.example` and
section 13.

## 12. Shop: Razorpay

The shop works in Razorpay's test mode (no real money) until the checklist below is done. README.md "Shop" describes
the flows.

1. **Account.** Sign up at <https://dashboard.razorpay.com> as ExamLeaf LLP and complete the activation (KYC: the LLP's
   documents, PAN, bank account, GSTIN if registered). Razorpay reviews the website: the Privacy, Terms, Refund,
   Shipping and Contact pages must be filled in (no square brackets left) and the shop must show prices.
2. **Test keys.** Dashboard in Test Mode → Account & Settings → API Keys → Generate. Put them in `.env`:
   `RAZORPAY_KEY_ID=rzp_test_…`, `RAZORPAY_KEY_SECRET=…`.
3. **Webhook.** In Test Mode: Account & Settings → Webhooks → Add new webhook: URL
   `https://examleaf.in/shop/webhooks/razorpay/`, a secret (`python3 -c "import secrets; print(secrets.token_urlsafe(32))"`,
   also into `.env` as `RAZORPAY_WEBHOOK_SECRET_TEST`), an alert email, and the events `payment.captured`,
   `payment.failed`, `order.paid`, `payment_link.paid`, `refund.processed` and `refund.failed`. The webhook completes
   orders whose customer never came back from the payment page, completes orders that staff made and sent a payment
   link for, and finishes refunds that Razorpay processes later. The live webhook gets a secret of its own when going
   live (`RAZORPAY_WEBHOOK_SECRET`): the site checks the secret of its keys' mode, so test-mode webhooks are refused
   once the live keys are in.

   **Shop closed during Razorpay's review.** Razorpay's activation review needs the shop public while it still runs on
   test keys, when anyone could "pay" with the published test card. Set `SHOP_OPEN=0`: the books and prices stay
   visible with "Shop opens soon", and only staff can use the cart, checkout and payment (website and API). Set it back
   to 1 (or remove it) when going live.
4. **Capture.** Account & Settings → Payment Capture: automatic (the site also captures an authorized payment when the
   customer comes back, so manual capture works too, but then a payment whose customer never returns is not captured).
5. **Payment Links** (for orders that staff make by phone or for schools): enable them in the Dashboard → Payment
   Links. We email the link ourselves, so Razorpay's own SMS and email for links stay off. A link lives 15 days; a staff
   order waits 16 days before the daily clean-up cancels it, after asking Razorpay whether its link was paid.
6. **Seller and options** in `.env`: `SELLER_LEGAL_NAME`, `SELLER_ADDRESS`, `SELLER_GSTIN` (empty if not registered),
   `SELLER_STATE`, `SELLER_STATE_CODE`, `SELLER_EMAIL`, `SELLER_PHONE`; `SHOP_COD_ENABLED=1` for cash on delivery
   (only for accounts with a confirmed email address, two orders on their way per account, each worth at most
   `SHOP_COD_MAX_VALUE`, ₹1,500 by default). Then `docker compose up -d` (the containers read `.env` when they start).
7. **Catalogue.** `docker compose exec web python manage.py seed_shop`, then in the admin (Shop): real prices and MRP,
   stock, ISBN, pages, weights, a cover for each Solutions book, the coupon's dates (or untick it), the shipping rates.
   Give the people who pack and ship the SALES role, and those who answer customers SUPPORT. The store's other parts
   (categories, collections, offers, staff orders) are section 19.
8. **Try it** with Razorpay's test card or the UPI ID `success@razorpay`: an order is paid, the confirmation email
   arrives, the invoice appears on the order page; a failed payment (`failure@razorpay`) can be retried; a cancellation
   is refunded and its credit note appears next to the invoice; Mark packed, Mark shipped (a tracking number) and Mark
   delivered send their emails. Dashboard → Webhooks shows each delivery answered 200.

### Going live

- [ ] Legal pages final: the email, phone, address, GSTIN and Grievance Officer filled in; the courier and dispatch days
      in Shipping; the refund rules in Refunds checked against what the business wants. The admin index says how many
      pages still hold a `[placeholder]` (the Pages list counts them page by page; on the site they are marked yellow).
- [ ] Seller details in `.env` correct: they print on every invoice and cannot be changed afterwards. While one of
      `SELLER_ADDRESS`, `SELLER_EMAIL` or `SELLER_PHONE` still holds its `[placeholder]`, no invoice of the real series is
      numbered (the worker logs the error and retries; the daily clean-up queues the invoices again once `.env` is right).
- [ ] Real prices, stock and ISBNs. Orders made in test mode stay in the admin, marked TEST once the live keys are in:
      they cannot be packed or shipped, a payment or webhook for them is ignored, and their invoices stay in the test
      series (`T/2026-27/…`, credit notes `TC/2026-27/…`, marked as not a tax document), so the real ones start at
      `EL/<year>/00001` and `CN/<year>/00001`.
- [ ] Razorpay account activated. Switch the Dashboard to Live Mode, generate live keys and set `RAZORPAY_KEY_ID=rzp_live_…`
      and `RAZORPAY_KEY_SECRET`; create the same webhook again in Live Mode (webhooks are per mode) with a new secret,
      set as `RAZORPAY_WEBHOOK_SECRET` (keep `RAZORPAY_WEBHOOK_SECRET_TEST`); `SHOP_OPEN=1`; `docker compose up -d`.
      The payment page no longer says "Test mode". RUNBOOK.md "Test mode and live mode" has the details.
- [ ] One real purchase of a cheap book, then cancel it: the refund appears in the Razorpay Dashboard (Refunds) and
      the money comes back to the card or UPI account.
- [ ] `check --deploy` shows only W005 and W021; `/health/` is OK; Sentry receives errors; the `media` volume (or the
      private bucket) is backed up (invoices and credit notes).
- [ ] The PIN code directory loaded (section 15, "The PIN code directory") and one real tracking number tried against
      each courier's link (RUNBOOK.md "Shipping with tracking links").
- [ ] After a first real order: `docker compose exec web python manage.py reconcile_payments` lists nothing but
      "no payment at Razorpay" for abandoned checkouts (it asks Razorpay about every unpaid online order; RUNBOOK.md,
      "A stuck payment").

## 13. Settings

Every environment variable the site, docker-compose.yml, the Dockerfile and `scripts/backup.sh` read, once, in the order
a person sets up a server. They come from `.env` (copy `.env.example`: each is explained there too) or the real
environment. "Required" means the site, the stack or the feature does not work without it; "no" means the default is
fine. docker-compose.yml sets `DATABASE_URL`, `CACHE_URL`, `CELERY_BROKER_URL`, `PROXY_COUNT`, `PAPERS_ROOT` and the two
`AWS_…_CHECKSUM_…` variables for its containers; the rest come from `.env`, except that the media worker (`x-media-env`
in docker-compose.yml) reads from `.env` only `SECRET_KEY`, `MEDIA_BUCKET`, `PUBLIC_MEDIA_BUCKET`,
`PUBLIC_MEDIA_DOMAIN`, the `S3_*` and `PUBLIC_S3_*` variables, `LEARN_PUBLIC_VIDEO`, `LEARN_MAX_UPLOAD_MB` and
`LOG_LEVEL`: it has no `DEBUG`, `SITE_URL`, `CACHE_URL` or `SENTRY_DSN` and reports nothing to Sentry, so add to that
list any variable its clip task comes to need. After a change: `docker compose up -d`.

### Core

| Variable | Default | Required | What it does; where to get the value |
|---|---|---|---|
| `DEBUG` | `0` (`.env.example` ships `1`) | set `0` on a server | 1 in development only: https redirect, secure cookies, HSTS and the enforced CSP are off or report-only, and the debug toolbar is on. With 1 the site refuses any `ALLOWED_HOSTS` but localhost, 127.0.0.1, [::1] and `*.localhost` |
| `SECRET_KEY` | none | required | long and random; signs sessions and (unless `JWT_SIGNING_KEY` is set) the API's tokens, and keys the hashes of the consent records' addresses and of the SMS log's numbers; with `DEBUG=0` the site refuses to start if it begins `dev-` or is shorter than 50 characters. `python3 -c "import secrets; print(secrets.token_urlsafe(50))"`; rotation: RUNBOOK.md |
| `SECRET_KEY_FALLBACKS` | none | no | the previous key(s), comma separated, while rotating (RUNBOOK.md) |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | required on a server | the host names the site answers to, comma separated: `examleaf.in`; it must include `DOMAIN` (the web container's health check sends it as the Host) |
| `SITE_URL` | `http://localhost:8000` | required on a server | `https://examleaf.in`, no trailing slash: the base of the QR codes and of the links in emails and SMS, and the host of the passkeys. `export_qr` refuses localhost and http. Printed in the books: final before printing |
| `CSRF_TRUSTED_ORIGINS` | `SITE_URL` | no | origins trusted for form posts, comma separated; add others only if the site is served under several names |
| `DOMAIN` | none | required (compose) | the domain Caddy serves and gets its certificate for: `examleaf.in` (`localhost` for a local run); compose refuses to start without it |
| `PAPERS_ROOT` | `Class 12` beside this repository when it is there (compose: `/book`) | no | a checkout of the books repository `LazyIndianBook/Class-12-Assam` (the folder that holds `production/`, the Markdown papers), for `import_papers` and `import_chapter_insights`; without it they stop and say so (`--root` gives it on the command line, `--fixtures` imports the test papers) |
| `BOOK_SOURCE` | `../../Class 12` | required to import on a server | compose only: the books checkout on the host (`/srv/books`, section 4), its `production/` mounted read-only at `/book/production` |
| `SOLUTIONS_REQUIRE_LOGIN` | `1` | no | 1: solutions for signed-in students; 0: for everyone (README.md, "Open or registered solutions") |
| `PARENTAL_CONSENT_MODE` | `declared` | no | `declared`: the parent ticks the sign-up box; `verified`: the parent also confirms by a link sent by email, or by SMS to an Indian mobile number when SMS are on (section 14; before May 2027) |
| `DATA_UPLOAD_MAX_MEMORY_SIZE` | `1048576` | no | largest form or JSON body in bytes, files not counted (the API answers 413 above it); Caddy stops bodies over 10 MB (500 MB only on the clip and revision admin pages, for signed-in staff) |

### Database, cache and queue

| Variable | Default | Required | What it does; where to get the value |
|---|---|---|---|
| `POSTGRES_PASSWORD` | none | required (compose) | the compose PostgreSQL's password: random, letters and digits only (it goes into a URL). `python3 -c "import secrets; print(secrets.token_hex(24))"` |
| `DATABASE_URL` | SQLite `db.sqlite3` | set by compose | `postgres://user:password@host:5432/examleaf`; compose builds it from `POSTGRES_PASSWORD` |
| `CONN_MAX_AGE` | `60` | no | seconds a database connection is kept between requests (0: closed after each); one per gunicorn thread and Celery process: PostgreSQL's `max_connections` must hold them all (RESILIENCE.md) |
| `DB_CONNECT_TIMEOUT` | `5` | no | seconds to connect to PostgreSQL |
| `DB_STATEMENT_TIMEOUT` | `15` in gunicorn, `600` in Celery, none in `manage.py` | no | seconds a statement may run before PostgreSQL cancels it (by the program's name; `0`: none). Behind PgBouncer in transaction mode set it on the database roles instead (RESILIENCE.md "The pooler") |
| `DB_IDLE_IN_TRANSACTION_TIMEOUT` | `60` in gunicorn, `600` in Celery, none in `manage.py` | no | seconds a transaction may sit idle before PostgreSQL ends the session (a thread stuck while holding row locks) |
| `CACHE_URL` | per-process memory | set by compose | `redis://host:6379/1`: a Redis of its own that may evict (compose: `redis-cache`, 256 MB, allkeys-lru), never the queue's; with Redis down the site runs on without it, but the shop's own limits (order lookup, checkout, place order, coupon codes, reviews, back-in-stock alerts, quotations) answer 429; a Redis that does not answer costs one second, then five seconds of misses at once (`examleaf/cache.py`) |
| `CELERY_BROKER_URL` | empty | set by compose | `redis://host:6379/0` (compose: `redis`, never evicts); empty: tasks run inline in the web process (development) |
| `CELERY_TASK_ALWAYS_EAGER` | `1` without a broker, else `0` | no | force inline tasks (1) or never (0) |
| `CELERY_WORKER_MAX_TASKS_PER_CHILD` | `200` | no | a Celery process is replaced after this many tasks |
| `CELERY_WORKER_MAX_MEMORY_PER_CHILD` | `307200` (KiB: 300 MB) | no | … or once it holds this much (WeasyPrint grows by about 1 MB an invoice); the worker's memory needs the main process (about 160 MB) and concurrency × this |

### Proxy, https and the web server

| Variable | Default | Required | What it does; where to get the value |
|---|---|---|---|
| `PROXY_COUNT` | `0` (compose sets `1`) | set by compose | proxies in front of the site: trusts `X-Forwarded-Proto` and `-For` from Caddy; also the client address for axes, allauth and the API |
| `USE_X_FORWARDED_HOST` | `0` (compose sets `1`) | set by compose | take the host name from `X-Forwarded-Host`: the Next.js frontend's server-side calls to `web:8000` name the site's host there (Caddy's requests carry it too) |
| `INTERNAL_API_TOKEN` | empty | yes with the frontend (compose refuses to start without it) | a shared secret (`python -c "import secrets; print(secrets.token_urlsafe(32))"`), given to `web` (`.env`) and to `frontend` (compose): the frontend sends it as `X-Internal-Token` with every server-side call, and only then does Django take the visitor's address from the `X-Forwarded-For` the frontend forwards (`examleaf.middleware.FrontendClientMiddleware`). Without it every anonymous page the frontend renders counts against one throttle bucket, the frontend's own address, and a burst of requests for missing pages can make the whole site answer "cannot be reached" (frontend review S4). Rotate it by changing `.env` and restarting both services |
| `SECURE_SSL_REDIRECT` | `1` with `DEBUG=0` | no | redirect http to https |
| `SECURE_HSTS_SECONDS` | `31536000` | no | HSTS lifetime |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS`, `SECURE_HSTS_PRELOAD` | `0` | no | on only when every subdomain is https (they are the two `check --deploy` warnings, W005 and W021) |
| `HEALTH_CHECK_TOKEN` | none | required (compose) | the value of the `X-Health-Token` header Caddy asks of `/health/` callers; letters, digits, `-` and `_`; compose refuses every command while it is empty (add it to `.env` before updating). `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`, then into the uptime monitor (section 14) |
| `WEB_CONCURRENCY` | `2` | no | gunicorn worker processes (about 2 x CPU cores + 1); `gunicorn.conf.py` reads it and the variables below |
| `GUNICORN_THREADS` | `8` | no | requests at once in each process; half of them at most wait on Razorpay or MSG91 (the bulkhead, RESILIENCE.md); each holds a database connection |
| `GUNICORN_TIMEOUT` | `60` | no | a process whose main loop is silent this long is killed and replaced (with threads it is no request's limit: their calls and statements have their own) |
| `GUNICORN_GRACEFUL_TIMEOUT` | `30` | no | after SIGTERM the requests in progress may finish this long; keep Docker's stop (40 s) and the chart's grace (70 s) above it |
| `GUNICORN_KEEPALIVE` | `5` | no | seconds an idle connection from Caddy or the frontend stays open |
| `GUNICORN_MAX_REQUESTS`, `GUNICORN_MAX_REQUESTS_JITTER` | `5000`, `2500` | no | a process is replaced after this many requests, each after a number of its own (smaller values restarted every process at once under load: RESILIENCE.md) |
| `GUNICORN_WORKER_CONNECTIONS` | `1000` | no | connections a process takes at once; leave it (a cap starves kept-alive connections) |
| `GUNICORN_BIND` | `0.0.0.0:8000` | no | where gunicorn listens |
| `GUNICORN_CMD_ARGS` | none | no | gunicorn's own variable: more arguments, which win over `gunicorn.conf.py`. Not in `.env.example` |
| `SLOW_REQUEST_SECONDS` | `2` | no | a request slower than this is logged as a warning (`examleaf.requests`) |

### Email

| Variable | Default | Required | What it does; where to get the value |
|---|---|---|---|
| `EMAIL_BACKEND` | console (printed in the log) | required on a server | `anymail.backends.amazon_ses.EmailBackend` (the production pick), `anymail.backends.brevo.EmailBackend` or `anymail.backends.postmark.EmailBackend` (section 15, "Email") |
| `DEFAULT_FROM_EMAIL` | `ExamLeaf <noreply@localhost>` | required on a server | the sender of every email: `ExamLeaf <noreply@examleaf.in>`, on the verified sending domain |
| `SES_ACCESS_KEY_ID`, `SES_SECRET_ACCESS_KEY` | none | with Amazon SES | the access key of the IAM user `examleaf-ses` (section 15); not the S3 or backup keys; the secret is required once the id is set |
| `SES_REGION` | `ap-south-1` | no | SES's region (Mumbai) |
| `ANYMAIL_AMAZON_SES_CONFIGURATION_SET_NAME` | none | with SES bounce handling | `examleaf`: the SES configuration set whose events go to the webhook |
| `ANYMAIL_WEBHOOK_SECRET` | none | with bounce handling | `user:password` (random letters and digits) that the provider puts in the webhook URL; empty: no `/anymail/` URLs at all, so no suppression list fills |
| `ANYMAIL_BREVO_API_KEY` (or the provider's own `ANYMAIL_…` key) | none | with Brevo, Postmark … | the provider's API key; any variable starting `ANYMAIL_` is handed to django-anymail |

### SMS

| Variable | Default | Required | What it does; where to get the value |
|---|---|---|---|
| `SMS_BACKEND` | `console` | for phone log-in and SMS | `msg91` sends SMS (section 15); `console` prints them, and on a server (`DEBUG=0`) turns phone log-in, order SMS and SMS consent links off. Any other value stops the site starting |
| `MSG91_AUTHKEY` | none | with `msg91` (the site refuses to start without it) | MSG91 → API: create an authkey, with the server's IP whitelisted (section 15) |
| `MSG91_TEMPLATE_OTP`, `MSG91_TEMPLATE_ORDER_PLACED`, `MSG91_TEMPLATE_ORDER_SHIPPED`, `MSG91_TEMPLATE_ORDER_DELIVERED`, `MSG91_TEMPLATE_PARENT_CONSENT`, `MSG91_TEMPLATE_ORDER_ARRIVING`, `MSG91_TEMPLATE_ORDER_NOT_DELIVERED` | none | one for each kind of SMS wanted | the id MSG91 gives each registered DLT template (texts: RUNBOOK.md "SMS"); the last two are a courier's news (section 21), not sent while empty |
| `SMS_DAILY_CAP` | `500` | no | SMS sent per day at most (India time), the last line behind the fixed limits per number, account and purpose; counted in the database (RUNBOOK.md "SMS") |

### Sign-in providers and Turnstile

| Variable | Default | Required | What it does; where to get the value |
|---|---|---|---|
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | none | no | Google sign-in; offered only when both are set; from the OAuth client of section 15 |
| `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY` | none | no | Cloudflare Turnstile on sign-up, code requests, the coupon and the quotation forms; on only when both are set; from the Turnstile widget of section 15 |

### Razorpay and the shop

| Variable | Default | Required | What it does; where to get the value |
|---|---|---|---|
| `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET` | none | to take online payments | API keys (`rzp_test_…` until going live; Dashboard → Account & Settings → API Keys); empty: the payment page says online payment is not set up |
| `RAZORPAY_WEBHOOK_SECRET_TEST`, `RAZORPAY_WEBHOOK_SECRET` | none | for webhooks | the secrets typed when creating the Test Mode and the Live Mode webhook; the one of the keys' mode is checked; empty: every webhook is refused (section 12) |
| `SHOP_OPEN` | `1` | no | 0: only staff use the cart, checkout and payment ("Shop opens soon"), for Razorpay's review on test keys |
| `SHOP_COD_ENABLED` | `0` | no | 1: offer cash on delivery (accounts with a confirmed email address, two orders on their way each) |
| `SHOP_COD_MAX_VALUE` | `1500` | no | the largest cash-on-delivery order, in rupees, shipping included |
| `SHOP_LOW_STOCK` | `5` | no | each morning at 8 the SALES role is emailed the books with fewer copies (RUNBOOK.md "Stock, stock alerts and the low-stock email"); also the dashboard's "running out" |
| `SELLER_LEGAL_NAME`, `SELLER_ADDRESS`, `SELLER_GSTIN`, `SELLER_STATE`, `SELLER_STATE_CODE`, `SELLER_EMAIL`, `SELLER_PHONE` | `ExamLeaf LLP`, `[address], [city], Assam [PIN]`, empty, `AS`, `18`, `[email]`, `[phone]` | required before the shop opens | the seller printed on every invoice (the LLP's registered details; GSTIN empty: "not registered"); no invoice of the real series is numbered while a `[placeholder]` is left |

### Tax

The storefront's GST documents (`shop/tax.py`, `shop/README.md` "Tax"; the panel's Tax module). The HSN and SAC master
and its dated rates live in the database (seeded by the migration, kept from the panel), not here.

| Variable | Default | Required | What it does; where to get the value |
|---|---|---|---|
| `SHOP_SERIES_FROM_FY` | `2027-28` | no | the financial year from which each type of document is numbered in a series of its own; until then `EL` holds every kind of invoice and `CN` the credit notes. Change it only before the year begins: a year's series never changes once it has a document |
| `SHOP_SERIES_PREFIXES` | `tax_invoice=TI,bill_of_supply=BS,invoice_cum_bill_of_supply=IB,credit_note=CN,debit_note=DN,receipt_voucher=RV,refund_voucher=RF` | before 1 April 2027 | the prefixes the CA confirms, as `type=prefix` pairs (any left out keep their default): two capitals or figures each, all different, never `TC`; ERPNext's B2B series must not use them. The server refuses to start otherwise |
| `SHOP_HSN_DIGITS` | `4` | no | how many figures of an HSN or SAC code the documents and the GSTR-1 HSN summary carry: 4 up to ₹5 crore of turnover in the year before, 6 above (the threshold monitor warns at ₹4 crore); 4, 6 or 8 |
| `SHOP_GST_QRMP` | `1` | no | the returns are quarterly under QRMP (GSTR-1 quarterly with the IFF, PMT-06 monthly, GSTR-3B on the 24th for Assam): the tax calendar's dates. The panel's Settings switch it (`staff.manage_settings`) |

### Integrations and shipping

| Variable | Default | Required | What it does; where to get the value |
|---|---|---|---|
| `INTEGRATION_KEYS` | none | once an integration account exists (the web container then refuses to migrate, and so to start, without it: `integrations.E001`) | Fernet keys, separated by commas, newest first, that encrypt the credentials and tokens of the integration accounts (Shiprocket's API user); make one with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`; a value that is not such a key stops the site starting. Kept with the other secrets: a database backup is unreadable without it (RUNBOOK.md "Integration keys") |
| `INTEGRATIONS_CONNECT_TIMEOUT`, `INTEGRATIONS_READ_TIMEOUT` | `5`, `20` | no | seconds a call to a provider waits to connect, then for its answer |
| `INTEGRATIONS_RETENTION_DAYS` | `90` | no | the call log, the inbound events and the dead letters dealt with go after this many days |
| `SHIPPING_PACKING_GRAMS` | `50` | no | the packing's weight, added to the books' (`Product.weight_grams`, which must be filled in) |
| `SHIPPING_PARCEL_CM` | `25,20,3` | no | a parcel's length, breadth and height in cm when staff give none (a flyer) |
| `SHIPPING_QUOTE_TIMEOUT` | `3` | no | seconds the booking screen's quote waits for Shiprocket before showing its last answer |
| `SHIPPING_MIN_RATING`, `SHIPPING_MAX_DAYS` | `4`, `7` | no | the quote ranks first the cheapest couriers rated this much or more that deliver within this many days |
| `SHIPPING_GYAN_POST` | `0` | no | 1: India Post's Gyan Post priced beside the couriers for prepaid orders, only once the postal division has confirmed in writing that the books qualify (research 6.1) |
| `SHIPPING_SURVEY_BATCH` | `500` | no | North-East PINs whose couriers are asked each Sunday, the oldest answers first |
| `API_THROTTLE_PARCEL_EVENTS` | `300/minute` | no | the couriers' webhook, per client address |

### Buckets and media

Set `MEDIA_BUCKET`, `PUBLIC_MEDIA_BUCKET` and `PUBLIC_MEDIA_DOMAIN` together or not at all (section 15, "Cloudflare R2",
and section 17).

| Variable | Default | Required | What it does; where to get the value |
|---|---|---|---|
| `MEDIA_BUCKET` | none (the `media` volume) | no | the private bucket: invoices, credit notes, quotations, answer sheets and the course's videos; links signed for 5 minutes (the course's videos: 10; a clip upload: 15) |
| `PUBLIC_MEDIA_BUCKET`, `PUBLIC_MEDIA_DOMAIN` | none | with `MEDIA_BUCKET` | the public bucket and its domain (`media.examleaf.in`, no `https://`): product pictures, their AVIF and WebP sizes, the link-preview pictures; cached a year; the CSP allows the domain for images |
| `S3_ENDPOINT_URL` | none (AWS) | with buckets on R2 | `https://<ACCOUNT_ID>.r2.cloudflarestorage.com` (R2 → the account id); empty for AWS S3 |
| `S3_REGION` | `auto` | no | R2: `auto`; AWS S3 Mumbai: `ap-south-1` |
| `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` | none | with buckets | an API token with Object Read & Write on the two buckets (R2 → Manage API tokens); not the `AWS_*` or `SES_*` keys |
| `PUBLIC_S3_ENDPOINT_URL`, `PUBLIC_S3_REGION`, `PUBLIC_S3_ACCESS_KEY_ID`, `PUBLIC_S3_SECRET_ACCESS_KEY` | the `S3_*` values | no | the public bucket's own, when the private one is on AWS S3 Mumbai and the public one stays on R2 |
| `AWS_REQUEST_CHECKSUM_CALCULATION`, `AWS_RESPONSE_CHECKSUM_VALIDATION` | `when_required` (compose sets both; `.env.example` ships them) | with R2 | boto3 sends checksums R2 refuses unless these are `when_required`; keep them when running outside Docker |

### Revision course and Firebase

| Variable | Default | Required | What it does; where to get the value |
|---|---|---|---|
| `LEARN_MAX_UPLOAD_MB` | `500` | no | the largest clip video the admin accepts, in MB (checked before the upload starts and again by the media worker; without a bucket Caddy's 500 MB limit applies too: section 18) |
| `LEARN_PUBLIC_VIDEO` | `0` | no | 1: processed clips go to the public bucket (plain links on `PUBLIC_MEDIA_DOMAIN`, cached by Cloudflare: cheaper, but anyone with a link can watch); 0: the private storage, links signed for 10 minutes. Run `reprocess_clips --all` after changing it |
| `LEARN_FREE_PREVIEW` | `1` | no | 1: the first clip of every revision, any clip marked as a free preview, and the first chapter's flash cards are free to any signed-in student |
| `LEARN_ACCESS_DAYS` | `365` | no | days a book code or a purchase opens the course for, from that day |
| `LEARN_CODE_SECRET` | none | required on a server | the key of the book codes' hashes: random, 50 characters or more, like `SECRET_KEY`; set it once, before the first print run, and never change it (printed codes would stop working); with `DEBUG=0` and no value `migrate` stops (check `learn.E001`), so the web container does not start, and `make_book_codes` refuses |
| `FCM_SERVICE_ACCOUNT_JSON` | none | for the daily reminders | the Firebase service account's JSON on one line, or the path of the file inside the container (section 15, "Firebase"); empty: no reminders are sent |

### REST API

| Variable | Default | Required | What it does; where to get the value |
|---|---|---|---|
| `CORS_ALLOWED_ORIGINS` | none | no | web origins allowed to call `/api/` from a browser, comma separated (the app and the site need none) |
| `JWT_ACCESS_MINUTES`, `JWT_REFRESH_DAYS` | `15`, `30` | no | lifetimes of the API's access and refresh tokens |
| `JWT_SIGNING_KEY` | `SECRET_KEY` | no | the key the API's tokens are signed with; changing it logs every app out, not the website (RUNBOOK.md) |
| `API_THROTTLE_ANON`, `API_THROTTLE_USER`, `API_THROTTLE_AUTH` | `200/minute`, `600/minute`, `30/minute` | no | API rate limits per client address (anonymous), per user, and for log-in, sign-up, codes, passwords, data export and deletion |
| `API_THROTTLE_ORDER_LOOKUP`, `API_THROTTLE_PAYMENT`, `API_THROTTLE_COUPON` | `10/hour`, `30/minute`, `10/hour` | no | guests' order lookup per address; starting and confirming payments; coupon codes tried per user |
| `API_THROTTLE_LEARN_REDEEM`, `API_THROTTLE_LEARN_REDEEM_ADDRESS`, `API_THROTTLE_LEARN_QUIZ` | `5/hour`, `5/hour`, `600/hour` | no | book codes tried per user and per client address (raise the second before a teacher has a classroom redeem together), and quiz answers per user |

### Logging and Sentry

| Variable | Default | Required | What it does; where to get the value |
|---|---|---|---|
| `LOG_JSON` | `1` with `DEBUG=0`, else `0` | no | log lines as JSON, or text; gunicorn's own lines too (`gunicorn.conf.py`: JSON unless `0`) |
| `LOG_LEVEL` | `INFO` | no | the log level |
| `SENTRY_DSN` | empty (off) | no | error reports, scrubbed of personal data (`examleaf/sentry.py`); the project's DSN from Sentry (section 15) |
| `SENTRY_ENVIRONMENT` | `production` | no | Sentry's environment name |
| `SENTRY_TRACES_SAMPLE_RATE` | `0` | no | share of requests traced (0 to 1) |
| `RELEASE` | none | no | a version label (e.g. the git commit) for Sentry; also names the service worker's cache, which otherwise follows the static files' hashed names, and is kept as each insights forecast run's code version |

### Insights

| Variable | Default | Required | What it does; where to get the value |
|---|---|---|---|
| `INSIGHTS_ALERT_EMAILS` | none | recommended | comma-separated addresses for the nightly email of new fraud signals and print runs to reprint now (section 21); empty: no email |
| `INSIGHTS_HASH_SALT` | `SECRET_KEY` | recommended | the key of the hashes the fraud rules count by (accounts, IP addresses, phone numbers, addresses, book codes): random, 50 characters or more, like `SECRET_KEY`; a new value (or a new `SECRET_KEY` while this is empty) starts the counts afresh |

### Backups

Read by `scripts/backup.sh` (which takes `BACKUP_KEEP_DAYS` and `BACKUP_AGE_RECIPIENT` straight from `.env`) and by
`manage.py upload_backup` (the rest).

| Variable | Default | Required | What it does; where to get the value |
|---|---|---|---|
| `BACKUP_BUCKET` | none | recommended | the private bucket that receives the database dumps; without it they stay on the server's disk (section 9) |
| `BACKUP_ENDPOINT_URL` | none (AWS) | with R2 or B2 | the bucket's S3 endpoint, e.g. `https://<ACCOUNT_ID>.r2.cloudflarestorage.com` |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | none | with `BACKUP_BUCKET` | the backup bucket's keys (the media buckets have `S3_*`, SES has `SES_*`) |
| `BACKUP_KEEP_DAYS` | `30` | no | days of local dumps kept (match the Privacy Policy) |
| `BACKUP_AGE_RECIPIENT` | none | recommended with a bucket | an age public key (`age1…`, from `age-keygen`; keep the private key off the server): the uploaded dumps are encrypted to it (section 9) |

### Staff (the Admin Control Panel's backend)

`staff/README.md`; section 23 for the audit log's database role, its copy and its retention.

| Variable | Default | Required | What it does; where to get the value |
|---|---|---|---|
| `ADMIN_HOSTS` | none: every host | with the panel | the hosts the staff API answers on (`admin.examleaf.in`), comma separated; on any other it answers 404. Each must be in `ALLOWED_HOSTS` too, and its `https://` origin in `CSRF_TRUSTED_ORIGINS` (the panel's session sends the CSRF token) |
| `STAFF_IDLE_TIMEOUT` | `1800` | no | seconds without a request after which a staff session ends (website, panel and admin) for the roles without a limit of their own; OWNER, ADMIN, FINANCE and PACKER have 15 minutes (`STAFF_IDLE_TIMEOUTS` in settings.py); a staff session also ends 8 hours after its log-in |
| `STAFF_POLICIES` | none | before staff start | the policies staff acknowledge, each version once, as `key=version` pairs (`acceptable_use=2026-10,childrens_data=2026-10,confidentiality=2026-10,incident_reporting=2026-10`, research 6); a new version asks everyone again (the manifest's `policies_due`). Publish the texts where staff read them (the panel links them by key) |
| `STAFF_BREAK_GLASS_HOURS` | `2` | no | a break-glass session (a superuser's) ends this many hours after its log-in however busy; it gives its reason first (`POST /api/v1/staff/session/reason/`), and the owners are told at its start and its end (RUNBOOK.md "Break-glass accounts") |
| `STAFF_ALERT_EMAILS` | every active member of OWNER | recommended | who gets the owners' alerts at once (a break-glass log-in, a privileged role given, an override, an API key, an impersonation, maintenance on, an incident, a staff lock-out or offboarding, a broken audit chain or a failed export), comma separated |
| `STAFF_PANEL_URL` | `SITE_URL` | with the panel | the panel's address (`https://admin.examleaf.in`): staff invitations link to its `/invite/<token>/` page |
| `STAFF_CHANGE_REQUEST_HOURS`, `STAFF_DORMANT_DAYS` | `24`, `45` | no | how long a change request waits before it expires; after how many days without a log-in the access review flags a member of staff |
| `STAFF_TEST_MODE` | `DEBUG`'s | on staging | `1` on any deployment that is not the production site: the panel shows its TEST band (the manifest's `flags.test_mode`) |
| `STAFF_AUDIT_RETENTION_DAYS`, `STAFF_AUDIT_MONEY_RETENTION_FY` | `730`, `8` | no | the audit log's retention (`manage.py purge_audit`): days of the general chain (365 at least), financial years of the money chain (8 at least); the site refuses to start below |
| `STAFF_DATA_REQUEST_ACK_HOURS`, `STAFF_DPDP_RULES_FROM`, `STAFF_DPDP_RESPONSE_DAYS` | `48`, `2027-05-13`, `90` | no | a data request's clocks: acknowledged within the hours; answered within a month until the date (the DPDP Rules' rights), within the days after it; move the date if MeitY brings it forward |
| `DATA_PROTECTION_OFFICER` | a `[placeholder]` | before going live | the contact person for personal data, quoted in every answer to a data request (DPDP Rules r.9); also a panel setting (Legal and privacy, Disclosures), which wins once set, beside the Grievance Officer's own name, designation and contact there |
| `CERT_IN_POINT_OF_CONTACT` | a `[placeholder]` | before going live | the point of contact registered with CERT-In (Annexure II of its Directions), quoted in every incident alert; also a panel setting (Disclosures), never shown on the website |
| `STAFF_THROTTLE`, `STAFF_THROTTLE_SEARCH`, `STAFF_THROTTLE_REVEAL`, `STAFF_THROTTLE_EXPORT`, `STAFF_THROTTLE_MONEY`, `STAFF_THROTTLE_INVITE` | `600/minute`, `60/minute`, `30/hour`, `10/hour`, `120/hour`, `10/hour` | no | the staff API's limits per member of staff or API key (API.md "Rate limits") |
| `STAFF_GOOGLE_DOMAIN` | none: off | with Google for staff | the Workspace's domain (`examleaf.in`): a staff Google sign-in (on the admin host, into a staff account, or by an account of the domain) needs the ID token's `hd` to be it and a confirmed address (section 15, "Google sign-in for staff") |
| `STAFF_GOOGLE_CLIENT_ID`, `STAFF_GOOGLE_CLIENT_SECRET` | none | recommended with the domain | the Workspace's own OAuth client (an Internal consent screen) for the admin host; without them the website's `GOOGLE_*` client serves the admin host too |
| `STAFF_GOOGLE_AUTO_STAFF` | `0` | no | `1`: a Workspace account of the domain with no ExamLeaf account signs up through Google as a member of staff with no role (an owner gives one); off, the account must exist already and be staff |

### ERPNext

`erp/README.md`; section 24 for the account, the webhook and the order of the switches. Each switch is also a feature
flag of the same name the panel can set (`staff/README.md`), which wins over the environment until set back to null.

| Variable | Default | Required | What it does; where to get the value |
|---|---|---|---|
| `ERP_ENABLED` | `0` | to sync | the platform talks to ERPNext: the relay, the pull, the reconciliation and ERPNext's webhooks (off: the flows' rows wait, the webhooks are refused) |
| `ERP_SYNC_CATALOGUE`, `ERP_SYNC_INVOICES`, `ERP_SYNC_PAYMENTS`, `ERP_SYNC_DELIVERIES`, `ERP_SYNC_SETTLEMENTS` | `0` | per flow | each flow writes its events to the outbox (items and bundles; invoices and credit notes; payments and refunds; delivery notes; COD settlements) |
| `ERP_PULL_STOCK`, `ERP_PULL_B2B` | `0` | per read | ERPNext's stock (snapshots, the nightly stock check) and its B2B documents (read-only copies) read back, by doorbell and every 15 minutes |
| `ERP_STOCK_PROJECTION` | `0` | at the cut-over | ERPNext's stock sets the copies for sale (less what its orders hold and what is reserved here); off: shadow mode, only compared |
| `ERP_WAREHOUSE` | `Main` | no | the storefront's warehouse in ERPNext (examleaf_erp's `Main`, `Damaged`, `At Printer`, without the company suffix) |
| `ERP_MAX_ATTEMPTS` | `10` | no | tries before an outbox row is dead (the delay doubles from a minute, jittered: 10 tries take some 4 to 8 hours) |
| `ERP_ALERT_EMAILS` | none | recommended | comma-separated addresses for the morning's reconciliation differences (FINANCE) |
| `ERP_MODE` | `erpnext` | no | `fake`: an in-memory ERPNext (development only) |
| `ERP_INSTANCE_PREFIX` | empty | when two platforms send to one ERPNext site | goes before every idempotency key (`staging-`), so that a staging copy and production never answer each other's |
| `API_THROTTLE_ERP_EVENTS` | `600/minute` | no | ERPNext's webhook, per client address |

## 14. Security settings

**Health checks.** From the internet Caddy answers `/health/`, `/health/web/`, `/health/live/` and
`/health/integrations/` (section 21) with 404 unless the request carries the header `X-Health-Token: <HEALTH_CHECK_TOKEN>`
(Caddyfile). Set the token in `.env` (letters, digits, `-` and `_`;
`secrets.token_urlsafe` gives that) and in the uptime monitor's request headers (UptimeRobot's paid plans, Better
Stack, Uptime Kuma and most others can send one). The web container's own health check calls `127.0.0.1:8000` and
needs no token. Caddy reads the token from its own environment, so docker-compose.yml passes it on:

```yaml
  caddy:
    environment:
      DOMAIN: ${DOMAIN:?set DOMAIN in .env}
      HEALTH_CHECK_TOKEN: ${HEALTH_CHECK_TOKEN:?set HEALTH_CHECK_TOKEN in .env}
```

Without it in Caddy's environment nobody gets through, the monitor included. The API has no health endpoint.

**Staff accounts.** The admin's log-in is allauth's: its limit of failed log-ins per account applies, and every member
of staff must set up an authenticator app (TOTP, with ten recovery codes) or a passkey before anything else opens. They
log in with the password and then the app or a passkey, never with a passkey alone, and the API gives them no tokens for
a password or an SMS code (they log in through allauth.headless). Their sessions end 8 hours after the log-in, and
after 15 minutes without a request for OWNER, ADMIN, FINANCE and PACKER, 30 for the others (`STAFF_IDLE_TIMEOUT`);
each log-in emails the person the time, the address and the browser. RUNBOOK.md, "Staff accounts", has the steps for
a new member of staff and for a lost phone; the Admin Control Panel's staff API does the same with an audit trail
(section 23). Periodic tasks, task results, groups, permissions, second factors and the Google sign-in apps and
accounts can be changed by superusers only (the ADMIN and OWNER roles see them), and only a superuser changes a
superuser's account or gives roles in the admin. Superusers are the sealed break-glass accounts only (section 23).

**Parental consent (before May 2027).** The DPDP Rules, 2025 ask for verifiable consent of a parent before a child's
data is processed, from May 2027 (18 months after the Rules were notified in November 2025). Until then the site runs
with `PARENTAL_CONSENT_MODE=declared` (the parent ticks the box on the sign-up form). To switch, before that date:

1. Edit the Privacy page in the admin ("Students under 18": the parent confirms through a link emailed to them) and
   change its version.
2. Set `PARENTAL_CONSENT_MODE=verified` in `.env` and `docker compose up -d`.

From then on a student under 18 must give a parent's email address (or, with SMS on, an Indian mobile number: the link
then goes by SMS; RUNBOOK.md "Parental consent" has what that does not prove) at sign-up; the parent gets a link valid
for 7 days, and until they press "I agree" the account can log in and read the solutions but not save marks or order
books. The link goes once the student has confirmed their own address, in fixed text that names the student only when
the name is plain letters; one parent's address or number gets at most 3 links a day. The student can send the link
again, also to a corrected address, from My account (every 10 minutes at most). Students under 18 who registered before
the switch are in the same state until a parent confirms: email them (RUNBOOK.md, "Parental consent").

**Supply chain.** `.github/dependabot.yml` (repository root) opens weekly pull requests for the pip requirements and the
GitHub Actions; switch on Dependabot alerts and security updates in the repository's Settings → Code security. Jazzband,
which publishes django-axes, django-model-utils, django-taggit, django-redis, django-widget-tweaks,
djangorestframework-simplejwt and tablib, is winding down (archived in early 2027; PyPI ownership moves to each
project's leads through December 2026): before merging a bump of one of them, check on PyPI who published the release.

**Recommended next steps** (not done yet):
- Lock the requirements with hashes (`pip-compile --generate-hashes`, or `uv pip compile --generate-hashes`, then
  `pip install --require-hashes`), with a `#sha256=` on the django-celery-beat archive until a release supports
  Django 6.1.
- Pin the base images by digest (`FROM python:3.14-slim@sha256:…`, and the same for postgres, redis and caddy in
  docker-compose.yml) and the CI actions by commit SHA; Dependabot already proposes updates for pip and the GitHub
  Actions, and could do so for the Docker images once `.github/dependabot.yml` lists them.
- Make the `dependency-audit` CI job blocking once its first findings are dealt with.

## 15. Accounts to open

Everything outside the server that the site needs or can use. These take days or weeks of calendar time and no code:
start them now. Each ends with values for `.env` (section 13 lists them). The costs are those these documents state
(this file; `../docs/research/2026-10-08-production-features/report.md` for SMS and Turnstile).

| Account or service | What it is for | How long | Cost, where stated | What to do | Fills | Needed |
|---|---|---|---|---|---|---|
| **Domain registrar and DNS** | the site's address; the QR codes printed in the books point at it for years | an hour, then the DNS wait | not stated | register `examleaf.in` for 10 years with auto-renew and the registrar lock, and a spare domain (another extension) that redirects to it; the `A` and `AAAA` records (section 2) | `SITE_URL`, `ALLOWED_HOSTS`, `DOMAIN` | required |
| **Server (VPS)** | runs the whole stack in Docker | an hour | not stated (2 vCPU / 4 GB is plenty) | section 3 | none | required |
| **GitHub** | the code (the server clones it), CI, Dependabot | minutes | not stated | a read-only deploy key on the server; Dependabot alerts and security updates (section 14) | none | required for the clone; CI and Dependabot optional |
| **Email: Amazon SES in Mumbai**, or Brevo or Postmark | every sign-up code, password reset and order mail; bounce and complaint webhooks through SNS | 1 to 3 days | SES $0.10 per 1,000 emails, new AWS accounts get $200 of credits for 6 months; Brevo's free plan stops at 300 emails a day | "Email: Amazon SES" below | `EMAIL_BACKEND`, `DEFAULT_FROM_EMAIL`, `SES_*`, `ANYMAIL_*` | required (a provider; SES for production) |
| **Razorpay** | online payments, refunds, Payment Links for staff orders | test keys at once; activation (KYC, the website review) takes calendar time, not stated | not stated | section 12 | `RAZORPAY_*`, `SHOP_OPEN` | required to sell online |
| **Cloudflare: DNS, R2 buckets, the media domain** | product pictures and private files in buckets; `media.examleaf.in` | an hour, once the DNS is on Cloudflare | free plan for DNS; R2: 10 GB, a million writes and ten million reads a month free, no fee for traffic (2026-10) | "Cloudflare R2" below | `MEDIA_BUCKET`, `PUBLIC_MEDIA_*`, `S3_*` | optional: files stay in the `media` volume until then |
| **Cloudflare Turnstile** | a bot check on sign-up, code requests, coupon and quotation forms | 10 minutes | free | "Cloudflare Turnstile" below | `TURNSTILE_*` | optional |
| **MSG91 with TRAI DLT registration** (entity, header, templates) | SMS: phone log-in, order updates, parents' consent links | 1 to 2 weeks | DLT about Rs 5,900 with GST, once; MSG91 about Rs 0.25 down to 0.16 per SMS | "SMS: TRAI DLT and MSG91" below | `SMS_BACKEND`, `MSG91_*`, `SMS_DAILY_CAP` | optional: without it no phone log-in, order SMS or SMS consent links |
| **Google Cloud (OAuth client)** | "Log in with Google" | an hour | not stated | "Google sign-in" below | `GOOGLE_*` | optional |
| **Google Workspace (an Internal OAuth client)** | staff sign in with their Workspace account | an hour | the Workspace's | "Google sign-in for staff" below | `STAFF_GOOGLE_*` | optional |
| **Firebase (FCM service account)** | the revision course's daily push reminder | minutes | not stated | "Firebase" below | `FCM_SERVICE_ACCOUNT_JSON` | optional |
| **AWS S3 Mumbai** | the private bucket, only if the Privacy Policy promises that students' files stay in India | an hour | not stated | step 6 of "Cloudflare R2" below | `S3_REGION=ap-south-1`, `S3_*`, `PUBLIC_S3_*` | optional |
| **Backup bucket** (R2, Backblaze B2 or AWS S3) and an age key | off-site, encrypted database dumps | an hour | not stated | section 9 | `BACKUP_*`, `AWS_*` | recommended: without it the dumps stay on the server's disk |
| **Sentry** | error reports without personal data | minutes | not stated | "Sentry" below | `SENTRY_DSN`, `SENTRY_ENVIRONMENT`, `RELEASE` | optional |
| **Uptime monitor** (UptimeRobot's paid plans, Better Stack, Uptime Kuma …) | calls `/health/` and alerts; it must send the header `X-Health-Token` | minutes | not stated | section 14 | `HEALTH_CHECK_TOKEN` (also in the monitor) | the token is required; the monitor is recommended |
| **data.gov.in** | the PIN code directory (CSV, once a year) | 15 minutes | free sign-in; Government Open Data Licence – India (credit required) | "The PIN code directory" below | none (`import_pincodes`) | optional: without the table nothing is checked |

No account is needed for: Let's Encrypt certificates (Caddy gets them itself), Pwned Passwords (the password check; only
a hash prefix leaves the server), passkeys, the tracking pages of Delhivery, Blue Dart,
Ekart and 17TRACK (links only), and the image build (the base images from Docker Hub, Debian and PyPI packages, and the
django-celery-beat archive from GitHub).

### SMS: TRAI DLT and MSG91 (1 to 2 weeks)

Until this is done the site has no phone log-in, no order SMS and no SMS consent links: with `SMS_BACKEND=console` (the
default) a server shows none of them.

1. **Principal Entity.** Register ExamLeaf LLP on one operator's DLT portal (Jio TrueConnect, Airtel, Vodafone Idea
   VILPOWER or BSNL; it is shared with all operators). About Rs 5,900 with GST, once. Documents: the LLP's PAN, GST or
   TAN certificate, the LLP certificate, an authorisation letter for the signatory and the signatory's ID. 3 to 7 days;
   the result is a 19-digit PE ID.
2. **Header** (sender ID): 6 letters, e.g. `EXMLEF`. 1 to 3 days.
3. **Templates**, one per kind, with the exact texts and categories of RUNBOOK.md "SMS" (each `{#var#}` holds at most
   30 characters). 1 to 3 days each.
4. **URL whitelisting:** the consent template contains `https://examleaf.in/c/`; whitelist the domain in the portal
   (since 1 October 2024 an SMS with an unlisted link is blocked).
5. **MSG91:** open an account; bind MSG91 to the PE ID as telemarketer in the DLT portal (MSG91's panel shows how;
   since 11 December 2024 an SMS on an unbound path is rejected); enter the PE ID, header and templates in MSG91 (the
   OTP template under OTP, the others as Flow templates) and copy each template's MSG91 id.
6. **Authkey:** MSG91 → API: create an authkey. Its IP security is on: whitelist the server's outgoing IP
   (`curl -4 ifconfig.me` on the server), or every call fails with error 418.
7. **`.env`:** `SMS_BACKEND=msg91`, `MSG91_AUTHKEY` and the five `MSG91_TEMPLATE_…` ids; `docker compose up -d`. Then
   add your own number on My account: the code must arrive. If not, Admin → Ops → SMS log says "refused by the
   provider" and the log (and Sentry) has MSG91's reason; compare with a test call from MSG91's API page.

### Google sign-in (an hour)

In the Google Cloud console (console.cloud.google.com), with the company's Google account:

1. Create a project "ExamLeaf".
2. Google Auth Platform → Branding: app name ExamLeaf, a support email, home page `https://examleaf.in/`, privacy policy
   `https://examleaf.in/privacy/`, authorised domain `examleaf.in`. No logo at first (a logo starts a brand review).
3. Audience: External, then "Publish app" (while Testing, only 100 listed users can sign in, and only for 7 days).
4. Data access: `openid`, `email`, `profile` only (not sensitive: no Google review, no user cap).
5. Clients → Create client → Web application. Authorised JavaScript origin `https://examleaf.in`; authorised redirect
   URI `https://examleaf.in/account/google/login/callback/` (and `http://localhost:8000/account/google/login/callback/`
   for development).
6. `.env`: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`; `docker compose up -d`. The website's log-in page then offers
   Google (with PKCE, through `/_allauth/browser/v1/auth/provider/redirect`; Google comes back to Django's callback
   above, which returns to the website). A new student fills in the student details after Google (class, board, date
   of birth, parent, consent); an address that already has an account logs in as before and can connect Google
   afterwards on the website's Security page (`/account/security/`).
7. For the app (section 20): also create an Android client (package name, SHA-1 of the signing certificate) and an iOS
   client (bundle ID) in the same project. The app asks Google for an ID token issued for the web client
   (`GOOGLE_CLIENT_ID`, its "server client ID") and posts it to `/_allauth/app/v1/auth/provider/token`; the server
   accepts only tokens for that client.

### Google sign-in for staff (an hour, with the Workspace)

The staff sign in on the admin host with their Google Workspace account, and their second factor after it. In the
Google Cloud console, with an administrator account of the company's Workspace (the organisation of `examleaf.in`):

1. A project under the Workspace's organisation (an Internal audience needs one): "ExamLeaf staff".
2. Google Auth Platform → Branding: app name "ExamLeaf staff", a support email. Audience: **Internal**: only accounts
   of the organisation can sign in (no Google review, no user cap, no "Publish").
3. Data access: `openid`, `email`, `profile` only.
4. Clients → Create client → Web application. Authorised JavaScript origin `https://admin.examleaf.in`; authorised
   redirect URI `https://admin.examleaf.in/account/google/login/callback/` (the admin host's: its Caddy site sends
   `/account/google/*` to Django).
5. `.env`: `STAFF_GOOGLE_CLIENT_ID`, `STAFF_GOOGLE_CLIENT_SECRET`, `STAFF_GOOGLE_DOMAIN=examleaf.in`, with
   `ADMIN_HOSTS=admin.examleaf.in` (section 23); `docker compose up -d`. The admin host's `config/` then says
   `google: true` and its Google button uses this client; the website keeps its own (above). Without the two client
   values the website's client serves the admin host too: add the admin host's redirect URI to it, and the domain check
   below is the only gate.
6. Each member of staff connects Google once: signed in with the password and the second factor, on the website's
   Security page (`/account/security/`), with their `@examleaf.in` account. Accounts are linked by Google's `sub`, never
   by the address. From then on Google signs them in on the admin host, and the authenticator app or the passkey is
   still asked after it. (`STAFF_GOOGLE_AUTO_STAFF=1` instead lets a Workspace account with no ExamLeaf account sign up
   there, as a member of staff with no role until an owner gives one; it then sets up its second factor first.)
7. Refused, each an `authz_fail` in the audit log and `?error=` at the console's callback: on the admin host, into a
   staff account or by an account of the domain, a Google account whose ID token's `hd` is not the domain or whose
   address Google has not confirmed (`staff_google_domain`: the request's `hd` parameter is only a hint, the server
   checks the claim); a break-glass account (`staff_google_break_glass`: they stay outside Google sign-in); a Workspace
   account with no staff account (`staff_google_no_account`), or one linked to an account that is not staff
   (`staff_google_not_staff`). A student's Google sign-in on the website is as before.
8. Leaving: suspend the person's Workspace account (no new sign-ins) and offboard them in the panel
   (`people/<id>/offboard/`): a suspended Google account does not end the sessions already open.

### Email: Amazon SES in Mumbai (1 to 3 days)

Brevo's free plan stops at 300 emails a day, and every sign-up and code is an email; SES costs $0.10 per 1,000.

1. An AWS account (new accounts get $200 of credits for 6 months); region Asia Pacific (Mumbai), `ap-south-1`.
2. SES → Identities → Create identity → domain `examleaf.in`, Easy DKIM (RSA 2048), custom MAIL FROM domain
   `mail.examleaf.in`. Add the DNS records SES shows: three DKIM `CNAME`s (`<token>._domainkey` to
   `<token>.dkim.amazonses.com`), and for `mail.examleaf.in` an `MX 10 feedback-smtp.ap-south-1.amazonses.com` and a
   `TXT "v=spf1 include:amazonses.com ~all"`. DMARC: a `TXT` record at `_dmarc.examleaf.in`,
   `v=DMARC1; p=none; rua=mailto:dmarc@examleaf.in`; after two to four weeks of clean reports, `p=quarantine`.
3. SES → Account dashboard → Request production access (the sandbox sends only to verified addresses, 200 a day):
   transactional email, the website, and that bounces and complaints are suppressed automatically. About 24 hours.
4. IAM: a user `examleaf-ses` allowed `ses:SendEmail`, `ses:SendRawEmail` and `sns:ConfirmSubscription` only; its
   access key goes into `SES_ACCESS_KEY_ID` and `SES_SECRET_ACCESS_KEY` (not the S3 keys).
5. `.env`: `EMAIL_BACKEND=anymail.backends.amazon_ses.EmailBackend`,
   `DEFAULT_FROM_EMAIL=ExamLeaf <noreply@examleaf.in>`, `ANYMAIL_WEBHOOK_SECRET=<user>:<password>` (random letters and
   digits), `ANYMAIL_AMAZON_SES_CONFIGURATION_SET_NAME=examleaf`; `docker compose up -d`.
6. SES → Configuration sets → Create `examleaf` → Event destination: Amazon SNS, events Send, Delivery, Bounce,
   Complaint and Reject (not opens and clicks), a new SNS topic in `ap-south-1`. SNS → the topic → Create
   subscription: HTTPS, `https://<user>:<password>@examleaf.in/anymail/amazon_ses/tracking/`. Anymail confirms the
   subscription itself (the secret must be set first). The `/anymail/` URLs exist only while
   `ANYMAIL_WEBHOOK_SECRET` is set: without it Anymail would accept events from anyone.
7. Test: send a sign-up code to `bounce@simulator.amazonses.com`; Admin → Ops → Email suppressions shows it.

Brevo or Postmark instead (the first weeks, say): their `EMAIL_BACKEND` and `ANYMAIL_…` key (`ANYMAIL_BREVO_API_KEY`),
and in their panel a webhook `https://<user>:<password>@examleaf.in/anymail/brevo/tracking/` (or `postmark`) for hard
bounces, spam complaints and blocked or invalid addresses.

### Cloudflare Turnstile (10 minutes; when bots or SMS pumping show up, or from the start)

Cloudflare dashboard → Turnstile → Add widget: hostname `examleaf.in`, mode Managed. `.env`: `TURNSTILE_SITE_KEY`,
`TURNSTILE_SECRET_KEY`. Sign-up, "Log in with a code", the coupon form and the quotation form then ask for the check
(the website's and the app's allauth.headless sign-up and code request, `cart/coupon/` and `quotes/` take the token as
`turnstile`, API.md "Turnstile"; the older `auth/registration/` and `auth/phone/code/` do not); the website shows the
widget (its CSP allows `challenges.cloudflare.com` only then). If
Cloudflare cannot be reached within 5 seconds the form goes through and the log says so.

### Cloudflare R2 and the media domain (an hour, once the domain's DNS is on Cloudflare)

Until this is done every upload stays in the `media` volume and product pictures are served by Django under
`/shop/media/`; that works, but puts the pictures' traffic on the server and the volume in the backups' way.

1. **DNS on Cloudflare** (free plan): add `examleaf.in`, copy the records it finds, check them against section 2, then
   change the nameservers at the registrar; wait until the zone shows Active. Leave the site's own records
   "DNS only" (grey cloud) for now: putting Cloudflare's proxy in front of the site later means changing `PROXY_COUNT`
   and Caddy's trusted proxies so that axes, allauth and the API still see the client's address (not set up in the
   shipped files).
2. **Two buckets** (R2 → Create bucket, location hint Asia-Pacific): `examleaf-private` and `examleaf-public`. Never
   give the private one a public URL or a custom domain: its files (invoices, credit notes, quotations, answer
   sheets, the course's videos) are reached only by links the site signs for 5 minutes (the videos: 10).
3. **The media domain:** `examleaf-public` → Settings → Custom Domains → `media.examleaf.in` (Cloudflare adds the record
   and the certificate). Leave the `r2.dev` URL off.
4. **Keys:** R2 → Manage API tokens → Create: Object Read & Write, the two buckets only. `.env`: `S3_ACCESS_KEY_ID`,
   `S3_SECRET_ACCESS_KEY`, `S3_ENDPOINT_URL=https://<ACCOUNT_ID>.r2.cloudflarestorage.com`, `S3_REGION=auto`,
   `MEDIA_BUCKET=examleaf-private`, `PUBLIC_MEDIA_BUCKET=examleaf-public`, `PUBLIC_MEDIA_DOMAIN=media.examleaf.in`.
   They are not the `AWS_*` keys of the backup bucket or the `SES_*` ones of the email. Better still, a second token
   for `examleaf-public` alone in `PUBLIC_S3_ACCESS_KEY_ID` and `PUBLIC_S3_SECRET_ACCESS_KEY` (and `PUBLIC_S3_ENDPOINT_URL`
   as above): without them the public files use the private bucket's key (SECURITY_REVIEW_PHASE5_6.md L12).
5. **Files already uploaded:** before switching, copy the `media` volume's `products/` and `og/` folders to
   `examleaf-public` and everything else (`invoices/`, `credit-notes/`, `quotations/`, `answer-sheets/`, `learn/`) to
   `examleaf-private`, keeping the paths (for example `rclone copy`); the database names them by path. Then restart
   (section 11).
6. **India only:** if the Privacy Policy promises that students' files stay in India, make the private bucket on AWS S3
   in Mumbai instead (Block Public Access on, ACLs disabled; `S3_REGION=ap-south-1`, no `S3_ENDPOINT_URL`, its IAM keys
   in `S3_*`) and give the R2 public bucket its own `PUBLIC_S3_ENDPOINT_URL`, `PUBLIC_S3_REGION=auto`,
   `PUBLIC_S3_ACCESS_KEY_ID` and `PUBLIC_S3_SECRET_ACCESS_KEY`.

### Firebase (push reminders; minutes)

Firebase console → a project for ExamLeaf → add the Android (and iOS) app (the app's developers need its
`google-services.json`). Then a service account that can send pushes and nothing else: Google Cloud console (the same
project) → IAM & Admin → Service accounts → Create → role "Firebase Cloud Messaging API Admin" only → Keys → Add key →
JSON. Not Firebase's "Generate new private key": that account administers the whole project, its users and databases
included (SECURITY_REVIEW_PHASE5_6.md L12). Put the JSON in `.env` as `FCM_SERVICE_ACCOUNT_JSON` (on one line), or the
path of a file mounted into the containers: a `.json` file left in `examleaf-web/` is never copied into the image
(`.dockerignore`). Celery beat queues the reminder at 18:00 and the worker sends it to students who turned it on in the
app, through firebase-admin (FCM HTTP v1); the media worker never sees the key. Without the variable nothing is sent.

### Sentry (minutes)

Sentry → a Django project → copy its DSN into `SENTRY_DSN`; `SENTRY_ENVIRONMENT` (`production`) and `RELEASE` (the git
commit) label the reports. Only the server reports, and every event is scrubbed of personal data first
(README.md, "Personal data").

### The PIN code directory (15 minutes, then once a year)

1. Sign in (free) at data.gov.in and download the CSV of "All India Pincode Directory (till last month)":
   https://www.data.gov.in/resource/all-india-pincode-directory-till-last-month (about 16 MB, one row per post office;
   Government Open Data Licence – India).
2. Load it: `docker compose cp pincodes.csv web:/tmp/pincodes.csv`, then
   `docker compose exec web python manage.py import_pincodes /tmp/pincodes.csv` (it replaces the whole table and stops
   on a state name it does not know: add the spelling to `ALIASES` in `shop/management/commands/import_pincodes.py`).
3. The address forms then fill in the district (when empty) and the state (when the PIN lies in one state) from the PIN
   code, and refuse a state that is not one of the PIN's (the state decides CGST + SGST or IGST). A PIN missing from the
   table is neither filled in nor checked.
4. The licence asks for credit: add "PIN codes: Department of Posts, data.gov.in" to the About page.

### The domain (an hour)

The QR codes printed in the books point at `SITE_URL` for years: register `examleaf.in` for 10 years with auto-renew
and the registrar lock on, and a spare domain (another extension) that redirects to it.

## 16. Sign-in, SMS and email: what is on and what is off

What each setting switches on, and what the site does without it (the variables are in section 13, the steps in
section 15):

| Feature | Needs | Without it |
|---|---|---|
| Sign-up codes, password resets, order and notice emails | a real `EMAIL_BACKEND` | the console backend prints each mail in the web or worker log: nobody receives a code |
| Bounce and complaint handling (the suppression list) | `ANYMAIL_WEBHOOK_SECRET` and the provider's webhook | no `/anymail/` URLs; the list stays empty (staff cannot add to it, only delete from it) |
| Phone log-in, order SMS, SMS consent links | `SMS_BACKEND=msg91` with `MSG91_AUTHKEY` and the template ids (a `console` backend on a server turns all three off) | no phone pages, no SMS, `POST auth/phone/code/` answers 404, and a parent's consent link goes by email only |
| Google sign-in | both `GOOGLE_*` | no Google button |
| Passkeys | nothing to set: HTTPS, and `SITE_URL` the address students use | always on; without HTTPS they work in development only |
| Cloudflare Turnstile | both `TURNSTILE_*` | no check on sign-up, code requests, the coupon and the quotation forms |
| Parental consent by a link | `PARENTAL_CONSENT_MODE=verified` (section 14), and SMS on to text it | the parent ticks the box on the sign-up form |

A passkey belongs to the host name of `SITE_URL` (`examleaf.in`), and would work on `www.` if that name were served too
(DNS, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` and a Caddyfile address). Students add one on My account; staff use one as
their second step after the password (a passkey alone does not log staff in). Phone log-in needs a number confirmed on
My account: sign-up asks for none.

## 17. Storage, media and the web platform

**Where files go.** Without `MEDIA_BUCKET` everything is in the `media` volume: the private files (invoices, credit
notes, quotations, answer sheets, the course's videos) are never served publicly, and the public ones (product pictures
and their sizes, link-preview pictures) are served by Django under `/shop/media/`, only from `products/` and `og/`. With
the three bucket variables (section 15, "Cloudflare R2") the private files go to the private bucket, reached only by
links the site signs for 5 minutes, and the public ones to the public bucket on `PUBLIC_MEDIA_DOMAIN`, cached a year
as immutable (a new upload never reuses a name). The CSP allows the media domain for images.

**Videos in a bucket.** The app gets links signed for 10 minutes; playlists are read through the site, segments and the
poster redirect to the bucket's own signed link. The staff player (`/learn/preview/<clip>/`) fetches segments from the
bucket in the browser: the CSP allows its host on those pages only (`allow_storage` in `learn/uploads.py`), and the
bucket needs a CORS rule (R2 → bucket → Settings → CORS policy):
`[{"AllowedOrigins": ["https://examleaf.in"], "AllowedMethods": ["GET", "PUT"], "AllowedHeaders": ["*"]}]` on
`examleaf-private` (PUT is the editors' direct upload of clip videos, section 18; without it every upload fails with
"The upload was cut off") and the same with GET alone on `examleaf-public` with `LEARN_PUBLIC_VIDEO=1`. The app's own
player needs none of this.

**Pictures.** Covers and pictures uploaded in the admin are saved with AVIF and WebP sizes (django-pictures, on the
worker's default queue); the API gives them to the website's `<picture>` with the original as the fallback. The four
static book covers (`static/img/<subject>.png`, which the website shows) have committed AVIF and WebP copies at 320 and
480 px; `python manage.py build_covers` remakes them and the default link-preview picture `static/img/og-default.jpg`
after a cover changes. A picture over 2 MB is refused in the admin.

**Link previews, search engines and the web app** are the website's (`../examleaf-frontend/`, its README): its tags,
JSON-LD, `sitemap.xml`, `robots.txt`, manifest and service worker. Django gives it a product's link-preview picture (its
cover and title, 1200x630, made by the worker whenever the product is saved and stored in the public storage) and the
product's search-engine title and description through the API.

## 18. Revision course

The app's short revision videos, flash cards and quiz (`learn/`; API.md "Revision course"; RUNBOOK.md "The revision
course"). Nothing is needed to start; what each part needs:

**ffmpeg and the media worker.** The image installs `ffmpeg` (Dockerfile). Clip videos are processed by the
`media-worker` service (docker-compose.yml): a Celery worker on the queue `media` only, one video at a time
(`--concurrency 1`), so a long encode never holds up emails, invoices or refunds on `worker`. A clip of a few minutes
takes a minute or two on two CPU cores; give the server 1 GB of memory more for ffmpeg. `docker compose up -d` starts it
with the rest; `docker compose logs media-worker` shows its work. It runs ffmpeg on files that come from outside, so it
has an environment of its own (section 13: the database, the queue, the buckets and `SECRET_KEY`, none of the other
secrets) and drops all Linux capabilities. In development the clips are processed in the web process when saved
(`brew install ffmpeg`; without it the clip shows "failed" with "ffprobe is not installed").

**Uploads.** Editors upload a clip's video in the admin (at most `LEARN_MAX_UPLOAD_MB`; mp4, mov, m4v, webm or mkv, with
H.264, HEVC, VP9 or AV1 video and AAC, Opus or MP3 sound: anything else fails at once with "Not a video we take"). With
the private bucket set, the editor's browser sends the video straight to the bucket on a link the site signs for 15
minutes (the bucket needs the CORS rule of section 17, with PUT), and the form carries only its signed name: no large
body reaches Caddy or gunicorn, and gunicorn keeps its 60-second timeout. Without a bucket (development) the video comes
with the form, so Caddy allows 500 MB on the clip and revision admin pages only, and `learn.uploads.LargeBodyGuard`
refuses a body over `DATA_UPLOAD_MAX_MEMORY_SIZE` there from anyone who is not signed-in staff. Caddy also gives a
client 10 seconds for its headers and 5 minutes for its body, and reads the body before gunicorn sees the request. For
reference, the Caddyfile block is:

```
@clip_upload path /admin/learn/clip/* /admin/learn/revision/*
request_body @clip_upload {
	max_size 500MB
}
@other not path /admin/learn/clip/* /admin/learn/revision/*
request_body @other {
	max_size 10MB
}
```

If you raise `LEARN_MAX_UPLOAD_MB` above 500 and have no bucket, raise the Caddyfile's `500MB` with it.

**Where the videos live.** The uploaded video (`learn/sources/`) and the processed HLS files (`learn/hls/<clip>/…`: two
renditions, 480×854 and 720×1280, 4-second segments, a poster) go to the private storage: the `media` volume, or the
private bucket once `MEDIA_BUCKET` is set (section 17). Sizes: the two renditions take about 1 MB per 4 seconds (15
minutes for each of the 51 chapters: about 13 GB); the uploaded videos are kept for processing again (a phone's 1080p is
about 1 GB per 15 minutes): on R2 all of it costs about a dollar a month. `LEARN_PUBLIC_VIDEO=1` puts the processed
files in the public bucket instead (plain links on `PUBLIC_MEDIA_DOMAIN`, cached by Cloudflare: cheaper and faster,
but anyone with a link can watch); after switching, `manage.py reprocess_clips --all`.

**The staff player** (`/learn/preview/<clip>/`, the "Preview" link on a clip in the admin) uses hls.js from the site
(`static/learn/hls.min.js`, 1.7.3, with its licence); with buckets it needs the CORS rule of section 17.

**Book codes.** Set `LEARN_CODE_SECRET` before the first print run and never change it (a server does not start without
it): the database keeps only a keyed hash of each code, and codes printed under one key work only with it. Keep a copy
in the password manager with the other secrets. `make_book_codes` and the print run: RUNBOOK.md "Printing book codes".

**Push reminders.** Celery beat sends the daily reminder at 18:00 to students who turned it on in the app, only while
`FCM_SERVICE_ACCOUNT_JSON` is set (section 15, "Firebase").

**First content.** After `import_papers`: `manage.py import_chapter_insights` (the chapters with the Board's marks and
the past papers' question counts, from `production/<subject>/format.json` and `pyq/`) and `manage.py build_quiz_items`
(about 660 one-mark quiz items from the imported papers; the rest are skipped and counted). Then RUNBOOK.md for the
first revision.

## 19. Store: categories, offers, staff orders and digital products

What the store needs beyond section 12:

1. **Imports and exports.** Product and category imports need `shop.import_product` / `shop.import_category`
   (`IMPORT_EXPORT_IMPORT_PERMISSION_CODE = "import"` in settings.py), which only ADMIN holds, like the exports.
2. **Payment Links.** Staff orders paid through a Razorpay Payment Link need the `payment_link.paid` event on the
   webhook and Payment Links enabled on the account (section 12, steps 3 and 5).
3. **Digital products.** A product of kind "Digital (in the app)" opens a course of the `learn` app when paid
   (`learn.services.grant_for_order`; section 18). The product form refuses the books' HSN code 4901 for it: enter the
   SAC code and GST rate your accountant gives for the course (founder decision, see RUNBOOK.md "Digital products").
4. **Bank details for offline payments.** The quotation asks schools to pay "to the account we send with it": keep
   the account name, number, IFSC and UPI ID ready for that email (they are not on the site). Staff record each
   payment with its reference (RUNBOOK.md "Payments received offline"), which the invoice prints.
5. **Roles.** CONTENT_EDITOR keeps the catalogue and the course content, SALES the orders and offers, SUPPORT the
   course entitlements; `bootstrap_roles` runs on every start and after `make migrate` (README.md, "Roles and
   permissions").

## 20. Frontends: allauth.headless and the API contract

The website and the app sign in through allauth.headless at `/_allauth/`, then use API v1 (API.md, "Frontend
integration guide"). The settings are in `examleaf/settings.py`, not in `.env`:

| Setting | Value | Why |
|---|---|---|
| `HEADLESS_ONLY` | `True` | allauth serves no page: the website's sign-in pages are the frontend's; only Google's callback (`/account/google/login/callback/`) stays Django's |
| `HEADLESS_CLIENTS` | `("app", "browser")` | `/_allauth/app/v1/` (header `X-Session-Token`; `POST /api/v1/auth/exchange/` turns the session into the API's JWT pair) and `/_allauth/browser/v1/` (the session cookie and the CSRF token, same origin only: CORS stays on `/api/`) |
| `HEADLESS_FRONTEND_URLS` | the website's pages under `SITE_URL`, which the Next.js frontend serves at the same paths | emails link to them whichever client asked: the new-password page, sign-up; a Google log-in that failed without its own `callback_url` lands on `/account/login/?error=…` (addresses are confirmed by code: no link) |
| `HEADLESS_SERVE_SPECIFICATION` | `True` | allauth's OpenAPI file at `/_allauth/openapi.json` and `.yaml`; no HTML page (`HEADLESS_SPECIFICATION_TEMPLATE_NAME = None`: allauth's loads Redoc from a CDN, which the CSP refuses) |
| `ACCOUNT_SIGNUP_FORM_CLASS` | `accounts.signup.StudentDetailsForm` | every sign-up (the website's, after Google, allauth.headless's) asks the student details, records the consent and checks Turnstile (except after Google) |

Everything else follows the settings already set: the log-in methods, SMS, Google, passkeys, Turnstile, allauth's rate
limits, the SMS cap, and staff's authenticator app (StaffMFAMiddleware; a member of staff without one gets 403 from
`auth/exchange/` and from `/api/` with the session, and sets one up through `/_allauth/…/account/authenticators/totp`).
Caddy passes `/_allauth/` on to Django; every answer there is `Cache-Control: private, no-store`. The website's log-in,
code, email-confirmation and phone-confirmation steps keep the site's rules there (`examleaf/urls.py`: numbers as people
type them, three tries per code counted in the cache), and the admin sends a signed-out visitor to the website's log-in
(`LOGIN_URL`), a member of staff without an authenticator app to its `/account/2fa/`.

**The website** (`examleaf-frontend/`) shares the site's origin: Caddy sends Django's prefixes (`/api/`,
`/_allauth/`, `/admin/`, `/static/`, `/shop/webhooks/`, `/shop/media/`, `/qr/`, `/health/` …) to `web` and every other
path to the website (`PAGES_UPSTREAM`, `frontend:3000` by default: Django has no pages of its own since the clean-up of
8 October 2026), so the browser calls the API and allauth.headless on its own origin with the session and CSRF
cookies (a visitor's guest cart included: API.md, "Guests"). Nothing changes in `.env`: `SITE_URL` stays the domain
(every email links there, and the frontend serves the same paths), `CSRF_TRUSTED_ORIGINS` defaults to it, compose sets
`USE_X_FORWARDED_HOST=1` on `web` for the frontend's server-side calls, and `CORS_ALLOWED_ORIGINS` stays empty: CORS
is for other origins, and there are none. In development run Django for the frontend on port 8100 with the frontend's
origin in place of the domain (README.md, "The website (Next.js) in development").

After a deploy: `curl -s https://examleaf.in/_allauth/app/v1/config` answers 200 (Google among the providers only with
`GOOGLE_*` set) and `curl -s https://examleaf.in/api/v1/config/` shows what section 16 switched on.

Before the app uses passkeys, the domain must vouch for it: `https://examleaf.in/.well-known/assetlinks.json` (Android:
the package name and the signing certificate's SHA-256, relation `delegate_permission/common.get_login_creds`) and
`https://examleaf.in/.well-known/apple-app-site-association` (iOS: `webcredentials` with the app ID). Neither is served
yet: add them with the app's first release.

## 21. Insights (the predictive jobs)

The `insights` app (`insights/README.md`: every job, its method and how to read it) works out forecasts, print runs,
item analysis, cohorts, code activation, delivery times, fraud signals and offer effects at night, one Celery task
each. Nothing to install: no library beyond the standard one, and its migrations run with the others (the second one
gives ADMIN the new permissions, as `bootstrap_roles` does at every start).

1. **The beat entries** are in `settings.py` and written into the beat tables when beat starts, as the others are
   (README.md, "Background tasks"); times are India's:

   | When | Task | Writes |
   |---|---|---|
   | 01:00 | `insights.tasks.backtest` | how the forecast method did last season against the seasonal naive |
   | 01:15 | `insights.tasks.forecast_demand` | weekly copies per title and district to the exam |
   | 01:30 | `insights.tasks.advise_print_run` | copies to print, reprint triggers, leftovers |
   | 01:45 | `insights.tasks.item_analysis` | the quiz's item statistics and chapter accuracy |
   | 02:00 | `insights.tasks.cohorts` | weekly retention per cohort |
   | 02:15 | `insights.tasks.code_activation` | book codes redeemed per batch and district |
   | 02:30 | `insights.tasks.delivery_stats` | transit days per courier and district |
   | 02:45 | `insights.tasks.offer_effectiveness` | what coupons and offers did |
   | 03:00 | `insights.tasks.fraud_rules` | fraud signals, then the email to `INSIGHTS_ALERT_EMAILS` |

   A failed task is tried once more ten minutes later, then reported to Sentry (RUNBOOK.md, "An insights job failed").
   Each keeps 90 days of its rows (book codes tried: 180).
2. **Settings** (section 13, "Insights"): `INSIGHTS_ALERT_EMAILS` (the founder, operations) and `INSIGHTS_HASH_SALT`
   (random, like `SECRET_KEY`; set it before launch so that rotating `SECRET_KEY` leaves the fraud counts alone).
3. **What staff enter** in the admin (Insights): the **exam seasons** (board, class, academic year, first and last
   paper, from the board's notice: forecasts count a season's weeks back from the first paper, and nothing is forecast
   without the coming season and the last one), and a **print cost** per title (cost and salvage per copy, copies on
   order, reprint lead time: no print-run advice without one). Forecasts start once a season of sales exists; the
   backtest, once two do.
4. **Check** after a deploy: `dj insights_run all` prints one line per job ("nothing to work on" is right on a new
   site), and `curl -H "Authorization: Bearer $STAFF_ACCESS" https://examleaf.in/api/v1/insights/forecasts/` answers
   200 for staff (403 for anyone else).

## 22. Shipping: Shiprocket, India Post and the integration keys

The courier integration (`shipping/README.md`, on `integrations/README.md`): parcels booked with Shiprocket, tracked
by its webhook and a two-hourly poll, reconciled from its statement; parcels sent by hand (India Post) as before.
Shiprocket has no sandbox: its test mode here answers from recorded examples, and the live smoke test books and
cancels one real parcel.

1. **The integration key.** Make one (section 13, "Integrations and shipping"), put it in `.env` as
   `INTEGRATION_KEYS`, keep a copy with the other secrets, `docker compose up -d`.
2. **Shiprocket's API user** (an hour, on the Lite plan; Business at about 50 parcels a month). In Shiprocket:
   Settings → API → Add New API User, with an email address that is not the account's own login, the modules the site
   uses (orders, couriers, tracking, NDR, billing and wallet, pickup addresses) and "Buyer's Details Access" allowed
   (the label needs the address). The password is shown once: copy it.
3. **The account in the admin.** Admin → Integrations → Integration accounts → Add: provider Shiprocket, mode
   **test**, enabled; "Replace the credentials" `{"email": "<API user>", "password": "<its password>"}`. Save, then
   the action "Test the connection" ("Connected: wallet balance ₹…", answered by the recorded double in test mode).
   Book a few parcels of test orders through `/api/v1/shipping/` (API.md "Shipping (staff)") to see the flow. For
   real parcels: add a second account with mode **live** and the same credentials, disable the test one, enable the
   live one (one enabled per provider), test the connection (the real wallet balance this time).
4. **The pickup address.** In Shiprocket: Settings → Pickup Addresses, our address with the nickname we will use
   ("Primary"). Then `POST /api/v1/shipping/pickup-locations/sync/` (or add it in Admin → Shipping → Pickup locations
   with the same nickname and PIN), the default one.
5. **The webhook.** Admin → Integration accounts → the live account → the action "New webhook token": the token is
   shown once. In Shiprocket: Settings → API → Webhooks, URL `https://<domain>/api/hooks/parcel-events/` (Shiprocket
   refuses a URL with "shiprocket", "kartrocket", "sr" or "kr" in it: this one has none; the domain must not either),
   the token as the security token, enabled. Caddy already sends `/api/` to Django. Without a token set, every
   webhook is refused (403); the previous token keeps working for 24 hours after a new one is made.
6. **The catalogue's weights.** Every printed product needs its `weight (g)` (the quote and the booking add
   `SHIPPING_PACKING_GRAMS`); a book without one cannot be quoted until it has one, or until staff weigh the parcel.
7. **India Post's tariff.** `docker compose exec web python manage.py loaddata postal_tariffs` into the empty table
   (Book Post, and Gyan Post for when `SHIPPING_GYAN_POST` is on: the published tariff as the research read it on 9
   October 2026; verify it at the counter and correct it in Admin → Shipping → Postal tariffs).
8. **The survey of the North-East's PINs.** With the PIN directory loaded (section 15), `docker compose exec web python
   manage.py shipping_survey_pins` (500 PINs a run, then each Sunday by itself): Admin → Shipping → PIN serviceability
   lists, per PIN, the couriers, their COD and rate; courier "no courier" PINs go by India Post.
9. **SMS of a courier's news** (optional): register the two DLT templates of RUNBOOK.md "SMS" (`order_arriving`,
   `order_not_delivered`) and set `MSG91_TEMPLATE_ORDER_ARRIVING` and `MSG91_TEMPLATE_ORDER_NOT_DELIVERED`; without
   them those SMS are not sent (the emails are).
10. **The live smoke test.** `docker compose exec web python manage.py shipping_smoke_test --yes`: books a prepaid
    parcel to our own pickup address, assigns an AWB, fetches the label, cancels it before pickup and waits for the
    freight's reversal in the statement, printing every step. It moves real money (the freight is debited, then given
    back), and refuses to run with a test-mode account.
11. **Monitoring.** A second uptime monitor on `https://<domain>/health/integrations/` with the `X-Health-Token`
    header (section 7): it fails while Shiprocket has been unavailable for 30 minutes (the circuit open), or dead
    letters or failed webhooks wait for staff. `/health/` stays the site's own.

The labels and the parcels' photographs are kept in the private storage (`MEDIA_BUCKET`, folders `shipping/labels/`
and `shipping/photos/`; MEDIA_ROOT without a bucket), behind links signed for 5 minutes, as invoices are. Celery beat
runs the shipping tasks by itself (settings.py `CELERY_BEAT_SCHEDULE`, written into the beat tables at start-up):
tracking every two hours, the statement 05:00, COD remittances 05:15, weight disputes 05:30, the token 05:45, the PIN
survey on Sundays at 06:00, the SMS held through the night at 08:00, and the integrations' clean-up at 04:45.

## 23. Staff and the audit log

The Admin Control Panel's backend (`staff/`, `staff/README.md`; its API: API.md "Staff API") runs in the same
containers and needs nothing new to start: `migrate` creates its tables and the append-only trigger, and after every
`migrate` the staff app syncs the roles, the new ones too (OWNER, FINANCE, PACKER, REVIEWER, MARKETING, AUDITOR,
SALES_REP), with every app's permissions (`bootstrap_roles` does the same by hand); beat runs its jobs
(`staff/README.md` "The jobs"). Before staff use it:

1. **Who is told.** Set `STAFF_ALERT_EMAILS` to the owners' addresses (otherwise every active member of OWNER gets
   the alerts), and `DATA_PROTECTION_OFFICER` and `CERT_IN_POINT_OF_CONTACT` (section 13, "Staff"), or set them with
   the other e-commerce disclosures in the panel (Legal and privacy, Disclosures: the legal name and addresses,
   customer care, the Grievance Officer, the nodal contact resident in India, before 1 January 2027). Until the panel
   sets them, the legal name, the registered address and customer care's email and phone are the seller's
   (`SELLER_LEGAL_NAME`, `SELLER_ADDRESS`, `SUPPORT_EMAIL` or `SELLER_EMAIL`, `SELLER_PHONE`); no other variable.
2. **The roles.** The founder's own account holds the OWNER role (every catalogued permission), not the superuser
   flag. Superusers (`createsuperuser`) are one or two break-glass accounts only: outside Google sign-in, each with a
   security key and a backup key kept offline, used when nothing else works. Their log-in alerts the owners, every
   audit event of their sessions is marked `break_glass` (review them within 24 hours), and they are tested every
   quarter (RUNBOOK.md, "Break-glass"). To start, a break-glass account gives the founder OWNER in the admin; then
   give the others their roles through the panel (`people/`, an owner's), where giving a privileged one (ADMIN,
   FINANCE, AUDITOR, OWNER) waits for a second person (ADMIN or another owner) and
   two roles that separation of duties keeps apart are refused; the admin's "Give role" actions still work and do not
   check that (`bootstrap_roles` logs a warning for anyone who holds such a pair). The thresholds that send an action for
   approval (`ROLE_LIMITS` in `accounts/roles.py`: refund caps, the offline payment value, the discount %, export and
   bulk rows) are placeholders: set yours there.
3. **The audit table's owner role.** On PostgreSQL a trigger refuses UPDATE, DELETE and TRUNCATE on
   `staff_auditevent`; the hash chain and the off-site copy show anything that got past it. A database role can always
   remove a trigger from a table it owns, and today the stack runs as one role, the database's owner (`POSTGRES_USER`
   of docker-compose.yml, a superuser in the postgres image). To take that away from the running site, keep that role
   for migrations and the retention purge only and give the containers a role of their own:

   ```sql
   -- as the owner: docker compose exec db psql -U examleaf examleaf
   CREATE ROLE examleaf_app LOGIN PASSWORD '<a new password>';
   GRANT CONNECT ON DATABASE examleaf TO examleaf_app;
   GRANT USAGE ON SCHEMA public TO examleaf_app;
   GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO examleaf_app;
   GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO examleaf_app;
   REVOKE UPDATE, DELETE, TRUNCATE ON staff_auditevent FROM examleaf_app;  -- the audit log: read and append only
   ALTER DEFAULT PRIVILEGES FOR ROLE examleaf IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO examleaf_app;
   ALTER DEFAULT PRIVILEGES FOR ROLE examleaf IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO examleaf_app;
   ```

   Then point `DATABASE_URL` of `web`, `worker`, `beat` and `media-worker` at `examleaf_app`, and run `migrate` (and
   `bootstrap_roles`, which only changes the role tables) as the owner instead of in the web container's start command:
   `docker compose run --rm -e DATABASE_URL=postgres://examleaf:…@db:5432/examleaf web python manage.py migrate`.
   After a migration that adds a table, `GRANT` it to `examleaf_app` if the default privileges did not; and if
   `staff_auditevent` is ever made again (`migrate staff zero`), run the `REVOKE` again: the default privileges give a
   new table every right.
4. **The off-site copy.** With `BACKUP_BUCKET` set, the audit log goes there daily as `audit/YYYY/MM/YYYY-MM-DD.jsonl`
   (06:00). Give the bucket's `audit/` prefix an object lock (Cloudflare R2: a bucket lock rule; S3: Object Lock in
   compliance mode) as long as the money events are kept, eight years (a day's file holds both chains), keep the
   bucket's keys only on this server, and let a lifecycle rule delete `audit/` objects when the lock lets go. The files
   hold ids, client addresses and browsers, the audit's own minimum, and no other personal data.
5. **Retention.** Monthly, as the owner role (on the host's crontab, beside `scripts/backup.sh`):
   `docker compose exec -T -e DATABASE_URL=postgres://examleaf:…@db:5432/examleaf web python manage.py purge_audit`
   deletes what is past `STAFF_AUDIT_RETENTION_DAYS` (two years) and, for refunds, payments and prices,
   `STAFF_AUDIT_MONEY_RETENTION_FY` (eight financial years). `--dry-run` says what would go. The nightly
   `verify_audit_chain` keeps checking what stays.
6. **Clocks.** CERT-In's Directions ask every ICT system's clock to follow NIC's or NPL's NTP servers (samay1.nic.in,
   samay2.nic.in, time.nplindia.org) or a source traceable to them; a cloud provider's own time is accepted (CERT-In's
   FAQ, questions 40 to 43). The audit log's times, the 6-hour incident clock and the data requests' clocks depend on
   it. On the server: `timedatectl` must say "System clock synchronized: yes"; to use NPL's servers, set
   `NTP=samay1.nic.in samay2.nic.in time.nplindia.org` in `/etc/systemd/timesyncd.conf` and
   `sudo systemctl restart systemd-timesyncd`. The containers use the host's clock.
7. **The admin host** (with the panel): serve the panel and `/api/v1/staff/` from `admin.examleaf.in`, and set
   `ADMIN_HOSTS=admin.examleaf.in` (the staff API then answers 404 on every other host), `STAFF_PANEL_URL` to
   `https://admin.examleaf.in`, and add the host to `ALLOWED_HOSTS` and `https://admin.examleaf.in` to
   `CSRF_TRUSTED_ORIGINS`, or Django refuses its requests (400) and the panel's changes (403, CSRF).

## 24. ERPNext

The platform's side of the ERPNext sync (`erp/README.md`; ERPNext's side: `../examleaf-erp/README.md` and its
`API.md`). Nothing to install: its migrations run with the others, the staff app gives the roles its permissions after
`migrate`, and beat runs its tasks. Everything is off until switched on, in this order:

1. **The sync user in ERPNext.** On the ERPNext site (`examleaf-erp/README.md` "The sync user"): the bootstrap makes
   `erp-sync@examleaf.in` with the EL Sync role only; `bench --site <site> execute
   frappe.core.doctype.user.user.generate_keys --args "['erp-sync@examleaf.in']"` prints its `api_key` and
   `api_secret` once. Set `examleaf_sync_user_restrict_ip` there to the platform's egress addresses.
2. **The integration account.** Admin → Integrations → Integration accounts → Add: provider ERPNext, mode **test**
   for the staging site (shadow mode, Phase B) or **live** for production's, enabled (one enabled per provider);
   "Replace the credentials" with `{"api_key": "…", "api_secret": "…", "base_url": "http://<erpnext service>:8080",
   "site_name": "erp.examleaf.in"}`: the in-cluster address of ERPNext's gunicorn service (the platform reaches it
   inside the cluster, never over the internet), and the site's name, sent as `X-Frappe-Site-Name` because the
   service's host name is not the site's. Then the action "Test the connection" ("Connected: ERPNext answered the
   ping (erp.examleaf.in, examleaf_erp …)").
3. **The webhook secret.** The same account → the action "New webhook token": shown once. In ERPNext's site config:
   `bench --site <site> set-config examleaf_webhook_secret '<it>'` and `examleaf_webhook_base
   'http://<platform web service>:8000/api/hooks/erp-events/'` (inside the cluster: Caddy is not on that path, so add
   the service's host name to `ALLOWED_HOSTS`; the six webhooks stay off until both are set). Plain http is fine there:
   this path alone is exempt from the https redirect, the hooks being authenticated by their signature, not by TLS
   (RESILIENCE.md 9.3.1); through the public address they come over https as before. A new token later: the
   previous one is accepted for 24 hours, so set the new one in ERPNext within that time (RUNBOOK.md, "ERPNext").
4. **The switches** (section 13, "ERPNext"; each also a feature flag the panel can set without a deploy, with its
   history: `PUT /api/v1/staff/flags/<name>/`): `ERP_ENABLED=1`, then the flows `ERP_SYNC_CATALOGUE`,
   `ERP_SYNC_INVOICES`, `ERP_SYNC_PAYMENTS`, `ERP_SYNC_DELIVERIES`, `ERP_SYNC_SETTLEMENTS`, and the reads
   `ERP_PULL_STOCK`, `ERP_PULL_B2B`. `ERP_STOCK_PROJECTION` stays off until the cut-over (shadow mode: ERPNext's
   stock is compared, never used). `ERP_ALERT_EMAILS` to FINANCE's addresses.
5. **The initial load.** `docker compose exec web python manage.py erp_initial_load` (a dry run: what it would write),
   then with `--apply` (and `--invoices-from YYYY-MM-DD` for the invoices since a day); or the panel's job
   `erp_initial_load`. Opening stock, suppliers and open B2B receivables go into ERPNext by its Data Import.
6. **Check**: `docker compose exec web python manage.py erp_status` (the outbox draining, no dead letter), the next
   morning's reconciliation (`erp_reconcile` by hand: "0 difference(s)"), and `/health/integrations/` green.

**The beat entries** (settings.py `CELERY_BEAT_SCHEDULE`, written into the beat tables at start-up; India's time):

| When | Task | Does |
|---|---|---|
| every minute (and after each change that wrote rows) | `erp.tasks.relay` | sends the outbox |
| every 15 minutes | `erp.tasks.pull` | reads what changed in ERPNext since each cursor (stock, B2B documents) |
| 03:30 | `erp.tasks.reconcile_day` | yesterday compared with ERPNext; differences to the inbox and `ERP_ALERT_EMAILS` |

The cut-over (plan 9.3; `erp/README.md` "Shadow mode and the cut-over"): on the night of 31 March 2027, the live
account enabled in place of the staging one, `ERP_STOCK_PROJECTION=1` after the stock has been checked, and a
reconciliation the next morning. Rollback: a flow's switch off (its rows wait; the initial load fills the gap once it
is on again); `ERP_STOCK_PROJECTION` off hands the copies for sale back to the platform's own number.
