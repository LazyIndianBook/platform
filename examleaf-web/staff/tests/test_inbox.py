"""The inbox (the plan's "one inbox of things that wait for a person"): items filed from what happens elsewhere, shown
to whoever may act on them, assigned, snoozed, done; and the system's page."""

import json
from datetime import timedelta

import pytest
from allauth.account.models import EmailAddress
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts import roles
from accounts.factories import UserFactory
from accounts.models import DeletionRequest
from learn.models import Clip
from learn.tests import make_course
from shop.factories import ProductFactory, make_order
from shop.models import Refund
from staff.models import InboxItem
from staff.signals import task_failed
from staff.tasks import watch

from .conftest import STAFF, events, make_staff, signed_in

pytestmark = pytest.mark.django_db
INBOX = STAFF + "inbox/"


def kinds(user, **query):
    return sorted(item["kind"] for item in signed_in(user).get(INBOX, query).json()["results"])


def test_requests_from_teachers_and_deletions_wait_for_those_who_act_on_them():
    teacher = UserFactory()
    EmailAddress.objects.create(user=teacher, email=teacher.email, verified=True, primary=True)
    api = APIClient()
    api.force_authenticate(teacher)
    api.post("/api/v1/me/teacher/", {"school_name": "Cotton", "district": "Kamrup", "subject": "Physics"})
    deletion = DeletionRequest.objects.create(user=UserFactory())
    support, sales = make_staff(roles.SUPPORT), make_staff(roles.SALES)
    assert kinds(support) == ["deletion_request", "teacher_request"]
    assert kinds(sales) == []  # neither is theirs to act on
    item = InboxItem.objects.get(kind="deletion_request")
    assert item.due_at == deletion.due_at and "#" in item.title and teacher.email not in item.title
    deletion.complete()
    assert kinds(support) == ["teacher_request"]  # done by itself once the deletion is


def test_items_are_assigned_snoozed_and_done():
    item = InboxItem.objects.create(
        kind="failed_job",
        title="A task failed",
        permission="staff.view_system",
        target_type="celery.task",
        target_id="x",
        due_at=timezone.now() - timedelta(hours=1),
    )
    admin, other_admin, support = make_staff(roles.ADMIN), make_staff(roles.ADMIN), make_staff(roles.SUPPORT)
    assert signed_in(admin).get(INBOX + "count/").json() == {"open": 1, "overdue": 1}
    refused = signed_in(admin).post(f"{INBOX}{item.pk}/assign/", {"assignee": support.pk}, format="json")
    assert refused.status_code == 400  # support may not act on it
    signed_in(admin).post(f"{INBOX}{item.pk}/assign/", {"assignee": other_admin.pk}, format="json")
    assert kinds(other_admin, mine="true") == ["failed_job"] and kinds(admin) == []  # the assignee's now
    later = (timezone.now() + timedelta(days=1)).isoformat()
    signed_in(other_admin).post(f"{INBOX}{item.pk}/snooze/", {"until": later})
    assert kinds(other_admin) == [] and kinds(other_admin, snoozed="true") == ["failed_job"]
    assert signed_in(other_admin).post(f"{INBOX}{item.pk}/done/").json()["done_by"] == other_admin.pk
    assert kinds(other_admin, snoozed="true") == []
    assert kinds(other_admin, done="true", snoozed="true") == ["failed_job"]


def test_a_failed_clip_a_failed_task_a_refused_webhook_and_a_failed_refund_are_filed(client, rzp):
    make_course(chapters=1, clips=1)
    clip = Clip.objects.get()
    Clip.objects.filter(pk=clip.pk).update(processing="processing")
    clip = Clip.objects.get(pk=clip.pk)
    clip.fail("ffmpeg is not installed")
    clip.save()
    assert InboxItem.objects.get(kind="failed_job", target_type="learn.clip").permission == "learn.change_clip"
    task_failed(sender=type("Task", (), {"name": "shop.tasks.generate_invoice"})(), task_id="t1", exception=OSError())
    task_failed(sender=type("Task", (), {"name": "shop.tasks.generate_invoice"})(), task_id="t2", exception=OSError())
    assert InboxItem.objects.filter(target_type="celery.task").count() == 1  # one a day per task
    body = json.dumps({"event": "payment.captured", "payload": {}})
    for _ in range(2):
        client.post(reverse("shop:razorpay_webhook"), body, content_type="application/json",
                    HTTP_X_RAZORPAY_SIGNATURE="forged")  # fmt: skip
    webhook = InboxItem.objects.get(kind="failed_webhook")
    assert webhook.data == {"count": 2} and webhook.permission == "staff.view_system"
    order = make_order((ProductFactory(), 1))
    payment = order.payments.get()
    refund = Refund.objects.create(order=order, payment=payment, amount=100, reason="x", status="failed",
                                   error="BAD_REQUEST")  # fmt: skip
    assert watch() == 1 and watch() == 0
    assert InboxItem.objects.get(target_type="shop.refund").permission == "staff.refund_order"
    Refund.objects.filter(pk=refund.pk).update(status="processed")
    watch()
    assert InboxItem.objects.get(target_type="shop.refund").done_at is not None
    system = signed_in(make_staff(roles.ADMIN)).get(STAFF + "system/").json()
    assert system["webhooks"]["refused_7_days"] == 2


