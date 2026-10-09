"""The integrations' check, for /health/integrations/ (examleaf/urls.py): a second uptime monitor's address, apart from
/health/, because a courier that is down is not the site that is down (DEPLOYMENT.md "Integrations")."""

import dataclasses
from datetime import timedelta

from django.utils import timezone
from health_check.base import HealthCheck
from health_check.exceptions import ServiceUnavailable

OPEN_TOO_LONG = timedelta(minutes=30)  # research 3.10: an alert when a circuit has been open half an hour


@dataclasses.dataclass
class Integrations(HealthCheck):
    """Fails while an enabled account has been unavailable (its circuit not closed) for OPEN_TOO_LONG, or while dead
    letters or failed inbound events wait for staff. The message names the provider and the counts only."""

    def run(self):
        from .models import InboundEvent, IntegrationAccount, IntegrationFailure

        problems = []
        since = timezone.now() - OPEN_TOO_LONG
        unavailable = IntegrationAccount.objects.filter(enabled=True, opened_at__lte=since)
        for account in unavailable.exclude(circuit_state=IntegrationAccount.Circuit.CLOSED):
            problems.append(f"{account} unavailable since {timezone.localtime(account.opened_at):%d %b %H:%M}")
        if waiting := IntegrationFailure.objects.filter(state=IntegrationFailure.State.OPEN).count():
            problems.append(f"{waiting} dead letter(s) waiting")
        if failed := InboundEvent.objects.filter(state=InboundEvent.State.FAILED).count():
            problems.append(f"{failed} inbound event(s) failed")
        if problems:
            raise ServiceUnavailable("; ".join(problems))
