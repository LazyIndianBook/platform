"""The base client: one log line per request (redacted), the circuit counted, and the three exceptions."""

import httpx
import pytest

from integrations.client import CircuitOpen, IntegrationAuthFailed, IntegrationRejected, IntegrationUnavailable
from integrations.models import IntegrationCall
from integrations.redact import excerpt

pytestmark = pytest.mark.django_db

ORDER = {
    "order_id": "EL-2026-000123",
    "billing_customer_name": "Rahul",
    "billing_last_name": "Das",
    "billing_address": "House 4, Zoo Road, Guwahati 781024",
    "billing_pincode": "781024",
    "billing_phone": "9864012345",
    "billing_email": "rahul@example.com",
    "order_items": [{"name": "Physics Sample Papers", "units": 1}],
    "comment": "call +91 98640 12345 first",
}


def test_a_success_is_logged_with_a_redacted_excerpt_and_counts_for_the_circuit(echo, account):
    client, sent = echo
    client.answer = lambda request: httpx.Response(200, json={"awb": "1411232210", "phone": "9864012345"})
    assert client.request("POST", "/orders/create?x=1", operation="create_order", json=ORDER)["awb"] == "1411232210"
    call = IntegrationCall.objects.get()
    assert (call.method, call.path, call.status_code, call.operation) == ("POST", "/orders/create", 200, "create_order")
    for personal in ["Rahul", "Das", "Zoo Road", "9864012345", "98640 12345", "rahul@example.com"]:
        assert personal not in call.excerpt
    assert "******2345" in call.excerpt and "r***@example.com" in call.excerpt and "PIN 781024" in call.excerpt
    assert "EL-2026-000123" in call.excerpt and "1411232210" in call.excerpt  # ids stay
    account.refresh_from_db()
    assert account.last_success_at and sent[0].url.path == "/v1/orders/create"


@pytest.mark.parametrize("status", [429, 500, 503])
def test_429_and_5xx_are_unavailable_and_counted(echo, account, status):
    client, _ = echo
    client.answer = lambda request: httpx.Response(status, json={"message": "busy"})
    with pytest.raises(IntegrationUnavailable):
        client.request("GET", "/x", operation="read")
    account.refresh_from_db()
    assert account.failure_count == 1 and account.last_error == f"HTTP {status}"


def test_no_answer_is_unavailable_and_logged_without_a_status(echo, account):
    client, _ = echo

    def down(request):
        raise httpx.ConnectTimeout("timed out", request=request)

    client.answer = down
    with pytest.raises(IntegrationUnavailable, match="ConnectTimeout"):
        client.request("GET", "/x", operation="read")
    call = IntegrationCall.objects.get()
    assert call.status_code is None and call.error == "ConnectTimeout: no answer"


def test_a_refusal_is_rejected_and_says_why_without_counting_against_the_provider(echo, account):
    client, _ = echo
    client.answer = lambda request: httpx.Response(422, json={"message": "Order id 9864012345 already exists"})
    with pytest.raises(IntegrationRejected) as refused:
        client.request("POST", "/orders/create", operation="create_order", json={})
    assert refused.value.status_code == 422 and refused.value.data["message"].startswith("Order id")
    account.refresh_from_db()
    assert account.failure_count == 0 and account.last_error == "HTTP 422: Order id ******2345 already exists"


def test_a_refused_key_is_an_authentication_failure(echo):
    client, _ = echo
    client.answer = lambda request: httpx.Response(401, json={"message": "Unauthenticated."})
    with pytest.raises(IntegrationAuthFailed):
        client.request("GET", "/x", operation="read")


def test_an_error_inside_a_200_is_a_refusal_when_the_provider_does_that(echo):
    client, _ = echo
    client.answer = lambda request: httpx.Response(200, json={"error_in_200": "Invalid Data"})
    with pytest.raises(IntegrationRejected, match="Invalid Data"):
        client.request("POST", "/all-in-one", operation="book", json={})


def test_an_open_circuit_makes_no_call(echo, account):
    client, sent = echo
    account.force_open()
    with pytest.raises(CircuitOpen):
        client.request("GET", "/x", operation="read")
    assert not sent and not IntegrationCall.objects.exists()
    client.force = True  # staff's connection test goes all the same
    assert client.request("GET", "/x", operation="test")


def test_timeouts_5_seconds_to_connect_and_20_for_the_answer_or_the_callers(echo, settings):
    client, sent = echo
    assert client.timeout() == httpx.Timeout(20, connect=5)
    client.request("GET", "/quote", operation="quote", timeout=3)
    assert sent[0].extensions["timeout"] == {"connect": 3, "read": 3, "write": 3, "pool": 3}


def test_a_file_is_described_not_copied():
    assert excerpt(b"%PDF-1.7 binary") == "[PDF, 15 bytes]"
    assert excerpt("plain text with 9864012345") == "plain text with ******2345"


def test_secrets_never_reach_the_log():
    logged = excerpt({"email": "api@examleaf.in", "password": "hunter2-hunter2", "token": "eyJhbGciOi", "id": 7})
    assert "hunter2" not in logged and "eyJ" not in logged and '"password":"[secret]"' in logged and '"id":7' in logged
