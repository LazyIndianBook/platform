"""The support staff API (plan 5.14): the queue sorted by the next legal clock, with its filters and the lookups by
email or phone logged; a ticket opened as a `sensitive_read` (a child's said so) with its sidebar by the reader's
permissions; replies emailed in the thread and notes with mentions; the statuses and what closing asks for; reopening
counted; assignment; the requester's details revealed under the reveal rules; the note-only permission; SALES's order
tickets only; the actions from a ticket, each logged on it and audited (a refund above the cap waits)."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core import mail
from django.core.files.base import ContentFile
from django.utils import timezone
from rest_framework.throttling import SimpleRateThrottle

from accounts import roles
from accounts.factories import UserFactory
from learn.models import CODE_ALPHABET, BookCode, Entitlement, code_digest
from shop import services as shop
from shop.factories import ProductFactory, captured, make_order, verified_user
from shop.models import Cart, Invoice, Order
from staff.models import DataRequest, InboxItem
from support import services
from support.models import Ticket

from .conftest import SUPPORT, events, make_staff, make_ticket, signed_in

pytestmark = pytest.mark.django_db
TICKETS = SUPPORT + "tickets/"


def birthday(years):
    today = date.today()
    return today.replace(year=today.year - years)


def order_of(user, *lines, **fields):
    """An order of this account's (each from a cart of its own: an account has one cart at a time)."""
    Cart.objects.filter(user=user).delete()
    return make_order(*lines, user=user, **fields)


def paid_order(email="rahul@example.com", price="1500.00", user=None):
    product = ProductFactory(price=Decimal(price), mrp=Decimal(price) + 100)
    order = order_of(user, (product, 1), email=email) if user else make_order((product, 1), email=email)
    shop.record_capture(captured(order))
    return Order.objects.get(pk=order.pk)


def test_the_queue_sorts_by_the_next_legal_clock_and_filters(commit, settings):
    settings.SMS_ENABLED = False  # the phone ticket's acknowledgement waits at any hour (by SMS it goes from 08:00)
    support = make_staff(roles.SUPPORT)
    now = timezone.now()
    with commit():
        late = make_ticket(subject="Old", received_at=now - timedelta(days=40), category="order")
        fresh = make_ticket(subject="New", category="payment")
        unacknowledged = make_ticket(subject="By SMS", email="", phone="+919864012345", source="phone",
                                     channel="phone", category="book_code")  # fmt: skip
        spam = make_ticket(subject="Spam", spam=True)
    services.assign(fresh, support, by=support)
    rows = signed_in(support).get(TICKETS).json()["results"]
    # the acknowledgement waits (48 hours) before a resolution due in a month; spam is never in the queue
    assert [row["number"] for row in rows] == [late.number, unacknowledged.number, fresh.number]
    assert rows[0]["overdue"] and rows[0]["clock"] == "due" and rows[1]["clock"] == "ack"
    assert rows[1]["requester"] == {"name": "Rahul Das", "email": "", "phone": "••••••2345", "user": None}
    queue = signed_in(support)
    assert [row["number"] for row in queue.get(TICKETS, {"mine": "true"}).json()["results"]] == [fresh.number]
    assert fresh.number not in [row["number"] for row in queue.get(TICKETS, {"unassigned": "true"}).json()["results"]]
    assert [row["number"] for row in queue.get(TICKETS, {"overdue": "true"}).json()["results"]] == [late.number]
    assert [row["number"] for row in queue.get(TICKETS, {"category": "payment"}).json()["results"]] == [fresh.number]
    assert [row["number"] for row in queue.get(TICKETS, {"status": "spam"}).json()["results"]] == [spam.number]
    assert queue.get(TICKETS, {"q": fresh.number.lower()}).json()["results"][0]["number"] == fresh.number


def test_looking_a_person_up_by_email_or_phone_is_logged_as_a_hash(commit):
    support = make_staff(roles.SUPPORT)
    with commit():
        ticket = make_ticket(phone="+919864012345")
        make_ticket(email="anita@example.com")
    client = signed_in(support)
    assert [row["number"] for row in client.get(TICKETS, {"q": "RAHUL@example.com"}).json()["results"]] == [
        ticket.number
    ]
    assert [row["number"] for row in client.get(TICKETS, {"q": "98640 12345"}).json()["results"]] == [ticket.number]
    lookups = events("customer.lookup", actor_id=support.pk)  # the access log's, as the users' and orders' searches
    assert [(e.details["kind"], e.details["list"], e.details["found"]) for e in lookups] == [
        ("email", "tickets", 1),
        ("phone", "tickets", 1),
    ]
    assert "rahul" not in str(list(lookups.values_list("details", flat=True))).lower()  # the query's keyed hash only
    assert client.get(TICKETS, {"q": "Rahul"}).json()["results"] == []  # names are not searched


