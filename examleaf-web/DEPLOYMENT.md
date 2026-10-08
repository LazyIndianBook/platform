# First deployment

The whole stack runs on one Linux server with Docker: PostgreSQL 17, Redis 7, the site (gunicorn), the Celery worker
and beat, and Caddy, which serves https and renews the certificate by itself. A 2 vCPU / 4 GB machine is plenty to
start: e.g. Hetzner CX22, a DigitalOcean 4 GB droplet, or an Indian provider (E2E Networks, AWS or Azure in Mumbai)
if the data should stay in India, as the Privacy Policy draft says ("servers in [India]": fill in what you choose).

## 1. Accounts you need

- the domain (here `examleaf.in`), at a registrar where you can edit DNS;
- an email provider supported by django-anymail (Brevo, Amazon SES, Postmark, Mailgun …), with the sending domain
  verified (SPF and DKIM records as the provider shows them, plus a DMARC record);
- optional: Sentry (errors), an S3-compatible bucket for off-site backups (Cloudflare R2, Backblaze B2, AWS S3);
- an uptime monitor for `https://examleaf.in/health/` that can send a request header (section 14);
- for the shop: a Razorpay account in the name of ExamLeaf LLP (section 12).

## 2. DNS

Create an `A` record (and `AAAA` for IPv6) for `examleaf.in` pointing at the server's address. Wait until
`dig +short examleaf.in` shows it: Caddy asks Let's Encrypt for the certificate on its first start, and that only
works once the name points at the server and ports 80 and 443 are open.

## 3. The server

As root on a fresh Ubuntu 24.04:

```sh
adduser --disabled-password examleaf && usermod -aG sudo examleaf   # then log in as examleaf with an SSH key
apt update && apt install -y unattended-upgrades ufw git
ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443/tcp && ufw allow 443/udp && ufw enable
curl -fsSL https://get.docker.com | sh && usermod -aG docker examleaf   # Docker Engine and the compose plugin
```

Docker publishes ports past ufw; only Caddy publishes any (80, 443). PostgreSQL and Redis are reachable only inside
the compose network.

## 4. Code and settings

```sh
sudo mkdir -p /srv/examleaf && sudo chown examleaf: /srv/examleaf
git clone git@github.com:LazyIndianBook/Class-12-Assam.git /srv/examleaf   # a read-only deploy key on the server
cd /srv/examleaf/examleaf-web
cp .env.example .env && chmod 600 .env
```

Edit `.env` (each variable is explained there). At least:

```sh
DEBUG=0
SECRET_KEY=<python3 -c "import secrets; print(secrets.token_urlsafe(50))">
ALLOWED_HOSTS=examleaf.in
SITE_URL=https://examleaf.in
DOMAIN=examleaf.in
POSTGRES_PASSWORD=<python3 -c "import secrets; print(secrets.token_hex(24))">
EMAIL_BACKEND=anymail.backends.brevo.EmailBackend
ANYMAIL_BREVO_API_KEY=...
DEFAULT_FROM_EMAIL=ExamLeaf <noreply@examleaf.in>
WEB_CONCURRENCY=3
SENTRY_DSN=...                       # optional
BACKUP_BUCKET=examleaf-backups       # optional, with AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, BACKUP_ENDPOINT_URL
BACKUP_AGE_RECIPIENT=age1...         # with a bucket: the uploaded dumps are encrypted to this key (section 9)
HEALTH_CHECK_TOKEN=<python3 -c "import secrets; print(secrets.token_urlsafe(32))">   # the uptime monitor's (section 14)
```

With `DEBUG=0` the site refuses to start while `SECRET_KEY` is the example's (`dev-…`) or shorter than 50 characters;
with `DEBUG=1` it refuses any `ALLOWED_HOSTS` but `localhost`, `127.0.0.1` and `[::1]`.

`DATABASE_URL`, `CACHE_URL`, `CELERY_BROKER_URL` and `PROXY_COUNT` are set by docker-compose.yml.

## 5. Start

```sh
docker compose up -d --build
docker compose ps                     # db, redis, web healthy; worker, beat, caddy running
docker compose logs -f web caddy      # migrations, bootstrap_roles, gunicorn; Caddy obtaining the certificate
```

