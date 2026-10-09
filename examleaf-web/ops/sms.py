"""SMS: `queue_sms(kind, phone, variables)` hands one message to the Celery task `send_sms`, which sends it through
settings.SMS_BACKEND ("console" prints it; "msg91") and records it in SmsLog. Numbers are E.164 (+919864012345). The
kinds, their variables and the DLT templates registered for them are in RUNBOOK.md "SMS":

    otp              {"otp": "483920"}                     allauth's codes: phone log-in, phone confirmation
    order_placed     {"var1": order number}
    order_shipped    {"var1": order number, "var2": courier and tracking number}
    order_delivered  {"var1": order number}
    order_arriving   {"var1": order number, "var2": the cash to keep ready, "638.00"} (out for delivery, COD only)
    order_not_delivered  {"var1": order number, "var2": the order link's token} (the courier's attempt failed)
    parent_consent   {"var1": the student's first name, or "a student", "var2": the consent link's token}

A DLT variable holds at most 30 characters."""

import logging
import math
from datetime import timedelta

import httpx
from celery import shared_task
from django.conf import settings
from django.utils import timezone
from django.utils.crypto import salted_hmac

from .models import SmsLog

logger = logging.getLogger(__name__)
MSG91 = "https://control.msg91.com/api/v5/"
TIMEOUT = httpx.Timeout(10, connect=3)  # seconds: 3 to connect, 10 for each read or write (retries: send_sms)
KEEP = timedelta(days=90)  # SmsLog rows
# Limits before SMS_DAILY_CAP (M2), every kind together: per number over the last hour and day, per account over the
# last day. Then each purpose's share of the day's cap (since midnight, India), so that consent links or order updates
# cannot use up the log-in codes' share, nor the codes theirs. SMS_DAILY_CAP stays the last line (send_sms).
PER_NUMBER = [(timedelta(hours=1), 5, "an hour"), (timedelta(days=1), 10, "a day")]
PER_ACCOUNT_DAY = 20
SHARES = {"otp": 0.7, "parent_consent": 0.1, "order": 0.3}


def purpose(kind):
    return "order" if kind.startswith("order_") else kind


def midnight(now):
    return timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)


def refusal(log):
    """Why the SMS of this SmsLog row (just made, so counted) may not go, or "" (M2)."""
    now, counted = timezone.now(), SmsLog.objects.exclude(status=SmsLog.Status.CAPPED)
    for window, most, span in PER_NUMBER:
        if counted.filter(phone_hash=log.phone_hash, created__gt=now - window).count() > most:
            return f"{most} to one number in {span}"
    if log.user_id and counted.filter(user=log.user_id, created__gt=now - timedelta(days=1)).count() > PER_ACCOUNT_DAY:
        return f"{PER_ACCOUNT_DAY} for one account in a day"
    share = math.ceil(settings.SMS_DAILY_CAP * SHARES[purpose(log.kind)])
    kinds = [kind for kind in settings.SMS_KINDS if purpose(kind) == purpose(log.kind)]
    if counted.filter(kind__in=kinds, created__gte=midnight(now)).count() > share:
        return f"the day's share of {purpose(log.kind)} SMS ({share})"
    return ""


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
        response = httpx.post(MSG91 + "otp", params=params, json={}, headers=headers, timeout=TIMEOUT)
    else:
        body = {"template_id": template, "short_url": "0", "recipients": [{"mobiles": mobile, **variables}]}
        response = httpx.post(MSG91 + "flow", json=body, headers=headers, timeout=TIMEOUT)
    try:
        data = response.json()
    except ValueError:
        data = {}
    if response.status_code != 200 or data.get("type") != "success":
        raise SmsRefused(f"MSG91 {response.status_code}: {data.get('message') or response.text[:200]}")
    return str(data.get("request_id") or data.get("message") or "")[:100]


BACKENDS = {"console": console, "msg91": msg91}


