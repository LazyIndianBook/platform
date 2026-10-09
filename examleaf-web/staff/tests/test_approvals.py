"""Maker-checker (research 1.5): what is approved is what runs (the stored payload, bound by its hash), once, before it
expires; the approver is never the maker nor the person the change is about, unless an owner overrides; within the
maker's limits it runs at once. The refund flow through it, end to end."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core import mail
from django.utils import timezone

from accounts import roles
from accounts.factories import UserFactory
from shop import services as shop
from shop.factories import ProductFactory, captured, make_order
from shop.models import Coupon, Order, Product, Refund
from staff import approvals
from staff.models import ChangeRequest, InboxItem
from staff.tasks import expire_change_requests

from .conftest import STAFF, events, make_staff, signed_in

pytestmark = pytest.mark.django_db
ASK = STAFF + "change-requests/"


def paid_order(price="1500.00", copies=2):
    order = make_order((ProductFactory(price=Decimal(price), mrp=Decimal(price) + 100), copies))
    shop.record_capture(captured(order))
    return Order.objects.get(pk=order.pk)


def ask_refund(user, order, key="", **payload):
    headers = {"HTTP_IDEMPOTENCY_KEY": key} if key else {}
    body = {"action": "order.refund", "target": order.number, "payload": payload, "reason": "Damaged in transit"}
    return signed_in(user).post(ASK, body, format="json", **headers)


def approve(user, change, sha=None, **body):
    return signed_in(user).post(f"{ASK}{change['id']}/approve/",
                                {"payload_sha256": sha or change["payload_sha256"], **body}, format="json")  # fmt: skip


def run(user, change):
    return signed_in(user).post(f"{ASK}{change['id']}/execute/")


def test_a_refund_within_the_makers_limit_runs_at_once(rzp, commit):
    order, sales = paid_order(price="299.00", copies=1), make_staff(roles.SALES)
    with commit():
        response = ask_refund(sales, order)
    assert response.status_code == 201, response.content
    change = response.json()
    assert change["status"] == "executed" and change["rule"].startswith("Within the maker's limits")
    refund = Refund.objects.get(order=order)
    assert refund.created_by == sales and refund.status == Refund.Status.PROCESSED  # through start_refund, Razorpay
    rzp.payment.refund.assert_called_once()
    trail = ["order.refund.requested", "order.refund.approved", "order.refund.executed"]
    assert list(events(change_request_id=change["id"]).values_list("action", flat=True)) == trail
    assert events("refund.started", target_id=str(order.pk)).get().chain == "money"  # the shop's own step
    assert not InboxItem.objects.filter(kind="approval").exists()  # nothing waited


def test_a_refund_above_the_makers_limit_waits_for_finance_then_runs_the_stored_payload(rzp, commit):
    order, sales, finance = paid_order(), make_staff(roles.SALES), make_staff(roles.FINANCE)
    response = ask_refund(sales, order)
    assert response.status_code == 202
    change = response.json()
    assert (
        change["status"] == "pending" and change["amount"] == "3000.00" and change["checker"] == "staff.approve_refund"
    )
    assert "above the limit of ₹2,000" in change["rule"] and not Refund.objects.exists()
    item = InboxItem.objects.get(kind="approval", done_at=None)
    assert item.permission == "staff.approve_refund" and order.number in item.title
    assert approve(make_staff(roles.SUPPORT), change).status_code == 403  # not an approver
    assert approve(finance, change, sha="0" * 64).status_code == 400  # not the payload finance read
    approved = approve(finance, change, comment="Photos checked")
    assert approved.status_code == 200 and approved.json()["status"] == "approved"
    assert approved.json()["approvals"][0]["comment"] == "Photos checked"
    assert InboxItem.objects.get(pk=item.pk).done_at is not None
    with commit():
        done = run(sales, change)  # its maker runs it (or the approver)
    assert done.status_code == 200 and done.json()["status"] == "executed"
    assert done.json()["result"]["amount"] == "3000.00" and Order.objects.get(pk=order.pk).status == "refunded"
    assert run(finance, change).status_code == 400  # once


def test_what_runs_is_the_payload_approved_or_nothing(rzp):
    order, sales, finance = paid_order(), make_staff(roles.SALES), make_staff(roles.FINANCE)
    change = ask_refund(sales, order).json()
    approve(finance, change)
    ChangeRequest.objects.filter(pk=change["id"]).update(payload={**change["payload"], "amount": "1.00"})
    failed = run(finance, change)
    assert failed.status_code == 400 and failed.json()["status"] == "failed"
    assert "does not match the one approved" in failed.json()["detail"]
    assert not Refund.objects.exists() and events("order.refund.failed", outcome="failed").exists()


def test_a_request_whose_order_changed_meanwhile_fails_instead_of_doing_something_else(rzp):
    order, sales, finance = paid_order(), make_staff(roles.SALES), make_staff(roles.FINANCE)
    change = ask_refund(sales, order).json()
    assert change["payload"]["cancel"] is True  # not shipped yet: cancelled and refunded in full
    approve(finance, change)
    shop.pack_order(order)
    shop.ship_order(order, "India Post", "EA1")
    failed = run(sales, change).json()
    assert failed["status"] == "failed" and "The order changed since the request" in failed["result"]["error"]
    assert not Refund.objects.exists()


def test_a_shipped_orders_refund_is_partial_and_capped_at_what_was_paid(rzp, commit):
    order, finance = paid_order(), make_staff(roles.FINANCE)
    shop.pack_order(order)
    shop.ship_order(order, "India Post", "EA1")
    change = ask_refund(make_staff(roles.SALES), order, amount="5000").json()
    assert change["payload"] == {"order": order.number, "amount": "3000.00", "cancel": False}
    with commit():
        approve(finance, change)
        run(finance, change)
    refund = Refund.objects.get()
    assert refund.amount.amount == Decimal("3000.00") and Order.objects.get(pk=order.pk).status == "refunded"
    assert not Order.objects.filter(pk=order.pk, status="cancelled").exists()  # shipped: refunded, not cancelled


def test_nothing_to_refund_online_is_refused_at_once():
    order = make_order((ProductFactory(), 1))  # never paid
    response = ask_refund(make_staff(roles.SALES), order)
    assert response.status_code == 400 and "Nothing to refund online" in response.json()["target"][0]
    other = make_staff(roles.PACKER)  # no refund_order
    assert ask_refund(other, order).status_code == 403


def test_an_idempotency_key_answers_the_first_request_again(rzp):
    order, sales = paid_order(), make_staff(roles.SALES)
    first = ask_refund(sales, order, key="refund-1")
    again = ask_refund(sales, order, key="refund-1")
    assert (first.status_code, again.status_code) == (202, 202) and first.json()["id"] == again.json()["id"]
    assert ChangeRequest.objects.count() == 1
    other = signed_in(sales).post(ASK, {"action": "product.price", "target": "x", "payload": {}, "reason": "r"},
                                  format="json", HTTP_IDEMPOTENCY_KEY="refund-1")  # fmt: skip
    assert other.status_code == 400 and "idempotency_key" in other.json()


def test_the_maker_never_approves_unless_an_owner_overrides_and_says_why(
    rzp, settings, django_capture_on_commit_callbacks
):
    settings.STAFF_ALERT_EMAILS = ["owner@examleaf.in"]
    order, finance = paid_order(price="6000.00"), make_staff(roles.FINANCE)
    change = ask_refund(finance, order).json()  # 12,000 is above FINANCE's 10,000
    assert change["status"] == "pending"
    refused = approve(finance, change)
    assert refused.status_code == 403 and "the maker never does" in refused.json()["detail"]
    owner = make_staff(roles.OWNER)  # the founder: the role, not the superuser flag
    own = ask_refund(owner, paid_order(price="20000.00")).json()
    assert own["status"] == "executed"  # an owner has no refund limit
    order_two = paid_order(price="4000.00")
    staff_admin = make_staff(roles.ADMIN)
    pending = ask_refund(staff_admin, order_two).json()  # 8,000 is within ADMIN's 10,000: runs
    assert pending["status"] == "executed"
    big = ask_refund(staff_admin, paid_order(price="7000.00")).json()
    assert approve(staff_admin, big, override=True, comment="Nobody else").status_code == 403  # not an owner
    assert approve(make_staff(roles.ADMIN), big).status_code == 403  # FINANCE approves money, not ADMIN (plan 4.1)
    owners_own = ChangeRequest.objects.get(pk=big["id"])
    ChangeRequest.objects.filter(pk=owners_own.pk).update(maker=owner)  # (as if the owner had asked)
    assert approve(owner, big, override=True).status_code == 400  # a reason first
    with django_capture_on_commit_callbacks(execute=True):
        overridden = approve(owner, big, override=True, comment="Alone this week")
    assert overridden.status_code == 200 and overridden.json()["overridden"] is True
    assert events("order.refund.overridden").get().break_glass  # marked, as a break-glass account's events are
    assert not events("order.refund.requested", change_request_id=big["id"]).get().break_glass
    assert any("approved their own request" in message.subject for message in mail.outbox)


def test_a_second_factor_reset_needs_a_second_person_and_admin_or_an_owner_for_staff():
    support, colleague, customer = make_staff(roles.SUPPORT), make_staff(roles.SUPPORT), UserFactory()
    reset = signed_in(support).post(f"{STAFF}users/{customer.pk}/reset-mfa/", {"reason": "Lost phone"}, format="json")
    assert reset.status_code == 202 and reset.json()["checker"] == "staff.reset_user_mfa"
    assert approve(support, reset.json()).status_code == 403  # the maker
    assert approve(colleague, reset.json()).status_code == 200  # a second person with the same permission


def test_nobody_approves_a_change_to_their_own_account():
    founder, partner, admin = make_staff(roles.OWNER), make_staff(roles.OWNER), make_staff(roles.ADMIN)
    asked = signed_in(partner).post(f"{STAFF}people/{founder.pk}/reset-mfa/", {"reason": "A new phone"}, format="json")
    assert asked.status_code == 202 and asked.json()["checker"] == "staff.approve_role_change"  # staff: ADMIN, owners
    own = approve(founder, asked.json())
    assert own.status_code == 403 and "their own account" in own.json()["detail"]
    assert approve(make_staff(roles.FINANCE), asked.json()).status_code == 403  # FINANCE approves money only
    assert approve(admin, asked.json()).status_code == 200  # ADMIN approves roles and staff second factors
    assert run(admin, asked.json()).json()["result"]["authenticators"] == 1
    assert not founder.authenticator_set.exists()
    assert signed_in(admin).post(f"{STAFF}people/{founder.pk}/reset-mfa/", {"reason": "x"}).status_code == 403


def test_a_request_expires_and_an_approval_works_once(rzp, settings):
    order, sales, finance = paid_order(), make_staff(roles.SALES), make_staff(roles.FINANCE)
    change = ask_refund(sales, order).json()
    ChangeRequest.objects.filter(pk=change["id"]).update(expires_at=timezone.now() - timedelta(minutes=1))
    late = approve(finance, change)
    assert late.status_code == 400 and "expired" in late.json()["non_field_errors"][0]
    assert ChangeRequest.objects.get(pk=change["id"]).status == "expired"
    assert events("order.refund.expired").exists()
    second = ask_refund(sales, paid_order()).json()
    approve(finance, second)
    ChangeRequest.objects.filter(pk=second["id"]).update(expires_at=timezone.now() - timedelta(minutes=1))
    assert expire_change_requests() == 1 and ChangeRequest.objects.get(pk=second["id"]).status == "expired"
    assert run(sales, second).status_code == 400


def test_a_checker_rejects_or_the_maker_withdraws(rzp):
    sales, finance = make_staff(roles.SALES), make_staff(roles.FINANCE)
    first, second = ask_refund(sales, paid_order()).json(), ask_refund(sales, paid_order()).json()
    assert signed_in(make_staff(roles.SUPPORT)).post(f"{ASK}{first['id']}/reject/").status_code == 403
    assert (
        signed_in(finance).post(f"{ASK}{first['id']}/reject/", {"comment": "No photos"}).json()["status"] == "rejected"
    )
    assert signed_in(sales).post(f"{ASK}{second['id']}/reject/").json()["status"] == "rejected"
    assert approve(finance, first).status_code == 400


def test_offline_payments_above_a_value_or_of_nothing_wait_for_finance():
    sales, finance = make_staff(roles.SALES), make_staff(roles.FINANCE)
    small = make_order((ProductFactory(price=Decimal("299.00")), 1))
    done = signed_in(sales).post(
        ASK,
        {
            "action": "order.offline_payment",
            "target": small.number,
            "payload": {"reference": "UTR1"},
            "reason": "NEFT received",
        },
        format="json",
    )
    assert done.status_code == 201 and Order.objects.get(pk=small.pk).status == "paid"
    big = make_order((ProductFactory(price=Decimal("3000.00")), 2))
    waiting = signed_in(sales).post(
        ASK,
        {
            "action": "order.offline_payment",
            "target": big.number,
            "payload": {"reference": "UTR2"},
            "reason": "A school's NEFT",
        },
        format="json",
    )
    assert waiting.status_code == 202 and "paid offline is above the limit" in waiting.json()["rule"]
    approve(finance, waiting.json())
    assert run(finance, waiting.json()).json()["status"] == "executed" and Order.objects.get(pk=big.pk).status == "paid"
    rule = approvals.OfflinePayment().rule(finance, ChangeRequest(amount=Decimal(0)))
    assert "₹0 order" in rule  # even within a limit
    assert signed_in(sales).post(ASK, {"action": "order.offline_payment", "target": small.number,
                                       "payload": {"reference": "UTR3"}, "reason": "again"},
                                 format="json").status_code == 400  # paid already  # fmt: skip


def test_prices_and_coupons_beyond_the_discount_limit_wait_for_finance():
    product = ProductFactory(mrp=Decimal("400.00"), price=Decimal("380.00"))
    sales, marketing, finance = make_staff(roles.SALES), make_staff(roles.MARKETING), make_staff(roles.FINANCE)
    price = {"action": "product.price", "target": product.slug, "reason": "Board offer"}
    within = signed_in(sales).post(ASK, {**price, "payload": {"price": "340.00"}}, format="json")  # 15% off
    assert within.status_code == 201 and Product.objects.get(pk=product.pk).price.amount == Decimal("340.00")
    beyond = signed_in(sales).post(ASK, {**price, "payload": {"price": "200.00"}}, format="json").json()  # 50% off
    assert beyond["status"] == "pending" and "50.00% off is beyond the limit of 20%" in beyond["rule"]
    Product.objects.filter(pk=product.pk).update(price=Decimal("399.00"))  # changed meanwhile
    approve(finance, beyond)
    assert run(finance, beyond).json()["result"]["error"] == "The price changed since the request: ask again."
    coupon = {"action": "coupon.create", "reason": "Diwali"}
    small = signed_in(marketing).post(ASK, {**coupon, "target": "DIWALI10", "payload": {"value": "10"}}, format="json")
    assert small.status_code == 201 and Coupon.objects.filter(code="DIWALI10").exists()
    large = signed_in(marketing).post(ASK, {**coupon, "target": "half", "payload": {"value": "50"}}, format="json")
    assert large.json()["status"] == "pending" and not Coupon.objects.filter(code="HALF").exists()
    fixed = signed_in(marketing).post(ASK, {**coupon, "target": "FLAT300", "payload": {"kind": "fixed", "value": "300",
                                      "min_order": "500"}}, format="json")  # 60% of the smallest order  # fmt: skip
    assert fixed.json()["status"] == "pending"
    approve(finance, large.json())
    assert run(marketing, large.json()).json()["status"] == "executed" and Coupon.objects.get(code="HALF").value == 50


def test_bulk_actions_above_the_row_limit_need_an_approver():
    sales = make_staff(roles.SALES)
    assert approvals.bulk_rule(sales, 100) is None
    assert approvals.bulk_rule(sales, 101) == "101 rows at once are above the limit of 100."
    assert approvals.bulk_rule(make_staff(roles.OWNER), 10_000) is None
    assert approvals.bulk_rule(make_staff(is_superuser=True), 10_000) is None  # a break-glass account: none either
