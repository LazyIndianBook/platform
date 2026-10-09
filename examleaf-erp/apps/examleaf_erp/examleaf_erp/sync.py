"""The plumbing every examleaf_erp.api method shares: who may call, strict input checks, idempotency, the Sync Log, and
one error shape. The contract is API.md; the platform's outbox (research 5.8) is the only intended caller."""

import hashlib
import json
import re
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

import frappe
from frappe import _
from frappe.utils import getdate, strip_html

from examleaf_erp.constants import SYNC_ROLE

LOG = "ExamLeaf Sync Log"
CALLER_ROLES = (SYNC_ROLE, "System Manager")
IGNORED_KEYS = {"cmd"}  # frappe adds the method's name to the form

KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:_./-]{0,139}$")
REF = re.compile(r"^[a-z][a-z0-9-]{1,30}:[A-Za-z0-9][A-Za-z0-9/_.:-]{0,100}$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d{1,6})?$")
PAISA = Decimal("0.01")


class ApiError(Exception):
    """A refusal the caller can act on. http_status: 400 the request is wrong, 404 a document it names is missing, 409
    it conflicts with what ERPNext holds, 422 ERPNext refused the document."""

    def __init__(self, code, message, http_status=400, field=None):
        super().__init__(message)
        self.code, self.message, self.http_status, self.field = code, message, http_status, field


def bad(field, message):
    return ApiError("invalid_request", message, 400, field)


# ---------------------------------------------------------------------------------------------------- input checks
class Fields:
    """Reads one request's fields, each check raising invalid_request with the field's dotted name. Unknown fields are
    refused too, so a typo in the platform's payload fails loudly instead of being ignored."""

    def __init__(self, data: dict, path: str = ""):
        if not isinstance(data, dict):
            raise bad(path or "body", "Send an object.")
        self.data, self.path, self.seen = data, path, set()

    def _name(self, key):
        return f"{self.path}.{key}" if self.path else key

    def _get(self, key, required):
        self.seen.add(key)
        value = self.data.get(key)
        if value is None or value == "":
            if required:
                raise bad(self._name(key), "This field is required.")
            return None
        return value

    def str(self, key, required=True, max_length=140, pattern=None, choices=None, default=None):
        value = self._get(key, required)
        if value is None:
            return default
        if not isinstance(value, str):
            raise bad(self._name(key), "Send a string.")
        value = value.strip()
        if len(value) > max_length:
            raise bad(self._name(key), f"At most {max_length} characters.")
        if pattern and not pattern.match(value):
            raise bad(self._name(key), "This value is not in the expected format.")
        if choices and value not in choices:
            raise bad(self._name(key), f"One of: {', '.join(choices)}.")
        return value

    def int(self, key, required=True, minimum=None, maximum=None, default=None):
        value = self._get(key, required)
        if value is None:
            return default
        if isinstance(value, bool) or not isinstance(value, int):
            raise bad(self._name(key), "Send a whole number.")
        if (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
            raise bad(self._name(key), f"From {minimum} to {maximum}.")
        return value

    def money(self, key, required=True, minimum=Decimal("0"), allow_zero=True, default=None):
        """Rupees as a JSON string ("299.00") or number, at most 2 decimals: Decimal, never float."""
        value = self._get(key, required)
        if value is None:
            return default
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            raise bad(self._name(key), 'Send an amount in rupees, like "299.00".')
        try:
            amount = Decimal(str(value))
        except InvalidOperation:
            raise bad(self._name(key), 'Send an amount in rupees, like "299.00".')
        if not amount.is_finite() or amount != amount.quantize(PAISA):
            raise bad(self._name(key), "At most 2 decimals (paise).")
        if amount < minimum or (not allow_zero and amount == 0):
            raise bad(self._name(key), "This amount is too small." if amount >= 0 else "Amounts are positive.")
        if amount >= Decimal("100000000"):
            raise bad(self._name(key), "This amount is too large.")
        return amount.quantize(PAISA)

    def rate(self, key, required=True):
        """A GST rate in percent: 0, 5, 18, … (at most 2 decimals)."""
        value = self.money(key, required)
        if value is not None and value > 100:
            raise bad(self._name(key), "A rate in percent, from 0 to 100.")
        return value

    def date(self, key, required=True, not_after_today=True):
        value = self.str(key, required, max_length=10, pattern=DATE)
        if value is None:
            return None
        try:
            day = datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            raise bad(self._name(key), "Not a date (YYYY-MM-DD).")
        if not_after_today and day > getdate():
            raise bad(self._name(key), "This date is in the future.")
        return day

    def bool(self, key, required=False, default=None):
        value = self._get(key, required)
        if value is None:
            return default
        if not isinstance(value, bool):
            raise bad(self._name(key), "Send true or false.")
        return value

    def obj(self, key, required=True):
        value = self._get(key, required)
        return None if value is None else Fields(value, self._name(key))

    def list(self, key, required=True, min_items=1, max_items=100):
        value = self._get(key, required)
        if value is None:
            return []
        if not isinstance(value, list):
            raise bad(self._name(key), "Send a list.")
        if not (min_items <= len(value) <= max_items):
            raise bad(self._name(key), f"From {min_items} to {max_items} entries.")
        return [Fields(entry, f"{self._name(key)}[{i}]") for i, entry in enumerate(value)]

    def done(self):
        """Refuse what was sent but not read."""
        if extra := sorted(set(self.data) - self.seen - IGNORED_KEYS):
            raise bad(self._name(extra[0]), "Unknown field.")


def ref_and_key(fields: Fields, ref_required=True):
    return (
        fields.str("examleaf_ref", required=ref_required, pattern=REF),
        fields.str("idempotency_key", pattern=KEY),
    )


# ---------------------------------------------------------------------------------------------------- the wrapper
def canonical(data: dict) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)


