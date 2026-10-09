"""Shared helpers for examleaf_erp's tests. They run on a bootstrapped site (before_tests runs the bootstrap) and commit
what they set up: the API rolls back its whole transaction when it refuses a call, as a real request does, so anything
a test made before such a call must already be committed. Every name carries a random suffix: runs never collide."""

import random
import uuid
from contextlib import contextmanager
from decimal import Decimal

import frappe
from frappe.utils import getdate

from examleaf_erp import api
from examleaf_erp.setup import conf


def unique(prefix=""):
    return f"{prefix}{uuid.uuid4().hex[:8]}"


def company():
    return frappe.defaults.get_global_default("company")


def abbr():
    return frappe.get_cached_value("Company", company(), "abbr")


def financial_year(day=None):
    return api.financial_year(getdate(day))


def number(prefix="EL", day=None):
    """A free legal number of this financial year: EL/2026-27/04711."""
    while True:
        candidate = f"{prefix}/{financial_year(day)}/{random.randint(10000, 99999)}"
        if not frappe.db.exists("Sales Invoice", candidate):
            return candidate


def ok(response):
    assert response.get("ok"), response
    return response


def make_item(kind="sample-papers", gst_rate="0", hsn="4901", mrp="299.00", **extra):
    code = extra.pop("item_code", None) or unique("T-")
    ok(
        api.upsert_item(
            examleaf_ref=f"product:{code.lower()}",
            idempotency_key=unique("item-"),
            item_code=code,
            item_name=f"Test book {code}" if kind != "digital" else f"Test course {code}",
            kind=kind,
            hsn_code=hsn,
            gst_rate=gst_rate,
            mrp=mrp,
            **extra,
        )
    )
    return code


def receive(item_code, qty, print_date, warehouse="Main", batch=None):
    """A print run: a Batch with its print date, received into the warehouse by a Stock Entry on that day (so that
    challans dated after it find the stock). Returns the batch."""
    batch = batch or unique("B-")
    frappe.get_doc({"doctype": "Batch", "batch_id": batch, "item": item_code, "manufacturing_date": print_date}).insert(
        ignore_permissions=True
    )
    entry = frappe.get_doc(
        {
            "doctype": "Stock Entry",
            "stock_entry_type": "Material Receipt",
            "company": company(),
            "posting_date": str(print_date),
            "set_posting_time": 1,
            "items": [
                {
                    "item_code": item_code,
                    "qty": qty,
                    "t_warehouse": f"{warehouse} - {abbr()}",
                    "basic_rate": 60,
                    "batch_no": batch,
                    "use_serial_batch_fields": 1,
                }
            ],
        }
    )
    entry.insert(ignore_permissions=True)
    entry.submit()
    return batch


def line(item_code, qty, rate, gst_rate="0", discount="0.00", **extra):
    return {"item_code": item_code, "qty": qty, "rate": rate, "gst_rate": gst_rate, "discount": discount, **extra}


def invoice_payload(
    lines, shipping_fee="0.00", state="AS", pin="781001", city="Guwahati", district="Kamrup Metro", **extra
):
    invoice_number = extra.pop("invoice_number", None) or number("EL")
    total = sum(
        (Decimal(item["rate"]) * item["qty"] - Decimal(item.get("discount") or "0") for item in lines), Decimal("0.00")
    ) + Decimal(shipping_fee)
    payload = {
        "examleaf_ref": f"invoice:{invoice_number}",
        "idempotency_key": unique("outbox-"),
        "invoice_number": invoice_number,
        "posting_date": str(getdate()),
        "order_number": f"EL-{getdate().year}-{random.randint(100000, 999999)}",
        "shipping_address": {"city": city, "district": district, "state": state, "pin": pin},
        "items": lines,
        "shipping_fee": shipping_fee,
        "total": f"{total:.2f}",
    }
    payload.update(extra)
    return payload


def make_invoice(lines, **extra):
    response = ok(api.create_sales_invoice(**invoice_payload(lines, **extra)))
    return frappe.get_doc("Sales Invoice", response["name"])


def sync_user():
    return conf("examleaf_sync_user")


@contextmanager
def as_user(user):
    previous = frappe.session.user
    frappe.set_user(user)
    try:
        yield
    finally:
        frappe.set_user(previous)


def make_customer(group, name=None, **extra):
    customer = frappe.get_doc(
        {
            "doctype": "Customer",
            "customer_name": name or unique(f"Test {group} "),
            "customer_group": group,
            "territory": extra.pop("territory", "Kamrup Metro"),
            "customer_type": "Company",
            **extra,
        }
    )
    customer.insert(ignore_permissions=True)
    return customer.name


def log_rows(**filters):
    return frappe.get_all(
        "ExamLeaf Sync Log", filters=filters, fields=["name", "status", "method"], order_by="creation asc"
    )
