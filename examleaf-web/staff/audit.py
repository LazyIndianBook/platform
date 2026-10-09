"""The audit log (research section 3). `record()` writes one AuditEvent inside the caller's transaction (an action
rolled back leaves no event), under a lock on the chains' head, chained to the event before it in its chain by its
hash. `verify()` recomputes the chains (the nightly task and `manage.py verify_audit_chain`); `export_day()` copies a
day of events, with the heads, to the backups' bucket. Personal data never goes in: actors and targets are ids,
labels name no one, and personal or secret values in `changes` and `details` are masked. Every event of a break-glass
account (a superuser) carries `break_glass`, and so does an owner's override of an approval."""

import hashlib
import ipaddress
import json
import logging
from datetime import UTC, date, datetime, time, timedelta

from axes.helpers import get_client_ip_address
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import InvalidStorageError, storages
from django.db import models, transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django_guid import get_guid
from simple_history.models import HistoricalRecords

from accounts.roles import OWNER

from .models import GENESIS, AuditEvent, AuditHead

logger = logging.getLogger(__name__)
Chain, ActorType, Outcome = AuditEvent.Chain, AuditEvent.ActorType, AuditEvent.Outcome

# Money events (orders, payments, refunds, prices, coupons, offers) chain apart and are kept 8 financial years
MONEY = ("order.", "payment.", "refund.", "product.price", "coupon.", "offer.")
PERSONAL = {  # masked to a keyed hash: equal values stay comparable, none can be read back
    *["email", "phone", "full_name", "parent_name", "parent_contact", "date_of_birth", "login_phone", "district"],
    *["address", "shipping_address", "line1", "line2", "requester", "contact", "ip", "user_agent", "nominee"],
    # free text staff type about a person (a data request's notes, an incident's description …): changed, not shown
    *["notes", "summary", "response", "identity_note", "description", "notice_text", "details", "text", "comment"],
}
SECRET = {"password", "password1", "password2", "token", "secret", "key", "code", "otp", "session_key", "signature"}
CHAINED = [  # the fields the hash covers, in the canonical JSON (every field but id, prev_hash and hash)
    *["chain", "ts", "actor_id", "actor_type", "actor_roles", "on_behalf_of", "break_glass", "action", "permission"],
    *["target_type", "target_id", "target_label", "outcome", "reason", "change_request_id", "request_id", "ip"],
    *["user_agent", "session_hash", "changes", "details"],
]
LABELS = {  # how a target is named in the log: by its number or code, never a person's details
    "shop.order": lambda order: order.number or f"Order #{order.pk}",
    "shop.product": lambda product: product.title,
    "shop.coupon": lambda coupon: coupon.code,
    "content.paper": lambda paper: paper.code,
}


def mask(value, key=None):
    """Secrets out, personal and free-text values to a keyed hash (a list item by item: a change's [before, after]
    stay comparable), whatever their depth."""
    if isinstance(value, list | tuple):
        return [mask(item, key) for item in value]
    if value is None or value == "":
        return value
    if key in SECRET:
        return "[secret]"
    if key in PERSONAL:
        text = json.dumps(plain(value), sort_keys=True) if isinstance(value, dict) else str(value)
        return "hash:" + salted_hmac("staff.audit.mask", text, algorithm="sha256").hexdigest()[:16]
    if isinstance(value, dict):
        return {name: mask(item, name) for name, item in value.items()}
    return value