def test_opening_a_ticket_is_a_sensitive_read_and_a_childs_says_so(commit):
    child = UserFactory(email="riya@example.com", date_of_birth=birthday(15), parent_name="A", parent_contact="a@b.in")
    support = make_staff(roles.SUPPORT)
    with commit():
        ticket = make_ticket(user=child, email="riya@example.com")
    data = signed_in(support).get(f"{TICKETS}{ticket.number}/").json()
    read = events("sensitive_read", actor_id=support.pk).get()
    assert read.target_type == "accounts.user" and read.target_id == str(child.pk)
    assert read.details == {"what": "ticket", "ticket": ticket.number, "child": True}
    assert data["requester"]["email"] == "ri•••@example.com" and "riya@example.com" not in str(data)
    assert data["sidebar"]["account"]["under_18"] is True
    assert [clock["name"] for clock in data["clocks"]] == ["ack", "redress"]
    assert data["closing_fields"] == ["category", "resolution"] and "resolved" in data["transitions"]
    by_id = signed_in(support).get(f"{TICKETS}{ticket.pk}/")  # the inbox and the audit log open it by its id
    assert by_id.status_code == 200 and by_id.json()["number"] == ticket.number


def test_the_sidebar_shows_each_part_only_to_whoever_may_read_it(commit):
    customer = verified_user("rahul@example.com")
    order = paid_order(user=customer)
    Entitlement.objects.create(user=customer, source="grant", valid_until=timezone.localdate() + timedelta(days=9))
    BookCode.objects.create(digest="a" * 64, batch="PHY-2027-1", redeemed_by=customer, redeemed_at=timezone.now())
    with commit():
        ticket = make_ticket(user=customer, order=order)
        make_ticket(user=customer, subject="An older one")
    support = signed_in(make_staff(roles.SUPPORT)).get(f"{TICKETS}{ticket.number}/").json()["sidebar"]
    [row] = support["orders"]
    assert row["number"] == order.number and row["linked"] and row["refund_mode"] == "cancel"
    assert row["payments"][0]["razorpay_order_id"] == f"order_{order.pk}" and row["items"][0]["quantity"] == 1
    assert support["entitlements"][0]["active"] and support["codes"][0]["batch"] == "PHY-2027-1"
    assert support["account"]["email"] == "ra•••@example.com" and len(support["tickets"]) == 1
    sales = make_staff(roles.SALES)  # an order ticket: theirs; no customer record (accounts.view_user), no course
    ticket.category = "order"
    ticket.save()
    seen = signed_in(sales).get(f"{TICKETS}{ticket.number}/").json()["sidebar"]
    assert seen["orders"] and seen["account"] is None and seen["entitlements"] is None and seen["devices"] is None


def test_sales_see_the_order_tickets_and_content_editors_the_content_errors_only(commit):
    with commit():
        order_ticket = make_ticket(category="order")
        error = make_ticket(category="content_error")
        privacy = make_ticket(category="privacy_request")
    sales, editor = make_staff(roles.SALES), make_staff(roles.CONTENT_EDITOR)
    assert [row["number"] for row in signed_in(sales).get(TICKETS).json()["results"]] == [order_ticket.number]
    assert [row["number"] for row in signed_in(editor).get(TICKETS).json()["results"]] == [error.number]
    assert signed_in(sales).get(f"{TICKETS}{privacy.number}/").status_code == 404  # not a 403 that says it exists


