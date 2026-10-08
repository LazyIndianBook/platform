from django.conf import settings
from django.core.checks import Error, register


@register()
def book_code_secret(app_configs, **kwargs):
    """Book codes are kept as HMACs keyed with LEARN_CODE_SECRET; without it the key is printed in the source, and a
    copy of the database could be searched for the codes not yet redeemed (L7). A server (DEBUG off) refuses to start
    without it: the web container runs manage.py migrate, which runs this check, before gunicorn."""
    if settings.DEBUG or settings.TESTING or settings.LEARN_CODE_SECRET:
        return []
    return [
        Error(
            "LEARN_CODE_SECRET is empty.",
            hint="Set it once, before the first print run (DEPLOYMENT.md).",
            id="learn.E001",
        )
    ]
