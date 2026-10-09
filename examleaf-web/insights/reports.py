"""The reports of the panel (plan 5.16): sales by product, subject, class, board, edition and period; sales by state,
district and PIN code; book codes by batch and district; the course's use by subject and chapter; cash on delivery's
ageing and remittance; and Razorpay's settlements. Each is a function of the person asking and the filters, answering
one dict: what it counts (`definition` and each column's), when it was worked out (`as_of`, and `computed_at` for what
a night's job wrote), whether it stands on test-keys data (`test_mode`) and its `rows`.

The rules every report keeps, which the tests hold it to: test-mode orders are left out on a live site
(metrics.live_orders and live_only); the rows are the person's own (`scoped()` with the data's view permission, as the
lists narrow them); a cell standing on fewer than the minimum is hidden (cells.py); nothing names, keys or lists a
person (no row has a user, a learner, an address or a contact: counts and sums only); the period is bounded to 13
months; one query (or a few) answers a report whatever its rows (no query per row); money is Decimal to the paisa.

The same functions answer the API (staff_api.py) and the export job (exports.py), so a file holds what the page
showed."""

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db.models import (
    Case,
    CharField,
    Count,
    DecimalField,
    ExpressionWrapper,
    F,
    Max,
    Min,
    Q,
    Sum,
    Value,
    When,
)
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Coalesce, NullIf, TruncDate, TruncMonth, TruncWeek
from django.utils import timezone
from rest_framework import serializers

from shop.models import STATES, OrderItem, PinCode, live_mode, rupees

from . import cells
from .jobs import UNKNOWN, health
from .metrics import Absent, Period, field, live_only, live_orders, model, rows

MAX_MONTHS = 13  # a report's period: no longer than this (the queries stay short; a season is shorter)
MAX_ROWS = 5000  # the rows of a sales report: more asks for a narrower period or a coarser grouping
MONEY = DecimalField(max_digits=14, decimal_places=2)


# ---- Filters ----


def day(value):
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError("A day: YYYY-MM-DD.") from None


def one_of(*choices):
    def cast(value):
        if value not in choices:
            raise ValueError(f"One of {', '.join(choices)}.")
        return value

    return cast


def whole(value):
    if not value.isdigit():
        raise ValueError("A number.")
    return int(value)


def parse(params, spec):
    """The filters of a report as it takes them, `{name: (cast, default)}`; raises the API's 400 naming each wrong."""
    clean, errors = {}, {}
    for name, (cast, default) in spec.items():
        raw = str(params.get(name) or "").strip()
        try:
            clean[name] = cast(raw) if raw else default
        except ValueError as error:
            errors[name] = [str(error)]
    if errors:
        raise serializers.ValidationError(errors)
    return clean


def months_back(from_day, months):
    """The same day `months` months earlier (the month's last day when it has not that many)."""
    index = from_day.year * 12 + from_day.month - 1 - months
    year, month = index // 12, index % 12 + 1
    return date(year, month, min(from_day.day, calendar.monthrange(year, month)[1]))


PERIOD = {"from": (day, None), "to": (day, None)}


def period_of(clean, days=30):
    """The period the filters name (India's days): `to` today and `from` a month before by default; never after today,
    never backwards, never longer than 13 months."""
    today = timezone.localdate()
    end = clean["to"] or today
    start = clean["from"] or end - timedelta(days=days - 1)
    if end > today:
        raise serializers.ValidationError({"to": ["Not after today."]})
    if start > end:
        raise serializers.ValidationError({"from": ["Not after the last day."]})
    if start <= months_back(end, MAX_MONTHS):
        raise serializers.ValidationError({"from": [f"At most {MAX_MONTHS} months before the last day."]})
    return Period(start, end)


def column(key, label, definition):
    return {"key": key, "label": label, "definition": definition}


def envelope(key, definition, columns, period=None, **parts):
    """What every report answers with: its words, its columns', when it was worked out, whether it stands on test keys
    (a site on test keys has no live orders to tell from the rest), its period and whatever else it holds."""
    return {
        "report": key,
        "definition": definition,
        "columns": columns,
        "as_of": timezone.now(),
        "test_mode": not live_mode(),
        "period": {"start": period.start, "end": period.end, "days": period.days} if period else None,
        **parts,
    }


# ---- Sales ----

