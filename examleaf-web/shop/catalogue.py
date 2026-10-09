"""The catalogue's rules (plan 5.5), apart from the staff API that speaks them (shop/staff_catalogue.py), the jobs that
run them in bulk (shop/catalogue_jobs.py) and the approvals that guard prices, coupons and offers (staff.approvals):

- the courier's data: a product with something to post weighs more than 0 g and is packed in a flyer (its standard
  size) or a box with its dimensions; `incomplete()` and `courier_problem()` find those that are not;
- stock: its state against SHOP_LOW_STOCK, the copies held by orders not yet sent, the back-in-stock requests, and
  `set_stock()` by hand with a reason (audited; a sale's change of stock never waits for it);
- an ISBN once per format: unique among the products of the same kind;
- single-use codes, made in batches for a school;
- coupons and offers made and changed through their approvals: every field checked here (the dark-pattern guardrails
  among them), a change applied in one version of its history;
- the versions of a product, coupon, offer or shipping rate, as staff read them."""

import re
import secrets
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Count, Exists, Max, OuterRef, Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from djmoney.money import Money
from rest_framework import serializers

from content.isbn import validate_isbn13
from staff import audit

from . import copy_rules
from .models import (
    BundleItem,
    Category,
    Collection,
    Coupon,
    CouponCode,
    Offer,
    Order,
    OrderItem,
    Product,
    StockAlert,
    live_mode,
)

GOODS = [Product.Kind.SAMPLE_PAPERS, Product.Kind.SOLUTIONS]  # copies of their own; a bundle sells its books'
BOX = Product.Packaging.BOX
SIZES = ("length_cm", "width_cm", "height_cm")


def invalid(field, message):
    return serializers.ValidationError({field: [message]})


# ---- The courier's data (plan 7.7: weight, dimensions or a packaging kind) ----


def incomplete(products):
    """Those of `products` the courier cannot be quoted for: with something to post, and no weight (a bundle: neither
    its own nor every book's), or neither dimensions nor a packaging kind, or a box without its dimensions."""
    goods = Q(kind__in=GOODS)
    books = BundleItem.objects.filter(bundle=OuterRef("pk")).exclude(product__kind=Product.Kind.DIGITAL)
    bundle = Q(kind=Product.Kind.BUNDLE) & Exists(books)
    no_weight = (goods & Q(weight_grams=0)) | (
        bundle & Q(weight_grams=0) & Exists(books.filter(product__weight_grams=0))
    )
    no_size = Q(length_cm__isnull=True) | Q(width_cm__isnull=True) | Q(height_cm__isnull=True)
    no_packing = (Q(packaging="") | Q(packaging=BOX)) & no_size
    return products.filter(no_weight | ((goods | bundle) & no_packing))


def courier_problem(product, items):
    """Why the courier cannot be quoted for `product` ("" when it can): `items` are its bundle lines with their
    products ([] for anything but a bundle). The rule incomplete() finds in the database."""
    books = [item for item in items if not item.product.is_digital]
    if product.kind == Product.Kind.DIGITAL or (product.kind == Product.Kind.BUNDLE and not books):
        return ""
    if product.kind == Product.Kind.BUNDLE:
        if not product.weight_grams and any(not item.product.weight_grams for item in books):
            return "No weight: weigh the bundle, or each of its books."
    elif not product.weight_grams:
        return "No weight: weigh one copy, in grams."
    sized = None not in (product.length_cm, product.width_cm, product.height_cm)
    if product.packaging == BOX and not sized:
        return "A box needs its length, width and height."
    if not product.packaging and not sized:
        return "Neither a packaging kind nor dimensions: a flyer, or the box's size."
    return ""


