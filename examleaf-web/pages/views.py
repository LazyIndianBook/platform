from django.conf import settings

from .models import PLACEHOLDER

CONTACT_SENT = "Thank you: your message is on its way to us. We reply by email."  # the message is a support ticket


def support_email():
    """The support address: SUPPORT_EMAIL, else the seller's address (SELLER_EMAIL); "" while that is empty or still a
    [placeholder], and the contact form (api/v1/contact/) is then refused. The support tickets' emails name it as their
    Reply-To (support/mail.py); forwarded to /api/hooks/support-mail/, it is the panel's inbox."""
    address = getattr(settings, "SUPPORT_EMAIL", "") or settings.SHOP_SELLER["email"]
    return "" if not address or PLACEHOLDER.search(address) else address
