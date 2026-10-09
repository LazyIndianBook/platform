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

from examleaf import retention
from examleaf.bulkhead import Bulkhead

from .models import SmsLog

logger = logging.getLogger(__name__)
MSG91 = "https://control.msg91.com/api/v5/"
TIMEOUT = httpx.Timeout(10, connect=3)  # seconds: 3 to connect, 10 for each read or write (retries: send_sms)
# MSG91's calls (made in a request only while the queue is down) share the providers' half of a process's threads
# (examleaf/bulkhead.py): over it, a call fails at once, as MSG91 unreachable.
CALLS = Bulkhead(httpx.ConnectError, "Half of this process's threads are waiting on providers already")
KEEP = timedelta(days=retention.rule("sms_log").keep_days)  # SmsLog rows (the nightly ops.tasks.purge_expired)
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


def console(kind, phone, variables, template=""):
    print(f"SMS {kind}{f' (template {template})' if template else ''} to {phone}: {variables}", flush=True)
    return ""


def authkey():
    """MSG91's authkey in force: the environment's (MSG91_AUTHKEY) until the panel holds one (replaced on the
    connections page; integrations/README.md "Precedence"), then the enabled account's ("" while none is: refused)."""
    from integrations.services import panel_keys

    panel = panel_keys("msg91")
    if panel is None:
        return settings.MSG91_AUTHKEY
    return (panel.get("credentials") or {}).get("authkey", "")


def template_id(kind, language="en"):
    """The MSG91 template id an SMS kind is sent with: the template registry's approved one (ops.MessageTemplate) when
    there is one, the environment's MSG91_TEMPLATE_<KIND> otherwise; "" when neither (the kind is not sent)."""
    from .models import MessageTemplate

    found = (
        MessageTemplate.objects.filter(
            event=kind,
            channel=MessageTemplate.Channel.SMS,
            language=language,
            approval_state=MessageTemplate.Approval.APPROVED,
        )
        .exclude(msg91_id="")
        .values_list("msg91_id", flat=True)
        .first()
    )
    return found or settings.MSG91_TEMPLATES.get(kind, "")


def mark_used(kind, template):
    """The registry's row of a template just sent: its last use (DLT deactivates a template unused for 90 days)."""
    from .models import MessageTemplate

    rows = MessageTemplate.objects.filter(event=kind, channel=MessageTemplate.Channel.SMS, msg91_id=template)
    rows.update(last_used_at=timezone.now())


def msg91(kind, phone, variables, template=""):
    """MSG91's OTP API for codes (allauth makes the code, MSG91 only delivers it) and its Flow API for the rest, with
    the kind's template id (template_id: the registry's, else MSG91_TEMPLATE_<KIND>) or the one given (a test send of a
    template from the panel). Returns MSG91's request id. HTTP 200 without "type": "success" is a refusal too."""
    headers, mobile = {"authkey": authkey()}, phone.removeprefix("+")
    template = template or template_id(kind)
    with CALLS:
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
    mark_used(kind, template)
    return str(data.get("request_id") or data.get("message") or "")[:100]


BACKENDS = {"console": console, "msg91": msg91}


@shared_task(autoretry_for=(httpx.TransportError,), retry_backoff=10, max_retries=3)
def send_sms(kind, phone, variables, log_id=None, template=""):
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
            chosen = {"template": template} if template else {}  # a test send's template (the registry's page)
            log.provider_id = BACKENDS[settings.SMS_BACKEND](kind, phone, variables, **chosen)
            log.status = SmsLog.Status.SENT
        except SmsRefused as error:
            log.status = SmsLog.Status.FAILED
            logger.error("SMS (%s) refused: %s", kind, error)
    log.save()


def queue_sms(kind, phone, variables, user=None, template=""):
    """Hand an SMS to the worker, within the limits per number, account and purpose (refusal, M2); if the broker cannot
    be reached, send it here and now (as ops.tasks.queue_email). Returns whether it went on its way: False while SMS
    are off (settings.SMS_ENABLED: a server without a real backend) or when a limit stops it, and then the page must
    not say that it was sent. The row is written first, so that requests at the same moment count each other.
    `template`: an MSG91 template id to send with instead of the kind's (a test send from the template registry)."""
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
    chosen = {"template": template} if template else {}
    try:
        send_sms.delay(kind, phone, variables, log.pk, **chosen)
    except send_sms.OperationalError:
        logger.exception("broker unavailable, sending the SMS synchronously")
        try:
            send_sms.run(kind, phone, variables, log.pk, **chosen)
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
