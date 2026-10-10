"""The system's pages beyond `system/` (plan 5.19), under /api/v1/staff/system/ (staff/urls.py): the sync monitor (the
ERPNext sync's outbox per flow, its dead letters, the links, ERPNext's doorbells and the nightly reconciliations: the
erp app's own API replays and resolves), the backups (the newest object of each source in the backups bucket, the
retention, the restore drills), logs and time (the log inventory, the retention in force, the clock), the dependencies
(CI's audit report), the admin host's hardening checks, and the scripts of the checkout and the console's sign-in. And
what `system/` opens on: one status line per subsystem. Reading is staff.view_system's (AUDITOR reads too), the sync's
erp.view_sync; recording a restore drill staff.manage_system's (high: a re-authentication). The checks that write
(the backups' age, the scripts, the dependency report's age) are tasks (staff/tasks.py) built on the functions here."""

import hashlib
import json
import platform
from datetime import UTC, date, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import django
import httpx
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.core.cache import cache
from django.core.exceptions import DisallowedHost
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, transaction
from django.db.models import Count, Max, Q, Sum
from django.http import HttpResponse
from django.http.request import validate_host
from django.middleware.security import SecurityMiddleware
from django.test import RequestFactory
from django.urls import path
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, serializers
from rest_framework.response import Response

from examleaf import logs
from integrations.redact import scrub

from . import audit
from .api import StaffView
from .backends import scoped
from .config import SETTINGS, site_setting
from .models import InboxItem, RestoreDrill, ScriptInventory

# Mail and SMS (the system page's section; the connections' SES and MSG91 cards read the same)

BOUNCE_LIMIT, COMPLAINT_LIMIT = 0.05, 0.001  # SES puts an account under review at 5 % bounces or 0.1 % complaints


def email_rates(days=7):
    """Emails sent, delivered, bounced for good and complained about over the last `days` (ops.EmailStat), and the
    bounce and complaint rates against SES's review thresholds; a rate is null while nothing was sent."""
    from ops.models import EmailStat

    since = timezone.localdate() - timedelta(days=days - 1)
    rows = EmailStat.objects.filter(day__gte=since).values_list("event").annotate(n=Sum("count")).order_by()
    counts = {event: n or 0 for event, n in rows}
    sent = counts.get("sent", 0)

    def rate(n):
        return round(n / sent, 4) if sent else None

    return {
        "sent": sent,
        "delivered": counts.get("delivered", 0),
        "bounced": counts.get("bounced", 0),
        "complained": counts.get("complained", 0),
        "bounce_rate": rate(counts.get("bounced", 0)),
        "complaint_rate": rate(counts.get("complained", 0)),
        "bounce_limit": BOUNCE_LIMIT,
        "complaint_limit": COMPLAINT_LIMIT,
    }


def mail_and_sms():
    """(email, sms): the week's email counts and rates; SMS by kind and status, the delivery reports and their
    reasons, today's one-time codes and the daily cap's hits (plan 5.19's mail and SMS). Grouped queries only."""
    from ops.models import SmsLog

    week = timezone.now() - timedelta(days=7)
    midnight = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    texts = SmsLog.objects.filter(created__gte=week)
    by_kind = {}
    for kind, state, n in texts.values_list("kind", "status").annotate(n=Count("pk")).order_by():
        by_kind.setdefault(kind, {})[state] = n
    reasons = texts.exclude(delivery_reason="").values_list("delivery_reason").annotate(n=Count("pk"))
    today = SmsLog.objects.filter(created__gte=midnight)
    sms = {
        "by_kind_7_days": by_kind,
        "delivery_7_days": dict(texts.exclude(delivery="").values_list("delivery").annotate(n=Count("pk")).order_by()),
        "failure_reasons_7_days": [{"reason": reason, "n": n} for reason, n in reasons.order_by("-n")[:10]],
        "otp_today": today.filter(kind="otp").exclude(status=SmsLog.Status.CAPPED).count(),
        "capped_today": today.filter(status=SmsLog.Status.CAPPED).count(),
        "capped_7_days": texts.filter(status=SmsLog.Status.CAPPED).count(),
        "daily_cap": settings.SMS_DAILY_CAP,
    }
    return {"stats_7_days": email_rates()}, sms


# Backups (research 7, CP-9): the newest object of each source in the backups bucket, and the restore drills

BACKUP_SOURCES = [  # the backups bucket's prefixes, each written by one job (DEPLOYMENT.md section 9; the chart)
    ("platform_dumps", "The platform's PostgreSQL dumps (scripts/backup.sh)", "database/"),
    ("platform_continuous", "The platform's PostgreSQL base backups (CloudNativePG)", "cnpg/"),
    ("erpnext_database", "ERPNext's MariaDB (mariadb-operator)", "erpnext/mariadb/"),
    ("erpnext_site", "ERPNext's site and files (bench backup)", "erpnext/sites/"),
]
SKIP_FOLDERS = {"wals"}  # a continuous archive's write-ahead log: its newest file is no backup of its own
MAX_DEPTH = 6
BACKUPS = "staff:system:backups"
BACKUPS_KEPT = 2 * 3600  # the hourly check (staff.tasks.check_backups) refreshes it


def newest(storage, prefix, depth=0):
    """The newest object under `prefix` by its name (backups are named by their time: examleaf-YYYYMMDD-HHMMSS.dump,
    barman's YYYYMMDDTHHMMSS, bench's YYYYMMDD_HHMMSS-…): the newest file of a folder that has files, else the newest
    file of its newest folder, MAX_DEPTH folders down at most; None when there is none. One listing per level."""
    folders, files = storage.listdir(prefix)
    files = [name for name in files if not name.endswith(".sha256")]
    if files:
        return prefix + max(files)
    folders = [name for name in folders if name not in SKIP_FOLDERS]
    if folders and depth < MAX_DEPTH:
        return newest(storage, f"{prefix}{max(folders)}/", depth + 1)
    return None


def checksum_of(storage, name):
    """The SHA-256 manage.py upload_backup keeps beside a dump (`<name>.sha256`), or ""."""
    try:
        if not storage.exists(f"{name}.sha256"):
            return ""
        with storage.open(f"{name}.sha256", "rb") as file:
            words = file.read(200).decode("ascii", "replace").split()
    except Exception:  # a missing or unreadable checksum is not a missing backup
        return ""
    return words[0] if words and len(words[0]) == 64 else ""


