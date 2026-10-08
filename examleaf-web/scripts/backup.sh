#!/bin/sh
# Back up the docker-compose PostgreSQL database to backups/examleaf-YYYYMMDD-HHMMSS.dump (pg_dump custom format,
# compressed), delete local dumps older than BACKUP_KEEP_DAYS (from .env, default 30), and upload the new dump to the
# private bucket BACKUP_BUCKET when .env sets one (manage.py upload_backup, django-storages). With BACKUP_AGE_RECIPIENT
# (an age public key, age1…) the uploaded copy is encrypted first: the bucket only ever holds examleaf-….dump.age,
# which only the private key, kept off the server, can open (RUNBOOK.md, restore). Needs `age` on the host.
# Run it daily from the host's crontab (DEPLOYMENT.md); restoring is in RUNBOOK.md.
set -eu
cd "$(dirname "$0")/.."
umask 077  # the dumps hold every student's personal data
DIR=backups
KEEP=$(sed -n 's/^BACKUP_KEEP_DAYS=//p' .env 2>/dev/null | tail -n 1)
RECIPIENT=$(sed -n 's/^BACKUP_AGE_RECIPIENT=//p' .env 2>/dev/null | tail -n 1)
FILE="examleaf-$(date +%Y%m%d-%H%M%S).dump"
mkdir -p "$DIR"
docker compose exec -T db pg_dump --username examleaf --format custom examleaf > "$DIR/$FILE.part"
mv "$DIR/$FILE.part" "$DIR/$FILE"
find "$DIR" -name 'examleaf-*.dump*' -mtime +"${KEEP:-30}" -delete
UPLOAD=$FILE
if [ -n "$RECIPIENT" ]; then
    age --recipient "$RECIPIENT" --output "$DIR/$FILE.age" "$DIR/$FILE"
    UPLOAD=$FILE.age
fi
docker compose run --rm --no-deps --volume "$(pwd)/$DIR:/backups:ro" web python manage.py upload_backup "/backups/$UPLOAD"
echo "Backup written: $DIR/$FILE"
