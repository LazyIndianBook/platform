from django.conf import settings
from django.core.checks import Error, Tags, register
from django.db import DatabaseError


@register(Tags.database)
def integration_keys(app_configs, databases=None, **kwargs):
    """A server (DEBUG off) that has integration accounts but no INTEGRATION_KEYS could neither read their secrets nor
    keep new ones: it refuses to start. A database check, so `manage.py migrate` runs it (the web container migrates
    before gunicorn starts), while `check --deploy` without --database, on a machine with no database, does not."""
    if settings.DEBUG or settings.TESTING or settings.INTEGRATION_KEYS or not databases:
        return []
    from .models import IntegrationAccount

    try:
        accounts = IntegrationAccount.objects.exists()
    except DatabaseError:  # not migrated yet: nothing to read
        return []
    if not accounts:
        return []
    return [
        Error(
            "INTEGRATION_KEYS is empty while integration accounts exist.",
            hint='Set the key their secrets were encrypted with (DEPLOYMENT.md, RUNBOOK.md "Integration keys").',
            id="integrations.E001",
        )
    ]
