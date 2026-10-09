"""The support mailbox (plan 5.14): the hook's token (constant time, the integrations framework's account), the raw
message kept once per SHA-256, threading by the thread id and our Message-IDs in the headers, by the number in the
subject only from the requester, the loop guard (our own mail, auto-replies, bounces, lists, floods), duplicates by
Message-ID, spam quarantined, attachments kept or dropped with why, quoted text cut, a reply reopening a resolved
ticket and starting a follow-up of a closed one, SES's receipt notification."""

import base64
import io
import json
from email.message import EmailMessage

import pytest
from django.core import mail
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from integrations.models import InboundEvent, IntegrationAccount
from support import services
from support.mail import strip_quoted
from support.models import Ticket, TicketAttachment

from .conftest import make_staff, make_ticket

pytestmark = pytest.mark.django_db
HOOK = "/api/hooks/support-mail/"


@pytest.fixture
def token():
    account = IntegrationAccount.objects.create(provider="support_mail", mode="live", enabled=True)
    return account.rotate_webhook_token()


def message(sender="rahul@example.com", subject="My parcel", text="It has not come.", **headers):
    found = EmailMessage()
    found["From"] = f"Rahul Das <{sender}>"
    found["To"] = "help@examleaf.in"
    found["Subject"] = subject
    found["Message-ID"] = headers.pop("message_id", f"<{abs(hash((sender, subject, text)))}@mail.example.com>")
    for name, value in headers.items():
        found[name.replace("_", "-")] = value
    found.set_content(text)
    return found


def post(token, found, content_type="message/rfc822"):
    raw = found.as_bytes() if isinstance(found, EmailMessage) else found
    return APIClient().post(HOOK, raw, content_type=content_type, HTTP_X_SUPPORT_MAIL_TOKEN=token)


def test_the_hook_needs_the_mailbox_accounts_token_and_keeps_each_body_once(token, commit):
    found = message()
    assert post("", found).status_code == 403 and post("wrong", found).status_code == 403
    assert InboundEvent.objects.filter(state="rejected", body="").count() == 2  # kept without its body
    with commit():
        assert post(token, found).json() == {"detail": "Received."}
        assert post(token, found).status_code == 200  # the same bytes again: kept once
    event = InboundEvent.objects.get(provider="support_mail", state__in=["accepted", "duplicate"])
    assert event.processed_at and len(event.sha256) == 64
    ticket = Ticket.objects.get()
    assert (ticket.source, ticket.subject, ticket.email, ticket.requester_name) == (
        "email",
        "My parcel",
        "rahul@example.com",
        "Rahul Das",
    )
    assert ticket.messages.get(direction="in").inbound_event == event
    assert mail.outbox[0].to == ["rahul@example.com"]  # acknowledged with its number
    IntegrationAccount.objects.update(enabled=False)
    assert post(token, message(subject="Another")).status_code == 403  # no enabled account: refused


def test_a_message_over_the_limit_is_refused(token, settings):
    settings.SUPPORT_MAIL_MAX_BYTES = 100
    assert post(token, message(text="x" * 500)).status_code == 413
    assert not Ticket.objects.exists()


def reply_to(ticket, *, sender="rahul@example.com", subject=None, **headers):
    return message(sender=sender, subject=subject or f"Re: [{ticket.number}] My parcel", text="Any news?", **headers)


def test_replies_thread_by_the_thread_id_and_our_message_ids(token, commit):
    with commit():
        ticket = make_ticket()
    sent = ticket.messages.get(direction="out")  # the acknowledgement: our Message-ID, the thread id in References
    with commit():
        post(token, reply_to(ticket, subject="Re: hello", References=ticket.thread_id, message_id="<r1@x.example>"))
        post(token, reply_to(ticket, subject="Re: hello", In_Reply_To=sent.message_id, message_id="<r2@x.example>"))
    assert Ticket.objects.count() == 1
    assert list(ticket.messages.filter(direction="in").values_list("message_id", flat=True)) == [
        None,
        "<r1@x.example>",
        "<r2@x.example>",
    ]


def test_the_number_in_the_subject_threads_only_from_the_requesters_address(token, commit):
    with commit():
        ticket = make_ticket()
        post(token, reply_to(ticket, message_id="<a@x.example>"))
        post(token, reply_to(ticket, sender="someone@else.example", message_id="<b@x.example>"))
    assert ticket.messages.filter(direction="in", message_id="<a@x.example>").exists()
    stranger = Ticket.objects.exclude(pk=ticket.pk).get()  # a number alone is easy to guess: a new ticket
    assert stranger.messages.get(direction="in").message_id == "<b@x.example>"


def test_the_loop_guard_drops_our_own_mail_auto_replies_bounces_lists_and_crowds(token, commit):
    crowd = ", ".join(f"p{index}@example.com" for index in range(51))
    dropped = [
        message(sender="noreply@examleaf.in", subject="ours"),
        message(subject="copy", X_ExamLeaf_Ticket="SR-2027-000001"),
        message(subject="away", Auto_Submitted="auto-replied"),
        message(subject="away 2", X_Autoreply="yes"),
        message(subject="news", Precedence="bulk"),
        message(subject="list", List_Id="<news.example.com>"),
        message(sender="mailer-daemon@mx.example.com", subject="Undelivered"),
        message(subject="crowd", Cc=crowd),
    ]
    with commit():
        for found in dropped:
            assert post(token, found).status_code == 200
    assert not Ticket.objects.exists() and not mail.outbox
    reasons = set(InboundEvent.objects.values_list("error", flat=True))
    assert "Not for a ticket: our own mail" in reasons and "Not for a ticket: an auto-reply" in reasons
    assert "Not for a ticket: more than 50 recipients" in reasons