def test_a_content_editor_writes_notes_on_content_errors_and_nothing_else(commit):
    editor = make_staff(roles.CONTENT_EDITOR)
    with commit():
        error = make_ticket(category="content_error")
        order_ticket = make_ticket(category="order")
    client = signed_in(editor)
    noted = client.post(f"{TICKETS}{error.number}/messages/", {"direction": "note", "body": "Fixed in PHY-E03."})
    assert noted.status_code == 201 and noted.json()["direction"] == "note"
    reply = client.post(f"{TICKETS}{error.number}/messages/", {"direction": "out", "body": "Thanks!"})
    assert reply.status_code == 403 and events("authz_fail", actor_id=editor.pk).exists()
    elsewhere = client.post(f"{TICKETS}{order_ticket.number}/messages/", {"direction": "note", "body": "Hm."})
    assert elsewhere.status_code == 404
    assert client.post(f"{TICKETS}{error.number}/status/", {"status": "open"}).status_code == 403


def test_a_reply_is_emailed_in_the_thread_and_a_note_names_people_in_their_inbox(commit):
    support, colleague, editor = make_staff(roles.SUPPORT), make_staff(roles.SUPPORT), make_staff(roles.CONTENT_EDITOR)
    with commit():
        ticket = make_ticket()
    mail.outbox.clear()
    client = signed_in(support)
    with commit():
        sent = client.post(f"{TICKETS}{ticket.number}/messages/", {"direction": "out", "body": "It left today."})
    assert sent.status_code == 201
    [reply] = mail.outbox
    assert reply.subject == f"[ExamLeaf] [{ticket.number}] Re: Where is my parcel?" and "It left today." in reply.body
    assert reply.extra_headers["References"].startswith(ticket.thread_id)
    assert reply.extra_headers["In-Reply-To"] == ticket.thread_id and "Auto-Submitted" not in reply.extra_headers
    assert events("support.replied", actor_id=support.pk).get().target_label == ticket.number
    noted = client.post(
        f"{TICKETS}{ticket.number}/messages/",
        {"direction": "note", "body": "@Colleague can you call?", "mentions": [colleague.pk]},
        format="json",
    )
    assert noted.status_code == 201
    item = InboxItem.objects.get(kind="ticket_mention")
    assert item.assignee == colleague and item.target_id == f"{ticket.pk}:{colleague.pk}" and "Rahul" not in item.title
    refused = client.post(
        f"{TICKETS}{ticket.number}/messages/",
        {"direction": "note", "body": "@Editor", "mentions": [editor.pk]},  # an order-less ticket: not theirs to see
        format="json",
    )
    assert refused.status_code == 400 and "mentions" in refused.json()
    signed_in(colleague).get(f"{TICKETS}{ticket.number}/")  # opened: the mention is done
    assert InboxItem.objects.get(pk=item.pk).done_at is not None


def test_closing_asks_for_what_the_category_requires(commit):
    support = make_staff(roles.SUPPORT)
    with commit():
        ticket = make_ticket()
    client = signed_in(support)
    url = f"{TICKETS}{ticket.number}/status/"
    unsorted = client.post(url, {"status": "resolved"})
    assert unsorted.status_code == 400 and set(unsorted.json()) == {"category", "resolution"}
    client.patch(f"{TICKETS}{ticket.number}/", {"category": "order"}, format="json")
    missing = client.post(url, {"status": "resolved", "resolution": "Sent again."})
    assert missing.status_code == 400 and set(missing.json()) == {"order"}
    order = make_order((ProductFactory(), 1), email="rahul@example.com")
    done = client.post(url, {"status": "resolved", "resolution": "Sent again.", "order": order.number})
    assert done.status_code == 200 and done.json()["status"] == "resolved"
    ticket.refresh_from_db()
    assert ticket.resolved_at and ticket.order == order and not ticket.due_breached
    assert client.post(url, {"status": "open"}).status_code == 400  # resolved: only closed, or reopen/
    reopened = client.post(f"{TICKETS}{ticket.number}/reopen/")
    assert reopened.json()["status"] == "open" and reopened.json()["reopened_count"] == 1
    assert client.post(f"{TICKETS}{ticket.number}/reopen/").status_code == 400


def test_a_resolution_past_the_due_time_is_a_breach_and_spam_is_quarantined(commit):
    support = make_staff(roles.SUPPORT)
    with commit():
        late = make_ticket(category="qr_solutions", received_at=timezone.now() - timedelta(days=35))
        junk = make_ticket()
    services.set_status(late, "closed", by=support, resolution="Answered at last.")
    late.refresh_from_db()
    assert late.due_breached and late.ack_breached and late.closed_at and late.resolved_at  # acknowledged late too
    breaches = events("support.clock_breached", target_id=str(late.pk))
    assert sorted(event.details["clock"] for event in breaches) == ["ack", "due"]  # each once
    services.set_status(junk, "spam", by=support)
    junk.refresh_from_db()
    assert junk.spam_at and junk.status == "spam"
    services.set_status(junk, "open", by=support)
    junk.refresh_from_db()
    assert junk.spam_at is None and junk.status == "open"