def request_hash(data: dict) -> str:
    body = {k: v for k, v in data.items() if k not in IGNORED_KEYS | {"idempotency_key"}}
    return hashlib.sha256(canonical(body).encode()).hexdigest()


def endpoint(mutating: bool):
    """Wrap an api method. The method takes the request's fields as a dict and returns
    (response dict, reference doctype or None); it raises ApiError (or frappe's own exceptions) to refuse.

    - mutating: needs an idempotency_key; a key seen before answers its first success again (duplicate: true) and a
      second Duplicate row is logged, a key reused with another payload is a 409;
    - every call ends in one Sync Log row (Success, Duplicate or Error), committed with the document it made;
    - on any error the transaction is rolled back, so no half-made document stays, and the Error row is written after."""

    def wrap(fn):
        def wrapper(**data):
            frappe.only_for(CALLER_ROLES)
            method = fn.__name__
            data = {k: v for k, v in data.items() if k not in IGNORED_KEYS}
            key = data.get("idempotency_key") if isinstance(data.get("idempotency_key"), str) else None
            ref = data.get("examleaf_ref") if isinstance(data.get("examleaf_ref"), str) else None
            digest = request_hash(data)
            try:
                if mutating and key and (first := _first_success(key)):
                    if first.request_hash != digest:
                        raise ApiError(
                            "idempotency_key_reused",
                            "This idempotency_key was used before with a different request.",
                            409,
                            "idempotency_key",
                        )
                    response = {**json.loads(first.response_data), "duplicate": True}
                    _log(method, "Duplicate", data, digest, response, duplicate_of=first.name)
                    return _finish(response)
                response, reference_doctype = _run_once(fn, data)
                response = {"ok": True, "duplicate": False, **response}
                response.setdefault("examleaf_ref", ref)
                status = "Duplicate" if response["duplicate"] else "Success"
                response["log"] = _log(method, status, data, digest, response, reference_doctype)
                return _finish(response)
            except Exception as error:
                return _fail(method, data, digest, ref, error)

        # not functools.wraps: its __wrapped__ would make frappe.call read fn's (data) signature and drop every field
        for attribute in ("__module__", "__name__", "__qualname__", "__doc__"):
            setattr(wrapper, attribute, getattr(fn, attribute))
        return wrapper

    return wrap


