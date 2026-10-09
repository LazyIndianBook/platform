"""The carriers, by name: an account's provider names its carrier, its mode says real or recorded (test mode answers
from fake.py: Shiprocket has no sandbox). A carrier with no account is the manual one."""

from .base import Booking, Carrier, NotSupported, Parcel, Quote, Scan, WebhookPayload
from .manual import ManualCarrier
from .shiprocket import ShiprocketCarrier

CARRIERS = {"manual": ManualCarrier, "shiprocket": ShiprocketCarrier}


def carrier_for(account=None):
    """The carrier of an IntegrationAccount (test mode: its recorded double), or the manual one without an account."""
    if account is None:
        return ManualCarrier()
    carrier = CARRIERS[account.provider]
    test = account.mode == account.Mode.TEST and hasattr(carrier, "test_transport")
    return carrier(account, transport=carrier.test_transport() if test else None)


__all__ = [
    "CARRIERS",
    "Booking",
    "Carrier",
    "ManualCarrier",
    "NotSupported",
    "Parcel",
    "Quote",
    "Scan",
    "ShiprocketCarrier",
    "WebhookPayload",
    "carrier_for",
]
