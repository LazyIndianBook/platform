"""Audit completeness (plan 9.2; research 3.1): every change made through the staff API is an audit event naming its
target, with no person's details in it. A walk of every POST, PUT, PATCH and DELETE row of the authorization tables as
an owner (every permission, re-authenticated a moment ago), with a valid body where one is simple (BODIES), or the
record first put in the state the action needs (PREPARE, which may point the row at a record that fits), asserts the
answer succeeds and leaves new events by the owner, naming a target where the action has one and holding none of the
fixtures' personal details. A row whose success needs more than that (an upload, a provider's answer, a long set-up)
is listed in COVERED with the test that asserts its event, checked here to exist and to read the log; a row that
changes no record (a preview, a calculation, a person's own saved lists, a method the view refuses) in EXEMPT, with
why; the shipping app's courier calls (Phase A) in COURIER. A test asserts the tables cover every change row."""

import inspect
import json
from datetime import date, timedelta
from importlib import import_module

import pytest
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from accounts import roles
from staff.models import AuditEvent

from .conftest import STAFF, make_staff, signed_in
from .test_matrix import ANY_STAFF_ENDPOINTS, APP_ENDPOINTS, ENDPOINTS, app_objects, objects

pytestmark = pytest.mark.django_db
ROWS = [("staff", m, p) for m, p, _ in ENDPOINTS + ANY_STAFF_ENDPOINTS if m != "get"]
ROWS += [("app", m, p) for m, p, _ in APP_ENDPOINTS if m != "get"]
WHY = {"reason": "Testing the audit trail"}
SOON = (timezone.now() + timedelta(days=1)).isoformat()


def picture():
    from io import BytesIO

    from PIL import Image

    image = BytesIO()
    Image.new("RGB", (4, 4), "white").save(image, "PNG")
    return SimpleUploadedFile("photo.png", image.getvalue(), content_type="image/png")


