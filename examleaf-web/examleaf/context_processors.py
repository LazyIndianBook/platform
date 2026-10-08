from django.conf import settings


def site(request):
    """For the templates: whether the solutions need a log-in (SOLUTIONS_REQUIRE_LOGIN), so that the words about
    registering fit the setting; whether SMS go out (phone log-in, order SMS)."""
    return {
        "solutions_require_login": settings.SOLUTIONS_REQUIRE_LOGIN,
        "sms_enabled": settings.SMS_ENABLED,
        "site_url": settings.SITE_URL,  # canonical and Open Graph URLs (base.html)
    }
