"""What the connections page knows of each integration (plan 5.18; research-integrations 5.2): its card (is it working,
since when, test or live, what it holds, how its calls went), its connection test (one harmless authenticated read,
through the integrations client or a logged boto3 call: the call log, the circuit, the result kept on its account), its
credentials (replaced only after a test of the new ones passes in the same call; never shown, only their last four
characters), its mode (off, test, live: an account per mode), its circuit (held open, or reset) and its webhooks (our
address, the token rotated with the previous one accepted for 24 hours, the events of the week, a silence alarm).

Where the keys live (README.md "Precedence"): Shiprocket's and ERPNext's in their IntegrationAccounts only; Razorpay's
and MSG91's in the environment until the panel holds some (services.panel_keys: an account with credentials), then the
enabled account's; SES's, the buckets', Google's and the error tracker's in the environment only (their libraries read
the settings at start), so the card says so and Replace is refused with the way to do it (RUNBOOK.md)."""

import base64
import json
import math
import time
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Max, Q
from django.utils import timezone
from rest_framework import exceptions, serializers

from . import crypto
from .client import Client, IntegrationAuthFailed, IntegrationError, IntegrationRejected, IntegrationUnavailable
from .models import (
    PREVIOUS_WEBHOOK_TOKEN,
    InboundEvent,
    IntegrationAccount,
    IntegrationCall,
    IntegrationFailure,
    forget_panel_keys,
    mask,
)
from .models import PROVIDERS as NAMES
from .redact import scrub
from .services import CONNECTION_TESTS, PANEL_MANAGED, test_connection

STATUSES = ["connected", "degraded", "expired", "disabled", "not_configured"]
MODES = ["off", "test", "live"]
SOURCES = ["panel", "environment", "none"]  # where its keys are read from
ERROR_SHARE, ERROR_FLOOR = 0.2, 5  # degraded: a fifth of the day's calls failed, of 5 calls at least
SMS_TOKEN_HEADER = "X-Webhook-Token"  # MSG91's delivery reports carry our secret in this header (ops/webhooks.py)


@dataclass(frozen=True)
class Provider:
    key: str
    kind: str  # payments, shipping, sms, whatsapp, email, storage, errors, sign_in, erp
    fields: tuple = ()  # the credentials the panel takes (empty: they stay in the environment)
    optional: tuple = ()
    modes: tuple = ("test", "live")  # empty: no mode to switch here
    webhook: dict = field(default_factory=dict)  # {"path", "auth", "header"}: where and how it calls us
    overlap: str = ""  # the written warning where a new key stops the old one at once
    circuit: bool = False  # its calls go through the integrations client, so through its circuit breaker


PROVIDERS = [  # the cards, in the page's order
    Provider(
        "razorpay",
        "payments",
        ("key_id", "key_secret"),
        webhook={"path": "/shop/webhooks/razorpay/", "auth": "signature", "header": "X-Razorpay-Signature"},
        overlap="Razorpay may stop a regenerated key's predecessor at once (or after 24 hours): replace it here in the "
        "same minute you regenerate it, and paste the webhook secret in Razorpay's dashboard when you rotate it.",
    ),
    Provider(
        "shiprocket",
        "shipping",
        ("email", "password"),
        webhook={"path": "/api/hooks/parcel-events/", "auth": "token", "header": "x-api-key"},
        circuit=True,
    ),
    Provider("manual", "shipping", modes=()),
    Provider(
        "msg91",
        "sms",
        ("authkey",),
        modes=("live",),
        webhook={"path": "/api/hooks/sms-events/", "auth": "token", "header": SMS_TOKEN_HEADER},
    ),
    Provider("whatsapp", "whatsapp", modes=()),
    Provider(
        "ses",
        "email",
        modes=(),
        webhook={"path": "/anymail/amazon_ses/tracking/", "auth": "basic_and_sns", "header": "Authorization"},
    ),
    Provider(
        "storage",
        "storage",
        modes=(),
        overlap="Rolling an R2 token stops it at once: make a second token, put it in the environment, then delete the "
        "first.",
    ),
    Provider("error_tracker", "errors", modes=()),
    Provider("google", "sign_in", modes=()),
    Provider(
        "erpnext",
        "erp",
        ("api_key", "api_secret", "base_url"),
        optional=("site_name",),
        webhook={"path": "/api/hooks/erp-events/", "auth": "signature", "header": "X-Frappe-Webhook-Signature"},
        overlap="Generating a new API secret for the sync user in ERPNext stops the old one at once: replace it here "
        "in the same minute.",
        circuit=True,
    ),
]
SPEC = {provider.key: provider for provider in PROVIDERS}
KINDS = sorted({provider.kind for provider in PROVIDERS})
PANEL_ONLY = ("shiprocket", "erpnext")  # their keys are the panel's alone
# The dead letters of a provider whose task failed before it knew its account (an error that is no IntegrationError)
TASK_PREFIXES = {"shiprocket": "shipping.", "erpnext": "erp.", "msg91": "ops."}


def refused(message, name="non_field_errors"):
    return serializers.ValidationError({name: [message]})


def provider_or_404(key):
    if key not in SPEC:
        raise exceptions.NotFound("No such connection.")
    return SPEC[key]


def name_of(key):
    return {**NAMES, "manual": "Manual carrier (India Post and others)", "whatsapp": "WhatsApp (MSG91)"}.get(key, key)


def by_id(user):
    return f"user #{user.pk}" if getattr(user, "pk", None) else "an API key"


# The environment's side: what settings.py configures for each provider (never a value: its last four characters)


def _s3_storages():
    """[(alias, bucket, storage)] of the S3 buckets in use (MEDIA_BUCKET, PUBLIC_MEDIA_BUCKET, BACKUP_BUCKET)."""
    from django.core.files.storage import storages

    found = []
    for alias in ("default", "public", "backups"):
        options = settings.STORAGES.get(alias, {})
        if options.get("BACKEND", "").endswith("S3Storage"):
            found.append((alias, options["OPTIONS"].get("bucket_name", ""), storages[alias]))
    return found


