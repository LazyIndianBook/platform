"""The message templates (ops.MessageTemplate, ops/staff_api.py): ops.sms sends a kind with the registry's approved
template (the environment's MSG91_TEMPLATE_<KIND> otherwise) and writes its last use; the API validates what DLT and
MSG91 ask for, audits each change, sends a test to the member of staff's own number or address only; the nightly
check warns of a template unused for months and of the yearly self-certification."""

from datetime import timedelta

import httpx
import pytest
from django.core import mail
from django.utils import timezone

from accounts import roles
from ops import sms
from ops.models import MessageTemplate, SmsLog
from ops.tasks import check_templates
from staff.models import AuditEvent, InboxItem
from staff.tests.conftest import STAFF, make_staff, quick_passwords, signed_in  # noqa: F401  (quick_passwords)

pytestmark = pytest.mark.django_db
TEMPLATES = STAFF + "templates/"
PHONE = "+919864012345"


def approved(event="order_placed", msg91_id="65f0a1b2c3d4e5f6a7b8c9d0", **fields):
    variables = [{"name": "var1", "type": "alphanumeric", "max_length": 30, "about": "the order number"}]
    return MessageTemplate.objects.create(event=event, channel="sms", category="service", approval_state="approved",
                                          msg91_id=msg91_id, variables=variables, **fields)  # fmt: skip


def test_ops_sms_sends_with_the_registrys_template_and_writes_its_last_use(settings, monkeypatch):
    settings.SMS_BACKEND, settings.MSG91_AUTHKEY = "msg91", "msg91-authkey-0123456789"
    settings.MSG91_TEMPLATES = {**settings.MSG91_TEMPLATES, "order_placed": "env-template-id"}
    assert sms.template_id("order_placed") == "env-template-id"  # no row yet: the environment's
    template = approved()
    draft = MessageTemplate.objects.create(event="order_placed", channel="sms", language="as", category="service",
                                           msg91_id="draft-template-0001")  # fmt: skip
    assert sms.template_id("order_placed") == template.msg91_id and sms.template_id("order_placed", "as") == (
        "env-template-id"  # a draft is never sent
    )
    sent = []

    def post(url, **kwargs):
        sent.append(kwargs["json"])
        return httpx.Response(200, json={"type": "success", "message": "req-1"})

    monkeypatch.setattr(sms.httpx, "post", post)
    sms.queue_sms("order_placed", PHONE, {"var1": "EL-2026-000001"})
    assert sent[0]["template_id"] == template.msg91_id
    template.refresh_from_db()
    draft.refresh_from_db()
    assert template.last_used_at is not None and draft.last_used_at is None
    assert SmsLog.objects.get().provider_id == "req-1"


def test_marketing_reads_the_registry_and_only_admin_changes_it():
    template = approved()
    assert signed_in(make_staff(roles.MARKETING)).get(TEMPLATES).json()[0]["id"] == template.pk
    marketing = signed_in(make_staff(roles.MARKETING)).patch(f"{TEMPLATES}{template.pk}/", {"notes": "x"},
                                                            format="json")  # fmt: skip
    assert marketing.status_code == 403
    assert signed_in(make_staff(roles.SUPPORT)).get(TEMPLATES).status_code == 403
    assert signed_in(make_staff(roles.ADMIN)).delete(f"{TEMPLATES}{template.pk}/").status_code == 403  # deactivate
    assert MessageTemplate.objects.filter(pk=template.pk).exists()  # never deleted: no permission names it


def test_a_template_is_validated_as_dlt_and_msg91_ask(settings):
    client = signed_in(make_staff(roles.ADMIN))
    base = {"event": "order_shipped", "channel": "sms", "category": "service"}
    errors = client.post(TEMPLATES, {**base, "dlt_template_id": "12ab", "header": "toolong"}, format="json").json()
    assert set(errors) == {"dlt_template_id", "header"}
    errors = client.post(TEMPLATES, {**base, "event": "welcome", "category": "utility"}, format="json").json()
    assert set(errors) == {"event", "category"}  # no SMS is sent for it; utility is WhatsApp's
    text = {"text": "Order {#var#} shipped by {#var#}", "variables": [{"name": "var1", "type": "alphanumeric",
                                                                         "max_length": 30}]}  # fmt: skip
    assert "text" in client.post(TEMPLATES, {**base, **text}, format="json").json()
    unsendable = client.post(TEMPLATES, {**base, "approval_state": "approved"}, format="json").json()
    assert unsendable == {"msg91_id": ["An approved SMS template needs MSG91's id: it is what is sent."]}
    otp = client.post(TEMPLATES, {"event": "otp", "channel": "sms", "category": "transactional", "variables": [
        {"name": "code", "type": "numeric", "max_length": 6}]}, format="json").json()  # fmt: skip
    assert "variables" in otp
    made = client.post(TEMPLATES, {**base, "header": "exmlef", "header_suffix": "S",
                                   "dlt_template_id": "1107161234567890123"}, format="json")  # fmt: skip
    assert made.status_code == 201 and made.json()["header"] == "EXMLEF"
    assert "No sender header." not in made.json()["warnings"]
    assert client.post(TEMPLATES, {**base}, format="json").status_code == 400  # one per event, channel and language
    assert AuditEvent.objects.get(action="template.created").details == {"event": "order_shipped", "channel": "sms",
                                                                         "language": "en"}  # fmt: skip


