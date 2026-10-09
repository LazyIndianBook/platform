"""Each print format renders, as HTML and as a PDF through v16's Chrome renderer, with what its rule requires."""

from decimal import Decimal

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import getdate

from examleaf_erp import api
from examleaf_erp.tests.utils import (
    abbr,
    company,
    line,
    make_customer,
    make_invoice,
    make_item,
    number,
    ok,
    receive,
    unique,
)


class TestPrintFormats(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.book = make_item()
        cls.course = make_item("digital", "18", "999293", mrp="999.00")
        receive(cls.book, 10, "2026-04-01")
        cls.exempt = make_invoice([line(cls.book, 2, "299.00")], shipping_fee="40.00")
        cls.mixed = make_invoice(
            [line(cls.book, 1, "299.00"), line(cls.course, 1, "999.00", gst_rate="18", hsn_code="999293")]
        )
        note_number = number("CN")
        cls.note = ok(
            api.create_credit_note(
                examleaf_ref=f"credit-note:{note_number}",
                idempotency_key=unique(),
                credit_note_number=note_number,
                invoice_number=cls.mixed.name,
                posting_date=str(getdate()),
                reason="Course not wanted",
                items=[{"item_code": cls.course, "amount": "999.00", "qty": 1}],
                total="999.00",
            )
        )["name"]
        cls.delivery = ok(
            api.create_delivery_note(
                examleaf_ref=f"shipment:{unique()}",
                idempotency_key=unique(),
                invoice_number=cls.exempt.name,
                posting_date=str(getdate()),
                courier="Delhivery",
                tracking_number="1234567890",
            )
        )["name"]
        cls.school = make_customer("School")
        quotation = frappe.get_doc(
            {
                "doctype": "Quotation",
                "quotation_to": "Customer",
                "party_name": cls.school,
                "company": company(),
                "transaction_date": str(getdate()),
                "items": [{"item_code": cls.book, "qty": 40, "rate": 269.10, "price_list_rate": 299.00}],
            }
        )
        quotation.insert(ignore_permissions=True)
        cls.quotation = quotation.name
        frappe.db.commit()

    def render(self, doctype, name, print_format):
        html = frappe.get_print(doctype, name, print_format)
        pdf = frappe.get_print(doctype, name, print_format, as_pdf=True, pdf_generator="chrome")
        self.assertTrue(pdf.startswith(b"%PDF"), print_format)
        return html

    def test_a_bill_of_supply(self):
        html = self.render("Sales Invoice", self.exempt.name, "ExamLeaf Invoice")
        for text in (
            "Bill of supply",
            self.exempt.name,
            "4901",
            "Rule 49",
            "18AAAAA0000A1Z1",
            "Value of exempt supplies",
        ):
            self.assertIn(text, html)
        self.assertNotIn("CGST", html.split("Summary by HSN")[0])  # no tax columns on a bill of supply

    def test_an_invoice_cum_bill_of_supply(self):
        html = self.render("Sales Invoice", self.mixed.name, "ExamLeaf Invoice")
        # 999.00 with 18 % in it is 846.61 + 76.19 + 76.19 = 998.99: the paisa left shows as a round off
        for text in (
            "Invoice-cum-bill of supply",
            "Exempt",
            "999293",
            "CGST",
            "SGST",
            "18-Assam",
            "Rule 46A",
            "Round off",
        ):
            self.assertIn(text, html)

    def test_a_credit_note(self):
        html = self.render("Sales Invoice", self.note, "ExamLeaf Credit Note")
        for text in ("Credit note", self.note, f"Against {self.mixed.name}", "Course not wanted", "Total credited"):
            self.assertIn(text, html)
        self.assertIn("Credit note", frappe.get_print("Sales Invoice", self.note, "ExamLeaf Invoice"))

    def test_a_delivery_challan_in_triplicate(self):
        html = self.render("Delivery Note", self.delivery, "ExamLeaf Delivery Challan")
        for text in (
            "Original for consignee",
            "Duplicate for transporter",
            "Triplicate for consigner",
            "Delhivery",
            "Print runs",
            self.exempt.name,
        ):
            self.assertIn(text, html)

    def test_a_quotation(self):
        html = self.render("Quotation", self.quotation, "ExamLeaf Quotation")
        self.assertIn("Quotation", html)
        self.assertIn("not a tax invoice", html)

    def test_a_statement_of_account(self):
        invoice = frappe.get_doc(
            {
                "doctype": "Sales Invoice",
                "customer": self.school,
                "company": company(),
                "posting_date": str(getdate()),
                "set_posting_time": 1,
                "items": [{"item_code": self.book, "qty": 10, "rate": 269.10}],
            }
        )
        invoice.insert(ignore_permissions=True)
        invoice.submit()
        html = self.render("Customer", self.school, "ExamLeaf Statement of Account")
        for text in ("Statement of account", invoice.name, "0-30 days", "90+ days", "Closing balance"):
            self.assertIn(text, html)
        statement = frappe.get_attr("examleaf_erp.printing.statement_of_account")(self.school)
        self.assertEqual(Decimal(str(statement["closing"])).quantize(Decimal("0.01")), Decimal("2691.00"))
        self.assertEqual(abbr(), "EL")