def environment(key):
    """{configured, mode (off, test, live), held: {name: its last four characters}} of the environment's settings."""
    if key == "razorpay":
        key_id, secret = settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET
        mode = "off" if not (key_id and secret) else "test" if key_id.startswith("rzp_test_") else "live"
        return {"configured": mode != "off", "mode": mode, "held": {"key_id": mask(key_id), "key_secret": mask(secret)}}
    if key == "msg91":
        on = settings.SMS_BACKEND == "msg91" and bool(settings.MSG91_AUTHKEY)
        return {"configured": on, "mode": "live" if on else "off", "held": {"authkey": mask(settings.MSG91_AUTHKEY)}}
    if key == "ses":
        on = "amazon_ses" in settings.MAILERS["default"]["BACKEND"]
        access = settings.ANYMAIL.get("AMAZON_SES_CLIENT_PARAMS", {}).get("aws_access_key_id", "")
        held = {"access_key_id": mask(access)} if access else {}
        return {"configured": on, "mode": "live" if on else "off", "held": held}
    if key == "storage":
        buckets = _s3_storages()
        access = settings.STORAGES.get("default", {}).get("OPTIONS", {}).get("access_key") or ""
        held = {"access_key": mask(access)} if access else {}
        return {"configured": bool(buckets), "mode": "live" if buckets else "off", "held": held}
    if key == "error_tracker":
        dsn = getattr(settings, "SENTRY_DSN", "")
        return {"configured": bool(dsn), "mode": "live" if dsn else "off", "held": {"dsn": mask(dsn)} if dsn else {}}
    if key == "google":
        website = bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET)
        staff = bool(settings.STAFF_GOOGLE_CLIENT_ID and settings.STAFF_GOOGLE_CLIENT_SECRET)
        held = {}
        if website:
            held["client_id"] = mask(settings.GOOGLE_CLIENT_ID)
        if staff:
            held["staff_client_id"] = mask(settings.STAFF_GOOGLE_CLIENT_ID)
        return {"configured": website or staff, "mode": "live" if website or staff else "off", "held": held}
    return {"configured": False, "mode": "off", "held": {}}


def env_credentials(key):
    """The environment's keys of a provider the panel may take over (for its test while they are in force)."""
    if key == "razorpay":
        return {"key_id": settings.RAZORPAY_KEY_ID, "key_secret": settings.RAZORPAY_KEY_SECRET}
    if key == "msg91":
        return {"authkey": settings.MSG91_AUTHKEY}
    return {}


def env_webhook_secret(key, mode):
    """The environment's webhook secret of a provider the panel takes over, for the mode (kept when it does)."""
    if key == "razorpay":
        return settings.RAZORPAY_WEBHOOK_SECRET_TEST if mode == "test" else settings.RAZORPAY_WEBHOOK_SECRET
    return ""


# The tests: one harmless authenticated read each (CONNECTION_TESTS: Shiprocket's and ERPNext's are their apps')


def transport_for(provider):
    """The HTTP transport of a test's client: the network (the tests put a recorded answer here)."""
    return None


class RazorpayClient(Client):
    """Razorpay's REST API with a pair of keys (HTTP Basic), for the connection test only (the shop uses the SDK)."""

    base_url = "https://api.razorpay.com/v1"

    def __init__(self, account, key_id, key_secret, **kwargs):
        super().__init__(account, **kwargs)
        self.basic = base64.b64encode(f"{key_id}:{key_secret}".encode()).decode()

    def headers(self):
        return {"Authorization": f"Basic {self.basic}"}

    def request_id(self, response):
        return response.headers.get("x-razorpay-request-id", "")


def keys_in_force(account):
    """The keys a provider's test reads with: its account's when it holds some, else the environment's."""
    return account.get_credentials() if account.credentials else env_credentials(account.provider)


def razorpay_test(account, credentials=None):
    """Razorpay: one payment read (`GET /payments?count=1`), with the keys given or those in force."""
    keys = credentials or keys_in_force(account)
    key_id = keys.get("key_id", "")
    client = RazorpayClient(
        account, key_id, keys.get("key_secret", ""), transport=transport_for("razorpay"), force=True
    )
    data = client.request("GET", "/payments", operation="payments", params={"count": 1}) or {}
    mode = "test" if key_id.startswith("rzp_test_") else "live"
    count = len(data.get("items") or []) if isinstance(data, dict) else 0
    return f"Connected with the {mode} keys: Razorpay answered ({count} payment read)."


class Msg91Client(Client):
    base_url = "https://control.msg91.com/api"


def msg91_test(account, credentials=None):
    """MSG91: the SMS balance of the transactional route (its key in the query, which the call log never keeps)."""
    keys = credentials or keys_in_force(account)
    client = Msg91Client(account, transport=transport_for("msg91"), force=True)
    params = {"authkey": keys.get("authkey", ""), "type": "4"}
    response = client.request("GET", "/balance.php", operation="balance", params=params, raw=True)
    text = response.text.strip()
    try:
        balance = Decimal(text)
    except InvalidOperation:
        account.record_error(f"balance: {scrub(text)[:200]}")
        raise IntegrationRejected(f"MSG91 refused: {scrub(text)[:200]}", account=account) from None
    return f"Connected: {balance:,.0f} SMS credits left on the transactional route."


