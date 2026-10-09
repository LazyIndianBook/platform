"""Razorpay's settlements (shop/settlements.py): a day fetched from the recon API through the integrations client
(Razorpay's answers recorded: conftest.FakeSettlements), kept once, matched to our payments and refunds by Razorpay's
id, the mismatched ones in FINANCE's inbox, the matched ones posted to ERPNext once and never in test mode, a line
matched by hand, a payment we never heard of asked of Razorpay, and the nightly tasks. No network."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.utils import timezone

from accounts import roles
from erp.models import ErpOutbox
from integrations.client import CircuitOpen, IntegrationUnavailable
from integrations.models import IntegrationAccount, IntegrationCall
from shop import services, settlements, tasks
from shop.factories import ProductFactory, captured, make_order
from shop.models import Order, Payment, Refund, Settlement, SettlementLine
from staff.models import AuditEvent, InboxItem
from staff.tests.conftest import make_staff

pytestmark = pytest.mark.django_db
DAY = date(2026, 10, 9)
LIVE = "rzp_live_key"


@pytest.fixture
def live(settings):
    """The site on live keys, with ERPNext's settlements flow on (its relay is not: rows wait in the outbox)."""
    settings.RAZORPAY_KEY_ID = LIVE
    settings.ERP_SYNC_SETTLEMENTS = True


def paid_order(*, live=False):
    """An order paid online (its payment pay_<order id>, ₹299), of the live keys or the test ones."""
    order = make_order((ProductFactory(), 1))
    Order.objects.filter(pk=order.pk).update(livemode=live)
    Payment.objects.filter(order=order).update(livemode=live)
    services.record_capture(captured(order))
    return Order.objects.get(pk=order.pk)


def a_day(fake, order, *more, settlement_id="setl_A1", net=None, refund=None):
    """A settlement of DAY holding the order's payment (fee ₹7.08 with its ₹1.08 GST), and more items."""
    items = [{"type": "payment", "entity_id": f"pay_{order.pk}", "amount": "299.00", "fee": "7.08", "tax": "1.08"}]
    if refund is not None:
        items.append({"type": "refund", "entity_id": refund.razorpay_refund_id, "amount": str(refund.amount.amount)})
    fake.add(DAY, settlement_id, *items, *more, net=net)


def test_a_day_is_kept_once_its_lines_matched_by_razorpay_id_and_posted_to_erpnext_once(live, razorpay_settlements):
    order = paid_order(live=True)
    refund = Refund.objects.create(
        order=order, payment=order.payments.get(), amount=Decimal("100.00"), reason="A damaged book",
        razorpay_refund_id="rfnd_1", status=Refund.Status.PROCESSED,
    )  # fmt: skip
    a_day(razorpay_settlements, order, refund=refund)
    first = settlements.fetch_day(DAY)
    second = settlements.fetch_day(DAY)  # the same day again: nothing new
    settlement = Settlement.objects.get()
    assert first["new_lines"] == 2 and second["new_lines"] == 0 and second["new_settlements"] == 0
    assert settlement.state == Settlement.State.POSTED and settlement.livemode
    payment_line, refund_line = settlement.lines.order_by("pk")
    assert payment_line.payment == order.payments.get() and payment_line.order == order
    assert refund_line.refund == refund and refund_line.order == order
    # Razorpay kept ₹7.08 of the payment, ₹1.08 of it GST; the refund went back whole
    assert (payment_line.fee.amount, payment_line.tax.amount) == (Decimal("6.00"), Decimal("1.08"))
    assert settlement.net.amount == Decimal("191.92") and settlement.gross.amount == Decimal("199.00")
    assert (settlement.fees.amount, settlement.tax.amount) == (Decimal("6.00"), Decimal("1.08"))
    rows = ErpOutbox.objects.filter(event="settlement.received")
    assert rows.count() == 1 and settlement.erp_outbox == rows.get()  # once, however often fetched
    payload = rows.get().payload
    assert payload == {
        "kind": "razorpay", "settlement_id": "setl_A1", "posting_date": "2026-10-09", "gross_amount": "199.00",
        "fee": "6.00", "tax_on_fee": "1.08", "net_amount": "191.92", "utr": "UTR20261009001",
    }  # fmt: skip
    parts = sum(Decimal(payload[name]) for name in ("net_amount", "fee", "tax_on_fee"))
    assert Decimal(payload["gross_amount"]) == parts  # ERPNext's rule for the Journal Entry
    assert not InboxItem.objects.filter(kind="settlement").exists()
    assert AuditEvent.objects.filter(action="payment.settlement_posted", target_id=str(settlement.pk)).count() == 1
    assert AuditEvent.objects.filter(action="payment.settlements_fetched").count() == 2
    assert IntegrationCall.objects.filter(operation="settlement_recon").exists()  # through the integrations client


