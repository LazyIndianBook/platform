import django_filters
from django import forms
from django.core.validators import MaxValueValidator, MinValueValidator

from content.models import Paper, Subject

from .models import Attempt


class AttemptForm(forms.ModelForm):
    class Meta:
        model = Attempt
        fields = ["date", "marks_obtained", "time_taken_minutes", "notes"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"}), "notes": forms.Textarea(attrs={"rows": 2})}
        labels = {"time_taken_minutes": "Time taken (minutes)"}

    def __init__(self, *args, paper, **kwargs):
        super().__init__(*args, **kwargs)
        self.paper = paper
        marks = self.fields["marks_obtained"]
        marks.label = f"Marks obtained (out of {paper.full_marks})"
        marks.widget.attrs.update(min=0, max=paper.full_marks, step="0.5", inputmode="decimal")
        marks.validators += [MinValueValidator(0), MaxValueValidator(paper.full_marks)]


class AttemptFilter(django_filters.FilterSet):
    subject = django_filters.ModelChoiceFilter(
        field_name="paper__book__subject", queryset=Subject.objects.select_related("board", "class_level"),
        empty_label="All subjects")  # the choice labels print board and class: no query per subject
    tier = django_filters.ChoiceFilter(field_name="paper__tier", choices=Paper.Tier.choices, empty_label="All tiers")

    class Meta:
        model = Attempt
        fields = ["subject", "tier"]