SALES_PARAMS = {
    **PERIOD,
    "by": (one_of("product", "subject", "class", "board", "edition", "none"), "product"),
    "grain": (one_of("none", "day", "week", "month"), "none"),
}
SALES_COLUMNS = [
    column("label", "Group", "What the lines are grouped by: a product, a subject, a class, a board or an edition."),
    column(
        "period_start",
        "Period",
        "The day, the week (it starts on Monday) or the month; the first and the last may be part of one.",
    ),
    column("orders", "Orders", "Orders with a line in the group, each counted once."),
    column("units", "Units", "Copies (or courses) sold: the quantity of each line."),
    column("gross", "Gross (₹)", "The lines' selling prices times their quantities, before any discount."),
    column(
        "discount", "Discount (₹)", "The lines' share of the order's discounts: coupon, offers and a staff discount."
    ),
    column(
        "net",
        "Net (₹)",
        "Gross less discount: what the lines sold for. Shipping is not in it and refunds are not "
        "taken off: net revenue on Home is the money in, less the money back.",
    ),
]
SALES_WORDS = (
    "Sales of the orders placed in the period: paid online, or placed to pay on delivery, and not cancelled or "
    "refunded in full since, without test-mode orders. Each line of an order counts in its group; the order's "
    "discounts are shared among its lines (the line's own share where it was kept, else in proportion to its value)."
)
# What a sales report groups by: the fields that name the group, the ones its label is made of, and the label
DIMENSIONS = {
    "product": (["product__slug"], ["product__title"], lambda v: v["product__title"]),
    "subject": (
        ["product__subject_id"],
        ["product__subject__name", "product__subject__board__short_name", "product__subject__class_level__number"],
        lambda v: (
            f"{v['product__subject__name']}, {v['product__subject__board__short_name']}, "
            f"Class {v['product__subject__class_level__number']}"
            if v["product__subject_id"] is not None
            else "No subject"
        ),
    ),
    "class": (
        ["product__subject__class_level__number"],
        [],
        lambda v: (
            f"Class {v['product__subject__class_level__number']}"
            if v["product__subject__class_level__number"] is not None
            else "No class"
        ),
    ),
    "board": (
        ["product__subject__board__short_name"],
        ["product__subject__board__name"],
        lambda v: v["product__subject__board__name"] or "No board",
    ),
    "edition": (["product__book__edition"], [], lambda v: v["product__book__edition"] or "No edition recorded"),
    "none": ([], [], lambda v: "All sales"),
}
GRAINS = {"day": TruncDate, "week": TruncWeek, "month": TruncMonth}


def value_of_line():
    """A line's selling price times its quantity."""
    return ExpressionWrapper(F("unit_price") * F("quantity"), output_field=MONEY)


def discount_of_line():
    """A line's share of its order's discounts: the share kept on the line (`OrderItem.discount`), else, for an order
    made before it was kept, the order's discount in proportion to the line's value (the invoices' own fallback)."""
    share = ExpressionWrapper(
        F("order__discount") * F("unit_price") * F("quantity") / NullIf(F("order__subtotal"), Value(0)),
        output_field=MONEY,
    )
    return Case(
        When(discount__isnull=False, then=F("discount")),
        default=Coalesce(share, Value(0), output_field=MONEY),
        output_field=MONEY,
    )


def placed_lines(user, period):
    """The lines of the live orders placed in the period that the person may see (their scope on the order's status)."""
    placed = live_orders().filter(placed_at__gte=period.since, placed_at__lt=period.until)
    return rows(OrderItem.objects.filter(order__in=placed), user, "shop.view_orderitem")


def line_sums():
    """The measures of a group of lines."""
    return {
        "orders": Count("order", distinct=True),
        "units": Sum("quantity"),
        "gross": Sum(value_of_line()),
        "discount": Sum(discount_of_line()),
    }


def money(row):
    """A row's gross, discount and net as rupees to the paisa."""
    gross, discount = rupees(row["gross"] or 0), rupees(row["discount"] or 0)
    return {"gross": gross, "discount": discount, "net": gross - discount}


def sales(user, params):
    clean = parse(params, SALES_PARAMS)
    period = period_of(clean)
    by, grain = clean["by"], clean["grain"]
    keys, extra, name = DIMENSIONS[by]
    lines = placed_lines(user, period)
    bucket = ["bucket"] if grain != "none" else []
    grouped = lines.annotate(bucket=GRAINS[grain]("order__placed_at")) if bucket else lines
    if keys or bucket:
        found = list(
            grouped.values(*keys, *extra, *bucket).annotate(**line_sums()).order_by(*bucket, *keys)[: MAX_ROWS + 1]
        )
    else:  # everything in one row (values() with nothing to group by would group by every column)
        everything = lines.aggregate(**line_sums())
        found = [everything] if everything["orders"] else []
    if len(found) > MAX_ROWS:
        raise serializers.ValidationError(
            {"non_field_errors": [f"More than {MAX_ROWS:,} rows: choose a shorter period or a coarser grouping."]}
        )
    table = [
        {
            "key": "|".join(str(row[each]) for each in keys),
            "label": name(row),
            "period_start": row["bucket"].date() if bucket and hasattr(row["bucket"], "date") else row.get("bucket"),
            "orders": row["orders"],
            "units": row["units"] or 0,
            **money(row),
        }
        for row in found
    ]
    table.sort(key=lambda each: (each["period_start"] or date.min, -each["net"], each["label"]))
    whole_period = lines.aggregate(**line_sums())
    totals = {"orders": whole_period["orders"], "units": whole_period["units"] or 0, **money(whole_period)}
    return envelope("sales", SALES_WORDS, SALES_COLUMNS, period, by=by, grain=grain, totals=totals, rows=table)


# ---- Sales by place ----

PLACE_PARAMS = {**PERIOD, "level": (one_of("state", "district", "pin"), "state"), "state": (str.upper, "")}
PLACE_COLUMNS = [
    column("label", "Place", "A state (the place of supply), a district or a PIN code (where the parcel goes)."),
    column("orders", "Orders", "Orders delivered there, each counted once."),
    column("units", "Units", "Copies (or courses) sold: the quantity of each line."),
    column("net", "Net (₹)", "What the lines sold for, after the order's discounts; shipping and refunds not in it."),
]
PLACE_WORDS = (
    "Sales of the orders placed in the period, by state, district or PIN code. A state is the place of supply the "
    "order was taxed in (its billing state, else the delivery address's); a district is the PIN code's in India Post's "
    "directory (else the one typed in the address); a PIN code is the delivery address's. A place with fewer than {k} "
    "orders is not shown, and no total counts the places hidden: the rows shown are not the whole of the sales."
)


