from pathlib import Path

from django.core.files import File
from django.core.files.storage import InvalidStorageError, storages
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Upload a backup file to the private bucket set by BACKUP_BUCKET (django-storages); skipped without it."

    def add_arguments(self, parser):
        parser.add_argument("path")

    def handle(self, path, **options):
        try:
            storage = storages["backups"]
        except InvalidStorageError:
            self.stdout.write("BACKUP_BUCKET is not set: the backup stays on this machine only.")
            return
        with open(path, "rb") as f:
            name = storage.save(f"database/{Path(path).name}", File(f))
        self.stdout.write(f"Uploaded to {name}")