def logged_call(account, operation, path, call):
    """A boto3 call (SES, the buckets) as the integrations client makes its own: logged (IntegrationCall), counted by
    the account's circuit, and its failure one of the client's three. Returns its answer."""
    from botocore.exceptions import BotoCoreError, ClientError

    log = IntegrationCall(account=account, operation=operation[:60], method="GET", path=path[:300])
    started = time.monotonic()

    def done(status, problem="", request_id=""):
        log.status_code, log.error = status, problem[:500]
        log.duration_ms, log.provider_request_id = int((time.monotonic() - started) * 1000), request_id[:100]
        log.save()

    try:
        answer = call()
    except ClientError as error:
        meta = error.response.get("ResponseMetadata", {})
        status = meta.get("HTTPStatusCode") or 400
        problem = f"HTTP {status}: {error.response.get('Error', {}).get('Code', 'refused')}"
        done(status, problem, meta.get("RequestId", ""))
        if status == 429 or status >= 500:
            account.record_failure(problem)
            raise IntegrationUnavailable(f"{account} {operation}: {problem}", account=account) from error
        account.record_success(answered_only=True)
        account.record_error(problem)
        failure = IntegrationAuthFailed if status in (401, 403) else IntegrationRejected
        raise failure(f"{account} {operation}: {problem}", account=account, status_code=status) from error
    except (BotoCoreError, OSError, ValueError) as error:  # unreachable, no keys, a malformed endpoint
        problem = f"{type(error).__name__}: no answer"
        done(None, problem)
        account.record_failure(problem)
        raise IntegrationUnavailable(f"{account} {operation}: {problem}", account=account) from error
    meta = (answer.get("ResponseMetadata") or {}) if isinstance(answer, dict) else {}
    done(meta.get("HTTPStatusCode") or 200, "", meta.get("RequestId", ""))
    account.record_success()
    return answer


def ses_client():
    """boto3's SES v2 client with anymail's parameters (region, keys, the timeouts of settings.py)."""
    import boto3
    from botocore.config import Config

    params = dict(settings.ANYMAIL.get("AMAZON_SES_CLIENT_PARAMS", {}))
    config = params.pop("config", {})
    kept = {
        name: params[name] for name in ("region_name", "aws_access_key_id", "aws_secret_access_key") if name in params
    }
    return boto3.session.Session().client("sesv2", config=Config(**config), **kept)


def ses_test(account, credentials=None):
    """SES: the account's sending quota (sesv2 GetAccount), and whether it is out of the sandbox."""
    answer = logged_call(account, "get_account", "sesv2/account", lambda: ses_client().get_account())
    quota = answer.get("SendQuota") or {}
    where = "in production" if answer.get("ProductionAccessEnabled") else "still in the SES sandbox"
    sent, most = quota.get("SentLast24Hours", 0), quota.get("Max24HourSend", 0)
    return f"Connected, {where}: {sent:,.0f} of {most:,.0f} emails sent in the last 24 hours."


def head_bucket(storage, bucket):
    return storage.connection.meta.client.head_bucket(Bucket=bucket)


def storage_test(account, credentials=None):
    """The buckets: each one's head (HeadBucket), the private, public and backups buckets in use."""
    buckets = _s3_storages()
    if not buckets:
        raise IntegrationRejected("No bucket is set (MEDIA_BUCKET, BACKUP_BUCKET).", account=account)
    for alias, bucket, storage in buckets:
        logged_call(account, f"head_bucket {alias}", bucket, lambda s=storage, b=bucket: head_bucket(s, b))
    return f"Connected: {', '.join(bucket for _, bucket, _ in buckets)} answered."


def google_test(account, credentials=None):
    """Google sign-in: its clients are set (a sign-in itself is the only full test: a person's, at /sign-in/)."""
    found = environment("google")
    if not found["configured"]:
        raise IntegrationRejected(
            "No Google client is set (GOOGLE_CLIENT_ID, STAFF_GOOGLE_CLIENT_ID).", account=account
        )
    parts = [
        "the website's client" if "client_id" in found["held"] else "",
        "the staff's client" if "staff_client_id" in found["held"] else "",
    ]
    domain = f"; staff sign in with @{settings.STAFF_GOOGLE_DOMAIN} only" if settings.STAFF_GOOGLE_DOMAIN else ""
    return f"Set: {' and '.join(part for part in parts if part)}{domain}."


def error_tracker_test(account, credentials=None):
    """The error tracker: its DSN is set (its host named; events are sent by the SDK, never by a test)."""
    dsn = getattr(settings, "SENTRY_DSN", "")
    if not dsn:
        raise IntegrationRejected("No DSN is set (SENTRY_DSN): errors are not reported.", account=account)
    return f"Set: errors go to {urlsplit(dsn).hostname}."


def shiprocket_trial(account, credentials):
    """Shiprocket with new credentials: their own log-in (no shared token, no lock) and the wallet balance."""
    from shipping.carriers.shiprocket import ShiprocketCarrier, ShiprocketClient, decimal

    transport = ShiprocketCarrier.test_transport() if account.mode == account.Mode.TEST else transport_for("shiprocket")
    client = ShiprocketClient(account, transport=transport, force=True)
    login = {"email": credentials.get("email", ""), "password": credentials.get("password", "")}
    data = client.request("POST", "/auth/login", operation="login", json=login, auth=False) or {}
    if not data.get("token"):
        raise IntegrationAuthFailed(f"{account} login: no token in the answer", account=account)
    client.headers = lambda: {"Authorization": f"Bearer {data['token']}"}
    balance = client.request("GET", "/account/details/wallet-balance", operation="wallet_balance") or {}
    return f"Connected: wallet balance ₹{decimal((balance.get('data') or {}).get('balance_amount')):,.2f}."


def erpnext_trial(account, credentials):
    """ERPNext with new credentials: examleaf_erp's ping (the account given holds them, unsaved: erp.client reads them
    from it)."""
    from erp.client import connection_test

    return connection_test(account)


CONNECTION_TESTS.update(
    razorpay=razorpay_test,
    msg91=msg91_test,
    ses=ses_test,
    storage=storage_test,
    google=google_test,
    error_tracker=error_tracker_test,
)
TRIALS = {"razorpay": razorpay_test, "msg91": msg91_test, "shiprocket": shiprocket_trial, "erpnext": erpnext_trial}


# The cards


