"""The audit log (research section 3): what an event holds and what it never holds, the hash chains and their
verification, the append-only trigger (PostgreSQL), the off-site copy, retention, the nightly checks, the flows it is
fed from, and who may read it (each read itself an event)."""

import json
import time
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from allauth.account.signals import user_logged_in
from allauth.mfa.totp.internal.auth import TOTP, format_hotp_value, generate_totp_secret, hotp_value
from axes.signals import user_locked_out
from django.contrib.auth.models import Group
from django.contrib.sessions.middleware import SessionMiddleware
from django.core import mail
from django.core.files.storage import storages
from django.db import DatabaseError, connection, transaction
from django.test import Client, RequestFactory
from django.utils import timezone

from accounts import roles
from accounts.factories import PASSWORD, UserFactory
from shop import services as shop
from shop.factories import ProductFactory, captured, make_order
from staff import audit
from staff.models import GENESIS, AuditEvent, AuditHead, InboxItem
from staff.tasks import export_audit_log, verify_audit_chain

from .conftest import STAFF, events, make_staff, signed_in

pytestmark = pytest.mark.django_db
BROWSER = "/_allauth/browser/v1"
postgresql_only = pytest.mark.skipif(connection.vendor != "postgresql", reason="the trigger is PostgreSQL's")


def tamper(sql, *params):
    """Change the table behind the trigger's back (PostgreSQL: as its owner, the trigger off for a moment)."""
    with connection.cursor() as cursor:
        if connection.vendor == "postgresql":
            cursor.execute("ALTER TABLE staff_auditevent DISABLE TRIGGER USER")
        cursor.execute(sql, params)
        if connection.vendor == "postgresql":
            cursor.execute("ALTER TABLE staff_auditevent ENABLE TRIGGER USER")


def signed_in_request(user):
    """A log-in's request, with its session (as allauth's user_logged_in sends it)."""
    request = RequestFactory().post(BROWSER + "/auth/login")
    SessionMiddleware(lambda request: None).process_request(request)
    request.user = user
    return request


def test_an_event_holds_who_what_when_and_where_but_no_personal_data(rf):
    staff = make_staff(roles.SUPPORT)
    customer = UserFactory(email="rahul@example.com", full_name="Rahul Das")
    request = rf.post("/api/v1/staff/users/1/suspend/", HTTP_USER_AGENT="Firefox " + "x" * 300)
    request.user, request.session = staff, Client().session
    request.session.save()
    event = audit.record(
        "user.updated",
        request=request,
        target=customer,
        reason="Asked by phone",
        changes={
            "email": ["rahul@example.com", "rahul.das@example.com"],
            "class_level": [10, 12],
            "notes": ["", "Rahul's mother called"],  # free text about a person: changed, not shown
            "details": [{}, {"nominee": "Anita Das"}],
        },
        details={"password": "Brahmaputra-2027", "rows": Decimal("2.50"), "when": date(2026, 10, 9)},
    )
    event = AuditEvent.objects.get(pk=event.pk)
    assert (event.actor_id, event.actor_type, event.actor_roles) == (staff.pk, "staff", [roles.SUPPORT])
    assert (event.target_type, event.target_id, event.target_label) == ("accounts.user", str(customer.pk),
                                                                        f"User #{customer.pk}")  # fmt: skip
    assert event.ip == "127.0.0.1" and len(event.user_agent) == 200 and len(event.session_hash) == 64
    assert event.changes["class_level"] == [10, 12]
    before, after = event.changes["email"]
    assert before.startswith("hash:") and before != after  # comparable, not readable
    stored = json.dumps([event.changes, event.details, event.target_label, event.reason])
    assert "rahul" not in stored.lower() and "Brahmaputra" not in stored and "Anita" not in stored
    assert event.changes["notes"][0] == "" and event.changes["notes"][1].startswith("hash:")
    assert event.changes["details"][1].startswith("hash:")
    assert event.details == {"password": "[secret]", "rows": "2.50", "when": "2026-10-09"}
    assert event.ts.microsecond % 1000 == 0 and event.ts.tzinfo is not None  # milliseconds, UTC
    before_it = AuditEvent.objects.filter(chain="general", pk__lt=event.pk).latest("pk")  # the roles given above
    assert event.chain == "general" and event.prev_hash == before_it.hash