def test_a_ticket_goes_only_to_someone_who_handles_tickets_like_it(commit):
    support, sales, finance = make_staff(roles.SUPPORT), make_staff(roles.SALES), make_staff(roles.FINANCE)
    with commit():
        ticket = make_ticket(category="grievance")
    client = signed_in(support)
    assert client.post(f"{TICKETS}{ticket.number}/assign/", {"assignee": finance.pk}).status_code == 400
    assert client.post(f"{TICKETS}{ticket.number}/assign/", {"assignee": sales.pk}).status_code == 400  # not theirs
    claimed = client.post(f"{TICKETS}{ticket.number}/claim/")
    assert claimed.json()["assignee"] == support.pk
    assert (
        client.post(f"{TICKETS}{ticket.number}/assign/", {"assignee": None}, format="json").json()["assignee"] is None
    )


def test_revealing_the_requesters_details_follows_the_reveal_rules(commit, monkeypatch):
    monkeypatch.setitem(SimpleRateThrottle.THROTTLE_RATES, "staff_reveal", "3/hour")
    support = make_staff(roles.SUPPORT)
    with commit():
        ticket = make_ticket(phone="+919864012345")
    url = f"{TICKETS}{ticket.number}/reveal/"
    stale = signed_in(support, reauth=False).post(url, {"show": ["email"], "reason": "Calling back"}, format="json")
    assert stale.json()["code"] == "reauthentication_required"
    assert signed_in(support).post(url, {"show": ["email"]}, format="json").status_code == 400  # a reason
    client = signed_in(support)
    shown = client.post(url, {"show": ["email", "phone"], "reason": "Calling back"}, format="json").json()
    assert shown == {"email": "rahul@example.com", "phone": "+919864012345"}
    read = events("sensitive_read", actor_id=support.pk).get()
    assert read.details["fields"] == ["email", "phone"] and read.reason == "Calling back"
    assert "rahul" not in str(read.details)
    assert client.post(url, {"show": ["email"], "reason": "Again"}, format="json").status_code == 200
    assert client.post(url, {"show": ["email"], "reason": "Again"}, format="json").status_code == 429
    assert signed_in(make_staff(roles.SALES)).post(url, {"show": ["email"], "reason": "x" * 6}).status_code == 403


def test_a_refund_from_a_ticket_runs_within_the_limit_and_waits_above_it(commit, rzp):
    customer = verified_user("rahul@example.com")
    big, small = paid_order(user=customer), paid_order(price="299.00", user=customer)
    with commit():
        ticket = make_ticket(user=customer, order=big, category="order")
    support = make_staff(roles.SUPPORT)  # refunds up to ₹1,000 at once
    client = signed_in(support)
    url = f"{TICKETS}{ticket.number}/refund/"
    waits = client.post(url, {"reason": "Damaged in transit"}, format="json", HTTP_IDEMPOTENCY_KEY="k1")
    assert waits.status_code == 202 and waits.json()["status"] == "pending" and waits.json()["amount"] == "1500.00"
    assert waits.json()["checker"] == "staff.approve_refund" and ticket.number in waits.json()["reason"]
    again = client.post(url, {"reason": "Damaged in transit"}, format="json", HTTP_IDEMPOTENCY_KEY="k1")
    assert again.json()["id"] == waits.json()["id"]  # the key answers the first request again
    with commit():
        runs = client.post(url, {"reason": "Wrong book sent", "order": small.number}, format="json")
    assert runs.status_code == 201 and runs.json()["status"] == "executed"
    lines = list(ticket.messages.filter(automatic=True).values_list("body", flat=True))
    assert any("pending" in line or "waiting" in line for line in lines) and len(lines) >= 2
    stranger = paid_order(email="anita@example.com")
    refused = client.post(url, {"reason": "Not theirs", "order": stranger.number}, format="json")
    assert refused.status_code == 400 and "order" in refused.json()
    actions = events("support.action", target_id=str(ticket.pk))
    assert {event.details["action"] for event in actions} == {"refund"} and actions.count() == 2


