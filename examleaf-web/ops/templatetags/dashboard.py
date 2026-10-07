from datetime import timedelta

from allauth.account.models import EmailAddress
from django import template
from django.db.models import Count, Q
from django.utils import timezone

from accounts.models import DeletionRequest, TeacherProfile, User
from practice.models import Attempt

register = template.Library()


@register.simple_tag
def dashboard_stats():
    """Rows of (label, today, last 30 days) for the admin index; one query per row."""
    today, since = timezone.localdate(), timezone.now() - timedelta(days=30)

    def row(label, queryset, field):
        counts = queryset.aggregate(
            today=Count("pk", distinct=True, filter=Q(**{f"{field}__date": today})),
            month=Count("pk", distinct=True, filter=Q(**{f"{field}__gte": since})),
        )
        return label, counts["today"], counts["month"]

    confirmed = User.objects.filter(pk__in=EmailAddress.objects.filter(verified=True).values("user"))
    return {
        "rows": [
            row("Registrations", User.objects.all(), "created"),
            row("… with a confirmed email", confirmed, "created"),
            row("Attempts saved", Attempt.objects.all(), "created"),
        ],
        "teachers_waiting": TeacherProfile.objects.filter(verified=False).count(),
        "deletions_waiting": DeletionRequest.objects.filter(status=DeletionRequest.Status.PENDING).count(),
    }