def plain(value):
    """JSON's own types only, as the database gives them back: decimals, floats and times as strings."""
    if isinstance(value, dict):
        return {str(name): plain(item) for name, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [plain(item) for item in value]
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat(timespec="milliseconds")
    if isinstance(value, date):
        return value.isoformat()
    if value is None or isinstance(value, bool | int | str):
        return value
    return str(value)  # Decimal, float, Money, UUID, a lazy string


def _ip(value):
    try:
        return str(ipaddress.ip_address(value)) if value else None
    except ValueError:
        return None


def canonical(fields):
    data = {name: fields[name] for name in CHAINED}
    data["ts"], data["ip"] = plain(data["ts"]), _ip(data["ip"])
    data = plain(data)
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def chain_hash(prev_hash, fields):
    return hashlib.sha256((prev_hash + canonical(fields)).encode()).hexdigest()


def current_request():
    """The request being served, if any (django-simple-history's middleware keeps it for the thread)."""
    return getattr(HistoricalRecords.context, "request", None)


def role_names(user):
    return sorted(user.groups.values_list("name", flat=True))


def describe_actor(actor, actor_type=None):
    """(actor_id, actor_type, roles) for a user, an API key's principal, or None (the site itself)."""
    if actor is None:
        return None, actor_type or ActorType.SYSTEM, []
    if key := getattr(actor, "api_key", None):
        return key.pk, ActorType.SERVICE, ["INTEGRATION"]
    if not actor.is_authenticated:
        return None, ActorType.ANONYMOUS, []
    return actor.pk, actor_type or (ActorType.STAFF if actor.is_staff else ActorType.USER), role_names(actor)


def label(obj):
    if make := LABELS.get(obj._meta.label_lower):
        return str(make(obj))[:200]
    return f"{obj._meta.verbose_name.capitalize()} #{obj.pk}"


def describe_target(target):
    if target is None:
        return "", "", ""
    if isinstance(target, models.Model):
        return target._meta.label_lower, str(target.pk), label(target)
    kind, pk, name = target
    return str(kind)[:60], str(pk)[:64], str(name)[:200]


def request_fields(request):
    if request is None:
        return {"ip": None, "user_agent": "", "session_hash": ""}
    session = getattr(request, "session", None)
    key = session.session_key if session is not None else None
    return {
        "ip": _ip(get_client_ip_address(request)),
        "user_agent": request.headers.get("User-Agent", "")[:200],
        "session_hash": salted_hmac("staff.audit.session", key, algorithm="sha256").hexdigest() if key else "",
    }


def session_break_glass(request):
    """A break-glass session's {"reason", "at"} (examleaf.middleware.BREAK_GLASS), or None."""
    from examleaf.middleware import BREAK_GLASS  # (the middleware imports this module late)

    session = getattr(request, "session", None)
    return session.get(BREAK_GLASS) if session is not None else None


def impersonator(request):
    """The member of staff logged in as the customer in this website session (staff.middleware.IMPERSONATING), or
    None: the actor of what the session does."""
    from .middleware import IMPERSONATING

    session = getattr(request, "session", None)
    staff_id = session.get(IMPERSONATING) if session is not None else None
    if not staff_id:
        return None
    if getattr(request, "_impersonator", None) is None:
        request._impersonator = get_user_model().objects.filter(pk=staff_id).first()
    return request._impersonator


def _lock_head():
    head = AuditHead.objects.select_for_update().filter(pk=1).first()
    if head is None:  # the first event (or a test database flushed): concurrent creators, one row
        AuditHead.objects.get_or_create(pk=1)
        head = AuditHead.objects.select_for_update().get(pk=1)
    return head


def record(
    action,
    *,
    request=None,
    actor=None,
    actor_type=None,
    target=None,
    outcome=Outcome.SUCCESS,
    reason="",
    changes=None,
    details=None,
    change_request=None,
    on_behalf_of=None,
    permission="",
    break_glass=None,
):
    """Write one event. `request` (Django's or DRF's) gives the actor (unless `actor` says), the address, the browser,
    the session and the permission the staff API checked; without one the current request is used, if any.
    `target`: a model instance, or (type, id, label). `changes`: {field: [before, after]}. `break_glass`: by default,
    whether the actor is a break-glass account (a superuser)."""
    request = getattr(request, "_request", request) or current_request()
    if actor is None and actor_type is None and request is not None:
        actor = getattr(request, "user", None)
        if getattr(actor, "is_authenticated", False) and (staff := impersonator(request)) is not None:
            actor, on_behalf_of = staff, on_behalf_of or actor  # a member of staff logged in as the customer
    actor_id, kind, roles = describe_actor(actor, actor_type)
    target_type, target_id, target_label = describe_target(target)
    fields = {
        "chain": Chain.MONEY if action.startswith(MONEY) else Chain.GENERAL,
        "actor_id": actor_id,
        "actor_type": kind,
        "actor_roles": roles,
        "on_behalf_of": getattr(on_behalf_of, "pk", on_behalf_of),
        "break_glass": bool(getattr(actor, "is_superuser", False) if break_glass is None else break_glass),
        "action": action[:80],
        "permission": (permission or getattr(request, "_staff_perm", "") or "")[:100],
        "target_type": target_type,
        "target_id": target_id,
        "target_label": target_label,
        "outcome": outcome,
        "reason": str(reason or "")[:500],
        "change_request_id": getattr(change_request, "pk", change_request),
        "request_id": str(get_guid() or "")[:64],
        **request_fields(request),
        "changes": plain(mask(changes or {})),
        "details": plain(mask(details or {})),
    }
    if fields["break_glass"] and (given := session_break_glass(request)):  # the session's reason, in each event
        fields["details"]["break_glass_reason"] = given["reason"]
    # ponytail: one lock for every writer, held to the end of the caller's transaction; fine at this volume, a lock
    # per chain and day if it ever contends. Callers lock their own rows first and record last (no deadlock).
    with transaction.atomic():
        head = _lock_head()
        now = timezone.now()
        fields["ts"] = now.replace(microsecond=now.microsecond // 1000 * 1000)  # milliseconds, as hashed
        prev = getattr(head, fields["chain"])
        event = AuditEvent(**fields, prev_hash=prev, hash=chain_hash(prev, fields))
        event.save(force_insert=True)
        AuditHead.objects.filter(pk=head.pk).update(**{fields["chain"]: event.hash})
    return event


def owners_emails():
    """Who gets the alerts: STAFF_ALERT_EMAILS, else the active members of OWNER (not the break-glass accounts: sealed,
    and not read day to day)."""
    if settings.STAFF_ALERT_EMAILS:
        return list(settings.STAFF_ALERT_EMAILS)
    users = get_user_model().objects.filter(is_active=True, groups__name=OWNER)
    return sorted(set(users.values_list("email", flat=True)))


def alert(subject, body):
    """Email the owners at once, once the transaction is committed (research 3.6)."""
    from ops.tasks import queue_text_email

    def send():
        for address in owners_emails():
            queue_text_email(address, f"[staff alert] {subject}", body)

    transaction.on_commit(send, robust=True)


def fields_of(event):
    return {name: getattr(event, name) for name in CHAINED}


def anchors():
    """The hashes of the last events a retention purge removed, per chain (the purge records them)."""
    found = {}
    for details in AuditEvent.objects.filter(action="audit.purged").values_list("details", flat=True):
        for chain, value in (details.get("anchors") or {}).items():
            found.setdefault(chain, set()).add(value)
    return found


def verify():
    """Recompute both chains: each event's hash, each link to the event before, the start (the genesis or a purge's
    anchor) and the end (the head). Returns the problems found; empty means intact."""
    problems, purged = [], anchors()
    head = AuditHead.objects.filter(pk=1).first()
    for chain in Chain.values:
        known = {GENESIS, *purged.get(chain, ())}
        prev = None
        for event in AuditEvent.objects.filter(chain=chain).order_by("id").iterator():
            if prev is None and event.prev_hash not in known:
                problems.append(f"{chain}: event #{event.pk} follows an event that is missing")
            elif prev is not None and event.prev_hash != prev.hash:
                problems.append(f"{chain}: event #{event.pk} does not follow event #{prev.pk}")
            if chain_hash(event.prev_hash, fields_of(event)) != event.hash:
                problems.append(f"{chain}: event #{event.pk} was altered")
            prev = event
        newest = prev.hash if prev else None
        expected = getattr(head, chain) if head else GENESIS
        if newest != expected and not (newest is None and expected in known):
            problems.append(f"{chain}: the newest events are missing (the head is {expected[:12]}…)")
    return problems


def heads(before=None):
    """{chain: {"id", "hash"}} of each chain's newest event (before a time)."""
    result = {}
    for chain in Chain.values:
        events = AuditEvent.objects.filter(chain=chain)
        if before is not None:
            events = events.filter(ts__lt=before)
        newest = events.order_by("-id").values("id", "hash").first()
        result[chain] = newest or {"id": None, "hash": GENESIS}
    return result


EXPORT_FIELDS = ["id", *CHAINED, "prev_hash", "hash"]


def export_row(event):
    row = {name: getattr(event, name) for name in EXPORT_FIELDS}
    row["ts"], row["ip"] = plain(row["ts"]), _ip(row["ip"])
    return plain(row)


def backups_storage():
    try:
        return storages["backups"]
    except InvalidStorageError:
        return None


def export_day(day):
    """The events of a UTC day as JSON lines in the backups' bucket (`audit/YYYY/MM/YYYY-MM-DD.jsonl`), the last line
    the chains' heads at the end of that day, so a copy can be checked on its own. Returns the file's name; None
    without a backups bucket (BACKUP_BUCKET) or when the day is there already (the bucket's lock keeps it)."""
    storage = backups_storage()
    if storage is None:
        logger.info("BACKUP_BUCKET is not set: the audit log is not copied off the server")
        return None
    name = f"audit/{day:%Y/%m}/{day.isoformat()}.jsonl"
    if storage.exists(name):
        return None
    start = datetime.combine(day, time.min, tzinfo=UTC)
    end = start + timedelta(days=1)
    lines = [
        json.dumps(export_row(event), sort_keys=True, ensure_ascii=False)
        for event in AuditEvent.objects.filter(ts__gte=start, ts__lt=end).order_by("id").iterator()
    ]
    last = {"type": "heads", "day": day.isoformat(), "chains": heads(before=end), "exported_at": plain(timezone.now())}
    lines.append(json.dumps(last, sort_keys=True))
    return storage.save(name, ContentFile(("\n".join(lines) + "\n").encode()))


def money_cutoff(today=None, years=None):
    """The first day kept of the money chain: the start of the financial year (April to March) `years` before the
    current one (Companies Act s.128(5): the current year and the 8 before it)."""
    today = today or timezone.localdate()
    years = settings.STAFF_AUDIT_MONEY_RETENTION_FY if years is None else years
    start = today.year if today.month >= 4 else today.year - 1
    return date(start - years, 4, 1)


def retention_cutoffs(now=None):
    """{chain: the time before which events go}: 2 years (STAFF_AUDIT_RETENTION_DAYS) for the general chain, 8
    financial years for money, at Indian midnight."""
    now = now or timezone.now()
    money = money_cutoff(timezone.localdate(now))
    tz = timezone.get_current_timezone()
    return {
        str(Chain.GENERAL): now - timedelta(days=settings.STAFF_AUDIT_RETENTION_DAYS),
        str(Chain.MONEY): datetime.combine(money, time.min, tzinfo=tz),
    }


def purgeable(chain, cutoff):
    """A chain's oldest events up to (not including) its first one from `cutoff` on: a whole prefix, so what stays
    still verifies from an anchor, and never an event newer than the cutoff, even after the clock was set back."""
    events = AuditEvent.objects.filter(chain=chain)
    first_kept = events.filter(ts__gte=cutoff).order_by("id").values_list("id", flat=True).first()
    return events.filter(id__lt=first_kept) if first_kept is not None else events


def purge(now=None):
    """Delete each chain's events past its retention (`purgeable`) and record the purge with the hash of the last one
    gone, the anchor the rest verifies from. On PostgreSQL the trigger refuses this unless
    `examleaf.audit_maintenance` is on, which only the audit table's owner should set (staff/README.md "Retention").
    Returns {chain: rows deleted}."""
    from django.db import connection

    deleted, anchors_ = {}, {}
    with transaction.atomic():
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL examleaf.audit_maintenance = 'on'")
        for chain, cutoff in retention_cutoffs(now).items():
            doomed = purgeable(chain, cutoff)
            last = doomed.order_by("-id").values("id", "hash").first()
            deleted[chain] = doomed.delete()[0] if last else 0
            if last:
                anchors_[chain] = last["hash"]
        if anchors_:
            record("audit.purged", actor_type=ActorType.SYSTEM, details={"deleted": deleted, "anchors": anchors_})
    return deleted
