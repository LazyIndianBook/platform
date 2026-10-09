"""What the integrations tell the rest of the site, sent once the transaction is committed: the staff app files its
inbox items from them (nothing listens yet)."""

from django.dispatch import Signal

integration_failed = Signal()  # account, error: its circuit opened, calls wait
integration_recovered = Signal()  # account: its circuit closed again
dead_letter_created = Signal()  # failure (IntegrationFailure): a task gave up
inbound_event_failed = Signal()  # event (InboundEvent), error: its processing gave up
