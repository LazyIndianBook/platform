"""DPDP self-service: download my data, delete my account (grace period, cancel, purge), re-verified email change."""

import json
import re
from datetime import timedelta

import pytest
from allauth.account.models import EmailAddress
from axes.models import AccessAttempt
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from accounts.factories import PASSWORD, UserFactory
from accounts.models import ConsentRecord, DeletionRequest, TeacherProfile, User
from accounts.tasks import purge_due_deletions
from content.tests import make_paper
from practice.models import Attempt
from shop.factories import ADDRESS, ProductFactory, make_order
from shop.models import Address, CreditNote, Invoice, Refund

pytestmark = pytest.mark.django_db


@pytest.fixture
def student(client):
    user = UserFactory(email="rahul@example.com", parent_name="Anita Das", parent_contact="+919864012345")
    EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
    ConsentRecord.objects.create(user=user, notice_version="2026-10-08", by_parent=True, ip_hash="ab" * 32)
    Attempt.objects.create(user=user, paper=make_paper(), marks_obtained=52, notes="revise optics")
    client.force_login(user)
    return user


def reauthenticate(client, response):
    """allauth asks for the password again (none entered in the last 5 minutes); then the request goes through."""
    assert response.status_code == 302 and response.url.startswith(reverse("account_reauthenticate"))
    return client.post(response.url, {"password": PASSWORD})


def test_download_my_data_asks_for_the_password_and_gives_everything(client, student):
    Address.objects.create(user=student, **{**ADDRESS, "phone": "+919864012345"}, is_default=True)
    order = make_order((ProductFactory(title="Physics Sample Papers", price=299), 1), user=student, email=student.email)
    invoice = Invoice.objects.create(order=order, number="EL/2026-27/00001", financial_year="2026-27", serial=1)
    refund = Refund.objects.create(order=order, payment=order.payments.get(), amount=299, reason="Parcel refused.")
    CreditNote.objects.create(
        refund=refund, invoice=invoice, number="CN/2026-27/00001", financial_year="2026-27", serial=1
    )
    response = reauthenticate(client, client.get(reverse("data_export")))
    response = client.get(response.url)
    assert response["Content-Disposition"].startswith('attachment; filename="examleaf-my-data-')
    assert "no-cache" in response["Cache-Control"]
    data = json.loads(response.content)
    assert data["profile"]["email"] == "rahul@example.com" and data["profile"]["parent_name"] == "Anita Das"
    assert data["attempts"][0]["paper__code"] == "PHY-E01" and data["attempts"][0]["notes"] == "revise optics"
    assert data["consents"][0]["notice_version"] == "2026-10-08" and data["email_addresses"][0]["verified"]
    address = data["addresses"][0]
    assert (address["pin"], address["phone"], address["is_default"]) == ("781001", "+919864012345", True)
    [exported] = data["orders"]
    assert (exported["number"], exported["total"], exported["status"]) == (order.number, "299.00", "awaiting payment")
    assert exported["items"] == [{"title": "Physics Sample Papers", "quantity": 1, "unit_price": "299.00"}]
    assert exported["shipping_address"]["name"] == "Rahul Das" and exported["refunds"][0]["amount"] == "299.00"
    assert (exported["invoice"], exported["credit_notes"]) == ("EL/2026-27/00001", ["CN/2026-27/00001"])  # numbers only


def test_delete_my_account_waits_seven_days_and_can_be_cancelled(client, student):
    assert client.get(reverse("account_delete")).status_code == 200  # the explanation needs no password
    response = reauthenticate(client, client.post(reverse("account_delete"), {"confirm": "on"}))
    client.get(response.url)  # allauth resumes the stashed POST after the password
    deletion = DeletionRequest.objects.get(user=student)
    assert deletion.status == "pending"
    assert deletion.due_at - deletion.requested_at == timedelta(days=7)
    assert student.consents.first().event == "withdrawn"
    assert mail.outbox[-1].subject == "[ExamLeaf] Your account will be deleted"
    assert "Keep my account" in client.get(reverse("account")).text

    client.post(reverse("account_delete_cancel"))
    deletion.refresh_from_db()
    assert deletion.status == "cancelled" and student.consents.first().event == "given"
    assert mail.outbox[-1].subject == "[ExamLeaf] Your account will not be deleted"


def test_purge_erases_personal_data_of_due_requests_only(student):
    other = UserFactory(full_name="Priya Kalita")
    DeletionRequest.objects.create(user=other)  # requested now: seven days to go
    DeletionRequest.objects.create(user=student, requested_at=timezone.now() - timedelta(days=7, minutes=1))
    TeacherProfile.objects.create(user=student, school_name="Cotton Collegiate", district="Kamrup", subject="Physics")
    AccessAttempt.objects.create(username=student.email, ip_address="10.0.0.1", failures_since_start=1)
    LogEntry.objects.log_actions(other.pk, [student], CHANGE, change_message="[]")

    assert purge_due_deletions.delay().get() == 1

    gone = User.objects.get(pk=student.pk)
    assert (gone.email, gone.full_name, gone.parent_name, gone.parent_contact, gone.date_of_birth) == (
        f"deleted-{gone.pk}@deleted.invalid",
        "Deleted account",
        "",
        "",
        None,
    )
    assert not gone.is_active and not gone.has_usable_password() and not gone.groups.exists()
    assert not EmailAddress.objects.filter(user=gone).exists() and not TeacherProfile.objects.exists()
    assert not AccessAttempt.objects.exists()
    assert list(gone.attempts.values_list("marks_obtained", "notes")) == [(52, "")]  # statistics, no notes
    assert gone.consents.get().ip_hash == ""  # the consent stays as proof, without the address hash
    log = LogEntry.objects.get(content_type=ContentType.objects.get_for_model(User), object_id=str(gone.pk))
    assert "rahul" not in log.object_repr
    assert DeletionRequest.objects.get(user=gone).status == "done"
    assert mail.outbox[-1].to == ["rahul@example.com"] and "deleted" in mail.outbox[-1].subject
    assert User.objects.get(pk=other.pk).full_name == "Priya Kalita"


def test_a_new_email_address_is_used_only_after_its_code_is_confirmed(client, student):
    response = reauthenticate(
        client, client.post(reverse("account_email"), {"email": "rahul.das@example.com", "action_add": ""})
    )
    client.get(response.url)
    to_new = [m for m in mail.outbox if m.to == ["rahul.das@example.com"]]
    assert to_new and re.search(r"^[A-Z0-9]{4}-[A-Z0-9]{4}$", to_new[0].body, re.M)
    student.refresh_from_db()
    assert student.email == "rahul@example.com"  # unchanged until the code is typed
