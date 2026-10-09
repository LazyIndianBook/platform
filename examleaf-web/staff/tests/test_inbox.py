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
