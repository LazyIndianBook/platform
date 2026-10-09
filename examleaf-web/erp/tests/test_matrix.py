"""The authorization matrix of the ERPNext sync's endpoints (staff/tests/test_matrix.py's, for /api/v1/staff/erp/):
every staff role (and a break-glass account) on every endpoint and method. A role without the endpoint's permission
gets 403 and leaves an `authz_fail` event; a role with it never gets 403. Every endpoint names a catalogued
permission, a view_ one for GET; the roles hold what the plan gives them."""

import pytest
from django.urls import URLPattern, URLResolver
from django.utils import timezone

from accounts import roles
from erp import api as erp_api
from erp.models import ErpOutbox, ErpReconciliationDifference, ErpReconciliationRun
from staff import catalogue
from staff.models import AuditEvent
from staff.tests.conftest import STAFF, make_staff, signed_in

pytestmark = pytest.mark.django_db
ENDPOINTS = [
    ("get", "erp/status/", "erp.view_sync"),
    ("get", "erp/outbox/", "erp.view_sync"),
    ("get", "erp/outbox/{row}/", "erp.view_sync"),
    ("get", "erp/dead-letters/", "erp.view_sync"),
    ("get", "erp/dead-letters/{dead}/", "erp.view_sync"),
    ("post", "erp/dead-letters/{dead}/replay/", "erp.replay_sync"),
    ("post", "erp/dead-letters/{dead}/discard/", "erp.replay_sync"),
    ("get", "erp/reconciliations/", "erp.view_sync"),
    ("get", "erp/reconciliations/{run}/", "erp.view_sync"),
    ("get", "erp/differences/", "erp.view_sync"),
    ("get", "erp/differences/{difference}/", "erp.view_sync"),
    ("post", "erp/differences/{difference}/resolve/", "erp.resolve_difference"),
    ("get", "erp/cursors/", "erp.view_sync"),
]
WHO = sorted(roles.STAFF_ROLES)


def objects():
    def outbox_row(state, sequence):
        fields = {"aggregate_type": "order", "aggregate_id": "EL-2026-000001", "event": "invoice.issued"}
        return ErpOutbox.objects.create(**fields, sequence=sequence, examleaf_ref=f"invoice:{sequence}", state=state)

    run = ErpReconciliationRun.objects.create(date=timezone.localdate(), state="done", differences_count=1)
    difference = ErpReconciliationDifference.objects.create(run=run, kind="invoices", key="total")
    return {
        "row": outbox_row("sent", 1).pk,
        "dead": outbox_row("dead", 2).pk,
        "run": run.pk,
        "difference": difference.pk,
    }


@pytest.mark.parametrize(("method", "path", "perm"), ENDPOINTS, ids=[f"{m} {p}" for m, p, _ in ENDPOINTS])
def test_each_role_reaches_an_endpoint_only_with_its_permission(method, path, perm, subtests):
    url = STAFF + path.format(**objects())
    people = [(role, make_staff(role)) for role in WHO] + [("break-glass", make_staff(is_superuser=True))]
    for who, user in people:
        with subtests.test(who=who):
            response = getattr(signed_in(user), method)(url, {}, format="json")
            denied = AuditEvent.objects.filter(action="authz_fail", actor_id=user.pk)
            if user.has_perm(perm):
                assert response.status_code != 403, (who, response.status_code, response.content[:200])
                assert not denied.exists()
            else:
                assert response.status_code == 403, (who, response.status_code, response.content[:200])
                assert denied.exists(), who


def test_the_roles_hold_what_the_plan_gives_them():
    def holds(role, perm):
        return make_staff(role).has_perm(perm)

    perms = ["erp.view_sync", "erp.replay_sync", "erp.resolve_difference", "erp.run_initial_load"]
    for role in (roles.OWNER, roles.ADMIN):
        assert all(holds(role, perm) for perm in perms), role
    assert holds(roles.FINANCE, "erp.view_sync") and holds(roles.FINANCE, "erp.resolve_difference")
    assert not holds(roles.FINANCE, "erp.replay_sync") and not holds(roles.FINANCE, "erp.run_initial_load")
    assert holds(roles.AUDITOR, "erp.view_sync") and not holds(roles.AUDITOR, "erp.resolve_difference")
    for role in (roles.SALES, roles.SUPPORT, roles.PACKER, roles.CONTENT_EDITOR, roles.MARKETING):
        assert not any(holds(role, perm) for perm in perms), role


def test_every_endpoint_names_a_catalogued_permission_and_a_view_one_for_get():
    from rest_framework.test import APIRequestFactory

    def walk(patterns, prefix=""):
        for pattern in patterns:
            if isinstance(pattern, URLResolver):
                yield from walk(pattern.url_patterns, prefix + str(pattern.pattern))
            elif isinstance(pattern, URLPattern):
                yield prefix + str(pattern.pattern), pattern.callback

    checked = 0
    for route, callback in walk(erp_api.urlpatterns):
        cls = callback.cls
        served = sorted(callback.actions.items()) if getattr(callback, "actions", None) else [("get", "GET")]
        for method, name in served:
            view = cls()
            view.action, view.kwargs = name, {}
            perm = view.required_permission(getattr(APIRequestFactory(), method)("/"))
            assert perm and catalogue.entry(perm) is not None, (route, name, perm)
            assert method != "get" or ".view_" in perm, (route, name, perm)
            assert catalogue.entry(perm).area == catalogue.ERP_SYNC
            checked += 1
    assert checked >= len(ENDPOINTS), checked
    assert catalogue.entry("erp.replay_sync").reauth and catalogue.entry("erp.run_initial_load").alerts
