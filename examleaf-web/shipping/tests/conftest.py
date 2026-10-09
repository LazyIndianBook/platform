import httpx
import pytest
from django.contrib.auth.models import Group

from accounts import roles
from accounts.factories import UserFactory
from integrations import crypto
from integrations.models import IntegrationAccount
from shipping import messages
from shipping.carriers.fake import FAKE
from shipping.models import PickupLocation
from shop import invoices
from shop import services as shop
from shop.factories import ProductFactory, make_order, verified_user
from shop.models import Cart

WEBHOOK_TOKEN = "fixed-webhook-token-for-the-tests-0123456789"


@pytest.fixture(autouse=True)
def fake_shiprocket():
    """Test mode's recorded Shiprocket, fresh for each test; no real request leaves."""
    FAKE.reset()
    yield FAKE
    FAKE.reset()


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(self, request):
        raise AssertionError(f"a test tried to reach {request.url}")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)


@pytest.fixture(autouse=True)
def daytime(monkeypatch):
    """SMS go at once unless a test is about the night (messages.quiet)."""
    monkeypatch.setattr(messages, "quiet", lambda now=None: False)


@pytest.fixture(autouse=True)
def quick_pdf(monkeypatch, settings):
    """A COD order's bill is made at dispatch: a stand-in PDF, by a seller whose details are filled in."""
    monkeypatch.setattr(invoices, "render_pdf", lambda document: b"%PDF-1.7 stand-in")
    settings.SHOP_SELLER = {
        **settings.SHOP_SELLER,
        "address": "House 1, Zoo Road, Guwahati, Assam 781024",
        "email": "orders@examleaf.in",
        "phone": "+91 98640 00000",
    }


@pytest.fixture
def texts(monkeypatch):
    """The SMS the shipping app asked for: (order number, kind)."""
    sent = []
    monkeypatch.setattr(messages, "send_order_sms", lambda order, kind: sent.append((order.number, kind)))
    return sent


@pytest.fixture
def account(db):
    account = IntegrationAccount.objects.create(provider="shiprocket", mode="test", enabled=True, label="API user")
    account.set_credentials({"email": "api-user@example.com", "password": "a-long-api-password"})
    account.save()
    IntegrationAccount.objects.filter(pk=account.pk).update(webhook_token=crypto.encrypt(WEBHOOK_TOKEN))
    account.refresh_from_db()
    return account


@pytest.fixture
def pickup(db):
    return PickupLocation.objects.create(
        nickname="Primary", city="Guwahati", state="Assam", pin_code="781024", phone="9864000000", is_default=True
    )


@pytest.fixture
def book(db):
    return ProductFactory(weight_grams=300, stock=20)


@pytest.fixture
def customer(db):
    user = verified_user("rahul@example.com")
    user.login_phone, user.login_phone_verified, user.sms_updates = "+919864012345", True, True
    user.save()
    return user


def ordered(*lines, **kwargs):
    order = make_order(*lines, **kwargs)
    Cart.objects.filter(user=kwargs.get("user")).delete()  # as the checkout does: the next order has a cart again
    return order


@pytest.fixture
def prepaid(book, customer):
    """A paid order of one book (₹299, no shipping rate), packed."""
    order = ordered((book, 1), user=customer, email=customer.email, pin="781024")
    shop.record_offline_payment(order, "UTR-TEST-1")
    return shop.pack_order(order)


@pytest.fixture
def cod(book, customer, settings):
    """A cash-on-delivery order of two books (₹598), placed and packed."""
    settings.SHOP_COD_ENABLED = True
    order = ordered((book, 2), method="cod", user=customer, email=customer.email, pin="781024")
    shop.place_cod(order)
    return shop.pack_order(order)


@pytest.fixture
def staff_client(client):
    """ADMIN: every shipping permission (staff/tests/test_matrix.py has each role's)."""
    admin = UserFactory(is_staff=True)
    admin.groups.set(Group.objects.filter(name=roles.ADMIN))
    client.force_login(admin)
    return client
