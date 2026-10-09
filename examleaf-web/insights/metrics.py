"""The numbers of the panel's Home and its reports, one function each (plan 5.1 and 5.16; research lms 5.1): net
revenue, orders placed, orders to pack, codes redeemed, active learners, clips completed, quotes open, tickets due and
breached, mistakes reported and items flagged, refunds to approve, bank refunds to mark paid, unmatched settlement
items, COD overdue. Each is defined once, here: the function's docstring is the definition the panel shows when the
number is hovered or its "How this is counted" opened, and the Home card, the reports and the admin's dashboard all call
it (nothing else counts the same thing).

Every function takes the person asking (`user`: their scope narrows the rows, exactly as the list the number links to
narrows them; None: all of them, for the Django admin's dashboard) and the period, and answers a `Metric`. Test mode is
kept out by construction: the orders a metric reads go through `live_orders()`, a payment, a refund or a parcel through
its order's `livemode`, and a ticket through the tickets' own rule, all on a live site (on a site running on test keys
every order is a test one, nothing is left out and `test_mode` says so). A metric whose source is not installed (the
Finance, Course or Support module not merged yet) raises `Absent`: Home leaves its card out, a report says it is not
configured. Counts of people are counts: nothing here names or keys a person.

A period is India's calendar days, both ends included (time zone Asia/Kolkata, as every legal clock here), so a month
end or a day's change never moves a payment into the next day."""

import inspect
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.apps import apps
from django.db.models import DateTimeField, F, OuterRef, Subquery, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from accounts import roles
from shop.models import Order, Payment, QuoteRequest, Refund, live_mode, rupees
from staff.backends import scoped


class Absent(Exception):
    """The metric reads an app or model that is not installed yet (Home leaves its card out)."""


# ---- Periods ----


def day_start(day):
    """The first moment of an India day (aware)."""
    return timezone.make_aware(datetime.combine(day, time.min))


@dataclass(frozen=True)
class Period:
    """India's days from `start` to `end`, both included."""

    start: date
    end: date

    @property
    def days(self):
        return (self.end - self.start).days + 1

    @property
    def since(self):
        """The first moment of the period."""
        return day_start(self.start)

    @property
    def until(self):
        """The first moment after it (filter with `< until`)."""
        return day_start(self.end + timedelta(days=1))

    def previous(self):
        """The period of the same length that ends the day before this one starts."""
        return Period(self.start - timedelta(days=self.days), self.start - timedelta(days=1))


def last_days(count, today=None):
    """The `count` days up to and including today (or `today`)."""
    today = today or timezone.localdate()
    return Period(today - timedelta(days=count - 1), today)


# ---- What a metric is, and the registry ----


@dataclass(frozen=True)
class Metric:
    """One number with what the panel shows beside it: the definition, when it was worked out and the period."""

    key: str
    label: str
    value: Decimal | int
    unit: str  # "inr" (rupees, two places) or "count"
    definition: str
    as_of: datetime
    period: Period | None  # None: the figure of this moment (a queue)
    test_mode: bool  # made of test-mode rows: the site runs on test keys (nothing is left out)


@dataclass(frozen=True)
class Spec:
    """How a metric is drawn and who sees it on Home: the permissions it needs (all of them: its own and the data's),
    the roles it is for, the list or report its card links to (`{period}` becomes the period's filters), and whether it
    is a total (`measure`) or something that waits for a person (`queue`)."""

    key: str
    label: str
    unit: str
    definition: str
    run: object
    needs: tuple
    roles: frozenset
    href: str
    group: str
    compares: bool  # a total with a previous period to set beside it
    days: int | None  # a window of its own (active learners: 7), whatever period Home shows
    orders: bool  # reads orders, payments, refunds or parcels: test mode applies
    home: bool  # a card of Home (the others are the reports' and the admin dashboard's)


SPECS = {}


def one_paragraph(text):
    """A docstring as one paragraph, whatever its line breaks."""
    return " ".join(inspect.cleandoc(text).split())


