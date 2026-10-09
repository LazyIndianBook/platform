"""Telling the customer: the SMS of a courier's news only to an account that asked for them, COD-only for "out for
delivery", never from 21:00 to 08:00 (held for the morning, sent then only if still true), only with its DLT
template; emails to the order's address, never to a suppressed one; WhatsApp a hook."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from django.core import mail

from ops.models import EmailSuppression
from ops.sms import send_order_sms
from shipping import messages, services
from shipping.messages import quiet as real_quiet
from shipping.models import ShipmentDetail
from shipping.status import Status
from shipping.tasks import send_held_messages

pytestmark = pytest.mark.django_db
IST = ZoneInfo("Asia/Kolkata")


@pytest.fixture
def parcel(account, pickup, cod):
    return services.book(services.prepare(cod, account=account, courier_company_id=51))


def test_quiet_from_nine_at_night_to_eight_in_the_morning():
    def at(hour, minute=0):
        return real_quiet(datetime(2026, 10, 9, hour, minute, tzinfo=IST))

    assert at(21) and at(23, 59) and at(0) and at(7, 59)
    assert not at(8) and not at(12) and not at(20, 59)


def test_a_courier_s_news_at_night_waits_for_the_morning(
    parcel, texts, monkeypatch, django_capture_on_commit_callbacks
):
    monkeypatch.setattr(messages, "quiet", lambda now=None: True)
    with django_capture_on_commit_callbacks(execute=True):
        messages.tell(parcel, "shipped")
    assert texts == [] and ShipmentDetail.objects.get(shipment=parcel).sms_held == "shipped"
    ShipmentDetail.objects.filter(shipment=parcel).update(status=Status.IN_TRANSIT)
    assert send_held_messages() == 1 and texts == [(parcel.order.number, "shipped")]
    assert ShipmentDetail.objects.get(shipment=parcel).sms_held == ""
    with django_capture_on_commit_callbacks(execute=True):
        messages.tell(parcel, "out_for_delivery")  # at 21:30: by the morning it is no longer news
    assert send_held_messages() == 0 and len(texts) == 1


def test_a_held_message_goes_only_if_still_true(parcel, texts):
    ShipmentDetail.objects.filter(shipment=parcel).update(status=Status.DELIVERED, sms_held="delivery_failed")
    assert send_held_messages() == 0 and texts == []


def test_sms_only_to_those_who_asked_for_them_and_out_for_delivery_only_for_cash_on_delivery(
    parcel, texts, prepaid, account, django_capture_on_commit_callbacks
):
    order = parcel.order
    assert messages.sms_wanted(order, "out_for_delivery") and not messages.sms_wanted(prepaid, "out_for_delivery")
    assert messages.sms_wanted(prepaid, "delivery_failed") and not messages.sms_wanted(order, "returning")
    order.user.sms_updates = False
    order.user.save()
    order.refresh_from_db()
    assert not messages.sms_wanted(order, "shipped")


def test_no_sms_for_a_kind_without_its_dlt_template(parcel, settings):
    settings.SMS_BACKEND = "msg91"
    settings.MSG91_TEMPLATES = {**settings.MSG91_TEMPLATES, "order_not_delivered": "", "order_shipped": "tmpl-1"}
    assert not messages.sms_wanted(parcel.order, "delivery_failed") and messages.sms_wanted(parcel.order, "shipped")


def test_the_new_sms_say_what_their_templates_need(parcel, capsys):
    order = parcel.order
    send_order_sms(order, "out_for_delivery")
    send_order_sms(order, "delivery_failed")
    out = capsys.readouterr().out
    assert f"order_arriving to +919864012345: {{'var1': '{order.number}', 'var2': '598.00'}}" in out
    assert f"order_not_delivered to +919864012345: {{'var1': '{order.number}', 'var2': '{order.token}'}}" in out


def test_emails_of_a_failed_delivery_and_a_return_and_never_to_a_suppressed_address(
    parcel, settings, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        messages.tell(parcel, "delivery_failed")
        messages.tell(parcel, "returning")
    failed, returning = mail.outbox[-2:]
    assert failed.subject.endswith("could not be delivered") and parcel.tracking_number in failed.body
    assert "/contact/" in failed.body and parcel.order.get_link_url() in failed.body
    assert returning.subject.endswith("is coming back to us") and "Nothing has been charged." in returning.body
    settings.MAILERS = {"default": {"BACKEND": "anymail.backends.test.EmailBackend"}}  # Anymail's pre_send runs
    EmailSuppression.objects.create(email=parcel.order.email, reason="bounce", esp="Amazon SES")
    sent = len(mail.outbox)
    with django_capture_on_commit_callbacks(execute=True):
        messages.tell(parcel, "delivery_failed")
    assert len(mail.outbox) == sent  # nothing went


def test_whatsapp_is_a_hook_only(parcel):
    assert messages.notify_whatsapp(parcel, "shipped") is None
