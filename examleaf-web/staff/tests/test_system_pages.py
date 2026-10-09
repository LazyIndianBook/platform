"""The system's pages (staff/system_api.py): one status line per subsystem; the sync monitor; the backups with their
newest object, checksum and the restore drills; logs and time; the dependency report read and its age watched; the
admin host's hardening rows; the checkout's and the console's scripts inventoried, a change alerting once; the weekly
audit skim sent once; the liveness probe reading no database."""

import json
import os
from datetime import timedelta

import httpx
import pytest
from django.core import mail
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.core.management import CommandError, call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from accounts import roles
from erp.models import ErpLink, ErpOutbox
from staff import audit, system_api
from staff.models import AuditEvent, InboxItem, RestoreDrill, ScriptInventory
from staff.tasks import check_backups, check_dependency_report, check_scripts, weekly_audit_skim

from .conftest import STAFF, make_staff, signed_in

pytestmark = pytest.mark.django_db
SYSTEM = STAFF + "system/"


@pytest.fixture
def bucket(tmp_path, monkeypatch):
    """The backups bucket, as a folder: its four sources, the platform's dumps with one dump and its checksum."""
    storage = FileSystemStorage(location=tmp_path / "backups")
    for _, _, prefix in system_api.BACKUP_SOURCES:
        (tmp_path / "backups" / prefix).mkdir(parents=True)
    monkeypatch.setattr(audit, "backups_storage", lambda: storage)
    return storage


def dump(storage, name="examleaf-20261009-020000.dump", hours=1):
    """A dump `hours` old, with the checksum manage.py upload_backup keeps beside it."""
    saved = storage.save(f"database/{name}", ContentFile(b"PGDMP" + b"0" * 1000))
    storage.save(f"{saved}.sha256", ContentFile(f"{'a' * 64}  {name}\n".encode()))
    at = (timezone.now() - timedelta(hours=hours)).timestamp()
    os.utime(storage.path(saved), (at, at))
    return saved


def test_system_opens_on_one_status_line_per_subsystem():
    lines = signed_in(make_staff(roles.ADMIN)).get(SYSTEM).json()["status"]
    keys = [line["key"] for line in lines]
    assert keys == ["health", "queues", "webhooks", "email", "sms", "backups", "audit", "sync", "dependencies",
                    "hardening", "scripts", "logs"]  # fmt: skip
    states = {line["key"]: line["state"] for line in lines}
    assert states["backups"] == "off" and states["sync"] == "off" and states["sms"] != "bad"
    assert all(line["since"] and line["summary"] for line in lines)
    assert signed_in(make_staff(roles.AUDITOR)).get(SYSTEM).status_code == 200  # AUDITOR reads


def test_the_backups_show_each_sources_newest_object_and_when_a_restore_last_worked(bucket):
    dump(bucket, "examleaf-20261008-020000.dump", hours=30)
    dump(bucket)
    client = signed_in(make_staff(roles.ADMIN))
    answer = client.get(SYSTEM + "backups/").json()
    platform = next(row for row in answer["sources"] if row["key"] == "platform_dumps")
    assert platform["latest"]["name"] == "database/examleaf-20261009-020000.dump"
    assert platform["latest"]["sha256"] == "a" * 64 and not platform["stale"] and not answer["stale"]
    assert answer["last_proven"] is None and answer["retention_days"] == 30
    drill = {"performed_on": "2026-10-08", "engine": "platform", "backup": platform["latest"]["name"],
             "result": "passed", "duration_minutes": 42, "notes": "Restored into a scratch database"}  # fmt: skip
    assert (
        signed_in(make_staff(roles.FINANCE)).post(SYSTEM + "backups/drills/", drill, format="json").status_code == 403
    )
    stale = signed_in(make_staff(roles.ADMIN), reauth=False).post(SYSTEM + "backups/drills/", drill, format="json")
    assert stale.json()["code"] == "reauthentication_required"
    assert client.post(SYSTEM + "backups/drills/", drill, format="json").status_code == 201
    assert RestoreDrill.objects.get().recorded_by.groups.filter(name=roles.ADMIN).exists()
    answer = client.get(SYSTEM + "backups/").json()
    assert answer["last_proven"] == {"on": "2026-10-08", "engine": "platform"}
    assert AuditEvent.objects.get(action="backup.drill_recorded").details["minutes"] == 42


def test_no_backup_for_a_day_opens_one_inbox_item_and_alerts_once(bucket, settings, commit):
    settings.STAFF_ALERT_EMAILS = ["owner@examleaf.in"]
    dump(bucket, hours=30)
    with commit():
        assert check_backups() == {"stale": True, "opened": True}
        assert check_backups() == {"stale": True, "opened": False}
    assert InboxItem.objects.filter(kind="backup_stale", done_at=None).count() == 1
    assert sum("No backup for 26 hours" in message.subject for message in mail.outbox) == 1
    dump(bucket, "examleaf-20261009-030000.dump", hours=1)
    assert check_backups()["stale"] is False
    assert not InboxItem.objects.filter(kind="backup_stale", done_at=None).exists()


