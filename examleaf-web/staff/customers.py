"""The Customers module's logic (plan 5.4; staff/README.md "Customers", API.md "Customers (staff)"): how a customers'
search is read (and which of it is a lookup of a person), the list's tabs (students, parents, guest buyers), a
person's merged timeline and commerce summary, the children waiting for a parent, a parent's consent recorded by hand,
and the account actions that a bulk job runs (user.suspend, user.unsuspend, user.end_sessions, user.resend_consent:
approvals Actions, named by bulk actions only). staff/customers_api.py draws them as endpoints.

Rules kept here: every queryset of customer-related rows goes through `scoped()`; a part of the timeline is shown only
to a reader who may see its records (the rest is named in `withheld`); a child's timeline carries a usage summary of
the course, never a trail of behaviour; test-mode orders stay out of every row and number on a live site; personal
data never goes into an audit event, a label or an error: accounts are named by their number, orders by theirs."""

import re
from datetime import datetime, time, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import NamedTuple

from allauth.account.models import EmailAddress
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Count, DateTimeField, Exists, Max, Min, OuterRef, Q, Sum
from django.db.models.functions import Coalesce, Lower, TruncWeek
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.text import Truncator
from rest_framework import exceptions, serializers

from accounts.audiences import adult_born_by
from accounts.forms import normalise_phone
from accounts.models import ConsentRecord, DeletionRequest
from accounts.views import PARENT_LINK_DAYS, PARENT_LINKS_PER_DAY, shown_name

from . import audit, services
from .approvals import Action, Refused
from .backends import scoped
from .config import site_setting
from .models import AuditEvent, Note

User = get_user_model()

KINDS = [  # the list's tabs: ?kind=
    ("students", "accounts with a class level, or a student under 18"),
    ("parents", "adult accounts a student named as their parent's contact"),
    ("guests", "buyers without an account, by the email address of their orders"),
]
TIMELINE_ROWS = 200  # the newest rows of an answer; ?before= asks for the older ones
GUEST_PREVIEW_LIMIT = 1000  # a lookup counts what it found up to this many
ERASED = "@deleted.invalid"  # an erased account's address ends so (accounts.models.forget_registration)
WEEKS = 26  # an adult's clip completions by week: this many weeks back at most
METHODS = [  # how a parent's consent was verified by hand: the methods of Rule 10 (accounts.ConsentRecord.Method)
    ConsentRecord.Method.STAFF_MANUAL,
    ConsentRecord.Method.ADULT_ACCOUNT,
    ConsentRecord.Method.DIGILOCKER,
]


def plural(count, one, many):
    return f"{count:,} {one if count == 1 else many}"


def rupees(value):
    """A money value as text in rupees: its amount to the paisa."""
    return str(Decimal(getattr(value, "amount", value) or 0).quantize(Decimal("0.01")))


def amount(value):
    return Decimal(getattr(value, "amount", value) or 0)


# ---- What was typed in the search box ----


def classify(value):
    """(kind, query) of a customers' search: "email" (an address, exactly), "phone" (a mobile number in any Indian
    format, or its last digits: 4 or more), "name" (three letters or more), else "none": too little to look anyone up
    (nothing is found, and it is no lookup). The query comes back as it is matched."""
    value = " ".join(str(value or "").split())[:100]
    if "@" in value:
        return "email", value.lower()
    if phone := normalise_phone(value):
        return "phone", phone
    digits = re.sub(r"\D", "", value)
    if len(digits) >= 4 and re.fullmatch(r"[\d\s+()-]+", value):
        return "phone", digits[-10:]  # the last digits of a number (a full number was found above)
    return ("name", value) if len(value) >= 3 else ("none", value)


def search(queryset, kind, query):
    """The accounts a classified query finds (queryset of accounts)."""
    if kind == "email":
        return queryset.filter(email__iexact=query)
    if kind == "phone":
        if query.startswith("+"):
            return queryset.filter(Q(login_phone=query) | Q(phone=query))
        return queryset.filter(Q(login_phone__endswith=query) | Q(phone__endswith=query))
    if kind == "name":
        return queryset.filter(full_name__icontains=query)
    return queryset.none()


# ---- The tabs ----


def students(queryset, today=None):
    """Accounts with a class level, or a student under 18 by their date of birth."""
    return queryset.filter(Q(class_level__isnull=False) | Q(date_of_birth__gt=adult_born_by(today)))