@shared_task(autoretry_for=(httpx.TransportError,), retry_backoff=10, max_retries=3)
def send_sms(kind, phone, variables, log_id=None):
    """Send one SMS (its SmsLog row made by queue_sms), unless SMS_DAILY_CAP were sent since midnight (India) already:
    the last line, whatever the other limits let through (SMS cost money). A network failure is tried again 3 times; a
    refusal is logged as an error (Sentry), not retried. Its row says whether it went: run again (the task given to
    another worker after one died), an SMS sent or refused already is not sent again. Returns nothing: Celery logs
    return values."""
    now = timezone.now()
    log = SmsLog.objects.filter(pk=log_id).first() or SmsLog(
        kind=kind, phone_hash=phone_hash(phone), phone_last4=phone[-4:]
    )
    if log.status in (SmsLog.Status.SENT, SmsLog.Status.FAILED):
        return
    if SmsLog.objects.filter(created__gte=midnight(now), status=SmsLog.Status.SENT).count() >= settings.SMS_DAILY_CAP:
        log.status = SmsLog.Status.CAPPED
        logger.error("SMS_DAILY_CAP reached: an SMS (%s) was not sent", kind)
    else:
        try:
            log.provider_id = BACKENDS[settings.SMS_BACKEND](kind, phone, variables)
            log.status = SmsLog.Status.SENT
        except SmsRefused as error:
            log.status = SmsLog.Status.FAILED
            logger.error("SMS (%s) refused: %s", kind, error)
    log.save()
    SmsLog.objects.filter(created__lt=now - KEEP).delete()  # ponytail: purged here; a beat task if SMS grow


def queue_sms(kind, phone, variables, user=None):
    """Hand an SMS to the worker, within the limits per number, account and purpose (refusal, M2); if the broker cannot
    be reached, send it here and now (as ops.tasks.queue_email). Returns whether it went on its way: False while SMS
    are off (settings.SMS_ENABLED: a server without a real backend) or when a limit stops it, and then the page must
    not say that it was sent. The row is written first, so that requests at the same moment count each other."""
    if not settings.SMS_ENABLED:
        return False
    log = SmsLog.objects.create(
        kind=kind,
        phone_hash=phone_hash(phone),
        phone_last4=phone[-4:],
        user=user if getattr(user, "pk", None) else None,
        status=SmsLog.Status.QUEUED,
    )
    if reason := refusal(log):
        SmsLog.objects.filter(pk=log.pk).update(status=SmsLog.Status.CAPPED)
        logger.warning("SMS (%s) not sent: %s", kind, reason)
        return False
    try:
        send_sms.delay(kind, phone, variables, log.pk)
    except send_sms.OperationalError:
        logger.exception("broker unavailable, sending the SMS synchronously")
        try:
            send_sms.run(kind, phone, variables, log.pk)
        except Exception:
            logger.exception("the SMS could not be sent here either; dropped")
    return True


ORDER_SMS = {
    "confirmation": "order_placed",
    "shipped": "order_shipped",
    "delivered": "order_delivered",
    "out_for_delivery": "order_arriving",  # a courier's news (shipping/messages.py); SmsLog.kind: 20 characters
    "delivery_failed": "order_not_delivered",
}


def send_order_sms(order, kind):
    """For the shop's notifications (shop.services.notify, with its kinds) and a courier's news (shipping/messages.py):
    the kinds of ORDER_SMS send an SMS, other kinds nothing; and only to an account with a confirmed mobile number that
    asked for order updates by SMS on My account."""
    user = order.user
    if kind not in ORDER_SMS or not (user and user.login_phone_verified and user.sms_updates):
        return
    variables = {"var1": order.number}
    if kind == "shipped" and (shipment := order.shipments.first()):  # the latest
        variables["var2"] = f"{shipment.courier} {shipment.tracking_number}"[:30]
    elif kind == "out_for_delivery":
        variables["var2"] = f"{order.total.amount:.2f}"
    elif kind == "delivery_failed":
        variables["var2"] = order.token  # https://examleaf.in/orders/t/{#var#}/ in the template
    queue_sms(ORDER_SMS[kind], user.login_phone, variables, user=user)
