"""What the shipping app tells the rest of the site, after the commit: the staff app files an inbox item for each
exception (nothing listens yet)."""

from django.dispatch import Signal

exception_opened = Signal()  # exception (ShippingException), kind: a parcel needs staff, by exception.due_at