def backup_summary(refresh=False):
    """The newest object of each backup source (its name, time, size, checksum, encrypted or not), its age and whether
    it is older than BACKUP_STALE_HOURS; kept BACKUPS_KEPT in the cache (a page never walks the bucket twice in a row).
    A source whose listing fails says why; one that never had an object is absent from this deployment. `stale`: a
    source that has backups has none recent, or no source has any; `unreadable`: none could be read."""
    if not refresh and (kept := cache.get(BACKUPS)) is not None:
        return kept
    storage, now = audit.backups_storage(), timezone.now()
    summary = {"configured": storage is not None, "bucket": "", "sources": [], "checked_at": now}
    summary.update({"stale": False, "unreadable": False})
    if storage is not None:
        summary["bucket"] = getattr(storage, "bucket_name", "") or ""
        for key, label, prefix in BACKUP_SOURCES:
            row = {"key": key, "label": label, "prefix": prefix, "latest": None, "error": ""}
            row.update({"age_hours": None, "stale": False})
            try:
                if name := newest(storage, prefix):
                    at = storage.get_modified_time(name)
                    at = at if timezone.is_aware(at) else timezone.make_aware(at, UTC)
                    row["latest"] = {
                        "name": name,
                        "at": at,
                        "size": storage.size(name),
                        "sha256": checksum_of(storage, name),
                        "encrypted": name.endswith(".age"),
                    }
                    row["age_hours"] = round((now - at).total_seconds() / 3600, 1)
                    row["stale"] = row["age_hours"] > settings.BACKUP_STALE_HOURS
            except Exception as error:  # the bucket says no, or cannot be reached: said, never a 500
                row["error"] = scrub(f"{type(error).__name__}: {error}")[:200]
            summary["sources"].append(row)
        present = [row for row in summary["sources"] if row["latest"]]
        summary["unreadable"] = all(row["error"] for row in summary["sources"])
        summary["stale"] = not present or any(row["stale"] for row in present)
    cache.set(BACKUPS, summary, BACKUPS_KEPT)
    return summary


def last_proven():
    """The newest restore drill that worked: {on, engine}, or None ("never proven" on the page)."""
    drill = RestoreDrill.objects.filter(result=RestoreDrill.Result.PASSED).first()
    return {"on": drill.performed_on, "engine": drill.engine} if drill else None


# Logs and time (CERT-In: 180 days of logs, NTP, a point of contact)


def clock():
    """The application's clock against the database's (the closest independent clock a container can read): the
    offset in milliseconds; and the host's documented time source (LOG_TIME_SOURCE: a container cannot see ntpd,
    chronyd or timed)."""
    before = timezone.now()
    with connection.cursor() as cursor:
        cursor.execute("SELECT CURRENT_TIMESTAMP")
        value = cursor.fetchone()[0]
    after = timezone.now()
    database = value if isinstance(value, datetime) else parse_datetime(str(value))
    if database is not None and timezone.is_naive(database):
        database = timezone.make_aware(database, UTC)  # SQLite's CURRENT_TIMESTAMP is UTC, to the second
    app = before + (after - before) / 2
    offset = None if database is None else round((database - app).total_seconds() * 1000)
    tolerance = 1000 if connection.vendor == "postgresql" else 2000  # SQLite keeps whole seconds
    return {
        "source": settings.LOG_TIME_SOURCE,
        "documented": bool(settings.LOG_TIME_SOURCE.strip()),
        "app_now": app,
        "database_now": database,
        "offset_ms": offset,
        "ok": offset is not None and abs(offset) <= tolerance,
    }


CERT_IN_KEYS = ("CERT_IN_POINT_OF_CONTACT", "CERT_IN_CONTACT")  # the disclosures' settings, when they come (P8)


def cert_in_contact():
    """The point of contact registered with CERT-In: the panel's disclosures setting when there is one, the
    environment's otherwise; `placeholder` while it is still the "[…]" of a fresh install."""
    for key in CERT_IN_KEYS:
        if key in SETTINGS and (value := site_setting(key)):
            return {"contact": str(value), "source": "panel", "placeholder": str(value).startswith("[")}
    value = settings.CERT_IN_POINT_OF_CONTACT
    return {"contact": value, "source": "environment", "placeholder": value.startswith("[")}


# Dependencies (research 7: the last pip-audit and npm audit runs, critical fixes within 7 days)

SEVERITIES = ["critical", "high", "moderate", "low", "unknown"]
CRITICAL_DAYS, STALE_DAYS = 7, 8
REPO = Path(settings.BASE_DIR).parent


def _local_versions():
    """What a checkout of the repository says (development: an image carries only examleaf-web): the console's Next.js
    and the ERPNext image's pins. Read once, at start."""
    found = {}
    try:
        found["next"] = json.loads((REPO / "examleaf-admin/package.json").read_text())["dependencies"]["next"]
    except OSError, ValueError, KeyError:
        pass
    try:
        for app in json.loads((REPO / "examleaf-erp/image/apps.json").read_text()):
            name = urlsplit(app["url"]).path.rstrip("/").rsplit("/", 1)[-1].replace("-", "_")
            found[name] = str(app.get("branch", "")).removeprefix("v")
    except OSError, ValueError, KeyError, TypeError:
        pass
    return found


VERSIONS_AT_START = {"django": django.get_version(), "python": platform.python_version(), **_local_versions()}


def dependency_report(today=None):
    """CI's report (the deploy loads it into the private storage: manage.py load_dependency_report) read: the open
    advisories by severity, each critical one with its 7-day target from when it was first seen, whether the report is
    older than STALE_DAYS, and the versions (Django and Python as they run, the rest from the report or a checkout)."""
    today = today or timezone.localdate()
    answer = {"available": False, "path": settings.DEPENDENCY_REPORT_PATH, "generated_at": None, "age_days": None}
    answer.update({"stale": True, "commit": "", "counts": dict.fromkeys(SEVERITIES, 0), "advisories": [], "error": ""})
    versions = dict(VERSIONS_AT_START)
    try:
        if default_storage.exists(settings.DEPENDENCY_REPORT_PATH):
            with default_storage.open(settings.DEPENDENCY_REPORT_PATH, "rb") as file:
                report = json.loads(file.read())
            generated = parse_datetime(str(report.get("generated_at") or ""))
            answer.update({"available": True, "generated_at": generated, "commit": str(report.get("commit", ""))})
            if generated is not None:
                answer["age_days"] = (today - timezone.localdate(generated)).days
                answer["stale"] = answer["age_days"] > STALE_DAYS
            versions.update({str(key): str(value) for key, value in (report.get("versions") or {}).items()})
            for row in report.get("advisories") or []:
                answer["advisories"].append(_advisory(row, today))
    except Exception as error:  # an unreadable report is said, never a 500
        answer["error"] = scrub(f"{type(error).__name__}: {error}")[:200]
    for row in answer["advisories"]:
        answer["counts"][row["severity"]] += 1
    answer["advisories"].sort(key=lambda row: (SEVERITIES.index(row["severity"]), row["package"], row["id"]))
    answer["versions"] = versions
    return answer