def address(key):
    """A key of the order's address snapshot."""
    return KeyTextTransform(key, "order__shipping_address")


def directory(pins):
    """{PIN code: its district} in India Post's directory (the first of a PIN on a border)."""
    found, pins = {}, sorted({pin for pin in pins if pin})
    for start in range(0, len(pins), 500):
        for pin, districts in PinCode.objects.filter(pin__in=pins[start : start + 500]).values_list("pin", "districts"):
            if districts:
                found[pin] = districts[0]
    return found


def sales_by_place(user, params):
    clean = parse(params, PLACE_PARAMS)
    period, level = period_of(clean), clean["level"]
    if clean["state"] and clean["state"] not in STATES:
        raise serializers.ValidationError({"state": ["A state's code: AS for Assam."]})
    lines = placed_lines(user, period)
    measures = line_sums()
    if level == "state":
        supplied = Coalesce(
            NullIf("order__billing_state", Value("")), address("state"), Value(""), output_field=CharField()
        )
        found = lines.annotate(supplied=supplied).values("supplied").annotate(**measures).order_by("supplied")
        grouped = {(row["supplied"], None, None): row for row in found}
    else:
        if clean["state"]:
            lines = lines.filter(order__shipping_address__state=clean["state"])
        places = lines.annotate(pin=address("pin"), state=address("state"), typed=address("district"))
        found = list(places.values("pin", "state", "typed").annotate(**measures).order_by("pin", "state", "typed"))
        known = directory(row["pin"] for row in found)
        grouped = {}
        for row in found:
            where = known.get(row["pin"]) or str(row["typed"] or "").strip() or UNKNOWN
            key = (row["state"], where, row["pin"] if level == "pin" else None)
            merged = grouped.setdefault(key, dict.fromkeys(measures, 0))
            for name in measures:
                merged[name] += row[name] or 0
    table = []
    for (state, where, pin), row in grouped.items():
        name = STATES.get(state, state) if state else None
        label = {"state": name or UNKNOWN, "district": where, "pin": pin}[level]
        shown = {
            "level": level,
            "state": state or None,
            "state_name": name,
            "district": where,
            "pin": pin,
            "label": f"{label}, {name}" if level != "state" and name else label,
            "orders": row["orders"],
            "units": row["units"] or 0,
            "net": money(row)["net"],
        }
        table.append(cells.apply(shown, row["orders"], ["orders", "units", "net"]))
    table.sort(key=lambda each: (each["hidden"], -(each["net"] or 0), each["label"]))
    visible = [each for each in table if not each["hidden"]]
    totals = {
        "orders": sum(each["orders"] for each in visible),
        "units": sum(each["units"] for each in visible),
        "net": sum((each["net"] for each in visible), Decimal("0.00")),
    }
    return envelope(
        "sales-by-place",
        PLACE_WORDS.format(k=cells.minimum()),
        PLACE_COLUMNS,
        period,
        level=level,
        state=clean["state"],
        minimum=cells.minimum(),
        hidden_rows=len(table) - len(visible),
        totals_shown=totals,
        rows=table,
    )


# ---- Codes ----

CODES_PARAMS = {"batch": (str, "")}
CODES_COLUMNS = [
    column("batch", "Batch", "The print run the codes were made for (the label on the books: PHY-2027-1)."),
    column("printed", "Printed", "Codes made for the batch."),
    column(
        "sold",
        "Sold",
        "Copies sold of the title the batch is printed in (all the title's batches together), once the course module "
        "records which title that is; empty until then.",
    ),
    column("activated", "Activated", "Codes a student has redeemed."),
    column("activated_7d", "Last 7 days", "Codes redeemed in the last 7 days."),
    column("revoked", "Revoked", "Codes voided before use, once the course module can void them; empty until then."),
    column("activation_rate", "Activation rate", "Activated divided by printed."),
]
CODES_WORDS = (
    "Book codes by print run: how many were printed, redeemed and (when the course module records them) sold and "
    "revoked, and the share redeemed; and the districts the redemptions came from, worked out each night from the "
    "redeemer's last order of the subject. A district with fewer than {k} redemptions is not shown."
)


def recorded_by_the_course(user, batches):
    """({batch: copies sold}, {batch: codes revoked}) where the course module records them: the book a batch is
    printed in, and a voided code. None for what it does not record (yet): those columns stay empty."""
    from learn.models import BookCode

    revoked = sold = None
    if void := field(BookCode, "voided_at", "revoked_at"):
        voided = rows(BookCode.objects.filter(**{f"{void}__isnull": False}), user, "learn.view_bookcode")
        revoked = dict(voided.order_by().values_list("batch").annotate(n=Count("pk")))
    try:
        batch_model = model("learn.CodeBatch")
    except Absent:
        return sold, revoked
    label, book = field(batch_model, "label", "batch", "name"), field(batch_model, "product")
    if label and book:
        titled = batch_model.objects.filter(**{f"{book}__isnull": False})
        books = dict(titled.values_list(label, f"{book}_id"))  # a batch with no title yet is not in it: not recorded
        units = OrderItem.objects.filter(order__in=live_orders(), product__in=set(books.values()))
        units = dict(units.order_by().values_list("product").annotate(n=Sum("quantity")))
        sold = {name: units.get(books[name], 0) for name in books if name in batches}
    return sold, revoked


