import django_filters
from django import forms
from django.core.validators import MaxValueValidator, MinValueValidator

from content.models import Paper, Subject

from .models import NOTES_MAX_LENGTH, Attempt, check_can_save


class AttemptForm(forms.ModelForm):
    notes = forms.CharField(
        label="What to revise", required=False, max_length=NOTES_MAX_LENGTH, widget=forms.Textarea(attrs={"rows": 2})
    )

    class Meta:
        model = Attempt
        fields = ["date", "marks_obtained", "time_taken_minutes", "notes"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"})}
        labels = {"time_taken_minutes": "Time taken (minutes)"}
        error_messages = {  # what each box needs, rather than "This field is required."
            "date": {"required": "Enter the date you sat the paper.", "invalid": "Enter the date you sat the paper."},
            "marks_obtained": {
                "required": "Enter the marks you gave yourself.",
                "invalid": "Enter the marks as a number, such as 52.5.",
                "max_decimal_places": "Use one decimal place at most, such as 52.5.",
            },
            "time_taken_minutes": {"invalid": "Enter the minutes as a number, such as 170."},
        }

    def __init__(self, *args, paper, **kwargs):
        super().__init__(*args, **kwargs)
        self.paper = paper
        marks = self.fields["marks_obtained"]
        marks.label = f"Marks obtained (out of {paper.full_marks})"
        marks.widget.attrs.update(min=0, max=paper.full_marks, step="0.5", inputmode="decimal")
        marks.validators += [
            MinValueValidator(0, "Marks cannot be below 0."),
            MaxValueValidator(paper.full_marks, f"At most {paper.full_marks}, the paper's full marks."),
        ]

    def clean(self):
        check_can_save(self.instance.user, self.paper, new=self.instance.pk is None)
        return super().clean()


class AttemptFilter(django_filters.FilterSet):
    subject = django_filters.ModelChoiceFilter(
        field_name="paper__book__subject",
        queryset=Subject.objects.select_related("board", "class_level"),
        empty_label="All subjects",
    )  # the choice labels print board and class: no query per subject
    tier = django_filters.ChoiceFilter(field_name="paper__tier", choices=Paper.Tier.choices, empty_label="All tiers")

    class Meta:
        model = Attempt
        fields = ["subject", "tier"]