def test_events_chain_by_hash_money_apart():
    first = audit.record("user.unlocked")
    second = audit.record("order.refund.requested")  # money: its own chain, kept 8 financial years
    third = audit.record("user.unlocked")
    assert (first.chain, second.chain, third.chain) == ("general", "money", "general")
    assert third.prev_hash == first.hash and second.prev_hash == GENESIS
    assert third.hash == audit.chain_hash(first.hash, audit.fields_of(AuditEvent.objects.get(pk=third.pk)))
    head = AuditHead.objects.get()
    assert (head.general, head.money) == (third.hash, second.hash)
    assert audit.verify() == []


def test_verification_finds_an_altered_a_removed_and_a_missing_newest_event():
    rows = [audit.record("user.unlocked", reason=f"#{n}") for n in range(4)]
    tamper("UPDATE staff_auditevent SET reason = %s WHERE id = %s", "rewritten", rows[1].pk)
    assert audit.verify() == [f"general: event #{rows[1].pk} was altered"]
    tamper("DELETE FROM staff_auditevent WHERE id = %s", rows[2].pk)
    assert f"general: event #{rows[3].pk} does not follow event #{rows[1].pk}" in audit.verify()
    tamper("DELETE FROM staff_auditevent WHERE id = %s", rows[3].pk)
    assert any("the newest events are missing" in problem for problem in audit.verify())


@postgresql_only
def test_postgresql_refuses_to_change_or_remove_an_event():
    event = audit.record("user.unlocked")
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL examleaf.audit_maintenance = 'off'")  # the tests' own flush turns it on
    for sql in [
        "UPDATE staff_auditevent SET reason = 'x'",
        "DELETE FROM staff_auditevent",
        "TRUNCATE staff_auditevent",
    ]:
        with pytest.raises(DatabaseError, match="append-only"), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(sql)
    with pytest.raises(DatabaseError), transaction.atomic():
        AuditEvent.objects.filter(pk=event.pk).update(reason="x")
    with connection.cursor() as cursor:  # the retention purge's setting lets a DELETE through, never an UPDATE
        cursor.execute("SET LOCAL examleaf.audit_maintenance = 'on'")
    with pytest.raises(DatabaseError), transaction.atomic():
        AuditEvent.objects.filter(pk=event.pk).update(reason="x")
    assert AuditEvent.objects.filter(pk=event.pk).delete()[0] == 1


@pytest.fixture
def backups(settings, tmp_path):
    settings.STORAGES = {
        **settings.STORAGES,
        "backups": {"BACKEND": "django.core.files.storage.FileSystemStorage", "OPTIONS": {"location": tmp_path}},
    }
    return tmp_path


def at(when, action="user.unlocked", **kwargs):
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(timezone, "now", lambda: when)
        return audit.record(action, **kwargs)


def test_a_day_goes_off_site_as_json_lines_with_the_heads_and_verifies_on_its_own(backups):
    yesterday = datetime.now(UTC).replace(hour=1) - timedelta(days=1)
    at(yesterday - timedelta(days=1))  # the day before: another file
    rows = [at(yesterday + timedelta(seconds=n), reason=f"#{n}") for n in range(3)]
    written = export_audit_log()
    day = yesterday.date()
    assert f"audit/{day:%Y/%m}/{day.isoformat()}.jsonl" in written
    lines = (backups / f"audit/{day:%Y/%m}/{day.isoformat()}.jsonl").read_text().splitlines()
    exported, heads = [json.loads(line) for line in lines[:-1]], json.loads(lines[-1])
    assert [row["id"] for row in exported] == [row.pk for row in rows]
    for row in exported:  # anyone can check the copy with the canonical form alone
        assert audit.chain_hash(row["prev_hash"], row) == row["hash"]
    assert heads["type"] == "heads" and heads["chains"]["general"]["hash"] == rows[-1].hash
    assert export_audit_log() == []  # once a day is there it is not written again (the bucket's lock keeps it)