BODIES = {  # (method, path): the body, or a function of (the objects, the owner) giving it
    ("post", "inbox/{item}/snooze/"): {"until": SOON},
    ("post", "inbox/{item}/assign/"): lambda made, owner: {"assignee": owner.pk},
    ("post", "jobs/"): {"kind": "audit_export", "params": {"filters": {}}},
    ("post", "change-requests/"): lambda made, owner: {
        "action": "order.refund",
        "target": made["order"],
        "payload": {},
        **WHY,
    },  # fmt: skip
    ("post", "change-requests/{change}/approve/"): lambda made, owner: {"payload_sha256": sha(made)},
    ("put", "settings/SHOP_OPEN/"): {"value": False, **WHY},
    ("put", "settings/MAINTENANCE_BANNER/"): {"value": "Back at noon", **WHY},
    ("put", "flags/ERP_SYNC_ORDERS/"): {"value": True, **WHY},
    ("post", "api-keys/"): {"name": "Audited", "scopes": ["shop.view_order"]},
    ("post", "people/invite/"): {"email": "new.person@examleaf.in", "role": roles.SUPPORT, **WHY},
    ("post", "people/{person}/roles/"): {"role": roles.SALES, **WHY},
    ("post", "people/{person}/scopes/"): {"kind": "subject", "value": "CHE"},
    ("post", "people/{person}/reset-mfa/"): WHY,
    ("post", "users/{customer}/reveal/"): {"show": ["email"], **WHY},
    ("post", "users/{customer}/suspend/"): WHY,
    ("post", "users/{customer}/reset-mfa/"): WHY,
    ("post", "users/{customer}/impersonate/"): {"ticket": "SR-2026-000001", **WHY},
    ("post", "data-requests/"): {
        "kind": "access",
        "channel": "email",
        "requester": "x@example.com",
        "summary": "A copy of my data",
    },  # fmt: skip
    ("post", "data-requests/{request}/verify-identity/"): {"note": "Called back on the number given"},
    ("post", "data-requests/{request}/close/"): {"outcome": "done", "response": "Sent by post."},
    ("post", "data-requests/{request}/reveal/"): WHY,
    ("post", "incidents/"): {"title": "A laptop lost", "kind": "data_leak"},
    ("post", "processors/"): {"name": "Brevo", "purpose": "email", "data_categories": "email", "country": "France"},
    ("put", "processors/{processor}/"): {
        "name": "Razorpay",
        "purpose": "payments",
        "data_categories": "orders",
        "country": "India",
    },  # fmt: skip
    ("post", "notes/"): lambda made, owner: {
        "target_type": "accounts.user",
        "target_id": made["customer"],
        "body": "Called back",
    },  # fmt: skip
    ("post", "tax/hsn/"): {
        "code": "49119990",
        "kind": "hsn",
        "description": "Other printed matter",
        "first_rate": {
            "rate": "12",
            "taxability": "taxable",
            "effective_from": "2025-09-22",
            "notification": "9/2025-CT(Rate)",
        },
    },  # fmt: skip
    ("post", "tax/documents/{document}/cancel/"): WHY,
    ("post", "tax/gstr1/"): {"month": "2026-09"},
    ("post", "privacy/holds/"): lambda made, owner: {"user": made["customer"], "reason": "dispute"},
    ("post", "privacy/holds/{hold}/release/"): WHY,
    ("put", "privacy/disclosures/"): {"values": {"DISCLOSURE_CARE_PHONE": "1800 123 4567"}, **WHY},
    ("post", "privacy/policies/privacy/publish/"): {
        "markdown": "# Privacy\n\nWho we are, again.",
        "summary": "The contact block moved up",
    },  # fmt: skip
    ("post", "privacy/dark-pattern-audits/"): {"year": 2026},
    ("post", "orders/pick-list/"): lambda made, owner: {"orders": [made["order"]]},
    ("post", "orders/{order}/hold/"): WHY,
    ("post", "orders/{order}/notify/"): {"kind": "paid"},
    ("post", "orders/{order}/refunds/"): WHY,
    ("post", "orders/{order}/cancel/"): WHY,
    ("post", "orders/{order}/tags/"): {"add": ["school"]},
    ("post", "orders/returns/{back}/decline/"): {"note": "Not damaged in the photos"},
    ("post", "orders/refunds/{refund}/mark-paid/"): {"utr": "UTR123456789"},
    ("post", "connections/shiprocket/events/replay-failed/"): {"since": "2026-01-01T00:00:00Z"},
    ("post", "connections/erpnext/failures/{erp_failure}/discard/"): WHY,
    ("post", "templates/"): {"event": "order_shipped", "channel": "sms", "category": "transactional"},
    ("patch", "templates/{template}/"): {
        "variables": [{"name": "otp", "type": "numeric", "max_length": 6}],
        "notes": "Approved on the DLT portal",
    },  # fmt: skip
    ("post", "content/books/"): lambda made, owner: {
        "title": "Chemistry 2027",
        "subject": physics(),
        "slug": "chemistry-2027-audit",
    },  # fmt: skip
    ("patch", "content/books/{book}/"): {"title": "ExamLeaf Physics Sample Papers 2027, revised"},
    ("patch", "content/papers/{paper}/"): {"title": "Paper 1, revised"},
    ("post", "content/papers/{paper}/publish/"): {"is_published": False},
    ("patch", "content/questions/{question}/"): {"text_md": "A new question?"},
    ("patch", "content/solutions/{solution}/"): {"body_md": "$x = 2$"},
    ("post", "content/reviews/{review}/needs-changes/"): {"comment": "A step is missing"},
    ("patch", "content/reports/{report}/"): {"staff_note": "Checked against the printing", "step": 2},
    ("post", "content/reports/{report}/reject/"): {"staff_note": "Not a mistake: see step 2"},
    ("post", "content/legal-deposits/"): lambda made, owner: {
        "book": made["book"],
        "library": "national_library",
        "sent_on": "2026-10-01",
        "proof": "Speed Post",
    },
    ("post", "support/tickets/"): {
        "source": "phone",
        "subject": "A call",
        "message": "Asked about a parcel",
        "phone": "+919812345678",
    },  # fmt: skip
    ("patch", "support/tickets/{ticket}/"): {"priority": "high"},
    ("post", "support/tickets/{ticket}/messages/"): {"direction": "note", "body": "Called them"},
    ("post", "support/tickets/{ticket}/assign/"): lambda made, owner: {"assignee": owner.pk},
    ("post", "support/tickets/{ticket}/status/"): {"status": "waiting_customer"},
    ("post", "support/tickets/{ticket}/reveal/"): {"show": ["email"], **WHY},
    ("post", "support/tickets/{ticket}/book-code/"): {"code": "ABCD-EFGH-JKLM"},
    ("post", "support/saved-replies/"): {"title": "Thanks", "body": "Thank you, {name|there}."},
    ("put", "support/saved-replies/{reply}/"): {"title": "Hello again", "body": "Hello {name|there}"},
    ("post", "finance/payment-links/invoices/{invoice_link}/posted/"): {"erp_name": "ACC-PAY-2026-00001"},
    ("post", "finance/settlements/{settlement}/match/"): lambda made, owner: {
        "line": line(made),
        "accept": True,
        "note": "Razorpay's fee",
    },
    ("post", "finance/settlements/fetch/"): {"day": "2026-10-01"},
    ("post", "catalogue/products/"): {
        "title": "Biology 2027",
        "slug": "biology-audit",
        "kind": "sample-papers",
        "mrp": "349.00",
        "weight_grams": 280,
    },  # fmt: skip
    ("patch", "catalogue/products/{product}/"): {"title": "Matrix book, revised"},
    ("post", "catalogue/products/{product}/stock/"): {"stock": 7, **WHY},
    ("patch", "catalogue/coupons/{coupon}/"): {"note": "For the schools", **WHY},
    ("post", "catalogue/offers/"): {"name": "Audit offer", "value": "10", **WHY},
    ("patch", "catalogue/offers/{offer}/"): {"name": "Matrix offer, renamed", **WHY},
    ("post", "catalogue/shipping-rates/"): {"name": "Audit rate", "fee": "50.00"},
    ("patch", "catalogue/shipping-rates/{rate}/"): {"name": "Renamed rate"},
    ("post", "catalogue/categories/"): {"name": "Audit shelf", "slug": "audit-shelf"},
    ("patch", "catalogue/categories/{category}/"): {"name": "Matrix, renamed"},
    ("post", "catalogue/categories/{category}/move/"): {"position": "last-child"},
    ("post", "catalogue/collections/"): {"slug": "audit-collection", "name": "Audit collection"},
    ("patch", "catalogue/collections/{collection}/"): {"name": "Matrix, renamed"},
    ("post", "catalogue/product-types/"): {"name": "Audit type"},
    ("patch", "catalogue/product-types/{kind}/"): {"name": "Matrix book, renamed"},
    ("post", "catalogue/product-types/{kind}/attributes/"): {"name": "Binding", "code": "binding"},
    ("patch", "catalogue/product-types/{kind}/attributes/{attribute}/"): {"name": "Language of the text"},
    ("patch", "course/chapters/{chapter}/"): {"must_do": "Coulomb's law"},
    ("patch", "course/revisions/{revision}/"): {"title": "Electrostatics, revised"},
    ("post", "course/revisions/{revision}/needs-changes/"): {"comment": "Say what to change: clip 2"},
    ("patch", "course/clips/{clip}/"): {"title": "A clip, renamed"},
    ("post", "course/clips/{clip}/move/"): {"to": "last"},
    ("patch", "course/cards/{card}/"): {"front": "A new front"},
    ("post", "course/cards/{card}/move/"): {"to": "last"},
    ("patch", "course/items/{quiz_item}/"): {"tags": ["revision"]},
    ("post", "course/items/{quiz_item}/move/"): {"to": "last"},
    ("post", "course/entitlements/"): lambda made, owner: {"user": made["customer"], "subject": "PHY", **WHY},
    ("post", "course/entitlements/{entitlement}/extend/"): {"days": 7, **WHY},
    ("post", "course/entitlements/{entitlement}/revoke/"): WHY,
    ("post", "course/codes/batches/{batch}/void/"): WHY,
    ("post", "course/codes/lookup/"): {"code": "ABCD-EFGH-JKLM"},
    ("post", "people/{person}/offboard/"): WHY,
    ("post", "policies/ack/"): {"policy": "conduct", "version": "1"},  # (STAFF_POLICIES: the walk's)
    ("post", "tax/hsn/4901/rates/"): {
        "rate": "5",
        "taxability": "taxable",
        "effective_from": "2027-04-01",
        "notification": "1/2027-CT(Rate)",
    },  # fmt: skip
    ("post", "catalogue/coupons/"): {"code": "AUDIT10", "kind": "percent", "value": "10", **WHY},
    ("post", "shipping/exceptions/{exception}/resolve/"): {"resolution": "Delivered on the second try"},
    ("post", "shipping/cod/{remittance}/reconcile/"): {"utr": "UTR123456789", "amount": "299.00"},
    ("post", "shipping/pickup-locations/"): {"nickname": "Second", "pin_code": "781001"},
    ("put", "shipping/pickup-locations/{pickup}/"): {"nickname": "Primary", "pin_code": "781024"},
}


