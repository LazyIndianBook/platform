"""Data protection duties as code (research section 4): the clocks of a data request, the erasure's dry run (what
DeletionRequest.complete erases, what stays and why, what stops it), the answer's text with the contact block, and the
masks staff see by default."""

import calendar
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import DataRequest

Kind = DataRequest.Kind


def add_month(when):
    """The same day a month later (the last day of a shorter month)."""
    year, month = (when.year + 1, 1) if when.month == 12 else (when.year, when.month + 1)
    return when.replace(year=year, month=month, day=min(when.day, calendar.monthrange(year, month)[1]))


def clocks(kind, received_at):
    """(acknowledge by, answer by) for a request received then. Acknowledged within STAFF_DATA_REQUEST_ACK_HOURS (48:
    the E-Commerce Rules); answered within one month (the SPDI Rules and the E-Commerce Rules) until the DPDP Rules'
    rights take effect (STAFF_DPDP_RULES_FROM, 13 May 2027), then within STAFF_DPDP_RESPONSE_DAYS (90, r.14(3)). A
    grievance or complaint keeps the E-Commerce Rules' month after that too: the strictest clock that applies."""
    ack = received_at + timedelta(hours=settings.STAFF_DATA_REQUEST_ACK_HOURS)
    month = add_month(received_at)
    if timezone.localdate(received_at) < settings.STAFF_DPDP_RULES_FROM:
        return ack, month
    due = received_at + timedelta(days=settings.STAFF_DPDP_RESPONSE_DAYS)
    return ack, min(due, month) if kind in (Kind.GRIEVANCE, Kind.COMPLAINT) else due


def mask_email(email):
    name, _, domain = (email or "").partition("@")
    return f"{name[:2]}•••@{domain}" if domain else ""


def mask_phone(phone):
    digits = "".join(char for char in str(phone or "") if char.isdigit())
    return f"••••••{digits[-4:]}" if len(digits) >= 4 else ""


def mask_ip(ip):
    """203.0.113.x; an IPv6 address to its first four groups."""
    if not ip:
        return ""
    if ":" in ip:
        return ":".join(ip.split(":")[:4]) + ":…"
    return ".".join(ip.split(".")[:3]) + ".x"


def financial_year_end(day):
    return day.replace(year=day.year + (day.month >= 4), month=3, day=31)


