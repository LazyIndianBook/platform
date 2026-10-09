"""What the erp app tells the rest of the site, after the commit: each difference the reconciliation found (the staff
inbox gets one item per run from erp/inbox.py; nothing else listens yet). A dead outbox row is integrations'
dead_letter_created."""

from django.dispatch import Signal

reconciliation_difference = Signal()  # difference (ErpReconciliationDifference): staff to look at, then resolve