def _advisory(row, today):
    severity = row.get("severity") if row.get("severity") in SEVERITIES else "unknown"
    first_seen = date.fromisoformat(str(row["first_seen"])) if row.get("first_seen") else today
    due = first_seen + timedelta(days=CRITICAL_DAYS) if severity == "critical" else None
    return {
        "id": str(row.get("id", "")),
        "ecosystem": str(row.get("ecosystem", "")),
        "project": str(row.get("project", "")),
        "package": str(row.get("package", "")),
        "version": str(row.get("version", "")),
        "severity": severity,
        "title": str(row.get("title", ""))[:300],
        "url": str(row.get("url", "")),
        "fixed_in": str(row.get("fixed_in", "")),
        "first_seen": first_seen,
        "due": due,
        "overdue": bool(due and today > due),
    }


def save_dependency_report(report, now=None):
    """Keep CI's report in the private storage at DEPENDENCY_REPORT_PATH, each advisory's `first_seen` carried over from
    the report it replaces (the 7-day target counts from the first sight, not from the latest run). Returns the rows."""
    now = now or timezone.now()
    if not isinstance(report, dict) or not isinstance(report.get("advisories", []), list):
        raise ValueError("Not a dependency report: an object with a list of advisories.")
    broken = [row for row in report.get("inputs") or [] if isinstance(row, dict) and row.get("ok") is False]
    if broken:  # CI's script marks an audit that did not run (the registry down): never loaded as a clean report
        what = "; ".join(
            f"{row.get('source') or 'an audit'} did not run ({row.get('error') or 'no answer'})" for row in broken
        )
        raise ValueError(f"Not a clean report: {what}.")
    seen = {}
    if default_storage.exists(settings.DEPENDENCY_REPORT_PATH):
        try:
            with default_storage.open(settings.DEPENDENCY_REPORT_PATH, "rb") as file:
                for row in json.loads(file.read()).get("advisories") or []:
                    seen[_advisory_key(row)] = row.get("first_seen")
        except ValueError, AttributeError:  # the old one unreadable: every advisory is first seen now
            seen = {}
    today = timezone.localdate(now).isoformat()
    rows = []
    for row in report.get("advisories", []):
        if not isinstance(row, dict):
            raise ValueError("An advisory is an object.")
        rows.append({**row, "first_seen": seen.get(_advisory_key(row)) or row.get("first_seen") or today})
    report = {**report, "advisories": rows, "generated_at": report.get("generated_at") or now.isoformat()}
    if default_storage.exists(settings.DEPENDENCY_REPORT_PATH):
        default_storage.delete(settings.DEPENDENCY_REPORT_PATH)
    default_storage.save(settings.DEPENDENCY_REPORT_PATH, ContentFile(json.dumps(report, indent=1).encode()))
    return rows


def _advisory_key(row):
    return (row.get("ecosystem"), row.get("project"), row.get("package"), row.get("id"))


# Hardening of the admin host (research 2.4; plan 5.19): each check with what it found and the fix


def _row(key, label, ok, detail, fix=""):
    return {"key": key, "label": label, "ok": ok, "detail": detail, "fix": "" if ok else fix}


def _fingerprint(value):
    """The first four hex digits of a secret's SHA-256: tells two values apart, reveals nothing."""
    return hashlib.sha256(str(value).encode()).hexdigest()[:4]


def _through_staff_middleware(host, address):
    """The staff middleware's answer to a request for `address` on `host`, made here (not over the network)."""
    from .middleware import StaffAuditMiddleware

    request = RequestFactory().get(address, HTTP_HOST=host, secure=True)
    request.session, request.user = SessionStore(), AnonymousUser()
    try:
        return StaffAuditMiddleware(lambda request: HttpResponse("reached"))(request).status_code
    except DisallowedHost:  # a host Django refuses outright (not in ALLOWED_HOSTS): 400, nothing reached
        return 400


def hardening(network=True):
    """The admin host's hardening, a row per check (ok true, false, or null when it cannot be tested from here), with
    the fix. `network`: also fetch the console's robots.txt (STAFF_PANEL_URL, 3 seconds); the status line skips it."""
    rows = []
    hosts = settings.ADMIN_HOSTS
    allowed = all(validate_host(host, settings.ALLOWED_HOSTS) for host in hosts)
    trusted = all(f"https://{host}" in settings.CSRF_TRUSTED_ORIGINS for host in hosts)
    rows.append(
        _row(
            "admin_hosts",
            "The admin host is set apart (ADMIN_HOSTS)",
            bool(hosts) and allowed and trusted,
            f"ADMIN_HOSTS: {', '.join(hosts) or 'not set'}"
            + ("" if allowed else "; not all in ALLOWED_HOSTS")
            + ("" if trusted else "; not all https:// origins in CSRF_TRUSTED_ORIGINS"),
            "Set ADMIN_HOSTS=admin.<domain>, add it to ALLOWED_HOSTS and https://admin.<domain> to "
            "CSRF_TRUSTED_ORIGINS (DEPLOYMENT.md section 13).",
        )
    )
    rows.append(_staff_404_row(hosts))
    request = RequestFactory().get("/api/v1/staff/session/", HTTP_HOST=hosts[0] if hosts else "localhost", secure=True)
    hsts = SecurityMiddleware(lambda request: HttpResponse())(request).headers.get("Strict-Transport-Security", "")
    rows.append(
        _row(
            "hsts",
            "HSTS of a year with subdomains",
            settings.SECURE_HSTS_SECONDS >= 31_536_000 and "includeSubDomains" in hsts,
            f"Strict-Transport-Security: {hsts or 'not sent'}",
            "DEBUG=0 with SECURE_HSTS_SECONDS=31536000 and SECURE_HSTS_INCLUDE_SUBDOMAINS=1 (every subdomain must "
            "serve https).",
        )
    )
    ancestors = [str(value) for value in (getattr(settings, "SECURE_CSP", None) or {}).get("frame-ancestors", [])]
    rows.append(
        _row(
            "csp",
            "A Content-Security-Policy with frame-ancestors 'none'",
            ancestors == ["'none'"],
            f"frame-ancestors: {' '.join(ancestors) or 'not enforced (DEBUG: report-only)'}",
            "Run with DEBUG=0: the policy is enforced (settings.py CONTENT_SECURITY_POLICY).",
        )
    )
    from .api import SessionView  # (staff.api's SystemView imports this module late)

    answer = SessionView.as_view()(RequestFactory().get("/api/v1/staff/session/", secure=True))
    rows.append(
        _row(
            "no_store",
            "Staff answers are never cached (Cache-Control: no-store)",
            answer.headers.get("Cache-Control") == "no-store",
            f"Cache-Control: {answer.headers.get('Cache-Control') or 'not sent'}",
            "Every staff view is a staff.api.StaffView.",
        )
    )
    rows.append(_robots_row(network))
    name, csrf_name, same_site = (
        settings.SESSION_COOKIE_NAME,
        settings.CSRF_COOKIE_NAME,
        settings.SESSION_COOKIE_SAMESITE,
    )
    rows.append(
        _row(
            "cookies",
            "__Host- cookies with SameSite Strict",
            name.startswith("__Host-") and csrf_name.startswith("__Host-") and same_site == "Strict",
            f"Session cookie {name} (SameSite {same_site}); CSRF cookie {csrf_name}.",
            "One Django serves both hosts with one cookie name, and the website needs SameSite Lax for Google's and "
            "Razorpay's returns: a deployment of its own for the admin host, with "
            "SESSION_COOKIE_NAME=__Host-sessionid, CSRF_COOKIE_NAME=__Host-csrftoken and SameSite Strict, sets them "
            "apart.",
        )
    )
    rows.append(
        _row("debug", "DEBUG is off", not settings.DEBUG, f"DEBUG={'1' if settings.DEBUG else '0'}", "DEBUG=0.")
    )
    rows.append(_secrets_row())
    rows.append(
        _row(
            "proxy_header",
            "The proxy strips X-Middleware-Subrequest",
            None,
            "Caddy drops it before the console (the Caddyfile's admin site; the chart's middleware): not testable "
            "from Django.",
        )
    )
    return rows


