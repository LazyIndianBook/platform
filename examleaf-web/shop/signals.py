"""What the shop tells the rest of the site, inside the transaction of the change: a receiver's writes commit or roll
back with it (the erp app's outbox rows, erp/producers.py)."""

from django.dispatch import Signal

order_shipped = Signal()  # order, shipment: the order's shipped step (services.shipped), in its transaction
