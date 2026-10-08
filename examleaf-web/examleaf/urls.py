from datetime import timedelta

from allauth.account.decorators import secure_admin_login
from allauth.headless.account.views import RequestLoginCodeView
from allauth.headless.constants import Client
from django.conf import settings
from django.contrib import admin
from django.contrib.sitemaps import Sitemap
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path, reverse
from django.views.generic import RedirectView, TemplateView

from accounts import views as accounts
from accounts.forms import ChangePhoneInput, RequestLoginCodeInput
from content import views as content
from content.models import Book
from learn import views as learn
from pages.models import SLUGS as PAGES
from pages.views import ContactView, PageView
from practice import views as practice
from shop.models import Category, Collection, Product

from .views import HealthView, RobotsView, ServiceWorkerView, manifest


class PageSitemap(Sitemap):
    def items(self):
        return ["home", "about", "revision", "shop:catalogue", "shop:quote", *PAGES]

    def location(self, item):
        return reverse(item)


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


class BookSitemap(Sitemap):
    def items(self):
        return Book.objects.order_by("id")


class ProductSitemap(Sitemap):
    def items(self):
        return Product.objects.filter(is_active=True).order_by("id")


class CategorySitemap(Sitemap):  # the shop's shelves and collections have pages of their own (Phase 6 E)
    def items(self):
        return Category.objects.order_by("path")


class CollectionSitemap(Sitemap):
    def items(self):
        return Collection.objects.filter(is_active=True).order_by("position", "pk")


# The admin's login is allauth's (H2): its per-account limit, email confirmation and the second factor apply.
admin.site.login = secure_admin_login(admin.site.login)

handler400 = "examleaf.views.bad_request"  # self-contained pages, and JSON under /api/
handler500 = "examleaf.views.server_error"  # 403, 404 and CSRF failures use templates/403.html, 404.html, 403_csrf.html

urlpatterns = [
    path("", content.HomeView.as_view(), name="home"),
    path("books/<slug:slug>/", content.BookView.as_view(), name="book"),
    path("s/<str:code>/", content.PaperView.as_view(), name="paper"),
    path("qr/<str:code>.png", content.qr_png, name="qr"),
    path("account/register/", RedirectView.as_view(pattern_name="account_signup", query_string=True)),
    path("account/record/", practice.RecordView.as_view(), name="record"),
    path("account/record/add/<str:code>/", practice.AttemptCreate.as_view(), name="attempt_add"),
    path("account/record/<int:pk>/edit/", practice.AttemptUpdate.as_view(), name="attempt_edit"),
    path("account/", accounts.AccountView.as_view(), name="account"),
    path("account/teacher/", accounts.TeacherRequestView.as_view(), name="teacher_request"),
    path("account/data/", accounts.data_export, name="data_export"),
    path("account/delete/", accounts.delete_account, name="account_delete"),
    path("account/delete/cancel/", accounts.cancel_deletion, name="account_delete_cancel"),
    path("account/parent-consent/", accounts.parent_consent_resend, name="parent_consent_resend"),
    path("account/sms-updates/", accounts.sms_updates, name="sms_updates"),
    path("c/<str:token>/", accounts.parent_consent, name="parent_consent"),  # a parent's link (email or SMS): short
    path("", include("shop.urls")),  # /shop/, /cart/, /checkout/, /account/orders/, /orders/lookup/ (shop/urls.py)
    path("account/", include("allauth.urls")),
    # allauth.headless: allauth's flows as JSON for the app and a decoupled web frontend (API.md "Frontend integration
    # guide"); its code request and phone change take the website's forms (accounts/forms.py), the rest is allauth's.
    *[
        path(f"_allauth/{client}/v1/{route}", view.as_api_view(client=Client(client), input_class=form))
        for client in settings.HEADLESS_CLIENTS
        for route, view, form in [
            ("auth/code/request", RequestLoginCodeView, RequestLoginCodeInput),
            ("account/phone", accounts.ManagePhoneView, ChangePhoneInput),  # 401 signed out (allauth: 500)
        ]
    ],
    path("_allauth/", include("allauth.headless.urls")),
    *[  # /privacy/, /terms/, …; /contact/ with its form
        path(f"{slug}/", (ContactView if slug == "contact" else PageView).as_view(), {"slug": slug}, name=slug)
        for slug in PAGES
    ],
    path("about/", TemplateView.as_view(template_name="about.html"), name="about"),
    path("robots.txt", RobotsView.as_view()),
    path("manifest.webmanifest", manifest, name="manifest"),  # the web app (PWA): examleaf/views.py
    path("sw.js", ServiceWorkerView.as_view(), name="sw"),
    path("offline/", TemplateView.as_view(template_name="offline.html"), name="offline"),
    path("favicon.ico", RedirectView.as_view(url=settings.STATIC_URL + "img/favicon-32.png", permanent=True)),
    path(
        "sitemap.xml",
        sitemap,
        {
            "sitemaps": {
                "pages": PageSitemap,
                "books": BookSitemap,
                "shop": ProductSitemap,
                "shelves": CategorySitemap,
                "collections": CollectionSitemap,
            }
        },
    ),
    path("health/", HealthView.as_view(checks=ALL_CHECKS), name="health"),
    path("health/web/", HealthView.as_view(checks=WEB_CHECKS), name="health_web"),
    path("api/", include("examleaf.api_urls")),  # REST API: api/, examleaf/api_urls.py
    path("revision/", learn.revision, name="revision"),  # the revision course's page (the course is in the app)
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