def parents(queryset, today=None):
    """Adult accounts a student named as their parent's contact: the account's verified email address, or its
    verified log-in number, is the contact on a student's record. A parent's link goes to a contact, not to an account
    (accounts.views.send_parent_link), so this finds the parents who also have an account: others are known only as
    the contact on their child's record. Who is named is not proof of parenthood."""
    named = User.objects.filter(is_staff=False).exclude(parent_contact="").exclude(email__endswith=ERASED)
    contacts = named.values("parent_contact")
    by_email = EmailAddress.objects.alias(lowered=Lower("email")).filter(
        user=OuterRef("pk"), verified=True, lowered__in=contacts
    )
    adult = Q(date_of_birth__isnull=True) | Q(date_of_birth__lte=adult_born_by(today))
    by_number = Q(login_phone_verified=True, login_phone__in=contacts)
    return queryset.alias(named_by_email=Exists(by_email)).filter(adult, Q(named_by_email=True) | by_number)


def guest_orders(reader):
    """The orders of people without an account that the reader may see: live ones on a live site, and those that
    still carry an email address (an order past its books' period lost its customer's details)."""
    from shop.models import Order, live_mode

    orders = scoped(Order.objects.filter(user__isnull=True), reader, "shop.view_order").filter(email__contains="@")
    return orders.filter(livemode=True) if live_mode() else orders


def guests(orders, kind="", query=""):
    """One order per guest, their newest (its id the row's), of the orders a lookup finds: the guests as the list
    shows them. A guest is an email address (in any case)."""
    if kind == "email":
        orders = orders.filter(email__iexact=query)
    elif kind == "phone":
        orders = orders.filter(shipping_address__phone__endswith=query[-10:])
    elif kind == "name":
        orders = orders.filter(shipping_address__name__icontains=query)
    elif kind == "none":
        orders = orders.none()
    newest = orders.annotate(who=Lower("email")).values("who").annotate(last=Max("pk")).values("last")
    return orders.filter(pk__in=newest)


def guest_counts(base, rows):
    """{lower-case email: how many orders} for the guests on a page, in one query over all their orders."""
    emails = {row.email.lower() for row in rows}
    counted = base.annotate(who=Lower("email")).filter(who__in=emails).values("who").annotate(n=Count("pk"))
    return {row["who"]: row["n"] for row in counted.order_by()}


# ---- The timeline ----


class Row(NamedTuple):
    at: datetime
    kind: str
    key: int  # the source row's id: with `at` and `kind`, the row's place in the order
    label: str
    href: str | None


HREFS = {  # the console's pages (examleaf-admin): the answer says where to look, the console draws the link
    "order": "/orders/{number}/",
    "ticket": "/support/tickets/{number}/",
    "learner": "/course/learners/{user}/",
}
KIND_NAMES = [  # the order of the parts, and the kinds a timeline can be narrowed to (?kind=)
    "order",
    "payment",
    "refund",
    "code",
    "access",
    "course",
    "ticket",
    "sms",
    "email",
    "consent",
    "note",
    "staff",
]
PARTS = {  # the permission that lets a reader see each part (its records' own view_ permission)
    "order": "shop.view_order",
    "payment": "shop.view_payment",
    "refund": "shop.view_refund",
    "code": "learn.view_bookcode",
    "access": "learn.view_entitlement",
    "course": "learn.view_entitlement",
    "ticket": "support.view_ticket",
    "sms": "ops.view_smslog",
    "email": "shop.view_order",
    "consent": "accounts.view_consentrecord",
    "note": "staff.view_note",
    "staff": "staff.view_auditlog",
}


def cursor_of(row):
    """Where a page ends: the row's time (to the microsecond), kind and id, so that rows of one instant are neither
    skipped nor shown twice at the page's edge."""
    return f"{row.at.isoformat(timespec='microseconds')}|{row.kind}|{row.key}"


def parse_cursor(text):
    """(time, kind, id) from `?before=` (an answer's next_before, or just a time: strictly before it), else 400."""
    if not text:
        return None
    when, _, rest = str(text).partition("|")
    moment = parse_datetime(when)
    kind, _, key = rest.partition("|")
    if moment is None or timezone.is_naive(moment) or (rest and not (kind in KIND_NAMES and key.isdigit())):
        raise serializers.ValidationError(
            {"before": ["A time with its offset, or the next_before of the last answer."]}
        )
    return (moment, kind, int(key)) if rest else (moment, "", -1)


def week_start(moment):
    """The Monday (India) of the week a moment is in, at its midnight."""
    local = timezone.localtime(moment)
    return timezone.make_aware(datetime.combine(local.date() - timedelta(days=local.weekday()), time.min))


