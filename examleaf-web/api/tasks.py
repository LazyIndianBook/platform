from celery import shared_task
from django.core.management import call_command


@shared_task
def flush_expired_tokens():
    """Daily (celery beat, scheduled by api/migrations/0001): forget refresh tokens past their lifetime and their
    blacklist entries; every log-in and every refresh adds one."""
    call_command("flushexpiredtokens")
