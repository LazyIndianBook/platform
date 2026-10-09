"""API keys for integrations (research 2.6): shown once and kept as a hash, holding view permissions only, until
they expire or are revoked, optionally from some addresses; never a re-authentication, never the panel's manifest."""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts import roles
from shop.factories import ProductFactory, make_order
from shop.models import Order
from staff.models import ApiKey

from .conftest import STAFF, events, make_staff, signed_in

pytestmark = pytest.mark.django_db
KEYS = STAFF + "api-keys/"


def make_key(owner, **body):
    return signed_in(owner).post(KEYS, {"name": "Shiprocket", "scopes": ["shop.view_order"], **body}, format="json")


def keyed(key, **extra):
    client = APIClient(**extra)
    client.credentials(HTTP_AUTHORIZATION=f"Api-Key {key}")
    return client


def test_a_key_is_shown_once_kept_as_a_hash_and_its_making_alerts_the_owners():
    owner = make_staff(roles.OWNER)
    response = make_key(owner)
    assert response.status_code == 201, response.content
    data = response.json()
    key = data["key"]
    assert key.startswith(f"elk_{data['prefix']}_") and len(key) > 40
    row = ApiKey.objects.get()
    assert key not in row.secret_hash and len(row.secret_hash) == 64 and row.sponsor == owner
    assert row.expires_at - timezone.now() > timedelta(days=364)  # 12 months unless given
    assert signed_in(owner).get(f"{KEYS}{row.pk}/").json()["key"] is None  # never again
    created = events("authn_token_created").get()
    assert created.details["scopes"] == ["shop.view_order"] and key not in str(created.details)
    assert signed_in(make_staff(roles.ADMIN)).get(KEYS).status_code == 200  # ADMIN sees them, OWNER makes them
    assert make_key(make_staff(roles.ADMIN)).status_code == 403


def test_a_key_holds_view_permissions_only_and_only_its_makers():
    owner = make_staff(roles.OWNER)
    assert make_key(owner, scopes=["staff.refund_order"]).status_code == 400  # a key never acts on money
    assert make_key(owner, scopes=["shop.change_order"]).status_code == 400
    assert make_key(owner, scopes=[]).status_code == 400
    assert make_key(owner, expires_at=(timezone.now() + timedelta(days=400)).isoformat()).status_code == 400
    assert make_key(owner, allowed_ips=["not-an-address"]).status_code == 400


def test_a_key_reads_what_its_permissions_allow_and_nothing_else():
    order = make_order((ProductFactory(), 1))
    key = make_key(make_staff(roles.OWNER), scopes=["accounts.view_user", "shop.view_order"]).json()["key"]
    client = keyed(key)
    assert client.get(STAFF + "users/").status_code == 200  # accounts.view_user
    assert client.get(STAFF + "inbox/").status_code == 403  # not one of its permissions
    assert client.get(STAFF + "session/").status_code == 403  # the manifest is for people
    assert client.post(STAFF + "users/1/unlock/").status_code == 403
    row = ApiKey.objects.get()
    assert row.last_used_at and row.last_used_ip == "127.0.0.1"
    denied = events("authz_fail", actor_type="service").first()
    assert denied.actor_id == row.pk and denied.actor_roles == ["INTEGRATION"]
    assert Order.objects.filter(pk=order.pk).exists()


def test_a_key_stops_when_revoked_or_expired_or_from_another_address():
    owner = make_staff(roles.OWNER)
    key = make_key(owner, scopes=["accounts.view_user"], allowed_ips=["10.0.0.0/8"]).json()["key"]
    assert keyed(key, REMOTE_ADDR="10.1.2.3").get(STAFF + "users/").status_code == 200
    assert keyed(key, REMOTE_ADDR="203.0.113.5").get(STAFF + "users/").status_code == 401
    assert keyed(key[:-2] + "xx", REMOTE_ADDR="10.1.2.3").get(STAFF + "users/").status_code == 401  # forged
    ApiKey.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    assert keyed(key, REMOTE_ADDR="10.1.2.3").get(STAFF + "users/").status_code == 401
    ApiKey.objects.update(expires_at=timezone.now() + timedelta(days=1))
    revoked = signed_in(owner).post(f"{KEYS}{ApiKey.objects.get().pk}/revoke/").json()
    assert revoked["revoked_at"] and events("authn_token_revoked").exists()
    assert keyed(key, REMOTE_ADDR="10.1.2.3").get(STAFF + "users/").status_code == 401


def test_a_key_whose_secret_holds_underscores_works(monkeypatch):
    from staff import permissions

    monkeypatch.setattr(permissions.secrets, "token_urlsafe", lambda size: "a_b_c-" + "x" * 37)
    key = make_key(make_staff(roles.OWNER), scopes=["accounts.view_user"]).json()["key"]
    assert key.count("_") == 4 and keyed(key).get(STAFF + "users/").status_code == 200  # two of them the secret's
