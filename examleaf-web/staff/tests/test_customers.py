"""The Customers module (staff/customers_api.py, staff/customers.py; plan 5.4), one test per rule of its package: the
badges on a list row and a record, the tabs (students, parents, guest buyers), a search for a person written to the
access log by its hash, the merged timeline (a `sensitive_read`, a child's marked, a child's course in counts and never
a trail, the newest 200 with ties kept at a page's edge, each part only for whoever may see it, no query per row), the
commerce summary (a child's counts only, test orders out), the children waiting for a parent and a parent's consent
recorded by hand (the record, its evidence, the parent told), the bulk account actions with their dry run, caps and the
approval a child's account always needs, and the rule that no serializer carries a predictive field."""

import json
from datetime import timedelta
from decimal import Decimal

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from axes.models import AccessAttempt
from django.core import mail
from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.utils.dateparse import parse_datetime

from accounts import roles
from accounts.models import ConsentRecord, DeletionRequest, ParentLinkSend, TeacherProfile, User
from accounts.tests import birthday
from api.tests import student
from shop import services as shop
from shop.factories import ProductFactory, captured, make_order
from shop.models import Cart, Order, Refund
from staff import audit
from staff.models import ChangeRequest, Job, Note, StaffScope
from staff.tests.conftest import STAFF, events, make_staff, signed_in

