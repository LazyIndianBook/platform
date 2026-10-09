"""The shipping app's Celery tasks. Each is idempotent and takes ids; those that call a carrier are IntegrationTasks
(retried with the refund task's backoff, put back while the account's circuit is open, written to the dead-letter
list when they give up). The beat entries are in settings.py ("shipping-…")."""

import logging

from celery import shared_task
from django.utils import timezone

from integrations.models import InboundEvent, IntegrationAccount
from integrations.tasks import IntegrationTask
from shop.models import Shipment

from . import messages, services
from .carriers import CARRIERS, carrier_for
from .carriers.shiprocket import RENEW_BEFORE
from .models import ShipmentDetail

logger = logging.getLogger(__name__)


def courier_accounts():
    return IntegrationAccount.objects.filter(provider__in=[name for name in CARRIERS if name != "manual"], enabled=True)


@shared_task(base=IntegrationTask, bind=True)
def book_shipment(self, shipment_id, courier_company_id=None):
    """Book a prepared parcel (services.book): the carrier's order and AWB, then its label."""
    services.book(Shipment.objects.get(pk=shipment_id), courier_company_id)


@shared_task(base=IntegrationTask, bind=True)
def fetch_label(self, shipment_id):
    """The label's PDF, kept with us once (services.fetch_label)."""
    services.fetch_label(Shipment.objects.get(pk=shipment_id))


class InboundEventTask(IntegrationTask):
    """An inbound event that cannot be processed is marked failed (and replayable, InboundEvent.replay) rather than
    written to the dead-letter list: the event is its own record."""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        if event := InboundEvent.objects.filter(pk=(args or [kwargs.get("event_id")])[0]).first():
            event.fail(f"{type(exc).__name__}: {exc}")


@shared_task(base=InboundEventTask, bind=True)
def process_inbound_event(self, event_id):
    """A webhook stored by /api/hooks/parcel-events/: its scans applied (services.process_event), a claim of delivered,
    returned or lost read again at the carrier first. Once: a processed event is left alone."""
    event = InboundEvent.objects.get(pk=event_id)
    if event.processed_at or event.state == InboundEvent.State.REJECTED:
        return
    new = services.process_event(event)
    event.processed_at = timezone.now()
    if new is None:
        event.error = "No parcel of ours has this AWB."
    elif not new:
        event.state = InboundEvent.State.DUPLICATE
    event.save(update_fields=["processed_at", "state", "error"])


@shared_task
def poll_tracking():
    """Every two hours: the tracking of the parcels silent for 6 hours (services.poll)."""
    return services.poll()


@shared_task(base=IntegrationTask, bind=True)
def sync_statement(self):
    """Daily: the carriers' wallet statements as ShipmentCharge rows (services.sync_statement)."""
    return {account.pk: services.sync_statement(account) for account in courier_accounts()}


@shared_task
def check_cod_remittances():
    """Daily: COD remittances awaited, remitted, overdue or mismatched (services.check_cod)."""
    return services.check_cod()


@shared_task(base=IntegrationTask, bind=True)
def check_weight_discrepancies(self):
    """Daily: the carriers' weight disputes as exceptions due in 7 working days (services.check_discrepancies)."""
    return {account.pk: len(services.check_discrepancies(account)) for account in courier_accounts()}


@shared_task(base=IntegrationTask, bind=True)
def renew_token(self):
    """Daily: a new Shiprocket token from day 9 of the old one's 10 (one worker at a time: a cache lock)."""
    renewed = 0
    for account in courier_accounts().filter(provider="shiprocket"):
        expires = account.token_expires_at
        if not account.token or expires is None or expires - timezone.now() <= RENEW_BEFORE:
            carrier_for(account).client.renew_token(stale=account.token)  # test mode: the recorded double's
            renewed += 1
    return renewed


@shared_task
def survey_pins():
    """Weekly: the North-East's PINs, a batch at a time (services.survey_pins)."""
    return {account.pk: services.survey_pins(account) for account in courier_accounts()}


@shared_task
def send_held_messages():
    """At 08:00 (India time): the SMS held through the night, if still true."""
    return sum(messages.send_held(detail) for detail in ShipmentDetail.objects.exclude(sms_held=""))