def sha(made):
    from staff.models import ChangeRequest

    return ChangeRequest.objects.get(pk=made["change"]).payload_sha256


def physics():
    from content.models import Subject

    return Subject.objects.get(code="PHY").pk


def line(made):
    from shop.models import SettlementLine

    return SettlementLine.objects.get(settlement_id=made["settlement"]).pk


def order_of(made):
    from shop.models import Order

    return Order.objects.get(number=made["order"])


# The states an action needs: each a function of (the objects, the owner, the owner's client) giving the body; it
# may point the row at another record that fits (`made` is the path's)


def approved_refund(made, owner, client):
    from staff import approvals
    from staff.models import ChangeRequest

    payload = {"order": made["order"], "amount": None, "cancel": True}
    payload = approvals.ACTIONS["order.refund"].validate(make_staff(roles.SALES), made["order"], payload)[1]
    clean = approvals.plain(payload)
    ChangeRequest.objects.filter(pk=made["change"]).update(
        payload=clean, payload_sha256=approvals.digest(clean), status=ChangeRequest.Status.APPROVED
    )
    return {}


def suspended(made, owner, client):
    from accounts.models import User

    User.objects.filter(pk=made["customer"]).update(is_active=False)
    return WHY


def a_minor(made):
    from accounts.models import User

    today = date.today()
    User.objects.filter(pk=made["customer"]).update(
        date_of_birth=today.replace(year=today.year - 15), parent_contact="parent@example.com"
    )


