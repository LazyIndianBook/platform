"""The authorization matrix (research 1.9, OWASP: test the authorization logic): every role × every staff endpoint and
method (the staff API's, the shipping app's and the insights'). A role without the endpoint's permission gets 403 and
leaves an `authz_fail` event; a role with it never gets 403 (its answer may be 400 for the empty body, 404 for an object
out of its reach, or 200). And every endpoint names a catalogued permission, a view_ one for GET (DRF's pitfall:
DjangoModelPermissions lets any GET through)."""

from datetime import timedelta

import pytest
from django.urls import URLPattern, URLResolver
from django.utils import timezone

from accounts import roles
from accounts.factories import UserFactory
from api import urls as api_urls
from insights.models import FraudSignal
from integrations.models import IntegrationAccount
from shipping.api import OrderQuoteView, ShipmentViewSet
from shipping.models import CodRemittance, PickupLocation, ShipmentCharge, ShippingException
from shop.factories import ProductFactory, make_order
from shop.models import Shipment
from staff import approvals, catalogue
from staff import urls as staff_urls
from staff.api import StaffView
from staff.audit import record
from staff.models import (
    ApiKey,
    AuditEvent,
    ChangeRequest,
    DataRequest,
    InboxItem,
    Incident,
    Job,
    ProcessorRecord,
    SavedView,
    StaffInvite,
    StaffScope,
)
from staff.permissions import ANY_STAFF

from .conftest import STAFF, make_staff, signed_in

pytestmark = pytest.mark.django_db

