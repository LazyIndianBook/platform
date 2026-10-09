"""The insights API: refused to all but active staff, and every answer says how its numbers were made."""

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from accounts.factories import UserFactory
from api.tests import sign_in, student
from insights.jobs import demand
from insights.models import PrintCost
from shop.factories import ProductFactory

from .helpers import day_in, sell

pytestmark = [pytest.mark.django_db, pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning")]
ENDPOINTS = [
    *["forecasts", "print-runs", "backtests", "item-stats", "chapter-stats", "cohorts", "code-activation"],
    *["delivery", "fraud-signals", "offers"],
]


@pytest.fixture
def api():
    return APIClient()


def test_the_insights_are_for_active_staff_only(api):
    for name in ENDPOINTS:
        assert api.get(f"/api/v1/insights/{name}/").status_code == 401, name
    sign_in(api, student())
    for name in ENDPOINTS:
        assert api.get(f"/api/v1/insights/{name}/").json() == {"detail": "For staff only."}, name
    sign_in(api, UserFactory(is_staff=True, is_active=False))
    assert api.get("/api/v1/insights/forecasts/").status_code == 401
    sign_in(api, UserFactory(is_staff=True))
    for name in ENDPOINTS:
        data = api.get(f"/api/v1/insights/{name}/").json()
        assert {"method", "data_as_of", "backtest", "shown", "count", "results"} <= set(data), name
        assert data["results"] == [], name  # nothing worked out yet


def test_staff_read_the_newest_forecast_with_its_method_backtest_and_n(api, physics, seasons):
    before, last, this = seasons
    book = ProductFactory(subject=physics, price=Decimal(195))
    for season, copies in ((before, 10), (last, 20)):
        for index in (3, 10, 20):
            sell(book, day_in(season, index), copies, pin="781001")
    today = day_in(this, 5)
    demand.backtest(today=today)
    run = demand.forecast_demand(today=today)
    PrintCost.objects.create(product=book, unit_cost=60, salvage=5)
    demand.advise_print_run(today=today)
    sign_in(api, UserFactory(is_staff=True))
    data = api.get("/api/v1/insights/forecasts/").json()
    assert (data["method"], data["shown"], data["count"]) == (demand.FORECAST, True, 47)  # weeks 5 to 51
    assert data["data_as_of"] == run.data_as_of.astimezone().isoformat()
    assert set(data["backtest"]) == {
        "horizon_weeks",
        "wape",
        "mase_vs_seasonal_naive",
        "shown",
        "n_weeks",
        "data_as_of",
    }
    assert (data["backtest"]["horizon_weeks"], data["backtest"]["n_weeks"]) == (4, 48)
    week = data["results"][15]  # week 20: last season's 20 copies × the damped growth
    assert (week["product"], week["district"], week["n"]) == (book.slug, None, 60)
    assert week["p10"] < week["p50"] < week["p90"]
    districts = api.get("/api/v1/insights/forecasts/", {"district": "all", "product": book.slug}).json()
    assert {row["district"] for row in districts["results"]} == {"Kamrup Metro"}
    assert api.get("/api/v1/insights/forecasts/", {"product": "another-title"}).json()["count"] == 0
    advice = api.get("/api/v1/insights/print-runs/").json()
    assert advice["method"] == demand.PRINT_RUN and advice["results"][0]["critical_ratio"] == pytest.approx(135 / 190)
    assert advice["results"][0]["net_price"] == "195.00"  # money as strings, as everywhere in the API
    cohorts = api.get("/api/v1/insights/cohorts/").json()
    assert (cohorts["backtest"], cohorts["shown"]) == (None, True)  # counts, not predictions
