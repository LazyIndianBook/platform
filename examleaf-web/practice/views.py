from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import CreateView, UpdateView
from django_filters.views import FilterView

from content.models import Paper
from content.views import PaperView

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
        # an empty result names the filter ("Hard Physics papers"), unless nothing is saved at all
        data = self.filterset.form.cleaned_data if self.filterset.is_valid() else {}
        subject, tier = data.get("subject"), dict(Paper.Tier.choices).get(data.get("tier"))
        if subject or tier:
            context["filtered"] = " ".join(word for word in (tier, subject and subject.name, "papers") if word)
        context["saved_any"] = bool(context["object_list"]) or self.request.user.attempts.exists()
        return context


class AttemptMixin(LoginRequiredMixin, SuccessMessageMixin):
    form_class = AttemptForm
    template_name = "attempt_form.html"
    success_url = reverse_lazy("record")
    success_message = "Saved to your record."


class AttemptCreate(AttemptMixin, CreateView):
    """The record card of the solutions page posts here: saved, the student is back on the paper (#record, the form's
    action too); a form with errors is shown in that card, on the paper."""

    def get_form_kwargs(self):
        self.paper = get_object_or_404(Paper, code__iexact=self.kwargs["code"], is_published=True)
        instance = Attempt(user=self.request.user, paper=self.paper)
        return {**super().get_form_kwargs(), "instance": instance, "paper": self.paper}

    def get_success_url(self):
        return self.paper.get_absolute_url() + "#record"

    def form_invalid(self, form):
        page = PaperView(request=self.request, kwargs={"code": self.paper.code}, object=self.paper)
        return page.render_to_response(page.get_context_data(form=form))


class AttemptUpdate(AttemptMixin, UpdateView):
    def get_queryset(self):
        return self.request.user.attempts.select_related("paper")

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "paper": self.object.paper}
