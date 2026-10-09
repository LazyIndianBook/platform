"""A parcel's status, ours rather than any courier's (research-integrations.md 3.6), and how Shiprocket's shipment
status codes map to it. A status only moves forward: through the stages booked (or a pickup problem), in transit,
out for delivery (or a failed attempt, which may alternate with it), partly delivered, delivered; or into the return
branch, returning then returned; or to lost or damaged; or, before pickup, cancelled. Delivered, returned, lost or
damaged and cancelled are final. A code that maps to nothing (11 Pending, 47 QC Failed ...) changes nothing."""

from django.db import models


class Status(models.TextChoices):
    BOOKED = "booked", "booked"
    PICKUP_PROBLEM = "pickup_problem", "pickup problem"
    IN_TRANSIT = "in_transit", "in transit"
    OUT_FOR_DELIVERY = "out_for_delivery", "out for delivery"
    DELIVERED = "delivered", "delivered"
    DELIVERY_FAILED = "delivery_failed", "delivery failed"
    RETURNING = "returning", "returning to us"
    RETURNED = "returned", "returned to us"
    LOST_OR_DAMAGED = "lost_or_damaged", "lost or damaged"
    CANCELLED = "cancelled", "cancelled"
    PARTIAL = "partial", "partly delivered"


# Shiprocket's shipment status codes (its tracking table, `shipment_status_id` and a scan's "sr-status"; its order
# status table numbers differently and is not used) [research 1.7, 3.6].
SHIPROCKET_CODES = {
    Status.BOOKED: [1, 2, 3, 4, 5, 15, 19, 27, 52],
    Status.PICKUP_PROBLEM: [13, 20],
    Status.IN_TRANSIT: [6, 18, 22, 38, 39, 42, 48, 51],
    Status.OUT_FOR_DELIVERY: [17],
    Status.DELIVERED: [7, 26],
    Status.DELIVERY_FAILED: [21, 77],
    Status.RETURNING: [9, 40, 41, 46, 75],
    Status.RETURNED: [10, 14, 78],
    Status.LOST_OR_DAMAGED: [12, 24, 25, 44, 76],
    Status.CANCELLED: [8, 16, 45],
    Status.PARTIAL: [23],
}
FROM_SHIPROCKET = {code: status for status, codes in SHIPROCKET_CODES.items() for code in codes}
OUT_FOR_PICKUP = 19  # after it, a shipment can no longer be cancelled (research 1.9)

STAGE = {  # the forward path; the same stage: either way
    Status.BOOKED: 1,
    Status.PICKUP_PROBLEM: 1,
    Status.IN_TRANSIT: 2,
    Status.OUT_FOR_DELIVERY: 3,
    Status.DELIVERY_FAILED: 3,
    Status.PARTIAL: 4,
    Status.DELIVERED: 5,
}
RETURN = {Status.RETURNING: 1, Status.RETURNED: 2}
FINAL = {Status.DELIVERED, Status.RETURNED, Status.LOST_OR_DAMAGED, Status.CANCELLED}
BEFORE_PICKUP = {Status.BOOKED, Status.PICKUP_PROBLEM}
LEFT = {s for s in Status if s not in BEFORE_PICKUP and s != Status.CANCELLED}  # on its way: the order is shipped
CONFIRM = {Status.DELIVERED, Status.RETURNED, Status.LOST_OR_DAMAGED}  # an unsigned webhook's claim is read again


def from_shiprocket(code):
    """Our status for a Shiprocket shipment status code (an int, or its text in a scan), or None."""
    try:
        return FROM_SHIPROCKET.get(int(code))
    except TypeError, ValueError:  # "NA", "", None
        return None


def moves_forward(current, new):
    """Whether a parcel at `current` (None: not booked yet) may move to `new`."""
    if new is None or new == current:
        return False
    if current is None:
        return True
    if current in FINAL:
        return False
    if new == Status.CANCELLED:
        return current in BEFORE_PICKUP
    if new == Status.LOST_OR_DAMAGED:
        return True
    if current in RETURN:
        return new in RETURN and RETURN[new] > RETURN[current]
    if new in RETURN:
        return True
    return STAGE[new] >= STAGE[current]