def _staff_404_row(hosts):
    label = "Staff endpoints answer 404 on any other host"
    public = urlsplit(settings.SITE_URL).hostname or "localhost"
    if not hosts:
        return _row("staff_404", label, False, "Without ADMIN_HOSTS every host answers them.", "Set ADMIN_HOSTS.")
    if validate_host(public, hosts):
        return _row(
            "staff_404",
            label,
            False,
            f"The website's host {public} is an admin host.",
            "Keep the website's host out of ADMIN_HOSTS.",
        )
    api, admin = (_through_staff_middleware(public, address) for address in ("/api/v1/staff/session/", "/admin/"))
    here = _through_staff_middleware(hosts[0], "/api/v1/staff/session/")
    refused = (404, 400)  # not found there, or the host refused outright
    ok = api in refused and admin in refused and here not in refused
    detail = f"On {public} the staff API answered {api} and the Django admin {admin}; on {hosts[0]} the staff API "
    detail += "is not reached." if here in refused else "is reached."
    return _row("staff_404", label, ok, detail, "Check ADMIN_HOSTS and staff/middleware.py.")


def _secrets_row():
    jwt = settings.SIMPLE_JWT.get("SIGNING_KEY")
    found = {
        "SECRET_KEY": "" if settings.SECRET_KEY.startswith("dev-") else settings.SECRET_KEY,
        "JWT_SIGNING_KEY": jwt if jwt and jwt != settings.SECRET_KEY else "",
        "INTEGRATION_KEYS": ",".join(settings.INTEGRATION_KEYS),
        "LEARN_CODE_SECRET": settings.LEARN_CODE_SECRET,
    }
    detail = "; ".join(
        f"{key}: {f'set ({_fingerprint(value)})' if value else 'not set'}" for key, value in found.items()
    )
    return _row(
        "secrets",
        "The secret keys are set, each its own",
        all(found.values()) and len(settings.SECRET_KEY) >= 50,
        detail,
        "Set each in the environment, never the development values (DEPLOYMENT.md section 13).",
    )


def network_transport():
    """The HTTP transport of the checks that fetch our own pages (robots.txt, the scripts): the network (the tests put
    recorded answers here)."""
    return None


def _robots_row(network):
    label = "The console is not indexed (robots.txt)"
    url = f"{settings.STAFF_PANEL_URL}/robots.txt"
    if not network:
        return _row("noindex", label, None, "Checked on the hardening page.")
    try:
        with httpx.Client(timeout=httpx.Timeout(3), transport=network_transport()) as client:
            response = client.get(url, follow_redirects=True)
    except httpx.HTTPError as error:
        return _row("noindex", label, None, f"{url} could not be reached from here ({type(error).__name__}).")
    lines = [line.strip().lower() for line in response.text.splitlines()]
    ok = response.status_code == 200 and "disallow: /" in lines
    detail = f"{url} answered {response.status_code}" + ("" if ok else " without Disallow: /")
    return _row("noindex", label, ok, detail, "The console's src/app/robots.ts disallows everything: deploy it there.")


# The checkout's and the console's scripts (PCI DSS 6.4.3, 11.6.1; research 4.8)

SCRIPT_PAGES = {
    ScriptInventory.Page.CHECKOUT: lambda: f"{settings.SITE_URL}/checkout/",
    ScriptInventory.Page.CONSOLE: lambda: f"{settings.STAFF_PANEL_URL}/sign-in/",
}
MAX_SCRIPTS, MAX_BYTES = 60, 3 * 1024 * 1024
SCRIPTS_RUN = "staff:system:scripts:{page}"  # the last check of a page: {at, ok, error, added, removed}
SCRIPTS_RUN_KEPT = 8 * 24 * 3600


class ScriptParser(HTMLParser):
    """Every <script> of a page: its src, or its inline text (a JSON script's too: it is still the page's code)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.scripts, self._inline = [], None

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            if src := dict(attrs).get("src"):
                self.scripts.append(("src", src))
            else:
                self._inline = []

    def handle_data(self, data):
        if self._inline is not None:
            self._inline.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self._inline is not None:
            self.scripts.append(("inline", "".join(self._inline)))
            self._inline = None


def page_scripts(client, url):
    """{(src or "", sha256)} of the page's scripts: each src fetched and hashed (resolved against the page), each
    inline script's text hashed. Raises httpx.HTTPError when the page or a script cannot be read."""
    page = client.get(url, follow_redirects=True)
    page.raise_for_status()
    parser = ScriptParser()
    parser.feed(page.text[:MAX_BYTES])
    found = set()
    for kind, value in parser.scripts[:MAX_SCRIPTS]:
        if kind == "inline":
            found.add(("", hashlib.sha256(value.encode()).hexdigest()))
            continue
        src = urljoin(str(page.url), value)
        script = client.get(src, follow_redirects=True)
        script.raise_for_status()
        found.add((src[:500], hashlib.sha256(script.content[:MAX_BYTES]).hexdigest()))
    return found


