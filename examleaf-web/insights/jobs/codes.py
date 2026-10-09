"""Book codes printed and redeemed per print run (batch) and district (research-b2b-predictive.md 4.6). A code's
district is its redeemer's last order of the code's subject placed before the redemption (a book bought online), by
its PIN code; codes from books bought in a shop have no order: "unknown". These are students, so districts with fewer
than 5 redemptions in a batch are counted together as "other districts"."""

from collections import Counter, defaultdict
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from learn.models import BookCode

from ..models import CodeActivationStat
from . import HIDDEN_BELOW, UNKNOWN, counted_orders, district, districts_of, save_stats

OTHER = "other districts"


def redeemers_orders(users):
    """{user id: [(placed at, a subject the order holds, address snapshot)]} of these users' orders that count."""
    orders, fields = defaultdict(list), ["user", "placed_at", "items__product__subject", "shipping_address"]
    for user, placed_at, subject, address in counted_orders().filter(user__in=users).values_list(*fields):
        orders[user].append((placed_at, subject, address))
    return orders


@transaction.atomic
def code_activation(today=None):
    """For each batch, a row of its codes printed, redeemed and redeemed in the last 7 days, and a row per district."""
    now = timezone.now()
    week_ago = now - timedelta(days=7)
    codes = list(BookCode.objects.values_list("batch", "subject", "redeemed_by", "redeemed_at"))
    orders = redeemers_orders({user for _, _, user, redeemed_at in codes if redeemed_at and user})
    known = districts_of(address for rows in orders.values() for *_, address in rows)
    printed, redeemed, recent = Counter(), Counter(), Counter()
    for batch, subject, user, redeemed_at in codes:
        printed[batch] += 1
        if redeemed_at is None:
            continue
        bought = [
            (placed_at, address)
            for placed_at, ordered, address in orders.get(user, [])
            if placed_at <= redeemed_at and (subject is None or ordered == subject)
        ]
        where = district(max(bought, key=lambda order: order[0])[1], known) if bought else UNKNOWN
        for key in ((batch, None), (batch, where)):
            redeemed[key] += 1
            recent[key] += redeemed_at >= week_ago
    rows = []
    for batch in sorted(printed):
        total = {"batch": batch, "computed_at": now}
        rows.append(
            CodeActivationStat(
                **total, printed=printed[batch], redeemed=redeemed[batch, None], redeemed_7d=recent[batch, None]
            )
        )
        places, places_7d = Counter(), Counter()
        for (of, where), count in redeemed.items():
            if of == batch and where is not None:
                name = where if count >= HIDDEN_BELOW or where == UNKNOWN else OTHER
                places[name] += count
                places_7d[name] += recent[of, where]
        rows += [
            CodeActivationStat(**total, district=name, redeemed=count, redeemed_7d=places_7d[name])
            for name, count in sorted(places.items())
        ]
    return save_stats(CodeActivationStat, rows, now)