def test_a_flood_from_one_sender_is_dropped_past_twenty_an_hour(token, commit):
    with commit():
        for index in range(22):
            post(token, message(subject=f"Again {index}", message_id=f"<flood{index}@x.example>"))
    assert Ticket.objects.count() == 20
    assert InboundEvent.objects.filter(error="Not for a ticket: too many emails from one sender").count() == 2


def test_the_same_message_id_twice_is_a_duplicate(token, commit):
    with commit():
        post(token, message(text="First copy", message_id="<same@x.example>"))
        post(token, message(text="Second copy, rewrapped", message_id="<same@x.example>"))
    assert Ticket.objects.count() == 1
    assert InboundEvent.objects.filter(state="duplicate").count() == 1


def test_spam_is_quarantined_without_an_acknowledgement(token, commit):
    with commit():
        post(token, message(subject="Win a prize", X_SES_Spam_Verdict="FAIL"))
    ticket = Ticket.objects.get()
    assert ticket.status == "spam" and ticket.spam_at and not mail.outbox and ticket.acknowledged_at is None


def png():
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), "white").save(buffer, "PNG")
    return buffer.getvalue()


def test_attachments_are_kept_privately_or_dropped_with_why_and_quotes_are_cut(token, commit):
    found = message(text="The box was torn.\n\nOn Mon, 5 Oct 2026, ExamLeaf <noreply@examleaf.in> wrote:\n> We have it")
    found.add_attachment(png(), maintype="image", subtype="png", filename="box.png")
    found.add_attachment(b"MZ...", maintype="application", subtype="x-msdownload", filename="tool.exe")
    with commit():
        post(token, found)
    first = Ticket.objects.get().messages.get(direction="in")
    assert first.body == "The box was torn."
    attachment = TicketAttachment.objects.get()
    assert (attachment.name, attachment.content_type, attachment.message) == ("box.png", "image/png", first)
    assert attachment.file.name.startswith("support/") and "box" not in attachment.file.name  # no typed name
    assert first.headers["dropped"] == ["tool.exe: not a kind kept (application/x-msdownload)"]


def test_strip_quoted_keeps_a_reply_written_under_the_quote():
    assert strip_quoted("> old\n> text\nMy answer below") == "> old\n> text\nMy answer below"
    assert strip_quoted("New text\n\n> quoted\n> more") == "New text"
    assert strip_quoted("Hi\n-----Original Message-----\nFrom: x") == "Hi"


def test_a_reply_reopens_a_resolved_ticket_and_starts_a_follow_up_of_a_closed_one(token, commit):
    staff = make_staff("SUPPORT")
    with commit():
        ticket = make_ticket(category="qr_solutions")
    services.set_status(ticket, "waiting_customer", by=staff)
    with commit():
        post(token, reply_to(ticket, References=ticket.thread_id, message_id="<w@x.example>"))
    ticket.refresh_from_db()
    assert ticket.status == "open"  # they answered: back to staff
    services.set_status(ticket, "resolved", by=staff, resolution="Explained the delay.")
    with commit():
        post(token, reply_to(ticket, References=ticket.thread_id, message_id="<r@x.example>"))
    ticket.refresh_from_db()
    assert (ticket.status, ticket.reopened_count, ticket.resolved_at) == ("open", 1, None)
    services.set_status(ticket, "closed", by=staff, resolution="Explained the delay.")
    with commit():
        post(token, reply_to(ticket, References=ticket.thread_id, message_id="<c@x.example>"))
    follow_up = Ticket.objects.exclude(pk=ticket.pk).get()
    assert follow_up.messages.filter(automatic=True, body__contains=ticket.number).exists()
    ticket.refresh_from_db()
    assert ticket.status == "closed"


def test_ses_receipt_notifications_are_read_with_their_verdicts(token, commit):
    found = message(subject="Through SES")
    notification = {
        "notificationType": "Received",
        "receipt": {"spamVerdict": {"status": "PASS"}, "virusVerdict": {"status": "PASS"}},
        "content": base64.b64encode(found.as_bytes()).decode(),
    }
    envelope = {"Type": "Notification", "Message": json.dumps(notification)}
    with commit():
        assert post(token, json.dumps(envelope).encode(), content_type="application/json").status_code == 200
    assert Ticket.objects.get().subject == "Through SES"
    notification["receipt"]["virusVerdict"]["status"] = "FAIL"
    notification["content"] = base64.b64encode(message(subject="Infected").as_bytes()).decode()
    with commit():
        post(token, json.dumps(notification).encode(), content_type="application/json")
    assert Ticket.objects.get(subject="Infected").status == "spam"


def test_eight_bit_mail_that_is_not_utf8_is_kept_whole(token, commit):
    raw = message(subject="Latin").as_bytes().replace(b"It has not come.", "Caf\xe9".encode("latin-1"))
    with commit():
        assert post(token, raw).status_code == 200
    event = InboundEvent.objects.get(provider="support_mail")
    assert event.body.startswith("base64:") and base64.b64decode(event.body[7:]) == raw
    assert Ticket.objects.get().subject == "Latin"
    assert timezone.now()  # (processed in the same test transaction)