def codes(user, params):
    from learn.models import BookCode

    from .models import CodeActivationStat

    clean = parse(params, CODES_PARAMS)
    week_ago = timezone.now() - timedelta(days=7)
    batches = (
        rows(BookCode.objects.all(), user, "learn.view_bookcode")
        .order_by()
        .values("batch")
        .annotate(
            printed=Count("pk"),
            activated=Count("redeemed_at"),
            recent=Count("pk", filter=Q(redeemed_at__gte=week_ago)),
            first=Min("created"),
        )
        .order_by("-first", "batch")
    )
    found = list(batches)
    names = {row["batch"] for row in found}
    sold, revoked = recorded_by_the_course(user, names)
    table = [
        {
            "batch": row["batch"],
            "printed": row["printed"],
            "sold": None if sold is None else sold.get(row["batch"]),
            "activated": row["activated"],
            "activated_7d": row["recent"],
            "revoked": None if revoked is None else revoked.get(row["batch"], 0),
            "activation_rate": share(row["activated"], row["printed"]),
        }
        for row in found
    ]
    stats = CodeActivationStat.objects.all()
    newest = stats.aggregate(newest=Max("computed_at"))["newest"]
    districts = []
    if newest is not None:
        by_district = stats.filter(computed_at=newest, district__isnull=False, batch__in=names)
        if clean["batch"]:
            by_district = by_district.filter(batch=clean["batch"])
        by_district = (
            by_district.order_by().values("district").annotate(redeemed=Sum("redeemed"), recent=Sum("redeemed_7d"))
        )
        districts = [
            cells.apply(
                {"district": each["district"], "redeemed": each["redeemed"], "redeemed_7d": each["recent"]},
                each["redeemed"],
                ["redeemed", "redeemed_7d"],
            )
            for each in by_district
        ]
        districts.sort(key=lambda each: (each["hidden"], -(each["redeemed"] or 0), each["district"]))
    return envelope(
        "codes",
        CODES_WORDS.format(k=cells.minimum()),
        CODES_COLUMNS,
        batch=clean["batch"],
        minimum=cells.minimum(),
        districts_computed_at=newest,
        districts=districts,
        rows=table,
    )


def share(part, whole_):
    """A share to four places, or None when there is nothing to divide."""
    return (Decimal(part) / Decimal(whole_)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP) if whole_ else None


# ---- Course health ----

HEALTH_PARAMS = {"subject": (whole, None), "chapter": (whole, None), "grain": (one_of("day", "week", "month"), "week")}
HEALTH_COLUMNS = [
    column("label", "Chapter", "A chapter of the course, under its subject."),
    column("active_7d", "Active, 7 days", "Learners with any activity in the chapter in the 7 days to yesterday."),
    column(
        "active_28d",
        "Active, 28 days",
        "Learners with any activity in the chapter in the 28 days to yesterday, each counted once.",
    ),
    column(
        "clips_started",
        "Clips started",
        "Clips whose progress was saved in the 28 days, counted on the day of the last save.",
    ),
    column("clips_completed", "Clips completed", "Of those, the ones watched to the end."),
    column("completion_rate", "Clip completion", "Completed divided by started."),
    column("quiz_answers", "Quiz answers", "Quiz questions answered in the 28 days (every try)."),
    column("quiz_accuracy", "Quiz accuracy", "The answers that were right, as a share of the answers."),
    column("card_reviews", "Cards turned", "Flash cards turned over in the 28 days."),
    column("card_lapses", "Lapses", "Of those, the cards the learner did not know."),
]
HEALTH_WORDS = (
    "How the revision course is used, by subject and chapter, over complete days, weeks and months (today is not "
    "over), worked out each night; staff accounts are left out. A learner counts once in a period however much they "
    "did. A cell standing on fewer than {k} learners is not shown. The averages of the daily series count a hidden "
    "day as 0; the redemptions by week are of book codes, by subject."
)


def smoothed(counts, days):
    """The mean of the last `days` days' learners at each day (a hidden day counts as 0, so nothing of it leaks)."""
    means = (Decimal(sum(counts[max(0, index - days + 1) : index + 1])) / days for index in range(len(counts)))
    return [mean.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP) for mean in means]


def health_scope(clean, allowed, narrowed, chapters):
    """(the subject the report is about or None, the filter of the stat rows): a chapter, a subject, or the whole
    course; a person who looks after some subjects only is shown one of theirs, never the whole course."""
    subject = clean["subject"]
    if clean["chapter"] is not None:
        picked = next((each for each in chapters if each.pk == clean["chapter"]), None)
        if picked is None:
            raise serializers.ValidationError({"chapter": ["No such chapter (or not one you look after)."]})
        return picked.subject_id, {"chapter_id": picked.pk}
    if subject is not None and subject not in allowed:
        raise serializers.ValidationError({"subject": ["No such subject (or not one you look after)."]})
    if subject is None and narrowed and allowed:
        subject = min(allowed)
    return subject, {"subject_id": subject, "chapter": None}