def consent_pending(made, owner, client):
    a_minor(made)
    return {}


def parent_to_confirm(made, owner, client):
    a_minor(made)
    return {"evidence_ref": "SR-2026-000123"}


def with_nominee(made, owner, client):
    from accounts.models import Nominee

    Nominee.objects.create(user_id=made["customer"], name="Asha Das", contact="asha@example.com", relation="mother")
    return WHY


def scheduled_policy(made, owner, client):
    later = (timezone.localdate() + timedelta(days=10)).isoformat()
    body = {"markdown": "# Privacy\n\nLater.", "summary": "From next week", "effective_from": later}
    assert client.post(f"{STAFF}privacy/policies/privacy/publish/", body, format="json").status_code == 200
    return WHY


def no_hold(made, owner, client):
    from accounts.models import LegalHold
    from staff.models import DataRequest

    LegalHold.objects.filter(pk=made["hold"]).delete()
    DataRequest.objects.filter(pk=made["erasure"]).update(identity_verified=True, verified_at=timezone.now())
    return WHY


def mine(made, owner, client):
    from staff.models import Job

    Job.objects.filter(pk=made["job"]).update(started_by=owner)
    return {}


def held(made, owner, client):
    from shop import services

    services.hold(order_of(made), "Address issue", owner)
    return {}


def invoiced(made, owner, client):
    from shop.models import Invoice

    invoice = Invoice.for_order(order_of(made))
    invoice.pdf.save("invoice.pdf", ContentFile(b"%PDF-1.7"))
    return {}


def pending_order(made, owner, client):
    from shop.factories import ProductFactory, make_order

    made["order"] = make_order((ProductFactory(stock=5), 1)).number  # online, awaiting its payment
    return {"reference": "UTR123456789", **WHY}


def delivered_order(made, owner, client):
    from shop.factories import ProductFactory, captured, make_order
    from shop.models import Order
    from shop.services import record_capture

    order = make_order((ProductFactory(stock=5), 2))
    record_capture(captured(order))
    Order.objects.filter(pk=order.pk).update(status=Order.Status.DELIVERED)
    made["order"] = order.number
    return {"lines": [{"item": order.items.get().pk, "quantity": 1}], "reason": "damaged"}


def in_status(status, body):
    def move(made, owner, client):
        from shop.models import Order

        Order.objects.filter(number=made["order"]).update(status=status)
        return body

    return move


def return_in(status, body):
    def move(made, owner, client):
        from shop.models import ReturnRequest

        ReturnRequest.objects.filter(pk=made["back"]).update(status=status)
        return body

    return move


