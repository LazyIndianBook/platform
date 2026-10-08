from unittest.mock import MagicMock

import pytest
import razorpay
import requests

from shop import invoices, payments
from shop.factories import KEY, SECRET, WEBHOOK_SECRET


def pytest_configure(config):
    config.addinivalue_line("markers", "real_pdf: render invoices with WeasyPrint instead of a stand-in")


@pytest.fixture(autouse=True)
def shop_settings(settings):
    settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET = KEY, SECRET  # test keys: test mode
    settings.RAZORPAY_WEBHOOK_SECRET_TEST, settings.RAZORPAY_WEBHOOK_SECRET = WEBHOOK_SECRET, "live-webhook-secret"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("a test tried to reach the network")

    monkeypatch.setattr(requests.Session, "request", refuse)


@pytest.fixture(autouse=True)
def quick_pdf(request, monkeypatch):
    if "real_pdf" not in request.keywords:  # WeasyPrint takes about a second per invoice
        monkeypatch.setattr(invoices, "render_pdf", lambda invoice: b"%PDF-1.7 stand-in")


@pytest.fixture
def rzp(monkeypatch):
    """Razorpay's client with its network calls replaced; signatures are still checked by the SDK (local HMAC)."""
    client = MagicMock()
    client.utility = razorpay.Client(auth=(KEY, SECRET)).utility
    client.order.create.side_effect = lambda data, **kw: {"id": f"order_{data['receipt']}", **data}
    client.payment.fetch_multiple_refund.return_value = {"entity": "collection", "count": 0, "items": []}
    client.payment.refund.side_effect = lambda payment_id, data, **kw: {
        "id": f"rfnd_{data['notes']['refund_id']}",
        "status": "processed",
        "amount": data["amount"],
    }
    monkeypatch.setattr(payments, "client", lambda: client)
    return client


@pytest.fixture
def commit(django_capture_on_commit_callbacks):
    """`with commit():` runs what the code queues for after the commit (emails, tasks), as production would."""
    return lambda: django_capture_on_commit_callbacks(execute=True)


@pytest.fixture
def real_seller(settings):
    """The seller's details as .env gives them once filled in (the defaults hold [placeholders])."""
    settings.SHOP_SELLER = {
        **settings.SHOP_SELLER,
        "address": "House 1, Zoo Road, Guwahati, Assam 781001",
        "email": "orders@examleaf.in",
        "phone": "+91 98640 00000",
    }
