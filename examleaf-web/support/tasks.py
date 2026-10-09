"""The support app's tasks (RESILIENCE.md "Celery, task by task"). Every 15 minutes (`support-watch`): the clocks'
watch (an inbox item at 75 % of each clock, a breach flagged once at its due time), resolved tickets closed after 4
days, the SMS acknowledgements held through the night sent once it is morning. Nightly (`support-purge`, 03:45): the
spam kept 30 days and the saved replies' bin purged. On demand: a new ticket's acknowledgement, and an email forwarded
to the support address. Each is safe to run twice: the clocks' flags, the acknowledgement's own row lock and the
email's Message-ID make a second run do nothing a first one did."""

import logging
from datetime import timedelta

from celery import shared_task
from django.db import IntegrityError
from django.utils import timezone

from examleaf.celery import single_run
from integrations.tasks import InboundEventTask

from . import services

logger = logging.getLogger(__name__)
FLOOD = 20  # emails an hour from one address: past it, a loop with someone else's autoresponder (they are dropped)


@shared_task
def send_acknowledgement(ticket_id):
    """A new ticket's acknowledgement (services.acknowledge: once, under the ticket's lock)."""
    services.acknowledge(ticket_id)


@shared_task
@single_run(300)
def watch_clocks():
    """Every 15 minutes: the clocks' warnings and breaches, the auto-close, the held acknowledgements."""
    counts = services.watch()
    counts["closed"] = services.close_resolved()
    counts["held_sent"] = services.send_held()
    return counts


@shared_task
@single_run(300)
def purge():
    """Nightly: spam quarantined 30 days, and saved replies in the bin 30 days."""
    from .models import SavedReply

    replies = SavedReply.objects.filter(deleted_at__lte=timezone.now() - timedelta(days=30)).delete()[0]
    return {"spam": services.purge_spam(), "saved_replies": replies}


def flooded(sender):
    """Whether this address sent more than FLOOD emails in the last hour (counted in the cache; never while the cache
    cannot be read: an email is not lost for that)."""
    from shop.views import hits

    from .models import contact_hash

    count = hits("support-mail", contact_hash("email", sender), 3600)
    return count is not None and count > FLOOD


@shared_task(base=InboundEventTask, bind=True)
def process_inbound_mail(self, event_id):
    """An email forwarded to the support address (an InboundEvent the hook kept): on the ticket it answers, or a new
    ticket (quarantined as spam when the provider says spam or a virus); nothing for a duplicate (its Message-ID seen:
    the event says so) or what the loop guard drops (the event says why). A failure marks the event failed, to be
    replayed."""
    from integrations.models import InboundEvent

    from . import mail
    from .models import Ticket, TicketMessage

    event = InboundEvent.objects.filter(pk=event_id).first()
    if event is None or event.processed_at:
        return None
    inbound = mail.parse(event.body)
    why = mail.guard(inbound) or ("too many emails from one sender" if flooded(inbound.sender) else "")
    seen = not why and TicketMessage.objects.filter(message_id=inbound.message_id).exists()
    ticket = None
    if not (why or seen):
        try:
            if found := mail.thread(inbound):
                ticket = services.receive(found, inbound, event)
            else:
                ticket = services.create_ticket(
                    source=Ticket.Source.EMAIL,
                    channel=TicketMessage.Channel.EMAIL,
                    subject=inbound.subject,
                    body=inbound.text,
                    user=services.account_for(inbound.sender),
                    name=inbound.sender_name,
                    email=inbound.sender,
                    spam=inbound.spam or inbound.virus,
                    message_id=inbound.message_id,
                    headers=services.headers_of(inbound),
                    inbound_event=event,
                    attachments=inbound.attachments,
                )
        except IntegrityError:  # the same Message-ID in another event, processed at the same moment
            seen = True
    event.processed_at = timezone.now()
    if seen:
        event.state = InboundEvent.State.DUPLICATE
    event.error = f"Not for a ticket: {why}" if why else ""
    event.save(update_fields=["processed_at", "state", "error"])
    if why:
        logger.info("support mail event %s dropped: %s", event.pk, why)
    return ticket.number if ticket else None
