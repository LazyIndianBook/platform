"""Demand per title and week of the season, its backtest, and the print-run advice (research-b2b-predictive.md 4.2).

A title's series is its line: every printed book of its subject and kind (Physics Sample Papers 2026, 2027 …), since a
new edition is a new product. So a new title takes the previous title's curve, scaled to its first weeks by the
growth factor, and a line with two seasons of sales can be backtested whatever its editions."""

import math
from collections import defaultdict
from datetime import timedelta
from itertools import groupby

from django.utils import timezone

from shop.models import OrderItem

from .. import stats
from ..models import Backtest, Forecast, ForecastRun, PrintCost, PrintRunAdvice
from . import WEEKS, counted_orders, history, latest, printed_books, run, seasons_around, week_index, week_start

FORECAST = "seasonal naive by week of season × damped growth (season to date ÷ the same weeks last season)"
BACKTEST = "rolling origin across last season: seasonal naive × damped growth against the seasonal naive"
PRINT_RUN = "newsvendor: the season's demand from now at the critical ratio Cu ÷ (Cu + Co)"
HORIZONS = (1, 4)  # weeks ahead: next week, and about a reprint's lead time
SHOWN_HORIZON = 4  # the backtest that decides whether a line's growth factor is used, and whether the panel shows it
LEFTOVER_SHARE = 0.10  # copies left at the exam above this share of the supply: an alert (a distributor's return cap)


def seasons_and_lines(books, today):
    """[(this, last and before seasons, {(subject, kind): [the line's books]})], one per board and class.
    ponytail: two different titles of one subject and kind would share a line; add a title family when that happens."""
    groups = defaultdict(lambda: defaultdict(list))
    for book in books:
        groups[book.subject.board_id, book.subject.class_level_id][book.subject_id, book.kind].append(book)
    return [(*seasons_around(board, level, today), lines) for (board, level), lines in groups.items()]


def line_sales(sold, books):
    """A line's weekly copies and its copies by district: its books' added up."""
    weeks, where = [0.0] * WEEKS, defaultdict(float)
    for book in books:
        book_weeks, book_where = sold[book.pk]
        weeks = [a + b for a, b in zip(weeks, book_weeks, strict=True)]
        for name, copies in book_where.items():
            where[name] += copies
    return weeks, where


def latest_backtests(horizon):
    """{product id: shown} from the newest backtest, `horizon` weeks ahead."""
    record = latest(ForecastRun.Kind.BACKTEST)
    rows = record.backtests.filter(horizon_weeks=horizon, product__isnull=False) if record else []
    return {row.product_id: row.shown for row in rows}