def words(day):
    return f"{day.day} {day:%B %Y}"


def order_rows(ctx):
    rows = ctx.orders.annotate(moment=Coalesce("placed_at", "created", output_field=DateTimeField()))
    if ctx.upto:
        rows = rows.filter(moment__lte=ctx.upto)
    return [
        Row(
            order.moment,
            "order",
            order.pk,
            f"Order {order.number}: {order.status_label}, ₹{rupees(order.total)}",
            HREFS["order"].format(number=order.number),
        )
        for order in rows.order_by("-moment", "-pk")[: ctx.limit]
    ]


def payment_rows(ctx):
    from shop.models import Payment

    rows = Payment.objects.filter(order__in=ctx.orders).select_related("order")
    if ctx.upto:
        rows = rows.filter(created__lte=ctx.upto)
    return [
        Row(
            payment.created,
            "payment",
            payment.pk,
            f"Payment of ₹{rupees(payment.amount)} for order {payment.order.number} "
            f"({payment.get_method_display()}): {payment.get_status_display()}",
            HREFS["order"].format(number=payment.order.number),
        )
        for payment in rows.order_by("-created", "-pk")[: ctx.limit]
    ]


def refund_rows(ctx):
    from shop.models import Refund

    rows = Refund.objects.filter(order__in=ctx.orders).select_related("order")
    if ctx.upto:
        rows = rows.filter(created__lte=ctx.upto)
    return [
        Row(
            refund.created,
            "refund",
            refund.pk,
            f"Refund of ₹{rupees(refund.amount)} for order {refund.order.number} "
            f"({refund.get_method_display()}): {refund.get_status_display()}",
            HREFS["order"].format(number=refund.order.number),
        )
        for refund in rows.order_by("-created", "-pk")[: ctx.limit]
    ]


def code_rows(ctx):
    from learn.models import BookCode

    rows = scoped(
        BookCode.objects.filter(redeemed_by=ctx.user, redeemed_at__isnull=False), ctx.reader, PARTS["code"]
    ).select_related("subject")
    if ctx.upto:
        rows = rows.filter(redeemed_at__lte=ctx.upto)
    return [
        Row(
            code.redeemed_at,
            "code",
            code.pk,
            f"Book code redeemed: batch {code.batch} ({code.subject.name if code.subject_id else 'every subject'})",
            HREFS["learner"].format(user=ctx.user.pk),
        )
        for code in rows.order_by("-redeemed_at", "-pk")[: ctx.limit]
    ]


def access_rows(ctx):
    from learn.models import Entitlement

    rows = scoped(Entitlement.objects.filter(user=ctx.user), ctx.reader, PARTS["access"]).select_related("subject")
    if ctx.upto:
        rows = rows.filter(created__lte=ctx.upto)
    result = []
    for access in rows.order_by("-created", "-pk")[: ctx.limit]:
        until = f", until {words(access.valid_until)}" if access.valid_until else ""
        subject = access.subject.name if access.subject_id else "every subject"
        result.append(
            Row(
                access.created,
                "access",
                access.pk,
                f"Course access opened ({access.get_source_display()}): {subject}{until}",
                HREFS["learner"].format(user=ctx.user.pk),
            )
        )
    return result


def course_rows(ctx):
    """The course in use, in counts: a student under 18's (or of an age not known) is one row (the chapters opened so
    far, and the last week they were active: no clip, no quiz answer, no day); a known adult's adds the clips completed
    in each of the last WEEKS weeks. Nothing here says what a child watched or when."""
    from learn.models import CardReview, Progress, QuizAttempt

    user = ctx.user
    chapters = Progress.objects.filter(user=user).values_list("clip__revision__chapter_id")
    chapters = chapters.union(
        QuizAttempt.objects.filter(user=user).values_list("item__chapter_id"),
        CardReview.objects.filter(user=user).values_list("card__chapter_id"),
    )
    opened = chapters.count()
    latest = [
        Progress.objects.filter(user=user).aggregate(at=Max("updated"))["at"],
        QuizAttempt.objects.filter(user=user).aggregate(at=Max("created"))["at"],
        CardReview.objects.filter(user=user).aggregate(at=Max("created"))["at"],
    ]
    latest = max((moment for moment in latest if moment), default=None)
    if not opened and latest is None:
        return []
    href = HREFS["learner"].format(user=user.pk)
    rows = []
    if latest is not None:
        week = week_start(latest)
        label = f"Course use so far: {plural(opened, 'chapter', 'chapters')} opened; "
        rows.append(Row(week, "course", 0, label + f"last active in the week of {words(week)}", href))
    if ctx.weekly:
        weekly = (
            Progress.objects.filter(user=user, completed=True)
            .annotate(week=TruncWeek("updated"))
            .values("week")
            .annotate(n=Count("pk"))
            .order_by("-week")[:WEEKS]
        )
        for each in weekly:
            label = f"Week of {words(each['week'])}: {plural(each['n'], 'clip', 'clips')} completed"
            rows.append(Row(each["week"], "course", each["week"].toordinal(), label, href))
    return [row for row in rows if not ctx.upto or row.at <= ctx.upto]