def call_stats(now=None):
    """{provider: {day_calls, day_errors, week_calls, week_errors, p90_ms}} of the call log: one grouped query, and
    one for each provider's p90 (the nearest rank: an offset into its week's calls by duration)."""
    now = now or timezone.now()
    day, week = now - timedelta(days=1), now - timedelta(days=7)
    failed, today = ~Q(error=""), Q(created__gte=day)
    rows = (
        IntegrationCall.objects.filter(created__gte=week)
        .values("account__provider")
        .annotate(
            week_calls=Count("pk"),
            week_errors=Count("pk", filter=failed),
            day_calls=Count("pk", filter=today),
            day_errors=Count("pk", filter=today & failed),
        )
        .order_by()
    )
    stats = {}
    for row in rows:
        provider = row.pop("account__provider")
        calls = IntegrationCall.objects.filter(account__provider=provider, created__gte=week)
        rank = max(0, math.ceil(0.9 * row["week_calls"]) - 1)
        row["p90_ms"] = calls.order_by("duration_ms").values_list("duration_ms", flat=True)[rank]
        stats[provider] = row
    return stats


def _days_until(day):
    return None if day is None else (day - timezone.localdate()).days


def account_row(account):
    """An account as the card lists it: its mode, whether it is the one in use, its credentials' last four characters,
    who set them and when, the 90-day rotation and the cached token's expiry as countdowns, its webhook token."""
    try:
        held = account.masked()
        unreadable = False
    except crypto.SecretUnreadable:
        held, unreadable = {"credentials": {}, "webhook_token": ""}, True
    token_in = account.token_expires_at - timezone.now() if account.token_expires_at else None
    return {
        "id": account.pk,
        "mode": account.mode,
        "enabled": account.enabled,
        "label": account.label,
        "held": held["credentials"],
        "unreadable": unreadable,
        "credentials_updated_at": account.credentials_updated_at,
        "credentials_updated_by": account.credentials_updated_by_id,
        "rotate_by": account.rotate_by,
        "rotate_in_days": _days_until(account.rotate_by),
        "token_expires_at": account.token_expires_at,
        "token_in_hours": None if token_in is None else round(token_in.total_seconds() / 3600, 1),
        "webhook_token": held["webhook_token"],
        "webhook_rotated_at": account.webhook_rotated_at,
    }


def _auth_failed(text):
    return "HTTP 401" in (text or "") or "HTTP 403" in (text or "")


def status_of(configured, mode, account, stats):
    """connected | degraded | expired | disabled | not_configured (research-integrations 5.2): degraded while its
    circuit is not closed, its last test failed, or a fifth of the day's calls failed; expired while the provider
    refuses its keys (401, 403) since their last success."""
    if not configured:
        return "not_configured"
    if mode == "off":
        return "disabled"
    if account is not None:
        success = account.last_success_at
        if account.circuit_state != account.Circuit.CLOSED or account.held_open:
            return "degraded"
        error_after = account.last_error_at and (success is None or account.last_error_at > success)
        if error_after and _auth_failed(account.last_error):
            return "expired"
        test_after = account.last_test_at and (success is None or account.last_test_at >= success)
        if account.last_test_ok is False and test_after:
            return "expired" if _auth_failed(account.last_test_message) else "degraded"
    day = stats.get("day_calls", 0)
    if day >= ERROR_FLOOR and stats.get("day_errors", 0) / day >= ERROR_SHARE:
        return "degraded"
    return "connected"


def card(spec, accounts, stats, now):
    """One integration's card."""
    rows = [account for account in accounts if account.provider == spec.key]
    enabled = next((account for account in rows if account.enabled), None)
    with_keys = [account for account in rows if account.credentials]
    env = environment(spec.key)
    if spec.key in PANEL_ONLY or (spec.key in PANEL_MANAGED and with_keys):
        source = "panel"
        configured, mode = bool(with_keys), enabled.mode if enabled and enabled.credentials else "off"
    elif spec.key == "manual":
        source, configured, mode = "none", True, "live"
    elif spec.key == "whatsapp":
        source, configured, mode = "none", False, "off"
    else:
        source, configured, mode = "environment", env["configured"], env["mode"]
    # the account whose test, circuit and last calls the card shows: the one in use, else the one of the mode in force
    shown = enabled or next((account for account in rows if account.mode == mode), None)
    status = "disabled" if spec.key == "whatsapp" else status_of(configured, mode, shown, stats)
    return {
        "provider": spec.key,
        "name": name_of(spec.key),
        "kind": spec.kind,
        "status": status,
        "mode": mode,
        "source": source,
        "held": env["held"] if source == "environment" else {},
        "accounts": [account_row(account) for account in rows],
        "last_success_at": shown.last_success_at if shown else None,
        "last_error_at": shown.last_error_at if shown else None,
        "last_error": shown.last_error if shown else "",
        "last_test": {
            "at": shown.last_test_at if shown else None,
            "ok": shown.last_test_ok if shown else None,
            "message": shown.last_test_message if shown else "",
        },
        "circuit": {
            "state": shown.circuit_state if shown else IntegrationAccount.Circuit.CLOSED,
            "held_open": bool(shown and shown.held_open),
            "opened_at": shown.opened_at if shown else None,
            "failures": shown.failure_count if shown else 0,
        },
        "calls": {
            "day": stats.get("day_calls", 0),
            "day_errors": stats.get("day_errors", 0),
            "week": stats.get("week_calls", 0),
            "week_errors": stats.get("week_errors", 0),
            "p90_ms": stats.get("p90_ms"),
        },
        "fields": [*spec.fields, *spec.optional],
        "optional": list(spec.optional),
        "modes": list(spec.modes),
        "overlap_warning": spec.overlap,
        "actions": {
            "test": spec.key not in ("manual", "whatsapp") and (configured or bool(with_keys)),
            "credentials": bool(spec.fields),
            "mode": bool(spec.fields and spec.modes),
            "circuit": spec.circuit and enabled is not None,
            "webhooks": bool(spec.webhook),
        },
        "extra": extra(spec.key, enabled or shown, now),
    }


