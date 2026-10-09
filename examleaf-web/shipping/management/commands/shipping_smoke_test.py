"""The live smoke test (research-integrations.md 3.10): with the live Shiprocket account, book a prepaid parcel to our
own pickup address, assign an AWB, fetch the label, cancel before pickup and look for the freight's reversal in the
wallet statement, printing every step. It touches no order of the shop. Real money moves (the freight is debited,
then given back on cancellation), so it runs only with --yes, and never with a test-mode account (whose answers are
recorded ones: nothing would be tested)."""

import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from integrations.client import IntegrationError
from integrations.models import IntegrationAccount
from shipping.carriers import ShiprocketCarrier
from shipping.carriers.shiprocket import decimal
from shipping.models import PickupLocation


class Command(BaseCommand):
    help = (
        "Book, label and cancel one prepaid parcel to our own pickup address with the live Shiprocket account, then "
        "check the freight's reversal in the statement. Real money moves: needs --yes."
    )

    def add_arguments(self, parser):
        parser.add_argument("--yes", action="store_true", help="Book for real (the freight is debited, then reversed).")
        parser.add_argument("--wait", type=int, default=120, help="Seconds to wait for the reversal (default 120).")

    def step(self, text):
        self.stdout.write(f"· {text}")

    def handle(self, *args, yes=False, wait=120, **options):
        account = IntegrationAccount.enabled_for("shiprocket")
        if account is None:
            raise CommandError("No Shiprocket account is enabled.")
        if account.mode != IntegrationAccount.Mode.LIVE:
            raise CommandError("The enabled Shiprocket account is in test mode: the smoke test is for the live one.")
        if not yes:
            raise CommandError("This books a real parcel (the freight is debited, then reversed): run it with --yes.")
        pickup = PickupLocation.default()
        if pickup is None:
            raise CommandError("No pickup location: add ours (Shipping → Pickup locations) as Shiprocket names it.")
        carrier = ShiprocketCarrier(account)
        call = carrier.client.call
        reference = f"SMOKE-{timezone.localtime():%Y%m%d%H%M%S}"
        try:
            self.step(f"Logging in as the API user of {account}")
            carrier.client.token()
            self.step(f"Token valid until {account.token_expires_at:%d %b %Y %H:%M}")
            balance = carrier.wallet_balance()
            self.step(f"Wallet balance: ₹{balance:,.2f}")
            params = {"pickup_postcode": pickup.pin_code, "delivery_postcode": pickup.pin_code, "cod": 0, "weight": 0.5}
            couriers = (call("GET", "/courier/serviceability/", operation="smoke_quote", params=params) or {}).get(
                "data", {}
            ).get("available_courier_companies") or []
            if not couriers:
                raise CommandError(f"No courier serves {pickup.pin_code} to itself: try another PIN by hand.")
            cheapest = min(couriers, key=lambda courier: decimal(courier.get("rate")))
            self.step(f"{len(couriers)} couriers; the cheapest: {cheapest['courier_name']} at ₹{cheapest['rate']}")
            order = call("POST", "/orders/create/adhoc", operation="smoke_create", json=self.order(reference, pickup))
            self.step(f"Order {reference}: Shiprocket order {order['order_id']}, shipment {order['shipment_id']}")
            assigned = call(
                "POST",
                "/courier/assign/awb",
                operation="smoke_assign",
                json={"shipment_id": order["shipment_id"], "courier_id": cheapest["courier_company_id"]},
            )
            awb = assigned["response"]["data"]["awb_code"]
            self.step(f"AWB {awb} assigned ({assigned['response']['data'].get('courier_name', '')})")
            label = call(
                "POST", "/courier/generate/label", operation="smoke_label", json={"shipment_id": [order["shipment_id"]]}
            )
            pdf = carrier.client.request("GET", label["label_url"], operation="smoke_label_file", auth=False, raw=True)
            self.step(
                f"Label: {len(pdf.content):,} bytes, {'a PDF' if pdf.content.startswith(b'%PDF') else 'NOT a PDF'}"
            )
            call("POST", "/orders/cancel/shipment/awbs", operation="smoke_cancel", json={"awbs": [awb]})
            self.step(f"Cancelled AWB {awb} before pickup")
        except IntegrationError as error:
            raise CommandError(f"Stopped: {error}") from error
        self.reversal(carrier, awb, wait)

    def order(self, reference, pickup):
        seller = settings.SHOP_SELLER
        return {
            "order_id": reference,
            "order_date": f"{timezone.localtime():%Y-%m-%d %H:%M}",
            "pickup_location": pickup.nickname,
            "billing_customer_name": "ExamLeaf",
            "billing_last_name": "smoke test",
            "billing_address": pickup.address or "Smoke test",
            "billing_city": pickup.city[:30] or "Guwahati",
            "billing_pincode": pickup.pin_code,
            "billing_state": pickup.state or "Assam",
            "billing_country": "India",
            "billing_email": seller["email"] if "@" in seller["email"] else "noreply@example.com",
            "billing_phone": pickup.phone[-10:] or "9999999999",
            "shipping_is_billing": True,
            "order_items": [{"name": "Smoke test: do not ship", "sku": "SMOKE", "units": 1, "selling_price": "1"}],
            "payment_method": "Prepaid",
            "sub_total": 1,
            "length": 25,
            "breadth": 20,
            "height": 3,
            "weight": 0.5,
        }

    def reversal(self, carrier, awb, wait):
        """The statement's freight line for the AWB and its reversal; asked every 20 seconds for `wait` seconds."""
        today = timezone.localdate()
        deadline = time.monotonic() + wait
        while True:
            rows = [row for row in carrier.statement(today, today) if str(row.get("awb_code")) == str(awb)]
            for row in rows:
                self.step(
                    f"Statement: {row.get('description')} −₹{row.get('debit_amount')} +₹{row.get('credit_amount')}"
                )
            if any("reversed" in str(row.get("description", "")).lower() for row in rows):
                self.stdout.write(self.style.SUCCESS("Smoke test passed: booked, labelled, cancelled, reversed."))
                return
            if time.monotonic() > deadline:
                raise CommandError(
                    "No reversal in the statement yet: it can take a while. Check later with shipping_sync_statement."
                )
            time.sleep(20)