def ticket_rows(ctx):
    from shop.models import live_mode
    from support.models import Ticket

    rows = scoped(Ticket.objects.filter(user=ctx.user), ctx.reader, PARTS["ticket"]).exclude(status=Ticket.Status.SPAM)
    if live_mode():
        rows = rows.exclude(order__livemode=False)  # a test order's tickets stay out on a live site
    if ctx.upto:
        rows = rows.filter(received_at__lte=ctx.upto)
    return [
        Row(
            ticket.received_at,
            "ticket",
            ticket.pk,
            f"Ticket {ticket.number}: {ticket.get_category_display() or 'not sorted yet'}, "
            f"{ticket.get_status_display()}",
            HREFS["ticket"].format(number=ticket.number),
        )
        for ticket in rows.order_by("-received_at", "-pk")[: ctx.limit]
    ]


def sms_rows(ctx):
    from ops.models import SmsLog

    rows = SmsLog.objects.filter(user=ctx.user)
    if ctx.upto:
        rows = rows.filter(created__lte=ctx.upto)
    result = []
    for sms in rows.order_by("-created", "-pk")[: ctx.limit]:
        report = f", {sms.get_delivery_display()}" if sms.delivery else ""
        result.append(
            Row(
                sms.created,
                "sms",
                sms.pk,
                f"SMS ({sms.kind.replace('_', ' ')}): {sms.get_status_display()}{report}",
                None,
            )
        )
    return result


def email_rows(ctx):
    from shop.models import OrderMessage

    rows = OrderMessage.objects.filter(order__in=ctx.orders, email=True).select_related("order")
    if ctx.upto:
        rows = rows.filter(created__lte=ctx.upto)
    return [
        Row(
            message.created,
            "email",
            message.pk,
            f"Email about order {message.order.number}: {message.kind.replace('_', ' ')}",
            HREFS["order"].format(number=message.order.number),
        )
        for message in rows.order_by("-created", "-pk")[: ctx.limit]
    ]


def consent_rows(ctx):
    rows = ConsentRecord.objects.filter(user=ctx.user)
    if ctx.upto:
        rows = rows.filter(created__lte=ctx.upto)
    result = []
    for consent in rows.order_by("-created", "-pk")[: ctx.limit]:
        marketing = consent.purpose == ConsentRecord.Purpose.MARKETING
        what = f"Consent {consent.event}" + (
            f" for marketing{f' ({consent.get_channel_display()})' if consent.channel else ''}" if marketing else ""
        )
        who = "by the parent" if consent.by_parent else "by the student"
        how = consent.get_method_display()
        if consent.verified_by_id:
            how += f"; evidence: {consent.evidence_ref or 'none given'}"
        notice = f"; privacy notice {consent.notice_version}" if consent.notice_version else ""
        result.append(Row(consent.created, "consent", consent.pk, f"{what} {who} ({how}){notice}", None))
    return result


def note_rows(ctx):
    rows = Note.objects.filter(target_type="accounts.user", target_id=str(ctx.user.pk)).select_related("author")
    if ctx.upto:
        rows = rows.filter(created__lte=ctx.upto)
    return [
        Row(
            note.created,
            "note",
            note.pk,
            f"Note by {note.author.full_name or note.author.email}: {Truncator(note.body).chars(200)}",
            None,
        )
        for note in rows.order_by("-created", "-pk")[: ctx.limit]
    ]


SENSITIVE = {  # what a sensitive_read event opened, in words
    "record": "Record opened",
    "reveal": "Contact details revealed",
    "timeline": "Timeline opened",
    "commerce": "Commerce summary opened",
    "nominee": "Nominee read",
}
STAFF_WORDS = {  # the staff actions on an account, in words (the rest: the action's own name)
    "user.suspended": "Account suspended",
    "user.unsuspended": "Suspension lifted",
    "user.unlocked": "Sign-in unlocked",
    "user.verification_resent": "Parent's link sent again",
    "user.consent_verified": "Parent's consent recorded by hand",
    "user.password_reset_started": "Password reset link sent",
    "user.impersonation_started": "Signed in to the website as them",
    "user.impersonation_ended": "Signed-in session ended",
    "session_ended_by_staff": "Signed out everywhere",
    "user.reset_mfa.executed": "Two-step sign-in reset",
}