def course_health(user, params):
    from content.models import Subject
    from learn.models import BookCode, Chapter

    from .models import CourseHealthStat

    clean = parse(params, HEALTH_PARAMS)
    perm = "learn.view_progress"
    subjects = rows(Subject.objects.select_related("board", "class_level"), user, perm)
    allowed = {subject.pk: subject for subject in subjects}
    narrowed = len(allowed) < Subject.objects.count()
    chapters = list(rows(Chapter.objects.select_related("subject"), user, perm).filter(subject__in=allowed))
    subject, scope = health_scope(clean, allowed, narrowed, chapters)
    latest = CourseHealthStat.objects.aggregate(newest=Max("computed_at"), counted_to=Max("computed_for"))
    newest = latest["newest"]
    series, table = [], []
    if newest is not None and allowed:
        grain = clean["grain"]
        found = {
            each.period_start: each
            for each in CourseHealthStat.objects.filter(computed_at=newest, grain=grain, **scope)
        }
        counts = []
        for begins in health.windows(latest["counted_to"])[grain]:
            point = found.get(begins)
            count = point.active_learners if point else 0
            counts.append(0 if cells.is_hidden(count, cells.CLASS) else count)
            shown = {
                "period_start": begins,
                "active_learners": count,
                "clips_completed": point.clips_completed if point else 0,
                "quiz_answers": point.quiz_answers if point else 0,
                "quiz_accuracy": share(point.quiz_correct, point.quiz_answers) if point else None,
                "card_reviews": point.card_reviews if point else 0,
                "card_lapses": point.card_lapses if point else 0,
            }
            series.append(cells.apply(shown, count, list(shown)[1:], cells.CLASS))
        means = (smoothed(counts, 7), smoothed(counts, 28)) if grain == "day" else (None, None)
        for index, point in enumerate(series):
            point["smoothed_7"] = means[0][index] if means[0] else None
            point["smoothed_28"] = means[1][index] if means[1] else None
        trailing = CourseHealthStat.objects.filter(
            computed_at=newest,
            grain__in=[CourseHealthStat.Grain.LAST_7, CourseHealthStat.Grain.LAST_28],
            chapter__subject__in=allowed,
        )
        windows = {(each.chapter_id, each.grain): each for each in trailing}
        for chapter in chapters:
            if subject is not None and chapter.subject_id != subject:
                continue
            month = windows.get((chapter.pk, CourseHealthStat.Grain.LAST_28))
            week = windows.get((chapter.pk, CourseHealthStat.Grain.LAST_7))
            count, week_count = month.active_learners if month else 0, week.active_learners if week else 0
            shown = {
                "subject": chapter.subject_id,
                "chapter": chapter.pk,
                "number": chapter.number,
                "title": chapter.title,
                "label": f"{chapter.subject.name}, chapter {chapter.number}: {chapter.title}",
                "active_7d": None if cells.is_hidden(week_count, cells.CLASS) else week_count,
                "active_28d": count,
                "clips_started": month.clips_started if month else 0,
                "clips_completed": month.clips_completed if month else 0,
                "completion_rate": share(month.clips_completed, month.clips_started) if month else None,
                "quiz_answers": month.quiz_answers if month else 0,
                "quiz_accuracy": share(month.quiz_correct, month.quiz_answers) if month else None,
                "card_reviews": month.card_reviews if month else 0,
                "card_lapses": month.card_lapses if month else 0,
            }
            table.append(cells.apply(shown, count, list(shown)[5:], cells.CLASS))
    redeemed = rows(
        BookCode.objects.filter(redeemed_at__gte=timezone.now() - timedelta(weeks=health.WEEKS)),
        user,
        "learn.view_bookcode",
    )
    if subject is not None:
        redeemed = redeemed.filter(subject=subject)
    weekly = (
        redeemed.annotate(week=TruncWeek("redeemed_at"))
        .order_by()
        .values("week")
        .annotate(n=Count("pk"))
        .order_by("week")
    )
    codes_by_week = [
        cells.apply({"week_start": each["week"].date(), "redeemed": each["n"]}, each["n"], ["redeemed"], cells.CLASS)
        for each in weekly
    ]
    return envelope(
        "course-health",
        HEALTH_WORDS.format(k=cells.minimum(cells.CLASS)),
        HEALTH_COLUMNS,
        None,
        grain=clean["grain"],
        computed_at=newest,
        minimum=cells.minimum(cells.CLASS),
        subject=subject,
        chapter=clean["chapter"],
        subjects=[
            {"id": each.pk, "name": f"{each.name}, {each.board.short_name}, {each.class_level}"}
            for each in allowed.values()
        ],
        whole_course=subject is None and clean["chapter"] is None,
        series=series,
        codes_by_week=codes_by_week,
        rows=table,
    )


# ---- Cash on delivery ----

COD_BUCKETS = [  # (key, label, days late from, to), by the day the remittance was expected
    ("not_due", "Not yet due", None, 0),
    ("late_1_7", "1 to 7 days late", 1, 7),
    ("late_8_14", "8 to 14 days late", 8, 14),
    ("late_15_30", "15 to 30 days late", 15, 30),
    ("late_31", "More than 30 days late", 31, None),
]
COD_COLUMNS = [
    column("label", "Ageing", "How late the courier's remittance is: counted from the day it was expected."),
    column("count", "Parcels", "Parcels delivered whose cash has not come: expected, or overdue."),
    column("expected", "Expected (₹)", "The cash on delivery amounts of those parcels."),
    column("oldest_expected_on", "Oldest expected", "The earliest day among them that a remittance was expected."),
]
COD_WORDS = (
    "Cash on delivery: the cash couriers collected and have not yet remitted, by how late it is (a remittance is "
    "expected {days} working days after delivery and is overdue {grace} working days after that), and what was "
    "remitted in the period, at the amount expected or another. Parcels of test-mode orders are left out."
)


