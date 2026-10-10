"""Step-up (research 2.3, plan 9.2's exit criteria): every money, role, key, export, erasure, void, cancel-document and
credential action answers `reauthentication_required` to a session authenticated an hour ago and goes on for one
authenticated a moment ago. The endpoints are derived from the catalogue and the authorization tables (which hold the
URL walk: test_matrix), so a new high or critical action without the step fails here; so are the jobs and change
requests whose permission is high. Three actions step up whatever their endpoint's permission: a cancellation that
refunds (approvals.step_up), a bulk cancellation (jobs.start), a child's erasure confirmed for the parent."""

from collections import defaultdict

import pytest
from django.urls import resolve

from accounts import roles
from erp.tests.test_matrix import ENDPOINTS as ERP_ENDPOINTS
from erp.tests.test_matrix import objects as erp_objects
from shop import services as shop
from shop.factories import ProductFactory, captured, make_order
from shop.models import Order
from staff import approvals, catalogue, jobs
from staff.models import AuditEvent, ChangeRequest, Job
from staff.permissions import ANY_STAFF

from .conftest import STAFF, make_staff, signed_in
from .test_matrix import APP_ENDPOINTS, ENDPOINTS, app_objects, objects

pytestmark = pytest.mark.django_db
TABLES = {"staff": (STAFF, ENDPOINTS, objects), "app": ("/api/v1/", APP_ENDPOINTS, app_objects)}
TABLES["erp"] = (STAFF, ERP_ENDPOINTS, erp_objects)


def stepped_up():
    """(table, method, path) of each row whose view names a high or critical permission for it, or always asks for the
    step (its `reauth` actions or methods; its `no_reauth` ones never: ending an impersonation)."""
    from rest_framework.test import APIRequestFactory

    rows = []
    for table, (base, endpoints, _) in TABLES.items():
        for method, path, _ in endpoints:
            callback = resolve(base + path.format_map(defaultdict(lambda: "1")).split("?")[0]).func
            name = (getattr(callback, "actions", None) or {}).get(method, method.upper())
            view = callback.cls()
            view.action, view.kwargs = name, {"key": "SHOP_OPEN"}
            perm = view.required_permission(getattr(APIRequestFactory(), method)("/"))
            if name not in view.no_reauth and (
                name in view.reauth or perm != ANY_STAFF and catalogue.needs_reauth(perm)
            ):
                rows.append((table, method, path))
    return rows


STEPPED = stepped_up()


def refused(response):
    return response.status_code == 403 and response.json().get("code") == "reauthentication_required"


@pytest.mark.parametrize(("table", "method", "path"), STEPPED, ids=[f"{m} {p}" for _, m, p in STEPPED])
def test_each_high_action_asks_an_hour_old_session_to_step_up_and_lets_a_fresh_one_on(table, method, path):
    base, _, made = TABLES[table]
    url = base + path.format(**made())
    owner = make_staff(roles.OWNER)  # every permission: only the step is missing
    stale = getattr(signed_in(owner, reauth=False), method)(url, {}, format="json")
    assert refused(stale), (stale.status_code, stale.content[:200])
    assert stale.json()["flows"] == [{"id": "reauthenticate"}, {"id": "mfa_reauthenticate"}]
    assert not AuditEvent.objects.filter(action="authz_fail", actor_id=owner.pk).exists()  # a step, not a refusal
    fresh = getattr(signed_in(owner), method)(url, {}, format="json")
    assert not refused(fresh), fresh.content[:200]


def test_the_walk_holds_each_kind_of_action_the_plan_names():
    """The derived rows hold a money, role, key, export, erasure, void, cancel-document and credential action each
    (a guard on the derivation itself)."""
    paths = {path for _, _, path in STEPPED}
    for path in [
        "orders/{order}/refunds/",  # money
        "orders/refunds/{refund}/payee/",  # a payee's bank details
        "people/{person}/roles/",  # roles
        "api-keys/",  # keys
        "audit/export/",  # exports
        "data-requests/{erasure}/erase/",  # erasure
        "privacy/deletions/{deletion}/parent-confirmation/",  # a child's erasure, confirmed for the parent
        "course/codes/batches/{batch}/void/",  # void
        "tax/documents/{document}/cancel/",  # cancel a document
        "connections/shiprocket/credentials/",  # credentials
        "connections/shiprocket/webhooks/rotate/",
        "change-requests/{change}/approve/",  # approvals
    ]:
        assert path in paths, path


def test_every_export_is_high():
    """Every permission that exports (an export_ codename, or an export job's own) needs the step: GSTR-1's, the
    products' and categories' as much as the personal data's; and a coupon's single-use codes, money made as a file."""
    exports = {perm for perm in catalogue.EXPLICIT if perm.partition(".")[2].startswith("export_")}
    exports |= {jobs.permission(kind, {}) for kind in Job.Kind.values if kind.endswith("_export")}
    assert len(exports) >= 10 and "staff.run_gstr1" in exports
    assert all(catalogue.needs_reauth(perm) for perm in exports), sorted(
        p for p in exports if not catalogue.needs_reauth(p)
    )
    assert catalogue.entry("shop.add_couponcode").reauth and catalogue.entry("staff.make_book_codes").reauth