def forecast_demand(today=None):
    """Weekly copies of each wanted title (on sale, or with a print cost) from this week to the exam, in all and per
    district (top-down by last season's shares), with P10 and P90 from last season's one-week-ahead errors or the
    stated default spread. The growth factor is left out (1) for a line whose backtest found it worse than none. Two
    wanted titles of one line share its forecast by their sales this season (equally before any)."""
    today = today or timezone.localdate()
    tested = latest_backtests(SHOWN_HORIZON)
    params = {"damping_weeks": stats.DAMPING_WEEKS, "default_spread": stats.DEFAULT_SPREAD, "titles": {}}
    with run(ForecastRun.Kind.FORECAST, FORECAST, **params) as record:
        rows, notes = [], []
        for this, last, before, lines in seasons_and_lines(list(printed_books()), today):
            if this is None or last is None:
                names = sorted({str(book.subject) for books in lines.values() for book in books})
                notes.append(f"{', '.join(names)}: enter {'the next' if this is None else 'last'} season's exam dates")
                continue
            ids = {book.pk for books in lines.values() for book in books}
            sold_this, sold_last = history(this, ids), history(last, ids)
            sold_before = history(before, ids) if before else None
            done = week_index(this, today) or 0  # weeks of this season already over
            for books in lines.values():
                if not (targets := [book for book in books if book.wanted]):
                    continue
                base, where = line_sales(sold_last, books)
                if not sum(base):
                    notes.append(f"{targets[0]}: its line sold nothing last season")
                    continue
                now = line_sales(sold_this, books)[0]
                growth = stats.damped_growth(sum(now[:done]), sum(base[:done]), done)
                if any(tested.get(book.pk) is False for book in targets):
                    growth = 1.0  # backtested: the growth factor did worse than the seasonal naive
                low, high = stats.DEFAULT_SPREAD
                earlier = line_sales(sold_before, books)[0] if sold_before is not None else []
                if sum(earlier):
                    low, high = stats.spread(stats.rolling_origin(earlier, base, 1))
                own = [sum(sold_this[book.pk][0][:done]) for book in targets]
                shares = [mine / sum(own) if sum(own) else 1 / len(targets) for mine in own]
                n, total = round(sum(base) + sum(now[:done])), sum(where.values())
                for book, share in zip(targets, shares, strict=True):
                    for index in range(done, WEEKS):
                        p50 = base[index] * growth * share
                        week = {"run": record, "product": book, "week_start": week_start(this, index), "n_history": n}
                        rows.append(Forecast(**week, p10=p50 * low, p50=p50, p90=p50 * high))
                        for name, copies in where.items() if p50 else ():  # top-down: last season's district shares
                            part = p50 * copies / total
                            rows.append(Forecast(**week, district=name, p10=part * low, p50=part, p90=part * high))
                    record.params["titles"][book.slug] = {
                        "growth": round(growth, 4),
                        "tested": book.pk in tested,
                        "spread": [round(low, 3), round(high, 3)],
                        "weeks_done": done,
                        "share_of_line": round(share, 4),
                    }
        Forecast.objects.bulk_create(rows, batch_size=1000)
        record.notes = "; ".join(notes)
        if not rows:
            record.status = ForecastRun.Status.SKIPPED
    return record


def scored(record, book, horizon, points):
    error = stats.mase(points)
    return Backtest(
        run=record,
        product=book,
        horizon_weeks=horizon,
        wape=stats.wape(points),
        mase_vs_seasonal_naive=error,
        n_weeks=len(points),
        shown=error is not None and error < 1,
    )


def backtest(today=None):
    """Last season's weeks forecast from the season before by a rolling origin, for each line with two seasons of
    sales: WAPE and seasonal MASE of the forecast against the seasonal naive, 1 and 4 weeks ahead, stored for each
    wanted title of the line (`shown`: it beats the naive). The row without a title sums every line's weeks."""
    today = today or timezone.localdate()
    with run(ForecastRun.Kind.BACKTEST, BACKTEST, horizons=list(HORIZONS), damping_weeks=stats.DAMPING_WEEKS) as record:
        rows, totals, notes = [], defaultdict(list), set()
        for _, last, before, lines in seasons_and_lines(list(printed_books()), today):
            if last is None or before is None:
                notes.add("A board and class has fewer than two past seasons entered.")
                continue
            ids = {book.pk for books in lines.values() for book in books}
            sold_last, sold_before = history(last, ids), history(before, ids)
            for books in lines.values():
                targets = [book for book in books if book.wanted]
                actual, earlier = line_sales(sold_last, books)[0], line_sales(sold_before, books)[0]
                if not (targets and sum(actual) and sum(earlier)):
                    continue
                for horizon in HORIZONS:
                    points = stats.rolling_origin(earlier, actual, horizon)
                    rows += [scored(record, book, horizon, points) for book in targets]
                    totals[horizon].append(points)
        for horizon, lines_points in totals.items():
            summed = [tuple(map(sum, zip(*week, strict=True))) for week in zip(*lines_points, strict=True)]
            rows.append(scored(record, None, horizon, summed))
        Backtest.objects.bulk_create(rows)
        record.notes = " ".join(sorted(notes))
        if not rows:
            record.status = ForecastRun.Status.SKIPPED
    return record


