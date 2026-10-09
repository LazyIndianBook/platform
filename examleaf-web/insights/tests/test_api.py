"""The insights API: staff.view_insights to read (the staff app's rules: staff/tests/test_matrix.py has every role),
staff.acknowledge_signal to acknowledge a fraud signal, and every answer says how its numbers were made."""

from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts import roles
from api.tests import sign_in, student
from insights.jobs import demand
from insights.models import FraudSignal, PrintCost
from shop.factories import ProductFactory
from staff.models import AuditEvent
from staff.tests.conftest import make_staff, signed_in

from .helpers import day_in, sell

pytestmark = [pytest.mark.django_db, pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning")]
ENDPOINTS = [
    *["forecasts", "print-runs", "backtests", "item-stats", "chapter-stats", "cohorts", "code-activation"],
    *["delivery", "fraud-signals", "offers"],
]


@pytest.fixture
def api():
    return signed_in(make_staff(roles.FINANCE))


def test_the_insights_need_their_permission(api):
    for name in ENDPOINTS:
        assert APIClient().get(f"/api/v1/insights/{name}/").status_code == 401, name
    app = APIClient()
    sign_in(app, make_staff(roles.OWNER))  # the app's JWT is never the staff's session
    assert app.get("/api/v1/insights/forecasts/").status_code == 401
    support = make_staff(roles.SUPPORT)
    refused = signed_in(support).get("/api/v1/insights/forecasts/")
    assert (refused.status_code, refused.json()["code"]) == (403, "permission_denied")
    assert AuditEvent.objects.filter(action="authz_fail", actor_id=support.pk).exists()
    assert signed_in(student()).get("/api/v1/insights/forecasts/").status_code == 403
    for name in ENDPOINTS:
        response = api.get(f"/api/v1/insights/{name}/")
        data = response.json()
        assert {"method", "data_as_of", "backtest", "shown", "count", "results"} <= set(data), name
        assert data["results"] == [] and response["Cache-Control"] == "no-store", name  # nothing worked out yet


def test_a_fraud_signal_is_acknowledged_once_by_whoever_may(api):
    now = timezone.now()
    signal = FraudSignal.objects.create(kind="codes_failed_account", subject="a" * 64, count=6, window_start=now,
                                        window_end=now)  # fmt: skip
    url = f"/api/v1/insights/fraud-signals/{signal.pk}/acknowledge/"
    assert signed_in(make_staff(roles.MARKETING)).post(url).status_code == 403  # reads them, does not acknowledge
    admin = make_staff(roles.ADMIN)
    done = signed_in(admin).post(url)
    assert done.status_code == 200 and done.json()["acknowledged_at"]
    signal.refresh_from_db()
    assert signal.acknowledged_by == admin.pk
    assert signed_in(admin).post(url).json()["acknowledged_at"] == done.json()["acknowledged_at"]  # once
    event = AuditEvent.objects.get(action="insights.signal_acknowledged")
    assert (event.actor_id, event.target_id, event.target_label) == (
        admin.pk,
        str(signal.pk),
        f"Fraud signal #{signal.pk}",
    )
    assert api.get("/api/v1/insights/fraud-signals/", {"open": 1}).json()["count"] == 0


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
