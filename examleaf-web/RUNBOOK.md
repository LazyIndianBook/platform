# Runbook

Commands run in `/srv/examleaf/examleaf-web` on the server. `dj` below stands for
`docker compose exec web python manage.py`.

## Restore the database from a backup

1. Pick the dump: `ls -lt backups/`, or download it from the backup bucket (`database/examleaf-….dump`).
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
5. Check `https://examleaf.in/health/`, log in to the admin, open a paper.

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
- **Suspected breach:** rotate everything above, end all sessions
  (`dj shell -c "from django.contrib.sessions.models import Session; Session.objects.all().delete()"`), find out what was
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

The parental consent is self-declared today (a parent ticks the box). The DPDP Rules, 2025 ask for verifiable consent
of a parent; plan the verification (e.g. a code sent to the parent's phone or email) before those rules apply.

## When email fails

Signs: students say the code never came; Sentry errors from `ops.tasks.send_email`; failed or retrying tasks under
Celery → Task results; `docker compose logs worker | grep send_email`.

1. Is the worker up? `/health/` says so (Celery ping). If not: `docker compose up -d worker` and look at its logs.
   While Redis is down, emails are sent directly by the web process, so sign-ups keep working.
2. Does the provider accept mail? `dj sendtestemail you@example.com` sends synchronously and shows the provider's
   error (wrong API key, quota, unverified sender domain, account suspended). Check the provider's dashboard and status
   page, and the SPF/DKIM records.
3. A failed email is retried five times over about 25 minutes, then dropped. Once mail works, students press "send the
   code again" (or reset the password), which sends a new one.
4. To switch provider quickly: set `EMAIL_BACKEND` and the new provider's `ANYMAIL_…` key in `.env`
   (django-anymail supports Amazon SES, Mailgun, Postmark, SendGrid, Brevo and others), `docker compose up -d`, and
   send a test email.

## Other incidents

- **/health/ returns 500:** the JSON (`curl -H 'Accept: application/json' https://examleaf.in/health/`) names the
  failing part: database (`docker compose logs db`), cache (Redis), storage (disk full? `df -h`), Celery (worker).
- **Disk full:** `docker system df`; old images (`docker image prune`), backups beyond `BACKUP_KEEP_DAYS`; logs are
  rotated already.
- **Certificate problems:** `docker compose logs caddy`; DNS must point at the server and ports 80/443 be open.
- **Someone locked out by django-axes** (10 failed log-ins): it lifts after 15 minutes, or `dj axes_reset_username x@example.com`.