def staff_rows(ctx):
    """The audit log's events about the account, for whoever reads the log (reading it is itself an event: the view
    writes `audit.read`). The log names people by number: staff here by their names, anyone else by their kind."""
    events = AuditEvent.objects.filter(target_type="accounts.user", target_id=str(ctx.user.pk))
    events = events.exclude(action__in=["note.created", "audit.read"])
    if ctx.upto:
        events = events.filter(ts__lte=ctx.upto)
    events = list(events.order_by("-ts", "-id")[: ctx.limit])
    people = User.objects.filter(pk__in={event.actor_id for event in events if event.actor_id})
    names = {person.pk: person.full_name or person.email for person in people}
    result = []
    for event in events:
        if event.action == "sensitive_read":
            what = SENSITIVE.get((event.details or {}).get("what"), "A detail read")
        else:
            what = STAFF_WORDS.get(event.action) or event.action.replace("_", " ").replace(".", ": ")
        by = names.get(event.actor_id) if event.actor_type == "staff" else None
        by = by or {"user": "the customer", "service": "an integration"}.get(event.actor_type, "the site")
        why = f": {event.reason}" if event.reason else ""
        result.append(Row(event.ts, "staff", event.pk, f"{what} by {by}{why}", None))
    return result


SOURCES = {
    "order": order_rows,
    "payment": payment_rows,
    "refund": refund_rows,
    "code": code_rows,
    "access": access_rows,
    "course": course_rows,
    "ticket": ticket_rows,
    "sms": sms_rows,
    "email": email_rows,
    "consent": consent_rows,
    "note": note_rows,
    "staff": staff_rows,
}


def customer_orders(reader, user):
    """The customer's orders the reader may see: live ones on a live site (test-mode orders belong under the TEST
    band, in the Orders list with ?livemode=false)."""
    from shop.models import Order, live_mode

    orders = scoped(Order.objects.filter(user=user), reader, "shop.view_order")
    return orders.filter(livemode=True) if live_mode() else orders


def timeline(reader, user, *, kinds=None, before=None, request=None):
    """One account's story, newest first: {"child", "rows" (at most TIMELINE_ROWS: at, kind, label, href),
    "next_before" (pass it as ?before= for the older ones, else null), "withheld" (the parts the reader's permissions
    leave out)}. Each part is one query however many rows it holds (the newest TIMELINE_ROWS + 1 of it); `kinds`
    narrows the answer to some of them. Reading the audit log's part is itself an event (`audit.read`)."""
    wanted = [kind for kind in KIND_NAMES if not kinds or kind in kinds]
    cursor = parse_cursor(before)
    ctx = SimpleNamespace(
        reader=reader,
        user=user,
        child=user.is_minor,
        weekly=user.date_of_birth is not None and not user.is_minor,  # an age not known is taken for a child's
        limit=TIMELINE_ROWS + 1,
        upto=cursor[0] if cursor else None,
        orders=customer_orders(reader, user),
    )
    rows, withheld = [], []
    for kind in wanted:
        if not reader.has_perm(PARTS[kind]):
            withheld.append(kind)
            continue
        rows += SOURCES[kind](ctx)
        if kind == "staff":
            audit.record("audit.read", request=request, target=user, details={"what": "customer timeline"})
    if cursor:  # the rows at the instant the page ended: only those after it in the order
        rows = [row for row in rows if (row.at, row.kind, row.key) < cursor]
    rows.sort(key=lambda row: (row.at, row.kind, row.key), reverse=True)
    more = len(rows) > TIMELINE_ROWS
    rows = rows[:TIMELINE_ROWS]
    return {
        "child": ctx.child,
        "rows": [{"at": row.at, "kind": row.kind, "label": row.label, "href": row.href} for row in rows],
        "next_before": cursor_of(rows[-1]) if more else None,
        "withheld": withheld,
    }


# ---- The commerce summary ----


