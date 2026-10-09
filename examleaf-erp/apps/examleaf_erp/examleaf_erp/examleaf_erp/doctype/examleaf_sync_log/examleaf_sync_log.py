import json

import frappe
from frappe import _
from frappe.model.document import Document

RESYNC_ROLES = ("EL Admin", "EL Finance", "System Manager")


class ExamLeafSyncLog(Document):
    pass


@frappe.whitelist(methods=["POST"])
def resync(name: str | int):
    """Run a failed call again with its original request, as the API user who made it, in a background job. A new row
    (Queued, retry_of the failed one) records who asked and, once the job ran, the outcome. The idempotency_key is the
    original's, so the platform's own retry of it, later, answers the result instead of making a second document."""
    frappe.only_for(RESYNC_ROLES)
    log = frappe.get_doc("ExamLeaf Sync Log", name)
    log.check_permission("read")
    from examleaf_erp import api

    if log.status != "Error" or log.direction != "Inbound" or not callable(getattr(api, log.method or "", None)):
        frappe.throw(_("Only a failed call of the sync API can be run again."), title=_("Cannot resync"))
    queued = frappe.get_doc(
        {
            "doctype": "ExamLeaf Sync Log",
            "direction": "Inbound",
            "method": log.method,
            "status": "Queued",
            "examleaf_ref": log.examleaf_ref,
            "idempotency_key": log.idempotency_key,
            "request_hash": log.request_hash,
            "request_data": log.request_data,
            "user": log.user,
            "retry_of": log.name,
            "requested_by": frappe.session.user,
        }
    ).insert(ignore_permissions=True)
    frappe.enqueue(
        "examleaf_erp.examleaf_erp.doctype.examleaf_sync_log.examleaf_sync_log.run_resync",
        queue="short",
        log_name=queued.name,
        enqueue_after_commit=True,
    )
    return queued.name


def run_resync(log_name):
    from examleaf_erp import api

    log = frappe.get_doc("ExamLeaf Sync Log", log_name)
    caller = frappe.session.user
    frappe.set_user(log.user or "Administrator")
    frappe.flags.examleaf_resync_log = log.name
    try:
        getattr(api, log.method)(**json.loads(log.request_data))
    finally:
        frappe.flags.examleaf_resync_log = None
        frappe.set_user(caller)
