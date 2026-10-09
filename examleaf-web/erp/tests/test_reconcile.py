"""The nightly reconciliation: quiet for a day that went through whole (GST within ERPNext's rounding), and a
difference planted in ERPNext found, kept, announced to the staff inbox and emailed; a document ERPNext never got;
the stock invariant; ERPNext unreachable; nothing while switched off."""

from decimal import Decimal

import pytest
from django.db import transaction
from django.utils import timezone

from erp import reconcile, signals
from erp.fake import FAKE
from erp.models import ErpOutbox, ErpReconciliationRun
from integrations.client import IntegrationError
from shipping.models import CodRemittance
from shop import services as shop

from .helpers import code, invoiced, ordered, pay_offline, pay_online, refund, relay, relay_all, ship_by_hand, stock_in

pytestmark = pytest.mark.django_db


@pytest.fixture
def day(on, book, course, customer, settings):
    """A day of the shop, mirrored whole: a prepaid parcel, a mixed cart paid online (book and course) shipped and
    partly refunded, a cash-on-delivery parcel delivered and its cash remitted; ERPNext holding the copies."""
    settings.SHOP_COD_ENABLED = True
    relay()
    stock_in(book, 20)  # what the platform holds, as the initial load's stock count would
    ship_by_hand(pay_offline(ordered((book, 2), user=customer)))
    online = ship_by_hand(pay_online(ordered((book, 1), (course, 1), user=customer)), "EA000000002IN")
    refund(online, amount=Decimal("100.00"))
    cod = ordered((book, 1), method="cod", user=customer)
    shop.place_cod(cod)
    cod = invoiced(ship_by_hand(cod, "EA000000003IN"))
    shop.deliver_order(cod)
    remittance = CodRemittance.objects.create(
        shipment=cod.shipments.get(), expected_amount=299, expected_on=timezone.localdate()
    )
    remittance.remitted_amount, remittance.utr, remittance.remitted_at = 299, "UTR0042", timezone.localdate()
    remittance.state = CodRemittance.State.REMITTED
    with transaction.atomic():
        remittance.save()
    relay_all()
    assert not ErpOutbox.objects.exclude(state="sent").exists()
    return timezone.localdate()


def differences(run):
    return sorted(run.differences.values_list("kind", "key", "platform_value", "erp_value"))


def test_a_day_that_went_through_whole_is_quiet(day, book):
    run = reconcile.run(day)
    assert run.state == "done" and differences(run) == []
    assert run.platform_totals["invoices"] | {"taxed": 0} == {
        "count": 3,
        "total": "2195.00",
        "exempt_value": "1196.00",
        "taxable_value": "846.61",
        "tax_total": "152.39",  # the platform's; ERPNext's 152.38 is within its rounding
        "taxed": 0,
    }
    assert run.erp_totals["invoices"]["tax_total"] == "152.38"
    assert run.platform_totals["payments"]["receive"] == {
        "cod": {"count": 1, "amount": "299.00"},
        "neft": {"count": 1, "amount": "598.00"},
        "razorpay": {"count": 1, "amount": "1298.00"},
    }
    assert run.platform_totals["payments"]["refund"] == {"razorpay": {"count": 1, "amount": "100.00"}}
    assert run.platform_totals["shipped"] == {"delivery_notes": 3, "items": {code(book): 4}}
    assert run.platform_totals["stock"][code(book)]["available"] == 16


def test_a_planted_difference_is_found_kept_announced_and_emailed(
    day, settings, mailoutbox, django_capture_on_commit_callbacks
):
    settings.ERP_ALERT_EMAILS = ["finance@examleaf.in"]
    first = FAKE.of("Sales Invoice")[0]
    first["grand_total"] += Decimal("1.00")  # changed in ERPNext by hand
    payment = next(entry for entry in FAKE.of("Payment Entry") if entry["mode"] == "neft")
    FAKE.docs.pop(("Payment Entry", payment["name"]))  # deleted there
    told = []
    signals.reconciliation_difference.connect(
        lambda sender, difference, **kwargs: told.append(difference), weak=False, dispatch_uid="t"
    )
    try:
        with django_capture_on_commit_callbacks(execute=True):
            run = reconcile.run(day)
    finally:
        signals.reconciliation_difference.disconnect(dispatch_uid="t")
    assert differences(run) == [
        ("invoices", "total", "2195.00", "2196.00"),
        ("payments", "receive neft amount", "598.00", "0.00"),
        ("payments", "receive neft count", "1", "0"),
    ]
    assert run.differences_count == 3 and {d.pk for d in told} == set(run.differences.values_list("pk", flat=True))
    [email] = mailoutbox
    assert email.to == ["finance@examleaf.in"] and "3 difference(s)" in email.subject
    assert "- invoices total: 2195.00 here, 2196.00 in ERPNext" in email.body
    assert "rahul" not in email.body.lower()


def test_gst_beyond_erpnext_s_rounding_is_a_difference(day):
    taxed = next(d for d in FAKE.of("Sales Invoice") if d["doc_kind"] == "invoice_cum_bill_of_supply")
    taxed["tax_total"] -= Decimal("0.05")
    assert differences(reconcile.run(day)) == [("invoices", "tax_total", "152.39", "152.33")]


def test_a_document_erpnext_never_got_is_named_with_where_its_row_is(day, book, customer):
    order = pay_offline(ordered((book, 1), user=customer))
    FAKE.fail("create_sales_invoice", 409, body={"message": {"ok": False, "error": {"code": "conflict"}}})
    relay()
    found = differences(reconcile.run(day))
    assert ("missing", f"invoice:{order.invoice.number}", "outbox: dead", "") in found
    assert ("missing", f"payment:{order.payments.get(status='captured').pk}", "outbox: pending", "") in found
    assert ("invoices", "count", "4", "3") in found


def test_the_stock_invariant(day, book):
    FAKE.move(code(book), "Main - EL", Decimal(-3))  # three copies written off in ERPNext, not here
    assert differences(reconcile.run(day)) == [("stock", code(book), "16", "13")]


def test_erpnext_unreachable_fails_the_run_and_is_raised(on):
    FAKE.fail("daily_totals", 503)
    with pytest.raises(IntegrationError):
        reconcile.run(timezone.localdate())
    failed = ErpReconciliationRun.objects.get()
    assert failed.state == "failed" and "503" in failed.error and failed.finished_at


def test_nothing_is_reconciled_while_switched_off(erp_account):
    assert reconcile.run() is None and not ErpReconciliationRun.objects.exists()


def test_yesterday_by_default(on):
    run = reconcile.run()
    assert run.date == timezone.localdate() - timezone.timedelta(days=1) and differences(run) == []
