"""Demand forecasts, their backtest and the print-run advice, on sales made week by week of three seasons."""

from decimal import Decimal

import pytest

from insights import stats
from insights.jobs import demand, week_index, week_start
from insights.models import Forecast, ForecastRun, PrintCost
from shop.factories import ProductFactory
from shop.models import StockAlert

from .helpers import at_noon, day_in, sell

pytestmark = pytest.mark.django_db
approx = pytest.approx


@pytest.fixture
def book(physics):
    return ProductFactory(subject=physics, title="Physics Sample Papers 2027", price=Decimal(195), stock=0)


def sales(product, season, weeks, **address):
    for index, copies in weeks.items():
        sell(product, day_in(season, index), copies, **address)


def weekly(run, season, product=None):
    """{week index: Forecast} of a run, every district together."""
    rows = run.forecasts.filter(district=None, **({"product": product} if product else {}))
    return {week_index(season, row.week_start): row for row in rows}


def test_this_season_selling_as_the_last_gives_last_season_again(book, seasons):
    _, last, this = seasons
    sales(book, last, {2: 3, 5: 2, 12: 4, 20: 6, 40: 10})
    sales(book, this, {2: 3, 5: 2})  # its ten weeks so far sold as last season's: a growth of 1
    run = demand.forecast_demand(today=day_in(this, 10))
    weeks = weekly(run, this)
    assert run.status == ForecastRun.Status.DONE and sorted(weeks) == list(range(10, 52))  # this week to the exam
    assert {index: row.p50 for index, row in weeks.items() if row.p50} == {12: 4, 20: 6, 40: 10}
    assert (weeks[40].p10, weeks[40].p90) == (approx(6), approx(15))  # no season before last: the default spread
    assert weeks[40].n_history == 30  # 25 copies last season, 5 this one so far
    assert run.params["titles"][book.slug] == {
        "growth": 1.0, "tested": False, "spread": [0.6, 1.5], "weeks_done": 10, "share_of_line": 1.0,
    }  # fmt: skip


def test_the_growth_factor_is_damped_by_the_weeks_this_season_has_run(book, seasons):
    _, last, this = seasons
    sales(book, last, {2: 3, 5: 2, 12: 4})
    sales(book, this, {2: 6, 5: 4})  # twice last season's
    weeks = weekly(demand.forecast_demand(today=day_in(this, 10)), this)
    assert weeks[12].p50 == approx(4 * (1 + (10 / 5 - 1) * 10 / (10 + 4)))  # ten weeks in: weight 10/14
    weeks = weekly(demand.forecast_demand(today=day_in(this, 6)), this)
    assert weeks[12].p50 == approx(4 * (1 + (10 / 5 - 1) * 6 / (6 + 4)))  # six weeks in: weight 6/10


def test_the_district_split_adds_up_to_the_total(book, seasons, directory):
    _, last, this = seasons
    sell(book, day_in(last, 12), 3, pin="781001")
    sell(book, day_in(last, 30), 1, pin="785001", district="typed by hand")  # the directory's district wins
    sell(book, day_in(last, 31), 2, pin="799001", district="West Tripura")  # not in the directory: as typed
    run = demand.forecast_demand(today=day_in(this, 10))
    totals = {row.week_start: row.p50 for row in run.forecasts.filter(district=None)}
    parts = {}
    for row in run.forecasts.exclude(district=None):
        parts.setdefault(row.week_start, {})[row.district] = row.p50
    assert set(parts) == {start for start, p50 in totals.items() if p50}
    for start, split in parts.items():
        assert sum(split.values()) == approx(totals[start])
    assert parts[week_start(this, 30)] == {
        "Kamrup Metro": approx(0.5), "Jorhat": approx(1 / 6), "West Tripura": approx(1 / 3),
    }  # fmt: skip


def test_a_new_title_takes_the_previous_titles_curve_scaled_to_its_first_weeks(physics, seasons):
    _, last, this = seasons
    old = ProductFactory(subject=physics, title="Physics Sample Papers 2026", is_active=False)
    new = ProductFactory(subject=physics, title="Physics Sample Papers 2027")
    solutions = ProductFactory(subject=physics, title="Physics Solutions 2027", kind="solutions")
    sales(old, last, {2: 2, 12: 8})
    sales(new, this, {2: 4})  # twice the old edition's first weeks
    run = demand.forecast_demand(today=day_in(this, 10))
    assert set(run.forecasts.values_list("product", flat=True)) == {new.pk}  # not the old one, no longer on sale
    assert weekly(run, this, new)[12].p50 == approx(8 * (1 + (4 / 2 - 1) * 10 / 14))
    assert f"{solutions}: its line sold nothing last season" in run.notes  # another line: no curve to take


def test_a_request_to_hear_when_it_is_back_counts_as_a_copy_sold(book, seasons):
    _, last, this = seasons
    sales(book, last, {12: 4})
    alert = StockAlert.objects.create(email="reader@example.com", product=book)
    StockAlert.objects.filter(pk=alert.pk).update(created=at_noon(day_in(last, 20)))
    weeks = weekly(demand.forecast_demand(today=day_in(this, 10)), this)
    assert (weeks[12].p50, weeks[20].p50) == (4, 1)