def check_physical(kind, values, items=()):
    """The courier's fields of a product of `kind` as they will be (`values`: weight_grams, length_cm, width_cm,
    height_cm, packaging; `items`: a bundle's lines), checked: dimensions come all three or none; a book weighs more
    than 0 g, and a bundle with books too unless each of its books does; a box has its dimensions; something to post
    has a packaging kind or dimensions. Raises ValidationError by field."""
    sizes = [values.get(name) for name in SIZES]
    if any(size is not None for size in sizes) and None in sizes:
        raise invalid("length_cm", "Give the length, width and height, or none (a flyer).")
    books = [item for item in items if not item.product.is_digital]
    if kind == Product.Kind.DIGITAL or (kind == Product.Kind.BUNDLE and not books):
        return
    if kind in GOODS and not values.get("weight_grams"):
        raise invalid("weight_grams", "A book needs its weight in grams, for the courier's quote.")
    if (
        kind == Product.Kind.BUNDLE
        and not values.get("weight_grams")
        and any(not i.product.weight_grams for i in books)
    ):
        raise invalid("weight_grams", "Weigh the bundle, or give each of its books a weight first.")
    if values.get("packaging") == BOX and None in sizes:
        raise invalid("length_cm", "A box needs its length, width and height.")
    if not values.get("packaging") and None in sizes:
        raise invalid("packaging", "Choose a flyer, or give the box's dimensions.")


# ---- Stock ----