def extra(key, account, now):
    """What a provider's card adds: Razorpay's webhook health, MSG91's SMS, SES's rates and suppressions, the buckets,
    Google's clients, the error tracker's host, ERPNext's sync."""
    if key == "razorpay":
        return {"webhook": razorpay_webhook_health(now)}
    if key == "msg91":
        from ops.models import MessageTemplate, SmsLog

        midnight = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
        week = SmsLog.objects.filter(created__gte=now - timedelta(days=7))
        reports = dict(week.exclude(delivery="").values_list("delivery").annotate(n=Count("pk")).order_by())
        approved = MessageTemplate.objects.filter(channel="sms", approval_state=MessageTemplate.Approval.APPROVED)
        return {
            "sms": {
                "sent_today": SmsLog.objects.filter(created__gte=midnight, status=SmsLog.Status.SENT).count(),
                "capped_today": SmsLog.objects.filter(created__gte=midnight, status=SmsLog.Status.CAPPED).count(),
                "capped_7_days": week.filter(status=SmsLog.Status.CAPPED).count(),
                "delivery_7_days": reports,
                "daily_cap": settings.SMS_DAILY_CAP,
                "templates": approved.count(),
            }
        }
    if key == "ses":
        from django.core.cache import cache

        from ops.models import EmailSuppression
        from ops.ses import SUPPRESSIONS_SYNCED
        from staff.system_api import email_rates

        return {
            "email": {
                "rates": email_rates(),
                "suppressed": EmailSuppression.objects.count(),
                "suppressions_synced": cache.get(SUPPRESSIONS_SYNCED),
                "topic_restricted": bool(settings.SES_SNS_TOPIC_ARN),
                "webhook_secret_set": bool(settings.ANYMAIL.get("WEBHOOK_SECRET")),
            }
        }
    if key == "storage":
        return {
            "storage": {
                "buckets": [{"alias": alias, "bucket": bucket} for alias, bucket, _ in _s3_storages()],
                "public_domain": settings.STORAGES.get("public", {}).get("OPTIONS", {}).get("custom_domain") or "",
            }
        }
    if key == "google":
        return {"google": {"domain": settings.STAFF_GOOGLE_DOMAIN, "auto_staff": settings.STAFF_GOOGLE_AUTO_STAFF}}
    if key == "error_tracker":
        dsn = getattr(settings, "SENTRY_DSN", "")
        return {"errors": {"host": (urlsplit(dsn).hostname or "") if dsn else ""}}
    if key == "erpnext":
        return {"erp": erp_health(account)}
    if key == "whatsapp":
        return {"phase": "D"}
    return {}


def razorpay_webhook_health(now):
    """Razorpay's webhook from our own rows (it keeps no delivery log we can read): the last event's age, the online
    payments captured in the same window, and whether it fell silent while payments came in (Razorpay disables a
    webhook after 24 hours of failures)."""
    from shop.models import Payment, WebhookEvent, live_mode

    hours = settings.INTEGRATION_WEBHOOK_SILENCE_HOURS
    since = now - timedelta(hours=hours)
    last = WebhookEvent.objects.aggregate(last=Max("received_at"))["last"]
    paid = Payment.objects.filter(
        method="razorpay", status=Payment.Status.CAPTURED, livemode=live_mode(), modified__gte=since
    ).count()
    silent = paid > 0 and (last is None or last < since)
    age = None if last is None else round((now - last).total_seconds() / 3600, 1)
    return {"last_event_at": last, "age_hours": age, "paid_in_window": paid, "window_hours": hours, "silent": silent}


def erp_health(account):
    """The ERPNext sync's health on its card (erp.tasks.status): switched on, the outbox waiting and dead, the last
    night's reconciliation, the sync user's key present, the webhook secret set."""
    from erp.tasks import status

    found = status()
    outbox = found["outbox"]
    try:
        key_present = bool(account and account.credentials and account.get_credentials().get("api_key"))
    except crypto.SecretUnreadable:
        key_present = False
    run = found["last_reconciliation"]
    return {
        "enabled": found["enabled"],
        "waiting": outbox.get("pending", 0) + outbox.get("sending", 0) + outbox.get("failed", 0),
        "dead": outbox.get("dead", 0),
        "oldest_waiting_seconds": found["oldest_waiting_seconds"],
        "last_reconciliation": run and {"date": run["date"], "state": run["state"], "differences": run["differences"]},
        "key_present": key_present,
        "webhook_secret_set": bool(account and account.webhook_token),
    }


def cards():
    """Every connection's card, in the page's order: one query for the accounts, a few for the call log and each
    provider's figures (bounded: no row is read one by one)."""
    now = timezone.now()
    accounts = list(IntegrationAccount.objects.order_by("provider", "mode"))
    stats = call_stats(now)
    return [card(spec, accounts, stats.get(spec.key, {}), now) for spec in PROVIDERS]


def one_card(key):
    spec = provider_or_404(key)
    now = timezone.now()
    accounts = list(IntegrationAccount.objects.filter(provider=spec.key).order_by("mode"))
    return card(spec, accounts, call_stats(now).get(spec.key, {}), now)


# The actions (each audited; the owners told of every change: staff.audit.alert)


def _audit(action, target, request, **kwargs):
    from staff.audit import record

    return record(action, request=request, target=target, **kwargs)


def _alert(subject, body):
    from staff.audit import alert

    alert(subject, body)


def test_account(spec):
    """The account a test reads with and keeps its result on: the one in use; else, for the environment's keys, the
    account of their mode (made for it, without credentials: the environment's keys stay in force)."""
    accounts = IntegrationAccount.objects.filter(provider=spec.key)
    if enabled := accounts.filter(enabled=True).first():
        return enabled
    with_keys = accounts.exclude(credentials="").exists()
    if spec.key in PANEL_ONLY or (spec.key in PANEL_MANAGED and with_keys):
        if with_keys:
            raise refused("No account of it is switched on: choose its mode first.")
        raise refused("Not set up: give its credentials first (Replace).")
    env = environment(spec.key)
    if not env["configured"]:
        raise refused("Not set up: there is nothing to test yet.")
    mode = env["mode"] if env["mode"] in ("test", "live") else "live"
    account, _ = IntegrationAccount.objects.get_or_create(
        provider=spec.key, mode=mode, defaults={"label": "The environment's keys"}
    )
    return account


