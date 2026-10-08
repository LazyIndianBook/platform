import django_filters

from content.models import Paper, Subject

from .models import Attempt


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