def commerce(reader, user):
    """What the customer bought: counts for everyone, and for an adult the money (spent, refunded, the lifetime value
    so far, the average order), the places they ordered to (masked), the tags of their orders and the parcels that came
    back. A student under 18: the counts only. Live orders only on a live site. An order counts once it is placed (paid
    online, or placed with cash on delivery) and not cancelled; a refund counts against the order it was made on."""
    from shipping.models import ShipmentDetail
    from shop.models import Address, Order, Refund, ReturnRequest

    orders = customer_orders(reader, user)
    kept = Q(placed_at__isnull=False) & ~Q(status=Order.Status.CANCELLED)
    counted = orders.aggregate(
        orders=Count("pk"),
        kept=Count("pk", filter=kept),
        cancelled=Count("pk", filter=Q(status=Order.Status.CANCELLED)),
    )
    child = user.is_minor
    result = {
        "child": child,
        **counted,
        "returns": ReturnRequest.objects.filter(order__in=orders).count(),
        "rtos": ShipmentDetail.objects.filter(shipment__order__in=orders, status="returned").count(),
        "spent": None,
        "refunded": None,
        "lifetime_value": None,
        "average_order": None,
        "first_order_at": None,
        "last_order_at": None,
        "addresses": None,
        "tags": None,
    }
    if child:
        return result
    kept_orders = orders.filter(kept)
    sums = kept_orders.aggregate(spent=Sum("total"), first=Min("placed_at"), last=Max("placed_at"))
    spent = amount(sums["spent"])
    refunded = amount(
        Refund.objects.filter(order__in=kept_orders, status=Refund.Status.PROCESSED).aggregate(total=Sum("amount"))[
            "total"
        ]
    )
    from taggit.models import TaggedItem

    tagged = (
        TaggedItem.objects.filter(
            content_type=ContentType.objects.get_for_model(Order), object_id__in=kept_orders.values("pk")
        )
        .values("tag__name")
        .annotate(n=Count("object_id"))
        .order_by("-n", "tag__name")[:20]
    )
    from staff.privacy import mask_phone

    result |= {
        "spent": rupees(spent),
        "refunded": rupees(refunded),
        "lifetime_value": rupees(spent - refunded),
        "average_order": rupees(spent / counted["kept"]) if counted["kept"] else None,
        "first_order_at": sums["first"],
        "last_order_at": sums["last"],
        "addresses": [
            {
                "city": address.city,
                "district": address.district,
                "state": address.state,
                "pin": address.pin,
                "phone": mask_phone(str(address.phone)),
                "is_default": address.is_default,
            }
            for address in Address.objects.filter(user=user)[:10]
        ],
        "tags": [{"name": row["tag__name"], "orders": row["n"]} for row in tagged],
    }
    return result


# ---- The children waiting for a parent ----


def waiting_children(today=None):
    """Active students under 18 with no consent a parent verified, and no deletion of their own under way (that is
    waiting for the parent too, and the cockpit lists it apart). While PARENTAL_CONSENT_MODE is "verified" their
    accounts read only; in "declared" they are the ones the switch will catch."""
    verified = ConsentRecord.objects.filter(event=ConsentRecord.Event.GIVEN, verified_at__isnull=False).values("user")
    leaving = DeletionRequest.objects.filter(status=DeletionRequest.Status.PENDING).values("user")
    children = User.objects.filter(is_staff=False, is_superuser=False, is_active=True)
    children = children.filter(date_of_birth__gt=adult_born_by(today))
    return children.exclude(pk__in=verified).exclude(pk__in=leaving)


def with_links(queryset):
    """The children with their links: how many were sent, the last one's time, how many today (India's day)."""
    midnight = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    return queryset.annotate(
        links=Count("parent_links"),
        last_link=Max("parent_links__sent_at"),
        links_today=Count("parent_links", filter=Q(parent_links__sent_at__gte=midnight)),
    )


def link_expires_at(last_link):
    return last_link + timedelta(days=PARENT_LINK_DAYS) if last_link else None


def parent_link(user):
    """A student under 18's consent link as the record shows it: how many went, the last one's time and when it stops
    working, how many today; None for anyone else (and for a student who named no parent)."""
    if not user.is_minor or not user.parent_contact:
        return None
    midnight = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    sums = user.parent_links.aggregate(
        sent=Count("pk"), last=Max("sent_at"), today=Count("pk", filter=Q(sent_at__gte=midnight))
    )
    expires = link_expires_at(sums["last"])
    return {
        "sent": sums["sent"],
        "last_at": sums["last"],
        "expires_at": expires,
        "expired": bool(expires and expires <= timezone.now()),
        "today": sums["today"],
        "daily_limit": DAILY_LINKS,
    }


