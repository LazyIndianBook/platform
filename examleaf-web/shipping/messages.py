"""Telling the customer about their parcel (research-integrations.md 3.7), through the shop's own emails and SMS:

    shipped           email (with the order's transition: shop.services.shipped) and SMS: courier, AWB, our order page
    out for delivery  SMS, cash on delivery only: keep ₹X ready
    delivered         email (shop.services.deliver_order) and SMS, as when staff mark it delivered
    delivery failed   email and SMS, with the link to the order's page
    returning         email

Emails go to the order's address; the email suppression list applies (Anymail's pre_send, ops.models). SMS go only to
an account with a confirmed number that asked for order updates (ops.sms.send_order_sms), only for a kind whose DLT
template is registered (MSG91_TEMPLATE_<KIND>), and never from 21:00 to 08:00 India time: one waits on the parcel for
the morning (tasks.send_held_messages) and goes then only if it is still true. No marketing in any of them."""

from datetime import time

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ops.sms import ORDER_SMS, send_order_sms
from shop.services import notify

from .models import ShipmentDetail

QUIET_FROM, QUIET_UNTIL = time(21, 0), time(8, 0)
EMAILS = {"delivery_failed", "returning"}  # shipped and delivered are the order's transitions' own
TEXTS = {"shipped", "out_for_delivery", "delivered", "delivery_failed"}


def quiet(now=None):
    """Whether it is too late or too early for an SMS (India time)."""
    hour = timezone.localtime(now).time()
    return hour >= QUIET_FROM or hour < QUIET_UNTIL


def sms_wanted(order, kind):
    user = order.user
    if kind not in TEXTS or (kind == "out_for_delivery" and not order.is_cod):
        return False
    if not (user and user.login_phone_verified and user.sms_updates):
        return False
    return settings.SMS_BACKEND != "msg91" or bool(settings.MSG91_TEMPLATES.get(ORDER_SMS[kind]))


def tell(shipment, kind, now=None):
    """The customer told of `kind` (above): the email at once, the SMS now or in the morning, WhatsApp (a hook)."""
    order = shipment.order
    if kind in EMAILS:
        notify(order, kind, sms=False, shipment=shipment)
    if sms_wanted(order, kind):
        if quiet(now):
            ShipmentDetail.objects.filter(shipment=shipment).update(sms_held=kind)
        else:
            transaction.on_commit(lambda: send_order_sms(order, kind), robust=True)
    notify_whatsapp(shipment, kind)


def send_held(detail):
    """In the morning: the SMS held through the night, if what it says is still true (out for delivery never is).
    Taken off the parcel before it goes, by this run alone: a second run finds nothing to send."""
    kind = detail.sms_held
    still = {
        "shipped": detail.has_left,
        "delivered": detail.status == "delivered",
        "delivery_failed": detail.status == "delivery_failed",
    }
    if not ShipmentDetail.objects.filter(pk=detail.pk, sms_held=kind).update(sms_held="", modified=timezone.now()):
        return False  # another run took it
    detail.sms_held = ""
    if still.get(kind) and sms_wanted(detail.shipment.order, kind):
        send_order_sms(detail.shipment.order, kind)
        return True
    return False


def notify_whatsapp(shipment, kind):
    """A hook, not built: the same news as WhatsApp utility templates.

    TODO(WhatsApp, research 4.2 and decision 6.1.4): send MSG91's WhatsApp utility template for `kind` (never a
    marketing one) to the account's confirmed number, only while that number has a WhatsApp opt-in of its own: a
    ConsentRecord (accounts.models) with the purpose "order updates on WhatsApp", given and not withdrawn since,
    which does not exist yet; within the same quiet hours, and logged as the SMS are (ops.models.SmsLog)."""
    return None
