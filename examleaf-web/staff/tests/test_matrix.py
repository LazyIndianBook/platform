"""The authorization matrix (research 1.9, OWASP: test the authorization logic): every role × every staff endpoint and
method (the staff API's, the shipping app's and the insights'). A role without the endpoint's permission gets 403 and
leaves an `authz_fail` event; a role with it never gets 403 (its answer may be 400 for the empty body, 404 for an object
out of its reach, or 200). And every endpoint names a catalogued permission, a view_ one for GET (DRF's pitfall:
DjangoModelPermissions lets any GET through)."""

from datetime import timedelta

import httpx
import pytest
from django.urls import URLPattern, URLResolver
from django.utils import timezone

from accounts import roles
from accounts.factories import UserFactory
from accounts.models import DeletionRequest, LegalHold
from api import urls as api_urls
from insights.models import FraudSignal
from integrations.models import InboundEvent, IntegrationAccount, IntegrationFailure
from ops.models import MessageTemplate
from shipping.api import OrderQuoteView, ShipmentViewSet
from shipping.models import CodRemittance, PickupLocation, ShipmentCharge, ShippingException
from shop import services as shop
from shop.factories import ProductFactory, captured, make_order
from shop.models import Invoice, Order, QuoteRequest, Refund, ReturnRequest, Shipment
from shop.staff_orders import OrderViewSet
from staff import approvals, catalogue
from staff import urls as staff_urls
from staff.api import StaffView
from staff.audit import record
from staff.models import (
    ApiKey,
    AuditEvent,
    ChangeRequest,
    DarkPatternAudit,
    DataRequest,
    InboxItem,
    Incident,
    Job,
    ProcessorRecord,
    SavedView,
    StaffInvite,
    StaffOffboarding,
    StaffScope,
)
from staff.permissions import ANY_STAFF
from support import services as support_services
from support.models import SavedReply

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
    ("get", "notes/?target_type=accounts.user&target_id={customer}", "staff.view_note"),  # (and the record's own)
    ("post", "notes/", "staff.add_note"),
    # Tax (shop/staff_tax.py)
    ("get", "tax/hsn/", "shop.view_hsncode"),
    ("get", "tax/hsn/4901/", "shop.view_hsncode"),
    ("post", "tax/hsn/", "shop.change_hsncode"),
    ("post", "tax/hsn/4901/rates/", "shop.change_hsncode"),
    ("get", "tax/problems/", "shop.view_hsncode"),
    ("get", "tax/documents/", "shop.view_documentseries"),
    ("get", "tax/documents/{document}/", "shop.view_documentseries"),
    ("get", "tax/documents/{document}/pdf/", "shop.view_documentseries"),  # not made yet: 404
    ("post", "tax/documents/{document}/cancel/", "staff.cancel_document"),
    ("get", "tax/series/", "shop.view_documentseries"),
    ("get", "tax/thresholds/", "shop.view_taxthreshold"),
    ("get", "tax/calendar/", "shop.view_taxthreshold"),
    ("post", "tax/gstr1/", "staff.run_gstr1"),
    # Legal and privacy (staff/privacy_api.py)
    ("get", "privacy/cockpit/", "staff.view_datarequest"),
    ("get", "privacy/retention/", "staff.view_datarequest"),
    ("get", "privacy/holds/", "accounts.view_legalhold"),
    ("get", "privacy/holds/{hold}/", "accounts.view_legalhold"),
    ("post", "privacy/holds/", "staff.manage_holds"),
    ("post", "privacy/holds/{hold}/release/", "staff.manage_holds"),
    ("get", "privacy/nominees/{customer}/", "accounts.view_user"),
    ("post", "privacy/nominees/{customer}/reveal/", "staff.reveal_contact"),
    ("post", "privacy/deletions/{deletion}/parent-confirmation/", "staff.handle_data_request"),
    ("get", "privacy/policies/", "pages.view_page"),
    ("get", "privacy/policies/privacy/", "pages.view_page"),
    ("get", "privacy/policies/privacy/versions/1/diff/", "pages.view_page"),
    ("post", "privacy/policies/privacy/publish/", "pages.change_page"),
    ("post", "privacy/policies/privacy/cancel-scheduled/", "pages.change_page"),
    ("get", "privacy/disclosures/", "staff.view_sitesetting"),
    ("put", "privacy/disclosures/", "staff.manage_settings"),
    ("get", "privacy/dark-pattern-audits/", "staff.view_darkpatternaudit"),
    ("get", "privacy/dark-pattern-audits/{audit}/", "staff.view_darkpatternaudit"),
    ("post", "privacy/dark-pattern-audits/", "staff.manage_compliance"),
    ("patch", "privacy/dark-pattern-audits/{audit}/", "staff.manage_compliance"),
    ("post", "privacy/dark-pattern-audits/{audit}/complete/", "staff.manage_compliance"),
    ("get", "privacy/dark-pattern-audits/{audit}/file/", "staff.view_darkpatternaudit"),
    ("post", "privacy/dark-pattern-audits/{audit}/file/", "staff.manage_compliance"),
    # Orders (shop/staff_orders.py)
    ("get", "orders/", "shop.view_order"),
    ("post", "orders/", "shop.add_order"),
    ("post", "orders/preview/", "shop.add_order"),
    ("get", "orders/products/", "shop.view_product"),
    ("get", "orders/packing/", "shop.view_order"),
    ("post", "orders/pick-list/", "staff.pack_order"),
    ("get", "orders/{order}/", "shop.view_order"),
    ("get", "orders/{order}/documents/packing-slip/", "staff.pack_order"),  # the address on it
    ("get", "orders/{order}/documents/label/", "staff.pack_order"),
    ("get", "orders/{order}/invoice/", "shop.view_invoice"),
    ("get", "orders/{order}/credit-notes/1/", "shop.view_creditnote"),
    ("post", "orders/{order}/tags/", "shop.change_order"),
    ("post", "orders/{order}/hold/", "shop.change_order"),
    ("post", "orders/{order}/release/", "shop.change_order"),
    ("post", "orders/{order}/notify/", "shop.change_order"),
    ("post", "orders/{order}/payment-link/", "shop.change_order"),
    ("post", "orders/{order}/invoice/regenerate/", "shop.change_order"),
    ("post", "orders/{order}/invoice/resend/", "shop.change_order"),
    ("post", "orders/{order}/refunds/", "staff.refund_order"),
    ("post", "orders/{order}/offline-payment/", "staff.record_offline_payment"),
    ("post", "orders/{order}/returns/", "staff.handle_return"),
    ("post", "orders/{order}/cancel/", "shop.change_order"),
    ("post", "orders/{order}/pack/", "staff.pack_order"),
    ("post", "orders/{order}/ship/", "staff.pack_order"),
    ("post", "orders/{order}/deliver/", "staff.pack_order"),
    ("get", "orders/returns/", "shop.view_returnrequest"),
    ("get", "orders/returns/{back}/", "shop.view_returnrequest"),
    ("get", "orders/returns/{back}/photos/0/", "shop.view_returnrequest"),
    ("post", "orders/returns/{back}/approve/", "staff.handle_return"),
    ("post", "orders/returns/{back}/decline/", "staff.handle_return"),
    ("post", "orders/returns/{back}/label/", "staff.handle_return"),
    ("post", "orders/returns/{back}/receive/", "staff.receive_return"),
    ("post", "orders/returns/{back}/inspect/", "staff.receive_return"),
    ("post", "orders/returns/{back}/photos/", "staff.receive_return"),
    ("post", "orders/refunds/{refund}/mark-paid/", "staff.approve_refund"),
    ("post", "orders/refunds/{refund}/payee/", "staff.approve_refund"),
    ("get", "orders/quotes/", "shop.view_quoterequest"),
    ("get", "orders/quotes/{quote}/", "shop.view_quoterequest"),
    ("get", "orders/quotes/{quote}/quotation/", "shop.view_quoterequest"),
    ("post", "orders/quotes/{quote}/convert/", "shop.change_quoterequest"),
    # Phase B: the people pages' additions, settings' history, the connections, the templates, the system's pages
    ("get", "people/roles/", "staff.view_staff"),
    ("get", "people/{person}/access/", "staff.view_staff"),
    ("post", "people/{person}/roles/preview/", "staff.view_staff"),
    ("get", "people/{person}/erp/", "staff.view_staff"),
    ("get", "people/{person}/offboarding/", "staff.view_staffoffboarding"),
    ("post", "people/{person}/offboarding/tick/", "staff.assign_role"),
    ("get", "settings/SHOP_OPEN/history/", "staff.view_sitesetting"),
    ("get", "flags/ERP_ENABLED/history/", "staff.view_featureflag"),
    ("get", "connections/", "integrations.view_integrationaccount"),
    ("get", "connections/shiprocket/", "integrations.view_integrationaccount"),
    ("post", "connections/shiprocket/test/", "staff.manage_connections"),
    ("post", "connections/shiprocket/credentials/", "staff.manage_connections"),
    ("post", "connections/shiprocket/mode/", "staff.manage_connections"),
    ("post", "connections/shiprocket/circuit/", "staff.manage_connections"),
    ("get", "connections/shiprocket/webhooks/", "integrations.view_integrationaccount"),
    ("post", "connections/shiprocket/webhooks/rotate/", "staff.manage_connections"),
    ("get", "connections/shiprocket/events/", "integrations.view_inboundevent"),
    ("post", "connections/shiprocket/events/replay-failed/", "staff.replay_webhook"),
    ("post", "connections/shiprocket/events/{inbound}/replay/", "staff.replay_webhook"),
    ("get", "connections/shiprocket/calls/", "integrations.view_integrationcall"),
    ("get", "connections/shiprocket/failures/", "integrations.view_integrationfailure"),
    ("post", "connections/shiprocket/failures/{failure}/replay/", "staff.replay_webhook"),
    ("post", "connections/shiprocket/failures/{failure}/discard/", "staff.replay_webhook"),
    ("post", "connections/erpnext/failures/{erp_failure}/discard/", "erp.replay_sync"),  # the sync's own rule
    ("get", "templates/", "ops.view_messagetemplate"),
    ("get", "templates/{template}/", "ops.view_messagetemplate"),
    ("post", "templates/", "ops.add_messagetemplate"),
    ("patch", "templates/{template}/", "ops.change_messagetemplate"),
    ("post", "templates/{template}/test/", "ops.change_messagetemplate"),
    ("get", "system/sync/", "erp.view_sync"),
    ("get", "system/sync/links/?q=EL-2026", "erp.view_sync"),
    ("get", "system/backups/", "staff.view_system"),
    ("get", "system/backups/drills/", "staff.view_restoredrill"),
    ("post", "system/backups/drills/", "staff.manage_system"),
    ("get", "system/logs/", "staff.view_system"),
    ("get", "system/dependencies/", "staff.view_system"),
    ("get", "system/hardening/", "staff.view_system"),
    ("get", "system/scripts/", "staff.view_scriptinventory"),
    # Content (Phase B): content/staff_api.py
    ("get", "content/summary/", "content.view_errorreport"),
    ("get", "content/books/", "content.view_book"),
    ("post", "content/books/", "content.add_book"),
    ("get", "content/books/{book}/", "content.view_book"),
    ("patch", "content/books/{book}/", "content.change_book"),
    ("get", "content/books/{book}/history/", "content.view_book"),
    ("post", "content/books/{book}/history/{book_version}/restore/", "content.change_book"),
    ("get", "content/papers/", "content.view_paper"),
    ("get", "content/papers/{paper}/", "content.view_paper"),
    ("patch", "content/papers/{paper}/", "content.change_paper"),
    ("post", "content/papers/{paper}/publish/", "staff.publish_paper"),
    ("get", "content/papers/{paper}/history/", "content.view_paper"),
    ("post", "content/papers/{paper}/history/{paper_version}/restore/", "content.change_paper"),
    ("get", "content/papers/{paper}/qr/", "content.view_paper"),
    *[
        row
        for model in ["question", "solution"]
        for row in [
            ("get", f"content/{model}s/", f"content.view_{model}"),
            ("get", f"content/{model}s/{{{model}}}/", f"content.view_{model}"),
            ("patch", f"content/{model}s/{{{model}}}/", f"content.change_{model}"),
            ("get", f"content/{model}s/{{{model}}}/history/", f"content.view_{model}"),
            ("post", f"content/{model}s/{{{model}}}/history/{{{model}_version}}/restore/", f"content.change_{model}"),
            ("post", f"content/{model}s/{{{model}}}/submit/", f"content.change_{model}"),
            ("post", f"content/{model}s/{{{model}}}/discard/", f"content.change_{model}"),
            ("post", f"content/{model}s/{{{model}}}/rollback/", "staff.publish_paper"),
        ]
    ],
    ("get", "content/reviews/", "content.view_reviewtask"),
    ("get", "content/reviews/{review}/", "content.view_reviewtask"),
    *[("post", f"content/reviews/{{review}}/{verb}/", "staff.publish_paper") for verb in ["approve", "needs-changes"]],
    ("post", "content/reviews/{review}/publish/", "staff.publish_paper"),
    ("get", "content/reports/", "content.view_errorreport"),
    ("get", "content/reports/{report}/", "content.view_errorreport"),
    ("patch", "content/reports/{report}/", "staff.triage_report"),
    *[
        ("post", f"content/reports/{{report}}/{verb}/", "staff.triage_report")
        for verb in ["confirm", "reject", "fix-online", "fix-in-printing", "reopen", "tell"]
    ],
    ("get", "content/errata/", "content.view_errorreport"),
    ("get", "content/imports/", "content.view_paper"),
    ("get", "content/legal-deposits/", "content.view_legaldeposit"),
    ("post", "content/legal-deposits/", "content.add_legaldeposit"),
    ("get", "content/legal-deposits/missing/", "content.view_legaldeposit"),
    ("get", "content/legal-deposits/{deposit}/", "content.view_legaldeposit"),
    ("get", "content/legal-deposits/{deposit}/proof/", "content.view_legaldeposit"),  # 404 without a scan
    # support (support/api.py): tickets, their actions (each its own permission), saved replies, the numbers
    ("get", "support/tickets/", "support.view_ticket"),
    ("post", "support/tickets/", "staff.handle_ticket"),
    ("get", "support/tickets/{ticket}/", "support.view_ticket"),
    ("patch", "support/tickets/{ticket}/", "staff.handle_ticket"),
    ("post", "support/tickets/{ticket}/messages/", "staff.handle_ticket"),  # a note: support.note_ticket
    ("post", "support/tickets/{ticket}/assign/", "staff.handle_ticket"),
    ("post", "support/tickets/{ticket}/claim/", "staff.handle_ticket"),
    ("post", "support/tickets/{ticket}/status/", "staff.handle_ticket"),
    ("post", "support/tickets/{ticket}/reopen/", "staff.handle_ticket"),
    ("post", "support/tickets/{ticket}/acknowledge/", "staff.handle_ticket"),
    ("post", "support/tickets/{ticket}/reveal/", "staff.reveal_contact"),
    ("get", "support/tickets/{ticket}/attachments/{attachment}/", "support.view_ticket"),
    ("post", "support/tickets/{ticket}/refund/", "staff.refund_order"),
    ("post", "support/tickets/{ticket}/cancel/", "shop.change_order"),
    ("post", "support/tickets/{ticket}/resend-invoice/", "staff.handle_ticket"),
    ("post", "support/tickets/{ticket}/resend-confirmation/", "staff.handle_ticket"),
    ("post", "support/tickets/{ticket}/extend-access/", "learn.change_entitlement"),
    ("post", "support/tickets/{ticket}/book-code/", "learn.view_bookcode"),
    ("post", "support/tickets/{ticket}/data-request/", "staff.handle_data_request"),
    ("get", "support/saved-replies/", "support.view_savedreply"),
    ("post", "support/saved-replies/", "support.add_savedreply"),
    ("get", "support/saved-replies/{reply}/", "support.view_savedreply"),
    ("patch", "support/saved-replies/{reply}/", "support.change_savedreply"),
    ("delete", "support/saved-replies/{reply}/", "support.delete_savedreply"),
    ("post", "support/saved-replies/{reply}/restore/", "support.delete_savedreply"),
    ("get", "support/summary/", "support.view_ticket"),
    ("get", "support/agents/", "support.view_ticket"),
    # Course (Phase B): learn/staff_api.py
    ("get", "course/subjects/", "learn.view_chapter"),
    ("get", "course/subjects/{course_subject}/outline/", "learn.view_chapter"),
    ("patch", "course/chapters/{chapter}/", "learn.change_chapter"),
    ("get", "course/revisions/{revision}/", "learn.view_revision"),
    ("patch", "course/revisions/{revision}/", "learn.change_revision"),
    ("post", "course/revisions/{revision}/submit/", "learn.change_revision"),  # (in review: 400)
    *[
        ("post", f"course/revisions/{{revision}}/{verb}/", "staff.publish_course")
        for verb in ["approve", "needs-changes", "publish", "unpublish"]
    ],
    *[
        row
        for kind, model, key in [
            ("clips", "clip", "clip"),
            ("cards", "flashcard", "card"),
            ("items", "quizitem", "quiz_item"),
        ]  # fmt: skip
        for row in [
            ("get", f"course/{kind}/{{{key}}}/", f"learn.view_{model}"),
            ("patch", f"course/{kind}/{{{key}}}/", f"learn.change_{model}"),
            ("post", f"course/{kind}/{{{key}}}/move/", f"learn.change_{model}"),
            ("post", f"course/{kind}/{{{key}}}/restore/", f"learn.change_{model}"),
            ("delete", f"course/{kind}/{{{key}}}/", f"learn.delete_{model}"),
        ]
    ],
    ("post", "course/clips/{clip}/retry/", "learn.change_clip"),
    ("get", "course/items/", "learn.view_quizitem"),
    ("get", "course/items/{quiz_item}/history/", "learn.view_quizitem"),
    ("post", "course/items/{quiz_item}/flag/", "staff.triage_report"),
    ("get", "course/bin/", "learn.view_clip"),
    ("get", "course/bin/?kind=items", "learn.view_quizitem"),
    ("get", "course/entitlements/", "learn.view_entitlement"),
    ("get", "course/entitlements/{entitlement}/", "learn.view_entitlement"),
    ("post", "course/entitlements/", "learn.add_entitlement"),
    ("post", "course/entitlements/{entitlement}/extend/", "learn.change_entitlement"),
    ("post", "course/entitlements/{entitlement}/revoke/", "learn.change_entitlement"),
    ("get", "course/codes/batches/", "learn.view_codebatch"),
    ("get", "course/codes/batches/{batch}/", "learn.view_codebatch"),
    ("post", "course/codes/batches/", "staff.make_book_codes"),
    ("post", "course/codes/batches/{batch}/dispatched/", "learn.change_codebatch"),
    ("post", "course/codes/batches/{batch}/void/", "staff.void_book_codes"),
    ("post", "course/codes/void/", "staff.void_book_codes"),
    ("post", "course/codes/lookup/", "learn.view_bookcode"),
    ("get", "course/codes/report/", "learn.view_codebatch"),
    ("get", "course/learners/{learner}/", "learn.view_entitlement"),
    ("post", "course/learners/{learner}/devices/{device}/sign-out/", "staff.end_user_sessions"),
    ("post", "people/{person}/offboard/", "staff.assign_role"),  # last: the person goes
]