def test_test_mode_settlements_are_matched_and_never_posted(settings, razorpay_settlements):
    settings.ERP_SYNC_SETTLEMENTS = True  # the flow on: test keys still never post
    order = paid_order()
    a_day(razorpay_settlements, order)
    settlements.fetch_day(DAY)
    settlement = Settlement.objects.get()
    assert settlement.state == Settlement.State.MATCHED and not settlement.livemode
    assert not ErpOutbox.objects.exists() and settlements.post_waiting() == 0


def test_an_unmatched_line_opens_one_inbox_item_and_a_match_by_hand_completes_it(live, razorpay_settlements):
    order = paid_order(live=True)
    a_day(razorpay_settlements, order, {"type": "adjustment", "entity_id": "adj_1", "amount": "10.00", "credit": "10"})
    settlements.fetch_day(DAY)
    settlements.fetch_day(DAY)
    settlement = Settlement.objects.get()
    assert settlement.state == Settlement.State.MISMATCHED and settlement.problem == "1 line not ours yet"
    item = InboxItem.objects.get(kind="settlement", done_at=None)
    assert item.permission == "staff.reconcile_settlements" and "setl_A1" in item.title
    assert not ErpOutbox.objects.exists()  # nothing posted while it does not match
    finance = make_staff(roles.FINANCE)
    adjustment = settlement.lines.get(entity_id="adj_1")
    with pytest.raises(ValueError, match="matched already"):
        settlements.manual_match(settlement, settlement.lines.get(type="payment").pk, accept=True, note="x", by=finance)
    line = settlements.manual_match(settlement, adjustment.pk, accept=True, note="Razorpay's fee reversal", by=finance)
    assert line.matched_by == finance and line.note == "Razorpay's fee reversal"
    settlement.refresh_from_db()
    assert settlement.state == Settlement.State.POSTED and settlement.adjustments.amount == Decimal("10.00")
    assert settlement.gross.amount == Decimal("309.00")  # the payment and the adjustment
    assert InboxItem.objects.get(pk=item.pk).done_at is not None
    event = AuditEvent.objects.get(action="payment.settlement_line_matched")
    assert event.actor_id == finance.pk and event.reason == "Razorpay's fee reversal"
    assert event.details["accepted"] is True and event.details["entity"] == "adj_1"
    with pytest.raises(ValueError, match="posted"):  # posted: corrected in ERPNext, never here
        settlements.manual_match(settlement, adjustment.pk, accept=True, note="again", by=finance)


def test_a_net_that_differs_from_the_lines_is_mismatched(live, razorpay_settlements):
    order = paid_order(live=True)
    a_day(razorpay_settlements, order, net="290.00")
    settlements.fetch_day(DAY)
    settlement = Settlement.objects.get()
    assert settlement.state == Settlement.State.MISMATCHED
    assert settlement.problem == "Razorpay's net ₹290.00 is not its lines' ₹291.92"
    assert InboxItem.objects.filter(kind="settlement", done_at=None).count() == 1 and not ErpOutbox.objects.exists()


def test_a_line_matches_only_a_payment_of_its_mode_and_amount(live, razorpay_settlements):
    order = paid_order(live=True)
    razorpay_settlements.add(
        DAY, "setl_B", {"type": "payment", "entity_id": f"pay_{order.pk}", "amount": "300.00", "fee": "7.08"}
    )
    settlements.fetch_day(DAY)
    line = SettlementLine.objects.get()
    assert line.matched_at is None and Settlement.objects.get().state == Settlement.State.MISMATCHED
    finance = make_staff(roles.FINANCE)
    with pytest.raises(ValueError, match="₹299.00, the line ₹300.00"):
        settlements.manual_match(
            line.settlement, line.pk, payment=order.payments.get(), note="The same payment", by=finance
        )


def test_a_payment_razorpay_settled_and_we_never_heard_of_is_asked_of_razorpay(live, razorpay_settlements, rzp):
    order = make_order((ProductFactory(), 1))  # its webhook lost: still pending here
    Order.objects.filter(pk=order.pk).update(livemode=True)
    Payment.objects.filter(order=order).update(livemode=True)
    rzp.order.payments.return_value = {"items": [captured(order)]}
    razorpay_settlements.add(
        DAY,
        "setl_C",
        {"type": "payment", "entity_id": f"pay_{order.pk}", "amount": "299.00", "order_receipt": order.number},
    )
    result = settlements.fetch_day(DAY)
    assert result["orders_paid_now"] == 1
    order.refresh_from_db()
    assert order.status == Order.Status.PAID
    assert SettlementLine.objects.get().payment == order.payments.get()
    assert Settlement.objects.get().state == Settlement.State.POSTED


