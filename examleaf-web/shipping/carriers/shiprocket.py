"""Shiprocket, API v1 (https://apiv2.shiprocket.in/v1/external; research-integrations.md section 1 and its Postman
collection). Authentication is a password grant: a dedicated API user's email and password (the account's
credentials) give a token valid for 10 days, cached encrypted on the account, renewed from day 9 by one worker at a
time (a cache lock) and once after a 401. Our `order_id` is the order number ("-R1" for a re-shipment), which
Shiprocket never takes twice; its own order and shipment ids come back, the AWB once a courier is assigned. Some
refusals come with HTTP 200 (`awb_assign_status: 0`, `label_created: 0`, `status_code: 422` in the body): they are
refusals here too. There is no sandbox: test mode answers from recorded examples (fake.py), live mode is real money.
Times come as India time without an offset, in two formats."""

import logging
import time
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from django.core.cache import cache
from django.utils import timezone

from integrations.client import Client, IntegrationAuthFailed, IntegrationRejected, describe
from integrations.models import IntegrationAccount
from shop.models import STATES

from ..status import from_shiprocket
from .base import Booking, Carrier, Quote, Scan, WebhookPayload

logger = logging.getLogger(__name__)
BASE_URL = "https://apiv2.shiprocket.in/v1/external"
TOKEN_LIFE = timedelta(days=10)  # "The validity of this token is 10 days"
RENEW_BEFORE = timedelta(days=1)  # renewed from day 9
IST = ZoneInfo("Asia/Kolkata")
MAX_LABEL_BYTES = 5 * 1024 * 1024
TRACK_BATCH = 50  # AWBs per tracking call
REFUSED_IN_200 = {  # a flag that is 0 when the call did not do what it says, and where the reason is
    "awb_assign_status": ("response", "data", "awb_assign_error"),
    "label_created": ("response",),
    "pickup_status": ("response", "data"),
}


