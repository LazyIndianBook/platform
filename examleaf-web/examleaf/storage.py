"""The public bucket's storage (settings.STORAGES["public"] with buckets). django-pictures puts a storage's
deconstruct() into every picture task it queues (Redis); S3Storage's is its constructor arguments, the secret key among
them (L12). This one names only its class and reads its options from settings wherever it is made (web, worker)."""

from django.conf import settings
from storages.backends.s3 import S3Storage


class PublicS3Storage(S3Storage):
    def __init__(self, **options):
        super().__init__(**{**settings.STORAGES["public"]["OPTIONS"], **options})

    def deconstruct(self):
        return f"{__name__}.PublicS3Storage", (), {}
