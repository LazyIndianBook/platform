"""The money of parcels: COD remittances (expected, remitted, overdue, mismatched), the wallet statement's lines (once
each, matched by AWB, reversals negative), and weight disputes due in 7 working days."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from accounts import roles
from shipping import services
from shipping.carriers.fake import FAKE
from shipping.models import CodRemittance, ShipmentCharge, ShipmentEvent, ShippingException
from shipping.services import working_days_after
from staff.models import AuditEvent
from staff.tests.conftest import make_staff, signed_in

pytestmark = pytest.mark.django_db


@pytest.fixture
def delivered(account, pickup, cod, django_capture_on_commit_callbacks):
    """A COD parcel, delivered: its remittance expected."""
    shipment = services.book(services.prepare(cod, account=account, courier_company_id=51))
    FAKE.move(shipment.tracking_number, 42, 18, 17, 7)
    with django_capture_on_commit_callbacks(execute=True):
        read = services.carrier_for(account).track([shipment.tracking_number])[shipment.tracking_number]
        services.apply_events(shipment, read, ShipmentEvent.Source.POLL)
    return services.parcel(shipment)


def test_working_days_skip_weekends():
    friday = date(2026, 10, 9)
    assert working_days_after(friday, 1) == date(2026, 10, 12)  # Monday
    assert working_days_after(friday, 10) == date(2026, 10, 23)
    assert working_days_after(date(2026, 10, 10), 1) == date(2026, 10, 12)  # from a Saturday


def test_a_remittance_is_expected_once_and_found_remitted(delivered):
    remittance = CodRemittance.objects.get(shipment=delivered)
    assert services.expect_cod(delivered) == remittance  # once
    order_id = int(delivered.detail.external_order_id)
    FAKE.remittances[order_id] = {
        "remittance_status": "Remitted",
        "remittance_utr": "UTR12345",
        "remittance_date": "2026-10-23",
        "remittance_amount": "598.00",
    }
    assert services.check_cod() == {"remitted": 1}
    remittance.refresh_from_db()
    assert (remittance.state, remittance.utr, remittance.remitted_at) == ("remitted", "UTR12345", date(2026, 10, 23))
    assert services.check_cod() == {}  # nothing awaited any more


def test_another_amount_is_a_mismatch_for_staff(delivered):
    FAKE.remittances[int(delivered.detail.external_order_id)] = {
        "remittance_utr": "UTR9",
        "remittance_amount": "498.00",
    }
    services.check_cod()
    exception = ShippingException.objects.get(kind="cod_overdue")
    assert exception.data == {"expected": "598.00", "remitted": "498.00", "utr": "UTR9"}
    assert CodRemittance.objects.get().state == "mismatch"


def test_overdue_two_working_days_after_its_day(delivered):
    remittance = CodRemittance.objects.get()
    assert services.check_cod(today=working_days_after(remittance.expected_on, 2)) == {"expected": 1}  # not yet
    assert services.check_cod(today=working_days_after(remittance.expected_on, 3)) == {"overdue": 1}
    services.check_cod(today=working_days_after(remittance.expected_on, 4))  # still overdue: one exception
    exception = ShippingException.objects.get(kind="cod_overdue")
    assert exception.state == "open" and exception.data["expected_on"] == remittance.expected_on.isoformat()
    FAKE.remittances[int(delivered.detail.external_order_id)] = {"remittance_utr": "UTR7", "remittance_amount": "598"}
    assert services.check_cod() == {"remitted": 1}  # late, but paid


def test_a_parcel_that_comes_back_owes_no_cash(account, pickup, cod):
    shipment = services.book(services.prepare(cod, account=account, courier_company_id=51))
    CodRemittance.objects.create(shipment=shipment, expected_amount=598, expected_on=timezone.localdate())
    FAKE.move(shipment.tracking_number, 42, 9)
    read = services.carrier_for(account).track([shipment.tracking_number])[shipment.tracking_number]
    services.apply_events(shipment, read, ShipmentEvent.Source.POLL)
    assert CodRemittance.objects.get().state == "not_expected"


def test_statement_lines_are_kept_once_matched_and_signed(account, delivered):
    awb = delivered.tracking_number
    rows = [
        {**FAKE.statement[0]},  # the freight, as the fake debited it
        {
            "awb_code": awb,
            "channel_order_id": delivered.detail.reference,
            "description": "Excess Weight Charge",
            "debit_amount": "48.88",
            "credit_amount": "0.00",
            "charged_weight": "1.00",
            "balance_amount": "1000.00",
            "created_at": "2026-10-12 10:00:00",
        },
        {
            "awb_code": awb,
            "description": "COD Charge Reversed",
            "debit_amount": "0.00",
            "credit_amount": "25.96",
            "balance_amount": "1025.96",
            "created_at": "2026-10-12 11:00:00",
        },
        {
            "awb_code": "NOT-OURS",
            "description": "Freight Charge",
            "debit_amount": "40.00",
            "credit_amount": "0.00",
            "balance_amount": "985.96",
            "created_at": "2026-10-12 12:00:00",
        },
        {"id": 77, "awb_code": awb, "description": "Something new", "debit_amount": "1", "created_at": "2026-10-13"},
    ]
    assert services.record_statement_lines(account, rows) == 5
    assert services.record_statement_lines(account, rows) == 0  # read again tomorrow: nothing twice
    charges = {charge.kind: charge for charge in ShipmentCharge.objects.all() if charge.shipment_id}
    assert charges["excess_weight"].amount == Decimal("48.88") and charges["cod_reversal"].amount == Decimal("-25.96")
    assert charges["other"].statement_line_id == "77"
    assert ShipmentCharge.objects.get(awb="NOT-OURS").shipment is None  # kept all the same: the money is ours
    delivered.detail.refresh_from_db()
    assert delivered.detail.charged_weight_g == 1000


def test_weight_disputes_are_exceptions_due_in_seven_working_days(account, delivered):
    FAKE.discrepancies.append(
        {**FAKE_ROW, "awb_code": delivered.tracking_number, "created_at": "2026-10-09 10:00:00", "id": 991}
    )
    FAKE.discrepancies.append({**FAKE_ROW, "awb_code": "NOT-OURS", "id": 992})
    [exception] = services.check_discrepancies(account)
    assert exception.kind == "weight_dispute" and exception.reference == "weight-991"
    assert timezone.localtime(exception.due_at).date() == date(2026, 10, 20)  # Friday + 7 working days
    assert exception.data["our_weight_g"] == 650 and exception.data["courier_weight_g"] == 1000
    assert exception.data["photo"] is False
    services.resolve_exception(exception, "Accepted: the flyer was 1 kg after all.")
    assert services.check_discrepancies(account)[0].state == "resolved"  # never opened again
    assert ShippingException.objects.filter(kind="weight_dispute").count() == 1


FAKE_ROW = {
    "order_id": 1,
    "channel_order_id": "",
    "courier_name": "Xpressbees Surface",
    "entered_weight": "0.65",
    "charged_weight": "1.00",
    "discrepancy_amount": "48.88",
    "status": "Discrepancy Raised",
    "created_at": "2026-10-12 10:00:00",
}


def test_an_exception_is_one_per_parcel_and_kind_until_resolved(account, pickup, prepaid):
    shipment = services.book(services.prepare(prepaid, account=account, courier_company_id=51))
    first = services.open_exception(shipment, "ndr", data={"attempts": 1})
    second = services.open_exception(shipment, "ndr", hours=2, data={"attempts": 2})
    assert first.pk == second.pk and second.data == {"attempts": 2}
    assert second.due_at <= timezone.now() + timedelta(hours=2)  # brought forward
    with pytest.raises(services.ShippingError):
        services.resolve_exception(second, " ")
    assert services.resolve_exception(second, "Called: deliver tomorrow.")
    assert not services.resolve_exception(second, "Again.")
    assert services.open_exception(shipment, "ndr").pk != first.pk  # a new failed attempt later


def test_finance_reconciles_a_remittance_with_the_banks_credit(delivered):
    remittance = CodRemittance.objects.get(shipment=delivered)
    url = f"/api/v1/shipping/cod/{remittance.pk}/reconcile/"
    assert signed_in(make_staff(roles.SALES)).post(url, {"utr": "UTR1", "amount": "598.00"}).status_code == 403
    finance = make_staff(roles.FINANCE)
    stale = signed_in(finance, reauth=False).post(url, {"utr": "UTR1", "amount": "598.00"})
    assert stale.json()["code"] == "reauthentication_required"  # money: a re-authentication first
    short = signed_in(finance).post(url, {"utr": "UTR7", "amount": "498.00", "on": "2026-10-23"})
    assert short.status_code == 200 and short.json()["state"] == "mismatch"
    assert ShippingException.objects.get(kind="cod_overdue", state="open").data["remitted"] == "498.00"
    paid = signed_in(finance).post(url, {"utr": "UTR8", "amount": "598.00"}).json()
    assert (paid["state"], paid["utr"], paid["remitted_amount"]) == ("remitted", "UTR8", "598.00")
    assert not ShippingException.objects.filter(kind="cod_overdue", state="open").exists()  # settled
    events = AuditEvent.objects.filter(action="payment.cod_reconciled").order_by("id")
    assert [event.details["state"] for event in events] == ["mismatch", "remitted"]
    assert {event.chain for event in events} == {"money"} and events[0].target_label == delivered.order.number