def high_jobs():
    """(kind, params) of each job whose own permission is high or critical: every kind, and a bulk action of each
    approvals action a bulk action may name."""
    found = []
    for kind in Job.Kind.values:
        params = [{"action": name} for name in jobs.bulk_actions()] if kind == Job.Kind.BULK_ACTION else [{}]
        found += [(kind, p) for p in params if catalogue.needs_reauth(jobs.permission(kind, p) or "staff.add_job")]
    return found


HIGH_JOBS = high_jobs()


@pytest.mark.parametrize(("kind", "params"), HIGH_JOBS, ids=[f"{k} {p.get('action', '')}" for k, p in HIGH_JOBS])
def test_a_high_job_asks_an_hour_old_session_to_step_up(kind, params):
    owner = make_staff(roles.OWNER)
    stale = signed_in(owner, reauth=False).post(STAFF + "jobs/", {"kind": kind, "params": params}, format="json")
    assert refused(stale), stale.content[:200]
    assert not Job.objects.exists()


def test_the_high_jobs_hold_every_export_and_bulk_money():
    kinds = {kind for kind, _ in HIGH_JOBS}
    for kind in ["audit_export", "orders_export", "product_export", "gstr1_export", "grievance_export"]:
        assert kind in kinds, kind
    assert {"report_export", "code_batch", "coupon_codes", "content_import", "product_import"} <= kinds
    assert ("bulk_action", {"action": "order.refund"}) in HIGH_JOBS


HIGH_ASKS = sorted(
    name for name, item in approvals.ACTIONS.items() if item.generic and catalogue.needs_reauth(item.maker)
)


@pytest.mark.parametrize("name", HIGH_ASKS)
def test_a_change_request_for_a_high_action_asks_an_hour_old_session_to_step_up(name):
    owner = make_staff(roles.OWNER)
    body = {"action": name, "target": "EL-2026-000001", "payload": {}, "reason": "Testing the step"}
    assert refused(signed_in(owner, reauth=False).post(STAFF + "change-requests/", body, format="json"))
    assert not ChangeRequest.objects.exists()


@pytest.fixture
def paid(rzp):
    order = make_order((ProductFactory(stock=5), 1))
    shop.record_capture(captured(order))
    return Order.objects.get(pk=order.pk)


def test_cancelling_an_order_paid_online_is_its_refund_and_steps_up_as_one(paid, commit):
    sales = make_staff(roles.SALES)  # shop.change_order and staff.refund_order, ₹2,000 at once
    url, body = f"{STAFF}orders/{paid.number}/cancel/", {"reason": "Asked by phone"}
    assert refused(signed_in(sales, reauth=False).post(url, body, format="json"))
    paid.refresh_from_db()
    assert paid.status == Order.Status.PAID and not paid.refunds.exists() and not ChangeRequest.objects.exists()
    with commit():
        done = signed_in(sales).post(url, body, format="json")
    assert done.status_code == 201, done.content
    paid.refresh_from_db()
    assert paid.status == Order.Status.REFUNDED


def test_a_tickets_cancellation_of_a_paid_order_steps_up_as_its_refund(paid, commit):
    from support.tests.conftest import make_ticket

    with commit():
        ticket = make_ticket(email=paid.email, order=paid, category="order")
    url, body = f"{STAFF}support/tickets/{ticket.number}/cancel/", {"reason": "Asked to cancel"}
    sales = make_staff(roles.SALES)
    assert refused(signed_in(sales, reauth=False).post(url, body, format="json"))
    assert not ChangeRequest.objects.exists()
    with commit():
        assert signed_in(sales).post(url, body, format="json").status_code == 201


def test_a_bulk_cancellation_steps_up_and_its_dry_run_does_not(paid):
    sales = make_staff(roles.SALES)
    body = {"kind": "orders_cancel", "params": {"targets": [paid.number], "reason": "Out of print"}}
    assert refused(signed_in(sales, reauth=False).post(STAFF + "jobs/", body, format="json"))
    assert not Job.objects.exists()
    dry = signed_in(sales, reauth=False).post(STAFF + "jobs/", {**body, "dry_run": True}, format="json")
    assert dry.status_code == 202, dry.content  # changes nothing: no step
    assert signed_in(sales).post(STAFF + "jobs/", body, format="json").status_code == 202


def test_the_admins_cancel_of_a_paid_order_steps_up_too(client, paid, commit):
    """The Django admin's Cancel (on the panel's session, admin host) asks for the same refund: refused, with the
    reason, until the session re-authenticated in the last 5 minutes (in the console)."""
    import time

    from allauth.account.internal.flows.login import AUTHENTICATION_METHODS_SESSION_KEY
    from django.urls import reverse

    admin = reverse("admin:shop_order_changelist")
    client.force_login(make_staff(roles.SALES))
    body = {"action": "cancel", "_selected_action": [paid.pk]}
    answer = client.post(admin, body, follow=True).content.decode()
    paid.refresh_from_db()
    assert paid.status == Order.Status.PAID and "Confirm it is you" in answer
    session = client.session
    session[AUTHENTICATION_METHODS_SESSION_KEY] = [{"method": "password", "at": time.time()}]
    session.save()
    with commit():
        client.post(admin, body, follow=True)
    paid.refresh_from_db()
    assert paid.status == Order.Status.REFUNDED