def test_the_sync_monitor_counts_each_flows_rows_and_finds_a_link():
    ErpOutbox.objects.create(aggregate_type="order", aggregate_id="EL-1", sequence=1, event="invoice.posted",
                             examleaf_ref="invoice:EL-2026-000001", state="dead", last_error="417")  # fmt: skip
    ErpLink.objects.create(examleaf_ref="invoice:EL-2026-000001", model="shop.invoice", object_id="1",
                           doctype="Sales Invoice", name="ACC-SINV-2026-00001")  # fmt: skip
    client = signed_in(make_staff(roles.FINANCE))
    sync = client.get(SYSTEM + "sync/").json()
    flows = {row["flow"]: row["states"] for row in sync["flows"]}
    assert sum(states.get("dead", 0) for states in flows.values()) == 1 and sync["dead_count"] == 1
    assert sync["dead_letters"][0]["examleaf_ref"] == "invoice:EL-2026-000001"
    [link] = client.get(SYSTEM + "sync/links/?q=SINV-2026").json()
    assert link["doctype"] == "Sales Invoice"
    assert client.get(SYSTEM + "sync/links/?q=EL").json() == []  # fewer than 3 characters: nothing


def test_logs_and_time_show_the_inventory_the_retention_in_force_and_the_clock(settings):
    settings.LOG_TIME_SOURCE = "chrony to time.google.com (the node's)"
    logs = signed_in(make_staff(roles.AUDITOR)).get(SYSTEM + "logs/").json()
    assert logs["retention_days"] == 180 and "CERT-In" in logs["rule"]
    assert {row["key"] for row in logs["inventory"]} >= {"audit", "requests", "integration_calls", "sms"}
    assert logs["time"]["documented"] and logs["time"]["ok"] and abs(logs["time"]["offset_ms"]) <= 2000
    assert logs["cert_in"]["placeholder"] is True  # the fresh install's "[…]"


def test_the_dependency_report_is_loaded_read_and_its_age_watched(settings, tmp_path):
    assert check_dependency_report() == {"stale": True}  # none loaded
    assert InboxItem.objects.filter(kind="dependencies_stale", done_at=None).count() == 1
    report = {"generated_at": timezone.now().isoformat(), "commit": "abc123", "versions": {"next": "16.0.1"},
              "advisories": [{"id": "GHSA-1", "ecosystem": "npm", "project": "admin", "package": "next",
                              "severity": "critical", "title": "A flaw", "fixed_in": "next 16.0.2"},
                             {"id": "PYSEC-1", "ecosystem": "pypi", "project": "examleaf-web", "package": "pillow",
                              "severity": "unknown"}]}  # fmt: skip
    path = tmp_path / "dependency-report.json"
    path.write_text(json.dumps(report))
    call_command("load_dependency_report", str(path))  # what the deploy runs
    answer = signed_in(make_staff(roles.ADMIN)).get(SYSTEM + "dependencies/").json()
    assert answer["available"] and not answer["stale"] and answer["counts"]["critical"] == 1
    critical = answer["advisories"][0]
    assert critical["package"] == "next" and critical["due"] and not critical["overdue"]
    assert critical["first_seen"] == timezone.localdate().isoformat()
    assert answer["versions"]["next"] == "16.0.1" and answer["versions"]["django"]
    assert check_dependency_report() == {"stale": False}
    assert not InboxItem.objects.filter(kind="dependencies_stale", done_at=None).exists()
    later = {**report, "generated_at": (timezone.now() - timedelta(days=9)).isoformat()}
    rows = system_api.save_dependency_report(later, now=timezone.now() + timedelta(days=30))
    assert rows[0]["first_seen"] == timezone.localdate().isoformat()  # first seen stays the first sight
    assert check_dependency_report() == {"stale": True}
    path.write_text("not json")
    with pytest.raises(CommandError):
        call_command("load_dependency_report", str(path))