def cod(user, params):
    from shipping.models import CodRemittance

    clean = parse(params, PERIOD)
    period = period_of(clean)
    today = timezone.localdate()
    State = CodRemittance.State
    every = live_only(rows(CodRemittance.objects.all(), user, "staff.view_cod"), "shipment__order__livemode")
    waiting = every.filter(state__in=[State.EXPECTED, State.OVERDUE])
    counts = {}
    for key, _, low, high in COD_BUCKETS:
        late = Q()
        if low is not None:
            late &= Q(expected_on__lte=today - timedelta(days=low))
        if high is not None:
            late &= Q(expected_on__gt=today - timedelta(days=high + 1))
        counts |= {
            f"{key}_n": Count("pk", filter=late),
            f"{key}_sum": Sum("expected_amount", filter=late),
            f"{key}_old": Min("expected_on", filter=late),
        }
    found = waiting.aggregate(**counts)
    ageing = [
        {
            "key": key,
            "label": label,
            "count": found[f"{key}_n"],
            "expected": rupees(found[f"{key}_sum"] or 0),
            "oldest_expected_on": found[f"{key}_old"],
        }
        for key, label, _, _ in COD_BUCKETS
    ]
    remitted = every.filter(
        state__in=[State.REMITTED, State.MISMATCH], remitted_at__gte=period.start, remitted_at__lte=period.end
    )
    done = remitted.aggregate(count=Count("pk"), expected=Sum("expected_amount"), received=Sum("remitted_amount"))
    couriers = (
        waiting.order_by()
        .values("shipment__courier")
        .annotate(
            count=Count("pk"), expected=Sum("expected_amount"), overdue=Count("pk", filter=Q(state=State.OVERDUE))
        )
    )
    by_courier = [
        {
            "courier": each["shipment__courier"],
            "count": each["count"],
            "expected": rupees(each["expected"] or 0),
            "overdue": each["overdue"],
        }
        for each in couriers.order_by("shipment__courier")
    ]
    expected, received = rupees(done["expected"] or 0), rupees(done["received"] or 0)
    return envelope(
        "cod",
        COD_WORDS.format(days=settings.SHIPPING_COD_REMITTANCE_DAYS, grace=settings.SHIPPING_COD_GRACE_DAYS),
        COD_COLUMNS,
        period,
        as_of_day=today,
        remitted={
            "count": done["count"],
            "expected": expected,
            "received": received,
            "difference": received - expected,
        },
        by_courier=by_courier,
        rows=ageing,
    )


# ---- Settlements ----

SETTLEMENT_COLUMNS = [
    column("date", "Date", "The day Razorpay settled."),
    column("reference", "Settlement", "Razorpay's settlement id."),
    column("gross", "Gross (₹)", "What the customers paid in the settlement's payments."),
    column("fees", "Fees (₹)", "Razorpay's fees."),
    column("tax", "GST on fees (₹)", "The GST Razorpay charged on its fees."),
    column("refunds", "Refunds (₹)", "The refunds taken off the settlement."),
    column("net", "Net (₹)", "What reached the bank."),
    column("utr", "UTR", "The bank's reference of the transfer."),
    column("state", "State", "Fetched, matched, posted or mismatched."),
]
SETTLEMENT_WORDS = (
    "Razorpay's settlements: for each, what was paid, the fees and the GST on them, the refunds and what reached the "
    "bank, with the bank's UTR; newest first."
)
SETTLEMENT_FIELDS = {  # the Finance module's names for each, in the order tried
    "reference": ("settlement_id", "razorpay_id", "reference", "external_id"),
    "date": ("date", "settled_on", "settled_at", "created_on"),
    "gross": ("gross", "gross_amount", "amount"),
    "fees": ("fees", "fee", "fees_amount"),
    "tax": ("tax", "tax_on_fees", "gst", "fee_tax"),
    "refunds": ("refunds", "refund_amount", "refunds_amount"),
    "net": ("net", "net_amount"),
    "utr": ("utr",),
    "state": ("state", "status"),
}
MAX_SETTLEMENTS = 500


def settlement_row(each, names, refunds=None):
    """One settlement as a row. `names` says which field of the model holds each part (SETTLEMENT_FIELDS tried in
    turn; None where the module has none); `refunds` the refunds taken off each settlement, by id, where they are
    summed from its lines (None: the module keeps none). The date is a day, whether the module keeps the day Razorpay
    settled or the moment; money is to the paisa, whether the module keeps Money or a Decimal."""

    def part(key):
        return getattr(each, names[key]) if names[key] else None

    def money(key):
        return rupees(getattr(part(key), "amount", part(key)) or 0) if names[key] else None

    when = part("date")
    taken = money("refunds") if names["refunds"] else None if refunds is None else rupees(refunds.get(each.pk, 0))
    return {
        "reference": str(part("reference") if names["reference"] else each.pk),
        "date": timezone.localtime(when).date() if isinstance(when, datetime) else when,
        "gross": money("gross"),
        "fees": money("fees"),
        "tax": money("tax"),
        "refunds": taken,
        "net": money("net"),
        "utr": part("utr") or "",
        "state": str(part("state") or ""),
    }


def refund_totals(record, ids):
    """The refunds taken off each settlement (`ids`), from its lines: the Finance module's lines of type "refund"
    summed, `{id: amount}`; None where the module keeps no lines with a type and an amount."""
    name = field(record, "lines")
    if not name:
        return None
    relation = record._meta.get_field(name)
    line = relation.related_model
    if not (field(line, "type") and field(line, "amount")):
        return None
    link = relation.field.name
    found = line.objects.filter(**{f"{link}__in": ids, "type": "refund"}).order_by().values(link)
    return {each[link]: getattr(each["total"], "amount", each["total"]) for each in found.annotate(total=Sum("amount"))}