def metric(
    key,
    label,
    *,
    unit="count",
    needs=(),
    roles=(),
    href="",
    group="queue",
    compares=False,
    days=None,
    orders=False,
    home=True,
):
    """Registers a metric. The function takes (user, period) and answers the number (a Decimal or an int); what is
    returned is a `Metric` made of it, the docstring and the spec."""

    def register(function):
        definition = one_paragraph(function.__doc__)

        def run(user=None, period=None):
            period = period or last_days(days or 7)
            value = function(user, period)
            return Metric(
                key,
                label,
                value,
                unit,
                definition,
                timezone.now(),
                period if (compares or days) else None,
                orders and not live_mode(),
            )

        run.__doc__, run.__name__ = function.__doc__, function.__name__
        SPECS[key] = Spec(
            key, label, unit, definition, run, tuple(needs), frozenset(roles), href, group, compares, days, orders, home
        )
        return run

    return register


OWNERS = (roles.OWNER, roles.ADMIN)


def visible(user):
    """The specs this person sees on Home, in the order of the registry: those for one of their roles whose
    permissions they all hold. A break-glass account is an owner; an API key has no roles and sees none."""
    names = set(user.role_names) | ({roles.OWNER} if user.is_superuser else set())
    return [
        spec
        for spec in SPECS.values()
        if spec.home and spec.roles & names and all(user.has_perm(permission) for permission in spec.needs)
    ]


# ---- What the metrics share ----


def rows(queryset, user, perm):
    """The rows the person reaches with `perm` (their scope, as the list narrows them); all of them without a person."""
    return queryset if user is None else scoped(queryset, user, perm)


def live_orders():
    """The orders that count as sales (placed, and neither cancelled nor refunded in full), without the test-mode ones
    on a live site: the one place that says which orders a number may stand on."""
    orders = Order.objects.counted()
    return orders.filter(livemode=True) if live_mode() else orders


def live_only(queryset, path):
    """A queryset of something that hangs on an order (`path`: its livemode, e.g. "order__livemode"), without the
    rows of test-mode orders on a live site."""
    return queryset.filter(**{path: True}) if live_mode() else queryset


def model(label):
    """A model of an app that may not be installed (yet): the model, or `Absent`."""
    try:
        return apps.get_model(label)
    except LookupError:
        raise Absent(label) from None


def field(model_, *names):
    """The first of these names that is a field of the model (another module's model, whose names are its own), else
    None."""
    found = {each.name for each in model_._meta.get_fields()}
    return next((name for name in names if name in found), None)


# ---- Money ----


def captured_at():
    """When a payment was first captured: its history's first captured row (a payment keeps every change); a payment
    without one (saved before its history was kept) is dated by its last change."""
    first = (
        Payment.history.filter(id=OuterRef("pk"), status=Payment.Status.CAPTURED)
        .order_by("history_date")
        .values("history_date")[:1]
    )
    return Coalesce(Subquery(first), F("modified"), output_field=DateTimeField())


def payments_captured(user, period):
    """The payments first captured in the period (a payment later refunded in part or whole was captured, too)."""
    payments = rows(
        Payment.objects.filter(status__in=[Payment.Status.CAPTURED, Payment.Status.REFUNDED]), user, "shop.view_payment"
    )
    payments = live_only(payments, "order__livemode").annotate(captured_at=captured_at())
    return payments.filter(captured_at__gte=period.since, captured_at__lt=period.until)


def refunds_processed(user, period):
    """The refunds that moved money and were processed in the period (a credit note alone, for a parcel that came back
    unpaid, moved none)."""
    processed = Refund.objects.filter(status=Refund.Status.PROCESSED).exclude(method=Refund.Method.NONE)
    processed = live_only(rows(processed, user, "shop.view_refund"), "order__livemode")
    processed = processed.annotate(done_at=Coalesce("processed_at", "modified", output_field=DateTimeField()))
    return processed.filter(done_at__gte=period.since, done_at__lt=period.until)


def total(queryset):
    """The sum of the rows' amounts in rupees, to the paisa (0 for none)."""
    return rupees(queryset.aggregate(total=Sum("amount"))["total"] or 0)


