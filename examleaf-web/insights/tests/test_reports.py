"""The reports (insights/reports.py, GET /api/v1/staff/reports/…) on fixtures worked out by hand: each report's totals,
test mode kept out, the period's bounds, the minimum cell hiding, the scope narrowing, both permissions needed, and the
print-run sum recomputed."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.utils import timezone

from accounts import roles
from content.models import Book, Subject
from insights import reports
from insights.jobs import demand
from insights.models import CodeActivationStat, PrintCost, PrintRunAdvice
from learn.models import BookCode
from shipping.models import CodRemittance
from shop.factories import ProductFactory
from shop.models import Order, OrderItem, Shipment
from staff.models import AuditEvent, StaffScope
from staff.tests.conftest import STAFF, make_staff, signed_in

from .helpers import as_test, at, day_in, learners, sell

pytestmark = pytest.mark.django_db
REPORTS = STAFF + "reports/"
FROM, TO = date(2026, 10, 1), date(2026, 10, 7)
PERIOD = {"from": str(FROM), "to": str(TO)}


@pytest.fixture(autouse=True)
def live_site(settings):
    settings.RAZORPAY_KEY_ID = ""  # no keys counts as live: test-mode orders are then left out
    settings.INSIGHTS_MIN_CELL = 10
    settings.INSIGHTS_MIN_CELL_CLASS = 5


@pytest.fixture
def october(monkeypatch):
    """The reports run on 10 October 2026 (the period ends on the 7th; "not after today" is the 10th)."""
    original = timezone.localdate
    monkeypatch.setattr(
        timezone, "localdate", lambda value=None, tz=None: date(2026, 10, 10) if value is None else original(value, tz)
    )
    return date(2026, 10, 10)


def ask(user, path="sales/", **query):
    return signed_in(user).get(REPORTS + path, query)


def get(path="sales/", role=roles.FINANCE, **query):
    response = ask(make_staff(role), path, **query)
    assert response.status_code == 200, response.content
    return response.json()


@pytest.fixture
def shop(physics, october):
    """Physics (ASSEB, class 12) with a book whose edition is 2027, and Chemistry without one; two orders in the period
    with a line's own discount and an older order's discount shared by value, and others that must not count."""
    chemistry = Subject.objects.create(
        name="Chemistry", code="CHE", board=physics.board, class_level=physics.class_level
    )
    book = Book.objects.create(title="Physics", slug="physics", subject=physics, edition="2027")
    phy = ProductFactory(subject=physics, book=book, title="Physics Sample Papers", slug="phy", price=Decimal("300.00"))
    che = ProductFactory(subject=chemistry, title="Chemistry Sample Papers", slug="che", price=Decimal("200.00"))
    first = sell(phy, date(2026, 10, 2), copies=2)  # 600, its own 30 of discount on the line
    OrderItem.objects.filter(order=first).update(discount=Decimal("30.00"))
    Order.objects.filter(pk=first.pk).update(discount=Decimal("30.00"))
    second = sell(che, date(2026, 10, 3))  # 500 in all: chemistry 200 and physics 300, a discount of 50 shared by value
    OrderItem.objects.create(
        order=second,
        product=phy,
        title=phy.title,
        hsn_code="4901",
        gst_rate=0,
        mrp=phy.mrp,
        unit_price=phy.price,
        quantity=1,
    )
    Order.objects.filter(pk=second.pk).update(
        subtotal=Decimal("500.00"), total=Decimal("450.00"), discount=Decimal("50.00")
    )
    as_test(sell(phy, date(2026, 10, 3)))  # a test order
    Order.objects.filter(pk=sell(phy, date(2026, 10, 4)).pk).update(status="cancelled")
    sell(phy, date(2026, 10, 8))  # after the period
    sell(phy, date(2026, 9, 30))  # before it
    return {"physics": physics, "chemistry": chemistry, "phy": phy, "che": che}


# ---- Sales ----


def test_sales_by_product_with_the_discount_as_kept_or_shared_by_value(shop):
    answer = get(**PERIOD, by="product")
    assert answer["report"] == "sales" and answer["period"] == {"start": str(FROM), "end": str(TO), "days": 7}
    assert [
        (row["label"], row["orders"], row["units"], row["gross"], row["discount"], row["net"]) for row in answer["rows"]
    ] == [
        ("Physics Sample Papers", 2, 3, "900.00", "60.00", "840.00"),  # 570 + 270
        ("Chemistry Sample Papers", 1, 1, "200.00", "20.00", "180.00"),  # 200 less its 200/500 of the 50
    ]
    assert answer["totals"] == {"orders": 2, "units": 4, "gross": "1100.00", "discount": "80.00", "net": "1020.00"}
    assert answer["test_mode"] is False and answer["as_of"]
    assert {column["key"] for column in answer["columns"]} >= {"units", "gross", "discount", "net"}
    assert all(column["definition"] for column in answer["columns"]) and answer["definition"]


def test_sales_by_subject_class_board_and_edition(shop):
    by = lambda name: [(row["label"], row["units"], row["net"]) for row in get(**PERIOD, by=name)["rows"]]  # noqa: E731
    assert by("subject") == [("Physics, ASSEB, Class 12", 3, "840.00"), ("Chemistry, ASSEB, Class 12", 1, "180.00")]
    assert by("class") == [("Class 12", 4, "1020.00")]
    assert by("board") == [("Assam State School Education Board", 4, "1020.00")]
    assert by("edition") == [("2027", 3, "840.00"), ("No edition recorded", 1, "180.00")]
    assert by("none") == [("All sales", 4, "1020.00")]


def test_sales_by_day_week_and_month(shop):
    days = get(**PERIOD, by="none", grain="day")["rows"]
    assert [(row["period_start"], row["units"], row["net"]) for row in days] == [
        ("2026-10-02", 2, "570.00"),
        ("2026-10-03", 2, "450.00"),
    ]
    weeks = get(**PERIOD, by="product", grain="week")["rows"]
    assert {row["period_start"] for row in weeks} == {"2026-09-28"}  # the Monday of both days (2 and 3 October, Friday)
    months = get(**PERIOD, by="none", grain="month")["rows"]
    assert [(row["period_start"], row["units"], row["net"]) for row in months] == [("2026-10-01", 4, "1020.00")]


def test_the_period_is_india_days_and_at_most_thirteen_months(shop):
    midnight = Order.objects.get(placed_at=at(date(2026, 10, 8)))
    Order.objects.filter(pk=midnight.pk).update(placed_at=at(date(2026, 10, 8), 0, 0))
    just_before = sell(shop["phy"], date(2026, 10, 7))
    Order.objects.filter(pk=just_before.pk).update(placed_at=at(date(2026, 10, 7), 23, 59))
    units = lambda **q: get(by="none", **q)["totals"]["units"]  # noqa: E731
    assert units(**PERIOD) == 5  # the 7th's last minute is in, the 8th's first is out
    assert units(**{"from": "2026-10-08", "to": "2026-10-08"}) == 1
    assert get()["period"]["days"] == 30 and get()["period"]["end"] == "2026-10-10"  # 30 days to today by default
    for query, field in [
        ({"from": "2026-10-09", "to": "2026-10-01"}, "from"),
        ({"to": "2026-10-11"}, "to"),
        ({"from": "2025-09-10", "to": "2026-10-10"}, "from"),
        ({"from": "10 Oct"}, "from"),
        ({"by": "colour"}, "by"),
        ({"grain": "year"}, "grain"),
    ]:
        refused = ask(make_staff(roles.FINANCE), **query)
        assert refused.status_code == 400 and field in refused.json(), query
    assert ask(make_staff(roles.FINANCE), **{"from": "2025-09-11", "to": "2026-10-10"}).status_code == 200  # 13 months


def test_sales_need_both_the_reports_and_the_orders_lines_permission(shop):
    assert ask(make_staff(roles.SALES), **PERIOD).status_code == 200
    assert ask(make_staff(roles.AUDITOR), **PERIOD).status_code == 200
    packer = make_staff(roles.PACKER)  # views order lines, not the reports
    refused = ask(packer, **PERIOD)
    assert refused.status_code == 403 and "staff.view_insights" in refused.json()["detail"]
    marketing = make_staff(roles.MARKETING)  # reads the reports, not the orders
    refused = ask(marketing, **PERIOD)
    assert refused.status_code == 403 and "shop.view_orderitem" in refused.json()["detail"]
    assert AuditEvent.objects.filter(action="authz_fail", actor_id=marketing.pk).exists()


def test_sales_are_the_persons_own_orders(shop):
    narrowed = make_staff(roles.SALES)
    StaffScope.objects.create(user=narrowed, kind="order_status", value="packed")
    assert ask(narrowed, **PERIOD).json()["totals"]["units"] == 0  # only the packed ones are theirs: there are none


def test_a_site_on_test_keys_counts_all_its_orders_and_says_so(shop, settings):
    settings.RAZORPAY_KEY_ID = "rzp_test_abc"
    answer = get(**PERIOD, by="none")
    assert answer["test_mode"] is True and answer["totals"]["units"] == 5  # the order with test keys is counted too


def test_more_rows_than_the_cap_ask_for_a_narrower_report(shop, monkeypatch):
    monkeypatch.setattr(reports, "MAX_ROWS", 1)
    refused = ask(make_staff(roles.FINANCE), **PERIOD, by="product")
    assert refused.status_code == 400 and "rows" in refused.json()["non_field_errors"][0]


# ---- Sales by place ----


@pytest.fixture
def places(shop, directory):
    """12 orders to Kamrup Metro, 3 to Jorhat, 10 to a PIN outside the directory in West Bengal (typed district), and
    one for a course alone billed in Maharashtra."""
    phy = shop["phy"]
    for _ in range(12):
        sell(phy, date(2026, 10, 5), pin="781001")
    for _ in range(3):
        sell(phy, date(2026, 10, 5), pin="785001")
    for _ in range(10):
        sell(phy, date(2026, 10, 5), pin="700001", state="WB", district="Kolkata")
    billed = sell(phy, date(2026, 10, 5), pin="781001")
    Order.objects.filter(pk=billed.pk).update(billing_state="MH")


def test_sales_by_state_use_the_place_of_supply_and_hide_a_small_one(places):
    answer = get("sales-by-place/", **PERIOD)
    rows = {row["label"]: row for row in answer["rows"]}
    assert answer["level"] == "state" and answer["minimum"] == 10
    # Assam: the 12 and 3 orders to Kamrup and Jorhat and the first two orders of the fixture (to 781001)
    assert (rows["Assam"]["orders"], rows["Assam"]["units"], rows["Assam"]["hidden"]) == (17, 19, False)
    assert (rows["West Bengal"]["orders"], rows["West Bengal"]["net"]) == (10, "3000.00")
    maharashtra = rows["Maharashtra"]  # one order billed there: under the minimum
    assert (maharashtra["hidden"], maharashtra["under"], maharashtra["orders"], maharashtra["net"]) == (
        True,
        10,
        None,
        None,
    )
    assert answer["hidden_rows"] == 1
    assert answer["totals_shown"]["orders"] == 27  # the places shown only: Maharashtra's one order is in no total


def test_sales_by_district_and_pin_hide_the_small_ones_and_the_total_never_holds_them(places):
    answer = get("sales-by-place/", **PERIOD, level="district", state="AS")
    rows = {row["district"]: row for row in answer["rows"]}
    assert (
        rows["Kamrup Metro"]["orders"] == 15 and rows["Kamrup Metro"]["hidden"] is False
    )  # 12 + 1 billed + 2 of the shop
    assert (rows["Jorhat"]["hidden"], rows["Jorhat"]["under"], rows["Jorhat"]["orders"]) == (True, 10, None)
    assert answer["hidden_rows"] == 1 and answer["totals_shown"]["orders"] == 15
    pins = {row["pin"]: row for row in get("sales-by-place/", **PERIOD, level="pin")["rows"]}
    assert pins["781001"]["orders"] == 15 and pins["785001"]["hidden"] and pins["700001"]["orders"] == 10
    assert pins["700001"]["district"] == "Kolkata"  # typed: the PIN is not in the directory


def test_the_minimum_cell_is_a_setting_and_a_district_is_hidden_by_it(places, settings):
    settings.INSIGHTS_MIN_CELL = 3
    rows = {row["district"]: row for row in get("sales-by-place/", **PERIOD, level="district", state="AS")["rows"]}
    assert rows["Jorhat"]["hidden"] is False and rows["Jorhat"]["orders"] == 3
    refused = ask(make_staff(roles.FINANCE), "sales-by-place/", **PERIOD, state="ZZ")
    assert refused.status_code == 400 and "state" in refused.json()


# ---- Codes ----


@pytest.fixture
def batches(physics, directory):
    redeemer = learners(1)[0]
    for number in range(10):
        BookCode.objects.create(
            digest=f"a{number}".ljust(64, "0"),
            batch="PHY-2027-1",
            subject=physics,
            redeemed_by=redeemer if number < 4 else None,
            redeemed_at=timezone.now() - timedelta(days=20 if number < 3 else 2) if number < 4 else None,
        )
    for number in range(5):
        BookCode.objects.create(digest=f"b{number}".ljust(64, "0"), batch="PHY-2027-2", subject=physics)
    now = timezone.now()
    CodeActivationStat.objects.bulk_create(
        [
            CodeActivationStat(batch="PHY-2027-1", printed=10, redeemed=4, redeemed_7d=1, computed_at=now),
            CodeActivationStat(
                batch="PHY-2027-1", district="Kamrup Metro", redeemed=12, redeemed_7d=3, computed_at=now
            ),
            CodeActivationStat(batch="PHY-2027-1", district="Jorhat", redeemed=3, redeemed_7d=0, computed_at=now),
            CodeActivationStat(batch="PHY-2027-2", district="Kamrup Metro", redeemed=2, redeemed_7d=0, computed_at=now),
            CodeActivationStat(batch="OLD", district="Elsewhere", redeemed=50, redeemed_7d=0, computed_at=now),
        ]
    )


def test_codes_by_batch_with_the_activation_rate_and_districts_under_the_minimum_hidden(batches):
    answer = get("codes/", role=roles.OWNER)
    rows = {row["batch"]: row for row in answer["rows"]}
    assert (rows["PHY-2027-1"]["printed"], rows["PHY-2027-1"]["activated"], rows["PHY-2027-1"]["activated_7d"]) == (
        10,
        4,
        1,
    )
    assert rows["PHY-2027-1"]["activation_rate"] == "0.4000" and rows["PHY-2027-2"]["activation_rate"] == "0.0000"
    assert rows["PHY-2027-1"]["sold"] is None and rows["PHY-2027-1"]["revoked"] is None  # not recorded (yet)
    districts = {row["district"]: row for row in answer["districts"]}
    assert districts["Kamrup Metro"]["redeemed"] == 14 and districts["Kamrup Metro"]["hidden"] is False  # 12 + 2
    assert (districts["Jorhat"]["hidden"], districts["Jorhat"]["under"], districts["Jorhat"]["redeemed"]) == (
        True,
        10,
        None,
    )
    assert "Elsewhere" not in districts  # a batch with no code of ours
    one = get("codes/", role=roles.OWNER, batch="PHY-2027-2")["districts"]
    assert [(row["district"], row["hidden"]) for row in one] == [("Kamrup Metro", True)]  # 2 in the batch: under 10


def test_codes_are_the_persons_subjects_only(batches, physics):
    other = Subject.objects.create(name="Chemistry", code="CHE", board=physics.board, class_level=physics.class_level)
    BookCode.objects.create(digest="c" * 64, batch="CHE-2027-1", subject=other)
    owner = make_staff(roles.OWNER)
    assert {row["batch"] for row in ask(owner, "codes/").json()["rows"]} == {"PHY-2027-1", "PHY-2027-2", "CHE-2027-1"}
    StaffScope.objects.create(user=owner, kind="subject", value="PHY")
    assert {row["batch"] for row in ask(owner, "codes/").json()["rows"]} == {"PHY-2027-1", "PHY-2027-2"}


# ---- Cash on delivery ----


def test_cod_ageing_remitted_and_the_courier(shop, october):
    today = october
    phy = shop["phy"]

    def parcel(days, state, amount=Decimal("300.00"), live=True, courier="India Post", remitted=None, received=None):
        order = sell(phy, date(2026, 9, 1), method="cod")
        if not live:
            as_test(order)
        shipment = Shipment.objects.create(order=order, courier=courier, tracking_number=f"T{order.pk}")
        return CodRemittance.objects.create(
            shipment=shipment,
            expected_amount=amount,
            expected_on=today - timedelta(days=days),
            state=state,
            remitted_at=remitted,
            remitted_amount=received,
        )

    parcel(-2, "expected")  # not yet due
    parcel(0, "expected")  # due today: not late
    parcel(3, "overdue")  # 1 to 7 days late
    parcel(10, "overdue", courier="Delhivery")  # 8 to 14
    parcel(20, "overdue")  # 15 to 30
    parcel(45, "overdue", Decimal("500.00"))  # more than 30
    parcel(50, "overdue", live=False)  # a test order's
    parcel(5, "not_expected")  # came back
    parcel(8, "remitted", remitted=date(2026, 10, 5), received=Decimal("300.00"))  # in the period
    parcel(9, "mismatch", remitted=date(2026, 10, 6), received=Decimal("250.00"))  # in the period, another amount
    parcel(30, "remitted", remitted=date(2026, 9, 20), received=Decimal("300.00"))  # before it
    answer = get("cod/", **PERIOD)
    ageing = {row["key"]: row for row in answer["rows"]}
    assert [(key, ageing[key]["count"], ageing[key]["expected"]) for key in ageing] == [
        ("not_due", 2, "600.00"),
        ("late_1_7", 1, "300.00"),
        ("late_8_14", 1, "300.00"),
        ("late_15_30", 1, "300.00"),
        ("late_31", 1, "500.00"),
    ]
    assert (
        ageing["late_31"]["oldest_expected_on"] == "2026-08-26"
        and ageing["not_due"]["oldest_expected_on"] == "2026-10-10"
    )
    assert answer["remitted"] == {"count": 2, "expected": "600.00", "received": "550.00", "difference": "-50.00"}
    couriers = {row["courier"]: row for row in answer["by_courier"]}
    assert (couriers["India Post"]["count"], couriers["India Post"]["overdue"], couriers["India Post"]["expected"]) == (
        5,
        3,
        "1700.00",
    )
    assert (couriers["Delhivery"]["count"], couriers["Delhivery"]["overdue"]) == (1, 1)
    assert ask(make_staff(roles.PACKER), "cod/").status_code == 403  # no staff.view_cod


# ---- Settlements ----


def test_settlements_say_they_are_not_configured_while_the_finance_module_is_not_there():
    answer = get("settlements/")
    assert (answer["configured"], answer["rows"]) == (False, [])
    assert "not set up" in answer["note"] and answer["period"]["days"] == 90
    index = {each["key"]: each for each in get("")["reports"]}
    assert index["settlements"]["configured"] is False and index["sales"]["configured"] is True


def test_a_settlement_row_takes_whichever_fields_the_finance_module_named():
    names = {key: None for key in reports.SETTLEMENT_FIELDS}
    named = dict(names, reference="razorpay_id", date="settled_at", gross="gross_amount", fees="fee", net="net_amount")
    each = SimpleNamespace(
        pk=7,
        razorpay_id="setl_Abc123",
        settled_at=datetime(2026, 10, 9, 21, 0, tzinfo=UTC),  # half past two on the 10th in India
        gross_amount=Decimal("1000"),
        fee=Decimal("23.6"),
        net_amount=Decimal("976.4"),
    )
    assert reports.settlement_row(each, named) == {
        "reference": "setl_Abc123",
        "date": date(2026, 10, 10),  # a day, not the moment
        "gross": Decimal("1000.00"),
        "fees": Decimal("23.60"),
        "tax": None,  # the module keeps no GST on fees: unknown, not zero
        "refunds": None,
        "net": Decimal("976.40"),
        "utr": "",
        "state": "",
    }
    bare = reports.settlement_row(SimpleNamespace(pk=3), names)  # a model with none of the names: still a row
    assert (bare["reference"], bare["date"], bare["gross"], bare["utr"]) == ("3", None, None, "")


# ---- The index ----


def test_the_index_lists_each_report_with_what_it_needs_and_whether_the_person_holds_it():
    finance = {each["key"]: each for each in get("", role=roles.FINANCE)["reports"]}
    assert set(finance) == {
        "sales",
        "sales-by-place",
        "codes",
        "course-health",
        "cod",
        "settlements",
        "cohorts",
        "forecasts",
    }
    assert finance["sales"]["needs"] == ["staff.view_insights", "shop.view_orderitem"] and finance["sales"]["available"]
    assert finance["cod"]["available"] is True and finance["codes"]["available"] is False  # no learn.view_bookcode
    assert (
        finance["cohorts"]["api"] == "/api/v1/insights/cohorts/" and finance["cohorts"]["page"] == "/reports/cohorts/"
    )
    assert ask(make_staff(roles.SUPPORT), "").status_code == 403  # staff.view_insights


# ---- The print run, recomputed ----


def critical(**inputs):
    return signed_in(make_staff(roles.FINANCE)).post(REPORTS + "print-run/", inputs, format="json")


def test_the_critical_ratio_of_the_plans_example_is_the_71st_percentile():
    book = ProductFactory(slug="phy-papers", price=Decimal("195.00"), stock=40)
    answer = critical(product=book.slug, net_price="195.00", unit_cost="60.00", salvage="5.00").json()
    assert (answer["critical_ratio"], answer["percentile"]) == (0.7105, 71)  # 135 / (135 + 55)
    assert (answer["target_quantity"], answer["recommended_quantity"], answer["supply"]) == (None, None, 40)
    assert "no demand forecast" in answer["note"] and answer["range"] is None and answer["shown"] is False


@pytest.fixture
def forecast(physics, seasons):
    """A title with two past seasons of sales, its forecast and its nightly advice as on `day_in(this season, 5)`;
    100 copies in stock and 25 on order."""
    before, last, this = seasons
    book = ProductFactory(subject=physics, price=Decimal(195), slug="phy-papers", stock=100)
    for season, copies in ((before, 10), (last, 20)):
        for index in (3, 10, 20):
            sell(book, day_in(season, index), copies, pin="781001")
    book.made_on = day_in(this, 5)
    demand.backtest(today=book.made_on)
    demand.forecast_demand(today=book.made_on)
    PrintCost.objects.create(product=book, unit_cost=60, salvage=5, on_order=25)
    demand.advise_print_run(today=book.made_on)
    return book


def recompute(book, **inputs):
    asked = {"product": book.slug, "salvage": Decimal(0), **{name: Decimal(value) for name, value in inputs.items()}}
    return reports.print_run(make_staff(roles.FINANCE), asked, today=book.made_on)


def test_the_recomputation_with_the_stored_inputs_is_the_nightly_advice(forecast):
    stored = PrintRunAdvice.objects.get(product=forecast)
    answer = recompute(forecast, net_price=stored.net_price, unit_cost="60", salvage="5")
    assert answer["critical_ratio"] == pytest.approx(stored.critical_ratio, abs=1e-4)
    assert (answer["target_quantity"], answer["supply"], answer["recommended_quantity"]) == (
        stored.target_quantity,
        stored.supply,
        stored.recommended_quantity,
    )
    assert answer["supply"] == 125 and answer["range"]["p10"] < answer["range"]["p50"] < answer["range"]["p90"]
    assert answer["method"] == demand.FORECAST and answer["data_as_of"] and answer["backtest"]["horizon_weeks"] == 4
    assert (answer["title"], answer["net_price"], answer["note"]) == (forecast.title, Decimal("195.00"), "")


def test_other_inputs_move_the_size_and_a_copy_that_sells_at_a_loss_prints_none(forecast):
    low = recompute(forecast, net_price="100", unit_cost="90")  # 10 / (10 + 90) = 0.1
    high = recompute(forecast, net_price="400", unit_cost="20")  # 380 / (380 + 20) = 0.95
    assert (low["percentile"], high["percentile"]) == (10, 95)
    assert low["target_quantity"] < high["target_quantity"]
    loss = recompute(forecast, net_price="50", unit_cost="60", salvage="5")
    assert (loss["critical_ratio"], loss["target_quantity"], loss["recommended_quantity"]) == (0.0, 0, 0)
    assert "sells at a loss" in loss["note"]


def test_the_print_run_inputs_are_checked_and_the_title_must_exist():
    book = ProductFactory(slug="phy-papers")
    for inputs, field in [
        ({"product": book.slug, "net_price": "100", "unit_cost": "50", "salvage": "60"}, "salvage"),
        ({"product": book.slug, "net_price": "-1", "unit_cost": "50"}, "net_price"),
        ({"product": book.slug, "net_price": "abc", "unit_cost": "50"}, "net_price"),
        ({"product": book.slug, "net_price": "100"}, "unit_cost"),
        ({"product": "no-such-title", "net_price": "100", "unit_cost": "50"}, "product"),
    ]:
        refused = critical(**inputs)
        assert refused.status_code == 400 and field in refused.json(), inputs
    assert signed_in(make_staff(roles.FINANCE)).post(REPORTS + "print-run/", {}).status_code == 400
    assert signed_in(make_staff(roles.SUPPORT)).post(REPORTS + "print-run/", {}, format="json").status_code == 403
