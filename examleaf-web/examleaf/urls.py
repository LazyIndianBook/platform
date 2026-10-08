from datetime import timedelta

from allauth.account.decorators import secure_admin_login
from allauth.headless.account.views import (
    ConfirmLoginCodeView,
    LoginView,
    RequestLoginCodeView,
    VerifyEmailView,
    VerifyPhoneView,
)
from allauth.headless.constants import Client
from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from accounts import views as accounts
from accounts.forms import (
    ChangePhoneInput,
    ConfirmLoginCodeInput,
    LoginInput,
    RequestLoginCodeInput,
    VerifyEmailInput,
    VerifyPhoneInput,
)
from content import views as content

from .views import HealthView

# /health/web/: what the web container needs (database, cache, file storage); docker-compose.yml's health check.
# /health/: that plus the Celery workers when a broker is in use (with eager tasks there is no worker to ask); for an
# uptime monitor. The container check leaves Celery out: the worker starts only once the web container is healthy.
# From the internet Caddy answers 404 to both unless the X-Health-Token header matches (Caddyfile); results are kept
# for 20 seconds (examleaf.views.HealthView).
WEB_CHECKS = ["health_check.checks.Database", "health_check.checks.Cache", "health_check.checks.Storage"]


def health_checks(eager):
    """The checks of /health/: the web ones, plus a ping of the Celery workers when a broker is in use. limit=1: the
    first worker's answer is enough; without it the ping waits out its whole timeout and holds a gunicorn worker."""
    if eager:
        return WEB_CHECKS
    return [*WEB_CHECKS, ("health_check.contrib.celery.Ping", {"timeout": timedelta(seconds=3), "limit": 1})]


ALL_CHECKS = health_checks(settings.CELERY_TASK_ALWAYS_EAGER)


# The admin's login is the website's (allauth, through headless: H2): its per-account limit, email confirmation and
# the second factor apply. Signed out, /admin/ sends to LOGIN_URL with ?next=.
admin.site.login = secure_admin_login(admin.site.login)

handler400 = "examleaf.views.bad_request"  # plain pages, and JSON under /api/
handler500 = "examleaf.views.server_error"  # 403, 404 and CSRF failures use templates/403.html, 404.html, 403_csrf.html

# Django answers only the paths Caddy sends it (Caddyfile, "Django's own paths"): the website's pages, /s/<code>/
# included, are the Next.js frontend's (examleaf-frontend/), on the same origin.
urlpatterns = [
    path("qr/<str:code>.png", content.qr_png, name="qr"),
    path("", include("shop.urls")),  # Razorpay's webhook and the product pictures (shop/urls.py)
    path("account/", include("allauth.urls")),  # HEADLESS_ONLY: Google's log-in callback, /account/google/…
    # allauth.headless: allauth's flows as JSON for the app and the website (API.md "Frontend integration guide"); its
    # log-in, code request, code tries and phone change keep the site's rules (accounts/forms.py), the rest allauth's.
    *[
        path(f"_allauth/{client}/v1/{route}", view.as_api_view(client=Client(client), input_class=form))
        for client in settings.HEADLESS_CLIENTS
        for route, view, form in [
            ("auth/login", LoginView, LoginInput),
            ("auth/code/request", RequestLoginCodeView, RequestLoginCodeInput),
            ("auth/code/confirm", ConfirmLoginCodeView, ConfirmLoginCodeInput),
            ("auth/email/verify", VerifyEmailView, VerifyEmailInput),
            ("auth/phone/verify", VerifyPhoneView, VerifyPhoneInput),
            ("account/phone", accounts.ManagePhoneView, ChangePhoneInput),  # 401 signed out (allauth: 500)
        ]
    ],
    path("_allauth/", include("allauth.headless.urls")),
    path("health/", HealthView.as_view(checks=ALL_CHECKS), name="health"),
    path("health/web/", HealthView.as_view(checks=WEB_CHECKS), name="health_web"),
    path("api/", include("examleaf.api_urls")),  # REST API: api/, examleaf/api_urls.py
    path("learn/", include("learn.urls")),  # revision course: clip files behind signed links, staff preview
    path("admin/", admin.site.urls),
]

# The email provider's bounce and complaint webhooks (ops.models.EmailSuppression). Their only protection is the
# HTTP basic auth of ANYMAIL_WEBHOOK_SECRET: without it Anymail would take events from anyone, so no URL then.
if settings.ANYMAIL.get("WEBHOOK_SECRET"):
    urlpatterns.append(path("anymail/", include("anymail.urls")))

if settings.DEBUG_TOOLBAR:
    from debug_toolbar.toolbar import debug_toolbar_urls

    urlpatterns += debug_toolbar_urls()