def test_a_settlement_matched_while_the_flow_was_off_posts_once_it_is_on(settings, live, razorpay_settlements):
    settings.ERP_SYNC_SETTLEMENTS = False
    a_day(razorpay_settlements, paid_order(live=True))
    settlements.fetch_day(DAY)
    assert Settlement.objects.get().state == Settlement.State.MATCHED and not ErpOutbox.objects.exists()
    settings.ERP_SYNC_SETTLEMENTS = True
    assert settlements.post_waiting() == 1 and settlements.post_waiting() == 0
    assert Settlement.objects.get().state == Settlement.State.POSTED and ErpOutbox.objects.count() == 1


def test_razorpay_out_of_reach_keeps_nothing_and_an_open_circuit_asks_nothing(live, razorpay_settlements):
    razorpay_settlements.fail = 503
    with pytest.raises(IntegrationUnavailable):
        settlements.fetch_day(DAY)
    assert not Settlement.objects.exists()
    account = IntegrationAccount.objects.get(provider="razorpay", mode="live")  # the environment keys' call log
    assert account.calls.filter(status_code=503).exists() and not account.enabled
    account.force_open()
    calls = len(razorpay_settlements.calls)
    with pytest.raises(CircuitOpen):
        settlements.fetch_day(DAY)
    assert len(razorpay_settlements.calls) == calls


def test_without_keys_there_is_nothing_to_fetch(settings, razorpay_settlements):
    settings.RAZORPAY_KEY_ID = settings.RAZORPAY_KEY_SECRET = ""
    with pytest.raises(settlements.NotConfigured):
        settlements.fetch_day(DAY)
    assert tasks.fetch_settlements(DAY.isoformat()) == {"day": "2026-10-09", "not_configured": True}
    assert not razorpay_settlements.calls


def test_a_dry_run_keeps_nothing(live, razorpay_settlements):
    a_day(razorpay_settlements, paid_order(live=True))
    result = settlements.fetch_day(DAY, dry_run=True)
    assert result["settlements"] == 1 and result["lines"] == 1 and result["dry_run"]
    assert not Settlement.objects.exists() and not ErpOutbox.objects.exists()
    assert not AuditEvent.objects.filter(action__startswith="payment.settlement").exists()


def test_the_nightly_fetch_is_yesterdays_and_runs_once_at_a_time(live, razorpay_settlements, monkeypatch):
    monkeypatch.setattr(settlements, "yesterday", lambda: DAY)
    a_day(razorpay_settlements, paid_order(live=True))
    lock = "single-run:shop.tasks.fetch_settlements"
    cache.add(lock, "running", 300)  # another run holds it
    assert tasks.fetch_settlements() is None and not razorpay_settlements.calls
    cache.delete(lock)
    result = tasks.fetch_settlements()
    assert result["day"] == "2026-10-09" and result["states"] == {"posted": 1} and cache.get(lock) is None


def test_fees_for_an_order(live, razorpay_settlements):
    order = paid_order(live=True)
    assert settlements.fees_for(order) == []
    a_day(razorpay_settlements, order)
    settlements.fetch_day(DAY)
    [fees] = settlements.fees_for(order)
    assert fees["entity"] == f"pay_{order.pk}" and fees["settlement"] == "setl_A1" and fees["utr"] == "UTR20261009001"
    assert (fees["amount"], fees["fee"], fees["tax"]) == (Decimal("299.00"), Decimal("6.00"), Decimal("1.08"))


def test_the_job_params_take_a_day_until_today():
    from rest_framework.exceptions import ValidationError

    assert settlements.job_params({"day": "2026-10-09"}) == {"day": "2026-10-09"}
    for wrong in [{}, {"day": "09/10/2026"}, {"day": (timezone.localdate() + timedelta(days=1)).isoformat()}]:
        with pytest.raises(ValidationError):
            settlements.job_params(wrong)


def test_the_nightly_reconcile_records_a_payment_that_turned_authorised_late(rzp, commit):
    order = make_order((ProductFactory(), 1))
    Order.objects.filter(pk=order.pk).update(created=timezone.now() - timedelta(hours=1))
    services.record_failure(captured(order, status="failed", error_description="Bank declined"))
    assert order.payments.get().status == Payment.Status.FAILED
    authorised = captured(order, status="authorized")
    rzp.order.payments.return_value = {"items": [authorised]}
    rzp.payment.capture.side_effect = lambda payment_id, amount, data, **kwargs: {**authorised, "status": "captured"}
    with commit():
        assert tasks.reconcile_payments() == {"paid": 1, "unpaid": 0, "unknown": 0}
    order.refresh_from_db()
    assert order.status == Order.Status.PAID and order.payments.get().status == Payment.Status.CAPTURED
    rzp.payment.capture.assert_called_once()
    lock = "single-run:shop.tasks.reconcile_payments"
    cache.add(lock, "running", 300)
    assert tasks.reconcile_payments() is None  # a run already under way: this one does nothing
    cache.delete(lock)