def linked_accounts(reader, user, limit=10):
    """The accounts a student's parent contact points to (their parent's own, when it has one), or for an adult the
    students who named them: {id, full_name, relation}, in the reader's reach. Named by a verified email address or
    log-in number only; being named is not proof of parenthood."""
    accounts = scoped(
        User.objects.filter(is_staff=False, is_superuser=False).exclude(pk=user.pk), reader, "accounts.view_user"
    ).exclude(email__endswith=ERASED)
    if user.is_minor:
        contact = user.parent_contact
        if not contact:
            return []
        if "@" in contact:
            named = EmailAddress.objects.alias(lowered=Lower("email")).filter(
                user=OuterRef("pk"), verified=True, lowered=contact.lower()
            )
            rows = accounts.alias(named=Exists(named)).filter(named=True)
        else:
            rows = accounts.filter(login_phone=contact, login_phone_verified=True)
        rows, relation = rows.exclude(date_of_birth__gt=adult_born_by()), "parent"
    else:
        names = [address.email.lower() for address in user.emailaddress_set.all() if address.verified]
        if user.login_phone_verified and user.login_phone:
            names.append(user.login_phone)
        rows, relation = accounts.filter(parent_contact__in=names, date_of_birth__gt=adult_born_by()), "child"
    return [{"id": row.pk, "full_name": row.full_name, "relation": relation} for row in rows.order_by("pk")[:limit]]


def blocking():
    """Whether a student's account reads only until a parent confirms (PARENTAL_CONSENT_MODE "verified")."""
    return site_setting("PARENTAL_CONSENT_MODE") == "verified"


DAILY_LINKS = PARENT_LINKS_PER_DAY  # a parent's address or number gets this many links a day, whichever students ask


# ---- A parent's consent recorded by hand ----

PHONE_LIKE = re.compile(r"(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}")


def evidence_problem(reference):
    """Why a reference to the evidence is not one, or None: it says where the evidence is (a ticket's number, a
    letter's date), never the document and never a contact."""
    if "@" in reference or PHONE_LIKE.search(reference):
        return "Say where the evidence is (a ticket's number, a letter's date), not a contact's details."
    return None


def erased(user):
    return user.email.endswith(ERASED)


def verify_consent(staff, user_id, *, method, evidence_ref, reason, request=None):
    """A student under 18's parental consent recorded by hand (staff.verify_consent): a verified consent of the method
    given (staff_manual: staff checked; adult_account: the parent's own verified adult account; digilocker: a token),
    with `verified_by` and where the evidence is. The account's row is locked, and what stops it is checked again
    under the lock (a second member of staff, or the parent's link, was first): ValidationError with the reason.
    The parent is told by email when their contact is one (a mobile number: no text is registered with DLT for it).
    Returns the new ConsentRecord."""
    with transaction.atomic():
        accounts = scoped(User.objects.filter(is_staff=False, is_superuser=False), staff, "accounts.view_user")
        user = accounts.select_for_update().filter(pk=user_id).first()
        if user is None:
            raise exceptions.NotFound()
        problem = None
        if erased(user):
            problem = "This account was erased."
        elif not user.is_minor:
            problem = "Not a student under 18: no parent's consent is needed."
        elif user.pending_deletion is not None:
            problem = "The student asked to delete the account: the parent confirms that, not their consent."
        elif ConsentRecord.objects.filter(
            user=user, event=ConsentRecord.Event.GIVEN, verified_at__isnull=False
        ).exists():
            problem = "A parent's consent is recorded already."
        if problem:
            raise serializers.ValidationError({"non_field_errors": [problem]})
        record = ConsentRecord.record(
            request,
            user,
            by_parent=True,
            method=method,
            verified_at=timezone.now(),
            verified_by=staff,
            evidence_ref=evidence_ref,
        )
        told = tell_parent(user)
        audit.record(
            "user.consent_verified",
            request=request,
            target=user,
            reason=reason,
            details={"consent": record.pk, "method": method, "child": True, "parent_told": told},
        )
    return record


def tell_parent(user):
    """The parent hears that their consent was recorded (so that one never given is noticed): by email, once the
    transaction commits. "email" when it goes, "" for a mobile number (nothing is registered with DLT to text it)."""
    from ops.tasks import queue_text_email

    contact = user.parent_contact
    if "@" not in contact:
        return ""
    name = shown_name(user.full_name)

    def send():
        queue_text_email(
            contact,
            "Your consent for your child's account was recorded",
            f"ExamLeaf has recorded your consent to keep the details of {name}'s account, confirmed by one of our "
            f"staff. If you did not give it, write to us at once: {settings.SITE_URL}/contact/",
        )

    transaction.on_commit(send, robust=True)
    return "email"