def available(product, items):
    """The copies that may be sold now (Product.available, from its prefetched bundle lines `items`)."""
    if product.kind == Product.Kind.DIGITAL:
        return 1
    if product.kind != Product.Kind.BUNDLE:
        return product.stock
    books = [item for item in items if not item.product.is_digital]
    if not books:
        return 1 if items else 0  # a bundle of courses: one at a time, as the cart sells it
    return min(item.product.stock // item.quantity for item in books)


def stock_state(product, items):
    """(copies to sell now, "none" for a course or a bundle of courses, else "out", "low" (a book below
    SHOP_LOW_STOCK, as the morning's email counts) or "in_stock")."""
    count = available(product, items)
    if product.kind == Product.Kind.DIGITAL or (
        product.kind == Product.Kind.BUNDLE and items and all(item.product.is_digital for item in items)
    ):
        return count, "none"
    if count < 1:
        return count, "out"
    return count, "low" if product.kind in GOODS and count < settings.SHOP_LOW_STOCK else "in_stock"


def stock_filter(products, state):
    """The books (copies of their own) in a stock state: out, low or in_stock."""
    books = products.filter(kind__in=GOODS)
    if state == "out":
        return books.filter(stock=0)
    if state == "low":
        return books.filter(stock__gt=0, stock__lt=settings.SHOP_LOW_STOCK)
    return books.filter(stock__gte=settings.SHOP_LOW_STOCK)


def held_copies(product_ids):
    """{book id: {"reserved": copies taken by orders placed and not yet sent (still on the shelf), "awaiting": copies
    in orders waiting for an online payment (taken once paid)}}, a bundle's line counted as its books'. Test orders on
    the live site are left out, as from every number."""
    wanted, found = set(product_ids), {}
    open_orders = Order.objects.filter(
        Q(status__in=[Order.Status.PAID, Order.Status.PACKED], stock_reserved=True)
        | Q(status=Order.Status.PENDING, stock_reserved=True)
        | Q(status=Order.Status.PENDING, placed_at__isnull=True)
    )
    if live_mode():
        open_orders = open_orders.filter(livemode=True)
    items = OrderItem.objects.filter(order__in=open_orders).select_related("order", "product")
    for item in items.prefetch_related("product__bundle_items"):
        product = item.product
        if product.kind == Product.Kind.BUNDLE:
            lines = {line.product_id: line.quantity * item.quantity for line in product.bundle_items.all()}
        else:
            lines = {product.pk: item.quantity}
        bucket = "reserved" if item.order.stock_reserved else "awaiting"
        for pk, copies in lines.items():
            if pk in wanted:
                found.setdefault(pk, {"reserved": 0, "awaiting": 0})[bucket] += copies
    return found


def alert_counts(product_ids):
    """{product id: (requests waiting, the latest one's time)} of "email me when it is back" (no address leaves)."""
    rows = StockAlert.objects.filter(product__in=product_ids).values("product")
    rows = rows.annotate(count=Count("pk"), last=Max("created"))
    return {row["product"]: (row["count"], row["last"]) for row in rows}


def set_stock(product, stock, reason, *, by=None, request=None, expected=None):
    """A book's copies set by hand (the printer's delivery, a count), with the reason, audited. `expected`: the count
    the person read; orders meanwhile change it, and then nothing is set (they read it again). A bundle's copies are
    its books', a course has none. Raises ValidationError."""
    with transaction.atomic():
        locked = Product.objects.select_for_update().get(pk=product.pk)
        if locked.kind not in GOODS:
            raise invalid("stock", "Only a book has copies of its own: a bundle sells its books', a course has none.")
        if expected is not None and locked.stock != expected:
            raise invalid("expected", f"Orders changed it meanwhile: {locked.stock} now. Read it again, then set it.")
        before = locked.stock
        Product.objects.filter(pk=locked.pk).update(stock=stock, modified=timezone.now())  # no version: as a sale
        changes = {"stock": [before, stock]}
        audit.record("catalogue.stock_set", request=request, actor=by, target=locked, reason=reason, changes=changes)
    locked.stock = stock
    return locked


# ---- ISBN: one per format ----


def isbn_problem(isbn, kind, exclude=None):
    """Why `isbn` (valid: checked first, ValidationError otherwise) cannot be this product's: another product of the
    same kind (a format) has it. None otherwise. Compared digit for digit, hyphens aside."""
    digits = validate_isbn13(isbn)
    same = Product.objects.filter(kind=kind).exclude(isbn="").exclude(pk=exclude).only("pk", "title", "isbn")
    for other in same:  # ponytail: read whole, fine for a catalogue of hundreds; a digits column if it grows
        if re.sub(r"[\s-]", "", other.isbn) == digits:
            return f"{other.title} has this ISBN already: one ISBN for each format."
    return None


# ---- Single-use codes ----

CODE_LETTERS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0, O, 1, I or L: read from paper and typed
CODE_LENGTH = 8
PREFIX = re.compile(r"[A-Z0-9]{2,10}")
MAX_CODES = 5000  # a batch: a large school's pupils


def make_codes(coupon, count, prefix, note="", job=None):
    """`count` single-use codes of `coupon` (PREFIX-XXXXXXXX: 31 letters and figures to the power of 8), none another
    code nor a coupon's: a clash, even with another batch made at the same moment, is drawn again. Returns them."""
    made = []
    while len(made) < count:
        drawn = set()
        while len(drawn) < count - len(made):
            drawn.add(f"{prefix}-{''.join(secrets.choice(CODE_LETTERS) for _ in range(CODE_LENGTH))}")
        drawn -= set(Coupon.objects.filter(code__in=drawn).values_list("code", flat=True))
        rows = [CouponCode(coupon=coupon, code=code, note=note, job=job) for code in sorted(drawn)]
        CouponCode.objects.bulk_create(rows, batch_size=500, ignore_conflicts=True)  # a code taken: left out
        made += sorted(CouponCode.objects.filter(code__in=drawn, coupon=coupon, job=job).values_list("code", flat=True))
    return made


# ---- Coupons and offers: their fields checked, their changes applied (through staff.approvals) ----

COUPON_DEFAULTS = {
    "kind": "percent",
    "value": None,
    "min_order": "0.00",
    "valid_from": None,
    "valid_until": None,
    "max_uses": None,
    "max_uses_per_customer": 1,
    "is_active": True,
    "description": "",
    "note": "",
    "first_order_only": False,
    "stackable": True,
    "single_use": False,
    "include_products": [],
    "include_categories": [],
    "exclude_products": [],
    "exclude_categories": [],
}
COUPON_LISTS = {
    "include_products": Product,
    "include_categories": Category,
    "exclude_products": Product,
    "exclude_categories": Category,
}
OFFER_DEFAULTS = {
    "name": "",
    "banner": "",
    "kind": "percent",
    "value": None,
    "scope": Offer.Scope.CART,
    "min_quantity": 0,
    "min_value": "0.00",
    "valid_from": None,
    "valid_until": None,
    "max_uses": None,
    "max_uses_per_customer": None,
    "combinable": True,
    "is_active": True,
    "show_countdown": False,
    "products": [],
    "categories": [],
    "collections": [],
}
OFFER_LISTS = {"products": Product, "categories": Category, "collections": Collection}
DECIMALS = {"value", "min_order", "min_value"}
MOMENTS = {"valid_from", "valid_until"}
LIMIT = Decimal("1000000")


def rupees(value, field, positive=False):
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except InvalidOperation, ValueError, TypeError:
        raise invalid(field, "A number of rupees.") from None
    if not amount.is_finite() or amount < 0 or (positive and amount == 0) or amount >= LIMIT:
        raise invalid(field, "More than 0, below ₹10,00,000." if positive else "From 0, below ₹10,00,000.")
    return amount


def whole(value, field, low=0, high=1_000_000):
    """A whole number from `low` to `high`, or None for empty."""
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, int | str) or not str(value).isdigit():
        raise invalid(field, f"A whole number from {low}, or empty.")
    if not low <= int(value) <= high:
        raise invalid(field, f"A whole number from {low:,} to {high:,}.")
    return int(value)


