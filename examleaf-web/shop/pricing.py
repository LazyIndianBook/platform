"""The prior price (plan 5.5; research-lms-crm-cms.md 0 and 3.5): from SHOP_PRIOR_PRICE_FROM (the E-Commerce Rules as
amended, 1 January 2027) a reduced selling price is shown beside the lowest selling price of the 30 days before the
reduction. Both come from the product's history (simple-history keeps a version at every save of a product): a price
is in force from the version that set it until the version that changed it; the reduction began when the price in
force now was set; the prior price is the lowest price in force at any moment of the 30 days before that, given only
when the price now is below it. Nothing is typed by staff: the line says what the history says."""

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import DecimalField, F, Value, Window
from django.db.models.functions import Cast, Lag
from django.utils import timezone

from .models import Product

WINDOW = timedelta(days=30)
AMOUNT = DecimalField(max_digits=10, decimal_places=2)


def changes(product_ids):
    """{product id: [(when, price)]}: each product's selling price at each moment it changed, oldest first (the
    versions of its history whose price differs from the version before; its first version counts as one), in one
    query whatever the number of products."""
    if not product_ids:
        return {}
    order = [F("history_date").asc(), F("history_id").asc()]
    rows = (
        Product.history.filter(id__in=list(product_ids))
        .exclude(history_type="-")
        .annotate(amount=Cast("price", AMOUNT))  # a plain decimal: djmoney's lookups stay out of the window's filter
        .annotate(
            before=Window(
                Lag("amount", default=Value(Decimal(-1), output_field=AMOUNT)), partition_by=[F("id")], order_by=order
            )
        )  # fmt: skip
        .exclude(amount=F("before"))
        .order_by("id", "history_date", "history_id")
        .values_list("id", "history_date", "amount")
    )
    found = {}
    for pk, when, amount in rows:
        found.setdefault(pk, []).append((when, amount))
    return found


def lowest_before(history, start):
    """The lowest selling price in force at any moment of the 30 days before `start`: the one in force when they
    began, and each one set during them. None when the history holds none of them (a product newer than that)."""
    since = start - WINDOW
    during = [price for when, price in history if since <= when < start]
    earlier = [price for when, price in history if when < since]
    return min([*during, *earlier[-1:]], default=None)


def in_force(on=None):
    """Whether the rule applies on `on` (today in India by default)."""
    return (on or timezone.localdate()) >= settings.SHOP_PRIOR_PRICE_FROM


def prior_price(product, on=None, history=None):
    """The prior price beside `product`'s selling price now: the lowest selling price of the 30 days before the price
    now was set, when the price now is below it and the rule applies on `on`; else None. `history`: changes()'s list
    of the product, when the caller has it. A price set outside the history (an update that skipped it) counts as set
    now."""
    if not in_force(on):
        return None
    history = changes([product.pk]).get(product.pk, []) if history is None else history
    price = product.price.amount
    start = history[-1][0] if history and history[-1][1] == price else timezone.now()
    lowest = lowest_before(history, start)
    return lowest if lowest is not None and price < lowest else None


def prior_prices(products, on=None):
    """{product id: its prior price, or None} for many products in one query (the storefront's list)."""
    products = list(products)
    if not in_force(on):
        return dict.fromkeys((product.pk for product in products), None)
    history = changes([product.pk for product in products])
    return {product.pk: prior_price(product, on, history.get(product.pk, [])) for product in products}


def proposal(product, price, on=None):
    """What a selling price of `price` rupees set now would show: the lowest price of the 30 days before now (the price
    in force now among them), the prior price it would have (when it is below that lowest), and whether the rule
    applies on `on` and from when. Nothing changes."""
    now = timezone.now()
    lowest = lowest_before(changes([product.pk]).get(product.pk, []), now)
    lowest = min(lowest, product.price.amount) if lowest is not None else product.price.amount
    return {
        "price": price,
        "lowest_in_30_days": lowest,
        "prior_price": lowest if price < lowest else None,
        "window_from": now - WINDOW,
        "applies": in_force(on),
        "applies_from": settings.SHOP_PRIOR_PRICE_FROM,
    }