def test_a_shipped_orders_refund_counts_the_copies_chosen_from_zero(commit, rzp):
    customer = verified_user("rahul@example.com")
    order = order_of(customer, (ProductFactory(price=Decimal("300.00"), mrp=Decimal("400.00")), 3))
    shop.record_capture(captured(order))
    order = Order.objects.get(pk=order.pk)
    Order.objects.filter(pk=order.pk).update(status=Order.Status.SHIPPED)
    with commit():
        ticket = make_ticket(user=customer, order=order, category="order")
    item = order.items.get()
    client = signed_in(make_staff(roles.SALES))
    url = f"{TICKETS}{ticket.number}/refund/"
    none = client.post(url, {"reason": "One copy torn", "lines": [{"item": item.pk, "quantity": 0}]}, format="json")
    assert none.status_code == 400 and "lines" in none.json()
    with commit():
        one = client.post(url, {"reason": "One copy torn", "lines": [{"item": item.pk, "quantity": 1}]}, format="json")
    assert one.status_code == 201 and one.json()["amount"] == "300.00"


def test_an_unpaid_order_is_cancelled_at_once_and_only_with_the_orders_own_permission(commit):
    customer = verified_user("rahul@example.com")
    order = order_of(customer, (ProductFactory(), 1), email="rahul@example.com")
    with commit():
        ticket = make_ticket(user=customer, order=order, category="order")
    url = f"{TICKETS}{ticket.number}/cancel/"
    assert signed_in(make_staff(roles.SUPPORT)).post(url, {"reason": "Asked to"}).status_code == 403
    with commit():
        done = signed_in(make_staff(roles.SALES)).post(url, {"reason": "Asked to cancel"})
    assert done.status_code == 200 and done.json() == {"order": order.number, "status": "cancelled"}


def test_the_invoice_and_the_confirmation_go_again_to_the_orders_address(commit, rzp):
    customer = verified_user("rahul@example.com")
    order = paid_order(user=customer)
    with commit():
        ticket = make_ticket(user=customer, order=order, category="order")
    client = signed_in(make_staff(roles.SUPPORT))
    Invoice.objects.filter(order=order).delete()
    assert client.post(f"{TICKETS}{ticket.number}/resend-invoice/").status_code == 400  # none yet
    with commit():
        invoice = Invoice.for_order(order)
        invoice.pdf.save("invoice.pdf", ContentFile(b"%PDF"))
    mail.outbox.clear()
    with commit():
        sent = client.post(f"{TICKETS}{ticket.number}/resend-invoice/")
    assert sent.status_code == 200 and invoice.number in sent.json()["detail"]
    [email] = mail.outbox
    assert email.to == [order.email] and order.get_link_url() in email.body
    with commit():
        assert client.post(f"{TICKETS}{ticket.number}/resend-confirmation/").status_code == 200
    assert mail.outbox[-1].subject.endswith(f"Order {order.number} confirmed")


def test_access_is_extended_by_days_with_a_reason(commit):
    customer = verified_user("rahul@example.com")
    ended = Entitlement.objects.create(user=customer, source="purchase", valid_until=date(2026, 1, 1))
    endless = Entitlement.objects.create(user=customer, source="grant", valid_until=None)
    with commit():
        ticket = make_ticket(user=customer, category="book_code")
    client = signed_in(make_staff(roles.SUPPORT))
    url = f"{TICKETS}{ticket.number}/extend-access/"
    body = {"entitlement": ended.pk, "days": 10, "reason": "The app failed in exam week"}
    done = client.post(url, body, format="json")
    assert done.status_code == 200
    ended.refresh_from_db()
    assert ended.valid_until == timezone.localdate() + timedelta(days=10) and ended.note == body["reason"]
    assert client.post(url, {**body, "entitlement": endless.pk}, format="json").status_code == 400
    assert client.post(url, {**body, "days": 400}, format="json").status_code == 400