def run_test(key, *, request=None):
    """Test a connection with the keys in force: the result kept on its account (last_test_at, _ok, _message) and in
    the audit log. Returns (account, ok, message)."""
    spec = provider_or_404(key)
    if spec.key in ("manual", "whatsapp"):
        raise refused("There is nothing to test: this connection has no API here.")
    account = test_account(spec)
    try:
        ok, message = test_connection(account)
    except crypto.SecretUnreadable:
        ok, message = False, "Its stored credentials cannot be read with INTEGRATION_KEYS: replace them (RUNBOOK.md)."
        account.last_test_at, account.last_test_ok, account.last_test_message = timezone.now(), ok, message
        account.save(update_fields=["last_test_at", "last_test_ok", "last_test_message", "modified"])
    with transaction.atomic():
        outcome = "success" if ok else "failed"
        _audit(
            "connection.tested",
            account,
            request,
            outcome=outcome,
            details={"provider": spec.key, "mode": account.mode, "ok": ok},
        )
    return account, ok, scrub(message)[:300]


def clean_credentials(spec, mode, data):
    """The credentials as the provider takes them: every required field, texts of at most 500 characters; Razorpay's
    key of the mode chosen (rzp_test_ or rzp_live_); ERPNext's base URL over https (http only for the cluster's own
    service name)."""
    if not spec.fields:
        raise refused(
            f"{name_of(spec.key)}'s keys are read from the environment: replace them there and restart (RUNBOOK.md "
            '"Secrets and key rotation").'
        )
    if mode not in spec.modes:
        raise refused(f"One of: {', '.join(spec.modes)}.", "mode")
    if not isinstance(data, dict):
        raise refused("An object of the provider's fields.", "credentials")
    clean, problems = {}, {}
    for name in [*spec.fields, *spec.optional]:
        value = data.get(name, "")
        value = value.strip() if isinstance(value, str) else value
        if not isinstance(value, str) or len(value) > 500:
            problems[name] = ["A text of at most 500 characters."]
        elif not value and name in spec.fields:
            problems[name] = ["Required."]
        elif value:
            clean[name] = value
    for name in sorted(set(map(str, data)) - {*spec.fields, *spec.optional}):
        problems[name[:40]] = ["Not a field of this provider."]
    if spec.key == "razorpay" and "key_id" in clean and not clean["key_id"].startswith(f"rzp_{mode}_"):
        problems["key_id"] = [f"A {mode} key starts rzp_{mode}_."]
    if spec.key == "erpnext" and "base_url" in clean:
        url = urlsplit(clean["base_url"])
        if url.scheme not in ("https", "http") or not url.hostname or (url.scheme == "http" and "." in url.hostname):
            problems["base_url"] = ["https://… (http:// only for the cluster's own service name)."]
    if problems:
        raise serializers.ValidationError({"credentials": problems})
    return clean


def replace_credentials(key, mode, data, *, reason, by, request=None):
    """New credentials for one mode of a provider, saved only if a test of them passes in the same call (a failure
    keeps the old ones and says why: 400). Their last four characters only, before and after, in the audit event
    (`changes`); the owners told.

    Razorpay and MSG91, whose environment keys are in force until the panel holds some: the panel's first keys must be
    of the mode in force, and take over at once (their account switched on, Razorpay's webhook secret of that mode
    carried over), so nothing stops; later keys of another mode wait for the mode switch (mode/)."""
    spec = provider_or_404(key)
    clean = clean_credentials(spec, mode, data)
    env = environment(spec.key)
    accounts = IntegrationAccount.objects.filter(provider=spec.key)
    first = spec.key in PANEL_MANAGED and not accounts.exclude(credentials="").exists()
    if first and env["configured"] and env["mode"] != mode:
        raise refused(
            f"The environment's {env['mode']} keys are in force: give the {env['mode']} keys first, so that the panel "
            f"takes over without stopping anything; the {mode} keys after that.",
            "mode",
        )
    account, _ = IntegrationAccount.objects.get_or_create(provider=spec.key, mode=mode)
    try:
        before = account.masked()["credentials"]
    except crypto.SecretUnreadable:
        before = {"stored": "unreadable"}
    trial = IntegrationAccount.objects.get(pk=account.pk)  # the new keys on a copy, never saved unless they pass
    trial.credentials, trial.token, trial.token_expires_at = crypto.encrypt(json.dumps(clean)), "", None
    try:
        message, ok = TRIALS[spec.key](trial, clean), True
    except IntegrationError as error:
        message, ok = str(error), False
    message = scrub(message)[:300]
    details = {"provider": spec.key, "mode": mode, "ok": ok}
    with transaction.atomic():
        account = IntegrationAccount.objects.select_for_update().get(pk=account.pk)
        account.last_test_at, account.last_test_ok, account.last_test_message = timezone.now(), ok, message
        if not ok:
            account.save(update_fields=["last_test_at", "last_test_ok", "last_test_message", "modified"])
            _audit("connection.credentials_refused", account, request, outcome="failed", reason=reason, details=details)
        else:
            others = accounts.filter(enabled=True).exclude(pk=account.pk)
            takes_over = first and env["configured"] and not others.exists()
            account.set_credentials(clean, by=by)
            if takes_over:
                account.enabled = True
                if not account.webhook_token and (secret := env_webhook_secret(spec.key, mode)):
                    account.webhook_token, account.webhook_rotated_at = crypto.encrypt(secret), timezone.now()
            account.save()
            after = {name: mask(value) for name, value in clean.items()}
            _audit(
                "connection.credentials_replaced",
                account,
                request,
                reason=reason,
                changes={"credentials": [before, after]},
                details={**details, "enabled": account.enabled, "took_over": takes_over},
            )
            _alert(
                f"{name_of(spec.key)}'s {mode} credentials replaced",
                f"By {by_id(by)}, after a passing test. Reason: {reason}",
            )
    if not ok:
        raise refused(f"The new credentials did not pass the test: {message}", "credentials")
    return account, message