def check_scripts(now=None, transport=None):
    """Inventory each page's scripts (ScriptInventory: first and last seen); on any change from its last check (a
    script added, changed or gone) open an inbox item for ADMIN and alert the owners, once per change. A page that
    cannot be read is said (its check's error), never taken for a change; the first inventory alerts nobody. Returns
    {page: its check}."""
    now = now or timezone.now()
    results = {}
    with httpx.Client(timeout=httpx.Timeout(10, connect=3), transport=transport or network_transport()) as client:
        for page, url_of in SCRIPT_PAGES.items():
            url = url_of()
            try:
                found = page_scripts(client, url)
            except httpx.HTTPError as error:
                results[page] = {"at": now, "ok": False, "error": f"{url}: {type(error).__name__}"}
                results[page].update({"added": 0, "removed": 0})
                cache.set(SCRIPTS_RUN.format(page=page), results[page], SCRIPTS_RUN_KEPT)
                continue
            rows = ScriptInventory.objects.filter(page=page)
            last = rows.aggregate(last=Max("last_seen"))["last"]
            before = set(rows.filter(last_seen=last).values_list("src", "sha256")) if last else set()
            for src, sha in found:
                ScriptInventory.objects.update_or_create(
                    page=page,
                    src=src,
                    sha256=sha,
                    defaults={"last_seen": now},
                    create_defaults={"first_seen": now, "last_seen": now},
                )
            added, removed = found - before, before - found
            results[page] = {"at": now, "ok": True, "error": "", "added": len(added), "removed": len(removed)}
            cache.set(SCRIPTS_RUN.format(page=page), results[page], SCRIPTS_RUN_KEPT)
            if before and (added or removed):
                scripts_changed(page, url, added, removed, now)
    return results


def scripts_changed(page, url, added, removed, now):
    """A page's scripts changed: an inbox item for ADMIN (the open one's details updated) and the owners alerted."""
    label = ScriptInventory.Page(page).label
    details = {"page": str(page), "added": len(added), "removed": len(removed), "at": now.isoformat()}
    change = f"{len(added)} new or changed, {len(removed)} gone"
    with transaction.atomic():
        item, created = InboxItem.objects.get_or_create(
            kind=InboxItem.Kind.SCRIPTS_CHANGED,
            target_type="staff.scriptinventory",
            target_id=str(page),
            done_at=None,
            defaults={
                "title": f"The scripts of {label} changed: {change}",
                "permission": "staff.view_system",
                "data": details,
            },
        )
        if not created:
            item.data = details
            item.save(update_fields=["data"])
        audit.record("scripts.changed", actor_type=audit.ActorType.SYSTEM, details=details)
        audit.alert(
            f"The scripts of {label} changed",
            f"{change} since the last check, on {url}. If no deploy explains it, treat it as an incident: the "
            "checkout's scripts are what PCI DSS asks to watch. The list: the console's System page, Scripts.",
        )


# The status line per subsystem (plan 5.19: green, yellow or red, with the time of the last change)

STATES_SEEN = "staff:system:states"  # {key: [state, since]}: when each line came to its state, as far as seen


def system_status(answer):
    """One line per subsystem from `system/`'s own answer and the cheap checks (no network), each with when it came to
    its state (remembered in the cache: after the cache is emptied, from when it is first seen again)."""
    lines = []

    def line(key, state, summary):
        lines.append({"key": key, "state": state, "summary": summary})

    failing = [check["check"] for check in answer["health"] if not check["ok"]]
    line("health", "bad" if failing else "ok", f"Failing: {', '.join(failing)}" if failing else "Every check passes")
    _queues_line(line, answer["celery"])
    refused = answer["webhooks"]["refused_7_days"]
    line("webhooks", "warn" if refused else "ok", f"{refused} refused in 7 days" if refused else "None refused")
    _email_line(line, answer["email"]["stats_7_days"])
    _sms_line(line, answer["sms"])
    _backups_line(line)
    _audit_line(line, answer["audit"]["last_verification"])
    _sync_line(line)
    _dependencies_line(line)
    misses = [row["key"] for row in hardening(network=False) if row["ok"] is False]
    line("hardening", "warn" if misses else "ok", f"To fix: {', '.join(misses)}" if misses else "Every check passes")
    _scripts_line(line)
    contact, time_ok = cert_in_contact(), bool(settings.LOG_TIME_SOURCE.strip())
    done = time_ok and not contact["placeholder"]
    line(
        "logs",
        "ok" if done else "warn",
        "Time source and CERT-In contact set" if done else "Set LOG_TIME_SOURCE and the CERT-In point of contact",
    )
    now, seen = timezone.now(), cache.get(STATES_SEEN) or {}
    for row in lines:
        before = seen.get(row["key"])
        if before and before[0] == row["state"]:
            row["since"] = parse_datetime(before[1])
        else:
            row["since"] = now
            seen[row["key"]] = [row["state"], now.isoformat()]
    cache.set(STATES_SEEN, seen, None)
    return lines


def _queues_line(line, celery):
    queues, failed = celery["queues"], celery["failed_7_days"]
    if isinstance(queues, dict) and "error" in queues:
        line("queues", "bad", "The queue's broker cannot be reached")
        return
    waiting = sum(queues.values()) if queues else 0
    state = "bad" if waiting > 1000 else "warn" if failed or waiting > 100 else "ok"
    line("queues", state, f"{waiting} tasks waiting, {failed} failed in 7 days")


def _email_line(line, stats):
    if settings.MAILERS["default"]["BACKEND"].endswith("console.EmailBackend"):
        line("email", "off", "Emails are printed, not sent (EMAIL_BACKEND)")
        return
    bounce, complaint = stats["bounce_rate"] or 0, stats["complaint_rate"] or 0
    if bounce >= BOUNCE_LIMIT or complaint >= COMPLAINT_LIMIT:
        state = "bad"
    else:
        state = "warn" if bounce >= BOUNCE_LIMIT / 2 or complaint >= COMPLAINT_LIMIT / 2 else "ok"
    line("email", state, f"{stats['sent']} sent in 7 days; bounces {bounce:.1%}, complaints {complaint:.2%}")


def _sms_line(line, texts):
    if not settings.SMS_ENABLED or settings.SMS_BACKEND == "console":
        line("sms", "off", "SMS are not sent from here (SMS_BACKEND)")
        return
    missed = texts["delivery_7_days"].get("failed", 0) + texts["delivery_7_days"].get("rejected", 0)
    state = "warn" if texts["capped_today"] or missed else "ok"
    line("sms", state, f"{texts['capped_today']} held by the daily cap today; {missed} not delivered in 7 days")


def _backups_line(line):
    backups = backup_summary()
    if not backups["configured"]:
        line("backups", "off", "No backups bucket (BACKUP_BUCKET)")
    elif backups["unreadable"]:
        line("backups", "bad", "The backups bucket could not be read")
    elif backups["stale"]:
        line("backups", "bad", f"No backup for {settings.BACKUP_STALE_HOURS} hours")
    else:
        proven = last_proven()
        quarter = bool(proven) and (timezone.localdate() - proven["on"]).days <= 92
        line(
            "backups",
            "ok" if quarter else "warn",
            "Recent, and proven by a restore this quarter" if quarter else "Recent; no restore proven this quarter",
        )


