"""What the shipping app tells the rest of the site: after the commit, exception_opened and exceptions_closed (the
staff app files an inbox item for each exception and closes it once the exception is: staff.signals); inside the
transaction of the scans, parcel_left (the erp app's delivery note is written with them)."""

from django.dispatch import Signal

exception_opened = Signal()  # exception (ShippingException), kind: a parcel needs staff, by exception.due_at
exceptions_closed = Signal()  # ids: exceptions resolved or dismissed, by staff or by the parcel's news
parcel_left = Signal()  # shipment: a courier's scans say its parcel has left us (once a parcel), in their transaction
