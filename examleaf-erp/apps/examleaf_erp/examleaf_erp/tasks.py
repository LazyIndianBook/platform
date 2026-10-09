"""scheduler_events (hooks.py)."""

import frappe
from frappe.utils import add_days, getdate, now_datetime

from examleaf_erp.sync import LOG, canonical

SYNC_LOG_DAYS = 90


def flag_sor_dispatches(day=None):
    """Daily: sale-or-return dispatches reaching five months turn Due Soon, past six Overdue (CGST s.31(7)). The status
    change fires the Notification "EL SOR Dispatch due" to EL Sales and EL Finance."""
    for name in frappe.get_all("SOR Dispatch", filters={"status": ["in", ["Open", "Due Soon"]]}, pluck="name"):
        doc = frappe.get_doc("SOR Dispatch", name)
        if doc.status_on(day) != doc.status:
            doc.flags.status_date = day
            doc.flags.ignore_permissions = True
            doc.save()


def purge_sync_log(days=SYNC_LOG_DAYS):
    """Daily: successful and duplicate calls go after 90 days (as Frappe's own ecommerce integrations do). Errors stay
    until someone has looked at them; daily snapshots (direction Internal) stay."""
    frappe.db.delete(
        LOG,
        {
            "direction": "Inbound",
            "status": ["in", ["Success", "Duplicate"]],
            "creation": ["<", add_days(now_datetime(), -days)],
        },
    )


def snapshot_daily_totals(day=None):
    """02:00: what ERPNext held of yesterday's platform documents, kept as a Sync Log row, so a later back-dated change
    shows against the night's reconciliation (research 5.8)."""
    from examleaf_erp.api import totals_for

    day = getdate(day) if day else add_days(getdate(), -1)
    frappe.get_doc(
        {
            "doctype": LOG,
            "direction": "Internal",
            "method": "daily_totals",
            "status": "Success",
            "examleaf_ref": f"daily:{day}",
            "request_data": canonical({"date": str(day)}),
            "response_data": canonical(totals_for(day)),
            "user": frappe.session.user,
        }
    ).insert(ignore_permissions=True)