pytestmark = [pytest.mark.django_db, pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning")]
USERS = STAFF + "users/"
JOBS = STAFF + "jobs/"


def child(age=15, contact="anita@example.com", **fields):
    """A student under 18 (their parent's contact given), with a confirmed email address."""
    fields = {"parent_name": "Anita Das", "parent_contact": contact, **fields}
    return student(date_of_birth=birthday(age), **fields)


def adult(**fields):
    return student(date_of_birth=birthday(40), class_level=None, **fields)


def rows(client, **query):
    response = client.get(USERS, query)
    assert response.status_code == 200, response.content[:300]
    return response.json()["results"]


def paid(*lines, **fields):
    if fields.get("user"):
        Cart.objects.filter(user=fields["user"]).delete()  # make_order starts a cart, one to an account
    order = make_order(*lines, **fields)
    shop.record_capture(captured(order))
    return Order.objects.get(pk=order.pk)


def go_live(settings):
    """The site on live Razorpay keys: orders made before were made in test mode."""
    settings.RAZORPAY_KEY_ID = "rzp_live_key"


# ---- Badges ----


def test_a_row_carries_the_badges_the_plan_asks_for_and_the_record_the_same(settings):
    settings.PARENTAL_CONSENT_MODE = "verified"
    little = child(11, login_phone="+919864012345", login_phone_verified=True)
    TOTP.activate(little, generate_totp_secret())
    declared = child(15)
    for pupil in (little, declared):  # the sign-up form's tick, as sign-up records it
        ConsentRecord.objects.create(user=pupil, by_parent=True, notice_version="1")
    confirmed = child(16, email="verified-child@example.com")
    ConsentRecord.objects.create(
        user=confirmed, by_parent=True, method="sms_link", notice_version="1", verified_at=timezone.now()
    )
    teacher = adult(email="teacher@example.com")
    TeacherProfile.objects.create(user=teacher, school_name="A school", district="Kamrup", subject="Physics")
    unknown = student(date_of_birth=None, verified=False)
    locked = adult(email="locked@example.com")
    AccessAttempt.objects.create(
        username="locked@example.com", ip_address="10.0.0.1", failures_since_start=10, user_agent="x",
        get_data="", post_data="", http_accept="", path_info="/",
    )  # fmt: skip
    client = signed_in(make_staff(roles.SUPPORT))
    by_id = {row["id"]: row for row in rows(client)}
    row = by_id[little.pk]
    assert (row["age_band"], row["consent"], row["consent_method"], row["mfa_on"]) == (
        "under_13",
        "pending",
        "declared",
        True,
    )
    assert (row["email_verified"], row["login_phone_verified"], row["teacher"], row["locked"]) == (
        True,
        True,
        "none",
        False,
    )
    assert by_id[declared.pk]["age_band"] == "13_17"
    assert (by_id[confirmed.pk]["consent"], by_id[confirmed.pk]["consent_method"]) == ("verified", "sms_link")
    assert by_id[teacher.pk]["teacher"] == "requested" and by_id[teacher.pk]["age_band"] == "adult"
    assert by_id[teacher.pk]["consent_method"] == "" and by_id[teacher.pk]["mfa_on"] is False
    assert (by_id[unknown.pk]["age_band"], by_id[unknown.pk]["email_verified"]) == ("unknown", False)
    assert by_id[locked.pk]["locked"] is True and by_id[locked.pk]["status"] == "active"
    record = client.get(f"{USERS}{little.pk}/").json()  # the record has the same badges, and its own parts
    assert (record["age_band"], record["consent_method"], record["mfa_on"], record["mfa"]) == (
        "under_13",
        "declared",
        True,
        ["totp"],
    )
    assert client.get(f"{USERS}{locked.pk}/").json()["locked"] is True


def test_a_page_of_badges_costs_the_same_few_queries_however_many_rows():
    def make(count):
        for _ in range(count):
            user = child()
            TOTP.activate(user, generate_totp_secret())
            TeacherProfile.objects.create(user=user, school_name="S", district="D", subject="P")
            ConsentRecord.objects.create(
                user=user, by_parent=True, notice_version="1", method="email_link", verified_at=timezone.now()
            )

    client = signed_in(make_staff(roles.SUPPORT))
    client.get(USERS)  # the session's own queries once

    def queries():
        with CaptureQueriesContext(connection) as captured_queries:
            assert client.get(USERS).status_code == 200
        return len(captured_queries)

    make(2)
    few = queries()
    make(10)
    assert queries() == few


# ---- The tabs ----


def test_the_students_tab_is_the_accounts_with_a_class_or_under_18():
    pupil, young, grown = student(), child(14, class_level=None), adult(email="grown@example.com")
    client = signed_in(make_staff(roles.SUPPORT))
    assert {row["id"] for row in rows(client, kind="students")} == {pupil.pk, young.pk}
    assert {row["id"] for row in rows(client)} == {pupil.pk, young.pk, grown.pk}  # everyone, without a tab
    assert client.get(USERS, {"kind": "teachers"}).status_code == 400  # an unknown tab is refused, not ignored


def test_the_parents_tab_is_the_adult_accounts_a_student_named_as_their_parents_contact():
    mother = adult(email="anita@example.com")  # her verified address is the contact on her child's record
    father = adult(email="father@example.com", login_phone="+919864012345", login_phone_verified=True)
    unverified = adult(email="unverified@example.com", verified=False)
    stranger = adult(email="stranger@example.com")
    child(15, contact="anita@example.com")
    child(14, contact="+919864012345")
    child(13, contact="unverified@example.com")
    erased = child(15, contact="stranger@example.com")
    User.objects.filter(pk=erased.pk).update(
        email=f"deleted-{erased.pk}@deleted.invalid"
    )  # an erased child names no one
    teenager = child(17, email="teen@example.com")  # a minor is never taken for a parent, whoever names them
    child(14, contact="teen@example.com")
    client = signed_in(make_staff(roles.SUPPORT))
    found = {row["id"] for row in rows(client, kind="parents")}
    assert found == {mother.pk, father.pk}  # not the unverified address, not a stranger, not a minor
    assert unverified.pk not in found and stranger.pk not in found and teenager.pk not in found


def test_the_guests_tab_lists_buyers_without_an_account_by_their_orders_masked_and_counted(settings):
    first = paid((ProductFactory(), 1), email="Guest.One@example.com", name="Guest One", phone="+919864011111")
    second = paid((ProductFactory(), 1), email="guest.one@example.com", name="Guest One", phone="+919864011111")
    other = paid((ProductFactory(), 1), email="other@example.com", name="Other Buyer", phone="+919864022222")
    member = paid((ProductFactory(), 1), email="member@example.com", user=student(email="member@example.com"))
    Order.objects.filter(pk=other.pk).update(email="deleted")  # forgotten after its books' period: no one to list
    client = signed_in(make_staff(roles.SUPPORT))
    guests = rows(client, kind="guests")
    assert [guest["id"] for guest in guests] == [second.pk]  # one row per address, in any case, by its newest order
    guest = guests[0]
    assert (guest["orders"], guest["last_order"], guest["name"]) == (2, second.number, "Guest One")
    assert (guest["email"], guest["phone"]) == ("gu•••@example.com", "••••••1111")
    assert first.number not in json.dumps(guests) and member.number not in json.dumps(guests)
    assert [g["id"] for g in rows(client, kind="guests", q="guest.one@EXAMPLE.com")] == [second.pk]
    assert [g["id"] for g in rows(client, kind="guests", q="1111")] == [second.pk]
    assert rows(client, kind="guests", q="Nobody Here") == []
    go_live(settings)  # a test-mode order is no sale on a live site
    assert rows(client, kind="guests") == []
    assert signed_in(make_staff(roles.MARKETING)).get(USERS, {"kind": "guests"}).status_code == 403


# ---- The access log ----


def test_a_search_for_a_person_is_one_lookup_event_with_the_queries_hash_and_what_it_found():
    rahul = student(
        email="rahul.das@example.com", full_name="Rahul Das", login_phone="+919864012345", login_phone_verified=True
    )
    support = make_staff(roles.SUPPORT)
    client = signed_in(support)
    for query in ["Rahul.Das@example.com", "98640 12345", "2345", "rahul"]:
        assert [row["id"] for row in rows(client, q=query)] == [rahul.pk], query
    looked = list(events("customer.lookup", actor_id=support.pk))
    assert [event.details["kind"] for event in looked] == ["email", "phone", "phone", "name"]
    assert all(event.details["found"] == 1 and event.details["list"] == "users" for event in looked)
    assert all(event.details["query"].startswith("hash:") for event in looked)
    text = json.dumps([event.details for event in looked]).lower()
    assert "rahul" not in text and "2345" not in text and "example.com" not in text  # the query itself, never
    assert looked[0].details["query"] == audit.mask("rahul.das@example.com", "contact")  # comparable, not readable
    rows(client, q="ra")  # too little to look anyone up: nothing found, and no lookup
    rows(client)  # a list, not a lookup
    rows(client, kind="students")
    assert events("customer.lookup").count() == 4
    assert rows(client, q="nobody@example.com") == []
    assert events("customer.lookup").last().details["found"] == 0


def test_a_guest_search_is_a_lookup_of_the_guests_list():
    paid((ProductFactory(), 1), email="guest@example.com")
    client = signed_in(make_staff(roles.SUPPORT))
    assert len(rows(client, kind="guests", q="guest@example.com")) == 1
    looked = events("customer.lookup").get()
    assert (looked.details["list"], looked.details["kind"], looked.details["found"]) == ("guests", "email", 1)


# ---- The timeline ----


def test_opening_a_timeline_is_a_sensitive_read_and_a_childs_says_so():
    boy, man = child(), adult(email="man@example.com")
    support = make_staff(roles.SUPPORT)
    client = signed_in(support)
    assert client.get(f"{USERS}{boy.pk}/timeline/").json()["child"] is True
    assert client.get(f"{USERS}{man.pk}/timeline/").json()["child"] is False
    first, second = events("sensitive_read", actor_id=support.pk)
    assert first.details == {"what": "timeline", "child": True} and first.target_id == str(boy.pk)
    assert second.details == {"what": "timeline", "child": False} and second.target_type == "accounts.user"


def test_the_timeline_merges_orders_payments_refunds_codes_access_tickets_messages_consents_and_notes():
    from learn.models import BookCode, Entitlement
    from ops.models import SmsLog
    from support import services as support

    customer = student(email="rahul@example.com", full_name="Rahul Das", date_of_birth=birthday(30))
    order = paid((ProductFactory(), 1), user=customer, email="rahul@example.com")
    Refund.objects.create(order=order, payment=order.payments.get(), amount=Decimal("100"), reason="Damaged")
    BookCode.objects.create(digest="a" * 64, batch="PHY-2027-1", redeemed_by=customer, redeemed_at=timezone.now())
    Entitlement.objects.create(user=customer, source="grant", note="Lost code")
    ticket = support.create_ticket(
        source="form", channel="web", subject="Where is it", body="?", user=customer, name="Rahul",
        email="rahul@example.com", category="order", order=order,
    )  # fmt: skip
    SmsLog.objects.create(
        kind="order_placed", phone_hash="h", phone_last4="2345", user=customer, status="sent", delivery="delivered"
    )
    ConsentRecord.objects.create(user=customer, by_parent=False, notice_version="2026-10")
    other = student()
    author = make_staff(roles.SUPPORT, full_name="Rina Saikia")
    Note.objects.create(
        target_type="accounts.user", target_id=str(customer.pk), author=author, body="Called back about the parcel."
    )
    Note.objects.create(target_type="accounts.user", target_id=str(other.pk), author=author, body="Not his")
    owner = make_staff(roles.OWNER)
    client = signed_in(owner)
    client.post(f"{USERS}{customer.pk}/unlock/")  # a staff action on the account
    body = client.get(f"{USERS}{customer.pk}/timeline/").json()
    assert body["withheld"] == [] and body["next_before"] is None
    by_kind = {}
    for row in body["rows"]:
        by_kind.setdefault(row["kind"], []).append(row)
    assert {"order", "payment", "refund", "code", "access", "ticket", "sms", "consent", "note", "staff"} <= set(by_kind)
    assert by_kind["order"][0]["label"].startswith(f"Order {order.number}: ")
    assert by_kind["order"][0]["href"] == f"/orders/{order.number}/"
    assert by_kind["payment"][0]["label"].startswith(
        f"Payment of ₹{order.total.amount} for order {order.number} (online"
    )
    assert by_kind["payment"][0]["label"].endswith("captured")
    assert by_kind["refund"][0]["label"].startswith(f"Refund of ₹100.00 for order {order.number}")
    assert by_kind["code"][0]["label"] == "Book code redeemed: batch PHY-2027-1 (every subject)"
    assert by_kind["code"][0]["href"] == f"/course/learners/{customer.pk}/"
    assert by_kind["access"][0]["label"] == "Course access opened (staff grant): every subject"
    assert by_kind["ticket"][0]["label"] == f"Ticket {ticket.number}: order, new"
    assert by_kind["ticket"][0]["href"] == f"/support/tickets/{ticket.number}/"
    assert by_kind["sms"][0]["label"] == "SMS (order placed): sent, delivered"
    assert by_kind["consent"][0]["label"] == "Consent given by the student (ticked on the form); privacy notice 2026-10"
    assert by_kind["note"][0]["label"] == "Note by Rina Saikia: Called back about the parcel."
    assert len(by_kind["note"]) == 1  # his, not the other account's
    assert any(row["label"].startswith("Sign-in unlocked by ") for row in by_kind["staff"])
    assert [row["at"] for row in body["rows"]] == sorted((row["at"] for row in body["rows"]), reverse=True)
    text = json.dumps(body)
    assert "rahul@example.com" not in text and "2345" not in text  # numbers and codes: no contact in a label
    assert events("audit.read", actor_id=owner.pk).get().target_id == str(customer.pk)  # the log's part was read


def test_each_part_is_shown_only_to_whoever_may_see_its_records():
    customer = student(date_of_birth=birthday(30))
    paid((ProductFactory(), 1), user=customer, email=customer.email)
    Note.objects.create(target_type="accounts.user", target_id=str(customer.pk), author=customer, body="A note")
    finance = signed_in(make_staff(roles.FINANCE))  # orders and payments, but no tickets, course, SMS, consents
    body = finance.get(f"{USERS}{customer.pk}/timeline/").json()
    assert {row["kind"] for row in body["rows"]} >= {"order", "payment", "note"}
    assert set(body["withheld"]) == {"code", "access", "course", "ticket", "sms", "consent", "staff"}
    narrowed = finance.get(f"{USERS}{customer.pk}/timeline/", {"kind": "ticket,order"}).json()
    assert {row["kind"] for row in narrowed["rows"]} == {"order"} and narrowed["withheld"] == ["ticket"]
    support = signed_in(make_staff(roles.SUPPORT))
    assert "staff" in support.get(f"{USERS}{customer.pk}/timeline/").json()["withheld"]  # the log: AUDITOR's, OWNER's
    assert not events("audit.read").exists()  # so nothing of it was read


def test_a_persons_scope_narrows_every_part_of_their_timeline():
    customer = student(date_of_birth=birthday(30))
    kept = paid((ProductFactory(), 1), user=customer, email=customer.email)
    packed = paid((ProductFactory(), 1), user=customer, email=customer.email)
    shop.pack_order(packed)
    support = make_staff(roles.SUPPORT)
    StaffScope.objects.create(user=support, kind="order_status", value="paid")
    body = signed_in(support).get(f"{USERS}{customer.pk}/timeline/").json()
    seen = {row["href"] for row in body["rows"] if row["kind"] in ("order", "payment", "email")}
    assert seen == {f"/orders/{kept.number}/"}  # the packed order and what hangs on it are out of reach


def test_a_childs_course_is_a_summary_never_a_trail_and_an_adults_adds_clips_by_week():
    from content.tests import make_paper
    from learn.models import CardReview, Chapter, Clip, FlashCard, Progress, QuizAttempt, QuizItem, Revision

    subject = make_paper().book.subject
    chapters = [Chapter.objects.create(subject=subject, number=n, title=f"Chapter {n}") for n in (1, 2, 3)]
    clips = []
    for chapter in chapters:
        revision = Revision.objects.create(chapter=chapter, title="R", status="published")
        clips += [Clip.objects.create(revision=revision, title=f"Secret clip {chapter.number}-{n}") for n in (1, 2)]
    item = QuizItem.objects.create(chapter=chapters[2], kind="mcq", text="Q", options=["a", "b"], answer="1")
    card = FlashCard.objects.create(chapter=chapters[2], front="front", back="back")

    def use(user):
        for clip in clips[:4]:
            Progress.objects.create(user=user, clip=clip, seconds_watched=60, completed=True)
        QuizAttempt.objects.create(user=user, item=item, correct=True)
        CardReview.objects.create(user=user, card=card, known=True)

    kid, grown = child(), adult(email="grown@example.com")
    use(kid)
    use(grown)
    client = signed_in(make_staff(roles.SUPPORT))
    kid_rows = client.get(f"{USERS}{kid.pk}/timeline/").json()["rows"]
    kid_course = [row for row in kid_rows if row["kind"] == "course"]
    assert len(kid_course) == 1  # one row: no clip, no quiz answer, no day
    assert kid_course[0]["label"].startswith("Course use so far: 3 chapters opened; last active in the week of ")
    assert "Secret clip" not in json.dumps(kid_rows) and kid_course[0]["href"] == f"/course/learners/{kid.pk}/"
    grown_rows = client.get(f"{USERS}{grown.pk}/timeline/").json()["rows"]
    grown_course = [row for row in grown_rows if row["kind"] == "course"]
    assert len(grown_course) == 2  # the summary and this week's completions
    assert any(row["label"].endswith(": 4 clips completed") for row in grown_course)
    assert "Secret clip" not in json.dumps(grown_rows)
    quiet = client.get(f"{USERS}{student().pk}/timeline/").json()["rows"]
    assert not [row for row in quiet if row["kind"] == "course"]  # no use, nothing said


def test_the_timeline_gives_the_newest_200_and_the_older_ones_on_ask_with_ties_kept_at_the_edge():
    customer = adult(email="busy@example.com")
    author = make_staff(roles.SUPPORT)
    same = timezone.now() - timedelta(days=1)
    for n in range(205):  # 205 notes; the 6 oldest at one instant, which straddles the first page's end
        when = same if n < 6 else timezone.now() - timedelta(minutes=205 - n)
        Note.objects.create(
            target_type="accounts.user", target_id=str(customer.pk), author=author, body=f"Note {n}", created=when
        )
    client = signed_in(make_staff(roles.SUPPORT))
    first = client.get(f"{USERS}{customer.pk}/timeline/", {"kind": "note"}).json()
    assert len(first["rows"]) == 200 and first["next_before"]
    older = client.get(f"{USERS}{customer.pk}/timeline/", {"kind": "note", "before": first["next_before"]}).json()
    assert len(older["rows"]) == 5 and older["next_before"] is None
    labels = [row["label"] for row in first["rows"] + older["rows"]]
    assert len(labels) == 205 == len(set(labels))  # none twice, none lost: the six at one instant were split cleanly
    assert client.get(f"{USERS}{customer.pk}/timeline/", {"before": "yesterday"}).status_code == 400
    assert client.get(f"{USERS}{customer.pk}/timeline/", {"kind": "gossip"}).status_code == 400


def test_the_timeline_costs_the_same_few_queries_however_long():
    customer = student(date_of_birth=birthday(30))
    client = signed_in(make_staff(roles.OWNER))
    path = f"{USERS}{customer.pk}/timeline/"
    client.get(path)

    def queries():
        with CaptureQueriesContext(connection) as captured_queries:
            assert client.get(path).status_code == 200
        return len(captured_queries)

    paid((ProductFactory(), 1), user=customer, email=customer.email)
    few = queries()
    for _ in range(5):
        order = paid((ProductFactory(), 1), user=customer, email=customer.email)
        Note.objects.create(target_type="accounts.user", target_id=str(customer.pk), author=customer, body="n")
        Refund.objects.create(order=order, payment=order.payments.get(), amount=Decimal("10"), reason="r")
    assert queries() == few


def test_test_mode_orders_stay_out_of_the_timeline_on_a_live_site(settings):
    customer = student(date_of_birth=birthday(30))
    test_order = paid((ProductFactory(), 1), user=customer, email=customer.email)
    go_live(settings)
    live = paid((ProductFactory(), 1), user=customer, email=customer.email)
    client = signed_in(make_staff(roles.SUPPORT))
    body = client.get(f"{USERS}{customer.pk}/timeline/").json()
    assert {row["href"] for row in body["rows"] if row["kind"] == "order"} == {f"/orders/{live.number}/"}
    assert test_order.number not in json.dumps(body)


# ---- The commerce summary ----


def test_the_commerce_summary_counts_an_adults_orders_and_values_them_so_far():
    from shipping.models import ShipmentDetail
    from shop.models import Address, Shipment

    customer = student(date_of_birth=birthday(30), email="rahul@example.com")
    books = [ProductFactory(price=Decimal(price), mrp=Decimal(price)) for price in ("500", "700", "900")]
    kept = paid((books[0], 1), user=customer, email=customer.email)
    two = paid((books[1], 1), user=customer, email=customer.email)
    gone = paid((books[2], 1), user=customer, email=customer.email)
    Order.objects.filter(pk=gone.pk).update(status="cancelled")
    Cart.objects.filter(user=customer).delete()
    make_order((ProductFactory(), 1), user=customer, email=customer.email)  # never paid: an order, not a kept one
    Refund.objects.create(
        order=two, payment=two.payments.get(), amount=Decimal("200"), reason="Damaged", status="processed"
    )
    Refund.objects.create(order=kept, payment=kept.payments.get(), amount=Decimal("50"), reason="Pending")
    kept.tags.add("school")
    two.tags.add("school", "reprint")
    parcel = Shipment.objects.create(order=two, courier="India Post", tracking_number="EA1")
    ShipmentDetail.objects.create(shipment=parcel, carrier="manual", status="returned")
    Address.objects.create(
        user=customer, name="Rahul Das", phone="+919864012345", line1="House 4, Zoo Road", city="Guwahati",
        district="Kamrup Metro", state="AS", pin="781001", is_default=True,
    )  # fmt: skip
    support = make_staff(roles.SUPPORT)
    body = signed_in(support).get(f"{USERS}{customer.pk}/commerce/").json()
    spent = Order.objects.get(pk=kept.pk).total.amount + Order.objects.get(pk=two.pk).total.amount
    assert (body["child"], body["orders"], body["kept"], body["cancelled"], body["rtos"]) == (False, 4, 2, 1, 1)
    assert (body["spent"], body["refunded"], body["lifetime_value"]) == (f"{spent}", "200.00", f"{spent - 200}")
    assert body["average_order"] == f"{spent / 2}" and body["last_order_at"] and body["first_order_at"]
    assert {(tag["name"], tag["orders"]) for tag in body["tags"]} == {("school", 2), ("reprint", 1)}
    assert body["addresses"] == [
        {
            "city": "Guwahati",
            "district": "Kamrup Metro",
            "state": "AS",
            "pin": "781001",
            "phone": "••••••2345",
            "is_default": True,
        }
    ]
    assert "House 4" not in json.dumps(body) and "Rahul" not in json.dumps(body)  # masked: no street, no name
    assert events("sensitive_read", actor_id=support.pk).get().details == {"what": "commerce", "child": False}


def test_a_childs_commerce_summary_is_the_counts_only():
    kid = child()
    paid((ProductFactory(), 1), user=kid, email=kid.email)
    support = make_staff(roles.SUPPORT)
    body = signed_in(support).get(f"{USERS}{kid.pk}/commerce/").json()
    assert (body["child"], body["orders"], body["kept"]) == (True, 1, 1)
    for field in ["spent", "refunded", "lifetime_value", "average_order", "first_order_at", "last_order_at"]:
        assert body[field] is None, field
    assert body["addresses"] is None and body["tags"] is None
    assert events("sensitive_read", actor_id=support.pk).get().details == {"what": "commerce", "child": True}


def test_commerce_keeps_test_orders_out_of_every_number_on_a_live_site_and_needs_both_permissions(settings):
    customer = student(date_of_birth=birthday(30))
    paid((ProductFactory(price=Decimal("111"), mrp=Decimal("111")), 1), user=customer, email=customer.email)
    go_live(settings)
    live = paid((ProductFactory(price=Decimal("222"), mrp=Decimal("222")), 1), user=customer, email=customer.email)
    body = signed_in(make_staff(roles.FINANCE)).get(f"{USERS}{customer.pk}/commerce/").json()
    assert (body["orders"], body["spent"]) == (1, f"{live.total.amount}")
    sales = signed_in(make_staff(roles.SALES))  # the figures are the orders': SALES may see them, but not the account
    assert sales.get(f"{USERS}{customer.pk}/commerce/").status_code == 404
    assert signed_in(make_staff(roles.MARKETING)).get(f"{USERS}{customer.pk}/commerce/").status_code == 403


# ---- The children waiting for a parent ----


def test_the_children_waiting_for_a_parent_come_oldest_first_with_their_links_life(settings):
    settings.PARENTAL_CONSENT_MODE = "verified"
    older, newer = child(15, contact="old@example.com"), child(14, contact="+919864012345")
    User.objects.filter(pk=older.pk).update(created=timezone.now() - timedelta(days=20))
    done = child(13)
    ConsentRecord.objects.create(user=done, by_parent=True, notice_version="1", verified_at=timezone.now())
    leaving = child(16)
    DeletionRequest.objects.create(user=leaving)
    suspended = child(12, is_active=False)
    adult(email="grown@example.com")  # not a child
    now = timezone.now()
    for days in (6, 1):
        ParentLinkSend.objects.create(user=older, channel="email", sent_at=now - timedelta(days=days))
    ParentLinkSend.objects.create(user=older, channel="email", sent_at=now)
    client = signed_in(make_staff(roles.SUPPORT))
    body = client.get(USERS + "consent-pending/").json()
    assert [row["id"] for row in body["results"]] == [older.pk, newer.pk]
    first, second = body["results"]
    assert (first["parent_contact"], first["parent_channel"], first["links_sent"], first["links_today"]) == (
        "ol•••@example.com",
        "email",
        3,
        1,
    )
    assert first["blocking"] is True and first["daily_limit"] == 3 and first["link_expired"] is False
    assert parse_datetime(first["link_expires_at"]) - parse_datetime(first["last_link_at"]) == timedelta(days=7)
    assert (second["parent_contact"], second["parent_channel"], second["links_sent"]) == ("••••••2345", "sms", 0)
    assert second["last_link_at"] is None and second["link_expires_at"] is None and second["link_expired"] is False
    assert {done.pk, leaving.pk, suspended.pk}.isdisjoint(row["id"] for row in body["results"])
    assert "old@example.com" not in json.dumps(body)  # the contact is masked here as everywhere
    ParentLinkSend.objects.filter(user=older).update(sent_at=now - timedelta(days=9))
    assert client.get(USERS + "consent-pending/").json()["results"][0]["link_expired"] is True
    settings.PARENTAL_CONSENT_MODE = "declared"  # the ones the switch will catch: listed, not blocked yet
    assert client.get(USERS + "consent-pending/").json()["results"][0]["blocking"] is False
    assert signed_in(make_staff(roles.MARKETING)).get(USERS + "consent-pending/").status_code == 403


def test_a_record_shows_its_consent_link_and_the_accounts_a_parent_contact_points_to():
    mother = adult(email="anita@example.com", full_name="Anita Das")
    kid, sibling = child(14, contact="anita@example.com"), child(12, contact="anita@example.com")
    lonely = child(13, contact="nobody@example.com")
    ParentLinkSend.objects.create(user=kid, channel="email")
    client = signed_in(make_staff(roles.SUPPORT))
    record = client.get(f"{USERS}{kid.pk}/").json()
    assert record["linked"] == [{"id": mother.pk, "full_name": "Anita Das", "relation": "parent"}]
    link = record["parent_link"]
    assert (link["sent"], link["expired"], link["today"]) == (1, False, 1)
    assert record["parent_link"]["daily_limit"] == 3
    parent = client.get(f"{USERS}{mother.pk}/").json()
    assert {account["id"] for account in parent["linked"]} == {kid.pk, sibling.pk}
    assert {account["relation"] for account in parent["linked"]} == {"child"} and parent["parent_link"] is None
    assert client.get(f"{USERS}{lonely.pk}/").json()["linked"] == []  # named, with no account of their own
    assert client.get(f"{USERS}{lonely.pk}/").json()["parent_link"]["sent"] == 0


def test_a_link_sent_is_on_record_whoever_sent_it_and_a_texts_quiet_hours_are_kept(settings, monkeypatch):
    settings.PARENTAL_CONSENT_MODE = "verified"
    by_email, by_sms = child(15, contact="anita@example.com"), child(14, contact="+919864012345")
    support = make_staff(roles.SUPPORT)
    client = signed_in(support)
    assert client.post(f"{USERS}{by_email.pk}/resend-verification/").status_code == 200
    monkeypatch.setattr("shipping.messages.quiet", lambda now=None: True)  # 22:30 in India
    night = client.post(f"{USERS}{by_sms.pk}/resend-verification/")
    assert night.status_code == 400 and "08:00 to 21:00" in night.json()["non_field_errors"][0]
    assert client.post(f"{USERS}{by_email.pk}/resend-verification/").status_code == 200  # an email goes at any hour
    monkeypatch.setattr("shipping.messages.quiet", lambda now=None: False)
    assert client.post(f"{USERS}{by_sms.pk}/resend-verification/").status_code == 200
    sent = list(ParentLinkSend.objects.order_by("pk").values_list("user", "channel", "sent_by"))
    assert sent == [
        (by_email.pk, "email", support.pk),
        (by_email.pk, "email", support.pk),
        (by_sms.pk, "sms", support.pk),
    ]


# ---- A parent's consent recorded by hand ----


def verify(client, user, **body):
    body = {
        "method": "staff_manual",
        "evidence_ref": "SR-2026-000042",
        "reason": "The father rang and was checked",
        **body,
    }
    return client.post(f"{USERS}{user.pk}/consent/verify/", body, format="json")


def test_a_parents_consent_by_hand_is_the_ledgers_record_with_its_evidence_and_clears_the_flag(settings, commit):
    settings.PARENTAL_CONSENT_MODE = "verified"
    kid = child(15, contact="anita@example.com", full_name="Rahul Das")
    assert User.objects.get(pk=kid.pk).consent_pending
    support = make_staff(roles.SUPPORT)
    with commit():
        response = verify(signed_in(support), kid, method="adult_account")
    assert response.status_code == 201, response.content
    body = response.json()
    assert (body["event"], body["method"], body["by_parent"], body["verified_by"]) == (
        "given",
        "adult_account",
        True,
        support.pk,
    )
    assert body["evidence_ref"] == "SR-2026-000042" and body["verified_at"]
    record = ConsentRecord.objects.get(pk=body["id"])
    assert (record.user, record.verified_by, record.evidence_ref, record.ip_hash) == (
        kid,
        support,
        "SR-2026-000042",
        "",
    )
    assert not User.objects.get(pk=kid.pk).consent_pending  # the flag clears
    detail = signed_in(support).get(f"{USERS}{kid.pk}/").json()
    assert (detail["consent"], detail["consent_method"]) == ("verified", "adult_account")
    assert signed_in(support).get(USERS + "consent-pending/").json()["results"] == []
    event = events("user.consent_verified").get()
    assert (event.actor_id, event.target_id, event.reason) == (
        support.pk,
        str(kid.pk),
        "The father rang and was checked",
    )
    assert event.details == {"consent": record.pk, "method": "adult_account", "child": True, "parent_told": "email"}
    assert "SR-2026-000042" not in json.dumps(event.details)  # the ledger has the evidence; the log the record's number
    [told] = [message for message in mail.outbox if message.to == ["anita@example.com"]]
    assert "recorded" in told.subject and "Rahul Das's account" in told.body


def test_a_second_recording_a_mobile_contact_and_every_refusal(settings):
    settings.PARENTAL_CONSENT_MODE = "verified"
    kid = child(14, contact="+919864012345")
    client = signed_in(make_staff(roles.SUPPORT))
    assert verify(client, kid).status_code == 201
    assert events("user.consent_verified").get().details["parent_told"] == ""  # a number: no text is registered for it
    again = verify(client, kid)
    assert again.status_code == 400 and "recorded already" in again.json()["non_field_errors"][0]
    assert ConsentRecord.objects.filter(user=kid, verified_by__isnull=False).count() == 1
    grown = verify(client, adult(email="grown@example.com"))
    assert grown.status_code == 400 and "Not a student under 18" in grown.json()["non_field_errors"][0]
    leaving = child(15)
    DeletionRequest.objects.create(user=leaving)
    assert "asked to delete" in verify(client, leaving).json()["non_field_errors"][0]
    erased = child(15)
    User.objects.filter(pk=erased.pk).update(email=f"deleted-{erased.pk}@deleted.invalid")
    assert "erased" in verify(client, erased).json()["non_field_errors"][0]
    waiting = child(15, email="waiting@example.com")
    for bad, field in [
        ({"method": "declared"}, "method"),
        ({"method": "carrier_pigeon"}, "method"),
        ({"evidence_ref": ""}, "evidence_ref"),
        ({"evidence_ref": "the father: father@example.com"}, "evidence_ref"),
        ({"evidence_ref": "rang from 98640 12345"}, "evidence_ref"),
        ({"reason": "  "}, "reason"),
    ]:
        refused = verify(client, waiting, **bad)
        assert refused.status_code == 400 and field in refused.json(), bad
    assert not ConsentRecord.objects.filter(user=waiting, verified_by__isnull=False).exists()
    stale = verify(signed_in(make_staff(roles.SUPPORT), reauth=False), waiting)
    assert (stale.status_code, stale.json()["code"]) == (403, "reauthentication_required")  # high risk: confirm it
    assert signed_in(make_staff(roles.SALES)).post(f"{USERS}{waiting.pk}/consent/verify/", {}).status_code == 403


# ---- Bulk account actions ----


def bulk(client, action, targets, reason="A batch of accounts", dry_run=False):
    body = {
        "kind": "bulk_action",
        "dry_run": dry_run,
        "params": {"action": action, "targets": [str(t) for t in targets], "payload": {}, "reason": reason},
    }
    return client.post(JOBS, body, format="json")


def test_a_dry_run_counts_what_would_change_and_changes_nothing(commit):
    kids = [child() for _ in range(2)]
    grown, suspended = adult(email="a@example.com"), adult(email="b@example.com", is_active=False)
    staff_member = make_staff(roles.SALES)
    admin = make_staff(roles.ADMIN)
    targets = [*[k.pk for k in kids], grown.pk, suspended.pk, staff_member.pk, 999999, "x"]
    with commit():
        response = bulk(signed_in(admin), "user.suspend", targets, dry_run=True)
    assert response.status_code == 202, response.content
    job = Job.objects.get(pk=response.json()["id"])
    assert job.state == "done" and job.dry_run and (job.done, job.total) == (7, 7)
    assert job.result["outcomes"] == {"valid": 3, "refused": 4} and job.result["minors"] == 2
    assert "children" in job.result["approval"] and "second person" in job.result["approval"]  # a real run would wait
    messages = {error["id"]: error["message"] for error in job.errors}
    assert messages[str(suspended.pk)] == "The account is suspended already."
    for refused in (staff_member.pk, 999999, "x"):
        assert "No such customer" in messages[str(refused)]
    assert all(User.objects.get(pk=k.pk).is_active for k in kids) and not ChangeRequest.objects.exists()
    assert not events("user.suspended").exists()
    with commit():
        clean = bulk(signed_in(admin), "user.suspend", [grown.pk], dry_run=True)  # no child: nothing to wait for
    assert Job.objects.get(pk=clean.json()["id"]).result["approval"] is None


def test_a_bulk_suspension_runs_each_account_as_a_request_audited_per_row_and_once_for_the_batch(commit):
    accounts = [adult(email=f"bulk{n}@example.com") for n in range(3)]
    admin = make_staff(roles.ADMIN)
    with commit():
        response = bulk(signed_in(admin), "user.suspend", [a.pk for a in accounts], reason="Chargeback fraud ring")
    job = Job.objects.get(pk=response.json()["id"])
    assert (job.state, job.done, job.total) == ("done", 3, 3) and job.result["outcomes"] == {"executed": 3}
    assert not any(User.objects.get(pk=a.pk).is_active for a in accounts)
    suspended = events("user.suspended")
    assert suspended.count() == 3 and {e.actor_id for e in suspended} == {admin.pk}
    assert {e.reason for e in suspended} == {"Chargeback fraud ring"}
    assert {e.target_id for e in suspended} == {str(a.pk) for a in accounts}
    batch = events("job.done", target_id=str(job.pk)).get()
    assert batch.details["action"] == "user.suspend" and (batch.details["done"], batch.details["total"]) == (3, 3)
    assert len([m for m in mail.outbox if "suspended" in m.subject]) == 3
    with commit():  # lifting them again, and signing one out
        back = bulk(signed_in(admin), "user.unsuspend", [a.pk for a in accounts])
    assert Job.objects.get(pk=back.json()["id"]).result["outcomes"] == {"executed": 3}
    assert all(User.objects.get(pk=a.pk).is_active for a in accounts)
    support = make_staff(roles.SUPPORT)
    with commit():
        signed_out = bulk(signed_in(support), "user.end_sessions", [accounts[0].pk])
    assert Job.objects.get(pk=signed_out.json()["id"]).result["outcomes"] == {"executed": 1}
    ended = events("session_ended_by_staff").get()
    assert ended.target_id == str(accounts[0].pk) and ended.actor_id == support.pk
    denied = bulk(signed_in(support), "user.suspend", [accounts[0].pk])  # suspending is not SUPPORT's
    assert denied.status_code == 403 and "staff.suspend_user" in denied.json()["detail"]


def test_a_bulk_action_above_the_role_cap_waits_for_an_approver_then_runs(monkeypatch, commit):
    monkeypatch.setitem(roles.ROLE_LIMITS[roles.SUPPORT], "bulk_rows", 1)
    accounts = [adult(email=f"cap{n}@example.com") for n in range(2)]
    support, admin = make_staff(roles.SUPPORT), make_staff(roles.ADMIN)
    waiting = bulk(signed_in(support), "user.end_sessions", [a.pk for a in accounts]).json()
    assert waiting["state"] == "queued" and waiting["change_request_id"]
    url = f"{STAFF}change-requests/{waiting['change_request_id']}/"
    change = signed_in(support).get(url).json()
    assert change["action"] == "job.run" and "2 rows are above the limit" in change["rule"]
    assert "minors" not in change["payload"]
    signed_in(admin).post(url + "approve/", {"payload_sha256": change["payload_sha256"]}, format="json")
    with commit():
        signed_in(support).post(url + "execute/")
    assert Job.objects.get(pk=waiting["id"]).result["outcomes"] == {"executed": 2}


def test_a_childs_account_in_a_bulk_action_needs_an_approver_whatever_the_count(commit):
    kid, grown = child(), adult(email="grown@example.com")
    admin, other = make_staff(roles.ADMIN), make_staff(roles.ADMIN)
    waiting = bulk(signed_in(admin), "user.end_sessions", [kid.pk, grown.pk]).json()  # 2 rows: far below the cap
    assert waiting["state"] == "queued" and waiting["change_request_id"]
    url = f"{STAFF}change-requests/{waiting['change_request_id']}/"
    change = signed_in(admin).get(url).json()
    assert change["payload"]["minors"] == 1 and "1 account of the 2 is a child" in change["rule"]
    own = signed_in(admin).post(url + "approve/", {"payload_sha256": change["payload_sha256"]}, format="json")
    assert own.status_code == 403  # not by its maker
    assert (
        signed_in(other).post(url + "approve/", {"payload_sha256": change["payload_sha256"]}, format="json").status_code
        == 200
    )
    with commit():
        assert signed_in(admin).post(url + "execute/").json()["status"] == "executed"
    assert Job.objects.get(pk=waiting["id"]).result["outcomes"] == {"executed": 2}
    alone = bulk(signed_in(admin), "user.end_sessions", [grown.pk]).json()  # without a child: at once
    assert alone["change_request_id"] is None
    one = bulk(signed_in(admin), "user.end_sessions", [kid.pk]).json()  # one child alone is enough
    assert one["state"] == "queued" and one["change_request_id"]
    owners = bulk(signed_in(make_staff(roles.OWNER)), "user.end_sessions", [kid.pk]).json()
    assert owners["change_request_id"]  # no limit does not lift it: the owners need a second person too


def test_resending_the_parents_link_in_bulk_skips_those_not_waiting_and_a_parent_at_the_daily_limit(settings, commit):
    settings.PARENTAL_CONSENT_MODE = "verified"
    one, two = child(15, contact="anita@example.com"), child(14, contact="anita@example.com")
    three, four = child(13, contact="busy@example.com"), child(12, contact="ravi@example.com")
    ConsentRecord.objects.create(user=four, by_parent=True, notice_version="1", verified_at=timezone.now())
    salt = "accounts.parent-consent"
    key = "accounts:parent-links:" + salted_hmac(salt, "busy@example.com", algorithm="sha256").hexdigest()
    cache.set(key, 3, 3600)  # three links went to this parent today already
    support, admin, approver = make_staff(roles.SUPPORT), make_staff(roles.ADMIN), make_staff(roles.ADMIN)
    targets = [one.pk, two.pk, three.pk, four.pk]
    with commit():
        dry = bulk(signed_in(support), "user.resend_consent", targets, dry_run=True).json()
    assert Job.objects.get(pk=dry["id"]).result["outcomes"] == {"valid": 3, "refused": 1}
    assert not ParentLinkSend.objects.exists()
    sent = bulk(signed_in(admin), "user.resend_consent", targets).json()
    assert sent["change_request_id"]  # children among them: a second person first
    change = ChangeRequest.objects.get(pk=sent["change_request_id"])
    payload = {"payload_sha256": change.payload_sha256}
    assert (
        signed_in(support).post(f"{STAFF}change-requests/{change.pk}/approve/", payload, format="json").status_code
        == 403
    )
    signed_in(approver).post(f"{STAFF}change-requests/{change.pk}/approve/", payload, format="json")
    with commit():
        signed_in(admin).post(f"{STAFF}change-requests/{change.pk}/execute/")
    job = Job.objects.get(pk=sent["id"])
    assert job.result["outcomes"] == {"executed": 2, "failed": 1, "refused": 1}
    reasons = {error["id"]: error["message"] for error in job.errors}
    assert "No parent's consent is pending" in reasons[str(four.pk)]
    assert "had its links for today" in reasons[str(three.pk)]
    assert {link.user_id for link in ParentLinkSend.objects.all()} == {one.pk, two.pk}
    assert {link.sent_by_id for link in ParentLinkSend.objects.all()} == {admin.pk}


def test_a_bulk_action_never_names_a_deletion_or_an_unknown_action():
    from staff import jobs

    assert {name for name in jobs.bulk_actions() if name.startswith("user.")} == {
        "user.suspend",
        "user.unsuspend",
        "user.end_sessions",
        "user.resend_consent",
    }
    bad = bulk(signed_in(make_staff(roles.ADMIN)), "user.erase", [1])
    assert bad.status_code == 400 and "action" in bad.json()["params"]


# ---- Queries, the retention of the link records, an age not known ----


def test_every_list_costs_the_same_few_queries_however_long(settings):
    settings.PARENTAL_CONSENT_MODE = "verified"
    client = signed_in(make_staff(roles.SUPPORT))
    paths = [USERS + tail for tail in ("", "?kind=students", "?kind=parents", "?kind=guests", "consent-pending/")]

    def more(count):
        for n in range(count):
            mother = adult(email=f"mother{count}x{n}@example.com")
            pupil = child(14, contact=mother.email)
            ParentLinkSend.objects.create(user=pupil, channel="email")
            paid((ProductFactory(), 1), email=f"guest{count}x{n}@example.com", name="Guest", phone="+919864011111")

    def queries(path):
        client.get(path)  # what the first request after a change reads once (the switches, the session's own)
        with CaptureQueriesContext(connection) as captured_queries:
            assert client.get(path).status_code == 200
        return len(captured_queries)

    more(2)
    few = {path: queries(path) for path in paths}
    more(10)
    assert {path: queries(path) for path in paths} == few


def test_the_link_records_are_kept_a_year_and_then_the_nightly_clean_up_deletes_them():
    from ops.tasks import purge_expired

    kid = child()
    now = timezone.now()
    old = ParentLinkSend.objects.create(user=kid, channel="email", sent_at=now - timedelta(days=400))
    recent = ParentLinkSend.objects.create(user=kid, channel="sms", sent_at=now - timedelta(days=100))
    assert purge_expired()["parent_links"] == 1
    assert list(ParentLinkSend.objects.values_list("pk", flat=True)) == [recent.pk] and old.pk != recent.pk


def test_an_age_not_known_is_taken_for_a_childs_in_the_course_summary():
    from content.tests import make_paper
    from learn.models import Chapter, Clip, Progress, Revision

    chapter = Chapter.objects.create(subject=make_paper().book.subject, number=1, title="One")
    clip = Clip.objects.create(revision=Revision.objects.create(chapter=chapter, title="R"), title="Secret clip")
    unknown = student(date_of_birth=None)
    Progress.objects.create(user=unknown, clip=clip, seconds_watched=30, completed=True)
    body = signed_in(make_staff(roles.SUPPORT)).get(f"{USERS}{unknown.pk}/timeline/").json()
    course = [row for row in body["rows"] if row["kind"] == "course"]
    assert body["child"] is False and len(course) == 1  # not a child by the record, but no weekly detail either
    assert course[0]["label"].startswith("Course use so far: 1 chapter opened")


# ---- The rule: no predictive lifetime value, RFM groups or churn scores on students ----

PREDICTIVE = [
    "predict",
    "forecast",
    "churn",
    "rfm",
    "propensity",
    "score",
    "segment",
    "cluster",
    "likelihood",
    "project",
]


def test_no_serializer_of_the_customers_carries_a_predictive_field():
    from rest_framework.serializers import BaseSerializer

    from staff import customers_api, serializers

    shapes = [serializers.CustomerSerializer, serializers.CustomerDetailSerializer]
    shapes += [getattr(customers_api, name) for name in dir(customers_api) if name.startswith("Customer")]
    shapes = [shape for shape in shapes if isinstance(shape, type) and issubclass(shape, BaseSerializer)]
    assert len(shapes) >= 8
    for shape in shapes:
        for name in shape().fields:
            assert not any(stem in name.lower() for stem in PREDICTIVE), (shape.__name__, name)


def test_no_customer_component_of_the_schema_carries_one_either():
    from drf_spectacular.generators import SchemaGenerator

    components = SchemaGenerator(api_version="v1").get_schema(request=None, public=True)["components"]["schemas"]
    seen = 0
    for name, component in components.items():
        if name.startswith("Customer"):
            for field in component.get("properties", {}):
                seen += 1
                assert not any(stem in field.lower() for stem in PREDICTIVE), (name, field)
    assert seen > 40