def test_without_a_backups_bucket_the_export_writes_nothing():
    audit.record("user.unlocked")
    assert "backups" not in storages.backends and audit.export_day(timezone.now().date()) is None


def test_the_nightly_check_alerts_the_owners_when_the_chain_breaks(settings, django_capture_on_commit_callbacks):
    settings.STAFF_ALERT_EMAILS = ["owner@examleaf.in"]
    event = audit.record("user.unlocked")
    assert verify_audit_chain() == 0 and events("audit.verified").exists()
    tamper("UPDATE staff_auditevent SET action = %s WHERE id = %s", "user.erased", event.pk)
    with django_capture_on_commit_callbacks(execute=True):
        assert verify_audit_chain() == 1
    assert events("audit.chain_broken", outcome="failed").get().details["problems"] == [
        f"general: event #{event.pk} was altered"
    ]
    assert InboxItem.objects.filter(kind="incident", target_type="audit.chain", done_at=None).exists()
    [alert] = mail.outbox
    assert alert.to == ["owner@examleaf.in"] and "chain is broken" in alert.subject and str(event.pk) in alert.body


def test_the_commands_verify_the_chain_and_purge_it(capsys):
    from django.core.management import CommandError, call_command

    event = audit.record("user.unlocked")
    call_command("verify_audit_chain")
    assert "Intact." in capsys.readouterr().out
    call_command("purge_audit", "--dry-run")
    assert "general: 0 events before" in capsys.readouterr().out and AuditEvent.objects.filter(pk=event.pk).exists()
    tamper("UPDATE staff_auditevent SET reason = %s WHERE id = %s", "x", event.pk)
    with pytest.raises(CommandError, match="was altered"):
        call_command("verify_audit_chain")


def test_alerts_go_to_the_owners_once_committed(settings, django_capture_on_commit_callbacks):
    owner = make_staff(roles.OWNER, email="founder@examleaf.in")
    make_staff(roles.OWNER, email="gone@examleaf.in", is_active=False)
    make_staff(is_superuser=True, email="sealed@examleaf.in")  # a break-glass account: sealed, not read day to day
    with django_capture_on_commit_callbacks(execute=True):
        audit.alert("Something", "happened")
    assert [message.to for message in mail.outbox] == [[owner.email]]
    settings.STAFF_ALERT_EMAILS = ["a@examleaf.in", "b@examleaf.in"]
    with django_capture_on_commit_callbacks(execute=True):
        audit.alert("Something", "happened")
    assert [message.to for message in mail.outbox[1:]] == [["a@examleaf.in"], ["b@examleaf.in"]]


def test_retention_keeps_two_years_and_money_eight_financial_years():
    assert audit.money_cutoff(date(2026, 10, 9)) == date(2018, 4, 1)  # FY 2026-27 and the 8 before it
    assert audit.money_cutoff(date(2027, 2, 1)) == date(2018, 4, 1)  # still FY 2026-27
    assert audit.money_cutoff(date(2027, 4, 1)) == date(2019, 4, 1)
    now = timezone.now()
    old = [at(now - timedelta(days=800), reason=f"#{n}") for n in range(2)]
    kept = at(now - timedelta(days=100))
    money_old = at(datetime(2017, 6, 1, tzinfo=UTC), "order.refund.executed")
    money_kept = at(datetime(2019, 6, 1, tzinfo=UTC), "order.refund.executed")
    deleted = audit.purge(now)
    assert deleted == {"general": 2, "money": 1}
    remaining = set(AuditEvent.objects.values_list("pk", flat=True))
    assert {kept.pk, money_kept.pk} <= remaining and not {*[row.pk for row in old], money_old.pk} & remaining
    purge = events("audit.purged").get()
    assert purge.details["anchors"] == {"general": old[-1].hash, "money": money_old.hash}
    assert audit.verify() == []  # what stays verifies from the anchors the purge kept


def test_a_purge_never_takes_an_event_newer_than_its_cutoff_even_after_the_clock_went_back():
    now = timezone.now()
    first = at(now - timedelta(days=800))
    recent = at(now - timedelta(days=10))
    late = at(now - timedelta(days=900))  # written after `recent` with the clock set back
    assert audit.purge(now) == {"general": 1, "money": 0}
    remaining = set(AuditEvent.objects.values_list("pk", flat=True))
    assert first.pk not in remaining and {recent.pk, late.pk} <= remaining and audit.verify() == []