def _audit_line(line, verification):
    if verification is None:
        line("audit", "warn", "The chain has not been verified yet")
    elif verification["action"] == "audit.chain_broken":
        line("audit", "bad", "The audit chain is broken")
    else:
        recent = timezone.now() - verification["ts"] <= timedelta(days=2)
        line("audit", "ok" if recent else "warn", "Verified" if recent else "Not verified for two days")


def _sync_line(line):
    from erp.models import ErpOutbox
    from erp.producers import switch

    if not switch("ERP_ENABLED"):
        line("sync", "off", "ERPNext is not switched on (ERP_ENABLED)")
        return
    counts = dict(ErpOutbox.objects.values_list("state").annotate(n=Count("pk")).order_by())
    dead, retrying = counts.get("dead", 0), counts.get("failed", 0)
    line("sync", "bad" if dead else "warn" if retrying else "ok", f"{dead} dead letters, {retrying} retrying")


def _dependencies_line(line):
    report = dependency_report()
    if not report["available"]:
        line("dependencies", "warn", "No report loaded (manage.py load_dependency_report)")
        return
    overdue = sum(1 for row in report["advisories"] if row["overdue"])
    critical = report["counts"]["critical"]
    state = "bad" if overdue else "warn" if critical or report["stale"] else "ok"
    age = "of unknown age" if report["age_days"] is None else f"{report['age_days']} days old"
    line("dependencies", state, f"{critical} critical ({overdue} past 7 days); the report is {age}")


def _scripts_line(line):
    runs = [cache.get(SCRIPTS_RUN.format(page=page)) for page in SCRIPT_PAGES]
    changed = InboxItem.objects.filter(kind=InboxItem.Kind.SCRIPTS_CHANGED, done_at=None).exists()
    if not any(runs) and not changed:
        line("scripts", "off", "Not checked yet (daily)")
        return
    unread = any(run and not run["ok"] for run in runs)
    summary = "Changed: see the inbox" if changed else "A page could not be read" if unread else "Unchanged"
    line("scripts", "warn" if changed or unread else "ok", summary)


# The views


class SyncFlowSerializer(serializers.Serializer):
    flow = serializers.CharField()
    switch = serializers.BooleanField(help_text="its ERP_SYNC_* switch, as the code reads it")
    states = serializers.DictField(child=serializers.IntegerField(), help_text="its outbox rows by state")


class SyncDeadSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    event = serializers.CharField()
    examleaf_ref = serializers.CharField()
    aggregate_type = serializers.CharField()
    aggregate_id = serializers.CharField()
    attempts = serializers.IntegerField()
    last_error = serializers.CharField(allow_blank=True)
    created = serializers.DateTimeField()


class SyncRunSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    date = serializers.DateField()
    state = serializers.CharField()
    differences_count = serializers.IntegerField()
    open_differences = serializers.IntegerField()
    finished_at = serializers.DateTimeField(allow_null=True)
    error = serializers.CharField(allow_blank=True)


class SyncInboundSerializer(serializers.Serializer):
    states = serializers.DictField(child=serializers.IntegerField(), help_text="ERPNext's doorbells of 7 days by state")
    last_received_at = serializers.DateTimeField(allow_null=True)


class SyncSerializer(serializers.Serializer):
    status = serializers.JSONField(help_text="as staff/erp/status/ answers it")
    flows = SyncFlowSerializer(many=True)
    dead_letters = SyncDeadSerializer(many=True, help_text="the newest 20 (replay or discard: staff/erp/dead-letters/)")
    dead_count = serializers.IntegerField()
    inbound = SyncInboundSerializer()
    reconciliations = SyncRunSerializer(many=True, help_text="the last 7 nights")


class SyncView(StaffView, generics.GenericAPIView):
    """The sync monitor (plan 5.19): the ERPNext sync's status, its outbox per flow and state, the newest dead letters
    (replayed and discarded through staff/erp/dead-letters/), ERPNext's doorbells of 7 days, the last week's nightly
    reconciliations with their open differences."""

    permissions = {"GET": "erp.view_sync"}
    pagination_class = None
    serializer_class = SyncSerializer

    def get(self, request, *args, **kwargs):
        from erp.contract import EVENTS
        from erp.models import ErpOutbox, ErpReconciliationRun
        from erp.producers import FLOWS, switch
        from erp.tasks import status
        from integrations.models import InboundEvent

        flows = {flow: {"flow": flow, "switch": switch(setting), "states": {}} for flow, setting in FLOWS.items()}
        for event, state, n in ErpOutbox.objects.values_list("event", "state").annotate(n=Count("pk")).order_by():
            flow = EVENTS[event].flow if event in EVENTS else "other"
            states = flows.setdefault(flow, {"flow": flow, "switch": False, "states": {}})["states"]
            states[state] = states.get(state, 0) + n
        dead = ErpOutbox.objects.filter(state=ErpOutbox.State.DEAD)
        week = timezone.now() - timedelta(days=7)
        doorbells = InboundEvent.objects.filter(provider="erpnext")
        received = doorbells.filter(received_at__gte=week).values_list("state").annotate(n=Count("pk")).order_by()
        open_differences = Count("differences", filter=Q(differences__resolved_at__isnull=True))
        runs = ErpReconciliationRun.objects.filter(date__gte=timezone.localdate() - timedelta(days=7))
        answer = {
            "status": json.loads(json.dumps(status(), cls=DjangoJSONEncoder)),
            "flows": list(flows.values()),
            "dead_letters": [
                {
                    "id": row.pk,
                    "event": row.event,
                    "examleaf_ref": row.examleaf_ref,
                    "aggregate_type": row.aggregate_type,
                    "aggregate_id": row.aggregate_id,
                    "attempts": row.attempts,
                    "last_error": row.last_error,
                    "created": row.created,
                }
                for row in dead.order_by("-created", "-pk")[:20]
            ],
            "dead_count": dead.count(),
            "inbound": {
                "states": dict(received),
                "last_received_at": doorbells.aggregate(last=Max("received_at"))["last"],
            },
            "reconciliations": [
                {
                    "id": run.pk,
                    "date": run.date,
                    "state": run.state,
                    "differences_count": run.differences_count,
                    "open_differences": run.open_count,
                    "finished_at": run.finished_at,
                    "error": run.error,
                }
                for run in runs.annotate(open_count=open_differences).order_by("-date", "-pk")
            ],
        }
        return Response(SyncSerializer(answer).data)


class ErpLinkSerializer(serializers.Serializer):
    examleaf_ref = serializers.CharField()
    model = serializers.CharField()
    object_id = serializers.CharField()
    doctype = serializers.CharField()
    name = serializers.CharField(help_text="ERPNext's name of the document")
    synced_at = serializers.DateTimeField()


