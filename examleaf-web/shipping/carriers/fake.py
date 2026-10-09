"""A double of Shiprocket's API, for test mode (an account with mode "test") and the tests: an httpx MockTransport that
answers every call ShiprocketCarrier makes from the documented examples (recorded/shiprocket.json), with the ids,
AWBs and statuses of what it was asked. Shiprocket has no sandbox (research 0.1), so this is how staging and CI book,
label, track and reconcile without real money.

It keeps what it was asked in memory, per process, and stays consistent across processes where it can (staging's web
and worker): ids come from our order ids, and a tracking read of an AWB it never saw answers "AWB assigned". The
tests script it: move(awb, *codes) adds scans, fail(path, status) makes the next calls fail, webhook(awb) is the body
Shiprocket would post, revoke_token() makes the next call a 401."""

import copy
import json
import re
import zlib
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs

import httpx
from django.utils import timezone

RECORDED = json.loads((Path(__file__).parent / "recorded" / "shiprocket.json").read_text())
LABELS = {
    **{1: "AWB ASSIGNED", 2: "LABEL GENERATED", 3: "PICKUP SCHEDULED", 4: "PICKUP QUEUED", 5: "MANIFEST GENERATED"},
    **{6: "SHIPPED", 7: "DELIVERED", 8: "CANCELLED", 9: "RTO INITIATED", 10: "RTO DELIVERED", 11: "PENDING"},
    **{12: "LOST", 13: "PICKUP ERROR", 14: "RTO ACKNOWLEDGED", 15: "PICKUP RESCHEDULED", 16: "CANCELLATION REQUESTED"},
    **{17: "OUT FOR DELIVERY", 18: "IN TRANSIT", 19: "OUT FOR PICKUP", 20: "PICKUP EXCEPTION", 21: "UNDELIVERED"},
    **{22: "DELAYED", 23: "PARTIAL DELIVERED", 24: "DESTROYED", 25: "DAMAGED", 26: "FULFILLED", 27: "PICKUP BOOKED"},
    **{38: "REACHED AT DESTINATION HUB", 39: "MISROUTED", 40: "RTO NDR", 41: "RTO OFD", 42: "PICKED UP"},
    **{43: "SELF FULFILLED", 44: "DISPOSED OFF", 45: "CANCELLED BEFORE DISPATCHED", 46: "RTO IN TRANSIT"},
    **{47: "QC FAILED", 48: "REACHED WAREHOUSE", 51: "HANDOVER TO COURIER", 52: "SHIPMENT BOOKED", 75: "RTO LOCK"},
    **{76: "UNTRACEABLE", 77: "ISSUE RELATED TO THE RECIPIENT", 78: "REACHED BACK AT SELLER CITY"},
}
FILES = "https://fake-shiprocket.test"
PREFIX = "/v1/external"


def recorded(name):
    return copy.deepcopy(RECORDED[name])


def answer(status, body):
    return httpx.Response(status, json=body)