def _run_once(fn, data):
    """Run the method; when two calls race for one document, the loser hits the unique index (name or examleaf_ref):
    roll back and run again, which now finds the winner's document and answers duplicate."""
    try:
        return fn(dict(data))
    except frappe.DuplicateEntryError, frappe.UniqueValidationError:
        frappe.db.rollback()
        frappe.clear_messages()
        return fn(dict(data))


def _first_success(key):
    rows = frappe.get_all(
        LOG,
        filters={"idempotency_key": key, "status": "Success"},
        fields=["name", "request_hash", "response_data"],
        order_by="creation asc",
        limit=1,
    )
    return rows[0] if rows else None


def _finish(response):
    warnings = [strip_html(m) for m in _messages()]
    frappe.clear_messages()
    if warnings:
        response["warnings"] = warnings
    return response


def _messages():
    out = []
    for raw in frappe.local.message_log or []:
        try:
            message = json.loads(raw) if isinstance(raw, str) else raw
            out.append(message.get("message", "") if isinstance(message, dict) else str(message))
        except ValueError:
            out.append(str(raw))
    return [m for m in out if m]


def _fail(method, data, digest, ref, error):
    frappe.db.rollback()
    erp_messages = [strip_html(m) for m in _messages()]
    frappe.clear_messages()
    if isinstance(error, ApiError):
        code, message, status, field = error.code, error.message, error.http_status, error.field
    elif isinstance(error, frappe.PermissionError):
        code, message, status, field = "permission_denied", strip_html(str(error)) or "Not permitted.", 403, None
    elif isinstance(error, frappe.DoesNotExistError):
        code, message, status, field = "not_found", strip_html(str(error)) or "Not found.", 404, None
    elif isinstance(error, frappe.ValidationError):
        message = strip_html(str(error)) or (erp_messages[-1] if erp_messages else "ERPNext refused the document.")
        code, status, field = "erp_validation_error", 422, None
    else:
        code, message, status, field = "internal_error", "Something failed in ERPNext: see the Sync Log.", 500, None
    response = {
        "ok": False,
        "duplicate": False,
        "examleaf_ref": ref,
        "name": None,
        "error": {"code": code, "message": message, "field": field},
    }
    response["log"] = _log(method, "Error", data, digest, response, traceback=frappe.get_traceback())
    frappe.local.response.http_status_code = status
    return response


def _log(method, status, data, digest, response, reference_doctype=None, duplicate_of=None, traceback=None):
    """One Sync Log row per call. A Resync (examleaf_sync_log.resync) runs the call again in a job and fills the Queued
    row it made instead of adding one."""
    values = {
        "direction": "Inbound",
        "method": method,
        "status": status,
        "examleaf_ref": data.get("examleaf_ref") if isinstance(data.get("examleaf_ref"), str) else None,
        "idempotency_key": data.get("idempotency_key") if isinstance(data.get("idempotency_key"), str) else None,
        "request_hash": digest,
        "request_data": canonical(data),
        "response_data": canonical(response),
        "traceback": traceback,
        "reference_doctype": reference_doctype if response.get("name") else None,
        "reference_name": response.get("name") if reference_doctype else None,
        "duplicate_of": duplicate_of,
        "user": frappe.session.user,
    }
    if queued := frappe.flags.examleaf_resync_log:
        log = frappe.get_doc(LOG, queued)
        log.update(values)
        log.save(ignore_permissions=True)
    else:
        log = frappe.get_doc({"doctype": LOG, **values})
        log.insert(ignore_permissions=True)
    return log.name


# ---------------------------------------------------------------------------------------------------- small helpers
def to_decimal(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(PAISA, rounding=ROUND_HALF_UP)


def money_str(value) -> str:
    return f"{to_decimal(value):.2f}"


def iso(value) -> str | None:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S.%f")
    if isinstance(value, date):
        return value.isoformat()
    return value


def company() -> str:
    name = frappe.defaults.get_global_default("company")
    if not name:
        raise ApiError("not_configured", "ERPNext has no default company yet: run examleaf_erp.setup.bootstrap.", 500)
    return name


def message_of(error) -> str:
    return strip_html(str(error)) or _("ERPNext refused the document.")