def resolved(made, owner, client):
    from support.models import Ticket

    Ticket.objects.filter(number=made["ticket"]).update(status=Ticket.Status.RESOLVED)
    return {}


def ticket_on_order(body, invoice=False, paid=True):
    def link(made, owner, client):
        from support.models import Ticket

        order = order_of(made)
        Ticket.objects.filter(number=made["ticket"]).update(order=order, requester_email_hash=hash_of(order.email))
        if invoice:
            invoiced(made, owner, client)
        return body(order) if callable(body) else body

    return link


def hash_of(email):
    from support.models import contact_hash

    return contact_hash("email", email.lower())


def learners_ticket(made, owner, client):
    from support.models import Ticket

    Ticket.objects.filter(number=made["ticket"]).update(user_id=made["learner"])
    return {"entitlement": made["entitlement"], "days": 7, **WHY}


def privacy_ticket(made, owner, client):
    from support.models import Ticket

    Ticket.objects.filter(number=made["ticket"]).update(category="privacy_request")
    return {"kind": "access"}


def binned_reply(made, owner, client):
    from support.models import SavedReply

    SavedReply._base_manager.filter(pk=made["reply"]).update(deleted_at=timezone.now())
    return {}


def binned(key):
    def bin_it(made, owner, client):
        from learn.models import Clip, FlashCard, QuizItem

        model = {"clip": Clip, "card": FlashCard, "quiz_item": QuizItem}[key]
        model._base_manager.filter(pk=made[key]).update(deleted_at=timezone.now())
        return {}

    return bin_it


def quoted(made, owner, client):
    from shop.factories import ProductFactory
    from shop.models import QuoteRequest

    book = ProductFactory(slug="quoted-book", stock=50)
    QuoteRequest.objects.filter(pk=made["quote"]).update(items=[{"product": book.slug, "title": book.title,
                                                                  "quantity": 20}])  # fmt: skip
    return BODIES_LATER["convert"]


def a_phone_order(made, owner, client):
    from shop.factories import ADDRESS, ProductFactory

    book = ProductFactory(slug="phone-book", stock=5)
    return {"channel": "phone", "lines": [{"product": book.slug, "quantity": 1}], "email": "buyer@example.com",
            "address": {k: v for k, v in ADDRESS.items() if k != "state"}, **WHY}  # fmt: skip


def circuit_in_use(made, owner, client):
    from integrations.models import IntegrationAccount

    IntegrationAccount.objects.create(provider="shiprocket", mode="test", enabled=True)
    return {"action": "open", **WHY}


def a_csv(made, owner, client):
    from shop.catalogue_jobs import COLUMNS

    row = {"slug": "imported-book", "title": "Imported 2027", "kind": "sample-papers", "is_active": "0",
           "mrp": "300.00", "price": "300.00", "weight_grams": "250"}  # fmt: skip
    text = ",".join(COLUMNS) + "\n" + ",".join(row.get(name, "") for name in COLUMNS) + "\n"
    return {"file": SimpleUploadedFile("products.csv", text.encode(), content_type="text/csv")}


def drafted(made, owner, client):
    from learn.models import Revision

    Revision.objects.filter(pk=made["revision"]).update(status=Revision.Status.DRAFT)
    return {}


def verified(made, owner, client):
    from staff.models import DataRequest

    DataRequest.objects.filter(pk=made["request"]).update(identity_verified=True, verified_at=timezone.now())
    return {}


def bundle(made, owner, client):
    from shop.factories import ProductFactory
    from shop.models import Product

    Product.objects.filter(slug=made["product"]).update(kind=Product.Kind.BUNDLE)
    return {"lines": [{"product": ProductFactory(slug="bundled-book").slug, "quantity": 2}]}


