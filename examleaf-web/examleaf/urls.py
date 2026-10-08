from datetime import timedelta

from allauth.account.decorators import secure_admin_login
from django.conf import settings
from django.contrib import admin
from django.contrib.sitemaps import Sitemap
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path, reverse
from django.views.generic import RedirectView, TemplateView

from accounts import views as accounts
from content import views as content
from content.models import Book
from pages.models import SLUGS as PAGES
from pages.views import PageView
from practice import views as practice
from shop.models import Product

from .views import HealthView, RobotsView


class PageSitemap(Sitemap):
    def items(self):
        return ["home", "about", *PAGES]

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
    path("consent/<str:token>/", accounts.parent_consent, name="parent_consent"),  # the link emailed to a parent
    path("", include("shop.urls")),  # /shop/, /cart/, /checkout/, /account/orders/, /orders/lookup/ (shop/urls.py)
    path("account/", include("allauth.urls")),
    *[path(f"{slug}/", PageView.as_view(), {"slug": slug}, name=slug) for slug in PAGES],  # /privacy/, /terms/, …
    path("about/", TemplateView.as_view(template_name="about.html"), name="about"),
    path("robots.txt", RobotsView.as_view()),
    path("favicon.ico", RedirectView.as_view(url=settings.STATIC_URL + "img/favicon-32.png", permanent=True)),
    path("sitemap.xml", sitemap, {"sitemaps": {"pages": PageSitemap, "books": BookSitemap, "shop": ProductSitemap}}),
    path("health/", HealthView.as_view(checks=ALL_CHECKS), name="health"),
    path("health/web/", HealthView.as_view(checks=WEB_CHECKS), name="health_web"),
    path("api/", include("examleaf.api_urls")),  # REST API: api/, examleaf/api_urls.py
    path("admin/", admin.site.urls),
]

if settings.DEBUG_TOOLBAR:
    from debug_toolbar.toolbar import debug_toolbar_urls

    urlpatterns += debug_toolbar_urls()
