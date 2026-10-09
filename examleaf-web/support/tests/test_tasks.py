"""The support app's periodic work: the clocks' watch (an inbox item at three quarters of each clock, a breach flagged
once at its due time, never paused by a waiting state), resolved tickets closed after 4 days, spam purged after 30
days with its numbers in the audit log, the saved replies' bin, and an erased account's tickets keeping only what the
grievance register needs."""

from datetime import timedelta

import pytest
from django.core.files.storage import default_storage
from django.utils import timezone

from accounts.models import DeletionRequest
from integrations.models import InboundEvent
from staff.models import InboxItem
from support import services, tasks
from support.models import SavedReply, Ticket, TicketAttachment

from .conftest import events, make_staff, make_ticket

pytestmark = pytest.mark.django_db


def test_the_watch_warns_at_three_quarters_and_flags_a_breach_once(commit, monkeypatch):
    from shipping import messages

    monkeypatch.setattr(messages, "quiet", lambda now=None: True)  # an SMS acknowledgement waits: its clock runs
    received = timezone.now()
    with commit():
        ticket = make_ticket(email="", phone="+919864012345", source="phone", channel="phone", received_at=received)
    assert services.watch(received + timedelta(hours=35)) == {"warned": 0, "breached": 0}
    assert services.watch(received + timedelta(hours=37)) == {"warned": 1, "breached": 0}  # 75 % of 48 hours
    item = InboxItem.objects.get(kind="ticket_due", done_at=None)
    assert item.due_at == received + timedelta(hours=48) and item.permission == "staff.handle_ticket"
    assert item.title.startswith(ticket.number) and "Rahul" not in item.title
    assert services.watch(received + timedelta(hours=40)) == {"warned": 0, "breached": 0}  # once
    late = received + timedelta(hours=49)
    assert services.watch(late) == {"warned": 0, "breached": 1}
    assert services.watch(late + timedelta(minutes=15)) == {"warned": 0, "breached": 0}  # flagged once
    ticket.refresh_from_db()
    assert ticket.ack_breached and not ticket.due_breached
    assert events("support.clock_breached", target_id=str(ticket.pk)).get().details["clock"] == "ack"
    assert InboxItem.objects.filter(kind="ticket_breach", done_at=None, target_id=str(ticket.pk)).count() == 1


def test_waiting_on_the_customer_never_pauses_the_clock_and_resolving_stops_it(commit):
    staff = make_staff("SUPPORT")
    received = timezone.now() - timedelta(days=40)
    with commit():
        ticket = make_ticket(category="qr_solutions", received_at=received)
    services.set_status(ticket, "waiting_customer", by=staff)
    assert services.watch()["breached"] >= 1  # waiting or not, its month is over
    ticket.refresh_from_db()
    assert ticket.due_breached
    with commit():
        quiet = make_ticket(category="qr_solutions")
    services.set_status(quiet, "resolved", by=staff, resolution="Answered.")
    assert services.watch(timezone.now() + timedelta(days=60)) == {"warned": 0, "breached": 0}  # stopped


def test_the_resolution_clock_warns_after_the_acknowledgement(commit):
    received = timezone.now()
    with commit():
        ticket = make_ticket(received_at=received)
    ticket.refresh_from_db()
    assert ticket.acknowledged_at
    three_quarters = received + (ticket.due_at - received) * 0.76
    assert services.watch(three_quarters) == {"warned": 1, "breached": 0}
    item = InboxItem.objects.get(kind="ticket_due", done_at=None)
    assert item.due_at == ticket.due_at and "resolve it soon" in item.title
    agent = make_staff("SUPPORT")
    services.assign(ticket, agent, by=make_staff("ADMIN"))
    assert InboxItem.objects.get(pk=item.pk).assignee == agent  # the item follows the ticket
    services.set_status(ticket, "spam", by=make_staff("SUPPORT"))
    assert InboxItem.objects.get(pk=item.pk).done_at is not None  # quarantined: nothing waits


def test_resolved_tickets_close_after_four_days_unless_reopened(commit):
    staff = make_staff("SUPPORT")
    with commit():
        old, recent = make_ticket(category="book_code"), make_ticket(category="book_code")
    for ticket in (old, recent):
        services.set_status(ticket, "resolved", by=staff, resolution="Explained.")
    Ticket.objects.filter(pk=old.pk).update(resolved_at=timezone.now() - timedelta(days=4, minutes=1))
    assert services.close_resolved() == 1 and services.close_resolved() == 0
    old.refresh_from_db()
    recent.refresh_from_db()
    assert (old.status, recent.status) == ("closed", "resolved") and old.closed_at
    assert events("support.status", target_id=str(old.pk)).last().details["auto"] is True


def test_spam_is_purged_after_30_days_with_its_files_and_raw_mail_and_its_numbers_logged(commit):
    with commit():
        junk = make_ticket(spam=True)
        kept = make_ticket(spam=True)
    event = InboundEvent.objects.create(provider="support_mail", sha256="0" * 64, body="raw")
    message = junk.messages.get()
    message.inbound_event = event
    message.save()
    services.save_attachments(message, [("photo.png", "image/png", b"\x89PNG...")])
    stored = TicketAttachment.objects.get().file.name
    Ticket.objects.filter(pk=junk.pk).update(spam_at=timezone.now() - timedelta(days=30, minutes=1))
    with commit():
        assert tasks.purge()["spam"] == 1
    assert list(Ticket.objects.values_list("pk", flat=True)) == [kept.pk]
    assert not InboundEvent.objects.filter(pk=event.pk).exists() and not default_storage.exists(stored)
    assert events("support.spam_purged").get().details["numbers"] == [junk.number]


def test_saved_replies_in_the_bin_go_after_30_days():
    SavedReply.objects.create(title="Old", body="x", deleted_at=timezone.now() - timedelta(days=31))
    SavedReply.objects.create(title="Recent", body="x", deleted_at=timezone.now() - timedelta(days=2))
    SavedReply.objects.create(title="Live", body="x")
    assert tasks.purge()["saved_replies"] == 1
    assert sorted(SavedReply.objects.values_list("title", flat=True)) == ["Live", "Recent"]


def test_an_erased_accounts_tickets_keep_only_what_the_register_needs(commit):
    from shop.factories import verified_user

    customer = verified_user("rahul@example.com")
    with commit():
        ticket = make_ticket(user=customer, category="order", subject="My parcel, house 4 Zoo Road")
    services.save_attachments(ticket.messages.get(direction="in"), [("id.png", "image/png", b"\x89PNG")])
    request = DeletionRequest.objects.create(user=customer)
    request.complete()
    ticket.refresh_from_db()
    assert (ticket.requester_name, ticket.requester_email, ticket.requester_email_hash, ticket.subject) == (
        "",
        "",
        "",
        services.ERASED,
    )
    assert set(ticket.messages.values_list("body", flat=True)) == {services.ERASED}
    assert not TicketAttachment.objects.exists()
    assert (ticket.number, ticket.category, ticket.received_at) != ("", "", None)  # the register's facts stay
    assert events("support.requester_forgotten").get().details == {"tickets": 1}


def test_the_watch_task_runs_once_at_a_time(commit, monkeypatch):
    from django.core.cache import cache

    cache.add("single-run:support.tasks.watch_clocks", "running", 60)
    assert tasks.watch_clocks() is None  # another run holds it
    cache.delete("single-run:support.tasks.watch_clocks")
    assert set(tasks.watch_clocks()) == {"warned", "breached", "closed", "held_sent"}