def erasure_report(user, data_request=None):
    """The dry run of an erasure (research 4.5): what DeletionRequest.complete would erase now, with counts; what stays,
    why and until when; and what stops it now (`blocks`). Nothing is changed."""
    from allauth.account.models import EmailAddress
    from axes.models import AccessAttempt

    from accounts.models import ConsentRecord, TeacherProfile
    from shop.models import Order, QuoteRequest, Refund, StockAlert

    from .models import AuditEvent

    erase = [
        ("profile", "name, email address, phones, date of birth, district, parent's details", 1),
        ("email_addresses", "email addresses", EmailAddress.objects.filter(user=user).count()),
        ("authenticators", "passkeys and authenticator apps", user.authenticator_set.count()),
        ("google_accounts", "Google accounts connected", user.socialaccount_set.count()),
        ("sessions", "signed-in devices", user.usersession_set.count()),
        ("teacher_profile", "teacher access request", TeacherProfile.objects.filter(user=user).count()),
        ("attempt_notes", "notes on saved marks", user.attempts.exclude(notes="").count()),
        ("answer_sheets", "answer sheets and their photos", user.answer_sheets.count()),
        ("addresses", "saved addresses", user.addresses.count()),
        ("reviews", "reviews", user.reviews.count()),
        (
            "stock_alerts",
            "'email me when it is back' requests",
            StockAlert.objects.filter(email__iexact=user.email).count(),
        ),
        ("sms", "the SMS log's rows", user.sms_messages.count()),
        (
            "failed_logins",
            "failed log-ins",
            AccessAttempt.objects.filter(username__in=[user.email, user.login_phone or user.email]).count(),
        ),
        ("roles", "roles and permissions", user.groups.count()),
    ]
    orders = Order.objects.filter(user=user)
    last_order = orders.exclude(placed_at=None).order_by("-placed_at").values_list("placed_at", flat=True).first()
    year_end = financial_year_end(timezone.localdate(last_order)) if last_order else None
    keep_orders_until = year_end.replace(year=year_end.year + 8) if year_end else None
    keep = [
        (
            "orders",
            "orders, invoices and credit notes, with the address copied into them",
            orders.count(),
            "tax records: 8 financial years (Companies Act s.128(5), CGST s.36)",
            keep_orders_until,
        ),
        (
            "consents",
            "consent records, without the address hash",
            ConsentRecord.objects.filter(user=user).count(),
            "proof of the notice and the consent (DPDP s.6(10))",
            None,
        ),
        ("attempts", "saved marks, as anonymous statistics", user.attempts.count(), "no personal data left", None),
        (
            "audit",
            "the staff's actions on the account",
            AuditEvent.objects.filter(target_type="accounts.user", target_id=str(user.pk)).count(),
            "the audit log: 2 years, money 8 financial years",
            None,
        ),
        (
            "quote_requests",
            "quotation requests made with the address",
            QuoteRequest.objects.filter(email__iexact=user.email).count(),
            "not erased by the purge: delete them by hand (RUNBOOK.md)",
            None,
        ),
    ]
    blocks = []
    if user.is_staff or user.is_superuser:
        blocks.append("A member of staff: offboard them first (people/<id>/offboard/).")
    if user.email.endswith("@deleted.invalid"):
        blocks.append("The account is erased already.")
    on_the_way = [Order.Status.PAID, Order.Status.PACKED, Order.Status.SHIPPED]
    if orders.filter(status__in=on_the_way).exists():
        blocks.append("An order is on its way: wait until it is delivered, cancelled or refunded.")
    if Refund.objects.filter(order__user=user, status=Refund.Status.PENDING).exists():
        blocks.append("A refund is under way: wait until it is done.")
    if data_request is not None and not data_request.identity_verified:
        blocks.append("The requester's identity is not verified yet.")
    if user.is_minor and not (data_request and data_request.details.get("parent_confirmed")):
        blocks.append("A student under 18: the parent or guardian must confirm the erasure (details.parent_confirmed).")
    notes = []
    if timezone.localdate() < settings.STAFF_DPDP_RULES_FROM:
        notes.append(
            f"From {settings.STAFF_DPDP_RULES_FROM:%d %B %Y} the logs of each processing (the SMS log, payment events) "
            "must be kept a year after it (DPDP Rules r.8(3)); the erasure deletes the SMS log's rows today."
        )
    return {
        "erase": [{"part": part, "what": what, "count": count} for part, what, count in erase],
        "keep": [
            {"part": part, "what": what, "count": count, "why": why, "until": until}
            for part, what, count, why, until in keep
        ],
        "blocks": blocks,
        "can_erase": not blocks,
        "notes": notes,
    }


RESPONSES = {
    Kind.ACCESS: "We attach a copy of the personal data we keep about the account, with the processors who handle it "
    "for us.",
    Kind.CORRECTION: "We have corrected the details as you asked.",
    Kind.ERASURE: "We have erased the account's personal data. Orders and invoices stay, as tax law requires, for "
    "eight financial years.",
    Kind.NOMINATION: "We have recorded the person you nominated to act for you in case of your death or incapacity.",
    Kind.GRIEVANCE: "We have looked into your grievance; what we found and did is below.",
    Kind.COMPLAINT: "We have looked into your complaint; what we found and did is below.",
}


def response_text(data_request):
    """The answer's subject and text for staff to complete and send, with the contact block (DPDP r.9)."""
    received = timezone.localtime(data_request.received_at)
    seller = settings.SHOP_SELLER
    body = (
        f"Hello,\n\nWe received your request ({data_request.get_kind_display()}) on {received:%d %B %Y}, reference "
        f"DR-{data_request.pk}.\n\n{RESPONSES[data_request.kind]}\n\n[What we did]\n\n"
        f"If you are not satisfied with this answer, write to our Grievance Officer: "
        f"{settings.DATA_PROTECTION_OFFICER}. Under the Digital Personal Data Protection Act, 2023 you may also "
        f"complain to the Data Protection Board of India once you have used this process.\n\n"
        f"{seller['name']}, {seller['address']}"
    )
    return {"subject": f"Your request DR-{data_request.pk} to ExamLeaf", "body": body}
