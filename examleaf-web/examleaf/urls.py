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
from django.shortcuts import redirect
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

from .views import HealthView, live

# Three answers, for three askers (RESILIENCE.md "Health and probes"):
# /health/live/: liveness, the process answers; no database, no Redis (examleaf.views.live). docker-compose.yml's
#   container check and the Kubernetes liveness probe.
# /health/web/: readiness, this pod can serve: the database answers and no migration is waiting. Not the cache, the
#   buckets or the workers: the site runs on without them (the cache fails soft), and an outage of what every pod
#   shares must not take every pod out of traffic at once. The Kubernetes readiness probe; before gunicorn starts in
#   docker-compose.yml.
# /health/: everything, for an uptime monitor: readiness, the cache, file storage and, when a broker is in use, the
#   Celery workers of each queue (with eager tasks there is no worker to ask).
# From the internet Caddy answers 404 to all three unless the X-Health-Token header matches (Caddyfile); /health/web/
# and /health/ keep their results for 20 seconds (examleaf.views.HealthView).
READY_CHECKS = ["health_check.checks.Database", "examleaf.health.Migrations"]
MONITOR_CHECKS = [*READY_CHECKS, "health_check.checks.Cache", "health_check.checks.Storage"]


def health_checks(eager):
    """The checks of /health/: the monitor's, plus a ping of the Celery workers when a broker is in use. The ping
    waits two seconds for every worker and then checks that the default and the media queue each have one
    (examleaf.health.WorkerPing); HealthView keeps the result for 20 seconds, so the wait costs little."""
    if eager:
        return MONITOR_CHECKS
    return [*MONITOR_CHECKS, ("examleaf.health.WorkerPing", {"timeout": timedelta(seconds=2)})]


ALL_CHECKS = health_checks(settings.CELERY_TASK_ALWAYS_EAGER)
# /health/integrations/: a second monitor's, apart from the site's own: a provider down (a circuit open 30 minutes),
# dead letters or failed inbound events waiting for staff (integrations/health.py).
INTEGRATION_CHECKS = ["integrations.health.Integrations"]


# The admin's login is the website's (allauth, through headless: H2): its per-account limit, email confirmation and
# the second factor apply. Signed out, /admin/ sends to LOGIN_URL with ?next=; on the admin host (ADMIN_HOSTS, the only
# host the admin answers on then) to the console's sign-in, whose session the admin shares (cookies are per host).
_admin_login = secure_admin_login(admin.site.login)


def admin_login(request, *args, **kwargs):
    if settings.ADMIN_HOSTS and not request.user.is_authenticated:
        return redirect(f"{settings.STAFF_PANEL_URL}/sign-in/")
    return _admin_login(request, *args, **kwargs)


admin.site.login = admin_login

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
    path("health/live/", live, name="health_live"),
    path("health/web/", HealthView.as_view(checks=READY_CHECKS), name="health_web"),
    path("health/integrations/", HealthView.as_view(checks=INTEGRATION_CHECKS), name="health_integrations"),
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