def moment(value, field):
    """A date and time (ISO 8601; a day alone is its start in India) as the payload keeps it (UTC, ISO), or None."""
    if value in (None, ""):
        return None
    when = parse_datetime(str(value))
    if when is None and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(value)):
        when = datetime.fromisoformat(f"{value}T00:00:00")
    if when is None:
        raise invalid(field, "A date and time (ISO 8601).")
    return audit.plain(timezone.make_aware(when) if timezone.is_naive(when) else when)


def flag(value, field):
    if not isinstance(value, bool):
        raise invalid(field, "true or false.")
    return value


def words(value, field, limit, *, required=False, dated=False, checked=True):
    """A customer's words: trimmed, within `limit`, and (`checked`) free of the dark patterns' phrases
    (shop/copy_rules.py; `dated`: the thing ends on a real date)."""
    value = " ".join(str(value or "").split())
    if required and not value:
        raise invalid(field, "Required.")
    if len(value) > limit:
        raise invalid(field, f"At most {limit} characters.")
    if checked:
        try:
            copy_rules.check(value, dated=dated)
        except DjangoValidationError as error:
            raise serializers.ValidationError({field: error.messages}) from None
    return value


def slugs(value, field, model):
    """Slugs of `model` (products, categories, collections), each found: sorted, once each."""
    if value in (None, ""):
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value) or len(value) > 500:
        raise invalid(field, "A list of slugs (500 at most).")
    wanted = sorted(set(value))
    found = set(model.objects.filter(slug__in=wanted).values_list("slug", flat=True))
    if missing := [slug for slug in wanted if slug not in found]:
        raise invalid(field, f"Not found: {', '.join(missing[:10])}.")
    return wanted


def current(obj, name, lists):
    """A field of a coupon or an offer as payloads hold it: rupees as text, times as ISO text, relations' slugs."""
    if name in lists:
        return sorted(getattr(obj, name).values_list("slug", flat=True))
    value = getattr(obj, name)
    if isinstance(value, Money):
        return f"{value.amount:.2f}"
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    return audit.plain(value)


def state_of(obj, defaults, lists):
    return {name: current(obj, name, lists) for name in defaults}


def common_fields(payload, kind_field_values):
    """The fields coupons and offers share, checked."""
    clean = {}
    if "kind" in payload:
        if payload["kind"] not in kind_field_values:
            raise invalid("kind", "percent or fixed.")
        clean["kind"] = payload["kind"]
    if "value" in payload:
        clean["value"] = str(rupees(payload["value"], "value", positive=True))
    for name in MOMENTS & set(payload):
        clean[name] = moment(payload[name], name)
    for name in {"max_uses", "max_uses_per_customer"} & set(payload):
        clean[name] = whole(payload[name], name, low=1)
    return clean


def check_terms(state, creating):
    if state["valid_until"] and state["valid_from"] and state["valid_until"] <= state["valid_from"]:
        raise invalid("valid_until", "It ends after it starts.")
    if creating and state["valid_until"] and state["valid_until"] <= audit.plain(timezone.now()):
        raise invalid("valid_until", "Its end has passed already.")
    if state["kind"] == Coupon.Kind.PERCENT and state["value"] is not None and Decimal(state["value"]) > 100:
        raise invalid("value", "At most 100 per cent.")


