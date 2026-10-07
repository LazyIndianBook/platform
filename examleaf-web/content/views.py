from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.cache import cache_control
from django.views.generic import DetailView, ListView

from practice.forms import AttemptForm

from .models import Book, Paper


class HomeView(ListView):
    template_name = "home.html"
    queryset = Book.objects.select_related("subject").order_by("id")


class BookView(DetailView):
    template_name = "book.html"
    queryset = Book.objects.select_related("subject__board", "subject__class_level")

    def get_context_data(self, **kwargs):
        papers = list(self.object.papers.filter(is_published=True))
        tiers = [(label, [p for p in papers if p.tier == tier]) for tier, label in Paper.Tier.choices]
        return super().get_context_data(tiers=tiers, **kwargs)


class PaperView(DetailView):
    """/s/<code>/, the address in the QR code: a register / log-in page for visitors, the solutions for students."""

    queryset = Paper.objects.filter(is_published=True).select_related("book__subject")

    def get_object(self, queryset=None):
        return get_object_or_404(self.get_queryset(), code__iexact=self.kwargs["code"])

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.code != kwargs["code"]:  # /s/phy-e01/ -> /s/PHY-E01/
            return redirect(self.object, permanent=True)
        return self.render_to_response(self.get_context_data())

    def get_template_names(self):
        return ["solutions.html" if self.request.user.is_authenticated else "landing.html"]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.is_authenticated:
            context["questions"] = self.object.questions.select_related("solution")
            context["form"] = AttemptForm(paper=self.object)
        return context


@cache_control(max_age=86400)
def qr_png(request, code):
    """/qr/<code>.png: the QR code printed on the paper, for the printing side."""
    paper = get_object_or_404(Paper, code__iexact=code)
    return HttpResponse(paper.qr_image("png"), content_type="image/png")
