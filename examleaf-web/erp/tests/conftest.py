from decimal import Decimal

import httpx
import pytest

from erp.fake import FAKE
from integrations import crypto
from integrations.models import IntegrationAccount
from shop import invoices
from shop.factories import ProductFactory, verified_user
from shop.models import Product

from .helpers import WEBHOOK_SECRET

SWITCHES = [
    *["ERP_ENABLED", "ERP_SYNC_CATALOGUE", "ERP_SYNC_INVOICES", "ERP_SYNC_PAYMENTS", "ERP_SYNC_DELIVERIES"],
    *["ERP_SYNC_SETTLEMENTS", "ERP_PULL_STOCK", "ERP_PULL_B2B"],
]


@pytest.fixture(autouse=True)
def fake_erp(settings):
    """The in-memory ERPNext (ERP_MODE=fake), fresh for each test; every switch off, as by default."""
    settings.ERP_MODE, settings.ERP_WAREHOUSE = "fake", "Main"
    for name in [*SWITCHES, "ERP_STOCK_PROJECTION"]:
        setattr(settings, name, False)
    FAKE.reset()
    yield FAKE
    FAKE.reset()


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(self, request):
        raise AssertionError(f"a test tried to reach {request.url}")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)


@pytest.fixture(autouse=True)
def quick_pdf(monkeypatch, settings):
    """Invoices and credit notes with a stand-in PDF, by a seller whose details are filled in."""
    monkeypatch.setattr(invoices, "render_pdf", lambda document: b"%PDF-1.7 stand-in")
    settings.SHOP_SELLER = {
        **settings.SHOP_SELLER,
        "address": "House 1, Zoo Road, Guwahati, Assam 781024",
        "email": "orders@examleaf.in",
        "phone": "+91 98640 00000",
    }


@pytest.fixture
def switched_on(settings):
    """ERPNext enabled, every flow and both pulls on; the projection off (shadow mode)."""
    for name in SWITCHES:
        setattr(settings, name, True)
    return settings


@pytest.fixture
def erp_account(db):
    account = IntegrationAccount.objects.create(provider="erpnext", mode="test", enabled=True, label="erp-sync@")
    keys = {"api_key": "key-of-the-tests", "api_secret": "secret-of-the-tests", "base_url": "https://erp.test"}
    account.set_credentials(keys)
    account.save()
    IntegrationAccount.objects.filter(pk=account.pk).update(webhook_token=crypto.encrypt(WEBHOOK_SECRET))
    account.refresh_from_db()
    return account


@pytest.fixture
def on(switched_on, erp_account):
    """Everything on and an account: the sync as in the parallel run (shadow mode)."""
    return erp_account


@pytest.fixture
def book(db):
    return ProductFactory(title="Physics Sample Papers 2027", weight_grams=300, stock=20)


@pytest.fixture
def course(db):
    return ProductFactory(
        title="Physics revision course",
        kind=Product.Kind.DIGITAL,
        hsn_code="999293",
        gst_rate=Decimal("18"),
        mrp=Decimal("999.00"),
        price=Decimal("999.00"),
        stock=0,
    )


@pytest.fixture
def customer(db):
    return verified_user("rahul@example.com")