def coupon_fields(payload, before=None):
    """The fields a coupon's payload gives, checked (`before`: the coupon changed, else a new one): {name: value} as
    JSON, a new one's required ones there, a change's only those that differ. Unknown names are refused: a coupon names
    no account, nor a list of them (plan 10.1: different prices only through published channels)."""
    if unknown := sorted(set(payload) - set(COUPON_DEFAULTS)):
        raise invalid(unknown[0], "Not a field of a coupon.")
    if before is None and payload.get("value") in (None, ""):
        raise invalid("value", "Required.")
    clean = common_fields(payload, Coupon.Kind.values)
    if "min_order" in payload:
        clean["min_order"] = str(rupees(payload["min_order"] or 0, "min_order"))
    for name in {"is_active", "first_order_only", "stackable", "single_use"} & set(payload):
        clean[name] = flag(payload[name], name)
    if "description" in payload:
        clean["description"] = words(payload["description"], "description", 200)
    if "note" in payload:
        clean["note"] = words(payload["note"], "note", 200, checked=False)  # staff's own words, never shown
    for name, model in COUPON_LISTS.items():
        if name in payload:
            clean[name] = slugs(payload[name], name, model)
    state = state_of(before, COUPON_DEFAULTS, COUPON_LISTS) if before else dict(COUPON_DEFAULTS)
    after = {**state, **clean}
    check_terms(after, creating=before is None)
    for kind in ("products", "categories"):
        if both := set(after[f"include_{kind}"]) & set(after[f"exclude_{kind}"]):
            raise invalid(f"exclude_{kind}", f"Both in and out: {', '.join(sorted(both))}.")
    return clean if before is None else {name: value for name, value in clean.items() if value != state[name]}


def offer_fields(payload, before=None):
    """The fields an offer's payload gives, checked as coupon_fields() checks a coupon's, with the dark-pattern
    guardrails (plan 5.5): a countdown only with a real end date, which never moves later once the countdown has shown
    while the offer ran; no guilt-trip or false-urgency words in its name or banner."""
    if unknown := sorted(set(payload) - set(OFFER_DEFAULTS)):
        raise invalid(unknown[0], "Not a field of an offer.")
    if before is None:
        for name in ("name", "value"):
            if payload.get(name) in (None, ""):
                raise invalid(name, "Required.")
    clean = common_fields(payload, Coupon.Kind.values)
    if "scope" in payload:
        if payload["scope"] not in Offer.Scope.values:
            raise invalid("scope", f"One of {', '.join(Offer.Scope.values)}.")
        clean["scope"] = payload["scope"]
    if "min_value" in payload:
        clean["min_value"] = str(rupees(payload["min_value"] or 0, "min_value"))
    if "min_quantity" in payload:
        clean["min_quantity"] = whole(payload["min_quantity"], "min_quantity", high=32767) or 0
    for name in {"combinable", "is_active", "show_countdown"} & set(payload):
        clean[name] = flag(payload[name], name)
    for name, model in OFFER_LISTS.items():
        if name in payload:
            clean[name] = slugs(payload[name], name, model)
    state = state_of(before, OFFER_DEFAULTS, OFFER_LISTS) if before else dict(OFFER_DEFAULTS)
    after = {**state, **clean}
    dated = bool(after["valid_until"])  # "limited time" is true of an offer that ends on a date
    for name, limit in (("name", 80), ("banner", 160)):
        if name in payload:
            clean[name] = after[name] = words(payload[name], name, limit, required=name == "name", dated=dated)
        elif "valid_until" in clean and not dated and after[name]:
            words(after[name], name, limit)  # its end taken away: its words checked again without one
    check_terms(after, creating=before is None)
    check_offer(after, before)
    return clean if before is None else {name: value for name, value in clean.items() if value != state[name]}


def check_offer(state, before=None):
    """An offer's rules across its fields, on what it will be (`before`: as it is, for its countdown's history)."""
    scope = state["scope"]
    for name in OFFER_LISTS:
        if name == scope and not state[name]:
            raise invalid(name, f"Choose the {name} it covers.")
        if name != scope and state[name]:
            raise invalid(name, f"It covers {Offer.Scope(scope).label}: leave the {name} empty.")
    if state["show_countdown"] and not state["valid_until"]:
        raise invalid("show_countdown", "A countdown needs a real end date: give it one, or show no countdown.")
    if before is not None and before.valid_until:
        end = current(before, "valid_until", ())
        if (state["valid_until"] is None or state["valid_until"] > end) and counted_down(before):
            raise invalid(
                "valid_until",
                "A countdown to its end showed while it ran: that end is real and does not move later. End it, and "
                "make a new offer.",
            )


def counted_down(offer):
    """Whether a countdown to its end showed at any moment it was running (now, or in its history)."""
    now = timezone.now()
    if offer.valid_from > now:
        return False
    rows = list(offer.history.order_by("history_date", "history_id").values_list("history_date", "show_countdown"))
    for (_when, shown), following in zip(rows, [*rows[1:], (None, None)], strict=True):
        if shown and (following[0] or now) >= offer.valid_from:
            return True
    return offer.show_countdown