ENDPOINTS = [
    ("get", "inbox/", "staff.view_inbox"),
    ("get", "inbox/count/", "staff.view_inbox"),
    ("post", "inbox/{item}/done/", "staff.view_inbox"),
    ("post", "inbox/{item}/snooze/", "staff.view_inbox"),
    ("post", "inbox/{item}/assign/", "staff.view_inbox"),
    ("get", "audit/", "staff.view_auditlog"),
    ("get", "audit/{event}/", "staff.view_auditlog"),
    ("post", "audit/export/", "staff.export_auditlog"),
    ("get", "jobs/", "staff.view_job"),
    ("get", "jobs/{job}/", "staff.view_job"),
    ("post", "jobs/", "staff.add_job"),  # (no kind: each kind needs its own permission too, test_jobs.py)
    ("get", "jobs/{job}/result/", "staff.view_job"),  # its starter's only: 404 for anyone else
    ("post", "jobs/{job}/cancel/", "staff.view_job"),
    ("get", "change-requests/", "staff.view_changerequest"),
    ("get", "change-requests/{change}/", "staff.view_changerequest"),
    ("post", "change-requests/", "staff.add_changerequest"),
    ("post", "change-requests/{change}/approve/", "staff.approve_refund"),
    ("post", "change-requests/{change}/reject/", "staff.approve_refund"),
    ("post", "change-requests/{change}/execute/", "staff.approve_refund"),  # or its maker
    ("get", "saved-views/", "staff.view_savedview"),
    ("post", "saved-views/", "staff.add_savedview"),
    ("patch", "saved-views/{view}/", "staff.change_savedview"),
    ("delete", "saved-views/{view}/", "staff.delete_savedview"),
    ("get", "settings/", "staff.view_sitesetting"),
    ("get", "settings/SHOP_OPEN/", "staff.view_sitesetting"),
    ("put", "settings/SHOP_OPEN/", "staff.manage_settings"),
    ("put", "settings/MAINTENANCE_BANNER/", "staff.toggle_maintenance"),
    ("get", "flags/", "staff.view_featureflag"),
    ("get", "flags/ERP_SYNC_ORDERS/", "staff.view_featureflag"),
    ("put", "flags/ERP_SYNC_ORDERS/", "staff.manage_flags"),
    ("get", "api-keys/", "staff.view_apikey"),
    ("get", "api-keys/{key}/", "staff.view_apikey"),
    ("post", "api-keys/", "staff.manage_api_keys"),
    ("post", "api-keys/{key}/revoke/", "staff.manage_api_keys"),
    ("get", "people/", "staff.view_staff"),
    ("get", "people/{person}/", "staff.view_staff"),
    ("get", "people/invites/", "staff.view_staff"),
    ("post", "people/invite/", "staff.assign_role"),
    ("delete", "people/invites/{invite}/", "staff.assign_role"),
    ("post", "people/{person}/roles/", "staff.assign_role"),
    ("delete", "people/{person}/roles/SUPPORT/", "staff.assign_role"),
    ("post", "people/{person}/scopes/", "staff.assign_role"),
    ("delete", "people/{person}/scopes/{scope}/", "staff.assign_role"),
    ("post", "people/{person}/end-sessions/", "staff.assign_role"),
    ("post", "people/{person}/reset-mfa/", "staff.reset_user_mfa"),
    ("get", "access-review/", "staff.view_staff"),
    ("get", "users/", "accounts.view_user"),
    ("get", "users/{customer}/", "accounts.view_user"),
    ("post", "users/{customer}/reveal/", "staff.reveal_contact"),
    ("post", "users/{customer}/suspend/", "staff.suspend_user"),
    ("post", "users/{customer}/unsuspend/", "staff.suspend_user"),
    ("post", "users/{customer}/unlock/", "staff.unlock_user"),
    ("post", "users/{customer}/resend-verification/", "staff.resend_verification"),
    ("post", "users/{customer}/end-sessions/", "staff.end_user_sessions"),
    ("post", "users/{customer}/password-reset/", "staff.initiate_password_reset"),
    ("post", "users/{customer}/reset-mfa/", "staff.reset_user_mfa"),
    ("post", "users/{customer}/impersonate/", "staff.impersonate_user"),
    ("post", "users/{customer}/impersonate/end/", "staff.impersonate_user"),
    ("get", "data-requests/", "staff.view_datarequest"),
    ("get", "data-requests/{request}/", "staff.view_datarequest"),
    ("post", "data-requests/", "staff.handle_data_request"),
    ("patch", "data-requests/{request}/", "staff.handle_data_request"),
    ("post", "data-requests/{request}/acknowledge/", "staff.handle_data_request"),
    ("post", "data-requests/{request}/verify-identity/", "staff.handle_data_request"),
    ("post", "data-requests/{request}/close/", "staff.handle_data_request"),
    ("get", "data-requests/{request}/response/", "staff.view_datarequest"),
    ("get", "data-requests/{erasure}/erasure-report/", "staff.view_datarequest"),
    ("post", "data-requests/{erasure}/erase/", "staff.handle_data_request"),
    ("post", "data-requests/{request}/export/", "staff.export_personal_data"),
    ("get", "incidents/", "staff.view_incident"),
    ("get", "incidents/{incident}/", "staff.view_incident"),
    ("post", "incidents/", "staff.manage_incident"),
    ("patch", "incidents/{incident}/", "staff.manage_incident"),
    ("post", "incidents/{incident}/close/", "staff.manage_incident"),
    ("get", "processors/", "staff.view_processorrecord"),
    ("get", "processors/{processor}/", "staff.view_processorrecord"),
    ("post", "processors/", "staff.add_processorrecord"),
    ("patch", "processors/{processor}/", "staff.change_processorrecord"),
    ("delete", "processors/{processor}/", "staff.delete_processorrecord"),
    ("get", "system/", "staff.view_system"),
    ("post", "system/reconcile/", "staff.replay_webhook"),
    ("post", "people/{person}/offboard/", "staff.assign_role"),  # last: the person goes
]
WHO = sorted(roles.STAFF_ROLES)  # one member of staff per role (OWNER: the founder), and a break-glass account


def objects():
    """One of everything the endpoints act on."""
    maker = make_staff(roles.SALES)
    customer = UserFactory()
    person = make_staff(roles.SUPPORT)
    payload = {"order": "EL-2026-000001", "amount": "5000.00", "cancel": False}
    change = ChangeRequest.objects.create(
        action="order.refund",
        payload=payload,
        payload_sha256=approvals.digest(payload),
        maker=maker,
        reason="A damaged parcel",
        expires_at=timezone.now() + timedelta(days=1),
    )
    erasure = DataRequest.objects.create(
        kind="erasure", channel="email", user=customer, requester="a@example.com", summary="Erase it"
    )
    return {
        "item": InboxItem.objects.create(
            kind="failed_job", title="A task failed", permission="staff.view_inbox", target_type="t", target_id="1"
        ).pk,
        "event": record("test.event").pk,
        "job": Job.objects.create(kind="audit_export", params={"filters": {}}, started_by=person).pk,
        "change": change.pk,
        "view": SavedView.objects.create(owner=person, list_key="users", name="Mine").pk,
        "key": ApiKey.objects.create(
            name="Courier",
            prefix="abcd1234",
            secret_hash="0" * 64,
            scopes=["shop.view_order"],
            sponsor=person,
            expires_at=timezone.now() + timedelta(days=30),
        ).pk,  # fmt: skip
        "person": person.pk,
        "invite": StaffInvite.objects.create(
            email="new@example.com", role=roles.SUPPORT, token_hash="1" * 64, expires_at=timezone.now()
        ).pk,
        "scope": StaffScope.objects.create(user=person, kind="subject", value="PHY").pk,
        "customer": customer.pk,
        "request": DataRequest.objects.create(
            kind="access", channel="letter", user=customer, requester="98640 12345", summary="A copy"
        ).pk,
        "erasure": erasure.pk,
        "incident": Incident.objects.create(title="A lost laptop", kind="data_leak").pk,
        "processor": ProcessorRecord.objects.create(
            name="Razorpay", purpose="payments", data_categories="orders", country="India"
        ).pk,  # fmt: skip
    }