def test_nothing_is_forecast_without_the_seasons_or_last_seasons_sales(book, physics, seasons):
    assert demand.forecast_demand(today=day_in(seasons[2], 10)).notes == f"{book}: its line sold nothing last season"
    for season in seasons:
        season.delete()
    run = demand.forecast_demand()
    assert run.status == ForecastRun.Status.SKIPPED and not run.forecasts.exists()
    assert run.notes == f"{physics}: enter the next season's exam dates"


def test_the_backtest_scores_a_line_against_the_seasonal_naive(book, seasons):
    before, last, this = seasons
    sales(book, before, {3: 10, 10: 10, 20: 10})
    sales(book, last, {3: 20, 10: 20, 20: 20})  # twice the season before: the growth factor helps
    run = demand.backtest(today=day_in(this, 5))
    rows = {(row.product_id, row.horizon_weeks): row for row in run.backtests.all()}
    assert set(rows) == {(book.pk, 1), (book.pk, 4), (None, 1), (None, 4)}  # each title, and every title together
    earlier, actual = [0] * 52, [0] * 52
    for index in (3, 10, 20):
        earlier[index], actual[index] = 10, 20
    for horizon in (1, 4):
        points = stats.rolling_origin(earlier, actual, horizon)
        row = rows[book.pk, horizon]
        assert (row.wape, row.mase_vs_seasonal_naive) == (approx(stats.wape(points)), approx(stats.mase(points)))
        assert row.shown and row.n_weeks == 52 - horizon
        assert (rows[None, horizon].wape, rows[None, horizon].shown) == (approx(row.wape), True)  # one line only
    assert demand.forecast_demand(today=day_in(this, 5)).params["titles"][book.slug]["tested"] is True


def test_a_line_whose_growth_lost_the_backtest_is_forecast_by_the_seasonal_naive(book, seasons):
    before, last, this = seasons
    sales(book, before, {0: 10, 30: 10})
    sales(book, last, {0: 20, 30: 10})  # a strong start, then as before: the growth factor misleads
    assert not demand.backtest(today=day_in(this, 5)).backtests.get(product=book, horizon_weeks=4).shown
    sales(book, this, {0: 40})
    run = demand.forecast_demand(today=day_in(this, 5))
    assert weekly(run, this)[30].p50 == 10 and run.params["titles"][book.slug]["growth"] == 1.0


def test_the_print_run_advice_prints_the_p71_and_sets_the_reprint_trigger(book, seasons):
    """Net ₹195, print ₹60, salvage ₹5 (the research's example): the P71 of the season's demand from now."""
    _, last, this = seasons
    sales(book, last, {11: 10, 12: 10, 13: 10, 30: 40})
    today = day_in(this, 10)
    demand.forecast_demand(today=today)
    assert demand.advise_print_run(today=today).notes == f"No print cost entered for {book}."
    PrintCost.objects.create(product=book, unit_cost=60, salvage=5, on_order=5, lead_time_weeks=3)
    book.stock = 10
    book.save()
    advice = demand.advise_print_run(today=today).advice.get()
    assert (advice.net_price, advice.critical_ratio) == (Decimal(195), approx(135 / 190))
    assert 70 * 1.5 ** (0.554923 / 1.281552) == approx(83.43, abs=0.01)  # P50 70 to the exam, P90 105 (default)
    assert (advice.target_quantity, advice.supply, advice.recommended_quantity) == (84, 15, 69)
    assert advice.reprint_trigger_units == 30  # P90 of the next three weeks: 0 + 15 + 15
    assert advice.weeks_of_cover == 2.5  # this week needs nothing, the next 10, then 5 of the 10 after
    assert (advice.projected_leftover, advice.level) == (0, "act") and advice.alert.startswith("Reprint now")


def test_the_advice_watches_a_shortfall_for_the_season_and_a_leftover_beyond_the_target(book, seasons):
    cost, today = PrintCost(product=book, unit_cost=60, salvage=5, lead_time_weeks=2), day_in(seasons[2], 10)
    weeks = [Forecast(p10=6, p50=10, p90=15, n_history=50) for _ in range(10)]  # 100 copies to the exam, P71 120
    book.stock = 60
    advice = demand.advice(None, cost, weeks, today)
    assert (advice.level, advice.recommended_quantity) == ("watch", 60)
    assert advice.alert == "Print 60 more for the season (P71 of its demand: 120)."
    book.stock = 120  # the target: some 20 copies are left over by design, no alert
    assert (demand.advice(None, cost, weeks, today).level, demand.advice(None, cost, weeks, today).alert) == ("ok", "")
    book.stock = 200
    advice = demand.advice(None, cost, weeks, today)
    assert (advice.level, advice.projected_leftover, advice.weeks_of_cover) == ("watch", 100, None)
    assert advice.alert == "100 copies may be left at the exam: move them to distributors or stop the reprint."
