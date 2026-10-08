from django.conf import settings
from django.utils.functional import SimpleLazyObject

from content.models import Book


def site(request):
    """For the templates: whether the solutions need a log-in (SOLUTIONS_REQUIRE_LOGIN), so that the words about
    registering fit the setting; whether SMS go out (phone log-in, order SMS); the books for the footer and the 404 page
    (read on the first use in a page, once)."""
    return {
        "solutions_require_login": settings.SOLUTIONS_REQUIRE_LOGIN,
        "sms_enabled": settings.SMS_ENABLED,
        "consent_by_link": settings.PARENTAL_CONSENT_MODE == "verified",  # the parent confirms through a link
        "site_url": settings.SITE_URL,  # canonical and Open Graph URLs (base.html)
        "site_books": SimpleLazyObject(lambda: list(Book.objects.select_related("subject").order_by("id"))),
    }