BODIES_LATER = {
    "convert": {
        "address": {
            "name": "Anita Das",
            "phone": "+919864012345",
            "line1": "Cotton Collegiate",
            "city": "Guwahati",
            "district": "Kamrup Metro",
            "pin": "781001",
        }
    },
}
PREPARE = {
    ("post", "jobs/{job}/cancel/"): mine,
    ("post", "orders/quotes/{quote}/convert/"): quoted,
    ("post", "orders/"): a_phone_order,
    ("post", "connections/shiprocket/circuit/"): circuit_in_use,
    ("post", "catalogue/import/"): a_csv,
    ("post", "change-requests/{change}/execute/"): approved_refund,
    ("post", "users/{customer}/unsuspend/"): suspended,
    ("post", "users/{customer}/resend-verification/"): consent_pending,
    ("post", "data-requests/{erasure}/erase/"): no_hold,
    ("post", "data-requests/{request}/export/"): verified,
    ("post", "privacy/nominees/{customer}/reveal/"): with_nominee,
    ("post", "privacy/deletions/{deletion}/parent-confirmation/"): parent_to_confirm,
    ("post", "privacy/policies/privacy/cancel-scheduled/"): scheduled_policy,
    ("post", "orders/{order}/release/"): held,
    ("post", "orders/{order}/invoice/resend/"): invoiced,
    ("post", "orders/{order}/offline-payment/"): pending_order,
    ("post", "orders/{order}/returns/"): delivered_order,
    ("post", "orders/{order}/ship/"): in_status("packed", {"courier": "India Post", "tracking_number": "EA1IN"}),
    ("post", "orders/{order}/deliver/"): in_status("shipped", {}),
    ("post", "orders/returns/{back}/label/"): return_in("approved", {"courier": "India Post", "awb": "EA2IN"}),
    ("post", "orders/returns/{back}/receive/"): return_in("approved", {}),
    ("post", "orders/returns/{back}/inspect/"): return_in("received", {"outcome": "restocked"}),
    ("post", "orders/returns/{back}/photos/"): return_in("received", {"photo": picture()}),
    ("post", "support/tickets/{ticket}/reopen/"): resolved,
    ("post", "support/tickets/{ticket}/cancel/"): ticket_on_order(WHY),
    ("post", "support/tickets/{ticket}/resend-invoice/"): ticket_on_order(lambda o: {"order": o.number}, True),
    ("post", "support/tickets/{ticket}/resend-confirmation/"): ticket_on_order(lambda o: {"order": o.number}),
    ("post", "support/tickets/{ticket}/extend-access/"): learners_ticket,
    ("post", "support/tickets/{ticket}/data-request/"): privacy_ticket,
    ("post", "support/saved-replies/{reply}/restore/"): binned_reply,
    ("put", "catalogue/products/{product}/bundle/"): bundle,
    ("post", "catalogue/products/{product}/pictures/"): lambda made, owner, client: {"image": picture()},
    ("post", "course/revisions/{revision}/submit/"): drafted,
    ("post", "course/clips/{clip}/restore/"): binned("clip"),
    ("post", "course/cards/{card}/restore/"): binned("card"),
    ("post", "course/items/{quiz_item}/restore/"): binned("quiz_item"),
}
MULTIPART = {("post", "orders/returns/{back}/photos/"), ("post", "catalogue/products/{product}/pictures/")}
MULTIPART |= {("post", "catalogue/import/")}
# The events of these rows name no target: the log's own export, a pick list of several orders, an approval asked of a
# fixture that names none
TARGETLESS = {("post", "audit/export/"), ("post", "orders/pick-list/"), ("post", "course/codes/lookup/")}
TARGETLESS |= {("post", f"change-requests/{{change}}/{verb}/") for verb in ["approve", "reject", "execute"]}
COVERED = {  # (method, path): the test that asserts its audit event (checked to exist and to read the log)
    ("post", "users/{customer}/impersonate/end/"): "staff.tests.test_impersonation."
    "test_it_ends_at_its_time_by_either_side_or_with_the_panels_session",
    ("post", "users/{customer}/consent/verify/"): "staff.tests.test_customers."
    "test_a_second_recording_a_mobile_contact_and_every_refusal",
    ("post", "system/reconcile/"): "staff.tests.test_inbox.test_asking_razorpay_again_about_a_stuck_payment",
    ("post", "privacy/dark-pattern-audits/{audit}/complete/"): "staff.tests.test_legal."
    "test_the_dark_pattern_self_audit_is_completed_once_and_its_certificate_shown_from_its_day",
    ("post", "privacy/dark-pattern-audits/{audit}/file/"): "staff.tests.test_legal."
    "test_the_certificates_signed_copy_is_kept_in_the_private_storage",
    ("post", "orders/{order}/payment-link/"): "shop.test_staff_finance."
    "test_an_orders_link_is_sent_cancelled_and_made_again_under_a_new_reference",
    ("post", "orders/refunds/{refund}/payee/"): "shop.test_staff_orders_api."
    "test_the_bank_path_is_refused_to_sales_and_marked_paid_by_finance_with_its_credit_note_once",
    ("post", "people/{person}/offboarding/tick/"): "staff.tests.test_offboarding."
    "test_only_an_owner_ticks_the_steps_done_by_hand_and_the_last_one_finishes_it",
    ("post", "connections/shiprocket/test/"): "integrations.tests.test_connections."
    "test_a_razorpay_test_reads_one_payment_through_the_client_and_keeps_its_result",
    ("post", "connections/shiprocket/credentials/"): "integrations.tests.test_connections."
    "test_new_credentials_are_kept_only_after_their_own_test_passes_and_are_masked_everywhere",
    ("post", "connections/shiprocket/mode/"): "integrations.tests.test_connections."
    "test_the_mode_switches_the_account_in_use_and_off_stops_razorpay",
    ("post", "connections/shiprocket/webhooks/rotate/"): "integrations.tests.test_connections."
    "test_a_webhook_token_is_answered_once_and_the_previous_one_works_for_a_day",
    **dict.fromkeys(
        [
            ("post", "connections/shiprocket/failures/{failure}/replay/"),
            ("post", "connections/shiprocket/failures/{failure}/discard/"),
        ],
        "integrations.tests.test_connections.test_dead_letters_are_replayed_or_discarded_and_erpnexts_through_the_sync",
    ),  # fmt: skip
    ("post", "templates/{template}/test/"): "ops.test_templates.test_a_test_goes_to_your_own_confirmed_number_or_"
    "address_only",
    ("post", "system/backups/drills/"): "staff.tests.test_system_pages."
    "test_the_backups_show_each_sources_newest_object_and_when_a_restore_last_worked",
    **dict.fromkeys(
        [
            ("post", f"content/{kind}s/{{{kind}}}/history/{{{kind}_version}}/restore/")
            for kind in ["book", "paper", "question"]
        ],
        "content.test_review.test_the_history_reads_as_a_diff_and_a_version_comes_back",
    ),  # fmt: skip
    **dict.fromkeys(
        [
            ("post", "content/questions/{question}/submit/"),
            ("post", "content/questions/{question}/discard/"),
            ("post", "content/solutions/{solution}/submit/"),
        ],
        "content.test_review.test_author_checker_publish_and_the_last_editor_never_publishes",
    ),  # fmt: skip
    **dict.fromkeys(
        [("post", "content/questions/{question}/rollback/"), ("post", "content/solutions/{solution}/rollback/")],
        "content.test_review.test_a_rollback_restores_the_text_before_the_publish",
    ),
    **dict.fromkeys(
        [("post", f"content/reports/{{report}}/{verb}/") for verb in ["fix-in-printing", "reopen", "tell"]],
        "content.test_reports.test_the_triage_moves_a_report_through_its_states_and_tells_the_reporter_once",
    ),
    ("post", "support/tickets/{ticket}/refund/"): "support.tests.test_api."
    "test_a_refund_from_a_ticket_runs_within_the_limit_and_waits_above_it",
    ("post", "finance/payments/{payment}/reconcile/"): "shop.test_staff_finance."
    "test_asking_razorpay_again_records_a_payment_that_turned_authorised_late",
    ("post", "finance/payment-links/"): "shop.test_staff_finance."
    "test_an_orders_link_is_sent_cancelled_and_made_again_under_a_new_reference",
    ("post", "course/clips/{clip}/retry/"): "learn.test_staff_course."
    "test_a_failed_clip_says_why_in_words_and_is_retried",
    ("post", "course/codes/batches/"): "learn.test_codes."
    "test_a_batch_keeps_digests_only_and_its_file_is_its_makers_for_24_hours",
    ("post", "course/codes/void/"): "learn.test_codes.test_one_code_is_voided_and_a_redeemed_one_is_refused",
    ("post", "session/reason/"): "staff.tests.test_session."
    "test_a_break_glass_session_gives_its_reason_first_and_each_of_its_events_carries_it",
    ("post", "people/me/sessions/1/end/"): "staff.tests.test_access."
    "test_own_sessions_are_listed_and_ended_one_by_one_or_all_but_this_one",
}
EXEMPT = {  # (method, path): why the row changes no record
    **dict.fromkeys(
        [
            ("post", "saved-views/"),
            ("patch", "saved-views/{view}/"),
            ("put", "saved-views/{view}/"),
            ("delete", "saved-views/{view}/"),
        ],
        "a person's own list filters (no record; another's is 404: test_objects)",
    ),  # fmt: skip
    **dict.fromkeys(
        [
            ("put", "data-requests/{request}/"),
            ("put", "incidents/{incident}/"),
            ("put", "privacy/dark-pattern-audits/{audit}/"),
        ],
        "PUT is refused (405): PATCH is the change, walked here",
    ),  # fmt: skip
    ("post", "orders/preview/"): "a staff order's price before it is asked for: changes nothing",
    ("post", "people/{person}/roles/preview/"): "a role change's preview: changes nothing",
    ("post", "reports/print-run/"): "the print-run calculator: changes nothing",
}
COURIER = {  # the shipping app's actions that ask a courier (Phase A, its own tests): a parcel typed by hand has none
    ("post", path): "shipping/tests/test_api.py"
    for path in ["shipping/shipments/", "shipping/shipments/{parcel}/label/", "shipping/shipments/{parcel}/pickup/",
                 "shipping/shipments/{parcel}/cancel/", "shipping/shipments/{parcel}/photo/",
                 "shipping/shipments/{parcel}/ndr-action/", "shipping/manifest/", "shipping/pickup-locations/sync/"]
}  # fmt: skip
WALKED = [row for row in ROWS if (row[1], row[2]) not in COVERED | EXEMPT | COURIER]
PERSONAL = ["rahul@example.com", "o@example.com", "a@example.com", "9864012345", "98640 12345", "x@example.com"]
PERSONAL += ["9812345678", "new.person@examleaf.in", "parent@example.com", "asha@example.com"]