class SyncLinksView(StaffView, generics.GenericAPIView):
    """ErpLink lookups (`?q=`): a reference (invoice:EL-2026-000123), an ERPNext name, or a platform object's id; the
    first 50 matches, newest first. A query of fewer than 3 characters finds nothing."""

    permissions = {"GET": "erp.view_sync"}
    pagination_class = None
    filter_backends = []  # `?q=` is its own
    serializer_class = ErpLinkSerializer

    @extend_schema(
        parameters=[OpenApiParameter("q", str, description="a reference, an ERPNext name or an object's id")],
        responses=ErpLinkSerializer(many=True),
    )
    def get(self, request, *args, **kwargs):
        from erp.models import ErpLink

        query = (request.query_params.get("q") or "").strip()[:140]
        if len(query) < 3:
            return Response([])
        found = Q(examleaf_ref__icontains=query) | Q(name__icontains=query) | Q(object_id=query)
        links = ErpLink.objects.filter(found).order_by("-synced_at", "-pk")[:50]
        return Response(ErpLinkSerializer(links, many=True).data)


class BackupFileSerializer(serializers.Serializer):
    name = serializers.CharField()
    at = serializers.DateTimeField()
    size = serializers.IntegerField()
    sha256 = serializers.CharField(allow_blank=True, help_text="kept beside it by manage.py upload_backup")
    encrypted = serializers.BooleanField(help_text="encrypted with age (BACKUP_AGE_RECIPIENT)")


class BackupSourceSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    prefix = serializers.CharField()
    latest = BackupFileSerializer(allow_null=True)
    age_hours = serializers.FloatField(allow_null=True)
    stale = serializers.BooleanField()
    error = serializers.CharField(allow_blank=True)


class RestoreDrillSerializer(serializers.ModelSerializer):
    class Meta:
        model = RestoreDrill
        fields = ["id", "performed_on", "engine", "backup", "result", "duration_minutes", "notes", "recorded_by"]
        fields += ["created"]
        read_only_fields = ["id", "recorded_by", "created"]

    def validate_performed_on(self, value):
        if value > timezone.localdate():
            raise serializers.ValidationError("Not in the future.")
        return value

    def validate_duration_minutes(self, value):
        if not 1 <= value <= 7 * 24 * 60:
            raise serializers.ValidationError("From 1 minute to a week.")
        return value


class ProvenSerializer(serializers.Serializer):
    on = serializers.DateField()
    engine = serializers.ChoiceField(choices=RestoreDrill.Engine.choices)


class BackupsSerializer(serializers.Serializer):
    configured = serializers.BooleanField(help_text="a backups bucket is set (BACKUP_BUCKET)")
    bucket = serializers.CharField(allow_blank=True)
    sources = BackupSourceSerializer(many=True)
    stale = serializers.BooleanField(help_text="no recent backup in any source (BACKUP_STALE_HOURS)")
    unreadable = serializers.BooleanField(help_text="the bucket could not be read")
    stale_hours = serializers.IntegerField()
    retention_days = serializers.IntegerField(help_text="BACKUP_KEEP_DAYS")
    checked_at = serializers.DateTimeField()
    last_proven = ProvenSerializer(allow_null=True, help_text="the newest restore drill that worked")
    drills = RestoreDrillSerializer(many=True, help_text="the newest 20")


class BackupsView(StaffView, generics.GenericAPIView):
    """The backups (research 7): the newest object of each source in the backups bucket (its time, size, checksum,
    whether it is encrypted; read at most every two hours, the hourly check alerts past BACKUP_STALE_HOURS), the
    retention, and the restore drills, the last one that worked in words on the page."""

    permissions = {"GET": "staff.view_system"}
    pagination_class = None
    serializer_class = BackupsSerializer

    def get(self, request, *args, **kwargs):
        answer = {
            **backup_summary(),
            "stale_hours": settings.BACKUP_STALE_HOURS,
            "retention_days": settings.BACKUP_KEEP_DAYS,
            "last_proven": last_proven(),
            "drills": RestoreDrill.objects.all()[:20],
        }
        return Response(BackupsSerializer(answer).data)


class DrillsView(StaffView, generics.GenericAPIView):
    """Restore drills: GET every one, newest first (staff.view_restoredrill); POST one just done (staff.manage_system,
    high: a re-authentication): the day, the engine, the backup restored, whether it worked, how long it took, notes."""

    permissions = {"GET": "staff.view_restoredrill", "POST": "staff.manage_system"}
    serializer_class = RestoreDrillSerializer
    queryset = RestoreDrill.objects.none()

    def get_queryset(self):
        return scoped(RestoreDrill.objects.all(), self.request.user, "staff.view_restoredrill")

    def get(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.get_queryset())
        return self.get_paginated_response(RestoreDrillSerializer(page, many=True).data)

    @extend_schema(responses={201: RestoreDrillSerializer})
    def post(self, request, *args, **kwargs):
        user, data = self.human(), RestoreDrillSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        with transaction.atomic():
            drill = data.save(recorded_by=user)
            details = {"engine": drill.engine, "result": drill.result, "minutes": drill.duration_minutes}
            audit.record("backup.drill_recorded", request=request, target=drill, details=details)
        return Response(RestoreDrillSerializer(drill).data, status=201)


class LogRowSerializer(serializers.Serializer):
    key = serializers.CharField()
    what = serializers.CharField()
    where = serializers.CharField()
    kept = serializers.CharField()
    readers = serializers.CharField()
    days = serializers.IntegerField(allow_null=True)
    meets_retention = serializers.BooleanField(allow_null=True, help_text="null: kept as the host decides")


class SystemClockSerializer(serializers.Serializer):
    source = serializers.CharField(allow_blank=True, help_text="LOG_TIME_SOURCE: the host's documented time source")
    documented = serializers.BooleanField()
    app_now = serializers.DateTimeField()
    database_now = serializers.DateTimeField(allow_null=True)
    offset_ms = serializers.IntegerField(allow_null=True, help_text="the database's clock minus the application's")
    ok = serializers.BooleanField(help_text="within a second (two on SQLite)")


class ContactSerializer(serializers.Serializer):
    contact = serializers.CharField()
    source = serializers.ChoiceField(choices=["panel", "environment"])
    placeholder = serializers.BooleanField()


class LogsSerializer(serializers.Serializer):
    retention_days = serializers.IntegerField(help_text="what the law asks for logs now")
    rule = serializers.CharField()
    dpdp_from = serializers.DateField()
    inventory = LogRowSerializer(many=True)
    time = SystemClockSerializer()
    cert_in = ContactSerializer()


