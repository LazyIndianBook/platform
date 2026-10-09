"""Tickets coming in (plan 5.14): the number series (gapless, per year, two at once), the contact form making a ticket
and its acknowledgement with the number (the copy of the complaint as recorded from the setting's date and not before;
by SMS, held through the night, when only a mobile number is known), the order a message names linked only when its
sender placed it, "My requests" (the customer's own tickets only, never staff's notes; a new request from the account),
and only a person's reply counting as the first response."""

import threading
from datetime import date, timedelta

import pytest
from allauth.account.models import EmailAddress
from django.core import mail
from django.db import connection, transaction
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.factories import UserFactory
from ops.models import SmsLog
from shop.factories import ProductFactory, make_order, verified_user
from support import services
from support.models import Ticket, TicketMessage, TicketSeries

from .conftest import make_staff, make_ticket

pytestmark = pytest.mark.django_db
CONTACT = "/api/v1/contact/"
MINE = "/api/v1/me/tickets/"
FORM = {"name": "Rahul  Das", "email": "Rahul@Example.com", "message": "Order EL-2026-000123 has not come."}


def test_the_series_has_no_gap_restarts_each_year_and_a_rolled_back_ticket_gives_its_number_back():
    year = timezone.localdate().year
    first, second = make_ticket(), make_ticket()
    assert (first.number, second.number) == (f"SR-{year}-000001", f"SR-{year}-000002")
    with pytest.raises(RuntimeError), transaction.atomic():
        make_ticket()
        raise RuntimeError("rolled back")
    assert make_ticket().number == f"SR-{year}-000003"
    with transaction.atomic():
        assert services.next_number(date(year + 1, 1, 1)) == f"SR-{year + 1}-000001"  # India's new year: a new series
    assert TicketSeries.objects.get(year=year).last == 3


@pytest.mark.django_db(transaction=True)
@pytest.mark.skipif(connection.vendor != "postgresql", reason="SQLite runs one writer at a time: nothing to race")
def test_two_tickets_made_at_once_take_one_number_each():
    numbers, barrier, errors = [], threading.Barrier(2), []

    def make():
        try:
            barrier.wait(5)
            numbers.append(make_ticket().number)
        except Exception as error:  # pragma: no cover - shown by the assertion below
            errors.append(error)
        finally:
            connection.close()

    threads = [threading.Thread(target=make) for _ in range(2)]
    [thread.start() for thread in threads]
    [thread.join(30) for thread in threads]
    year = timezone.localdate().year
    assert not errors and sorted(numbers) == [f"SR-{year}-000001", f"SR-{year}-000002"]


def test_the_contact_form_makes_a_ticket_acknowledged_with_its_number_by_email(commit, settings):
    settings.SUPPORT_COMPLAINT_COPY_FROM = timezone.localdate() + timedelta(days=1)  # not yet: no copy
    with commit():
        answer = APIClient().post(CONTACT, FORM, format="json")
    assert answer.status_code == 200 and answer.json() == {
        "detail": "Thank you: your message is on its way to us. We reply by email."
    }
    ticket = Ticket.objects.get()
    assert (ticket.source, ticket.status, ticket.category, ticket.requester_name) == ("form", "new", "", "Rahul Das")
    assert ticket.email == "rahul@example.com" and ticket.requester_email != "rahul@example.com"  # encrypted at rest
    assert ticket.user is None and ticket.order is None  # no account confirmed this address, no such order
    [ack] = mail.outbox
    assert ack.to == ["rahul@example.com"] and ack.subject == f"[ExamLeaf] [{ticket.number}] We have your request"
    assert ticket.number in ack.body and "as we recorded it" not in ack.body
    headers = ack.extra_headers
    assert headers["Reply-To"] == "help@examleaf.in" and headers["X-ExamLeaf-Ticket"] == ticket.number
    assert headers["Auto-Submitted"] == "auto-replied" and headers["References"].startswith(ticket.thread_id)
    ticket.refresh_from_db()
    assert ticket.acknowledged_at and ticket.complaint_copy_sent_at is None and ticket.first_response_at is None
    sent = ticket.messages.get(direction="out")
    assert sent.automatic and sent.channel == "email" and sent.message_id == headers["Message-ID"]
    assert ticket.next_due_at == ticket.due_at  # acknowledged: the queue now waits on its resolution


