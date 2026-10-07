from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import CreateView, UpdateView
from django_filters.views import FilterView

from content.models import Paper

from .forms import AttemptFilter, AttemptForm
from .models import Attempt


class RecordView(LoginRequiredMixin, FilterView):
    """My record: the student's attempts, filterable by subject and tier, with the average per tier."""

    filterset_class = AttemptFilter
    template_name = "record.html"

    def get_queryset(self):
        return self.request.user.attempts.select_related("paper__book__subject")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        averages = []
        for tier, label in Paper.Tier.choices:
            rows = [a for a in context["object_list"] if a.paper.tier == tier]
            if rows:
                averages.append((label, len(rows), round(sum(a.percent for a in rows) / len(rows))))
        context["averages"] = averages
        return context


class AttemptMixin(LoginRequiredMixin, SuccessMessageMixin):
    form_class = AttemptForm
    template_name = "attempt_form.html"
    success_url = reverse_lazy("record")
    success_message = "Saved to your record."


class AttemptCreate(AttemptMixin, CreateView):
    def get_form_kwargs(self):
        paper = get_object_or_404(Paper, code__iexact=self.kwargs["code"], is_published=True)
        return {**super().get_form_kwargs(), "instance": Attempt(user=self.request.user, paper=paper), "paper": paper}


class AttemptUpdate(AttemptMixin, UpdateView):
    def get_queryset(self):
        return self.request.user.attempts.select_related("paper")

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "paper": self.object.paper}