class LogsView(StaffView, generics.GenericAPIView):
    """Logs and time (CERT-In's directions; the DPDP Rules): the log inventory (what, where, how long, who reads it,
    and whether that meets the retention in force), the clock against the database's with the host's documented time
    source, and the point of contact registered with CERT-In."""

    permissions = {"GET": "staff.view_system"}
    pagination_class = None
    serializer_class = LogsSerializer

    def get(self, request, *args, **kwargs):
        needed = logs.required_days()
        rule = "A year: the DPDP Rules apply"
        if needed != logs.DPDP_DAYS:
            rule = f"180 days, rolling (CERT-In); a year from {settings.STAFF_DPDP_RULES_FROM:%d %B %Y}"
        answer = {
            "retention_days": needed,
            "rule": rule,
            "dpdp_from": settings.STAFF_DPDP_RULES_FROM,
            "inventory": logs.inventory(),
            "time": clock(),
            "cert_in": cert_in_contact(),
        }
        return Response(LogsSerializer(answer).data)


class AdvisorySerializer(serializers.Serializer):
    id = serializers.CharField()
    ecosystem = serializers.CharField(help_text="python or npm")
    project = serializers.CharField(help_text="examleaf-web, examleaf-admin, examleaf-frontend")
    package = serializers.CharField()
    version = serializers.CharField(allow_blank=True)
    severity = serializers.ChoiceField(choices=SEVERITIES)
    title = serializers.CharField(allow_blank=True)
    url = serializers.CharField(allow_blank=True)
    fixed_in = serializers.CharField(allow_blank=True)
    first_seen = serializers.DateField()
    due = serializers.DateField(allow_null=True, help_text="a critical one's 7-day target")
    overdue = serializers.BooleanField()


class DependenciesSerializer(serializers.Serializer):
    available = serializers.BooleanField(help_text="a report was loaded")
    path = serializers.CharField()
    generated_at = serializers.DateTimeField(allow_null=True)
    age_days = serializers.IntegerField(allow_null=True)
    stale = serializers.BooleanField(help_text="older than 8 days, or none")
    commit = serializers.CharField(allow_blank=True)
    counts = serializers.DictField(child=serializers.IntegerField(), help_text="open advisories by severity")
    advisories = AdvisorySerializer(many=True)
    versions = serializers.DictField(child=serializers.CharField())
    error = serializers.CharField(allow_blank=True)


class DependenciesView(StaffView, generics.GenericAPIView):
    """The dependencies (research 7): CI's last pip-audit and npm audit (the report the deploy loads), the open
    advisories by severity with the 7-day target of the critical ones, and the versions in use."""

    permissions = {"GET": "staff.view_system"}
    pagination_class = None
    serializer_class = DependenciesSerializer

    def get(self, request, *args, **kwargs):
        return Response(DependenciesSerializer(dependency_report()).data)


class HardeningRowSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    ok = serializers.BooleanField(allow_null=True, help_text="null: not testable from here")
    detail = serializers.CharField()
    fix = serializers.CharField(allow_blank=True)


class HardeningView(StaffView, generics.GenericAPIView):
    """The admin host's hardening, each check with what it found and the fix: the admin host set apart, staff
    endpoints 404 elsewhere, HSTS, the CSP's frame-ancestors, no-store, the console's robots.txt, the cookies, DEBUG,
    the secret keys, the proxy's stripped header."""

    permissions = {"GET": "staff.view_system"}
    pagination_class = None
    filter_backends = []
    serializer_class = HardeningRowSerializer

    @extend_schema(responses=HardeningRowSerializer(many=True))
    def get(self, request, *args, **kwargs):
        return Response(HardeningRowSerializer(hardening(), many=True).data)


class ScriptRowSerializer(serializers.ModelSerializer):
    current = serializers.SerializerMethodField(help_text="seen by its page's last check")

    class Meta:
        model = ScriptInventory
        fields = ["id", "page", "src", "sha256", "first_seen", "last_seen", "current"]

    def get_current(self, row) -> bool:
        return row.last_seen == self.context.get("latest", {}).get(row.page)


class ScriptRunSerializer(serializers.Serializer):
    page = serializers.ChoiceField(choices=ScriptInventory.Page.choices)
    url = serializers.CharField()
    at = serializers.DateTimeField(allow_null=True)
    ok = serializers.BooleanField(allow_null=True, help_text="null: not checked yet")
    error = serializers.CharField(allow_blank=True)
    added = serializers.IntegerField()
    removed = serializers.IntegerField()


class ScriptsSerializer(serializers.Serializer):
    runs = ScriptRunSerializer(many=True)
    scripts = ScriptRowSerializer(many=True, help_text="each page's last check's, then the 50 newest others")


class ScriptsView(StaffView, generics.GenericAPIView):
    """The scripts the checkout and the console's sign-in load, as the daily check found them (staff.tasks
    .check_scripts): each page's last check, and its scripts with when they were first and last seen."""

    permissions = {"GET": "staff.view_scriptinventory"}
    pagination_class = None
    serializer_class = ScriptsSerializer

    def get(self, request, *args, **kwargs):
        rows = scoped(ScriptInventory.objects.all(), request.user, "staff.view_scriptinventory")
        latest = dict(rows.values_list("page").annotate(last=Max("last_seen")).order_by())
        current = Q(pk__in=[])
        for page, last in latest.items():
            current |= Q(page=page, last_seen=last)
        scripts = [*rows.filter(current).order_by("page", "src", "pk"), *rows.exclude(current)[:50]]
        runs = []
        for page, url_of in SCRIPT_PAGES.items():
            run = cache.get(SCRIPTS_RUN.format(page=page)) or {}
            runs.append(
                {
                    "page": page,
                    "url": url_of(),
                    "at": run.get("at"),
                    "ok": run.get("ok"),
                    "error": run.get("error", ""),
                    "added": run.get("added", 0),
                    "removed": run.get("removed", 0),
                }
            )
        answer = {"runs": runs, "scripts": scripts}
        return Response(ScriptsSerializer(answer, context={"latest": latest}).data)


urlpatterns = [  # under /api/v1/staff/system/ (staff/urls.py); system/ itself and system/reconcile/ are staff.api's
    path("sync/", SyncView.as_view(), name="system-sync"),
    path("sync/links/", SyncLinksView.as_view(), name="system-sync-links"),
    path("backups/", BackupsView.as_view(), name="system-backups"),
    path("backups/drills/", DrillsView.as_view(), name="system-drills"),
    path("logs/", LogsView.as_view(), name="system-logs"),
    path("dependencies/", DependenciesView.as_view(), name="system-dependencies"),
    path("hardening/", HardeningView.as_view(), name="system-hardening"),
    path("scripts/", ScriptsView.as_view(), name="system-scripts"),
]
