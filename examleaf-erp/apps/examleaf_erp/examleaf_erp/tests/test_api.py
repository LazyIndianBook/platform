"""The sync API (examleaf_erp.api, API.md): idempotency, the legal numbers, the document kinds, credit notes, payments,
settlements, FIFO dispatch, the read side and the Sync Log."""

import json
from decimal import Decimal

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt, getdate, now_datetime

from examleaf_erp import api
from examleaf_erp.tests.utils import (
    abbr,
    as_user,
    invoice_payload,
    line,
    log_rows,
    make_invoice,
    make_item,
    number,
    ok,
    receive,
    sync_user,
    unique,
)


class TestSyncAPI(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.book = make_item("sample-papers", "0", "4901", mrp="299.00")
        cls.solutions = make_item("solutions", "0", "4901", mrp="199.00")
        cls.course = make_item("digital", "18", "999293", mrp="999.00")
        receive(cls.book, 50, "2026-04-01")
        receive(cls.solutions, 50, "2026-04-01")
        frappe.db.commit()

    # ---------------------------------------------------------------------------------------------- basics
    def test_ping(self):
        response = ok(api.ping())
        self.assertEqual(response["name"], frappe.local.site)
        self.assertIn("examleaf_erp", response["versions"])
        self.assertIsNone(response["examleaf_ref"])

    def test_unknown_and_missing_fields_are_refused_and_logged(self):
        payload = invoice_payload([line(self.book, 1, "299.00")], colour="blue")
        response = api.create_sales_invoice(**payload)
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"], {"code": "invalid_request", "message": "Unknown field.", "field": "colour"})
        self.assertEqual(frappe.local.response.http_status_code, 400)
        self.assertEqual(frappe.db.get_value("ExamLeaf Sync Log", response["log"], "status"), "Error")
        self.assertFalse(frappe.db.exists("Sales Invoice", payload["invoice_number"]))

        payload = invoice_payload([line(self.book, 1, "299.00")])
        del payload["items"][0]["gst_rate"]
        response = api.create_sales_invoice(**payload)
        self.assertEqual(response["error"]["field"], "items[0].gst_rate")

    # ---------------------------------------------------------------------------------------------- idempotency
    def test_same_key_twice_returns_the_first_result(self):
        payload = invoice_payload([line(self.book, 2, "299.00")])
        first = ok(api.create_sales_invoice(**payload))
        second = ok(api.create_sales_invoice(**payload))
        self.assertFalse(first["duplicate"])
        self.assertTrue(second["duplicate"])
        self.assertEqual(first["name"], second["name"])
        self.assertEqual(frappe.db.count("Sales Invoice", {"examleaf_ref": payload["examleaf_ref"]}), 1)
        self.assertEqual(
            [r.status for r in log_rows(idempotency_key=payload["idempotency_key"])], ["Success", "Duplicate"]
        )
        replay = frappe.db.get_value(
            "ExamLeaf Sync Log", second["log"], ["status", "duplicate_of", "reference_name"], as_dict=True
        )
        self.assertEqual(
            (replay.status, replay.duplicate_of, replay.reference_name), ("Duplicate", str(first["log"]), first["name"])
        )

    def test_same_ref_with_a_new_key_is_a_duplicate(self):
        payload = invoice_payload([line(self.book, 1, "299.00")])
        first = ok(api.create_sales_invoice(**payload))
        again = ok(api.create_sales_invoice(**{**payload, "idempotency_key": unique("retry-")}))
        self.assertTrue(again["duplicate"])
        self.assertEqual(again["name"], first["name"])
        self.assertEqual(frappe.db.count("Sales Invoice", {"examleaf_ref": payload["examleaf_ref"]}), 1)

    def test_a_key_reused_for_another_request_is_a_conflict(self):
        payload = invoice_payload([line(self.book, 1, "299.00")])
        ok(api.create_sales_invoice(**payload))
        frappe.db.commit()
        other = invoice_payload([line(self.book, 3, "299.00")], idempotency_key=payload["idempotency_key"])
        response = api.create_sales_invoice(**other)
        self.assertEqual(response["error"]["code"], "idempotency_key_reused")
        self.assertEqual(frappe.local.response.http_status_code, 409)
        self.assertFalse(frappe.db.exists("Sales Invoice", other["invoice_number"]))

    def test_a_number_held_by_another_reference_is_a_conflict(self):
        payload = invoice_payload([line(self.book, 1, "299.00")])
        ok(api.create_sales_invoice(**payload))
        frappe.db.commit()
        response = api.create_sales_invoice(
            **{**payload, "examleaf_ref": "invoice:someone-else", "idempotency_key": unique()}
        )
        self.assertEqual(response["error"]["code"], "conflict")

    def test_a_second_order_under_a_number_is_a_conflict(self):
        # the shadow run (examleaf-web/erp/SHADOW-RUN.md): a number issued again for another order (a restored
        # database, a second platform) carries the same reference, and was answered as the first one's duplicate
        payload = invoice_payload([line(self.book, 1, "299.00")])
        ok(api.create_sales_invoice(**payload))
        frappe.db.commit()
        other = invoice_payload([line(self.book, 3, "299.00")], invoice_number=payload["invoice_number"])
        other["order_number"] = payload["order_number"][:-1] + ("1" if payload["order_number"][-1] != "1" else "2")
        response = api.create_sales_invoice(**other)
        self.assertEqual((response["error"]["code"], response["error"]["field"]), ("conflict", "order_number"))
        self.assertEqual(frappe.local.response.http_status_code, 409)
        kept = frappe.db.get_value("Sales Invoice", payload["invoice_number"], ["examleaf_order_no", "grand_total"])
        self.assertEqual((kept[0], flt(kept[1])), (payload["order_number"], 299.0))

    # ---------------------------------------------------------------------------------------------- numbers and kinds
    def test_the_invoice_takes_the_platforms_number_and_passes_india_compliance(self):
        from india_compliance.gst_india.utils import validate_invoice_number

        invoice = make_invoice([line(self.book, 1, "299.00")])
        self.assertRegex(invoice.name, r"^EL/\d{4}-\d{2}/\d{5}$")
        self.assertEqual(len(invoice.name), 16)
        self.assertEqual(invoice.docstatus, 1)
        self.assertTrue(validate_invoice_number(invoice, throw=False))
        self.assertEqual(invoice.customer, "Online Customers (B2C)")
        self.assertEqual(invoice.place_of_supply, "18-Assam")

    def test_an_all_exempt_invoice_is_a_bill_of_supply(self):
        invoice = make_invoice([line(self.book, 2, "299.00"), line(self.solutions, 1, "199.00")], shipping_fee="40.00")
        self.assertEqual(invoice.examleaf_doc_kind, "bill_of_supply")
        self.assertEqual(invoice.select_print_heading, "Bill of Supply")
        self.assertEqual(flt(invoice.total_taxes_and_charges), 0)
        self.assertEqual(flt(invoice.grand_total), 837.00)
        shipping = next(row for row in invoice.items if row.item_code == "EL-SHIPPING")
        self.assertEqual((shipping.gst_hsn_code, shipping.item_tax_template), ("4901", f"GST Exempted - {abbr()}"))

    def test_a_mixed_cart_is_an_invoice_cum_bill_of_supply(self):
        invoice = make_invoice(
            [line(self.book, 1, "299.00"), line(self.course, 1, "999.00", gst_rate="18", hsn_code="999293")]
        )
        self.assertEqual(invoice.examleaf_doc_kind, "invoice_cum_bill_of_supply")
        self.assertEqual(invoice.select_print_heading, "Invoice-cum-Bill of Supply")
        self.assertEqual(flt(invoice.grand_total), 1298.00)
        course = next(row for row in invoice.items if row.item_code == self.course)
        self.assertEqual(flt(course.taxable_value), 846.61)  # 999 / 1.18, halves up, as shop/invoices.py
        # each tax on the taxable value: 9 % of 846.61 = 76.19 twice; the price's last paisa is round-off (API.md)
        self.assertEqual(flt(invoice.total_taxes_and_charges), 152.38)
        self.assertEqual({flt(row.tax_amount) for row in invoice.taxes}, {76.19})
        accounts = {row.account_head.rsplit(" - ", 1)[0] for row in invoice.taxes}
        self.assertEqual(accounts, {"Output Tax CGST", "Output Tax SGST"})  # Assam to Assam

    def test_a_taxed_cart_out_of_state_is_a_tax_invoice_with_igst(self):
        invoice = make_invoice(
            [line(self.course, 1, "999.00", gst_rate="18", hsn_code="999293")], state="WB", pin="700001", city="Kolkata"
        )
        self.assertEqual(invoice.examleaf_doc_kind, "tax_invoice")
        self.assertEqual(invoice.select_print_heading, "Tax Invoice")
        self.assertEqual(invoice.place_of_supply, "19-West Bengal")
        self.assertEqual({row.account_head.rsplit(" - ", 1)[0] for row in invoice.taxes}, {"Output Tax IGST"})
        self.assertEqual(invoice.territory, "Rest of India")

    def test_a_discount_that_does_not_divide_keeps_the_line_exact(self):
        invoice = make_invoice([line(self.book, 3, "299.00", discount="10.00")])
        rows = [row for row in invoice.items if row.item_code == self.book]
        self.assertEqual(sorted((row.qty, flt(row.rate)) for row in rows), [(1, 295.66), (2, 295.67)])
        self.assertEqual(flt(invoice.grand_total), 887.00)

    def test_the_districts_territory(self):
        invoice = make_invoice([line(self.book, 1, "299.00")], district="Jorhat", pin="785001", city="Jorhat")
        self.assertEqual(invoice.territory, "Jorhat")

    def test_totals_that_do_not_add_up_are_refused(self):
        payload = invoice_payload([line(self.book, 1, "299.00")])
        payload["total"] = "300.00"
        response = api.create_sales_invoice(**payload)
        self.assertEqual((response["error"]["code"], response["error"]["field"]), ("invalid_request", "total"))

    def test_the_declared_kind_must_match_the_lines(self):
        payload = invoice_payload([line(self.book, 1, "299.00")], doc_kind="tax_invoice")
        response = api.create_sales_invoice(**payload)
        self.assertEqual(response["error"]["code"], "doc_kind_mismatch")
        self.assertFalse(frappe.db.exists("Sales Invoice", payload["invoice_number"]))

    def test_the_number_must_belong_to_the_posting_dates_year(self):
        payload = invoice_payload([line(self.book, 1, "299.00")])
        payload["invoice_number"] = "EL/2019-20/00001"
        response = api.create_sales_invoice(**payload)
        self.assertEqual(response["error"]["field"], "invoice_number")

    def test_the_test_series_only_where_allowed(self):
        payload = invoice_payload([line(self.book, 1, "299.00")], invoice_number=number("T"))
        allowed = frappe.local.conf.get("examleaf_allow_test_series")
        try:
            frappe.local.conf.examleaf_allow_test_series = 0
            refused = api.create_sales_invoice(**payload)
            self.assertEqual(refused["error"]["field"], "invoice_number")
            frappe.local.conf.examleaf_allow_test_series = 1
            ok(api.create_sales_invoice(**{**payload, "idempotency_key": unique()}))
        finally:
            frappe.local.conf.examleaf_allow_test_series = allowed

    # ---------------------------------------------------------------------------------------------- cancel and amend
    def test_a_platform_invoice_is_never_cancelled_or_amended(self):
        invoice = make_invoice([line(self.book, 1, "299.00")])
        frappe.db.commit()
        with self.assertRaisesRegex(frappe.ValidationError, "credit note"):
            invoice.cancel()
        frappe.db.rollback()
        invoice.reload()  # the refused cancel left docstatus 2 on the object
        amendment = frappe.copy_doc(invoice)
        amendment.amended_from = invoice.name
        with self.assertRaisesRegex(frappe.ValidationError, "credit note"):
            amendment.insert()

    def test_a_cancelled_number_is_not_issued_again(self):
        invoice = make_invoice([line(self.book, 1, "299.00")])
        frappe.db.set_value("Sales Invoice", invoice.name, "docstatus", 2)  # as an invoice cancelled before this app
        frappe.db.commit()
        payload = invoice_payload([line(self.book, 1, "299.00")], invoice_number=invoice.name)
        response = api.create_sales_invoice(**{**payload, "examleaf_ref": f"invoice:{unique()}"})
        self.assertEqual(response["error"]["code"], "amendment_refused")
        self.assertEqual(frappe.local.response.http_status_code, 409)
        again = api.create_sales_invoice(**{**payload, "idempotency_key": unique()})  # its own reference
        self.assertEqual(again["error"]["code"], "cancelled")

    # ---------------------------------------------------------------------------------------------- credit notes
    def credit(self, invoice, items, shipping="0.00", **extra):
        total = sum((Decimal(i["amount"]) for i in items), Decimal("0.00")) + Decimal(shipping)
        note_number = extra.pop("credit_note_number", None) or number("CN")
        return api.create_credit_note(
            examleaf_ref=f"credit_note:{note_number}",  # the platform's kinds: order, invoice, credit_note, payment, …
            idempotency_key=unique("cn-"),
            credit_note_number=note_number,
            invoice_number=invoice.name,
            posting_date=str(getdate()),
            reason="Parcel refused",
            items=items,
            shipping_credit=shipping,
            total=f"{total:.2f}",
            **extra,
        )

    def test_a_credit_note_takes_its_number_and_points_at_the_invoice(self):
        invoice = make_invoice([line(self.book, 2, "299.00"), line(self.solutions, 1, "199.00")], shipping_fee="40.00")
        response = ok(self.credit(invoice, [{"item_code": self.book, "amount": "598.00", "qty": 2}], shipping="40.00"))
        note = frappe.get_doc("Sales Invoice", response["name"])
        self.assertRegex(note.name, r"^CN/\d{4}-\d{2}/\d{5}$")
        self.assertEqual((note.is_return, note.return_against, note.docstatus), (1, invoice.name, 1))
        self.assertEqual(flt(note.grand_total), -638.00)
        self.assertEqual(response["total_credit"], "638.00")
        self.assertEqual(note.place_of_supply, invoice.place_of_supply)
        self.assertEqual(note.examleaf_order_no, invoice.examleaf_order_no)
        self.assertEqual(sorted(-row.qty for row in note.items), [1, 2])  # two books and the shipping line

    def test_a_credit_note_number_against_another_invoice_is_a_conflict(self):
        first, second = make_invoice([line(self.book, 1, "299.00")]), make_invoice([line(self.book, 1, "299.00")])
        frappe.db.commit()
        note_number = number("CN")
        ok(self.credit(first, [{"item_code": self.book, "amount": "50.00"}], credit_note_number=note_number))
        frappe.db.commit()
        response = self.credit(second, [{"item_code": self.book, "amount": "50.00"}], credit_note_number=note_number)
        self.assertEqual((response["error"]["code"], response["error"]["field"]), ("conflict", "invoice_number"))
        self.assertEqual(frappe.db.get_value("Sales Invoice", note_number, "return_against"), first.name)

    def test_a_value_only_credit_uses_the_fewest_units(self):
        invoice = make_invoice([line(self.book, 3, "299.00")])
        note = frappe.get_doc(
            "Sales Invoice", ok(self.credit(invoice, [{"item_code": self.book, "amount": "50.00"}]))["name"]
        )
        self.assertEqual([(row.qty, flt(row.rate)) for row in note.items], [(-1, 50.0)])
        frappe.db.commit()
        too_much = self.credit(invoice, [{"item_code": self.book, "amount": "300.00", "qty": 1}])
        self.assertEqual(too_much["error"]["code"], "over_credit")

    # ---------------------------------------------------------------------------------------------- payments
    def pay(self, against, amount, mode="razorpay", reference=None):
        return api.create_payment_entry(
            examleaf_ref=f"payment:{unique()}",
            idempotency_key=unique("pay-"),
            invoice_number=against,
            amount=amount,
            posting_date=str(getdate()),
            mode=mode,
            reference_no=reference or unique("pay_"),
        )

    def test_a_payment_settles_the_invoice_and_a_refund_settles_its_credit_note(self):
        invoice = make_invoice([line(self.book, 2, "299.00")])
        paid = ok(self.pay(invoice.name, "598.00"))
        entry = frappe.get_doc("Payment Entry", paid["name"])
        self.assertEqual(
            (entry.payment_type, entry.paid_to, entry.mode_of_payment),
            ("Receive", f"Razorpay Clearing - {abbr()}", "Razorpay"),
        )
        self.assertEqual(paid["outstanding_after"], "0.00")
        note = ok(self.credit(invoice, [{"item_code": self.book, "amount": "299.00", "qty": 1}]))
        refund = ok(self.pay(note["name"], "299.00", reference=unique("rfnd_")))
        self.assertEqual(refund["payment_type"], "Pay")
        self.assertEqual(refund["outstanding_after"], "0.00")
        self.assertEqual(flt(frappe.db.get_value("Sales Invoice", note["name"], "outstanding_amount")), 0)

    def test_cod_goes_to_the_couriers_account_and_overpayment_is_refused(self):
        invoice = make_invoice([line(self.book, 1, "299.00")])
        paid = ok(self.pay(invoice.name, "299.00", mode="cod", reference="AWB123456"))
        self.assertEqual(frappe.db.get_value("Payment Entry", paid["name"], "paid_to"), f"COD in Transit - {abbr()}")
        frappe.db.commit()
        again = self.pay(invoice.name, "1.00", mode="cod")
        self.assertEqual(again["error"]["code"], "overpayment")

    def test_a_razorpay_settlement_moves_clearing_to_the_bank(self):
        settlement = unique("setl_")
        settled = ok(api.daily_totals(date=str(getdate())))["settlements"].get("razorpay", {})
        response = ok(
            api.record_settlement(
                examleaf_ref=f"settlement:{settlement}",
                idempotency_key=unique(),
                kind="razorpay",
                settlement_id=settlement,
                posting_date=str(getdate()),
                gross_amount="1000.00",
                fee="20.00",
                tax_on_fee="3.60",
                net_amount="976.40",
                utr="AXISN26100912345",
            )
        )
        entry = frappe.get_doc("Journal Entry", response["name"])
        lines = {row.account.rsplit(" - ", 1)[0]: (flt(row.debit), flt(row.credit)) for row in entry.accounts}
        self.assertEqual(lines["Razorpay Clearing"], (0, 1000.0))
        self.assertEqual(lines["Payment Gateway Charges"], (20.0, 0))
        self.assertEqual(lines["Input Tax IGST"], (3.6, 0))
        self.assertEqual(lines["Main Bank"], (976.4, 0))
        self.assertEqual(entry.cheque_no, "AXISN26100912345")  # the bank statement's reference
        self.assertIn(settlement, entry.user_remark)
        now = ok(api.daily_totals(date=str(getdate())))["settlements"]["razorpay"]
        self.assertEqual(now["count"] - settled.get("count", 0), 1)
        self.assertEqual(Decimal(now["total"]) - Decimal(settled.get("total", "0")), Decimal("1000.00"))
        refused = api.record_settlement(
            examleaf_ref=f"settlement:{unique()}",
            idempotency_key=unique(),
            kind="cod",
            settlement_id="R1",
            posting_date=str(getdate()),
            gross_amount="100.00",
            net_amount="90.00",
        )
        self.assertEqual(refused["error"]["field"], "gross_amount")

    # ---------------------------------------------------------------------------------------------- dispatch and stock
    def test_a_delivery_note_takes_the_oldest_print_run_first(self):
        book = make_item("sample-papers", "0", "4901")
        newer = receive(book, 10, "2026-06-01")  # received first, printed later
        older = receive(book, 3, "2026-04-10")
        invoice = make_invoice([line(book, 5, "299.00")], shipping_fee="40.00")
        before = flt(frappe.db.get_value("Bin", {"item_code": book, "warehouse": f"Main - {abbr()}"}, "actual_qty"))
        response = ok(
            api.create_delivery_note(
                examleaf_ref=f"shipment:{unique()}",
                idempotency_key=unique(),
                invoice_number=invoice.name,
                posting_date=str(getdate()),
                courier="India Post",
                tracking_number="EK123456789IN",
            )
        )
        self.assertEqual(
            sorted((b["batch_no"], b["qty"]) for b in response["batches"]), sorted([(older, 3.0), (newer, 2.0)])
        )
        after = flt(frappe.db.get_value("Bin", {"item_code": book, "warehouse": f"Main - {abbr()}"}, "actual_qty"))
        self.assertEqual(before - after, 5)
        note = frappe.get_doc("Delivery Note", response["name"])
        self.assertEqual([row.item_code for row in note.items], [book])  # the shipping line does not travel
        self.assertEqual((note.lr_no, note.docstatus), ("EK123456789IN", 1))
        stock = ok(api.get_stock(item_code=book, warehouse="Main"))["items"][0]
        self.assertEqual(stock["actual_qty"], 8)
        self.assertEqual([b["batch_no"] for b in stock["batches"]], [newer])

    def test_a_delivery_note_needs_the_stock(self):
        book = make_item("sample-papers", "0", "4901")
        receive(book, 1, "2026-04-01")
        invoice = make_invoice([line(book, 2, "299.00")])
        frappe.db.commit()
        response = api.create_delivery_note(
            examleaf_ref=f"shipment:{unique()}",
            idempotency_key=unique(),
            invoice_number=invoice.name,
            posting_date=str(getdate()),
        )
        self.assertEqual(response["error"]["code"], "insufficient_stock")

    def test_a_bundle_ships_its_books(self):
        bundle = make_item("bundle", "0", "4901", mrp="499.00")
        ok(
            api.upsert_bundle(
                examleaf_ref=f"bundle:{bundle.lower()}",  # its own ref, not the Item's
                idempotency_key=unique(),
                item_code=bundle,
                items=[{"item_code": self.book, "qty": 1}, {"item_code": self.solutions, "qty": 1}],
            )
        )
        frappe.db.commit()  # a refusal rolls back
        not_a_bundle = api.upsert_bundle(
            examleaf_ref=f"bundle:{self.book.lower()}",
            idempotency_key=unique(),
            item_code=self.book,
            items=[{"item_code": self.solutions, "qty": 1}],
        )
        self.assertEqual(not_a_bundle["error"]["code"], "conflict")
        invoice = make_invoice([line(bundle, 1, "449.00")])
        response = ok(
            api.create_delivery_note(
                examleaf_ref=f"shipment:{unique()}",
                idempotency_key=unique(),
                invoice_number=invoice.name,
                posting_date=str(getdate()),
            )
        )
        self.assertEqual(sorted(b["item_code"] for b in response["batches"]), sorted([self.book, self.solutions]))

    # ---------------------------------------------------------------------------------------------- the read side
    def test_daily_totals_count_what_was_made_today(self):
        today = str(getdate())
        before = ok(api.daily_totals(date=today))
        make_invoice([line(self.book, 1, "299.00")], shipping_fee="40.00")
        mixed = make_invoice(
            [line(self.solutions, 1, "199.00"), line(self.course, 1, "999.00", gst_rate="18", hsn_code="999293")]
        )
        self.pay(mixed.name, "1198.00", mode="upi", reference="UTR1")
        self.credit(mixed, [{"item_code": self.solutions, "amount": "199.00", "qty": 1}])
        ok(
            api.create_delivery_note(
                examleaf_ref=f"shipment:{unique()}",
                idempotency_key=unique(),
                invoice_number=mixed.name,
                posting_date=today,
            )
        )
        after = ok(api.daily_totals(date=today))

        def delta(path):
            def get(d):
                for key in path.split("."):
                    d = d.get(key, {}) if isinstance(d, dict) else 0
                return Decimal(str(d or 0))

            return get(after) - get(before)

        self.assertEqual(delta("invoices.count"), 2)
        self.assertEqual(delta("invoices.total"), Decimal("1537.00"))
        self.assertEqual(delta("invoices.exempt_value"), Decimal("538.00"))  # 299 + 40 + 199
        self.assertEqual(delta("invoices.taxable_value"), Decimal("846.61"))
        self.assertEqual(delta("invoices.tax_total"), Decimal("152.38"))
        self.assertEqual(delta("credit_notes.count"), 1)
        self.assertEqual(delta("credit_notes.total"), Decimal("199.00"))
        self.assertEqual(delta("payments.receive.upi.amount"), Decimal("1198.00"))
        self.assertEqual(delta("shipped.items." + self.solutions), 1)

    def test_get_changes_since_pages_without_gaps_or_repeats(self):
        codes = [make_item() for _ in range(3)]
        stamp = now_datetime().replace(microsecond=0) + __import__("datetime").timedelta(days=3650)
        for code in codes:  # one shared modified time: only the name orders them
            frappe.db.set_value("Item", code, "modified", stamp, update_modified=False)
        seen, cursor = [], {"modified_after": str(add_days(stamp, -1))}
        while True:
            response = ok(api.get_changes_since(doctype="Item", limit=2, **cursor))
            seen += [row["name"] for row in response["rows"]]
            if not response["has_more"]:
                break
            cursor = response["next"]
        self.assertEqual([code for code in seen if code in codes], sorted(codes))
        self.assertEqual(len(seen), len(set(seen)))

    # ---------------------------------------------------------------------------------------------- catalogue and B2B
    def test_upsert_item_updates_and_keeps_dated_rates(self):
        code = make_item("digital", "18", "999293", mrp="999.00")
        response = ok(
            api.upsert_item(
                examleaf_ref=f"product:{code.lower()}",
                idempotency_key=unique(),
                item_code=code,
                item_name="Renamed course",
                kind="digital",
                hsn_code="999293",
                gst_rate="5",
                gst_rate_effective_from=str(add_days(getdate(), 1)),
                mrp="899.00",
                isbn="978-0-306-40615-7",
            )
        )
        self.assertFalse(response["created"])
        item = frappe.get_doc("Item", code)
        self.assertEqual(item.item_name, "Renamed course")
        self.assertEqual(item.isbn, "9780306406157")
        self.assertEqual(
            [(r.item_tax_template.split(" - ")[0], str(r.valid_from or "")) for r in item.taxes],
            [("GST 18%", ""), ("GST 5%", str(add_days(getdate(), 1)))],
        )
        price = frappe.db.get_value("Item Price", {"item_code": code, "price_list": "MRP"}, "price_list_rate")
        self.assertEqual(flt(price), 899.0)
        frappe.db.commit()  # the refusals below roll back their transaction
        bad = api.upsert_item(**{**self.item_payload(code), "isbn": "978-0-306-40615-8"})
        self.assertEqual(bad["error"]["field"], "isbn")
        moved = api.upsert_item(**{**self.item_payload(code), "item_code": unique("OTHER-")})
        self.assertEqual(moved["error"]["code"], "conflict")

    def item_payload(self, code):
        return {
            "examleaf_ref": f"product:{code.lower()}",
            "idempotency_key": unique(),
            "item_code": code,
            "item_name": "x",
            "kind": "digital",
            "hsn_code": "999293",
            "gst_rate": "18",
            "mrp": "1.00",
        }

    def test_upsert_b2b_customer(self):
        ref = f"school:{unique()}"
        payload = {
            "examleaf_ref": ref,
            "idempotency_key": unique(),
            "customer_name": unique("Cotton School "),
            "customer_group": "School",
            "udise_code": "18270100101",
            "school_board": "ASSEB",
            "school_medium": "English",
            "district": "Kamrup Metro",
            "address": {
                "line1": "Panbazar",
                "city": "Guwahati",
                "district": "Kamrup Metro",
                "state": "AS",
                "pin": "781001",
            },
            "contact": {"name": "Anita Das", "email": f"{unique()}@example.com", "phone": "+91 98640 12345"},
        }
        created = ok(api.upsert_b2b_customer(**payload))
        customer = frappe.get_doc("Customer", created["name"])
        self.assertEqual(
            (customer.customer_group, customer.territory, customer.udise_code),
            ("School", "Kamrup Metro", "18270100101"),
        )
        self.assertTrue(customer.customer_primary_contact and customer.customer_primary_address)
        again = ok(api.upsert_b2b_customer(**{**payload, "idempotency_key": unique(), "school_medium": "Assamese"}))
        self.assertFalse(again["created"])
        self.assertEqual(frappe.db.get_value("Customer", created["name"], "school_medium"), "Assamese")
        wrong = api.upsert_b2b_customer(**{**payload, "idempotency_key": unique(), "customer_group": "Distributor"})
        self.assertEqual(wrong["error"]["field"], "udise_code")

    # ---------------------------------------------------------------------------------------------- least privilege
    def test_the_sync_user_can_do_its_work_and_no_more(self):
        user = sync_user()
        with as_user(user):
            book = make_item("sample-papers", "0", "4901")
            bundle = make_item("bundle", "0", "4901", mrp="399.00")
            ok(
                api.upsert_bundle(
                    examleaf_ref=f"product:{bundle.lower()}",
                    idempotency_key=unique(),
                    item_code=bundle,
                    items=[{"item_code": self.book, "qty": 1}, {"item_code": self.solutions, "qty": 1}],
                )
            )
            invoice = make_invoice([line(self.book, 1, "299.00"), line(bundle, 1, "399.00")], shipping_fee="40.00")
            ok(self.pay(invoice.name, "738.00"))
            ok(
                api.create_delivery_note(
                    examleaf_ref=f"shipment:{unique()}",
                    idempotency_key=unique(),
                    invoice_number=invoice.name,
                    posting_date=str(getdate()),
                )
            )
            note = ok(self.credit(invoice, [{"item_code": self.book, "amount": "299.00", "qty": 1}]))
            ok(self.pay(note["name"], "299.00", reference=unique("rfnd_")))
            ok(
                api.record_settlement(
                    examleaf_ref=f"settlement:{unique()}",
                    idempotency_key=unique(),
                    kind="razorpay",
                    settlement_id=unique("setl_"),
                    posting_date=str(getdate()),
                    gross_amount="439.00",
                    fee="10.00",
                    tax_on_fee="1.80",
                    net_amount="427.20",
                )
            )
            ok(
                api.upsert_b2b_customer(
                    examleaf_ref=f"distributor:{unique()}",
                    idempotency_key=unique(),
                    customer_name=unique("Books and Co "),
                    customer_group="Distributor",
                    district="Jorhat",
                )
            )
            ok(api.get_stock(item_code=self.book))
            ok(api.get_changes_since(doctype="Bin", modified_after="2026-01-01 00:00:00"))
            ok(api.daily_totals(date=str(getdate())))
            self.assertTrue(book)
            self.assertEqual(frappe.get_doc("Sales Invoice", invoice.name).owner, user)
            self.assertFalse(frappe.has_permission("Sales Invoice", "cancel"))
            self.assertFalse(frappe.has_permission("Sales Order", "read"))
            self.assertFalse(frappe.has_permission("Stock Entry", "create"))
        with as_user("Guest"), self.assertRaises(frappe.PermissionError):
            api.ping()

    # ---------------------------------------------------------------------------------------------- the Sync Log
    def test_a_failed_call_can_be_resynced(self):
        from examleaf_erp.examleaf_erp.doctype.examleaf_sync_log.examleaf_sync_log import resync, run_resync

        code = unique("LATER-")
        payload = invoice_payload([line(code, 1, "299.00")])
        failed = api.create_sales_invoice(**payload)
        self.assertEqual(failed["error"]["code"], "not_found")
        frappe.db.commit()
        make_item("sample-papers", "0", "4901", item_code=code)
        queued = resync(failed["log"])
        run_resync(queued)
        row = frappe.get_doc("ExamLeaf Sync Log", queued)
        self.assertEqual(
            (row.status, row.retry_of, row.reference_name), ("Success", str(failed["log"]), payload["invoice_number"])
        )
        replay = ok(api.create_sales_invoice(**payload))  # the outbox's own retry, same key: the resync's result
        self.assertTrue(replay["duplicate"])
        self.assertEqual(json.loads(row.request_data)["invoice_number"], payload["invoice_number"])