def test_a_change_is_audited_and_what_a_template_is_for_stays():
    template = approved(dlt_template_id="")
    client = signed_in(make_staff(roles.ADMIN))
    url = f"{TEMPLATES}{template.pk}/"
    changed = client.patch(url, {"dlt_template_id": "1107161234567890123", "self_certified_on": "2026-10-01"},
                           format="json")  # fmt: skip
    assert changed.status_code == 200 and changed.json()["dlt_template_id"] == "1107161234567890123"
    event = AuditEvent.objects.get(action="template.changed")
    assert event.changes["dlt_template_id"] == ["", "1107161234567890123"]
    assert client.patch(url, {"event": "order_delivered"}, format="json").json()["event"] == [
        "What a template is for stays: add another one instead."
    ]


def test_a_test_goes_to_your_own_confirmed_number_or_address_only(settings, capsys):
    template = approved()
    admin = make_staff(roles.ADMIN)
    url = f"{TEMPLATES}{template.pk}/test/"
    refused = signed_in(admin).post(url, {}, format="json")
    assert refused.status_code == 400 and "your own account" in refused.json()["non_field_errors"][0]
    admin.login_phone, admin.login_phone_verified = PHONE, True
    admin.save()
    answer = signed_in(admin).post(url, {"variables": {"var1": "EL-TEST-1"}}, format="json").json()
    assert answer == {"sent": True, "to": "******2345", "detail": "Sent: it should arrive within a minute."}
    assert "SMS order_placed (template 65f0a1b2c3d4e5f6a7b8c9d0) to +919864012345" in capsys.readouterr().out
    assert SmsLog.objects.get().user == admin  # to the member of staff, counted like any other SMS
    email = MessageTemplate.objects.create(event="order_confirmation", channel="email", category="service",
                                           subject="Your order", text="Order {#var#} is confirmed.",
                                           variables=[{"name": "number", "type": "alphanumeric",
                                                       "max_length": 20}])  # fmt: skip
    mail.outbox.clear()
    sent = signed_in(admin).post(f"{TEMPLATES}{email.pk}/test/", {}, format="json").json()
    assert sent["sent"] and mail.outbox[0].to == [admin.email] and "TEST01" in mail.outbox[0].body
    whatsapp = MessageTemplate.objects.create(event="order_shipped", channel="whatsapp", category="utility")
    assert signed_in(admin).post(f"{TEMPLATES}{whatsapp.pk}/test/", {}, format="json").status_code == 400
    assert AuditEvent.objects.filter(action="template.test_sent").count() == 2


def test_the_nightly_check_warns_of_idle_templates_and_the_yearly_certification():
    now = timezone.now()
    idle = approved(self_certified_on=timezone.localdate())
    MessageTemplate.objects.filter(pk=idle.pk).update(last_used_at=now - timedelta(days=80))
    uncertified = approved(event="order_delivered", msg91_id="65f0a1b2c3d4e5f6a7b8c9d1", last_used_at=now)
    MessageTemplate.objects.create(event="order_shipped", channel="sms", category="service")  # a draft: no warning
    assert check_templates() == {"idle": 1, "certify": 1}
    assert check_templates() == {"idle": 1, "certify": 1}  # still due: the same items, none twice
    kinds = sorted(InboxItem.objects.filter(done_at=None).values_list("kind", "target_id"))
    assert kinds == [("template_certify", str(uncertified.pk)), ("template_idle", str(idle.pk))]
    MessageTemplate.objects.filter(pk=idle.pk).update(last_used_at=now)
    MessageTemplate.objects.filter(pk=uncertified.pk).update(self_certified_on=timezone.localdate())
    assert check_templates() == {"idle": 0, "certify": 0}
    assert not InboxItem.objects.filter(done_at=None).exists()