class FakeShiprocket:
    def __init__(self):
        self.reset()

    def reset(self):
        self.orders = {}  # our order id: what Shiprocket would know of it
        self.scans = {}  # AWB: [scan], oldest first
        self.failures = []  # [method or None, path prefix, status, body, times left]
        self.calls = []  # (method, path) of every request
        self.statement = []
        self.discrepancies = []
        self.remittances = {}  # Shiprocket order id: remittance fields of orders/show
        self.unserviceable = set()  # PINs no courier serves
        self.token = RECORDED["login"]["token"]
        self.logins = 0

    def transport(self):
        return httpx.MockTransport(self.handle)

    # Scripting

    def fail(self, path, status=503, body=None, times=1, method=None):
        self.failures.append([method, PREFIX + path if path.startswith("/") else path, status, body, times])

    def revoke_token(self):
        self.token = f"{RECORDED['login']['token']}-revoked-{self.logins}"

    def move(self, awb, *codes, at=None):
        """Scans with these shipment status codes, a minute apart (from `at`, or just after the last one)."""
        scans = self.scans.setdefault(awb, [])
        when = at or (scans[-1]["at"] + timedelta(minutes=1) if scans else timezone.now() - timedelta(hours=1))
        for code in codes:
            label = LABELS.get(code, "NA")
            scans.append(
                {
                    "at": when,
                    "date": timezone.localtime(when).strftime("%Y-%m-%d %H:%M:%S"),
                    "status": f"X-{code}",
                    "activity": label.title(),
                    "location": "GUWAHATI_HUB (Assam)",
                    "sr-status": str(code),
                    "sr-status-label": label,
                }
            )
            when += timedelta(minutes=1)

    def public_scans(self, awb):
        return [{key: value for key, value in scan.items() if key != "at"} for scan in self.scans.get(awb, [])]

    def webhook(self, awb):
        """The body Shiprocket posts for this AWB now: its scans so far and the last one's status."""
        body = recorded("webhook")
        scans = self.public_scans(awb)
        last = scans[-1] if scans else {"sr-status": "1", "sr-status-label": LABELS[1]}
        order = next((o for o in self.orders.values() if o["awb"] == awb), {})
        body.update(
            awb=awb,
            courier_name=order.get("courier_name", body["courier_name"]),
            current_status=last["sr-status-label"],
            shipment_status=last["sr-status-label"],
            shipment_status_id=int(last["sr-status"]),
            current_timestamp=timezone.localtime(self.scans[awb][-1]["at"] if scans else timezone.now()).strftime(
                "%d %m %Y %H:%M:%S"
            ),
            order_id=order.get("reference", body["order_id"]),
            sr_order_id=order.get("order_id", body["sr_order_id"]),
            scans=scans,
        )
        return body

    def charge(self, order, description, debit="0.00", credit="0.00"):
        row = recorded("statement_row")
        row.update(
            order_id=order["order_id"],
            channel_order_id=order["reference"],
            awb_code=order["awb"] or "",
            description=description,
            charge=debit if debit != "0.00" else credit,
            debit_amount=debit,
            credit_amount=credit,
            balance_amount=f"{Decimal('1250.00') - Decimal(len(self.statement)):.2f}",
            created_at=timezone.localtime().strftime("%Y-%m-%d %H:%M:%S"),
        )
        self.statement.append(row)

    # The API

    ROUTES = [
        ("POST", r"/auth/login", "login"),
        ("GET", r"/courier/serviceability/", "serviceability"),
        ("POST", r"/orders/create/adhoc", "create_order"),
        ("GET", r"/orders", "search_orders"),
        ("POST", r"/courier/assign/awb", "assign_awb"),
        ("POST", r"/courier/generate/label", "generate_label"),
        ("POST", r"/courier/generate/pickup", "generate_pickup"),
        ("POST", r"/manifests/(generate|print)", "manifest"),
        ("POST", r"/orders/cancel/shipment/awbs", "cancel_awbs"),
        ("POST", r"/orders/cancel", "cancel_orders"),
        ("GET", r"/courier/track/awb/(?P<awb>[^/]+)", "track_awb"),
        ("POST", r"/courier/track/awbs", "track_awbs"),
        ("POST", r"/ndr/(?P<awb>[^/]+)/action", "ndr_action"),
        ("GET", r"/account/details/wallet-balance", "wallet_balance"),
        ("GET", r"/account/details/statement", "statement_rows"),
        ("GET", r"/billing/discrepancy", "discrepancy"),
        ("GET", r"/orders/show/(?P<order_id>\d+)", "order_show"),
        ("GET", r"/settings/company/pickup", "pickup_locations"),
    ]

    def handle(self, request):
        path, method = request.url.path, request.method
        self.calls.append((method, path))
        for failure in self.failures:
            wanted, prefix, status, body, times = failure
            if (
                times
                and (wanted in (None, method))
                and (path.startswith(prefix) or str(request.url).startswith(prefix))
            ):
                failure[4] -= 1
                return answer(status, body or {"message": "Service Unavailable"})
        if request.url.host == "fake-shiprocket.test":
            return httpx.Response(
                200, content=b"%PDF-1.4 fake document " + path.encode(), headers={"Content-Type": "application/pdf"}
            )
        if not path.startswith(PREFIX):
            return answer(404, {"message": "Not found"})
        route = path.removeprefix(PREFIX)
        for verb, pattern, name in self.ROUTES:
            if verb == method and (match := re.fullmatch(pattern, route)):
                if name != "login" and request.headers.get("Authorization") != f"Bearer {self.token}":
                    return answer(401, {"message": "Unauthenticated.", "status_code": 401})
                body = json.loads(request.content) if request.content else {}
                query = {key: values[0] for key, values in parse_qs(request.url.query.decode()).items()}
                return getattr(self, name)(body=body, query=query, **match.groupdict())
        return answer(404, {"message": "Not found"})

    def login(self, body, query):
        if not body.get("email") or not body.get("password"):
            return answer(400, {"message": "Invalid email and password combination", "status_code": 400})
        self.logins += 1
        self.token = f"{RECORDED['login']['token']}-{self.logins}"
        return answer(200, {**recorded("login"), "token": self.token, "email": body["email"]})

    def serviceability(self, body, query):
        if query.get("delivery_postcode") in self.unserviceable:
            return answer(200, recorded("not_serviceable"))
        return answer(200, recorded("serviceability"))

    def create_order(self, body, query):
        reference = body.get("order_id", "")
        if reference in self.orders:
            return answer(422, recorded("order_exists"))
        missing = [
            name
            for name in ["order_id", "pickup_location", "billing_pincode", "billing_phone", "sub_total", "order_items"]
            if body.get(name) in (None, "", [])
        ]
        if missing:
            return answer(422, {"message": "Oops! Invalid Data.", "errors": {name: ["required"] for name in missing}})
        if body["pickup_location"] != "Primary":
            return answer(422, {"message": "Wrong Pickup location entered.", "status_code": 422})
        order_id = 100_000_000 + zlib.crc32(reference.encode()) % 800_000_000
        self.orders[reference] = {
            "reference": reference,
            "order_id": order_id,
            "shipment_id": order_id + 1,
            "awb": None,
            "courier_id": None,
            "courier_name": "",
            "cancelled": False,
            "payload": body,
        }
        return answer(200, {**recorded("create_order"), "order_id": order_id, "shipment_id": order_id + 1})

    def by_shipment(self, shipment_id):
        return next((o for o in self.orders.values() if o["shipment_id"] == int(shipment_id)), None)

    def search_orders(self, body, query):
        found = [o for o in self.orders.values() if o["reference"] == query.get("search")]
        rows = [
            {
                "id": o["order_id"],
                "channel_order_id": o["reference"],
                "shipments": [{"id": o["shipment_id"], "awb": o["awb"] or ""}],
            }
            for o in found
        ]
        return answer(200, {"data": rows, "meta": {"pagination": {"total_pages": 1}}})

    def assign_awb(self, body, query):
        order = self.by_shipment(body.get("shipment_id", 0))
        couriers = {
            c["courier_company_id"]: c for c in RECORDED["serviceability"]["data"]["available_courier_companies"]
        }
        courier = couriers.get(body.get("courier_id"))
        if order is None or courier is None or order["cancelled"]:
            return answer(200, recorded("assign_awb_refused"))
        if order["awb"]:
            return answer(
                200, {"awb_assign_status": 0, "response": {"data": {"awb_assign_error": "AWB is already assigned"}}}
            )
        order.update(
            awb=f"1411{order['shipment_id']:010d}",
            courier_id=courier["courier_company_id"],
            courier_name=courier["courier_name"],
        )
        self.charge(order, "Freight Charge", debit=f"{courier['freight_charge']:.2f}")
        if order["payload"].get("payment_method") == "COD":
            self.charge(order, "COD Charge", debit=f"{courier['cod_charges']:.2f}")
        result = recorded("assign_awb")
        result["response"]["data"].update(
            awb_code=order["awb"],
            courier_company_id=courier["courier_company_id"],
            courier_name=courier["courier_name"],
            order_id=order["order_id"],
            shipment_id=order["shipment_id"],
        )
        return answer(200, result)

    def generate_label(self, body, query):
        [shipment_id] = body.get("shipment_id") or [0]
        if self.by_shipment(shipment_id) is None:
            return answer(200, {"label_created": 0, "response": "Shipment not found", "not_created": [shipment_id]})
        return answer(200, {**recorded("generate_label"), "label_url": f"{FILES}/labels/{shipment_id}.pdf"})

    def generate_pickup(self, body, query):
        [shipment_id] = body.get("shipment_id") or [0]
        order = self.by_shipment(shipment_id)
        if order is None or not order["awb"]:
            return answer(400, {"message": "Please assign AWB first", "status_code": 400})
        result = recorded("generate_pickup")
        day = (body.get("pickup_date") or [(timezone.localdate() + timedelta(days=1)).isoformat()])[0]
        result["response"]["pickup_scheduled_date"] = f"{day} 10:00:00"
        self.move(order["awb"], 3)
        return answer(200, result)

    def manifest(self, body, query):
        return answer(200, recorded("generate_manifest"))

    def cancel_awbs(self, body, query):
        for order in self.orders.values():
            if order["awb"] in body.get("awbs", []) and not order["cancelled"]:
                order["cancelled"] = True
                self.move(order["awb"], 8)
                for row in [r for r in self.statement if r["awb_code"] == order["awb"] and r["debit_amount"] != "0.00"]:
                    self.charge(order, f"{row['description']} Reversed", credit=row["debit_amount"])
        return answer(200, recorded("cancel_awbs"))

    def cancel_orders(self, body, query):
        for order in self.orders.values():
            if order["order_id"] in body.get("ids", []):
                order["cancelled"] = True
        return httpx.Response(204)

    def tracking(self, awb):
        result = recorded("track")
        scans = list(reversed(self.public_scans(awb)))  # Shiprocket lists the newest first
        data = result["tracking_data"]
        data["shipment_track_activities"] = scans
        data["shipment_status"] = int(scans[0]["sr-status"]) if scans and scans[0]["sr-status"].isdigit() else 1
        data["track_status"] = 1 if scans else 0
        data["shipment_track"][0].update(
            awb_code=awb, current_status=scans[0]["sr-status-label"].title() if scans else "AWB Assigned"
        )
        return result

    def track_awb(self, body, query, awb):
        return answer(200, self.tracking(awb))

    def track_awbs(self, body, query):
        return answer(200, {awb: self.tracking(awb) for awb in body.get("awbs", [])})

    def ndr_action(self, body, query, awb):
        if body.get("action") not in ("re-attempt", "return", "fake-attempt") or not body.get("comments"):
            return answer(422, {"message": "action and comments are required", "status_code": 422})
        return answer(202, recorded("ndr_action"))

    def wallet_balance(self, body, query):
        return answer(200, recorded("wallet_balance"))

    def statement_rows(self, body, query):
        return answer(200, {"data": self.statement, "meta": {"pagination": {"total_pages": 1, "current_page": 1}}})

    def discrepancy(self, body, query):
        return answer(200, {"data": self.discrepancies})

    def order_show(self, body, query, order_id):
        order = next((o for o in self.orders.values() if o["order_id"] == int(order_id)), None)
        if order is None:
            return answer(404, {"message": "Order not found", "status_code": 404})
        result = recorded("order_show")
        result["data"].update(
            id=order["order_id"], channel_order_id=order["reference"], **self.remittances.get(order["order_id"], {})
        )
        result["data"].pop("_inferred_remittance_amount", None)
        return answer(200, result)

    def pickup_locations(self, body, query):
        return answer(200, recorded("pickup_locations"))


FAKE = FakeShiprocket()  # test mode's, one per process