@pytest.fixture(autouse=True)
def own_pages(monkeypatch):
    """The hardening page's fetch of the console's robots.txt answered here: nothing leaves the tests."""
    answer = httpx.MockTransport(lambda request: httpx.Response(200, text="User-agent: *\nDisallow: /\n"))
    monkeypatch.setattr("staff.system_api.network_transport", lambda: answer)


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
    document = Invoice.objects.create(
        order=make_order((ProductFactory(stock=5), 1)), number="EL/2026-27/00001", financial_year="2026-27", serial=1,
        series="EL", document_type="bill_of_supply",
    )  # fmt: skip
    order, delivered = make_order((ProductFactory(stock=5), 1)), make_order((ProductFactory(stock=5), 2))
    shop.record_capture(captured(order))
    Order.objects.filter(pk=delivered.pk).update(status="delivered", placed_at=timezone.now())
    back = ReturnRequest.objects.create(order=delivered, lines=[{"item": delivered.items.get().pk, "quantity": 1}],
                                        reason="damaged")  # fmt: skip
    payment = delivered.payments.get()
    refund = Refund.objects.create(order=delivered, payment=payment, amount=10, reason="Damaged", method="bank")
    quote = QuoteRequest.objects.create(school="Cotton Collegiate", contact_name="Anita Das", email="o@example.com",
                                        phone="+919864012345", delivery_pin="781001",
                                        items=[{"product": "x", "title": "X", "quantity": 1}])  # fmt: skip
    ticket = support_services.create_ticket(
        source="email", channel="email", subject="Late parcel", body="Where is it?", email="a@example.com",
        category="order",
    )  # fmt: skip
    message = ticket.messages.get()
    support_services.save_attachments(message, [("photo.png", "image/png", b"\x89PNG")])
    return {
        "document": document.number.replace("/", "-"),
        "order": order.number,
        "back": back.pk,
        "refund": refund.pk,
        "quote": quote.pk,
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
        "hold": LegalHold.objects.create(user=customer, reason="dispute").pk,
        "deletion": DeletionRequest.objects.create(user=customer).pk,
        "audit": DarkPatternAudit.objects.create(year=2027).pk,
        "ticket": ticket.number,
        "attachment": message.attachments.get().pk,
        "reply": SavedReply.objects.create(title="Hello", body="Hello {name|there}").pk,
        **phase_b_objects(person),
    }


