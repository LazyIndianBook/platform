"""The carrier interface: what a courier is asked, whoever the courier is. A carrier is made for an IntegrationAccount
(carrier_for, in __init__.py) and each method does one thing at the carrier; services.py decides when, keeps the
results and runs their effects. What a carrier cannot do raises NotSupported."""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from shop.models import Shipment


class NotSupported(Exception):
    """This carrier does not do that (the manual one books no pickup, prints no label)."""


@dataclass
class Parcel:
    """What a quote needs: from where to where, how heavy and big, cash on delivery or not, and its value."""

    pickup_pin: str
    delivery_pin: str
    weight_g: int
    cod: bool
    declared_value: Decimal
    length_cm: int
    breadth_cm: int
    height_cm: int


@dataclass
class Quote:
    """One courier's offer for a parcel."""

    courier_company_id: int
    courier_name: str
    rate: Decimal
    etd_days: int | None = None
    rating: float | None = None
    cod: bool = False
    cod_charges: Decimal = Decimal("0.00")
    rto_charges: Decimal = Decimal("0.00")
    blocked: bool = False  # blocked for the account, or out of its delivery area (ODA)
    recommended: bool = False  # the carrier's own pick


@dataclass
class Booking:
    """A parcel the carrier has taken: its ids and the AWB."""

    external_order_id: str
    external_shipment_id: str
    awb: str
    courier_company_id: int | None
    courier_name: str


@dataclass
class Scan:
    """One tracking event as the carrier reports it, with our status for its code (None: none of ours)."""

    awb: str
    code: str  # the carrier's status code (Shiprocket: the shipment status id)
    label: str
    status: str | None
    occurred_at: datetime
    location: str = ""
    activity: str = ""
    raw: dict = field(default_factory=dict)

    @property
    def digest(self):
        """The scan's identity: the AWB, the code, the time and the activity (spaces and case aside), so that a scan
        repeated in later payloads, or read again by a poll, is one."""
        activity = " ".join(self.activity.split()).lower()
        text = f"{self.awb}|{self.code}|{self.occurred_at.isoformat()}|{activity}"
        return hashlib.sha256(text.encode()).hexdigest()


@dataclass
class WebhookPayload:
    awb: str
    scans: list[Scan]
    is_return: bool = False


class Carrier:
    name = ""

    def __init__(self, account=None):
        self.account = account

    def quote(self, parcel, timeout=None):
        """[Quote] for a Parcel (empty: no courier serves it)."""
        raise NotSupported(f"{self.name}: no quotes")

    def book(self, shipment, courier_company_id):
        """Hand the parcel (shop.Shipment with its detail) to the carrier with this courier: a Booking. Idempotent:
        a booking whose answer was lost is found again, never made twice."""
        raise NotSupported(f"{self.name}: no booking")

    def label(self, shipment):
        """The label as PDF bytes."""
        raise NotSupported(f"{self.name}: no labels")

    def schedule_pickup(self, shipment, on=None):
        """Ask for the courier to collect it (on a date, or the next one possible): the date it was booked for."""
        raise NotSupported(f"{self.name}: no pickups")

    def manifest(self, shipments):
        """The handover list of these parcels: a link to its PDF."""
        raise NotSupported(f"{self.name}: no manifests")

    def cancel(self, shipment):
        """Cancel a booking (before the courier is out to collect it)."""
        raise NotSupported(f"{self.name}: no cancellation")

    def track(self, awbs):
        """{awb: [Scan]} for these AWBs."""
        raise NotSupported(f"{self.name}: no tracking")

    def ndr_action(self, shipment, action, comments, **fields):
        """After a failed delivery: try again (with a date, phone or address), report a fake attempt, or return."""
        raise NotSupported(f"{self.name}: no NDR actions")

    def parse_webhook(self, data):
        """A WebhookPayload from the decoded JSON the carrier posted."""
        raise NotSupported(f"{self.name}: no webhooks")

    def tracking_url(self, courier, awb):
        """Where a customer can follow the parcel themselves: the courier's page, or 17TRACK's (as for staff's)."""
        return Shipment.tracking_url_for(courier, awb)