def reach(method, url, perm, subtests):
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


@pytest.mark.parametrize(("method", "path", "perm"), ENDPOINTS, ids=[f"{m} {p}" for m, p, _ in ENDPOINTS])
def test_each_role_reaches_an_endpoint_only_with_its_permission(method, path, perm, subtests):
    reach(method, STAFF + path.format(**objects()), perm, subtests)


APP_ENDPOINTS = [  # under /api/v1/: the shipping app's staff endpoints and the insights'
    *[("get", f"shipping/shipments/{path}", "staff.view_parcels") for path in ["", "{parcel}/", "{parcel}/events/"]],
    ("post", "shipping/shipments/", "staff.book_parcel"),
    ("get", "shipping/shipments/{parcel}/label/", "staff.book_parcel"),  # the label: the customer's address on it
    *[
        ("post", f"shipping/shipments/{{parcel}}/{name}/", "staff.book_parcel")
        for name in ["label", "pickup", "cancel"]
    ],
    ("post", "shipping/shipments/{parcel}/photo/", "staff.book_parcel"),
    ("post", "shipping/shipments/{parcel}/ndr-action/", "staff.act_on_exception"),
    ("get", "shipping/orders/{order}/quote/", "staff.book_parcel"),  # a courier's answer, for a booking
    ("post", "shipping/manifest/", "staff.book_parcel"),
    ("get", "shipping/exceptions/", "staff.view_parcels"),
    ("get", "shipping/exceptions/{exception}/", "staff.view_parcels"),
    ("post", "shipping/exceptions/{exception}/resolve/", "staff.act_on_exception"),
    ("get", "shipping/cod/", "staff.view_cod"),
    ("get", "shipping/cod/{remittance}/", "staff.view_cod"),
    ("post", "shipping/cod/{remittance}/reconcile/", "staff.reconcile_cod"),
    ("get", "shipping/charges/", "staff.view_cod"),
    ("get", "shipping/charges/{charge}/", "staff.view_cod"),
    ("get", "shipping/pickup-locations/", "staff.view_parcels"),
    ("get", "shipping/pickup-locations/{pickup}/", "staff.view_parcels"),
    ("post", "shipping/pickup-locations/", "staff.manage_pickup_locations"),
    ("patch", "shipping/pickup-locations/{pickup}/", "staff.manage_pickup_locations"),
    ("post", "shipping/pickup-locations/sync/", "staff.manage_pickup_locations"),
    *[
        ("get", f"insights/{name}/", "staff.view_insights")
        for name in ["forecasts", "print-runs", "backtests", "item-stats", "chapter-stats", "cohorts"]
        + ["code-activation", "delivery", "fraud-signals", "offers"]
    ],
    ("post", "insights/fraud-signals/{signal}/acknowledge/", "staff.acknowledge_signal"),
]


def app_objects():
    """A parcel typed by hand (no courier to ask: nothing leaves the test) and what hangs on it."""
    order = make_order((ProductFactory(stock=5), 1))
    parcel = Shipment.objects.create(order=order, courier="India Post", tracking_number="EA123456789IN")
    account = IntegrationAccount.objects.create(provider="shiprocket", mode="test", enabled=False)
    now = timezone.now()
    return {
        "order": order.number,
        "parcel": parcel.pk,
        "exception": ShippingException.objects.create(shipment=parcel, kind="ndr", due_at=now).pk,
        "remittance": CodRemittance.objects.create(shipment=parcel, expected_amount=299, expected_on=now.date()).pk,
        "charge": ShipmentCharge.objects.create(
            shipment=parcel, account=account, kind="freight", amount=63, statement_line_id="1", charged_at=now
        ).pk,
        "pickup": PickupLocation.objects.create(nickname="Primary", pin_code="781024", is_default=True).pk,
        "signal": FraudSignal.objects.create(
            kind="codes_failed_account", subject="a" * 64, count=6, window_start=now, window_end=now
        ).pk,
    }