The static files were collected (hashed, compressed) when the image was built. The web container runs `migrate` and
`bootstrap_roles` on every start, in that order, then the readiness check
(`manage.py health_check health_web --no-http`: database, cache, a write to the media volume), then gunicorn; if the
check fails the container stops, its log names the failing part, and Docker starts it again. To run them by hand:
`docker compose exec web python manage.py migrate && docker compose exec web python manage.py bootstrap_roles`.
Worker and beat start once the web container is healthy (`/health/web/`: database, cache and storage).

## 6. Content and the first admin

```sh
docker compose exec web python manage.py import_papers --all      # reads ../production, mounted read-only
docker compose exec web python manage.py createsuperuser
```

Log in at `https://examleaf.in/admin/`: the admin's log-in is the site's (the emailed code the first time), and every
member of staff sets up an authenticator app before anything else opens (RUNBOOK.md, "Staff accounts").
In the admin: fill in the square-bracket placeholders of the five legal pages (Pages),
create staff accounts and give them roles (Users → action "Give role …"), and look at Periodic tasks (the purge at
03:00 and the failed-log-in clean-up at 03:30, India time).

## 7. Check

```sh
curl -s -H 'Accept: application/json' -H "X-Health-Token: $HEALTH_CHECK_TOKEN" https://examleaf.in/health/   # all "OK"
curl -s -o /dev/null -w '%{http_code}\n' https://examleaf.in/health/     # 404: without the header nobody gets an answer
docker compose exec web python manage.py check --deploy               # only security.W005 and security.W021
docker compose exec web python manage.py sendtestemail you@example.com   # the email provider works
```

