"""Data protection duties (research 4): the requests queue with its clocks, the answer's contact block, the erasure's
dry run with its holds and blocks and its approval, the access request's email, the breach register's clocks, and the
processor register."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from django.core import mail
from django.utils import timezone

from accounts import roles
from accounts.models import User
from accounts.tests import birthday
from api.tests import student
from shop import services as shop
from shop.factories import ProductFactory, captured, make_order
from staff.models import DataRequest, InboxItem, Incident, ProcessorRecord
from staff.privacy import add_month, clocks

from .conftest import STAFF, events, make_staff, signed_in

pytestmark = pytest.mark.django_db
REQUESTS = STAFF + "data-requests/"
IST = timezone.get_fixed_timezone(330)


def test_a_request_is_acknowledged_in_48_hours_and_answered_in_a_month_then_90_days_from_may_2027():
    now = datetime(2026, 10, 9, 10, 0, tzinfo=IST)
    assert clocks("access", now) == (now + timedelta(hours=48), datetime(2026, 11, 9, 10, 0, tzinfo=IST))
    later = datetime(2027, 6, 1, 10, 0, tzinfo=IST)  # the DPDP Rules' rights in force
    assert clocks("erasure", later)[1] == later + timedelta(days=90)
    assert clocks("grievance", later)[1] == datetime(2027, 7, 1, 10, 0, tzinfo=IST)  # the E-Commerce Rules' month
    assert add_month(datetime(2027, 1, 31, tzinfo=UTC)).day == 28 and add_month(datetime(2026, 12, 15)).month == 1


def test_the_clocks_follow_the_settings(settings):
    settings.STAFF_DPDP_RULES_FROM = timezone.localdate()  # earlier than planned (MeitY's proposal)
    settings.STAFF_DATA_REQUEST_ACK_HOURS, settings.STAFF_DPDP_RESPONSE_DAYS = 24, 60
    now = timezone.now()
    assert clocks("access", now) == (now + timedelta(hours=24), now + timedelta(days=60))


def test_a_request_goes_through_the_queue_with_its_inbox_item_and_answer():
    support = make_staff(roles.SUPPORT)
    customer = student(email="rahul@example.com")
    client = signed_in(support)
    created = client.post(REQUESTS, {"kind": "access", "channel": "letter", "user": customer.pk,
                                     "requester": "rahul@example.com", "summary": "A copy of my data"},
                          format="json")  # fmt: skip
    assert created.status_code == 201, created.content
    data = created.json()
    assert data["status"] == "new" and not data["ack_overdue"] and data["created_by"] == support.pk
    item = InboxItem.objects.get(kind="data_request", done_at=None)
    assert item.due_at == DataRequest.objects.get(pk=data["id"]).ack_due_at  # first, the acknowledgement
    listed = client.get(REQUESTS).json()["results"][0]
    assert listed["requester"] == "ra•••@example.com"  # masked in lists
    client.post(f"{REQUESTS}{data['id']}/acknowledge/")
    assert DataRequest.objects.get(pk=data["id"]).status == "acknowledged"
    assert InboxItem.objects.get(pk=item.pk).due_at == DataRequest.objects.get(pk=data["id"]).due_at  # now the answer
    text = client.get(f"{REQUESTS}{data['id']}/response/").json()
    assert f"DR-{data['id']}" in text["subject"] and "Grievance Officer" in text["body"]
    assert "Data Protection Board" in text["body"]
    closed = client.post(f"{REQUESTS}{data['id']}/close/", {"outcome": "done", "response": text["body"]}, format="json")
    assert closed.json()["status"] == "closed" and InboxItem.objects.get(pk=item.pk).done_at
    assert [event.action for event in events(target_type="staff.datarequest")] == [
        "data_request.created", "data_request.acknowledged", "data_request.closed"]  # fmt: skip


def test_an_access_requests_data_goes_by_email_to_the_accounts_address_only(django_capture_on_commit_callbacks):
    customer, support = student(email="rahul@example.com"), make_staff(roles.SUPPORT)
    ProcessorRecord.objects.create(name="Razorpay", purpose="payments", data_categories="orders", country="India")
    request = DataRequest.objects.create(kind="access", channel="letter", user=customer, requester="Rahul by post",
                                         summary="A copy")  # fmt: skip
    url = f"{REQUESTS}{request.pk}/export/"
    assert signed_in(support).post(url).status_code == 403  # export_personal_data: ADMIN's
    admin = make_staff(roles.ADMIN)
    assert signed_in(admin).post(url).status_code == 400  # the identity first
    signed_in(admin).post(f"{REQUESTS}{request.pk}/verify-identity/", {"note": "Called the number on the account"})
    with django_capture_on_commit_callbacks(execute=True):
        assert signed_in(admin).post(url).status_code == 202
    [message] = [message for message in mail.outbox if message.attachments]
    assert message.to == ["rahul@example.com"]
    name, content, kind = message.attachments[0]
    assert kind == "application/json" and json.loads(content)["profile"]["email"] == "rahul@example.com"
    assert "- Razorpay: payments (orders; India)" in message.body  # who else processes it (s.11)
    assert events("data_request.exported").get().actor_id == admin.pk


def erasure_request(user, **fields):
    return DataRequest.objects.create(kind="erasure", channel="email", user=user, requester=user.email,
                                      summary="Delete my account", **fields)  # fmt: skip


def test_the_erasure_dry_run_says_what_goes_what_stays_and_what_stops_it(rzp):
    customer = student(email="rahul@example.com")
    order = make_order((ProductFactory(), 1), user=customer, email=customer.email)
    shop.record_capture(captured(order))  # paid: on its way
    request = erasure_request(customer)
    report = signed_in(make_staff(roles.SUPPORT)).get(f"{REQUESTS}{request.pk}/erasure-report/").json()
    parts = {row["part"]: row for row in report["erase"]}
    assert parts["email_addresses"]["count"] == 1 and parts["profile"]["count"] == 1
    kept = {row["part"]: row for row in report["keep"]}  # the books' lines: test_legal.py (this order: test mode)
    assert kept["test_orders"]["count"] == 1 and kept["test_orders"]["kind"] == "test"
    assert kept["test_orders"]["line"] == "kept: 1 order made in test mode, as they are: not books of account"
    assert not report["can_erase"]
    assert any("order is on its way" in block for block in report["blocks"])
    assert any("identity is not verified" in block for block in report["blocks"])


def test_a_childs_erasure_needs_the_parent_and_a_staff_erasure_waits_for_an_approver(
    django_capture_on_commit_callbacks,
):
    child = student(email="rahul@example.com", date_of_birth=birthday(15), parent_name="Anita Das",
                    parent_contact="anita@example.com")  # fmt: skip
    request = erasure_request(child, identity_verified=True)
    support, admin = make_staff(roles.SUPPORT), make_staff(roles.ADMIN)
    blocked = signed_in(support).post(f"{REQUESTS}{request.pk}/erase/", {"reason": "Asked by email"}, format="json")
    assert blocked.status_code == 400 and any("parent or guardian" in block for block in blocked.json()["blocks"])
    DataRequest.objects.filter(pk=request.pk).update(details={"parent_confirmed": "by phone, 9 Oct"})
    asked = signed_in(support).post(f"{REQUESTS}{request.pk}/erase/", {"reason": "Asked by email"}, format="json")
    assert asked.status_code == 202 and asked.json()["checker"] == "staff.approve_erasure"
    change = asked.json()
    url = f"{STAFF}change-requests/{change['id']}/"
    assert signed_in(support).post(url + "approve/", {"payload_sha256": change["payload_sha256"]}).status_code == 403
    signed_in(admin).post(url + "approve/", {"payload_sha256": change["payload_sha256"]})
    with django_capture_on_commit_callbacks(execute=True):
        done = signed_in(admin).post(url + "execute/").json()
    assert done["status"] == "executed", done
    erased = User.objects.get(pk=child.pk)
    assert erased.email == f"deleted-{child.pk}@deleted.invalid" and not erased.is_active
    assert any(message.to == ["rahul@example.com"] and "deleted" in message.subject for message in mail.outbox)
    assert "erased_at" in DataRequest.objects.get(pk=request.pk).details


def test_an_incident_has_its_clocks_and_tells_the_owners_at_once(settings, django_capture_on_commit_callbacks):
    settings.STAFF_ALERT_EMAILS = ["owner@examleaf.in"]
    admin = make_staff(roles.ADMIN)
    detected = timezone.now() - timedelta(hours=7)
    with django_capture_on_commit_callbacks(execute=True):
        created = signed_in(admin).post(STAFF + "incidents/", {"title": "A laptop with exports was stolen",
                                        "kind": "data_leak", "detected_at": detected.isoformat(),
                                        "children_affected": True, "people_affected": 120}, format="json")  # fmt: skip
    assert created.status_code == 201, created.content
    data = created.json()
    assert data["cert_in_overdue"] and not data["board_overdue"]  # 6 hours passed, 72 not
    assert datetime.fromisoformat(data["board_due"]) - datetime.fromisoformat(data["cert_in_due"]) == timedelta(
        hours=66
    )
    assert any("Incident #" in message.subject for message in mail.outbox)
    item = InboxItem.objects.get(kind="incident", done_at=None)
    assert item.permission == "staff.manage_incident" and item.due_at == Incident.objects.get().cert_in_due
    report = {"cert_in_reported_at": timezone.now().isoformat(), "cert_in_reference": "CERTIn-2026-1"}
    reported = signed_in(admin).patch(f"{STAFF}incidents/{data['id']}/", report, format="json").json()
    assert (
        not reported["cert_in_overdue"] and InboxItem.objects.get(pk=item.pk).due_at == Incident.objects.get().board_due
    )
    assert events("incident.updated").get().changes["cert_in_reference"] == ["", "CERTIn-2026-1"]
    signed_in(admin).post(f"{STAFF}incidents/{data['id']}/close/")
    assert InboxItem.objects.get(pk=item.pk).done_at and Incident.objects.get().closed_by == admin
    assert signed_in(make_staff(roles.SUPPORT)).get(STAFF + "incidents/").status_code == 403


def test_the_processor_register_is_kept_with_each_change_logged():
    admin = make_staff(roles.ADMIN)
    created = signed_in(admin).post(STAFF + "processors/", {"name": "Amazon SES", "purpose": "email",
                                    "data_categories": "email addresses, the emails' text", "country": "India (Mumbai)",
                                    "contract_signed_on": "2026-09-01"}, format="json")  # fmt: skip
    assert created.status_code == 201
    pk = created.json()["id"]
    signed_in(admin).patch(f"{STAFF}processors/{pk}/", {"active": False}, format="json")
    assert signed_in(make_staff(roles.SUPPORT)).get(STAFF + "processors/").json()["results"][0]["name"] == "Amazon SES"
    signed_in(admin).delete(f"{STAFF}processors/{pk}/")
    assert not ProcessorRecord.objects.exists()
    assert [event.action for event in events(target_type="staff.processorrecord")] == [
        "processor.created", "processor.updated", "processor.deleted"]  # fmt: skip