def test_a_form_messages_subject_is_its_first_line_but_the_order_box():
    assert services.form_subject("Order EL-2026-000123\n\nThe parcel has not come.\nPlease check.") == (
        "The parcel has not come."
    )
    assert services.form_subject("Where is my parcel?\nOrder EL-2026-000123") == "Where is my parcel?"
    assert services.form_subject("Order EL-2026-000123") == "Order EL-2026-000123"  # nothing else: the line itself
    assert services.form_subject("  \n\n") == ""  # create_ticket names it "(no subject)"


def test_from_the_settings_date_the_acknowledgement_carries_the_complaint_as_recorded(commit, settings):
    settings.SUPPORT_COMPLAINT_COPY_FROM = timezone.localdate()
    with commit():
        APIClient().post(CONTACT, FORM, format="json")
    [ack] = mail.outbox
    assert "Your complaint as we recorded it:\n\nOrder EL-2026-000123 has not come." in ack.body
    assert Ticket.objects.get().complaint_copy_sent_at is not None


def test_the_support_address_gets_a_copy_only_with_the_setting(commit, settings):
    with commit():
        APIClient().post(CONTACT, FORM, format="json")
    assert [message.to for message in mail.outbox] == [["rahul@example.com"]]
    settings.SUPPORT_COPY_TO_EMAIL = True
    with commit():
        APIClient().post(CONTACT, {**FORM, "message": "A second question."}, format="json")
    copy = next(message for message in mail.outbox if message.to == ["help@examleaf.in"])
    ticket = Ticket.objects.order_by("-pk").first()
    assert copy.extra_headers["Reply-To"] == "Rahul@Example.com" and ticket.number in copy.subject  # as typed
    assert copy.extra_headers["X-ExamLeaf-Ticket"] == ticket.number  # forwarded back in, the loop guard drops it


def test_the_honeypot_and_the_unset_support_address_make_no_ticket(settings, commit):
    with commit():
        assert APIClient().post(CONTACT, {**FORM, "website": "spam"}, format="json").status_code == 200
    settings.SUPPORT_EMAIL, settings.SHOP_SELLER = "", {**settings.SHOP_SELLER, "email": "[email]"}
    assert APIClient().post(CONTACT, FORM, format="json").status_code == 503
    assert not Ticket.objects.exists() and not mail.outbox


def test_the_form_links_the_order_it_names_only_when_its_sender_placed_it_and_the_account_that_confirmed_the_address(
    commit,
):
    customer = verified_user("rahul@example.com")
    theirs = make_order((ProductFactory(), 1), email="rahul@example.com", user=customer)
    someone_elses = make_order((ProductFactory(), 1), email="anita@example.com")
    with commit():
        APIClient().post(CONTACT, {**FORM, "message": f"Order {theirs.number} is late."}, format="json")
        APIClient().post(CONTACT, {**FORM, "message": f"Order {someone_elses.number} is late."}, format="json")
    first, second = Ticket.objects.order_by("pk")
    assert (first.order, first.user) == (theirs, customer)
    assert (second.order, second.user) == (None, customer)


def test_with_only_a_mobile_number_the_acknowledgement_goes_by_sms_and_waits_for_the_morning(commit, monkeypatch):
    from shipping import messages

    monkeypatch.setattr(messages, "quiet", lambda now=None: True)  # 22:00
    staff = make_staff("SUPPORT")
    with commit():
        ticket = make_ticket(
            source="phone", channel="phone", email="", name="", phone="+919864012345", by=staff, body="A lost code"
        )
    ticket.refresh_from_db()
    assert ticket.ack_held and ticket.acknowledged_at is None and not SmsLog.objects.exists()
    monkeypatch.setattr(messages, "quiet", lambda now=None: False)  # 08:00
    assert services.send_held() == 1 and services.send_held() == 0  # once
    ticket.refresh_from_db()
    assert ticket.acknowledged_at and not ticket.ack_held and ticket.complaint_copy_sent_at is None  # no copy by SMS
    log = SmsLog.objects.get()
    assert log.kind == "ticket_ack" and log.phone_last4 == "2345"
    assert ticket.messages.get(direction="out").channel == "sms"


