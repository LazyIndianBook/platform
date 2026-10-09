"""The manual carrier: today's counter flow. Staff hand the parcel over (India Post, or any courier without an API),
then type the courier and its number; the customer follows it on the courier's page or 17TRACK's
(shop.models.Shipment.tracking_url_for). Nothing is asked of anyone, so everything but book() is NotSupported and the
parcel's status is what staff record."""

from .base import Booking, Carrier


class ManualCarrier(Carrier):
    name = "manual"

    def book(self, shipment, courier_company_id=None):
        """What staff typed is the booking: the courier and its number on the shipment."""
        return Booking(
            external_order_id="",
            external_shipment_id="",
            awb=shipment.tracking_number,
            courier_company_id=None,
            courier_name=shipment.get_courier_display(),
        )

    def track(self, awbs):
        return {}  # tracking by link