def switch_mode(key, mode, *, reason, by, request=None):
    """Off, test or live: the account of that mode in use (its credentials needed), every other switched off; off
    switches them all off (Razorpay and MSG91 then take nothing, the panel's keys being in force). Audited, the owners
    told. Returns the account in use, None when off."""
    spec = provider_or_404(key)
    if not (spec.fields and spec.modes):
        raise refused(f"{name_of(spec.key)}'s mode is the environment's (or it has none): change it there.")
    if mode != "off" and mode not in spec.modes:
        raise refused(f"One of: off, {', '.join(spec.modes)}.", "mode")
    with transaction.atomic():
        accounts = list(IntegrationAccount.objects.select_for_update().filter(provider=spec.key))
        current = next((account for account in accounts if account.enabled), None)
        before = current.mode if current else "off"
        target = next((account for account in accounts if account.mode == mode), None)
        if mode != "off" and (target is None or not target.credentials):
            raise refused(f"Give the {mode} credentials first (Replace).", "mode")
        if before == mode:
            return target if mode != "off" else None
        if spec.key in PANEL_MANAGED and not any(account.credentials for account in accounts):
            raise refused("The environment's keys are in force: give the panel its keys first (Replace).", "mode")
        IntegrationAccount.objects.filter(provider=spec.key, enabled=True).update(enabled=False)
        if mode != "off":
            target.enabled = True
            target.save(update_fields=["enabled", "modified"])
        anchor = target if mode != "off" else current
        _audit(
            "connection.mode_changed",
            anchor,
            request,
            reason=reason,
            changes={"mode": [before, mode]},
            details={"provider": spec.key},
        )
        _alert(f"{name_of(spec.key)} switched to {mode}", f"From {before}, by {by_id(by)}. Reason: {reason}")
        forget_panel_keys(IntegrationAccount, anchor)  # an update() sends no signal
    return target if mode != "off" else None


def set_circuit(key, action, *, reason, by, request=None):
    """Hold the circuit of the account in use open (its calls wait until it is reset), or reset it (calls go through,
    the failures counted forgotten, its "unavailable" inbox item done). Audited, the owners told."""
    spec = provider_or_404(key)
    if not spec.circuit:
        raise refused(f"{name_of(spec.key)}'s calls do not go through the circuit breaker: there is none to change.")
    account = IntegrationAccount.objects.filter(provider=spec.key, enabled=True).first()
    if account is None:
        raise refused("No account of it is in use: there is no circuit to change.")
    with transaction.atomic():
        if action == "open":
            account.force_open()
        else:
            from staff.models import InboxItem
            from staff.signals import close_items

            account.reset()
            close_items(account, InboxItem.Kind.INTEGRATION_DOWN)
        verb = "connection.circuit_opened" if action == "open" else "connection.circuit_reset"
        _audit(verb, account, request, reason=reason, details={"provider": spec.key})
        state = "held open" if action == "open" else "reset"
        _alert(f"{name_of(spec.key)}'s circuit {state}", f"By {by_id(by)}. Reason: {reason}")
    return account


def webhook_account(key, create=False):
    """The account whose webhook token a provider's webhook is checked with: the one in use; MSG91's (no test mode)
    its live account, made with its first token."""
    accounts = IntegrationAccount.objects.filter(provider=key)
    if enabled := accounts.filter(enabled=True).first():
        return enabled
    if key == "msg91":
        if create:
            return IntegrationAccount.objects.get_or_create(provider="msg91", mode="live")[0]
        return accounts.filter(mode="live").first()
    return None


def rotate_webhook(key, *, reason, by, request=None):
    """A new webhook token (32 random bytes) for the provider to send or sign with: answered once; the previous one
    still accepted for 24 hours. Audited (never the token), the owners told."""
    spec = provider_or_404(key)
    if not spec.webhook:
        raise refused("It sends no webhook here.")
    if spec.key == "ses":
        raise refused(
            "SES's tracking webhook uses ANYMAIL_WEBHOOK_SECRET's basic auth: change it in the environment and in the "
            "SNS subscription's address together (RUNBOOK.md)."
        )
    with_keys = IntegrationAccount.objects.filter(provider="razorpay").exclude(credentials="")
    if spec.key == "razorpay" and not with_keys.exists():
        raise refused(
            "Razorpay's webhook secret is the environment's (RAZORPAY_WEBHOOK_SECRET) while its keys are: rotate it "
            "there, or give the panel its keys first."
        )
    account = webhook_account(spec.key, create=True)
    if account is None:
        raise refused("No account of it is in use: switch one on first.")
    with transaction.atomic():
        token = account.rotate_webhook_token()
        _audit("connection.webhook_rotated", account, request, reason=reason, details={"provider": spec.key})
        _alert(
            f"{name_of(spec.key)}'s webhook token rotated",
            f"By {by_id(by)}. Paste the new one at the provider within 24 hours. Reason: {reason}",
        )
    return account, token