Then register a test student from a phone, type the emailed code, open a paper's solutions, and delete the account
from My account (the purge erases it seven days later). Point the uptime monitor at `/health/` with the header
`X-Health-Token` (it returns 500 when the database, cache, storage or the Celery worker fails).

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
uploads each dump to `BACKUP_BUCKET` when set. Without a bucket the dumps stay on the same disk as the database:
copy them elsewhere. Try a restore once (RUNBOOK.md) before relying on them. The `media` volume holds the invoice PDFs
(tax records: keep them eight years) and the product pictures: back it up too, e.g.
`docker run --rm -v examleaf-web_media:/m -v /srv/examleaf/backups:/b alpine tar czf /b/media-$(date +%F).tgz -C /m .`
(the volume name is `docker volume ls`'s); an invoice that is missing is made again by the daily clean-up, or by hand:
`docker compose exec web python manage.py shell -c "from shop.tasks import generate_invoice; generate_invoice(<order id>)"`.

The bucket keeps what is uploaded until it is deleted, so give it a lifecycle rule that deletes objects under
`database/` 30 days after they are uploaded (Cloudflare R2's object lifecycle rules, Backblaze B2's lifecycle rules, or
an S3 lifecycle configuration; with versioning on, old versions must expire too), as the Privacy Policy promises
("Backups: 30 days"). Encrypt
the uploaded copies with [age](https://age-encryption.org) (`sudo apt install age`): on your own computer run
`age-keygen -o examleaf-backup.key`, keep that file off the server (a password manager and a second safe place), and
put the public key it prints (`age1…`) into `.env` as `BACKUP_AGE_RECIPIENT`. `backup.sh` then uploads only
`examleaf-….dump.age`; the local dumps stay plain on the server for a quick restore (RUNBOOK.md shows how to decrypt).

## 10. Logs

- `docker compose logs -f web worker beat` — Django and Celery, one JSON object per line with `time`, `level`,
  `logger`, `message` and `request_id`;
- `docker compose logs -f caddy` — the access log (JSON, with the same `X-Request-ID` in the request headers);
- `docker compose logs db redis`.

Docker keeps them in `/var/lib/docker/containers/<id>/<id>-json.log`, rotated at 10 MB, five files per service.
Rotation is by size, not by time (Docker's json-file driver has no age limit), so the Privacy Policy draft says that a
fixed amount is kept and fills in the days it lasts: look at the oldest line of `docker compose logs caddy` after a
month of traffic and put that number in the policy. For a hard limit in days use the journald driver instead
(`logging: {driver: journald}` in docker-compose.yml and `MaxRetentionSec=30day` in `/etc/systemd/journald.conf`).
Celery task results are in the admin (Task results) for a week; errors go to Sentry when it is set.

## 11. Updates

```sh
cd /srv/examleaf && git pull
cd examleaf-web && docker compose up -d --build     # migrations and bootstrap_roles run on start
docker compose exec web python manage.py import_papers --all   # when papers changed
```

The site is down for the few seconds the web container takes to restart.

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
   `payment.failed`, `order.paid`, `refund.processed`, `refund.failed`. The webhook completes orders whose customer
   never came back from the payment page, and finishes refunds that Razorpay processes later. The live webhook gets a
   secret of its own when going live (`RAZORPAY_WEBHOOK_SECRET`): the site checks the secret of its keys' mode, so
   test-mode webhooks are refused once the live keys are in.

   **Shop closed during Razorpay's review.** Razorpay's activation review needs the shop public while it still runs on
   test keys, when anyone could "pay" with the published test card. Set `SHOP_OPEN=0`: the books and prices stay
   visible with "Shop opens soon", and only staff can use the cart, checkout and payment (website and API). Set it back
   to 1 (or remove it) when going live.
4. **Capture.** Account & Settings → Payment Capture: automatic (the site also captures an authorized payment when the
   customer comes back, so manual capture works too, but then a payment whose customer never returns is not captured).
5. **Seller and options** in `.env`: `SELLER_LEGAL_NAME`, `SELLER_ADDRESS`, `SELLER_GSTIN` (empty if not registered),
   `SELLER_STATE`, `SELLER_STATE_CODE`, `SELLER_EMAIL`, `SELLER_PHONE`; `SHOP_COD_ENABLED=1` for cash on delivery
   (only for accounts with a confirmed email address, two orders on their way per account, each worth at most
   `SHOP_COD_MAX_VALUE`, ₹1,500 by default). Then `docker compose up -d` (the containers read `.env` when they start).
6. **Catalogue.** `docker compose exec web python manage.py seed_shop`, then in the admin (Shop): real prices and MRP,
   stock, ISBN, pages, weights, a cover for each Solutions book, the coupon's dates (or untick it), the shipping rates.
   Give the people who pack and ship the SALES role, and those who answer customers SUPPORT.
7. **Try it** with Razorpay's test card or the UPI ID `success@razorpay`: an order is paid, the confirmation email
   arrives, the invoice appears on the order page; a failed payment (`failure@razorpay`) can be retried; a cancellation
   is refunded and its credit note appears next to the invoice; Mark packed, Mark shipped (a tracking number) and Mark delivered send their emails. Dashboard →
   Webhooks shows each delivery answered 200.

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
- [ ] `check --deploy` shows only W005 and W021; `/health/` is OK; Sentry receives errors; the `media` volume is backed
      up (invoices and credit notes).
- [ ] After a first real order: `docker compose exec web python manage.py reconcile_payments` lists nothing but
      "no payment at Razorpay" for abandoned checkouts (it asks Razorpay about every unpaid online order; RUNBOOK.md,
      "A stuck payment").


## 13. Environment variables

All of them are read from `.env` (copy `.env.example`: each is explained there) or the real environment. docker-compose.yml
sets `DATABASE_URL`, `CACHE_URL`, `CELERY_BROKER_URL`, `PROXY_COUNT` and `BOOK_ROOT` for its containers; the rest come
from `.env`.

| Variable | Default | What it does |
|---|---|---|
| `DEBUG` | 0 | 1 in development only (https redirect, secure cookies, HSTS and the strict CSP are off or report-only) |
| `SECRET_KEY` | required | long and random; signs sessions, tokens and the consent address hashes |
| `SECRET_KEY_FALLBACKS` | none | the previous key(s) while rotating (RUNBOOK.md) |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | host names the site answers to (comma separated) |
| `SITE_URL` | `http://localhost:8000` | base of the QR codes and of the links in emails; `export_qr` refuses localhost and http |
| `CSRF_TRUSTED_ORIGINS` | `SITE_URL` | origins trusted for form posts |
| `BOOK_ROOT` | the folder above `examleaf-web` | where `production/` (the Markdown papers) is, for `import_papers` |
| `SOLUTIONS_REQUIRE_LOGIN` | 1 | 1: solutions for signed-in students; 0: for everyone (README, "Open or registered solutions") |
| `PARENTAL_CONSENT_MODE` | `declared` | `declared`: the parent ticks the sign-up box; `verified`: the parent also confirms by an emailed link (section 14; before May 2027) |
| `DATA_UPLOAD_MAX_MEMORY_SIZE` | 1048576 | largest form or JSON body in bytes (the API answers 413 above it) |
| `DATABASE_URL` | SQLite `db.sqlite3` | `postgres://user:password@host:5432/examleaf` (compose sets it from `POSTGRES_PASSWORD`) |
| `CONN_MAX_AGE` | 60 | seconds a database connection is kept between requests |
| `CACHE_URL` | per-process memory | `redis://host:6379/1`; a Redis of its own that may evict (compose: `redis-cache`, 256 MB, allkeys-lru), never the queue's; with Redis down the site runs on without it, but the shop's order lookup, checkout and coupon codes answer 429 |
| `CELERY_BROKER_URL` | empty | `redis://host:6379/0`; empty: tasks run inline in the web process (development) |
| `CELERY_TASK_ALWAYS_EAGER` | 1 without a broker | force inline tasks (1) or never (0) |
| `EMAIL_BACKEND` | console | `anymail.backends.brevo.EmailBackend` etc. in production |
| `ANYMAIL_*` | none | the email provider's settings, e.g. `ANYMAIL_BREVO_API_KEY` |
| `DEFAULT_FROM_EMAIL` | `ExamLeaf <noreply@localhost>` | the sender of every email: use the verified sending domain |
| `PROXY_COUNT` | 0 (compose: 1) | proxies in front of the site: trusts `X-Forwarded-Proto` and `-For` from Caddy |
| `USE_X_FORWARDED_HOST` | 0 | take the host name from `X-Forwarded-Host` (Caddy does not need it) |
| `SECURE_SSL_REDIRECT` | 1 (with `DEBUG=0`) | redirect http to https |
| `SECURE_HSTS_SECONDS` | 31536000 | HSTS lifetime |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS`, `SECURE_HSTS_PRELOAD` | 0 | on only when every subdomain is https (they are the two `check --deploy` warnings) |
| `MEDIA_BUCKET`, `MEDIA_ENDPOINT_URL` | none | private S3-compatible bucket for uploads instead of the `media` volume |
| `BACKUP_BUCKET`, `BACKUP_ENDPOINT_URL` | none | private bucket that `scripts/backup.sh` uploads the dumps to |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | none | keys for both buckets |
| `BACKUP_KEEP_DAYS` | 30 | days of local dumps `scripts/backup.sh` keeps (match the Privacy Policy) |
| `BACKUP_AGE_RECIPIENT` | none | an age public key (`age1…`): `scripts/backup.sh` uploads the dumps encrypted to it (section 9) |
| `HEALTH_CHECK_TOKEN` | none (Caddy: 404 for everyone) | the value of the `X-Health-Token` header Caddy asks of `/health/` callers (section 14) |
| `SENTRY_DSN` | empty (off) | error reports, scrubbed of personal data (`examleaf/sentry.py`) |
| `SENTRY_ENVIRONMENT`, `SENTRY_TRACES_SAMPLE_RATE`, `RELEASE` | `production`, 0, none | Sentry's environment name, trace sampling, version label |
| `LOG_JSON`, `LOG_LEVEL` | 1 with `DEBUG=0`, `INFO` | JSON log lines or text, and the level |
| `CORS_ALLOWED_ORIGINS` | none | web origins allowed to call `/api/` from a browser (the app and the site need none) |
| `JWT_ACCESS_MINUTES`, `JWT_REFRESH_DAYS` | 15, 30 | token lifetimes of the API |
| `JWT_SIGNING_KEY` | `SECRET_KEY` | the key the API's tokens are signed with; changing it logs every app out, not the website (RUNBOOK.md) |
| `API_THROTTLE_ANON`, `API_THROTTLE_USER`, `API_THROTTLE_AUTH` | 200/minute, 600/minute, 30/minute | API rate limits per address, per user, and for log-in, sign-up and passwords |
| `API_THROTTLE_ORDER_LOOKUP`, `API_THROTTLE_PAYMENT`, `API_THROTTLE_COUPON` | 10/hour, 30/minute, 10/hour | guests' order lookup per address; starting and confirming payments; coupon codes tried per user |
| `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET` | empty | API keys (`rzp_test_…` until going live); empty: online payment is not set up |
| `RAZORPAY_WEBHOOK_SECRET_TEST`, `RAZORPAY_WEBHOOK_SECRET` | empty | the Test Mode and Live Mode webhooks' secrets; the one of the keys' mode is checked; empty: every webhook is refused |
| `SHOP_OPEN` | 1 | 0: only staff use the cart, checkout and payment ("Shop opens soon"), for Razorpay's review on test keys |
| `SHOP_COD_ENABLED` | 0 | offer cash on delivery (accounts with a confirmed email address, two orders on their way each) |
| `SHOP_COD_MAX_VALUE` | 1500 | the largest cash-on-delivery order, in rupees, shipping included |
| `SELLER_LEGAL_NAME`, `SELLER_ADDRESS`, `SELLER_GSTIN`, `SELLER_STATE`, `SELLER_STATE_CODE`, `SELLER_EMAIL`, `SELLER_PHONE` | ExamLeaf LLP, placeholders, empty, `AS`, `18`, placeholders | the seller printed on invoices (no invoice is numbered while a `[placeholder]` is left) |
| `DOMAIN` | required (compose) | the domain Caddy serves and gets its certificate for |
| `POSTGRES_PASSWORD` | required (compose) | the compose PostgreSQL's password: random, letters and digits only (it goes into a URL) |
| `WEB_CONCURRENCY` | 1 | gunicorn worker processes (about 2 x CPU cores + 1) |
| `BOOK_SOURCE` | `..` | folder holding `production/` on the host, mounted read-only for `import_papers` |

## 14. Security settings (phase 4)

**Health checks.** From the internet Caddy answers `/health/` and `/health/web/` with 404 unless the request carries
the header `X-Health-Token: <HEALTH_CHECK_TOKEN>` (Caddyfile). Set the token in `.env` (letters, digits, `-` and `_`;
`secrets.token_urlsafe` gives that) and in the uptime monitor's request headers (UptimeRobot's paid plans, Better
Stack, Uptime Kuma and most others can send one). The web container's own health check calls `127.0.0.1:8000` and
needs no token. Caddy reads the token from its own environment, so docker-compose.yml passes it on:

```yaml
  caddy:
    environment:
      DOMAIN: ${DOMAIN:?set DOMAIN in .env}
      HEALTH_CHECK_TOKEN: ${HEALTH_CHECK_TOKEN:?set HEALTH_CHECK_TOKEN in .env}
```

Without it in Caddy's environment nobody gets through, the monitor included. The API has no health endpoint any more.

**Staff accounts.** The admin's log-in is allauth's: its limit of failed log-ins per account applies, and every member
of staff must set up an authenticator app (TOTP, with ten recovery codes) before anything else opens. Their sessions
end 8 hours after the log-in. RUNBOOK.md, "Staff accounts", has the steps for a new member of staff and for a lost
phone. Periodic tasks, task results, groups, permissions and second factors can be changed by superusers only (the
ADMIN role sees them), and only a superuser changes a superuser's account.

**Parental consent (before May 2027).** The DPDP Rules, 2025 ask for verifiable consent of a parent before a child's
data is processed, from May 2027 (18 months after the Rules were notified in November 2025). Until then the site runs
with `PARENTAL_CONSENT_MODE=declared` (the parent ticks the box on the sign-up form). To switch, before that date:

1. Edit the Privacy page in the admin ("Students under 18": the parent confirms through a link emailed to them) and
   change its version.
2. Set `PARENTAL_CONSENT_MODE=verified` in `.env` and `docker compose up -d`.

From then on a student under 18 must give a parent's email address at sign-up; the parent gets a link valid for 7 days,
and until they press "I agree" the account can log in and read the solutions but not save marks or order books. The
student can send the link again, also to a corrected address, from My account. Students under 18 who registered before
the switch are in the same state until a parent confirms: email them (RUNBOOK.md, "Parental consent").

**Recommended next steps** (not done yet):
- Lock the requirements with hashes (`pip-compile --generate-hashes`, or `uv pip compile --generate-hashes`, then
  `pip install --require-hashes`), with a `#sha256=` on the django-celery-beat archive until a release supports
  Django 6.1.
- Pin the base images by digest (`FROM python:3.14-slim@sha256:…`, and the same for postgres, redis and caddy in
  docker-compose.yml) and the CI actions by commit SHA; let Dependabot or Renovate propose the updates.
- Make the `dependency-audit` CI job blocking once its first findings are dealt with.