def depth(state, now=None):
    """How deep a coupon's or an offer's discount goes, in per cent: its percentage, or a fixed amount's share of the
    smallest order it applies to (no minimum: 100); 0 while it is switched off or once it has ended (the approvals'
    rule: making a discount deeper is what needs a second person beyond the maker's limit)."""
    ended = state.get("valid_until") and state["valid_until"] <= audit.plain(now or timezone.now())
    if not state.get("is_active", True) or ended or state.get("value") is None:
        return Decimal(0)
    value = Decimal(state["value"])
    if state.get("kind", "percent") == Coupon.Kind.PERCENT:
        return value.quantize(Decimal("0.01"))
    least = Decimal(state.get("min_order") or state.get("min_value") or 0)
    return (Decimal(100) if not least else min(Decimal(100), value * 100 / least)).quantize(Decimal("0.01"))


def apply_fields(obj, values, lists, *, by=None, reason=""):
    """Checked fields written onto a coupon or an offer, saved with who and why on its history: a change in one
    version (its relations set within it); a new one as made, then each relation set (simple-history's own)."""
    for name, value in values.items():
        if name in lists:
            continue
        if name in MOMENTS:
            value = parse_datetime(value) if value else (timezone.now() if name == "valid_from" else None)
        elif name in DECIMALS:
            value = Decimal(value)
        setattr(obj, name, value)
    obj._history_user, obj._change_reason = by, (reason or "")[:100]
    relations = {name: lists[name].objects.filter(slug__in=value) for name, value in values.items() if name in lists}
    if obj.pk is None or not relations:
        obj.save()
        for name, chosen in relations.items():
            getattr(obj, name).set(chosen)
        return obj
    obj.skip_history_when_saving = True
    try:
        obj.save()
        for name, chosen in relations.items():
            getattr(obj, name).set(chosen)
    finally:
        del obj.skip_history_when_saving
    obj.save()
    return obj


def changed_since(obj, changes, defaults, lists):
    """The fields of `changes` ({name: [before, after]}) whose value is no longer `before` (changed meanwhile)."""
    return [
        name for name, (before, _after) in changes.items() if name in defaults and current(obj, name, lists) != before
    ]


# ---- Versions (simple-history), as staff read them ----

HIDDEN = {"modified", "created", "price_currency", "mrp_currency", "min_order_currency", "min_value_currency"}
HIDDEN |= {"fee_currency", "free_above_currency"}


def shown(value):
    if isinstance(value, Money):
        return f"{value.amount:.2f}"
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    return audit.plain(value)


def versions(page, older, owner, relations=None):
    """[{id, at, by, by_name, reason, type, changes: [{field, before, after}]}] of a page of versions newest first;
    `older`: the version before the page's last (its changes are against it), or None; a relation's rows as the
    related objects' slugs (`relations`: {field: model}; `owner`: the through rows' own key, "coupon", "offer")."""
    rows, wanted = [], {}
    for index, version in enumerate(page):
        previous = page[index + 1] if index + 1 < len(page) else older
        changes = []
        for change in version.diff_against(previous).changes if previous is not None else []:
            if change.field in HIDDEN:
                continue
            if isinstance(change.old, list) or isinstance(change.new, list):  # a relation: its rows' other ids
                before, after = (
                    sorted(r[k] for r in rows_ or [] for k in r if k != owner) for rows_ in (change.old, change.new)
                )
                wanted.setdefault(change.field, set()).update([*before, *after])
            else:
                before, after = shown(change.old), shown(change.new)
            changes.append({"field": change.field, "before": before, "after": after})
        user = version.history_user
        rows.append(
            {
                "id": version.history_id,
                "at": version.history_date,
                "by": version.history_user_id,
                "by_name": (user.full_name or user.email) if user else "",
                "reason": version.history_change_reason or "",
                "type": version.history_type,
                "changes": changes,
            }
        )
    names = {
        field: dict(relations[field].objects.filter(pk__in=ids).values_list("pk", "slug"))
        for field, ids in wanted.items()
        if relations and field in relations
    }
    for row in rows:
        for change in row["changes"]:
            if change["field"] in names:
                slug = names[change["field"]]
                change["before"] = [slug.get(pk, f"#{pk}") for pk in change["before"]]
                change["after"] = [slug.get(pk, f"#{pk}") for pk in change["after"]]
    return rows
