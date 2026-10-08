from django.conf import settings


def site(request):
    """For the templates: whether the solutions need a log-in (SOLUTIONS_REQUIRE_LOGIN), so that the words about
    registering fit the setting."""
    return {"solutions_require_login": settings.SOLUTIONS_REQUIRE_LOGIN}
