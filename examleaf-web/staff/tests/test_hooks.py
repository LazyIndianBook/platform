"""The inbound hooks (/api/hooks/: the couriers', MSG91's, the support mailbox's, ERPNext's; plan 9.2's exit criteria):
each compares its token or signature in constant time (hmac.compare_digest), takes the previous one only within its
24 hours' overlap after a rotation, keeps a replayed event once, refuses an oversized body (Caddy's 10 MB, then
Django's own limit, smaller) and answers a malformed one without an exception leaking into the answer."""

import base64
import hashlib
import hmac
import json
from datetime import timedelta

import pytest
from django.conf import settings as django_settings
from django.utils import timezone
from rest_framework.test import APIClient

from integrations.models import InboundEvent, IntegrationAccount

pytestmark = pytest.mark.django_db
MAIL = b"From: Rahul Das <rahul@example.com>\r\nTo: help@examleaf.in\r\nSubject: My parcel\r\n"
MAIL += b"Message-ID: <1@mail>\r\n\r\nIt has not come.\r\n"
HOOKS = {  # the hook: its provider, how it is called, a body it takes
    "parcel-events": {"provider": "shiprocket", "mode": "test", "header": "HTTP_X_API_KEY",
                      "type": "application/json", "body": b'{"awb": "EA123456789IN", "current_status": "PICKED UP"}'},
    "sms-events": {"provider": "msg91", "mode": "live", "header": "HTTP_X_WEBHOOK_TOKEN", "type": "application/json",
                   "body": json.dumps([{"requestId": "5f1a2b3c4d5e6f7a8b9c0d1e",
                                        "report": [{"number": "919864012345", "status": "1", "desc": "Delivered"}]}
                                       ]).encode()},
    "support-mail": {"provider": "support_mail", "mode": "live", "header": "HTTP_X_SUPPORT_MAIL_TOKEN",
                     "type": "message/rfc822", "body": MAIL},
    "erp-events": {"provider": "erpnext", "mode": "test", "header": None, "type": "application/json",
                   "body": b'{"doctype": "Sales Invoice", "name": "ACC-SINV-2026-00001", "event": "on_update"}'},
}  # fmt: skip


@pytest.fixture
def hooks(settings, monkeypatch):
    settings.ERP_ENABLED = True  # (ERPNext's doorbells are refused while the sync is off)
    monkeypatch.setattr(InboundEvent, "process_later", lambda self: None)  # kept, not processed: nothing leaves


def account_of(hook):
    spec = HOOKS[hook]
    account = IntegrationAccount.objects.create(provider=spec["provider"], mode=spec["mode"], enabled=True)
    return account, account.rotate_webhook_token()


def call(hook, token, body=None):
    spec, body = HOOKS[hook], HOOKS[hook]["body"] if body is None else body
    if spec["header"]:
        headers = {spec["header"]: token}
    else:  # ERPNext signs the body with the secret (erp.inbound.signed)
        signature = base64.b64encode(hmac.new(token.encode(), body, hashlib.sha256).digest()).decode()
        headers = {"HTTP_X_FRAPPE_WEBHOOK_SIGNATURE": signature}
    return APIClient().post(f"/api/hooks/{hook}/", body, content_type=spec["type"], **headers)


def kept(hook):
    return InboundEvent.objects.filter(provider=HOOKS[hook]["provider"]).exclude(state=InboundEvent.State.REJECTED)


@pytest.mark.parametrize("hook", HOOKS)
def test_a_hook_compares_in_constant_time_and_takes_the_previous_token_only_within_its_overlap(
    hook, hooks, monkeypatch
):
    account, first = account_of(hook)
    compared = []
    real = hmac.compare_digest
    monkeypatch.setattr(hmac, "compare_digest", lambda a, b: compared.append(1) or real(a, b))
    assert call(hook, "not-the-token").status_code == 403 and compared  # compared, in constant time
    assert not kept(hook).exists()  # a refused one is kept without its body, never processed
    second = account.rotate_webhook_token()
    another = HOOKS[hook]["body"]  # another event, of the same shape
    for old, new in [(b"5f1a2b", b"6a2b3c"), (b"<1@mail>", b"<2@mail>"), (b"0001", b"0002")]:
        another = another.replace(old, new)
    another = another.replace(b"EA123456789IN", b"EA987654321IN")
    assert call(hook, second).status_code == 200 and call(hook, first, body=another).status_code == 200
    IntegrationAccount.objects.filter(pk=account.pk).update(webhook_rotated_at=timezone.now() - timedelta(hours=25))
    assert call(hook, first).status_code == 403  # the overlap is over: the previous token is no more


@pytest.mark.parametrize("hook", HOOKS)
def test_a_replayed_event_is_kept_once(hook, hooks):
    _, token = account_of(hook)
    assert call(hook, token).status_code == 200 and call(hook, token).status_code == 200
    assert kept(hook).count() == 1


@pytest.mark.parametrize("hook", HOOKS)
def test_an_oversized_body_is_refused_and_a_malformed_one_leaks_nothing(hook, hooks, settings):
    _, token = account_of(hook)
    settings.DATA_UPLOAD_MAX_MEMORY_SIZE = settings.SUPPORT_MAIL_MAX_BYTES = 1000  # (Django's own limits, smaller)
    big = call(hook, token, body=b"x" * 2000)
    assert big.status_code == 413 and not kept(hook).exists(), big.content[:200]
    settings.DATA_UPLOAD_MAX_MEMORY_SIZE = settings.SUPPORT_MAIL_MAX_BYTES = 10 * 1024 * 1024
    for garbage in [b"\xff\xfe\x00 not a body", b"[[[", b'{"report": 7}']:
        answer = call(hook, token, body=garbage)
        assert answer.status_code < 500, (garbage, answer.status_code)
        assert set(answer.json()) <= {"detail", "code"} and b"Traceback" not in answer.content  # its words only


def test_caddy_caps_every_hooks_body_and_djangos_limits_sit_under_it():
    caddy = (django_settings.BASE_DIR / "Caddyfile").read_text()
    assert "@other not path /admin/learn/clip/* /admin/learn/revision/*" in caddy  # /api/hooks/ is "other"
    assert "request_body @other {\n\t\tmax_size 10MB" in caddy
    cap = 10 * 1024 * 1024
    assert django_settings.DATA_UPLOAD_MAX_MEMORY_SIZE <= cap and django_settings.SUPPORT_MAIL_MAX_BYTES <= cap
