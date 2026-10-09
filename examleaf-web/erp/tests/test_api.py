"""The ERPNext sync's staff API under /api/v1/staff/erp/, on the staff app's rules: the catalogued permission of
each action (FINANCE reads and resolves, AUDITOR reads, ADMIN and OWNER replay and discard, with a recent
re-authentication), the admin host only, every refusal an audit event and every action one too; and in the schema
under its own tag."""

import pytest
from django.core.management import call_command
from django.utils import timezone

from accounts import roles
from accounts.factories import UserFactory
from erp import reconcile
from erp.fake import FAKE
from erp.models import ErpOutbox
from staff.models import AuditEvent
from staff.tests.conftest import make_staff, signed_in

from .helpers import ordered, pay_offline, relay

pytestmark = pytest.mark.django_db
BASE = "/api/v1/staff/erp"
CONFLICT = {"message": {"ok": False, "error": {"code": "conflict", "message": "Taken.", "field": "invoice_number"}}}


@pytest.fixture
def dead(on, book, customer):
    """An order whose invoice ERPNext refused for good: its payment waits behind it."""
    order = pay_offline(ordered((book, 1), user=customer))
    FAKE.fail("create_sales_invoice", 409, body=CONFLICT)
    relay()
    return ErpOutbox.objects.get(examleaf_ref=f"invoice:{order.invoice.number}")


@pytest.fixture
def admin():
    return signed_in(make_staff(roles.ADMIN))


def test_signed_out_students_and_staff_without_a_second_factor_get_nothing(client):
    assert client.get(f"{BASE}/status/").status_code == 401  # the Api-Key challenge, as the staff API's
    client.force_login(UserFactory())  # a student
    assert client.get(f"{BASE}/status/").status_code == 403
    client.force_login(UserFactory(is_staff=True, totp=False))  # staff without an authenticator app
    assert client.get(f"{BASE}/status/").json()["code"] == "mfa_setup_required"
    assert AuditEvent.objects.filter(action="authz_fail").count() == 2  # the student's, and the step left undone


def test_only_on_the_admin_host(settings):
    settings.ADMIN_HOSTS, settings.ALLOWED_HOSTS = ["admin.examleaf.in"], ["admin.examleaf.in", "examleaf.in"]
    owner = signed_in(make_staff(roles.OWNER))
    assert owner.get(f"{BASE}/status/", HTTP_HOST="examleaf.in").status_code == 404
    assert owner.get(f"{BASE}/status/", HTTP_HOST="admin.examleaf.in").status_code == 200


def test_the_outbox_with_its_filters(admin, dead):
    listed = admin.get(f"{BASE}/outbox/", {"aggregate_id": dead.aggregate_id}).json()
    assert [row["event"] for row in listed["results"]] == ["payment.received", "invoice.issued"]  # newest first
    one = admin.get(f"{BASE}/outbox/{dead.pk}/").json()
    assert (one["state"], one["idempotency_key"], one["dead_letter"]) == ("dead", str(dead.pk), dead.failure_id)
    assert one["payload"]["invoice_number"] and "conflict" in one["last_error"]
    assert len(admin.get(f"{BASE}/outbox/", {"state": "dead"}).json()["results"]) == 1


def test_a_dead_letter_replayed_with_a_recent_sign_in_and_audited(dead):
    person = make_staff(roles.ADMIN)
    assert signed_in(person, reauth=False).post(f"{BASE}/dead-letters/{dead.pk}/replay/").json()["code"] == (
        "reauthentication_required"
    )  # erp.replay_sync is high: a step-up first
    replayed = signed_in(person).post(f"{BASE}/dead-letters/{dead.pk}/replay/").json()
    assert (replayed["state"], replayed["attempts"]) == ("pending", 0)
    event = AuditEvent.objects.get(action="erp.replay")
    assert (event.actor_id, event.permission, event.target_id, event.details["reference"]) == (
        person.pk,
        "erp.replay_sync",
        str(dead.pk),
        dead.examleaf_ref,
    )
    assert signed_in(person).post(f"{BASE}/dead-letters/{dead.pk}/replay/").status_code == 404  # not dead any more


def test_a_dead_letter_discarded_with_a_reason(admin, dead):
    refused = admin.post(f"{BASE}/dead-letters/{dead.pk}/discard/", {}, format="json")
    assert refused.status_code == 400 and "reason" in refused.json()
    body = {"reason": "Made by hand in ERPNext."}
    discarded = admin.post(f"{BASE}/dead-letters/{dead.pk}/discard/", body, format="json").json()
    assert discarded["state"] == "discarded" and not admin.get(f"{BASE}/dead-letters/").json()["results"]
    event = AuditEvent.objects.get(action="erp.discard")
    assert event.reason == "Made by hand in ERPNext." and event.details["event"] == "invoice.issued"


def test_finance_resolves_differences_but_never_replays(dead):
    finance = make_staff(roles.FINANCE)
    run = reconcile.run(timezone.localdate())
    listed = signed_in(finance).get(f"{BASE}/differences/", {"run": run.pk, "open": "1"}).json()["results"]
    assert len(listed) == run.differences_count > 0
    first = listed[0]["id"]
    resolve = f"{BASE}/differences/{first}/resolve/"
    assert signed_in(finance).post(resolve, {}, format="json").status_code == 400
    note = {"note": "The invoice was made by hand in ERPNext; its row discarded."}
    resolved = signed_in(finance).post(resolve, note, format="json").json()
    assert resolved["note"] == note["note"] and resolved["resolved_by"] == finance.pk
    assert signed_in(finance).post(resolve, note, format="json").json()["non_field_errors"] == ["Resolved already."]
    assert AuditEvent.objects.get(action="erp.resolve").details["about"] == listed[0]["key"]
    assert signed_in(finance).post(f"{BASE}/dead-letters/{dead.pk}/replay/").status_code == 403
    detail = signed_in(finance).get(f"{BASE}/reconciliations/{run.pk}/").json()
    assert len(detail["differences"]) == run.differences_count and detail["state"] == "done"


def test_the_auditor_reads_and_does_nothing_else(dead):
    auditor = signed_in(make_staff(roles.AUDITOR))
    assert auditor.get(f"{BASE}/status/").status_code == 200
    assert auditor.post(f"{BASE}/dead-letters/{dead.pk}/replay/").status_code == 403


def test_the_status(admin, dead):
    status = admin.get(f"{BASE}/status/").json()
    assert status["enabled"] and status["mode"] == "fake" and status["flows"]["invoices"]
    assert status["outbox"]["dead"] == 1 and status["held_aggregates"] == 1
    assert status["account"]["circuit"] == "closed" and status["last_reconciliation"] is None
    assert admin.get(f"{BASE}/status/")["Cache-Control"] == "no-store"


def test_the_schema_has_the_staff_endpoints(tmp_path):
    call_command("spectacular", "--validate", "--fail-on-warn", "--file", tmp_path / "schema.yml")
    schema = (tmp_path / "schema.yml").read_text()
    for path in ["/api/v1/staff/erp/dead-letters/{id}/discard/", "/api/v1/staff/erp/differences/{id}/resolve/"]:
        assert path in schema
    assert "/api/hooks/erp-events/" not in schema and "erp (staff)" in schema
