"""The support tests' helpers: the staff tests' (members of staff with roles, the panel's session, the audit log's
events) and the shop's fixtures (Razorpay mocked, no network), and a ticket made as the services make one."""

import pytest
from django.utils import timezone

from shop.conftest import commit, no_network, quick_pdf, rzp, shop_settings  # noqa: F401  (fixtures)
from staff.tests.conftest import STAFF, events, make_staff, quick_passwords, signed_in  # noqa: F401
from support import services
from support.models import Ticket, TicketMessage

SUPPORT = STAFF + "support/"


@pytest.fixture(autouse=True)
def support_settings(settings):
    settings.SUPPORT_EMAIL = "help@examleaf.in"  # the contact form needs a support address
    settings.DEFAULT_FROM_EMAIL = "ExamLeaf <noreply@examleaf.in>"


def make_ticket(**fields):
    """A ticket from the website's form (by default), its clocks from `received_at`; its acknowledgement waits for the
    test's commit()."""
    values = {
        "source": Ticket.Source.FORM,
        "channel": TicketMessage.Channel.WEB,
        "subject": "Where is my parcel?",
        "body": "Order EL-2026-000123 has not come.",
        "name": "Rahul Das",
        "email": "rahul@example.com",
        "received_at": timezone.now(),
        **fields,
    }
    return services.create_ticket(**values)