def phase_b_objects(person):
    """An offboarding's checklist, a provider's event and dead letter (ERPNext's too), a message template."""
    StaffOffboarding.objects.create(user=person, reason="Testing the checklist")
    failure = {"task_name": "integrations.tasks.purge_old_records", "last_error": "IntegrationUnavailable: no answer"}
    erp = IntegrationAccount.objects.create(provider="erpnext", mode="live")
    return {
        "inbound": InboundEvent.objects.create(provider="shiprocket", body="{}", sha256="a" * 64).pk,
        "failure": IntegrationFailure.objects.create(operation="track", task_id="t-1", **failure).pk,
        "erp_failure": IntegrationFailure.objects.create(account=erp, operation="sync", task_id="t-2", **failure).pk,
        "template": MessageTemplate.objects.create(event="otp", channel="sms", category="transactional").pk,
        **content_objects(),
        **course_objects(),
    }


def course_objects():
    """A published course of a chapter (its revision in review, submitted by an editor), a learner with an
    entitlement and a phone, a print run's batch of one code."""
    from content.models import Subject
    from learn.models import Chapter, Clip, CodeBatch, Device, Entitlement, FlashCard, QuizItem, Revision
    from learn.services import make_codes
    from learn.tests import make_course

    subject = make_course(subject=Subject.objects.get(code="PHY"), chapters=1, clips=2)
    revision = Revision.objects.get(chapter__subject=subject)
    Revision.objects.filter(pk=revision.pk).update(status="review", submitted_by=make_staff(roles.CONTENT_EDITOR))
    learner = UserFactory()
    entitlement = Entitlement.objects.create(
        user=learner, subject=subject, valid_until=timezone.localdate() + timedelta(days=30)
    )
    make_codes(subject, 1, "PHY-2027-1")
    CodeBatch.objects.create(label="PHY-2027-1", subject=subject, printed=1, generated_at=timezone.now())
    return {
        "course_subject": subject.pk,
        "chapter": Chapter.objects.get(subject=subject).pk,
        "revision": revision.pk,
        "clip": Clip.objects.filter(revision=revision).order_by("order").first().pk,
        "card": FlashCard.objects.get(chapter__subject=subject).pk,
        "quiz_item": QuizItem.objects.get(chapter__subject=subject).pk,
        "entitlement": entitlement.pk,
        "batch": "PHY-2027-1",
        "learner": learner.pk,
        "device": Device.objects.create(user=learner, token="fid-matrix", platform="android").pk,
    }


