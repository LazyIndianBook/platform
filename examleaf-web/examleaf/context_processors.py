from django.conf import settings
from django.utils.functional import SimpleLazyObject
from django.utils.http import url_has_allowed_host_and_scheme

from content.models import Book


def login_next(request):
    """Where the header's Log in and Register links bring the visitor back to: this page, or on the log-in pages
    (/account/...) the `next` they were given. A path on this site only (no host is allowed, so not //other.site/),
    and not the home page, where a log-in lands anyway."""
    path = request.GET.get("next", "") if request.path.startswith("/account/") else request.get_full_path()
    return path if path.startswith("/") and path != "/" and url_has_allowed_host_and_scheme(path, None) else ""


def site(request):
    """For the templates: whether the solutions need a log-in (SOLUTIONS_REQUIRE_LOGIN), so that the words about
    registering fit the setting; whether SMS go out (phone log-in, order SMS); the books for the footer and the 404 page
    (read on the first use in a page, once)."""
    return {
        "solutions_require_login": settings.SOLUTIONS_REQUIRE_LOGIN,
        "sms_enabled": settings.SMS_ENABLED,
        "consent_by_link": settings.PARENTAL_CONSENT_MODE == "verified",  # the parent confirms through a link
        "site_url": settings.SITE_URL,  # canonical and Open Graph URLs (base.html)
        "login_next": login_next(request),  # the header's Log in and Register links
        "site_books": SimpleLazyObject(lambda: list(Book.objects.select_related("subject").order_by("id"))),
    }