def settlements(user, params):
    clean = parse(params, PERIOD)
    period = period_of(clean, days=90)
    try:
        record = model("shop.Settlement")
    except Absent:
        note = "Razorpay's settlements are not set up yet: the Finance module fetches them."
        return envelope(
            "settlements", SETTLEMENT_WORDS, SETTLEMENT_COLUMNS, period, configured=False, note=note, rows=[]
        )
    names = {key: field(record, *candidates) for key, candidates in SETTLEMENT_FIELDS.items()}
    found = rows(record.objects.all(), user, "shop.view_settlement")
    if field(record, "livemode"):  # one fetched with test keys is no settlement of the business
        found = live_only(found, "livemode")
    if dated := names["date"]:
        whole_day = record._meta.get_field(dated).get_internal_type() == "DateField"
        start, end = (period.start, period.end + timedelta(days=1)) if whole_day else (period.since, period.until)
        found = found.filter(**{f"{dated}__gte": start, f"{dated}__lt": end}).order_by(f"-{dated}", "-pk")
    else:
        found = found.order_by("-pk")

    shown = list(found[:MAX_SETTLEMENTS])
    refunds = None if names["refunds"] else refund_totals(record, [each.pk for each in shown])
    table = [settlement_row(each, names, refunds) for each in shown]
    return envelope("settlements", SETTLEMENT_WORDS, SETTLEMENT_COLUMNS, period, configured=True, note="", rows=table)


# ---- The print run, recomputed ----

PRINT_RUN_NOTES = {
    "no_forecast": "There is no demand forecast for this title yet, so no size can be recommended: the forecast is "
    "made every night once two seasons of sales and their exam dates are entered.",
    "loss": "At this net price a copy sells at a loss: print none.",
}


def print_run(user, asked, today=None):
    """The newsvendor's sum for a title with the inputs the person typed (`asked`: the title's slug, its net price, its
    print cost and its salvage per copy): the critical ratio Cu ÷ (Cu + Co) from insights.stats, and, from the newest
    demand forecast, the season's demand from now at that percentile, less the copies in stock and on order, as the
    copies to print (`today`: the day "from now" starts, today by default). Nothing is stored: the nightly advice
    (insights/print-runs/) is unchanged."""
    import math

    from shop.models import Product

    from . import stats
    from .api import backtest_summary
    from .jobs import latest
    from .models import ForecastRun, PrintCost

    product = rows(Product.objects.all(), user, "shop.view_product").filter(slug=asked["product"]).first()
    if product is None:
        raise serializers.ValidationError({"product": ["No such title."]})
    ratio = stats.critical_ratio(asked["net_price"], asked["unit_cost"], asked["salvage"])
    today = today or timezone.localdate()
    record = latest(ForecastRun.Kind.FORECAST)
    weeks = []
    if record is not None:
        weeks = list(record.forecasts.filter(product=product, district=None, week_start__gt=today - timedelta(days=7)))
    cost = PrintCost.objects.filter(product=product).first()
    supply = product.stock + (cost.on_order if cost else 0)
    span, target, note = None, None, ""
    if weeks:
        p10, p50, p90 = (sum(getattr(week, name) for week in weeks) for name in ("p10", "p50", "p90"))
        span = {"p10": round(p10), "p50": round(p50), "p90": round(p90), "weeks": len(weeks)}
        target = math.ceil(stats.quantile_between(p10, p50, p90, ratio)) if ratio > 0 else 0
    else:
        note = PRINT_RUN_NOTES["no_forecast"]
    if ratio == 0:
        note = PRINT_RUN_NOTES["loss"]
    backtest = backtest_summary()
    return {
        "product": product.slug,
        "title": product.title,
        "net_price": rupees(asked["net_price"]),
        "unit_cost": rupees(asked["unit_cost"]),
        "salvage": rupees(asked["salvage"]),
        "critical_ratio": round(ratio, 4),
        "percentile": round(ratio * 100),
        "target_quantity": target,
        "supply": supply,
        "recommended_quantity": None if target is None else max(0, target - supply),
        "range": span,
        "method": record.method if record else "",
        "data_as_of": record.data_as_of if record else None,
        "backtest": backtest,
        "shown": bool(backtest and backtest["shown"]),
        "note": note,
    }


# ---- The registry ----


@dataclass(frozen=True)
class Report:
    """A report as the index, the API and the export know it."""

    key: str
    label: str
    summary: str  # one line, for the index
    run: object  # (user, filters) → the answer
    needs: tuple  # the permissions that open it: its own and the data's
    params: dict
    page: str  # the console's page
    columns: list  # of the rows, for the export
    measures: tuple  # the columns that hold numbers (a hidden row says "fewer than k" in them)
    source: str = ""  # the model of another module it reads, which may not be installed yet

    def configured(self):
        """Whether the model it reads is installed (a report with none always is)."""
        try:
            return not self.source or bool(model(self.source))
        except Absent:
            return False

    def required(self):
        """The permissions it asks for now: its own and its data's; while the data's model is not installed there is
        no permission for it, and the report, which only says it is not set up, asks for its own alone."""
        return self.needs if self.configured() else self.needs[:1]


