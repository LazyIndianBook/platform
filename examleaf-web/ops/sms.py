"""SMS: `queue_sms(kind, phone, variables)` hands one message to the Celery task `send_sms`, which sends it through
settings.SMS_BACKEND ("console" prints it; "msg91") and records it in SmsLog. Numbers are E.164 (+919864012345). The
kinds, their variables and the DLT templates registered for them are in RUNBOOK.md "SMS":

    otp              {"otp": "483920"}                     allauth's codes: phone log-in, phone confirmation
    order_placed     {"var1": order number}
    order_shipped    {"var1": order number, "var2": courier and tracking number}
    order_delivered  {"var1": order number}
    parent_consent   {"var1": the student's first name, "var2": the consent link's token}

A DLT variable holds at most 30 characters."""

import logging
from datetime import timedelta

import httpx
from celery import shared_task
from django.conf import settings
from django.utils import timezone
from django.utils.crypto import salted_hmac

from .models import SmsLog

logger = logging.getLogger(__name__)
MSG91 = "https://control.msg91.com/api/v5/"
KEEP = timedelta(days=90)  # SmsLog rows


class SmsRefused(Exception):
    """The provider answered and did not take the message (template, number, key or server address: see its text)."""


def phone_hash(phone):
    return salted_hmac("ops.SmsLog.phone", phone, algorithm="sha256").hexdigest()


def console(kind, phone, variables):
    print(f"SMS {kind} to {phone}: {variables}", flush=True)
    return ""


def msg91(kind, phone, variables):
    """MSG91's OTP API for codes (allauth makes the code, MSG91 only delivers it) and its Flow API for the rest, with
    the template id of MSG91_TEMPLATE_<KIND>. Returns MSG91's request id. HTTP 200 without "type": "success" is a
    refusal too."""
    headers, mobile = {"authkey": settings.MSG91_AUTHKEY}, phone.removeprefix("+")
    template = settings.MSG91_TEMPLATES[kind]
    if kind == "otp":
        params = {"template_id": template, "mobile": mobile, "otp": variables["otp"]}
        response = httpx.post(MSG91 + "otp", params=params, json={}, headers=headers, timeout=10)
    else:
        body = {"template_id": template, "short_url": "0", "recipients": [{"mobiles": mobile, **variables}]}
        response = httpx.post(MSG91 + "flow", json=body, headers=headers, timeout=10)
    try:
        data = response.json()
    except ValueError:
        data = {}
    if response.status_code != 200 or data.get("type") != "success":
        raise SmsRefused(f"MSG91 {response.status_code}: {data.get('message') or response.text[:200]}")
    return str(data.get("request_id") or data.get("message") or "")[:100]


BACKENDS = {"console": console, "msg91": msg91}


@shared_task(autoretry_for=(httpx.TransportError,), retry_backoff=10, max_retries=3)
def send_sms(kind, phone, variables):
    """Send one SMS, unless SMS_DAILY_CAP were sent since midnight (India) already: SMS cost money, and the cache-based
    limits let everything through while Redis is down. A network failure is tried again 3 times; a refusal is logged
    as an error (Sentry), not retried. Returns nothing: Celery logs return values."""
    now = timezone.now()
    midnight = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
    log = SmsLog(kind=kind, phone_hash=phone_hash(phone), phone_last4=phone[-4:])
    if SmsLog.objects.filter(created__gte=midnight, status=SmsLog.Status.SENT).count() >= settings.SMS_DAILY_CAP:
        log.status = SmsLog.Status.CAPPED
        logger.error("SMS_DAILY_CAP reached: an SMS (%s) was not sent", kind)
    else:
        try:
            log.provider_id = BACKENDS[settings.SMS_BACKEND](kind, phone, variables)
            log.status = SmsLog.Status.SENT
        except SmsRefused as refusal:
            log.status = SmsLog.Status.FAILED
            logger.error("SMS (%s) refused: %s", kind, refusal)
    log.save()
    SmsLog.objects.filter(created__lt=now - KEEP).delete()  # ponytail: purged here; a beat task if SMS grow


def queue_sms(kind, phone, variables):
    """Hand an SMS to the worker; if the broker cannot be reached, send it here and now (as ops.tasks.queue_email).
    Nothing goes out while SMS are off (settings.SMS_ENABLED: a server without a real backend)."""
    if not settings.SMS_ENABLED:
        return
    try:
        send_sms.delay(kind, phone, variables)
    except send_sms.OperationalError:
        logger.exception("broker unavailable, sending the SMS synchronously")
        try:
            send_sms.run(kind, phone, variables)
        except Exception:
            logger.exception("the SMS could not be sent here either; dropped")


ORDER_SMS = {"confirmation": "order_placed", "shipped": "order_shipped", "delivered": "order_delivered"}


def send_order_sms(order, kind):
    """For the shop's notifications (shop.services.notify, with its kinds): "confirmation", "shipped" and "delivered"
    send an SMS, other kinds nothing; and only to an account with a confirmed mobile number that asked for order
    updates by SMS on My account."""
    user = order.user
    if kind not in ORDER_SMS or not (user and user.login_phone_verified and user.sms_updates):
        return
    variables = {"var1": order.number}
    if kind == "shipped" and (shipment := order.shipments.first()):  # the latest
        variables["var2"] = f"{shipment.courier} {shipment.tracking_number}"[:30]
    queue_sms(ORDER_SMS[kind], user.login_phone, variables)
