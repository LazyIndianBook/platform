import httpx
import pytest
from cryptography.fernet import Fernet

from integrations.client import Client
from integrations.models import IntegrationAccount
from shop.conftest import commit, no_network, rzp  # noqa: F401  (fixtures: the commit's callbacks, Razorpay's SDK)
from staff.tests.conftest import quick_passwords  # noqa: F401  (the connections page's members of staff)


@pytest.fixture
def account(db):
    return IntegrationAccount.objects.create(provider="shiprocket", mode="test", enabled=True, label="tests")


@pytest.fixture
def fernet_keys(settings):
    """Two real keys, the first one in use."""
    keys = [Fernet.generate_key().decode(), Fernet.generate_key().decode()]
    settings.INTEGRATION_KEYS = keys[:1]
    return keys


class Echo(Client):
    """A provider whose answers the test gives: `answer(request)` returns an httpx.Response, or raises."""

    base_url = "https://api.example.test/v1"

    def body_error(self, response, data):
        return data.get("error_in_200", "") if isinstance(data, dict) else ""


@pytest.fixture
def echo(account):
    """(client, sent): an Echo client of `account` and the requests it sent; set `client.answer`."""
    sent = []

    def handler(request):
        sent.append(request)
        return client.answer(request)

    client = Echo(account, transport=httpx.MockTransport(handler))
    client.answer = lambda request: httpx.Response(200, json={"ok": True})
    return client, sent