INSIGHTS = "staff.view_insights"
REPORTS = {
    each.key: each
    for each in [
        Report(
            "sales",
            "Sales",
            "Units, gross, discount and net by product, subject, class, board or edition, by day, week or month.",
            sales,
            (INSIGHTS, "shop.view_orderitem"),
            SALES_PARAMS,
            "/reports/sales/",
            SALES_COLUMNS,
            ("orders", "units", "gross", "discount", "net"),
        ),
        Report(
            "sales-by-place",
            "Sales by place",
            "Orders, units and net by state, district or PIN code; small places hidden.",
            sales_by_place,
            (INSIGHTS, "shop.view_orderitem"),
            PLACE_PARAMS,
            "/reports/place/",
            PLACE_COLUMNS,
            ("orders", "units", "net"),
        ),
        Report(
            "codes",
            "Codes",
            "Book codes printed, sold, activated and revoked by batch, and the districts they were redeemed in.",
            codes,
            (INSIGHTS, "learn.view_bookcode"),
            CODES_PARAMS,
            "/reports/codes/",
            CODES_COLUMNS,
            ("printed", "sold", "activated", "activated_7d", "revoked", "activation_rate"),
        ),
        Report(
            "course-health",
            "Course health",
            "Learners, clips, quiz answers and flash cards by subject and chapter, day by day, week by week.",
            course_health,
            (INSIGHTS, "learn.view_progress"),
            HEALTH_PARAMS,
            "/reports/course-health/",
            HEALTH_COLUMNS,
            tuple(each["key"] for each in HEALTH_COLUMNS[1:]),
        ),
        Report(
            "cod",
            "Cash on delivery",
            "The cash couriers collected and have not remitted, by how late, and what was remitted.",
            cod,
            (INSIGHTS, "staff.view_cod"),
            PERIOD,
            "/reports/cod/",
            COD_COLUMNS,
            ("count", "expected", "oldest_expected_on"),
        ),
        Report(
            "settlements",
            "Settlements",
            "Razorpay's settlements: gross, fees, GST, refunds, net and the UTR.",
            settlements,
            (INSIGHTS, "shop.view_settlement"),
            PERIOD,
            "/reports/settlements/",
            SETTLEMENT_COLUMNS,
            (),
            source="shop.Settlement",
        ),
    ]
}


# ---- What the nightly jobs wrote, as reports for the export (the console draws them from insights/api.py) ----


def newest_rows(model_, serializer, **filters):
    """The serialized rows of the newest night of an insights job (its `computed_at`), or []."""
    from django.db.models import Max as Newest

    record = model_.objects.aggregate(newest=Newest("computed_at"))["newest"]
    return (
        (serializer(model_.objects.filter(computed_at=record, **filters), many=True).data, record)
        if record
        else ([], None)
    )


def cohorts(user, params):
    from .api import CohortStatSerializer
    from .models import CohortStat

    found, computed = newest_rows(CohortStat, CohortStatSerializer)
    return envelope(
        "cohorts",
        COHORT_WORDS.format(k=cells.minimum()),
        COHORT_COLUMNS,
        computed_at=computed,
        minimum=cells.minimum(),
        rows=[dict(each) for each in found],
    )


COHORT_COLUMNS = [
    column("cohort_month", "Cohort", "The month the learners' course first opened."),
    column("source", "Source", "How it opened: a book code, a purchase or a staff grant."),
    column("week_index", "Week", "Weeks since the course opened (0: the first)."),
    column("n", "Learners", "Learners counted that week, their exam still ahead."),
    column("active_share", "Active", "The share with any activity that week."),
    column("churned_share", "Gone quiet", "The share with no activity for 14 days."),
]
COHORT_WORDS = (
    "Cohorts of learners by the month their course opened and how, as the share active in each week since, worked out "
    "each night while their exam is ahead. A cohort week of fewer than {k} learners shows no shares."
)


def forecasts(user, params):
    from .api import ForecastSerializer, PrintRunAdviceSerializer  # noqa: F401
    from .jobs import latest
    from .models import ForecastRun

    record = latest(ForecastRun.Kind.FORECAST)
    found = record.forecasts.filter(district=None).select_related("product") if record else []
    return envelope(
        "forecasts",
        FORECAST_WORDS,
        FORECAST_COLUMNS,
        computed_at=record and record.data_as_of,
        rows=[dict(each) for each in ForecastSerializer(found, many=True).data],
    )


FORECAST_COLUMNS = [
    column("title", "Title", "A printed book."),
    column("week_start", "Week", "The week's Monday."),
    column("p10", "P10", "Copies: a week in ten sells less."),
    column("p50", "P50", "Copies: the middle."),
    column("p90", "P90", "Copies: a week in ten sells more."),
    column("n", "Sample", "Copies of history the forecast stands on."),
]
FORECAST_WORDS = (
    "The demand forecast of the newest night, every district together: copies a week from now to the exam, as the "
    "seasonal naive of last season's same week times a growth factor (insights/README.md)."
)

COHORT_REPORT = Report(
    "cohorts",
    "Cohorts",
    "Retention by the month the course opened.",
    cohorts,
    (INSIGHTS,),
    {},
    "/reports/cohorts/",
    COHORT_COLUMNS,
    ("n", "active_share", "churned_share"),
)
FORECAST_REPORT = Report(
    "forecasts",
    "Forecasts",
    "Weekly demand per title with its range.",
    forecasts,
    (INSIGHTS,),
    {},
    "/reports/forecasts/",
    FORECAST_COLUMNS,
    ("p10", "p50", "p90", "n"),
)
EXPORTABLE = {**REPORTS, "cohorts": COHORT_REPORT, "forecasts": FORECAST_REPORT}