def test_the_hardening_rows_say_what_is_set_and_how_to_fix_what_is_not(settings, monkeypatch):
    settings.ADMIN_HOSTS = ["admin.examleaf.in"]
    settings.ALLOWED_HOSTS = ["examleaf.in", "admin.examleaf.in", "testserver"]
    settings.CSRF_TRUSTED_ORIGINS = ["https://admin.examleaf.in"]
    robots = httpx.MockTransport(lambda request: httpx.Response(200, text="User-agent: *\nDisallow: /\n"))
    monkeypatch.setattr(system_api, "network_transport", lambda: robots)
    client = signed_in(make_staff(roles.ADMIN))
    rows = {row["key"]: row for row in client.get(SYSTEM + "hardening/", HTTP_HOST="admin.examleaf.in").json()}
    assert set(rows) == {"admin_hosts", "staff_404", "hsts", "csp", "no_store", "noindex", "cookies", "debug",
                         "secrets", "proxy_header"}  # fmt: skip
    assert rows["admin_hosts"]["ok"] and rows["no_store"]["ok"] and rows["noindex"]["ok"]
    assert rows["proxy_header"]["ok"] is None  # not testable from here: documented
    assert all(row["fix"] for row in rows.values() if row["ok"] is False)
    settings.ADMIN_HOSTS = []
    rows = {row["key"]: row for row in signed_in(make_staff(roles.ADMIN)).get(SYSTEM + "hardening/").json()}
    assert rows["admin_hosts"]["ok"] is False and "ADMIN_HOSTS" in rows["admin_hosts"]["fix"]


def test_the_scripts_are_inventoried_and_a_change_alerts_once(settings, commit):
    settings.STAFF_ALERT_EMAILS = ["owner@examleaf.in"]
    pages = {"version": "1"}

    def answer(request):
        if request.url.path.endswith("/checkout/") or request.url.path.endswith("/sign-in/"):
            body = f'<script src="/static/app.js"></script><script>window.v="{pages["version"]}"</script>'
            return httpx.Response(200, text=body)
        return httpx.Response(200, content=b"console.log('app')")

    transport = httpx.MockTransport(answer)
    first = system_api.check_scripts(transport=transport)
    assert all(run["ok"] and run["added"] == 2 for run in first.values())
    assert ScriptInventory.objects.count() == 4 and not InboxItem.objects.filter(kind="scripts_changed").exists()
    assert system_api.check_scripts(transport=transport)["checkout"]["added"] == 0  # unchanged: nothing
    pages["version"] = "2"  # an inline script changed
    with commit():
        changed = system_api.check_scripts(transport=transport)
    assert changed["checkout"] == {**changed["checkout"], "added": 1, "removed": 1}
    assert InboxItem.objects.filter(kind="scripts_changed", done_at=None).count() == 2  # one per page
    assert sum("scripts of" in message.subject for message in mail.outbox) == 2
    with commit():
        system_api.check_scripts(transport=transport)  # the same again: no new alert
    assert sum("scripts of" in message.subject for message in mail.outbox) == 2
    scripts = signed_in(make_staff(roles.ADMIN)).get(SYSTEM + "scripts/").json()
    assert {run["page"] for run in scripts["runs"]} == {"checkout", "console"}
    assert sum(row["current"] for row in scripts["scripts"]) == 4


def test_the_daily_task_checks_both_pages_through_its_transport(monkeypatch):
    page = httpx.Response(200, text="<script>window.ready=1</script>")
    monkeypatch.setattr(system_api, "network_transport", lambda: httpx.MockTransport(lambda request: page))
    assert check_scripts() == {"checkout": {"ok": True, "added": 1, "removed": 0},
                               "console": {"ok": True, "added": 1, "removed": 0}}  # fmt: skip


def test_a_page_that_cannot_be_read_is_said_never_taken_for_a_change():
    transport = httpx.MockTransport(lambda request: httpx.Response(503))
    result = system_api.check_scripts(transport=transport)
    assert all(run["ok"] is False and "HTTPStatusError" in run["error"] for run in result.values())
    assert not InboxItem.objects.filter(kind="scripts_changed").exists()


def test_the_weekly_skim_counts_the_high_risk_events_and_is_sent_once(settings, commit):
    settings.STAFF_ALERT_EMAILS = ["owner@examleaf.in"]
    actor = make_staff(roles.SUPPORT)
    audit.record("user.revealed", actor=actor, permission="staff.reveal_contact", details={"email": "a@b.in"})
    audit.record("user.revealed", actor=actor, permission="staff.reveal_contact")
    audit.record("authz_fail", actor=actor)
    audit.record("order.viewed", actor=actor, permission="shop.view_order")  # low risk: not in the skim
    with commit():
        counts = weekly_audit_skim()
        assert weekly_audit_skim() is None  # the same week: once
    assert counts == {"user.revealed": 2, "authz_fail": 1}
    [message] = [message for message in mail.outbox if "high-risk events" in message.subject]
    assert "- user.revealed: 2" in message.body and "a@b.in" not in message.body
    assert AuditEvent.objects.filter(action="audit.skim_sent").count() == 1


def test_the_liveness_probe_reads_no_database(client):
    with CaptureQueriesContext(connection) as queries:
        response = client.get("/health/live/")
    assert response.status_code == 200 and len(queries) == 0