def net_price(product, today):
    """What a copy sold for over the last year, after its share of the discounts (the title's own order lines: a
    bundle's price is not split back to its books); the selling price before it sold."""
    lines = OrderItem.objects.filter(
        order__in=counted_orders(), product=product, order__placed_at__date__gt=today - timedelta(days=365)
    )
    copies = paid = 0
    for line in lines:
        copies += line.quantity
        paid += line.unit_price.amount * line.quantity - (line.discount.amount if line.discount is not None else 0)
    return round(paid / copies, 2) if copies else product.price.amount


def advise_print_run(today=None):
    """For each title of the newest forecast that has a print cost: the critical ratio, the season's demand from now at
    that quantile (the target), the copies to print now (the target less stock and copies on order), the reprint
    trigger (the P90 of the demand over the reprint lead time), the weeks the supply lasts and the copies left at the
    exam; "act" to reprint now, "watch" to print more for the season or to move a leftover above 10 %."""
    today = today or timezone.localdate()
    forecast = latest(ForecastRun.Kind.FORECAST)
    with run(ForecastRun.Kind.PRINT_RUN, PRINT_RUN, forecast_run=forecast and forecast.pk) as record:
        if forecast is None:
            record.status, record.notes = ForecastRun.Status.SKIPPED, "No demand forecast yet."
            return record
        costs = {cost.product_id: cost for cost in PrintCost.objects.select_related("product")}
        weeks = forecast.forecasts.filter(district=None, week_start__gt=today - timedelta(days=7))
        rows, missing = [], []
        for product_id, forecasts in groupby(weeks.order_by("product", "week_start"), key=lambda f: f.product_id):
            forecasts = list(forecasts)
            if (cost := costs.get(product_id)) is None:
                missing.append(str(forecasts[0].product))
                continue
            rows.append(advice(record, cost, forecasts, today))
        PrintRunAdvice.objects.bulk_create(rows)
        record.notes = f"No print cost entered for {', '.join(missing)}." if missing else ""
        if not rows:
            record.status = ForecastRun.Status.SKIPPED
    return record


def advice(record, cost, forecasts, today):
    """One title's PrintRunAdvice from its weekly forecasts (this week to the exam)."""
    product, lead = cost.product, cost.lead_time_weeks
    price = net_price(product, today)
    ratio = stats.critical_ratio(price, cost.unit_cost, cost.salvage)
    p10, p50, p90 = (sum(getattr(week, name) for week in forecasts) for name in ("p10", "p50", "p90"))
    target = math.ceil(stats.quantile_between(p10, p50, p90, ratio))
    supply = product.stock + cost.on_order
    trigger = math.ceil(sum(week.p90 for week in forecasts[:lead]))
    cover = stats.weeks_of_cover(supply, [week.p50 for week in forecasts])
    cover = cover if cover is None else round(cover, 2)
    leftover = max(0, round(supply - p50))
    level, alert = PrintRunAdvice.Level.OK, ""
    if p50 and (supply <= trigger or (cover is not None and cover < lead + 1)):
        level = PrintRunAdvice.Level.ACT
        alert = f"Reprint now: {supply} copies in stock and on order; the next {lead} weeks may need {trigger}."
    elif target > supply:
        level = PrintRunAdvice.Level.WATCH
        alert = f"Print {target - supply} more for the season (P{round(ratio * 100)} of its demand: {target})."
    elif supply > target and leftover > LEFTOVER_SHARE * supply:  # (at the target some are left over by design)
        level = PrintRunAdvice.Level.WATCH
        alert = f"{leftover} copies may be left at the exam: move them to distributors or stop the reprint."
    return PrintRunAdvice(
        run=record,
        product=product,
        net_price=price,
        unit_cost=cost.unit_cost,
        salvage=cost.salvage,
        critical_ratio=ratio,
        target_quantity=target,
        supply=supply,
        recommended_quantity=max(0, target - supply),
        reprint_trigger_units=trigger,
        weeks_of_cover=cover,
        projected_leftover=leftover,
        n_history=forecasts[0].n_history,
        level=level,
        alert=alert,
    )
