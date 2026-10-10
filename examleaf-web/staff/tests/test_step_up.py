"""Step-up (research 2.3, plan 9.2's exit criteria): every money, role, key, export, erasure, void, cancel-document and
credential action answers `reauthentication_required` to a session authenticated an hour ago and goes on for one
authenticated a moment ago. The endpoints are derived from the catalogue and the authorization tables (which hold the
URL walk: test_matrix), so a new high or critical action without the step fails here. A child's erasure confirmed for
the parent steps up whatever its endpoint's permission (its view's `reauth`)."""

from collections import defaultdict

import pytest
from django.urls import resolve

from accounts import roles
from erp.tests.test_matrix import ENDPOINTS as ERP_ENDPOINTS
from erp.tests.test_matrix import objects as erp_objects
from staff import catalogue
from staff.models import AuditEvent
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