def test_the_tables_cover_every_change_row_once():
    rows = {(method, path) for _, method, path in ROWS}
    for name, table in [("COVERED", COVERED), ("EXEMPT", EXEMPT), ("COURIER", COURIER)]:
        assert set(table) <= rows, (name, sorted(set(table) - rows))
    assert not set(COVERED) & set(EXEMPT) and not (set(COVERED) | set(EXEMPT)) & set(COURIER)
    assert not set(BODIES) & set(PREPARE), sorted(set(BODIES) & set(PREPARE))
    for key in [*BODIES, *PREPARE]:
        assert key in rows and key not in COVERED | EXEMPT | COURIER, key


@pytest.mark.parametrize("key", sorted(COVERED), ids=[f"{m} {p}" for m, p in sorted(COVERED)])
def test_a_covered_row_names_a_test_that_reads_the_log(key):
    module, _, name = COVERED[key].rpartition(".")
    source = inspect.getsource(getattr(import_module(module), name))
    assert "events(" in source or "AuditEvent" in source or "audit" in source, COVERED[key]


@pytest.mark.parametrize(("table", "method", "path"), WALKED, ids=[f"{m} {p}" for _, m, p in WALKED])
def test_each_change_is_an_audit_event_naming_its_target_without_personal_data(table, method, path, rzp, settings):
    settings.PARENTAL_CONSENT_MODE, settings.STAFF_POLICIES = "verified", {"conduct": "1"}
    made = objects() if table == "staff" else app_objects()
    owner = make_staff(roles.OWNER)  # every permission, re-authenticated: the action itself answers
    client, key = signed_in(owner), (method, path)
    body = PREPARE[key](made, owner, client) if key in PREPARE else BODIES.get(key, {})
    body = body(made, owner) if callable(body) else body
    url = (STAFF if table == "staff" else "/api/v1/") + path.format(**made)
    before = AuditEvent.objects.order_by("-id").values_list("id", flat=True).first() or 0
    response = getattr(client, method)(url, body, format="multipart" if key in MULTIPART else "json")
    text = b"" if response.streaming else response.content[:300]
    assert 200 <= response.status_code < 300, (response.status_code, text)
    new = list(AuditEvent.objects.filter(id__gt=before, actor_id=owner.pk))
    assert new, "no audit event"
    assert key in TARGETLESS or any(event.target_type for event in new), [e.action for e in new]
    kept = json.dumps([[e.details, e.changes, e.target_label] for e in new], default=str).lower()
    digits = "".join(char for char in kept if char.isdigit())
    assert not [w for w in PERSONAL if (w.lower() in kept if "@" in w else w.replace(" ", "") in digits)], kept[:400]