def test_a_book_code_is_looked_up_by_its_digest_in_one_line_and_never_kept(commit):
    customer = verified_user("rahul@example.com")
    code = "".join(CODE_ALPHABET[index] for index in range(12))
    BookCode.objects.create(
        digest=code_digest(code), batch="PHY-2027-1", redeemed_by=customer, redeemed_at=timezone.now()
    )
    with commit():
        ticket = make_ticket(user=customer, category="book_code")
    client = signed_in(make_staff(roles.SUPPORT))
    url = f"{TICKETS}{ticket.number}/book-code/"
    answer = client.post(url, {"code": f"{code[:4]}-{code[4:8]}-{code[8:]}".lower()}).json()
    assert answer["found"] and answer["by_requester"] and answer["line"].startswith("Code of batch PHY-2027-1")
    assert client.post(url, {"code": "ZZZZ-ZZZZ-ZZZZ"}).json() == {
        "found": False,
        "line": "No such code: check it against the one printed in the book.",
    }
    assert client.post(url, {"code": "short"}).status_code == 400
    trail = str(list(events("support.action").values_list("details", flat=True)))
    assert code not in trail and code not in str(list(ticket.messages.values_list("body", flat=True)))


def test_a_grievance_starts_a_data_request_received_when_it_was(commit):
    customer = verified_user("rahul@example.com")
    received = timezone.now() - timedelta(days=3)
    with commit():
        ticket = make_ticket(user=customer, category="grievance", received_at=received)
        order_ticket = make_ticket(category="order")
    client = signed_in(make_staff(roles.SUPPORT))
    made = client.post(f"{TICKETS}{ticket.number}/data-request/", {"kind": "erasure"})
    assert made.status_code == 201
    request = DataRequest.objects.get()
    assert (request.kind, request.user, request.requester) == ("erasure", customer, "rahul@example.com")
    assert request.received_at == received and request.details == {"ticket": ticket.number}
    ticket.refresh_from_db()
    assert ticket.data_request == request
    assert client.post(f"{TICKETS}{ticket.number}/data-request/", {"kind": "access"}).status_code == 400  # once
    assert client.post(f"{TICKETS}{order_ticket.number}/data-request/", {"kind": "access"}).status_code == 400


def test_logging_a_call_and_an_nch_complaint(commit):
    support = make_staff(roles.SUPPORT)
    client = signed_in(support)
    nch = {"source": "nch", "subject": "Refund not received", "message": "As NCH forwarded it.", "email": "a@b.in"}
    assert client.post(TICKETS, nch, format="json").json() == {
        "nch_docket": ["A complaint from the National Consumer Helpline needs its docket number."]
    }
    with commit():
        made = client.post(TICKETS, {**nch, "nch_docket": "NCH/2027/123"}, format="json")
    assert made.status_code == 201 and made.json()["source"] == "nch" and made.json()["nch_due_at"]
    call = {"source": "phone", "subject": "Lost code", "message": "Said the code fails.", "phone": "98640 12345"}
    future = (timezone.now() + timedelta(hours=2)).isoformat()
    assert "received_at" in client.post(TICKETS, {**call, "received_at": future}, format="json").json()
    with commit():
        logged = client.post(TICKETS, call, format="json")
    assert logged.status_code == 201 and logged.json()["requester"]["phone"] == "••••••2345"
    assert Ticket.objects.get(number=logged.json()["number"]).phone == "+919864012345"


def test_a_test_orders_tickets_stay_out_of_the_live_queue_unless_asked_for(commit, settings):
    support = make_staff(roles.SUPPORT)
    with commit():
        test = make_ticket(subject="Test", order=make_order((ProductFactory(), 1)), category="order")  # test keys
        real = make_ticket(subject="Real")
    settings.RAZORPAY_KEY_ID = "rzp_live_key"  # the site now runs live: that order is a test order
    client = signed_in(support)
    assert [row["number"] for row in client.get(TICKETS).json()["results"]] == [real.number]
    [shown] = client.get(TICKETS, {"test": "true"}).json()["results"]
    assert shown["number"] == test.number and shown["is_test"]
    assert client.get(SUPPORT + "summary/").json()["received"] == 1


def test_the_agents_are_the_staff_who_read_tickets_and_whether_they_handle_them():
    support = make_staff(roles.SUPPORT)
    editor = make_staff(roles.CONTENT_EDITOR)  # notes on content errors, never given a ticket
    make_staff(roles.PACKER)  # reads no ticket
    rows = signed_in(support).get(SUPPORT + "agents/").json()
    assert {row["id"]: row["handles"] for row in rows} == {support.pk: True, editor.pk: False}