# ---- The metrics ----

MONEY = ("staff.view_insights", "shop.view_payment", "shop.view_refund")
ORDERS_OFFICE = (*OWNERS, roles.SALES, roles.SALES_REP)
SUPPORT_DESK = (*OWNERS, roles.SUPPORT)
EDITORS = (*OWNERS, roles.CONTENT_EDITOR, roles.REVIEWER)
LEARNING = ("staff.view_insights",)


@metric(
    "net_revenue",
    "Net revenue",
    unit="inr",
    needs=MONEY,
    roles=(*OWNERS, roles.FINANCE, roles.AUDITOR),
    href="/reports/sales/{period}",
    group="measure",
    compares=True,
    orders=True,
)
def net_revenue(user, period):
    """Money received less money returned in the period, in rupees, with the shipping and any GST charged: the payments
    first captured in it, less the refunds processed in it. A cash-on-delivery order counts when its parcel is delivered
    and the courier has the cash, not when it is placed. Test-mode payments are left out."""
    return total(payments_captured(user, period)) - total(refunds_processed(user, period))


@metric(
    "orders_placed",
    "Orders",
    needs=("shop.view_order",),
    roles=(*OWNERS, roles.AUDITOR),
    href="/reports/sales/{period}",
    group="measure",
    compares=True,
    orders=True,
)
def orders_placed(user, period):
    """Orders placed in the period: paid online, or placed to pay on delivery, and not cancelled or refunded in full
    since. Test-mode orders are left out."""
    placed = rows(live_orders(), user, "shop.view_order")
    return placed.filter(placed_at__gte=period.since, placed_at__lt=period.until).count()


@metric(
    "orders_to_pack",
    "Orders to pack",
    needs=("shop.view_order",),
    roles=(*ORDERS_OFFICE, roles.PACKER),
    href="/orders/?tab=to_pack",
    orders=True,
)
def orders_to_pack(user, period):
    """Orders waiting to be packed now: paid, or placed to pay on delivery, not packed and not on hold. The same orders
    as the Orders list's "To pack" tab; test-mode orders are left out."""
    from shop.staff_orders import OrderFilter  # (it imports the staff API: not at import time)

    queryset = rows(Order.objects.all(), user, "shop.view_order")
    return OrderFilter({"tab": "to_pack"}, queryset=queryset).qs.count()


@metric(
    "orders_on_the_way",
    "Orders on the way",
    needs=("shop.view_order",),
    roles=(*OWNERS, roles.SALES),
    href="/orders/?tab=shipped",
    orders=True,
    home=False,
)
def orders_on_the_way(user, period):
    """Orders sent and not yet delivered now. Test-mode orders are left out."""
    sent = live_only(rows(Order.objects.filter(status=Order.Status.SHIPPED), user, "shop.view_order"), "livemode")
    return sent.count()


@metric(
    "quotes_open",
    "Quotes open",
    needs=("shop.view_quoterequest",),
    roles=ORDERS_OFFICE,
    href="/orders/quotes/?status=new",
)
def quotes_open(user, period):
    """Quotation requests from schools and booksellers that wait for a quotation (status "new")."""
    waiting = QuoteRequest.objects.filter(status=QuoteRequest.Status.NEW)
    return rows(waiting, user, "shop.view_quoterequest").count()


@metric(
    "refunds_to_approve",
    "Refunds to approve",
    needs=("staff.approve_refund",),
    roles=(roles.OWNER, roles.FINANCE),
    href="/approvals/?who=awaiting",
    orders=True,
)
def refunds_to_approve(user, period):
    """Refunds asked for above the asker's limit that wait for a second person's decision: change requests of
    "order.refund" still pending and not past their time, other than the person's own (nobody approves their own).
    Refunds of test-mode orders are left out."""
    from staff.models import ChangeRequest

    waiting = ChangeRequest.objects.filter(
        action="order.refund", status=ChangeRequest.Status.PENDING, expires_at__gt=timezone.now()
    )
    if user is not None:
        waiting = waiting.exclude(maker=user)
    asked = list(waiting.values_list("target_type", "target_id"))
    if live_mode():  # a test-mode order's refund waits too, but is no one's work on a live site
        ids = [int(each) for kind, each in asked if kind == "shop.order" and each.isdigit()]
        test = set(Order.objects.filter(pk__in=ids, livemode=False).values_list("pk", flat=True))
        asked = [
            (kind, each) for kind, each in asked if not (kind == "shop.order" and each.isdigit() and int(each) in test)
        ]
    return len(asked)


