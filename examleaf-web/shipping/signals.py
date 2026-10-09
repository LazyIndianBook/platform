"""What the shipping app tells the rest of the site: after the commit, exception_opened (the staff app files an inbox
item for each exception; nothing listens yet); inside the transaction of the scans, parcel_left (the erp app's
delivery note is written with them)."""

from django.dispatch import Signal

exception_opened = Signal()  # exception (ShippingException), kind: a parcel needs staff, by exception.due_at
parcel_left = Signal()  # shipment: a courier's scans say its parcel has left us (once a parcel), in their transaction