def test_the_log_is_fed_by_staff_log_ins_with_an_alert_email_and_log_outs(settings):
    settings.MFA_TOTP_TOLERANCE = 1
    staff, secret = make_staff(roles.SUPPORT), generate_totp_secret()
    staff.authenticator_set.all().delete()
    TOTP.activate(staff, secret)
    from allauth.account.models import EmailAddress

    EmailAddress.objects.create(user=staff, email=staff.email, verified=True, primary=True)
    client = Client(HTTP_USER_AGENT="Mozilla/5.0 (Macintosh) Firefox/140.0")
    client.post(BROWSER + "/auth/login", {"email": staff.email, "password": PASSWORD}, "application/json")
    wrong = client.post(BROWSER + "/auth/2fa/authenticate", {"code": "000000"}, "application/json")
    assert wrong.status_code == 400
    code = format_hotp_value(hotp_value(secret, int(time.time()) // 30))
    assert client.post(BROWSER + "/auth/2fa/authenticate", {"code": code}, "application/json").status_code == 200
    login = events("authn_login_success").get()
    assert login.actor_id == staff.pk and login.ip == "127.0.0.1" and "Firefox" in login.user_agent
    [alert] = [message for message in mail.outbox if message.subject.endswith("New sign-in to your ExamLeaf staff "
                                                                              "account")]  # fmt: skip
    assert alert.to == [staff.email] and "127.0.0.1" in alert.body and "Firefox/140.0" in alert.body
    client.delete(BROWSER + "/auth/session")
    assert events("session_logout", actor_id=staff.pk).exists()
    Client().post(BROWSER + "/auth/login", {"email": staff.email, "password": "wrong-password"}, "application/json")
    assert events("authn_login_fail", actor_id=staff.pk, outcome="failed").exists()
    student = UserFactory()
    Client().post(BROWSER + "/auth/login", {"email": student.email, "password": "wrong-password"}, "application/json")
    assert not events("authn_login_fail", actor_id=student.pk).exists()  # customers' failures stay axes'


def test_a_break_glass_log_in_alerts_the_owners_and_every_event_of_its_session_is_marked(
    settings, django_capture_on_commit_callbacks
):
    settings.STAFF_ALERT_EMAILS = ["owner@examleaf.in"]
    sealed, owner = make_staff(is_superuser=True), make_staff(roles.OWNER)
    with django_capture_on_commit_callbacks(execute=True):
        user_logged_in.send(sender=type(sealed), request=signed_in_request(sealed), user=sealed)
        user_logged_in.send(sender=type(owner), request=signed_in_request(owner), user=owner)
    alerts = [message.subject for message in mail.outbox if message.to == ["owner@examleaf.in"]]
    assert alerts == [f"[ExamLeaf] [staff alert] Break-glass account #{sealed.pk} signed in"]  # the founder's: none
    client = signed_in(sealed)
    client.get(STAFF + "audit/")  # every request of the session: its events carry the mark
    client.post(f"{STAFF}users/{UserFactory().pk}/unlock/")
    marked = events(actor_id=sealed.pk)
    assert marked.count() == 3 and all(event.break_glass for event in marked)  # log-in, the read, the unlock
    assert not events(actor_id=owner.pk).filter(break_glass=True).exists()  # the founder's own account is not one
    assert signed_in(make_staff(roles.AUDITOR)).get(STAFF + "audit/", {"break_glass": "true"}).json()["results"]


def test_a_staff_lock_out_is_logged_and_alerts_the_owners(settings, django_capture_on_commit_callbacks):
    settings.STAFF_ALERT_EMAILS = ["owner@examleaf.in"]
    staff = make_staff(roles.SALES)
    with django_capture_on_commit_callbacks(execute=True):
        user_locked_out.send("axes", request=RequestFactory().post("/"), username=staff.email, ip_address="1.2.3.4")
    assert events("authn_login_lock", actor_id=staff.pk, outcome="denied").exists()
    assert any("locked out" in message.subject for message in mail.outbox)


def test_role_changes_from_the_admin_are_logged_with_who_made_them(client):
    sealed = UserFactory(is_staff=True, is_superuser=True)  # the admin's role actions are superusers' (I7)
    client.force_login(sealed)
    user = UserFactory()
    client.post("/admin/accounts/user/", {"action": "add_role_sales", "_selected_action": [user.pk]})
    change = events("authz_change", target_id=str(user.pk)).get()
    assert change.actor_id == sealed.pk and change.details["added"] == [roles.SALES] and change.break_glass
    UserFactory().groups.add(*Group.objects.filter(name=roles.STUDENT))
    assert events("authz_change").count() == 1  # a student's own role is no event


def test_refunds_and_offline_payments_through_the_shop_are_money_events(rzp, commit):
    order = make_order((ProductFactory(), 1))
    with commit():
        shop.record_capture(captured(order))
        shop.cancel_order(order, "Changed their mind")
    refund = events("refund.started").get()
    assert refund.chain == "money" and refund.target_label == order.number and refund.actor_type == "system"
    assert refund.details["amount"] == str(order.total.amount)
    staff_order = make_order((ProductFactory(), 1))
    shop.record_offline_payment(staff_order, "UTR123")
    assert events("payment.offline_recorded", target_id=str(staff_order.pk)).get().chain == "money"


def test_an_export_from_the_admin_is_an_event(rf):
    from django.contrib import admin
    from import_export.formats.base_formats import CSV

    from accounts.models import User

    request = rf.get("/admin/accounts/user/export/")
    request.user = UserFactory(is_staff=True, is_superuser=True)
    admin.site._registry[User].get_export_data(CSV(), request, User.objects.all())
    export = events("data_export").get()
    assert export.details == {"model": "accounts.user", "rows": 1, "where": "admin"}
    assert export.permission == "accounts.export_user"


def test_only_auditors_and_owners_read_the_log_and_each_read_is_an_event():
    audit.record("user.unlocked")
    auditor = make_staff(roles.AUDITOR)
    assert signed_in(make_staff(roles.ADMIN)).get(STAFF + "audit/").status_code == 403  # AU-9(4)
    page = signed_in(auditor).get(STAFF + "audit/", {"action": "user.unlocked"}).json()
    assert [row["action"] for row in page["results"]] == ["user.unlocked"] and "next" in page
    read = events("audit.read", actor_id=auditor.pk).get()
    assert read.details == {"filters": {"action": "user.unlocked"}}
    event = AuditEvent.objects.filter(action="user.unlocked").get()
    assert signed_in(auditor).get(f"{STAFF}audit/{event.pk}/").json()["hash"] == event.hash
    assert events("audit.read", actor_id=auditor.pk).count() == 2


def test_the_log_exports_as_json_lines_and_above_the_limit_becomes_a_job_an_approver_passes(settings):
    for n in range(3):
        audit.record("user.unlocked", reason=f"#{n}")
    auditor = make_staff(roles.AUDITOR)
    response = signed_in(auditor).post(STAFF + "audit/export/", {"filters": {"action": "user.unlocked"}}, format="json")
    assert response.status_code == 200 and response["Content-Type"] == "application/x-ndjson"
    rows = [json.loads(line) for line in b"".join(response.streaming_content).decode().splitlines()]
    assert [row["reason"] for row in rows] == ["#0", "#1", "#2"] and all(row["hash"] for row in rows)
    assert events("audit.exported").get().details["rows"] == 3
    with pytest.MonkeyPatch.context() as patch:
        patch.setitem(roles.ROLE_LIMITS[roles.AUDITOR], "export_rows", 2)
        asked = signed_in(auditor).post(STAFF + "audit/export/", {"filters": {}}, format="json")
        assert asked.status_code == 202 and asked.json()["kind"] == "audit_export"  # a job (test_jobs.py)
        assert asked.json()["state"] == "queued" and asked.json()["change_request_id"]  # ADMIN approves it first
    typo = signed_in(auditor).post(STAFF + "audit/export/", {"filters": {"acton": "user.unlocked"}}, format="json")
    assert typo.status_code == 400 and "acton" in typo.json()["filters"]  # a typo never widens an export