@metric(
    "bank_refunds_to_pay",
    "Bank refunds to mark paid",
    needs=("staff.approve_refund",),
    roles=(roles.OWNER, roles.FINANCE),
    href="/inbox/?kind=bank_refund",
    orders=True,
)
def bank_refunds_to_pay(user, period):
    """Refunds to be transferred by bank or UPI that wait for FINANCE to make the transfer and mark them paid (status
    "requested", method bank). Refunds of test-mode orders are left out."""
    waiting = Refund.objects.filter(method=Refund.Method.BANK, status=Refund.Status.PENDING)
    return live_only(rows(waiting, user, "shop.view_refund"), "order__livemode").count()


@metric(
    "cod_overdue",
    "COD overdue",
    needs=("staff.view_cod",),
    roles=(*OWNERS, roles.FINANCE),
    href="/reports/cod/",
    orders=True,
)
def cod_overdue(user, period):
    """Cash-on-delivery remittances from the couriers that are overdue: the cash was collected on delivery and the
    courier's remittance is more than SHIPPING_COD_GRACE_DAYS working days past the day it was expected. Parcels of
    test-mode orders are left out."""
    from shipping.models import CodRemittance

    late = CodRemittance.objects.filter(state=CodRemittance.State.OVERDUE)
    return live_only(rows(late, user, "staff.view_cod"), "shipment__order__livemode").count()


@metric(
    "tickets_due", "Tickets due today", needs=("support.view_ticket",), roles=SUPPORT_DESK, href="/support/?tab=due"
)
def tickets_due(user, period):
    """Support tickets that are new, open or waiting whose next legal deadline falls later today (India's time). A
    ticket past its deadline is a breach and counts under "Tickets breached", not here. Spam, and tickets about a
    test-mode order, are left out."""
    from support.api import TicketFilter

    queryset = rows(model("support.Ticket").objects.all(), user, "support.view_ticket")
    running = TicketFilter({"open": "true", "overdue": "false"}, queryset=queryset).qs
    return running.filter(next_due_at__lt=day_start(timezone.localdate() + timedelta(days=1))).count()


@metric(
    "tickets_breached",
    "Tickets breached",
    needs=("support.view_ticket",),
    roles=SUPPORT_DESK,
    href="/support/?tab=overdue",
)
def tickets_breached(user, period):
    """Support tickets that are new, open or waiting and already past a legal deadline (the acknowledgement or the
    resolution that applies): the list's "Overdue" tab. Spam, and tickets about a test-mode order, are left out."""
    from support.api import TicketFilter

    queryset = rows(model("support.Ticket").objects.all(), user, "support.view_ticket")
    return TicketFilter({"overdue": "true"}, queryset=queryset).qs.count()


def error_reports(user, **filters):
    """The open mistake reports a person reaches (the content list's own filters, spam never), by `filters`."""
    from content.staff_api import ReportFilter

    reports = model("content.ErrorReport").objects.filter(spam=False)
    return ReportFilter(filters, queryset=rows(reports, user, "content.view_errorreport")).qs


@metric("reports_open", "Reports open", needs=("content.view_errorreport",), roles=EDITORS, href="/content/reports/")
def reports_open(user, period):
    """Mistakes in the content that wait for triage: reported by a reader or flagged by the quiz's item analysis, and
    neither fixed nor rejected (status "reported" or "confirmed"), within the subjects the person looks after. Spam is
    left out."""
    return error_reports(user).count()