def content_objects():
    """A paper with a question and a solution whose draft waits in a review (someone else's edit), a reported
    mistake, a legal deposit, and a version of each record."""
    from content.conftest import make_paper
    from content.models import ErrorReport, LegalDeposit, ReviewTask, Solution

    paper = make_paper()
    solution = Solution.objects.get(question__paper=paper)
    editor = make_staff(roles.CONTENT_EDITOR)
    Solution.objects.filter(pk=solution.pk).update(draft={"body_md": "$x = 1$"}, state="in_review", draft_by=editor)
    review = ReviewTask.objects.create(
        target=solution, subject=paper.book.subject, paper=paper, label="PHY-E01 2(c), solution",
        draft={"body_md": "$x = 1$"}, submitted_by=editor, edited_by=editor,
    )  # fmt: skip
    report = ErrorReport.objects.create(
        target=solution, subject=paper.book.subject, paper=paper, question=solution.question, category="typo"
    )
    deposit = LegalDeposit.objects.create(
        book=paper.book, edition=paper.book.edition, library="connemara", sent_on=timezone.localdate(), proof="Post"
    )
    version = lambda obj: obj.history.order_by("-history_id").first().history_id  # noqa: E731
    return {
        "book": paper.book.pk,
        "book_version": version(paper.book),
        "paper": paper.pk,
        "paper_version": version(paper),
        "question": solution.question.pk,
        "question_version": version(solution.question),
        "solution": solution.pk,
        "solution_version": version(solution),
        "review": review.pk,
        "report": report.pk,
        "deposit": deposit.pk,
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
    for path in ["session/", "catalogue/", "people/me/sessions/"]:
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
                assert path in ANY_STAFF_PATHS, path
                continue
            assert catalogue.entry(perm) is not None, (path, name, perm)
            if method == "get" and (cls, name) not in BOOKING_READS:
                assert ".view_" in perm, (path, name, perm)
    assert checked > 100, checked


ANY_STAFF_PATHS = (  # every member of staff's own: the manifest, the catalogue, the policies, their own sessions
    *["session/", "session/reason/", "catalogue/", "policies/ack/", "^people/me/sessions/$"],
    *["^people/me/sessions/end-others/$", r"^people/me/sessions/(?P<session>\d+)/end/$"],
)
# Two reads that need more than a view_ permission: the courier's quote (asked of the courier, for a booking) and the
# label's PDF (the customer's address on it): the packing room's, staff.book_parcel. And the Orders module's packing
# slip and hand label (the address whole on each): staff.pack_order.
BOOKING_READS = {(OrderQuoteView, "GET"), (ShipmentViewSet, "label")}
BOOKING_READS |= {(OrderViewSet, "packing_slip"), (OrderViewSet, "label")}


def test_api_md_lists_every_staff_endpoint_and_field_as_the_code_has_them():
    from django.conf import settings

    from staff.management.commands.staff_api_reference import reference

    text = (settings.BASE_DIR / "API.md").read_text()
    start, end = "<!-- staff-api-reference -->\n", "<!-- /staff-api-reference -->"
    listed = text[text.index(start) + len(start) : text.index(end)]
    assert listed == reference(), "API.md is behind: run manage.py staff_api_reference and paste its output there"
