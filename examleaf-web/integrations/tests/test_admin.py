"""The integrations' admin: every page opens, credentials are written and never shown, the actions (connection test,
webhook token shown once, circuit held open and reset, dead letters discarded and replayed, events processed again)."""

import json

import pytest
from django.urls import reverse

from accounts.factories import UserFactory
from integrations import services
from integrations.models import InboundEvent, IntegrationAccount, IntegrationCall, IntegrationFailure

pytestmark = pytest.mark.django_db
SECRET = "correct-horse-battery-staple"


@pytest.fixture
def admin_client(client):
    client.force_login(UserFactory(is_staff=True, is_superuser=True))
    return client


@pytest.fixture
def rows(account):
    account.set_credentials({"email": "api@examleaf.in", "password": SECRET})
    account.save()
    IntegrationCall.objects.create(account=account, operation="track", method="GET", path="/courier/track/awb/1")
    failure = IntegrationFailure.objects.create(
        account=account, operation="refused", task_name="integrations.tests.test_failures.refused", last_error="e"
    )
    event = InboundEvent.objects.create(provider="shiprocket", account=account, sha256="b" * 64, state="failed")
    return account, failure, event


def test_every_page_opens_and_the_records_cannot_be_changed(admin_client, rows):
    for model in [IntegrationAccount, IntegrationCall, IntegrationFailure, InboundEvent]:
        base = f"admin:integrations_{model._meta.model_name}"
        row = model.objects.first()
        editable = model is IntegrationAccount
        for url, expected in [
            (reverse(f"{base}_changelist"), 200),
            (reverse(f"{base}_changelist") + "?q=a&o=1", 200),
            (reverse(f"{base}_add"), 200 if editable else 403),
            (reverse(f"{base}_change", args=[row.pk]), 200),
            (reverse(f"{base}_history", args=[row.pk]), 200),
            (reverse(f"{base}_delete", args=[row.pk]), 200 if editable else 403),
        ]:
            assert admin_client.get(url).status_code == expected, url


def test_credentials_are_written_and_never_shown(admin_client, account):
    url = reverse("admin:integrations_integrationaccount_change", args=[account.pk])
    data = {"provider": "shiprocket", "mode": "test", "label": "API user", "enabled": "on", "scopes": "[]"}
    data["where_else_configured"], data["rotate_by"] = "", ""
    response = admin_client.post(url, {**data, "new_credentials": "not json"})
    assert "This is not JSON" in response.content.decode()
    new = json.dumps({"email": "api@examleaf.in", "password": SECRET})
    assert admin_client.post(url, {**data, "new_credentials": new}).status_code == 302
    account.refresh_from_db()
    assert account.get_credentials()["password"] == SECRET and SECRET not in account.credentials
    assert account.credentials_updated_by.is_superuser and account.rotate_by
    page = admin_client.get(url).content.decode()
    assert SECRET not in page and "…aple" in page
    admin_client.post(url, {**data, "new_credentials": ""})  # left empty: kept
    account.refresh_from_db()
    assert account.get_credentials()["password"] == SECRET


def act(client, model, action, objects, **data):
    url = reverse(f"admin:integrations_{model}_changelist")
    return client.post(url, {"action": action, "_selected_action": [o.pk for o in objects], **data}, follow=True)


def test_connection_test_webhook_token_and_circuit_actions(admin_client, account, monkeypatch):
    monkeypatch.setitem(services.CONNECTION_TESTS, "shiprocket", lambda account: "wallet balance ₹1,250.00")
    response = act(admin_client, "integrationaccount", "run_connection_test", [account])
    assert "wallet balance ₹1,250.00" in response.content.decode()
    account.refresh_from_db()
    assert account.last_test_ok and account.last_test_message == "wallet balance ₹1,250.00"
    page = act(admin_client, "integrationaccount", "new_webhook_token", [account]).content.decode()
    account.refresh_from_db()
    token = page.split("<code>")[2].split("</code>")[0]  # the first <code> is the webhook's address
    assert (
        account.webhook_token_matches(token)
        and token
        not in admin_client.get(
            reverse("admin:integrations_integrationaccount_change", args=[account.pk])
        ).content.decode()
    )
    act(admin_client, "integrationaccount", "hold_circuit_open", [account])
    account.refresh_from_db()
    assert account.held_open and not account.allows_call()
    act(admin_client, "integrationaccount", "reset_circuit", [account])
    account.refresh_from_db()
    assert account.circuit_state == "closed" and account.allows_call()


def test_dead_letters_are_discarded_with_a_reason_and_events_processed_again(admin_client, rows, monkeypatch):
    _, failure, event = rows
    page = act(admin_client, "integrationfailure", "discard", [failure]).content.decode()
    assert "Discard dead letters" in page  # the reason first
    act(admin_client, "integrationfailure", "discard", [failure], apply="1", reason="Booked by hand.")
    failure.refresh_from_db()
    assert failure.state == "discarded" and failure.discard_reason == "Booked by hand."
    queued = []
    monkeypatch.setattr(InboundEvent, "process_later", lambda self: queued.append(self.pk))
    act(admin_client, "inboundevent", "replay", [event])
    event.refresh_from_db()
    assert event.state == "accepted" and queued == [event.pk]
