import hashlib
from pathlib import Path

from django.core.files import File
from django.core.files.base import ContentFile
from django.core.files.storage import InvalidStorageError, storages
from django.core.management.base import BaseCommand


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class Command(BaseCommand):
    help = (
        "Upload a backup file to the private bucket set by BACKUP_BUCKET (django-storages), with its SHA-256 beside it "
        "(<name>.sha256: the console's System page shows it, a restore checks it); skipped without it."
    )

    def add_arguments(self, parser):
        parser.add_argument("path")

    def handle(self, path, **options):
        try:
            storage = storages["backups"]
        except InvalidStorageError:
            self.stdout.write("BACKUP_BUCKET is not set: the backup stays on this machine only.")
            return
        digest = sha256_of(path)  # first: a file that changes while it uploads would not match its checksum
        with open(path, "rb") as f:
            name = storage.save(f"database/{Path(path).name}", File(f))
        storage.save(f"{name}.sha256", ContentFile(f"{digest}  {Path(name).name}\n".encode()))
        self.stdout.write(f"Uploaded to {name} (SHA-256 {digest})")
