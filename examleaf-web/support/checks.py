from django.conf import settings
from django.core.checks import Error, Tags, register


@register(Tags.database)
def integration_keys(app_configs, databases=None, **kwargs):
    """A server (DEBUG off) keeps every ticket's requester's email address and mobile number encrypted with
    INTEGRATION_KEYS (integrations.crypto): without one it could take no ticket (the contact form would fail), so it
    refuses to migrate, and so to start. A database check, as integrations.E001: `manage.py migrate` runs it (the web
    container migrates before gunicorn starts), `check --deploy` without --database does not."""
    if settings.DEBUG or settings.TESTING or settings.INTEGRATION_KEYS or not databases:
        return []
    return [
        Error(
            "INTEGRATION_KEYS is empty: support tickets cannot keep their requesters' contact details.",
            hint="Set a Fernet key (DEPLOYMENT.md, Integrations and Support).",
            id="support.E001",
        )
    ]