@pytest.mark.parametrize(("method", "path", "perm"), APP_ENDPOINTS, ids=[f"{m} {p}" for m, p, _ in APP_ENDPOINTS])
def test_each_role_reaches_the_shipping_and_insights_endpoints_only_with_their_permission(method, path, perm, subtests):
    reach(method, "/api/v1/" + path.format(**app_objects()), perm, subtests)


def test_the_manifest_and_the_catalogue_are_every_staff_members_and_nobody_elses(subtests):
    for path in ["session/", "catalogue/"]:
        for who in WHO:
            with subtests.test(path=path, who=who):
                assert signed_in(make_staff(who)).get(STAFF + path).status_code == 200
        student = UserFactory()
        assert signed_in(student).get(STAFF + path).status_code == 403
        assert AuditEvent.objects.filter(action="authz_fail", actor_id=student.pk).exists()


def test_signed_out_and_the_apps_tokens_get_nothing():
    from rest_framework.test import APIClient
    from rest_framework_simplejwt.tokens import RefreshToken

    signed_out = APIClient().get(STAFF + "session/")  # refused, and not logged: Caddy's access log has it
    assert signed_out.status_code == 401 and signed_out["WWW-Authenticate"] == "Api-Key"
    assert signed_out.json()["code"] == "not_authenticated"  # every error has its code beside its detail
    api = APIClient()
    owner = make_staff(roles.OWNER)
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(owner).access_token}")
    assert api.get(STAFF + "users/").status_code == 401  # the app's JWT is not the panel's session
    assert not AuditEvent.objects.filter(action="authz_fail", actor_type="anonymous").exists()


def views():
    """(path, the view class, the action or method names it serves) for every staff URL: the staff API's, and the
    rest of the API's staff views (the shipping app's, the insights')."""

    def walk(patterns, prefix=""):
        for pattern in patterns:
            if isinstance(pattern, URLResolver):
                yield from walk(pattern.url_patterns, prefix + str(pattern.pattern))
            elif isinstance(pattern, URLPattern):
                yield prefix + str(pattern.pattern), pattern.callback

    others = [(path, callback) for path, callback in walk(api_urls.urlpatterns)
              if issubclass(getattr(callback, "cls", object), StaffView)]  # fmt: skip
    assert len(others) > 20, others
    for path, callback in [*walk(staff_urls.urlpatterns), *others]:
        cls = callback.cls
        if actions := getattr(callback, "actions", None):  # a viewset's route: method → action
            yield path, cls, sorted(actions.items())
        else:
            methods = [name.upper() for name in ("get", "post", "put", "patch", "delete") if hasattr(cls, name)]
            yield path, cls, [(method.lower(), method) for method in methods]


def test_every_endpoint_names_a_catalogued_permission_and_a_view_one_for_get():
    from rest_framework.test import APIRequestFactory

    from staff.api import InviteAcceptView

    checked = 0
    for path, cls, served in views():
        if cls is InviteAcceptView:  # the invitation's link: for people not yet staff, the token is the credential
            continue
        for method, name in served:
            view = cls()
            view.action, view.kwargs = name, {"key": "SHOP_OPEN"}
            request = getattr(APIRequestFactory(), method)("/")
            perm = view.required_permission(request)
            assert perm, (path, method, name)
            checked += 1
            if perm == ANY_STAFF:
                assert path in ("session/", "catalogue/"), path
                continue
            assert catalogue.entry(perm) is not None, (path, name, perm)
            if method == "get" and (cls, name) not in BOOKING_READS:
                assert ".view_" in perm, (path, name, perm)
    assert checked > 100, checked


# Two reads that need more than a view_ permission: the courier's quote (asked of the courier, for a booking) and the
# label's PDF (the customer's address on it): the packing room's, staff.book_parcel.
BOOKING_READS = {(OrderQuoteView, "GET"), (ShipmentViewSet, "label")}


def test_api_md_lists_every_staff_endpoint_and_field_as_the_code_has_them():
    from django.conf import settings

    from staff.management.commands.staff_api_reference import reference

    text = (settings.BASE_DIR / "API.md").read_text()
    start, end = "<!-- staff-api-reference -->\n", "<!-- /staff-api-reference -->"
    listed = text[text.index(start) + len(start) : text.index(end)]
    assert listed == reference(), "API.md is behind: run manage.py staff_api_reference and paste its output there"
