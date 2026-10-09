"""What the integrations tell the rest of the site, sent once the transaction is committed: the staff app files its
inbox items from them and closes them again (staff.signals; an inbound event's item closes once it is processed)."""

from django.dispatch import Signal

integration_failed = Signal()  # account, error: its circuit opened, calls wait
integration_recovered = Signal()  # account: its circuit closed again
dead_letter_created = Signal()  # failure (IntegrationFailure): a task gave up
dead_letter_closed = Signal()  # failure: replayed or discarded by staff
inbound_event_failed = Signal()  # event (InboundEvent), error: its processing gave up
