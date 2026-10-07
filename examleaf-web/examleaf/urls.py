from django.conf import settings
from django.contrib import admin
from django.contrib.sitemaps import Sitemap
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path, reverse
from django.views.generic import RedirectView, TemplateView

from content import views as content
from content.models import Book
from practice import views as practice


class PageSitemap(Sitemap):
    def items(self):
        return ["home", "about", "privacy"]

    def location(self, item):
        return reverse(item)


class BookSitemap(Sitemap):
    def items(self):
        return Book.objects.order_by("id")


urlpatterns = [
    path("", content.HomeView.as_view(), name="home"),
    path("books/<slug:slug>/", content.BookView.as_view(), name="book"),
    path("s/<str:code>/", content.PaperView.as_view(), name="paper"),
    path("qr/<str:code>.png", content.qr_png, name="qr"),
    path("account/register/", RedirectView.as_view(pattern_name="account_signup", query_string=True)),
    path("account/record/", practice.RecordView.as_view(), name="record"),
    path("account/record/add/<str:code>/", practice.AttemptCreate.as_view(), name="attempt_add"),
    path("account/record/<int:pk>/edit/", practice.AttemptUpdate.as_view(), name="attempt_edit"),
    path("account/", include("allauth.urls")),
    path("privacy/", TemplateView.as_view(template_name="privacy.html"), name="privacy"),
    path("about/", TemplateView.as_view(template_name="about.html"), name="about"),
    path("sitemap.xml", sitemap, {"sitemaps": {"pages": PageSitemap, "books": BookSitemap}}),
    path("admin/", admin.site.urls),
]

if settings.DEBUG_TOOLBAR:
    from debug_toolbar.toolbar import debug_toolbar_urls

    urlpatterns += debug_toolbar_urls()
