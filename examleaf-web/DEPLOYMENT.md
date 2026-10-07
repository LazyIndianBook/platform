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
- an uptime monitor (e.g. UptimeRobot) for `https://examleaf.in/health/`;
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
```

`DATABASE_URL`, `CACHE_URL`, `CELERY_BROKER_URL` and `PROXY_COUNT` are set by docker-compose.yml.

## 5. Start

```sh
docker compose up -d --build
docker compose ps                     # db, redis, web healthy; worker, beat, caddy running
docker compose logs -f web caddy      # migrations, bootstrap_roles, gunicorn; Caddy obtaining the certificate
```

The web container runs `migrate` and `bootstrap_roles` on every start, then gunicorn; to run them by hand:
`docker compose exec web python manage.py migrate && docker compose exec web python manage.py bootstrap_roles`.
Worker and beat start once the web container is healthy (`/health/web/`: database, cache and storage).

## 6. Content and the first admin

```sh
docker compose exec web python manage.py import_papers --all      # reads ../production, mounted read-only
docker compose exec web python manage.py createsuperuser
```

In the admin (`https://examleaf.in/admin/`): fill in the square-bracket placeholders of the five legal pages (Pages),
create staff accounts and give them roles (Users → action "Give role …"), and look at Periodic tasks (the purge at
03:00 and the failed-log-in clean-up at 03:30, India time).

## 7. Check

```sh
curl -s -H 'Accept: application/json' https://examleaf.in/health/        # all "OK", including the Celery ping
docker compose exec web python manage.py check --deploy               # only security.W005 and security.W021
docker compose exec web python manage.py sendtestemail you@example.com   # the email provider works
```

Then register a test student from a phone, type the emailed code, open a paper's solutions, and delete the account
from My account (the purge erases it seven days later). Point the uptime monitor at `/health/` (it returns 500 when
the database, cache, storage or the Celery worker fails).

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
(the volume name is `docker volume ls`'s); invoices can also be made again from the orders (`generate_invoice`).

## 10. Logs

- `docker compose logs -f web worker beat` — Django and Celery, one JSON object per line with `time`, `level`,
  `logger`, `message` and `request_id`;
- `docker compose logs -f caddy` — the access log (JSON, with the same `X-Request-ID` in the request headers);
- `docker compose logs db redis`.

Docker keeps them in `/var/lib/docker/containers/<id>/<id>-json.log`, rotated at 10 MB, five files per service.
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
3. **Webhook.** Account & Settings → Webhooks → Add new webhook: URL `https://examleaf.in/shop/webhooks/razorpay/`,
   a secret (`python3 -c "import secrets; print(secrets.token_urlsafe(32))"`, also into `.env` as
   `RAZORPAY_WEBHOOK_SECRET`), an alert email, and the events `payment.captured`, `payment.failed`, `order.paid`,
   `refund.processed`, `refund.failed`. The webhook completes orders whose customer never came back from the payment
   page, and finishes refunds that Razorpay processes later.
4. **Capture.** Account & Settings → Payment Capture: automatic (the site also captures an authorized payment when the
   customer comes back, so manual capture works too, but then a payment whose customer never returns is not captured).
5. **Seller and options** in `.env`: `SELLER_LEGAL_NAME`, `SELLER_ADDRESS`, `SELLER_GSTIN` (empty if not registered),
   `SELLER_STATE`, `SELLER_STATE_CODE`, `SELLER_EMAIL`, `SELLER_PHONE`; `SHOP_COD_ENABLED=1` for cash on delivery.
   Then `docker compose up -d` (the containers read `.env` when they start).
6. **Catalogue.** `docker compose exec web python manage.py seed_shop`, then in the admin (Shop): real prices and MRP,
   stock, ISBN, pages, weights, a cover for each Solutions book, the coupon's dates (or untick it), the shipping rates.
   Give the people who pack and ship the SALES role, and those who answer customers SUPPORT.
7. **Try it** with Razorpay's test card or the UPI ID `success@razorpay`: an order is paid, the confirmation email
   arrives, the invoice appears on the order page; a failed payment (`failure@razorpay`) can be retried; a cancellation
   is refunded; Mark packed, Mark shipped (a tracking number) and Mark delivered send their emails. Dashboard →
   Webhooks shows each delivery answered 200.

### Going live

- [ ] Legal pages final: the email, phone, address, GSTIN and Grievance Officer filled in; the courier and dispatch days
      in Shipping; the refund rules in Refunds checked against what the business wants.
- [ ] Seller details in `.env` correct: they print on every invoice and cannot be changed afterwards.
- [ ] Real prices, stock and ISBNs. Orders made in test mode stay in the admin; their invoices are in the test series
      (`T/2026-27/…`, marked as not a tax document), so the real ones start at `EL/<year>/00001`.
- [ ] Razorpay account activated. Switch the Dashboard to Live Mode, generate live keys and set `RAZORPAY_KEY_ID=rzp_live_…`
      and `RAZORPAY_KEY_SECRET`; create the same webhook again in Live Mode (webhooks are per mode) and set its
      secret as `RAZORPAY_WEBHOOK_SECRET`; `docker compose up -d`. The payment page no longer says "Test mode".
- [ ] One real purchase of a cheap book, then cancel it: the refund appears in the Razorpay Dashboard (Refunds) and
      the money comes back to the card or UPI account.
- [ ] `check --deploy` shows only W005 and W021; `/health/` is OK; Sentry receives errors; the `media` volume is backed
      up (invoices).