def parse_time(value):
    """Shiprocket's two time formats ("2026-10-09 11:59:16" in scans, "09 10 2026 11:43:52" in a webhook's
    current_timestamp), India time, as an aware datetime; None if it is neither."""
    for pattern in ("%Y-%m-%d %H:%M:%S", "%d %m %Y %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(value).strip(), pattern).replace(tzinfo=IST)
        except TypeError, ValueError:
            continue
    return None


def flag(value):
    return value in (1, "1", True, "true", "True")


def decimal(value):
    try:
        return Decimal(str(value)).quantize(Decimal("0.01")) if value not in (None, "") else Decimal("0.00")
    except InvalidOperation:
        return Decimal("0.00")


def whole(value):
    try:
        return int(float(value))
    except TypeError, ValueError:
        return None


class ShiprocketClient(Client):
    base_url = BASE_URL

    def headers(self):
        return {"Authorization": f"Bearer {self.token()}"}

    def body_error(self, response, data):
        if not isinstance(data, dict):
            return ""
        for name, path in REFUSED_IN_200.items():
            if name in data and not flag(data[name]):
                reason = data
                for key in path:
                    reason = reason.get(key) if isinstance(reason, dict) else None
                return str(reason or describe(data) or f"{name}: 0")
        code = data.get("status_code")
        if isinstance(code, int) and code >= 400:
            return describe(data) or f"status_code {code}"
        if str(data.get("message", "")).lower().startswith("invalid data"):
            return describe(data)
        return ""

    def token(self):
        account = self.account
        if account.token and account.token_expires_at and account.token_expires_at - timezone.now() > RENEW_BEFORE:
            return account.get_token()
        return self.renew_token()

    def renew_token(self, stale=""):
        """A new token from the API user's email and password, unless another worker has just made one: one worker at
        a time logs in (a cache lock; while the cache is down, each worker logs in for itself, which Shiprocket
        allows). No transaction is held during the call."""
        lock = f"shipping:shiprocket-token:{self.account.pk}"
        locked = cache.add(lock, 1, timeout=60)
        if locked is False:  # another worker is logging in: use its token once it is there (3 s at most)
            for _ in range(10):
                time.sleep(0.3)
                fresh = IntegrationAccount.objects.get(pk=self.account.pk)
                if fresh.token and fresh.token != stale and fresh.token_expires_at > timezone.now() + RENEW_BEFORE:
                    self.account.token, self.account.token_expires_at = fresh.token, fresh.token_expires_at
                    return fresh.get_token()
        try:
            credentials = self.account.get_credentials()
            login = {"email": credentials.get("email", ""), "password": credentials.get("password", "")}
            data = self.request("POST", "/auth/login", operation="login", json=login, auth=False) or {}
            if not data.get("token"):
                raise IntegrationAuthFailed(f"{self.account} login: no token in the answer", account=self.account)
            self.account.set_token(data["token"], timezone.now() + TOKEN_LIFE)
            return data["token"]
        finally:
            if locked:
                cache.delete(lock)

    def call(self, method, path, *, operation, **kwargs):
        """request(), with one new token and one more try after a 401 (a token revoked or expired early)."""
        try:
            return self.request(method, path, operation=operation, **kwargs)
        except IntegrationAuthFailed:
            if kwargs.get("auth") is False:
                raise
            self.renew_token(stale=self.account.token)
            return self.request(method, path, operation=operation, **kwargs)


class ShiprocketCarrier(Carrier):
    name = "shiprocket"

    def __init__(self, account, transport=None, force=False):
        super().__init__(account)
        self.client = ShiprocketClient(account, transport=transport, force=force)

    @classmethod
    def test_transport(cls):
        from .fake import FAKE

        return FAKE.transport()

    # Rates

    def quote(self, parcel, timeout=None):
        params = {
            "pickup_postcode": parcel.pickup_pin,
            "delivery_postcode": parcel.delivery_pin,
            "cod": int(parcel.cod),
            "weight": f"{parcel.weight_g / 1000:.3f}",
            "length": parcel.length_cm,
            "breadth": parcel.breadth_cm,
            "height": parcel.height_cm,
            "declared_value": f"{parcel.declared_value:.2f}",
        }
        try:
            data = self.client.call(
                "GET", "/courier/serviceability/", operation="quote", params=params, timeout=timeout
            )
        except IntegrationRejected as error:
            if error.status_code in (404, 422):  # no courier serves it
                return []
            raise
        data = data if isinstance(data, dict) else {}
        if whole(data.get("status")) == 404:
            return []
        body = data.get("data") or {}
        recommended = whole(body.get("recommended_courier_company_id") or body.get("shiprocket_recommended_courier_id"))
        quotes = []
        for item in body.get("available_courier_companies") or []:
            courier = whole(item.get("courier_company_id"))
            if courier is None:
                continue
            quotes.append(
                Quote(
                    courier_company_id=courier,
                    courier_name=str(item.get("courier_name") or ""),
                    rate=decimal(item.get("rate")),
                    etd_days=whole(item.get("estimated_delivery_days")),
                    rating=float(item["rating"]) if item.get("rating") not in (None, "") else None,
                    cod=flag(item.get("cod")),
                    cod_charges=decimal(item.get("cod_charges")),
                    rto_charges=decimal(item.get("rto_charges")),
                    blocked=flag(item.get("blocked")) or flag(item.get("odablock")),
                    recommended=courier == recommended,
                )
            )
        return quotes

    # Booking

    def order_payload(self, shipment):
        """Shiprocket's order for the parcel: the customer as billing and shipping address, the books as items,
        `sub_total` the cash the courier collects (cash on delivery) or the value (prepaid); shipping and discounts are
        already in it, so they are sent as 0 (Shiprocket does not add them up, and must not add them again)."""
        order, detail = shipment.order, shipment.detail
        address = order.shipping_address
        first, _, last = address["name"].strip().partition(" ")
        payload = {
            "order_id": detail.reference,
            "order_date": timezone.localtime(order.placed_at or order.created, IST).strftime("%Y-%m-%d %H:%M"),
            "pickup_location": detail.pickup_location.nickname,
            "billing_customer_name": first,
            "billing_last_name": last,
            "billing_address": address["line1"],
            "billing_address_2": address.get("line2", ""),
            "billing_city": address["city"][:30],
            "billing_pincode": address["pin"],
            "billing_state": STATES.get(address["state"], address["state"]),
            "billing_country": "India",
            "billing_email": order.email,
            "billing_phone": str(address["phone"]).removeprefix("+91")[-10:],
            "shipping_is_billing": True,
            "order_items": [
                {
                    "name": item.title[:200],
                    "sku": f"EL-{item.product_id}",
                    "units": item.quantity,
                    "selling_price": f"{item.unit_price.amount:.2f}",
                    "discount": "0",
                    "tax": f"{item.gst_rate:.2f}",
                    "hsn": item.hsn_code,
                }
                for item in order.items.all()
            ],
            "payment_method": "COD" if order.is_cod else "Prepaid",
            "shipping_charges": 0,
            "giftwrap_charges": 0,
            "transaction_charges": 0,
            "total_discount": 0,
            "sub_total": float(detail.cod_amount if order.is_cod else detail.declared_value),
            "length": detail.length_cm,
            "breadth": detail.breadth_cm,
            "height": detail.height_cm,
            "weight": round(detail.weight_g / 1000, 3),
        }
        return payload

    def find_order(self, reference):
        """Shiprocket's order made with our order id, if a try whose answer was lost made it: (order id, shipment
        id, AWB) or None."""
        data = self.client.call("GET", "/orders", operation="find_order", params={"search": reference}) or {}
        for order in data.get("data") or []:
            if str(order.get("channel_order_id")) == reference:
                shipments = order.get("shipments") or [{}]
                awb = str(shipments[0].get("awb") or shipments[0].get("awb_code") or "")
                return str(order.get("id")), str(shipments[0].get("id") or ""), awb
        return None

    def book(self, shipment, courier_company_id):
        """Create the order (or find the one an earlier try made: Shiprocket refuses a reused order id with a 422),
        saving its ids at once, then assign the AWB with this courier, unless an earlier try did (its answer lost)."""
        detail = shipment.detail
        if detail.external_shipment_id and (found := self.find_order(detail.reference)) and found[2]:
            return Booking(found[0], found[1], found[2], courier_company_id, detail.courier_name)
        if not detail.external_shipment_id:
            try:
                data = self.client.call(
                    "POST", "/orders/create/adhoc", operation="create_order", json=self.order_payload(shipment)
                )
                ids = str(data["order_id"]), str(data["shipment_id"])
            except IntegrationRejected as error:
                if error.status_code != 422 or not (found := self.find_order(detail.reference)):
                    raise
                ids = found[:2]
            detail.change(external_order_id=ids[0], external_shipment_id=ids[1])
        data = self.client.call(
            "POST",
            "/courier/assign/awb",
            operation="assign_awb",
            json={"shipment_id": int(detail.external_shipment_id), "courier_id": courier_company_id},
        )
        assigned = ((data or {}).get("response") or {}).get("data") or {}
        if not assigned.get("awb_code"):
            raise IntegrationRejected(f"{self.account} assign_awb: no AWB in the answer", account=self.account)
        return Booking(
            external_order_id=detail.external_order_id,
            external_shipment_id=detail.external_shipment_id,
            awb=str(assigned["awb_code"]),
            courier_company_id=whole(assigned.get("courier_company_id")) or courier_company_id,
            courier_name=str(assigned.get("courier_name") or ""),
        )

    def label(self, shipment):
        """The label's PDF, fetched from the link Shiprocket gives (the link's host gets no token)."""
        data = self.client.call(
            "POST",
            "/courier/generate/label",
            operation="label",
            json={"shipment_id": [int(shipment.detail.external_shipment_id)]},
        )
        url = (data or {}).get("label_url")
        if not url:
            raise IntegrationRejected(f"{self.account} label: no label_url in the answer", account=self.account)
        content = self.client.request("GET", url, operation="label_file", auth=False, raw=True).content
        if not content.startswith(b"%PDF") or len(content) > MAX_LABEL_BYTES:
            raise IntegrationRejected(f"{self.account} label_file: not a PDF of 5 MB at most", account=self.account)
        return content

    def schedule_pickup(self, shipment, on=None):
        payload = {"shipment_id": [int(shipment.detail.external_shipment_id)]}
        if on:
            payload["pickup_date"] = [on.isoformat()]
        data = self.client.call("POST", "/courier/generate/pickup", operation="pickup", json=payload) or {}
        when = parse_time((data.get("response") or {}).get("pickup_scheduled_date"))
        return when.date() if when else on

    def manifest(self, shipments):
        ids = [int(shipment.detail.external_shipment_id) for shipment in shipments]
        try:
            data = self.client.call("POST", "/manifests/generate", operation="manifest", json={"shipment_id": ids})
        except IntegrationRejected:  # generated before: print it again
            orders = [int(shipment.detail.external_order_id) for shipment in shipments]
            data = self.client.call("POST", "/manifests/print", operation="manifest_print", json={"order_ids": orders})
        url = (data or {}).get("manifest_url")
        if not url:
            raise IntegrationRejected(f"{self.account} manifest: no manifest_url in the answer", account=self.account)
        return url

    def cancel(self, shipment):
        """Cancel by AWB (possible only before the courier is out for pickup), or the order while it has no AWB."""
        if shipment.tracking_number:
            body = {"awbs": [shipment.tracking_number]}
            self.client.call("POST", "/orders/cancel/shipment/awbs", operation="cancel", json=body)
        else:
            body = {"ids": [int(shipment.detail.external_order_id)]}
            self.client.call("POST", "/orders/cancel", operation="cancel_order", json=body)

    def ndr_action(self, shipment, action, comments, **fields):
        body = {"action": action, "comments": comments, **{name: value for name, value in fields.items() if value}}
        self.client.call("POST", f"/ndr/{shipment.tracking_number}/action", operation="ndr_action", json=body)

    # Tracking

    def scan(self, awb, item):
        """A scan of a tracking answer or a webhook ("sr-status" is the shipment status code); None without a time."""
        occurred_at = parse_time(item.get("date"))
        if occurred_at is None:
            return None
        code = str(item.get("sr-status") or "").strip()
        label = str(item.get("sr-status-label") or item.get("status") or "")
        return Scan(
            awb=awb,
            code=code,
            label=label if label != "NA" else str(item.get("activity") or "")[:100],
            status=from_shiprocket(code),
            occurred_at=occurred_at,
            location=str(item.get("location") or "")[:200],
            activity=str(item.get("activity") or "")[:300],
            raw=item,
        )

    def scans(self, awb, tracking_data):
        activities = (tracking_data or {}).get("shipment_track_activities") or []
        found = [self.scan(awb, item) for item in activities if isinstance(item, dict)]
        return sorted((scan for scan in found if scan), key=lambda scan: scan.occurred_at)

    def track(self, awbs):
        awbs = [awb for awb in awbs if awb]
        result = {}
        for start in range(0, len(awbs), TRACK_BATCH):
            batch = awbs[start : start + TRACK_BATCH]
            if len(batch) == 1:
                data = self.client.call("GET", f"/courier/track/awb/{batch[0]}", operation="track") or {}
                answers = {batch[0]: data}
            else:
                answers = self.client.call("POST", "/courier/track/awbs", operation="track", json={"awbs": batch})
                if isinstance(answers, list):  # one object per AWB, keyed by it, in a list
                    answers = {
                        awb: answer for item in answers if isinstance(item, dict) for awb, answer in item.items()
                    }
            for awb in batch:
                answer = (answers or {}).get(awb) or {}
                result[awb] = self.scans(awb, answer.get("tracking_data"))
        return result

    def parse_webhook(self, data):
        """The documented body: the AWB, the current status (shipment_status_id, and current_timestamp) and the scans
        so far. The current status becomes a scan of its own when no scan carries it."""
        awb = str(data.get("awb") or "")
        scans = [scan for item in data.get("scans") or [] if isinstance(item, dict) and (scan := self.scan(awb, item))]
        code = str(data.get("shipment_status_id") or "")
        status = from_shiprocket(code)
        at = parse_time(data.get("current_timestamp"))
        if status and at and not any(scan.code == code for scan in scans):
            fields = [
                "current_status",
                "current_status_id",
                "shipment_status",
                "shipment_status_id",
                "current_timestamp",
            ]
            label = str(data.get("shipment_status") or data.get("current_status") or "")
            raw = {name: data.get(name) for name in fields}
            scans.append(Scan(awb, code, label, status, at, activity=str(data.get("current_status") or ""), raw=raw))
        return WebhookPayload(
            awb=awb, scans=sorted(scans, key=lambda scan: scan.occurred_at), is_return=flag(data.get("is_return"))
        )

    # Money

    def wallet_balance(self):
        data = self.client.call("GET", "/account/details/wallet-balance", operation="wallet_balance") or {}
        return decimal((data.get("data") or {}).get("balance_amount"))

    def statement(self, start, end):
        """The wallet statement's rows from `start` to `end` (dates), every page."""
        rows, page = [], 1
        while page <= 100:
            params = {"from": start.isoformat(), "to": end.isoformat(), "page": page, "per_page": 100}
            data = self.client.call("GET", "/account/details/statement", operation="statement", params=params) or {}
            batch = [row for row in data.get("data") or [] if isinstance(row, dict)]
            rows += batch
            pages = whole(((data.get("meta") or {}).get("pagination") or {}).get("total_pages")) or 1
            if not batch or page >= pages:
                break
            page += 1
        return rows

    def discrepancies(self):
        data = self.client.call("GET", "/billing/discrepancy", operation="discrepancies") or {}
        return [row for row in data.get("data") or [] if isinstance(row, dict)]

    def order_detail(self, external_order_id):
        data = self.client.call("GET", f"/orders/show/{external_order_id}", operation="order_detail") or {}
        return data.get("data") or {}

    def pickup_locations(self):
        data = self.client.call("GET", "/settings/company/pickup", operation="pickup_locations") or {}
        return (data.get("data") or {}).get("shipping_address") or []


def connection_test(account):
    """The account's connection test (integrations.services.CONNECTION_TESTS): the wallet balance, a harmless read."""
    carrier = ShiprocketCarrier(
        account, transport=ShiprocketCarrier.test_transport() if account.mode == account.Mode.TEST else None, force=True
    )
    return f"Connected: wallet balance ₹{carrier.wallet_balance():,.2f}."