def test_a_parcels_exception_waits_until_its_deadline_and_goes_once_settled(django_capture_on_commit_callbacks):
    from shipping import services as shipping
    from shop.models import Shipment

    order = make_order((ProductFactory(), 1))
    parcel = Shipment.objects.create(order=order, courier="India Post", tracking_number="EA1IN")
    with django_capture_on_commit_callbacks(execute=True):
        failed = shipping.open_exception(parcel, "ndr", hours=24, data={"attempts": 1})
    item = InboxItem.objects.get(kind="shipping_exception")
    assert (item.target_type, item.target_id, item.permission) == ("shipping.shippingexception", str(failed.pk),
                                                                   "staff.act_on_exception")  # fmt: skip
    assert item.title == f"Parcel of {order.number}: delivery failed (NDR)" and item.due_at == failed.due_at
    sales, packer = make_staff(roles.SALES), make_staff(roles.PACKER)
    assert kinds(sales) == ["shipping_exception"] and kinds(packer) == []  # who acts on failed deliveries
    shipping.open_exception(parcel, "ndr", hours=2, data={"attempts": 2})  # a second attempt failed: sooner
    item.refresh_from_db()
    assert item.due_at == InboxItem.objects.get().due_at <= timezone.now() + timedelta(hours=2)
    with django_capture_on_commit_callbacks(execute=True):
        shipping.resolve_exception(failed, "Called: at home tomorrow.", by=sales)
    assert kinds(sales) == [] and InboxItem.objects.get().done_at
    with django_capture_on_commit_callbacks(execute=True):
        owed = shipping.open_exception(parcel, "cod_overdue", data={"expected": "299.00"}, reference="cod-1")
    assert InboxItem.objects.get(target_id=str(owed.pk)).permission == "staff.reconcile_cod"  # FINANCE's
    assert kinds(make_staff(roles.FINANCE)) == ["shipping_exception"]
    with django_capture_on_commit_callbacks(execute=True):
        shipping.close_exceptions(parcel, ["cod_overdue"], "Remitted.")  # settled by the parcel's news
    assert not InboxItem.objects.filter(done_at=None).exists()


def test_an_integrations_dead_letter_failed_event_and_open_circuit_wait_until_settled(
    django_capture_on_commit_callbacks,
):
    from integrations import services as integrations
    from integrations.models import FAILURES_TO_OPEN, InboundEvent, IntegrationAccount

    admin = make_staff(roles.ADMIN)
    with django_capture_on_commit_callbacks(execute=True):
        failure = integrations.dead_letter("shipping.tasks.poll_tracking", "t-1", OSError("down"), [], {})
        event = InboundEvent.objects.create(provider="shiprocket", body="{}", sha256="0" * 64)
        event.fail("KeyError: 'awb'")
        account = IntegrationAccount.objects.create(provider="shiprocket", mode="test", enabled=True)
        for _ in range(FAILURES_TO_OPEN):
            account.record_failure(OSError("timed out"))
        integrations.dead_letter("erp.tasks.replay_row", "t-2", OSError("refused"), [1], {})  # (erp/inbox.py's own)
    assert kinds(admin) == ["dead_letter", "failed_event", "integration_down"]
    assert sorted(InboxItem.objects.values_list("title", flat=True)) == [
        f"Dead letter #{failure.pk}: poll_tracking gave up",
        f"Shiprocket event #{event.pk} not processed",
        "Shiprocket unavailable: calls wait (its circuit is open)",
    ]
    assert kinds(make_staff(roles.SALES)) == []  # the system's watchers': staff.view_system
    with django_capture_on_commit_callbacks(execute=True):
        failure.discard("Shiprocket fixed it on their side", by=admin)
        event.processed_at = timezone.now()  # replayed, and it went through this time
        event.state = InboundEvent.State.ACCEPTED
        event.save()
        account.record_success()
    assert kinds(admin) == [] and InboxItem.objects.filter(done_at=None).count() == 0


def test_the_system_page_shows_health_queues_mail_sms_backups_and_the_audit_chain():
    staff = make_staff(roles.ADMIN)
    from staff.tasks import verify_audit_chain

    verify_audit_chain()
    data = signed_in(staff).get(STAFF + "system/").json()
    assert {row["check"] for row in data["health"]} >= {"Database", "Cache", "Storage"}
    assert all(row["ok"] for row in data["health"]), data["health"]
    assert data["celery"]["queues"] is None and data["celery"]["failed_7_days"] == 0  # tasks run inline here
    assert data["backups"] == {"configured": False} and data["maintenance"] == {"on": False, "banner": ""}
    assert data["audit"]["last_verification"]["action"] == "audit.verified"
    assert signed_in(make_staff(roles.SUPPORT)).get(STAFF + "system/").status_code == 403


def test_the_system_page_lists_the_last_backup_in_the_bucket(settings, tmp_path):
    settings.STORAGES = {**settings.STORAGES, "backups": {"BACKEND": "django.core.files.storage.FileSystemStorage",
                                                          "OPTIONS": {"location": tmp_path}}}  # fmt: skip
    (tmp_path / "database").mkdir()
    for name in ["examleaf-20261007-021500.dump.age", "examleaf-20261008-021500.dump.age"]:
        (tmp_path / "database" / name).write_bytes(b"x" * 10)
    backups = signed_in(make_staff(roles.ADMIN)).get(STAFF + "system/").json()["backups"]
    assert (backups["latest"], backups["size"]) == ("examleaf-20261008-021500.dump.age", 10)


def test_asking_razorpay_again_about_a_stuck_payment(rzp):
    order = make_order((ProductFactory(), 1))
    rzp.order.payments.return_value = {"items": []}
    response = signed_in(make_staff(roles.ADMIN)).post(STAFF + "system/reconcile/", {"order": order.number})
    assert response.json() == {"order": order.number, "paid": False}
    assert events("order.reconciled").get().details == {"paid": False}
    assert (
        signed_in(make_staff(roles.SUPPORT)).post(STAFF + "system/reconcile/", {"order": order.number}).status_code
        == 403
    )