# ---- The account actions that a bulk job runs ----


def minors_among(targets):
    """How many of these accounts' ids are students under 18 (ids that are not numbers count for nothing: the row is
    refused when it runs)."""
    ids = [int(target) for target in targets if str(target).isdigit()]
    return sum(
        User.objects.filter(pk__in=ids[start : start + 500], date_of_birth__gt=adult_born_by()).count()
        for start in range(0, len(ids), 500)
    )


class CustomerAction(Action):
    """An account action named by a bulk action (staff.jobs): each target an account's id, run as its own request with
    the starter's permission (`maker`) and the accounts in their scope. Within the starter's limits it runs at once; a
    job above them, or with a child's account among its targets, waits for an approver as a whole (staff.jobs.start),
    so a row never waits by itself. Audited per row (the account's own event, with the starter as actor) and once for
    the batch (the job's events)."""

    generic, bulk = False, True
    checker = "staff.approve_export"  # (the job's approval is the job.run request's; a row has none of its own)

    def account(self, change_request):
        return change_request.payload["user"]

    def children(self, targets):
        return minors_among(targets)

    def customer(self, maker, target):
        """The account (a customer in the maker's scope), or ValidationError for the row."""
        pk = int(target) if str(target).isdigit() else None
        accounts = scoped(User.objects.filter(is_staff=False, is_superuser=False), maker, "accounts.view_user")
        user = accounts.filter(pk=pk).first() if pk is not None else None
        if user is None:
            raise serializers.ValidationError({"target": ["No such customer (or not one you may see)."]})
        if erased(user):
            raise serializers.ValidationError({"target": ["This account was erased."]})
        return user

    def problem(self, user):
        """Why the action does not apply to this account now, in words, or None."""
        return None

    def validate(self, maker, target, payload):
        user = self.customer(maker, target)
        if problem := self.problem(user):
            raise serializers.ValidationError({"target": [problem]})
        return user, {"user": user.pk}, None

    def rule(self, maker, change_request):
        return None

    def current(self, change_request):
        """The account as it is now, locked, or Refused when it is gone or was erased meanwhile; and Refused when the
        action no longer applies (it did when the row was asked)."""
        user = User.objects.select_for_update().filter(pk=change_request.payload["user"]).first()
        if user is None or erased(user):
            raise Refused("The account is gone.")
        if problem := self.problem(user):
            raise Refused(problem)
        return user


class Suspend(CustomerAction):
    name, label, maker = "user.suspend", "Suspend a customer's account", "staff.suspend_user"

    def problem(self, user):
        return None if user.is_active else "The account is suspended already."

    def run(self, change_request, by):
        user = self.current(change_request)
        services.suspend(user, reason=change_request.reason, actor=by)
        return {"user": user.pk}


class Unsuspend(CustomerAction):
    name, label, maker = "user.unsuspend", "Lift a customer's suspension", "staff.suspend_user"

    def problem(self, user):
        return "The account is not suspended." if user.is_active else None

    def run(self, change_request, by):
        user = self.current(change_request)
        services.unsuspend(user, reason=change_request.reason, actor=by)
        return {"user": user.pk}


class EndSessions(CustomerAction):
    name, label, maker = "user.end_sessions", "Sign a customer out everywhere", "staff.end_user_sessions"

    def run(self, change_request, by):
        user = self.current(change_request)
        sessions, tokens = services.end_sessions(user, actor=by)
        return {"user": user.pk, "sessions": sessions, "tokens": tokens}


class ResendConsent(CustomerAction):
    name, label, maker = "user.resend_consent", "Send a parent's consent link again", "staff.resend_verification"

    def problem(self, user):
        if not user.consent_pending:
            return "No parent's consent is pending for this account."
        return None

    def run(self, change_request, by):
        user = self.current(change_request)
        try:
            services.resend_verification(user, actor=by)
        except (serializers.ValidationError, exceptions.Throttled) as error:
            raise Refused(" ".join(str(item) for item in _messages(error))) from error
        return {"user": user.pk}


def _messages(error):
    """The words of a DRF error, flat."""
    detail = getattr(error, "detail", error)
    if isinstance(detail, dict):
        return [item for value in detail.values() for item in _messages(value)]
    if isinstance(detail, list):
        return [item for value in detail for item in _messages(value)]
    return [detail]


from . import approvals  # noqa: E402  (approvals imports this module last: its ACTIONS exist by now)

approvals.ACTIONS.update({action.name: action for action in [Suspend(), Unsuspend(), EndSessions(), ResendConsent()]})
