"""What the framework does for the apps that use it: the connection test of each provider, the intake of inbound
events (kept raw, deduplicated, processed by a task) and the entries of the dead-letter list."""

import hashlib
import json
import logging

from django.db import IntegrityError, transaction
from django.utils import timezone

from . import signals
from .client import IntegrationError
from .models import InboundEvent, IntegrationFailure
from .redact import redact, scrub

logger = logging.getLogger(__name__)

# Each provider's connection test: a harmless authenticated read (Shiprocket: the wallet balance) made for the account
# given, even while it is disabled or its circuit open, returning what it read in a few words. The provider's app adds
# its own (shipping/apps.py).
CONNECTION_TESTS = {}
KEPT_HEADERS = ("Content-Type", "Content-Length", "User-Agent")  # of an inbound event; never its token


def test_connection(account):
    """Run the provider's test and keep its result on the account (last_test_at, _ok, _message). Returns (ok, message);
    ok is None for a provider without a test."""
    check = CONNECTION_TESTS.get(account.provider)
    if check is None:
        ok, message = None, "No connection test for this provider yet."
    else:
        try:
            ok, message = True, check(account)
        except IntegrationError as error:
            ok, message = False, str(error)
    account.last_test_at, account.last_test_ok, account.last_test_message = timezone.now(), ok, message[:300]
    account.save(update_fields=["last_test_at", "last_test_ok", "last_test_message", "modified"])
    return ok, message


test_connection.__test__ = False  # pytest: not a test, when a test module imports it


def receive_event(provider, body, headers, account=None, rejected=False, event_id=""):
    """Keep a webhook as it came and queue its processing (InboundEvent.process_later). A body already received from
    this provider is not kept again: None; nor one whose `event_id` (the provider's own id of what it reports) was
    received. A rejected one (wrong or missing token) is kept without its body, and never processed."""
    digest = hashlib.sha256(body).hexdigest()
    kept = {name: str(headers[name])[:200] for name in KEPT_HEADERS if name in headers}
    if rejected:
        return InboundEvent.objects.create(
            provider=provider, sha256=digest, headers=kept, state=InboundEvent.State.REJECTED
        )
    try:
        with transaction.atomic():
            event = InboundEvent.objects.create(
                provider=provider,
                account=account,
                body=body.decode("utf-8", "replace"),
                sha256=digest,
                headers=kept,
                event_id=event_id[:100],
            )
    except IntegrityError:
        return None
    event.process_later()
    return event


# Phase B: the panel's keys of a provider whose environment keys give way to them (README.md "Precedence")

PANEL_MANAGED = ("razorpay", "msg91")  # the environment's keys stay in force until the panel holds some (credentials/)


def panel_keys(provider):
    """The keys the panel holds for `provider` (one of PANEL_MANAGED), read through the shared cache (ciphertexts only:
    decrypted here), forgotten at every change of one of its accounts (models.forget_panel_keys):
    - None while no account of the provider holds credentials: the environment's keys apply (RAZORPAY_*, MSG91_*);
    - {} once one does, while none of them is enabled: the provider is switched off in the panel;
    - else {"mode", "credentials", "webhook_secrets"} of the enabled account (the webhook's current secret and, for 24
      hours after a rotation, the previous one)."""
    from django.core.cache import cache

    from . import crypto
    from .models import PANEL_KEYS, PREVIOUS_WEBHOOK_TOKEN, IntegrationAccount

    key = PANEL_KEYS.format(provider=provider)
    state = cache.get(key)
    if state is None:
        accounts = IntegrationAccount.objects.filter(provider=provider).exclude(credentials="")
        enabled = accounts.filter(enabled=True).first()
        state = {"managed": accounts.exists(), "account": None}
        if enabled is not None:
            state["account"] = {
                "mode": enabled.mode,
                "credentials": enabled.credentials,
                "webhook_token": enabled.webhook_token,
                "previous_webhook_token": enabled.previous_webhook_token,
                "rotated_at": enabled.webhook_rotated_at,
            }
        cache.set(key, state, 60)
    if not state["managed"]:
        return None
    account = state["account"]
    if account is None:
        return {}
    secrets = [crypto.decrypt(account["webhook_token"])] if account["webhook_token"] else []
    recent = account["rotated_at"] and timezone.now() - account["rotated_at"] < PREVIOUS_WEBHOOK_TOKEN
    if account["previous_webhook_token"] and recent:
        secrets.append(crypto.decrypt(account["previous_webhook_token"]))
    return {
        "mode": account["mode"],
        "credentials": json.loads(crypto.decrypt(account["credentials"])),
        "webhook_secrets": secrets,
    }


def dead_letter(task_name, task_id, error, args, kwargs, attempts=1, operation=None):
    """A task that gave up, in the dead-letter list (once per task run) with its arguments redacted; the staff inbox is
    told (dead_letter_created). `operation`: what it was doing, when the task's own name does not say it (the erp
    app's replay task, for the ERPNext method a dead outbox row was for)."""
    arguments = json.loads(json.dumps({"args": list(args or []), "kwargs": dict(kwargs or {})}, default=str))
    failure, created = IntegrationFailure.objects.get_or_create(
        task_id=task_id or None,
        defaults={
            "account": getattr(error, "account", None),
            "operation": (operation or task_name.rsplit(".", 1)[-1])[:60],
            "task_name": task_name,
            "args": redact(arguments),
            "attempts": attempts,
            "last_error": scrub(f"{type(error).__name__}: {error}")[:500],
        },
    )
    if created:
        logger.error("%s gave up after %s tries: dead letter #%s", task_name, attempts, failure.pk)
        transaction.on_commit(
            lambda: signals.dead_letter_created.send(sender=IntegrationFailure, failure=failure), robust=True
        )
    return failure
