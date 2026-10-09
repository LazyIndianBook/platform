"""What each event sends, field by field, as examleaf-erp/API.md takes it: an invoice that is a bill of supply, a tax
invoice or an invoice-cum-bill of supply, always for the one B2C customer with the parcel's city, district, state and
PIN and no personal data; a credit note and its refund; payments by mode; a delivery note; a COD and a Razorpay
settlement; an item."""

from decimal import Decimal

import pytest
from django.db import transaction
from django.utils import timezone

from content.tests import make_paper
from erp import contract, producers
from erp.fake import FAKE
from shipping.models import CodRemittance
from shop import services as shop
from shop.factories import ProductFactory, ShippingRateFactory

from .helpers import (
    code,
    invoiced,
    no_personal_data,
    ordered,
    pay_offline,
    pay_online,
    refund,
    relay,
    relay_all,
    row,
    ship_by_hand,
    stock_in,
)

pytestmark = pytest.mark.django_db


def today():
    return timezone.localdate().isoformat()


def test_a_bill_of_supply_for_the_b2c_customer_without_personal_data(on, book, customer):
    ShippingRateFactory()  # ₹40 under ₹499
    order = pay_offline(ordered((book, 1), user=customer))
    payload = row("invoice.issued").payload
    assert payload == {
        "invoice_number": order.invoice.number,
        "posting_date": today(),
        "order_number": order.number,
        "channel": "web",
        "doc_kind": "bill_of_supply",
        "shipping_address": {"city": "Guwahati", "district": "Kamrup Metro", "state": "AS", "pin": "781001"},
        "items": [
            {
                "item_code": code(book),
                "qty": 1,
                "rate": "299.00",
                "discount": "0.00",
                "hsn_code": "4901",
                "gst_rate": "0.00",
            }
        ],
        "shipping_fee": "40.00",
        "total": "339.00",
    }  # the shipping follows the books: ERPNext needs no HSN or rate for it
    assert not no_personal_data(payload)
    relay()
    made = FAKE.doc("Sales Invoice", order.invoice.number)
    assert (made["customer"], made["doc_kind"], made["exempt_value"], made["tax_total"]) == (
        "Online Customers (B2C)",
        "bill_of_supply",
        Decimal("339.00"),
        Decimal("0"),
    )


def test_a_tax_invoice_of_the_course(on, course, customer):
    order = pay_offline(ordered((course, 1), user=customer))
    payload = row("invoice.issued").payload
    assert payload["doc_kind"] == "tax_invoice" and payload["total"] == "999.00"
    assert payload["items"][0] | {"item_code": ""} == {
        "item_code": "",
        "qty": 1,
        "rate": "999.00",
        "discount": "0.00",
        "hsn_code": "999293",
        "gst_rate": "18.00",
    }
    relay()
    answer = row("invoice.issued").response
    # ERPNext rounds CGST and SGST once on the taxable value: 846.61 + 76.19 + 76.19 (the platform prints 152.39)
    assert (answer["taxable_value"], answer["tax_total"], answer["grand_total"]) == ("846.61", "152.38", "999.00")
    assert order.invoice.number == answer["name"]


def test_a_mixed_cart_is_an_invoice_cum_bill_of_supply(on, book, course, customer):
    ShippingRateFactory(free_above=Decimal("5000.00"))
    order = pay_offline(ordered((book, 2), (course, 1), user=customer))
    payload = row("invoice.issued").payload
    assert payload["doc_kind"] == "invoice_cum_bill_of_supply"
    assert [(line["qty"], line["gst_rate"]) for line in payload["items"]] == [(2, "0.00"), (1, "18.00")]
    assert (payload["shipping_fee"], payload["total"]) == ("40.00", "1637.00")
    assert "shipping_gst_rate" not in payload  # the books are the goods it carries
    assert not no_personal_data(payload)
    relay()
    made = FAKE.doc("Sales Invoice", order.invoice.number)
    assert (made["doc_kind"], made["exempt_value"], made["taxable_value"]) == (
        "invoice_cum_bill_of_supply",
        Decimal("638.00"),  # the books and the shipping
        Decimal("846.61"),
    )


def test_a_discount_is_the_line_s_rupees_off(on, book, customer):
    from shop.factories import CouponFactory

    order = pay_offline(ordered((book, 2), user=customer, coupon=CouponFactory(value=Decimal("10"))))
    [line] = row("invoice.issued").payload["items"]
    assert (line["rate"], line["qty"], line["discount"]) == ("299.00", 2, f"{order.discount.amount:.2f}")
    relay()
    assert row("invoice.issued").state == "sent"


def test_a_credit_note_and_its_refund(on, book, customer):
    order = pay_online(ordered((book, 2), user=customer))
    made = refund(order, amount=Decimal("100.00"))
    note = made.credit_note
    assert row("credit_note.issued").payload == {
        "credit_note_number": note.number,
        "invoice_number": order.invoice.number,
        "posting_date": today(),
        "reason": f"Refund {made.pk} of order {order.number}",  # never what staff typed
        "items": [{"item_code": code(book), "amount": "100.00"}],
        "shipping_credit": "0.00",
        "total": "100.00",
    }
    assert row("refund.paid").payload == {
        "invoice_number": note.number,
        "amount": "100.00",
        "posting_date": today(),
        "mode": "razorpay",
        "reference_no": f"rfnd_{made.pk}",
    }
    assert not no_personal_data(row("credit_note.issued").payload)
    relay()
    assert [entry["payment_type"] for entry in FAKE.of("Payment Entry")] == ["Receive", "Pay"]
    assert FAKE.doc("Sales Invoice", note.number)["return_against"] == order.invoice.number


