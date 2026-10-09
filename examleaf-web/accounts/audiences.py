"""Who may be sent marketing (plan 5.15 "Children's rules"; research-rbac-security.md 4.3): the one audience function
every marketing send, segment, ad audience or export goes through (Phase D's Marketing; nothing sends marketing yet).
The DPDP Act forbids targeted advertising at anyone under 18 (s.9(3)), which no consent lifts, and consent is per
purpose and withdrawn as easily as given (s.6(4)); so a minor is never marketable, and an account of unknown age only
on a consent verified as an identifiable adult's (a link, the adult's own account, DigiLocker, or staff with
evidence: ConsentRecord.verified_at)."""

from django.db.models import F, OuterRef, Q, Subquery
from django.utils import timezone

from .models import ConsentRecord, DeletionRequest


def adult_born_by(today=None):
    """The latest birthday of someone 18 or over today (accounts.models.age_on's rule, 29 February included)."""
    today = today or timezone.localdate()
    try:
        return today.replace(year=today.year - 18)
    except ValueError:  # 29 February, eighteen years before a year without one
        return today.replace(year=today.year - 18, day=28)


def marketable(queryset, channel, today=None):
    """The accounts of `queryset` that may get marketing on `channel` (email, sms or whatsapp): active, not waiting
    for their deletion, and either 18 or over by their date of birth with a marketing consent for that channel (or for
    every channel) given and not withdrawn since, or of an unknown age with such a consent verified. Every account
    under 18 is left out, whatever any consent says. One query, whatever the number of accounts."""
    if channel not in ConsentRecord.Channel.values:
        raise ValueError(f"A channel: {', '.join(ConsentRecord.Channel.values)}.")
    marketing = ConsentRecord.objects.filter(
        user=OuterRef("pk"), purpose=ConsentRecord.Purpose.MARKETING, channel__in=[channel, ""]
    ).order_by("-created", "-pk")

    def newest(rows):
        return Subquery(rows.values("created")[:1])

    accounts = (
        queryset.filter(is_active=True)
        .exclude(deletion_requests__status=DeletionRequest.Status.PENDING)
        .annotate(
            marketing_given=newest(marketing.filter(event=ConsentRecord.Event.GIVEN)),
            marketing_verified=newest(marketing.filter(event=ConsentRecord.Event.GIVEN, verified_at__isnull=False)),
            marketing_withdrawn=newest(marketing.filter(event=ConsentRecord.Event.WITHDRAWN)),
        )
    )

    def in_force(given):
        later = Q(marketing_withdrawn__isnull=True) | Q(**{f"{given}__gt": F("marketing_withdrawn")})
        return Q(**{f"{given}__isnull": False}) & later

    adult = Q(date_of_birth__lte=adult_born_by(today))
    unknown_age = Q(date_of_birth__isnull=True)
    return accounts.filter((adult & in_force("marketing_given")) | (unknown_age & in_force("marketing_verified")))
