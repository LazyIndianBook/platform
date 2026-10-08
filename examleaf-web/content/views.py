from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.cache import patch_cache_control
from django.views.decorators.cache import cache_page
from django.views.generic import DetailView, ListView

from practice.forms import AttemptForm
from shop.models import Product, ShippingRate
from shop.seo import organization_jsonld

from .models import Book, Paper


class HomeView(ListView):
    template_name = "home.html"
    queryset = Book.objects.select_related("subject").order_by("id")

    def get_context_data(self, **kwargs):
        offers = home_offers()
        return super().get_context_data(
            jsonld=[organization_jsonld()],  # templates/_head_meta.html
            offers=offers,
            same_price=not any(offer["from"] for offer in offers),
            shipping_rates=ShippingRate.objects.filter(is_active=True),  # the FAQ's delivery fees
            **kwargs,
        )


def home_offers():
    """Q.4 of the home page, one card for each kind of printed book: the cheapest one on sale, what it saves on the
    MRP, and whether others of the kind cost more (the card then says "from")."""
    offers = {}
    kinds = [Product.Kind.SAMPLE_PAPERS, Product.Kind.SOLUTIONS, Product.Kind.BUNDLE]
    for product in Product.objects.filter(is_active=True, kind__in=kinds).select_related("subject").order_by("price"):
        if product.kind in offers:
            offers[product.kind]["from"] |= product.price != offers[product.kind]["product"].price
        else:
            offers[product.kind] = {"product": product, "from": False, "saving": product.mrp - product.price}
    return [offers[kind] for kind in kinds if kind in offers]


class BookView(DetailView):
    template_name = "book.html"
    queryset = Book.objects.select_related("subject__board", "subject__class_level")

    def get_context_data(self, **kwargs):
        papers = list(self.object.papers.filter(is_published=True))
        tiers = [(label, [p for p in papers if p.tier == tier]) for tier, label in Paper.Tier.choices]
        return super().get_context_data(tiers=tiers, og={"title": self.object.title}, **kwargs)


OPEN_SOLUTIONS_MAX_AGE = 300  # seconds a shared cache may keep open solutions


def cache_solutions(response, user):
    """Private while the page depends on the log-in (landing or solutions; the record form's CSRF token). Open
    solutions seen by a visitor are the same for everyone: public for a few minutes."""
    if settings.SOLUTIONS_REQUIRE_LOGIN or user.is_authenticated:
        patch_cache_control(response, private=True)
    else:
        patch_cache_control(response, public=True, max_age=OPEN_SOLUTIONS_MAX_AGE)
    return response


class PaperView(DetailView):
    """/s/<code>/, the address in the QR code: the solutions, for signed-in students (a register / log-in page for
    visitors) or for everyone (SOLUTIONS_REQUIRE_LOGIN=0); saving marks always needs an account."""

    queryset = Paper.objects.filter(is_published=True).select_related("book__subject")

    def get_object(self, queryset=None):
        return get_object_or_404(self.get_queryset(), code__iexact=self.kwargs["code"])

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.code != kwargs["code"]:  # /s/phy-e01/ -> /s/PHY-E01/
            return redirect(self.object, permanent=True)
        return cache_solutions(self.render_to_response(self.get_context_data()), request.user)

    @property
    def shows_solutions(self):
        return self.request.user.is_authenticated or not settings.SOLUTIONS_REQUIRE_LOGIN

    def get_template_names(self):
        return ["solutions.html" if self.shows_solutions else "landing.html"]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.shows_solutions:
            context["questions"] = self.object.questions.select_related("solution")
        if self.request.user.is_authenticated:
            context["form"] = AttemptForm(paper=self.object)
        return context


@cache_page(86400)  # a day, in the cache and in browsers: it never changes, and drawing it costs a little each time
def qr_png(request, code):
    """/qr/<code>.png: the QR code printed on the paper, for the printing side; published papers only (I3)."""
    paper = get_object_or_404(Paper, code__iexact=code, is_published=True)
    return HttpResponse(paper.qr_image("png"), content_type="image/png")