def webhook_info(key, now=None):
    """A provider's inbound webhooks: our address to paste, how it authenticates, the token's last four characters and
    rotation, the previous one's last moment, the week's events by state, the last event, and the silence alarm."""
    spec = provider_or_404(key)
    if not spec.webhook:
        raise exceptions.NotFound("It sends no webhook here.")
    now = now or timezone.now()
    week = now - timedelta(days=7)
    account = webhook_account(spec.key)
    info = {
        "provider": spec.key,
        "url": f"{settings.SITE_URL}{spec.webhook['path']}",
        "auth": spec.webhook["auth"],
        "header": spec.webhook["header"],
        "token": "",
        "rotated_at": None,
        "previous_valid_until": None,
        "rotatable": spec.key != "ses",
        "events_kept": spec.key not in ("razorpay", "ses"),
        "states": {},
        "last_event_at": None,
        "silence_hours": settings.INTEGRATION_WEBHOOK_SILENCE_HOURS,
        "silent": False,
    }
    if account is not None and spec.key != "ses":
        try:
            info["token"] = account.masked()["webhook_token"]
        except crypto.SecretUnreadable:
            info["token"] = ""
        info["rotated_at"] = account.webhook_rotated_at
        if account.webhook_rotated_at and account.previous_webhook_token:
            until = account.webhook_rotated_at + PREVIOUS_WEBHOOK_TOKEN
            info["previous_valid_until"] = until if until > now else None
    if spec.key == "razorpay":
        from shop.models import WebhookEvent

        events = WebhookEvent.objects.filter(received_at__gte=week)
        info["states"] = dict(events.values_list("name").annotate(n=Count("pk")).order_by())
        health = razorpay_webhook_health(now)
        info["last_event_at"], info["silent"] = health["last_event_at"], health["silent"]
        return info
    if spec.key == "ses":
        from django.db.models import Sum

        from ops.models import EmailStat

        since = timezone.localdate(now) - timedelta(days=6)
        rows = EmailStat.objects.filter(day__gte=since).exclude(event="sent").values_list("event")
        info["states"] = {event: n or 0 for event, n in rows.annotate(n=Sum("count")).order_by()}
        return info
    events = InboundEvent.objects.filter(provider=spec.key)
    info["states"] = dict(events.filter(received_at__gte=week).values_list("state").annotate(n=Count("pk")).order_by())
    info["last_event_at"] = events.aggregate(last=Max("received_at"))["last"]
    in_use = account is not None and (account.enabled or spec.key == "msg91") and bool(account.webhook_token)
    limit = now - timedelta(hours=settings.INTEGRATION_WEBHOOK_SILENCE_HOURS)
    info["silent"] = bool(in_use and (info["last_event_at"] is None or info["last_event_at"] < limit))
    return info


def replay_failed_events(key, since, *, request=None, limit=500):
    """Every failed event of a provider since a time, processed again (at most `limit` at once: whether more wait is
    answered). Returns (replayed, more)."""
    spec = provider_or_404(key)
    failed = InboundEvent.objects.filter(provider=spec.key, state=InboundEvent.State.FAILED, received_at__gte=since)
    rows = list(failed.order_by("received_at", "pk")[: limit + 1])
    more = len(rows) > limit
    with transaction.atomic():
        replayed = sum(1 for event in rows[:limit] if event.replay())
        target = ("integrations.connection", spec.key, name_of(spec.key))
        _audit(
            "connection.events_replayed",
            target,
            request,
            details={"provider": spec.key, "replayed": replayed, "since": since, "more": more},
        )
    return replayed, more


def replay_event(key, event, *, request=None):
    """One inbound event processed again (a rejected one never: it was not ours to take)."""
    was = event.state
    with transaction.atomic():
        if not event.replay():
            raise refused("A rejected event is never processed: its token or signature was wrong.")
        _audit("connection.event_replayed", event, request, details={"provider": key, "state_was": was})
    return event


def failure_outbox_row(failure):
    """The ERPNext outbox row a dead letter belongs to, if any: the sync replays and discards its own (erp.models)."""
    from erp.models import ErpOutbox

    return ErpOutbox.objects.filter(failure=failure).first()


def replay_failure(failure, *, by, request=None):
    """A dead letter's task run again, once (an ERPNext outbox row's through the sync's own replay)."""
    if failure.state != IntegrationFailure.State.OPEN:
        raise refused("Dealt with already.")
    if (row := failure_outbox_row(failure)) is not None:
        if not row.replay(by=by, request=request):
            raise refused("Dealt with already.")
        failure.refresh_from_db()
        return failure
    with transaction.atomic():
        if not failure.replay(by=by):
            raise refused("Dealt with already.")
        _audit(
            "connection.dead_letter_replayed",
            failure,
            request,
            details={"operation": failure.operation, "attempts": failure.attempts},
        )
    return failure


def discard_failure(failure, reason, *, by, request=None):
    """A dead letter given up, with the reason (kept with it)."""
    if failure.state != IntegrationFailure.State.OPEN:
        raise refused("Dealt with already.")
    if (row := failure_outbox_row(failure)) is not None:
        if not row.discard(reason, by=by, request=request):
            raise refused("Dealt with already: only a dead row of the sync is discarded.")
        failure.refresh_from_db()
        return failure
    with transaction.atomic():
        if not failure.discard(reason, by=by):
            raise refused("Dealt with already.")
        _audit(
            "connection.dead_letter_discarded",
            failure,
            request,
            reason=reason,
            details={"operation": failure.operation},
        )
    return failure


def watch_webhooks(now=None):
    """Razorpay's webhook watched (hourly): payments captured for INTEGRATION_WEBHOOK_SILENCE_HOURS without a webhook
    open an inbox item for ADMIN (staff.manage_connections) and alert the owners, once; it is done when one arrives.
    Returns whether it is silent (None: Razorpay is not set up)."""
    from staff.models import InboxItem

    now = now or timezone.now()
    panel = IntegrationAccount.objects.filter(provider="razorpay", enabled=True).exclude(credentials="")
    if not (environment("razorpay")["configured"] or panel.exists()):
        return None
    health = razorpay_webhook_health(now)
    items = InboxItem.objects.filter(
        kind=InboxItem.Kind.WEBHOOK_SILENT, target_type="integrations.connection", target_id="razorpay", done_at=None
    )
    if not health["silent"]:
        items.update(done_at=now)
        return False
    title = f"No Razorpay webhook for {health['window_hours']} hours while {health['paid_in_window']} payments came in"
    with transaction.atomic():
        _, created = InboxItem.objects.get_or_create(
            kind=InboxItem.Kind.WEBHOOK_SILENT,
            target_type="integrations.connection",
            target_id="razorpay",
            done_at=None,
            defaults={
                "title": title,
                "permission": "staff.manage_connections",
                "data": {"paid": health["paid_in_window"]},
            },
        )
        if created:
            _alert(
                "Razorpay's webhook fell silent",
                f"{title}. Razorpay disables a webhook after 24 hours of failures: look at it in Razorpay's dashboard "
                "and enable it again (RUNBOOK.md).",
            )
    return True