def test_a_ticket_logged_by_staff_is_audited_and_acknowledged_by_email(commit):
    from .conftest import events

    staff = make_staff("SUPPORT")
    with commit():
        ticket = make_ticket(source="nch", channel="nch", nch_docket="NCH-2027-0042", by=staff)
    event = events("support.ticket_logged").get()
    assert event.actor_id == staff.pk and event.target_label == ticket.number and event.details["nch"] is True
    assert "rahul" not in str(event.details).lower()  # no personal data in the log
    assert mail.outbox[0].to == ["rahul@example.com"]
    first = ticket.messages.get(direction="in")
    assert first.author == staff and first.channel == "nch"  # the complaint as staff recorded it


def test_only_a_persons_reply_is_the_first_response(commit):
    staff = make_staff("SUPPORT")
    with commit():
        ticket = make_ticket()
    ticket.refresh_from_db()
    assert ticket.acknowledged_at and ticket.first_response_at is None  # the acknowledgement is not a response
    services.add_message(ticket, by=staff, direction="note", body="Checking with the courier.")
    ticket.refresh_from_db()
    assert ticket.first_response_at is None  # nor a note
    with commit():
        services.add_message(ticket, by=staff, direction="out", body="It left today.")
    ticket.refresh_from_db()
    assert ticket.first_response_at and ticket.status == "open"


def signed_in(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def test_my_requests_shows_the_customers_own_only_and_never_staffs_notes(commit):
    customer = verified_user("rahul@example.com")
    EmailAddress.objects.create(user=customer, email="old@example.com", verified=False)
    staff = make_staff("SUPPORT")
    with commit():
        own = make_ticket(user=customer, subject="My parcel")
        guest = make_ticket(email="RAHUL@example.com", subject="Before I had an account")  # the confirmed address
        make_ticket(email="old@example.com", subject="From an unconfirmed address")
        make_ticket(email="anita@example.com", subject="Someone else's")
        make_ticket(user=customer, subject="Junk", spam=True)
    services.add_message(own, by=staff, direction="note", body="Internal: a difficult customer.")
    answer = signed_in(customer).get(MINE)
    assert answer.status_code == 200
    rows = answer.json()["results"]
    assert [row["number"] for row in rows] == [guest.number, own.number]  # newest first
    assert rows[1]["status"] == "new" and rows[1]["status_label"] == "received"
    assert set(rows[0]) == {
        *["number", "subject", "category", "category_label", "status", "status_label", "order", "received_at"],
        *["acknowledged_at", "answer_by", "resolved_at", "closed_at", "modified"],
    }
    assert "Internal" not in answer.content.decode() and "assignee" not in answer.content.decode()
    assert APIClient().get(MINE).status_code in (401, 403)


def test_a_customer_makes_a_request_on_my_requests(commit):
    customer = verified_user("rahul@example.com")
    order = make_order((ProductFactory(), 1), email="rahul@example.com", user=customer)
    other = make_order((ProductFactory(), 1), email="anita@example.com")
    body = {"category": "order", "subject": "Late parcel", "message": "Where is it?", "order": order.number}
    with commit():
        made = signed_in(customer).post(MINE, body, format="json")
    assert made.status_code == 201, made.content
    ticket = Ticket.objects.get(number=made.json()["number"])
    assert (ticket.user, ticket.order, ticket.category, ticket.source) == (customer, order, "order", "form")
    assert mail.outbox[0].to == ["rahul@example.com"] and made.json()["status_label"] == "received"
    refused = signed_in(customer).post(MINE, {**body, "order": other.number}, format="json")
    assert refused.status_code == 400 and "order" in refused.json()
    unconfirmed = UserFactory(email="new@example.com")
    assert signed_in(unconfirmed).post(MINE, body, format="json").status_code == 403  # a confirmed address first
    assert TicketMessage.objects.filter(ticket=ticket, direction="in").get().body == "Where is it?"