@pytest.mark.parametrize(
    ("reference", "mode", "sent"),
    [
        ("NEFT UTR 401234567890 from Rahul Das", "neft", "401234567890"),
        ("UPI ref 512345678901 (rahul@okaxis)", "upi", "512345678901"),
        ("Cheque no 004512, SBI Guwahati", "cheque", "004512,"),
        ("cash at the counter", "neft", None),
    ],
)
def test_a_payment_recorded_by_staff_keeps_only_its_reference_s_numbers(on, book, customer, reference, mode, sent):
    order = pay_offline(ordered((book, 1), user=customer), reference)
    payment = order.payments.get(status="captured")
    assert row("payment.received").payload == {
        "invoice_number": order.invoice.number,
        "amount": "299.00",
        "posting_date": today(),
        "mode": mode,
        "reference_no": sent or f"payment-{payment.pk}",
    }


def test_an_online_payment_has_razorpay_s_id(on, book, customer):
    order = pay_online(ordered((book, 1), user=customer))
    payload = row("payment.received").payload
    assert (payload["mode"], payload["reference_no"]) == ("razorpay", f"pay_{order.pk}")


def test_cash_on_delivery_its_delivery_note_payment_and_settlement(on, book, customer, settings):
    settings.SHOP_COD_ENABLED = True
    order = ordered((book, 1), method="cod", user=customer)
    shop.place_cod(order)
    order = invoiced(ship_by_hand(order))  # its bill is made at dispatch: then its delivery note
    assert row("parcel.dispatched").payload == {
        "invoice_number": order.invoice.number,
        "posting_date": today(),
        "warehouse": "Main",
        "courier": "India Post",
        "tracking_number": "EA123456789IN",
    }
    shop.deliver_order(order)  # the courier collected the cash
    assert row("payment.received").payload | {"invoice_number": ""} == {
        "invoice_number": "",
        "amount": "299.00",
        "posting_date": today(),
        "mode": "cod",
        "reference_no": "EA123456789IN",  # the AWB
    }
    remittance = CodRemittance.objects.create(
        shipment=order.shipments.get(), expected_amount=299, expected_on=timezone.localdate()
    )
    remittance.remitted_amount, remittance.utr, remittance.remitted_at = 299, "UTR0042", timezone.localdate()
    remittance.state = CodRemittance.State.REMITTED
    with transaction.atomic():
        remittance.save()
    assert row("settlement.received").payload == {
        "kind": "cod",
        "settlement_id": f"cod-{remittance.pk}",
        "posting_date": today(),
        "gross_amount": "299.00",
        "fee": "0.00",
        "tax_on_fee": "0.00",
        "net_amount": "299.00",
        "utr": "UTR0042",
    }
    relay()  # the item first: then the copies in ERPNext
    stock_in(book, 10)
    relay_all()
    assert {r.event: r.state for r in order_rows(order)} == {
        "invoice.issued": "sent",
        "parcel.dispatched": "sent",
        "payment.received": "sent",
        "settlement.received": "sent",
    }
    assert FAKE.bins[(code(book), "Main - EL")] == 9


def order_rows(order):
    from erp.models import ErpOutbox

    return ErpOutbox.objects.filter(aggregate_id=order.number)


def test_a_razorpay_settlement(on):
    settlement = {"id": "setl_ABC123", "date": "2026-10-08", "gross": "1000.00", "fees": "20.00", "tax": "3.60"}
    written = producers.razorpay_settlement({**settlement, "net": "976.40", "utr": "UTR1"})
    assert (written.aggregate_type, written.aggregate_id) == ("settlement", "setl_ABC123")
    assert written.payload == {
        "kind": "razorpay",
        "settlement_id": "setl_ABC123",
        "posting_date": "2026-10-08",
        "gross_amount": "1000.00",
        "fee": "20.00",
        "tax_on_fee": "3.60",
        "net_amount": "976.40",
        "utr": "UTR1",
    }
    relay()
    written.refresh_from_db()
    assert written.state == "sent" and FAKE.of("Journal Entry")[0]["gross"] == Decimal("1000.00")


def test_an_item_with_its_catalogue_fields_and_a_valid_isbn_only(switched_on):
    paper = make_paper()
    book = ProductFactory(subject=paper.book.subject, book=paper.book, isbn="978-0-306-40615-7", weight_grams=310)
    assert row("item.upserted").payload == {
        "item_code": contract.item_code(book),
        "item_name": book.title,
        "kind": "sample-papers",
        "hsn_code": "4901",
        "gst_rate": "0.00",
        "mrp": "349.00",
        "weight_grams": 310,
        "is_active": True,
        "isbn": "9780306406157",
        "subject": "Physics",
        "class_level": "12",
        "board": "ASSEB",
    }
    other = ProductFactory(isbn="978-0-306-40615-8")  # a wrong check digit: ERPNext would refuse the item
    assert "isbn" not in row("item.upserted", examleaf_ref=f"item:{other.pk}").payload