@metric(
    "items_flagged",
    "Items flagged",
    needs=("content.view_errorreport",),
    roles=EDITORS,
    href="/content/reports/?category=item_analysis",
)
def items_flagged(user, period):
    """Quiz items that the item analysis flagged (too easy, too hard, a distractor that the strong chose) and that
    nobody has looked at yet: the open reports of category "flagged by the item analysis", also counted under "Reports
    open"."""
    return error_reports(user, category="item_analysis").count()


@metric(
    "settlement_items_unmatched",
    "Settlement items unmatched",
    needs=("shop.view_settlement",),
    roles=(*OWNERS, roles.FINANCE, roles.AUDITOR),
    href="/finance/settlements/",
)
def settlement_items_unmatched(user, period):
    """Lines of Razorpay's settlements that match no payment, no refund and no payment link of ours (an adjustment is
    not a line to match). FINANCE finds each one in the settlement it belongs to."""
    line = model("shop.SettlementLine")
    links = [
        each.name
        for each in line._meta.get_fields()
        if each.is_relation and each.many_to_one and (each.related_model in (Payment, Refund) or each.name == "link")
    ]
    if not links:
        raise Absent("shop.SettlementLine has no link to a payment or a refund")
    unmatched = line.objects.all()
    for name in links:
        unmatched = unmatched.filter(**{f"{name}__isnull": True})
    if kind := field(line, "type", "kind", "entity_type"):
        unmatched = unmatched.exclude(**{kind: "adjustment"})
    return rows(unmatched, user, "shop.view_settlementline").count()


@metric(
    "codes_redeemed",
    "Codes redeemed",
    needs=(*LEARNING, "learn.view_bookcode"),
    roles=(*OWNERS, roles.AUDITOR),
    href="/reports/codes/",
    group="measure",
    compares=True,
)
def codes_redeemed(user, period):
    """Book codes redeemed in the period: the codes printed in the books that a student entered in the app for the
    course (a code is redeemed once)."""
    from learn.models import BookCode

    redeemed = rows(BookCode.objects.all(), user, "learn.view_bookcode")
    return redeemed.filter(redeemed_at__gte=period.since, redeemed_at__lt=period.until).count()


def activity(period):
    """The customers' accounts with any course activity in the period, as one query of ids that counts each once: a clip
    watched (its progress saved), a quiz question answered or a flash card turned over. Staff accounts are left out."""
    from learn.models import CardReview, Progress, QuizAttempt

    def accounts(queryset, when):
        within = {f"{when}__gte": period.since, f"{when}__lt": period.until}
        return queryset.filter(user__is_staff=False, **within).order_by().values("user")  # (no ordering in a UNION)

    return accounts(Progress.objects, "updated").union(
        accounts(QuizAttempt.objects, "created"), accounts(CardReview.objects, "created")
    )


@metric(
    "active_learners",
    "Active learners",
    needs=(*LEARNING, "learn.view_progress"),
    roles=(*OWNERS, roles.AUDITOR),
    href="/reports/course-health/",
    group="measure",
    compares=True,
    days=7,
)
def active_learners(user, period):
    """Customers' accounts with any course activity in the period (Home: the last 7 days): a clip watched, a quiz answer
    given or a flash card turned over. A count of accounts, never a list of them; staff accounts are left out."""
    if user is not None and not user.has_perm("learn.view_progress"):
        return 0
    return activity(period).count()


@metric(
    "clips_completed",
    "Clips completed",
    needs=(*LEARNING, "learn.view_progress"),
    roles=(*OWNERS, roles.AUDITOR),
    href="/reports/course-health/",
    group="measure",
    compares=True,
    home=False,
)
def clips_completed(user, period):
    """Clips that students watched to the end, counted on the day of the clip's last progress (the course keeps no
    time of completion of its own): progress marked completed and saved in the period. Staff accounts are left out."""
    from learn.models import Progress

    if user is not None and not user.has_perm("learn.view_progress"):
        return 0
    done = Progress.objects.filter(completed=True, updated__gte=period.since, updated__lt=period.until)
    return done.filter(user__is_staff=False).count()
