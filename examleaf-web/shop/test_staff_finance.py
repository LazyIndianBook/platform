"""The Finance module's staff API (shop/staff_finance.py): payments and the stuck ones, a payment asked of Razorpay
again (the late-authorised case), offline payments and refunds waiting for approval, payment links for orders and
for ERPNext's B2B invoices (with the manual posting ERPNext's contract leaves to FINANCE), settlements with a line
matched by hand and a day fetched as a job, Finance today's counts with test mode left out, a document's ERPNext
mirror, and the lists' queries. Razorpay's SDK is mocked (conftest.rzp) and its settlement API recorded
(conftest.FakeSettlements): nothing leaves the tests."""

import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from accounts import roles
from erp.models import ErpLink, ErpMirror, ErpReconciliationDifference, ErpReconciliationRun
from shop import services
from shop.factories import WEBHOOK_SECRET, ProductFactory, captured, make_order, post_webhook, sign
from shop.models import (
    Invoice,
    InvoicePaymentLink,
    Order,
    Payment,
    Refund,
    Settlement,
    SettlementLine,
    WebhookEvent,
)
from staff import approvals
from staff.models import AuditEvent, ChangeRequest, InboxItem, Job
from staff.tests.conftest import STAFF, make_staff, signed_in

pytestmark = pytest.mark.django_db
FINANCE = STAFF + "finance/"
DAY = "2026-10-09"


@pytest.fixture
def finance():
    return signed_in(make_staff(roles.FINANCE))


def aged(order, minutes=30):
    Payment.objects.filter(order=order).update(created=timezone.now() - timedelta(minutes=minutes))
    Order.objects.filter(pk=order.pk).update(created=timezone.now() - timedelta(minutes=minutes))


def ids(response):
    assert response.status_code == 200, response.content
    return [row["id"] for row in response.json()["results"]]


# Payments


def test_the_stuck_filter_finds_old_unpaid_payments_and_captured_ones_on_pending_orders(finance, rzp):
    old = make_order((ProductFactory(), 1))  # its checkout opened half an hour ago, nothing heard since
    aged(old)
    fresh = make_order((ProductFactory(), 1))  # the customer may be paying now
    captured_on_pending = make_order((ProductFactory(), 1))
    Payment.objects.filter(order=captured_on_pending).update(status=Payment.Status.CAPTURED)  # the order's webhook lost
    paid = make_order((ProductFactory(), 1))
    services.record_capture(captured(paid))
    aged(paid)
    never = make_order((ProductFactory(), 1))  # never reached Razorpay
    Payment.objects.filter(order=never).update(razorpay_order_id=None)
    aged(never)
    staff_order = make_order((ProductFactory(), 1))  # a link, still within its 15 days
    Payment.objects.filter(order=staff_order).update(razorpay_order_id=None, razorpay_payment_link_id="plink_1")
    aged(staff_order, minutes=60 * 24)
    stuck = ids(finance.get(FINANCE + "payments/?stuck=true"))
    pk = lambda order: order.payments.get().pk  # noqa: E731
    assert sorted(stuck) == sorted([pk(old), pk(captured_on_pending)])
    rows = {row["id"]: row for row in finance.get(FINANCE + "payments/").json()["results"]}
    assert rows[pk(old)]["stuck"] and not rows[pk(fresh)]["stuck"] and not rows[pk(staff_order)]["stuck"]
    assert rows[pk(paid)]["order"] == paid.number and rows[pk(staff_order)]["is_link"]
    assert set(ids(finance.get(FINANCE + "payments/?stuck=false"))) == set(rows) - set(stuck)


def test_payments_are_found_by_order_number_and_razorpay_ids_and_test_ones_only_when_asked(finance, settings, rzp):
    paid = make_order((ProductFactory(), 1))
    services.record_capture(captured(paid))
    payment = paid.payments.get()
    assert ids(finance.get(FINANCE + f"payments/?q={paid.number}")) == [payment.pk]
    assert ids(finance.get(FINANCE + f"payments/?q=pay_{paid.pk}")) == [payment.pk]
    assert ids(finance.get(FINANCE + f"payments/?q=order_{paid.pk}")) == [payment.pk]
    assert ids(finance.get(FINANCE + "payments/?q=UTR-NONE")) == []
    settings.RAZORPAY_KEY_ID = "rzp_live_key"  # the live site: the test payments are TEST, kept apart
    assert ids(finance.get(FINANCE + "payments/")) == []
    rows = finance.get(FINANCE + "payments/?livemode=false").json()["results"]
    assert [row["id"] for row in rows] == [payment.pk] and rows[0]["is_test"]


def test_a_payment_record_lists_its_webhooks_and_timeline(client, finance, rzp):
    order = make_order((ProductFactory(), 1))
    assert post_webhook(client, "payment.captured", captured(order), event_id="evt_1").status_code == 200
    payment = order.payments.get()
    assert WebhookEvent.objects.get().payment == payment
    record = finance.get(FINANCE + f"payments/{payment.pk}/").json()
    assert [hook["event_id"] for hook in record["webhooks"]] == ["evt_1"]
    assert record["status"] == "captured" and record["order_status"] == "paid"
    assert {entry["kind"] for entry in record["timeline"]} >= {"payment", "webhook"}
    assert not any(entry["kind"] == "audit" for entry in record["timeline"])  # FINANCE does not read the audit log
    owner = signed_in(make_staff(roles.OWNER))
    owner.post(FINANCE + f"payments/{payment.pk}/reconcile/", {}, format="json")
    timeline = owner.get(FINANCE + f"payments/{payment.pk}/").json()["timeline"]
    assert any(entry["kind"] == "audit" and entry["label"] == "payment.reconciled" for entry in timeline)
    assert AuditEvent.objects.filter(action="audit.read", target_type="shop.payment").exists()


def test_asking_razorpay_again_records_a_payment_that_turned_authorised_late(finance, rzp):
    order = make_order((ProductFactory(), 1))
    services.record_failure(captured(order, status="failed", error_description="Bank declined"))
    payment = order.payments.get()
    authorised = captured(order, status="authorized")
    rzp.order.payments.return_value = {"items": [authorised]}
    rzp.payment.capture.side_effect = lambda payment_id, amount, data, **kwargs: {**authorised, "status": "captured"}
    response = finance.post(FINANCE + f"payments/{payment.pk}/reconcile/", {}, format="json")
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["paid"] is True and body["changes"]["order"] == ["pending", "paid"]
    assert body["changes"][f"payment {payment.pk}"] == ["failed", "captured"]
    assert body["payment"]["status"] == "captured" and "the order is paid now" in body["detail"]
    event = AuditEvent.objects.get(action="payment.reconciled")
    assert event.target_type == "shop.payment" and event.details["paid"] is True
    rzp.order.payments.return_value = {"items": []}
    again = finance.post(FINANCE + f"payments/{payment.pk}/reconcile/", {}, format="json").json()
    assert again["changes"] == {} and "nothing changed" in again["detail"]


def test_asking_razorpay_again_is_for_online_payments_of_the_keys_in_force(finance, rzp, settings):
    import requests

    order = make_order((ProductFactory(), 1))
    online = order.payments.get()
    offline = Payment.objects.create(order=order, method="offline", amount=Decimal("299.00"), reference="UTR1")
    response = finance.post(FINANCE + f"payments/{offline.pk}/reconcile/", {}, format="json")
    assert response.status_code == 400 and "not made online" in response.json()["non_field_errors"][0]
    rzp.order.payments.side_effect = requests.ConnectionError("down")
    response = finance.post(FINANCE + f"payments/{online.pk}/reconcile/", {}, format="json")
    assert response.status_code == 503 and response.json()["code"] == "unavailable"
    assert AuditEvent.objects.get(action="payment.reconciled").details["paid"] is None
    settings.RAZORPAY_KEY_ID = "rzp_live_key"
    response = finance.post(FINANCE + f"payments/{online.pk}/reconcile/", {}, format="json")
    assert response.status_code == 400 and "test keys" in response.json()["non_field_errors"][0]


# Offline payments and refunds waiting for FINANCE


def test_offline_payments_waiting_and_recorded(finance, rzp):
    sales = make_staff(roles.SALES)  # ₹5,000 offline at most
    order = make_order((ProductFactory(price=Decimal("6000.00")), 1))
    change_request, _ = approvals.ask(
        "order.offline_payment", maker=sales, target=order.number, payload={"reference": "UTR123"}, reason="NEFT in"
    )
    assert change_request.status == ChangeRequest.Status.PENDING
    [row] = finance.get(FINANCE + "offline-payments/?state=waiting").json()["results"]
    assert row["kind"] == "request" and row["change_request"] == change_request.pk and row["order"] == order.number
    assert row["checker"] == "staff.approve_payment" and row["reference"] == "UTR123" and row["amount"] == "6000.00"
    assert finance.get(FINANCE + "offline-payments/").json()["results"] == []
    small = make_order((ProductFactory(), 1))
    payload = {"reference": "UPI77"}
    approvals.ask("order.offline_payment", maker=sales, target=small.number, payload=payload, reason="UPI")
    [recorded] = finance.get(FINANCE + "offline-payments/").json()["results"]
    assert recorded["kind"] == "payment" and recorded["order"] == small.number and recorded["reference"] == "UPI77"
    assert recorded["by"] == (sales.full_name or sales.email) and recorded["change_request_status"] == "executed"


def test_refunds_by_state_with_the_requests_waiting(finance, rzp):
    support = make_staff(roles.SUPPORT)  # ₹1,000 at most
    order = make_order((ProductFactory(price=Decimal("1500.00")), 1))
    services.record_capture(captured(order))
    asked, _ = approvals.ask(
        "order.refund", maker=support, target=order.number, payload={"amount": "1500.00"}, reason="Never arrived"
    )
    [waiting] = finance.get(FINANCE + "refunds/?state=waiting").json()["results"]
    assert waiting["kind"] == "request" and waiting["id"] == asked.pk and waiting["checker"] == "staff.approve_refund"
    refund = Refund.objects.create(
        order=order, payment=order.payments.get(), amount=Decimal("100.00"), reason="Damaged", method="bank",
        payee_masked="UPI ra•••@ok",
    )  # fmt: skip
    rows = finance.get(FINANCE + "refunds/?state=pending&method=bank").json()["results"]
    assert [(row["kind"], row["id"], row["payee_masked"]) for row in rows] == [("refund", refund.pk, "UPI ra•••@ok")]
    assert finance.get(FINANCE + "refunds/?state=processed").json()["results"] == []
    assert signed_in(make_staff(roles.PACKER)).get(FINANCE + "refunds/").status_code == 403


# Payment links


def test_an_orders_link_is_sent_cancelled_and_made_again_under_a_new_reference(finance, rzp):
    sales = signed_in(make_staff(roles.SALES))
    order = make_order((ProductFactory(), 1))
    Order.objects.filter(pk=order.pk).update(created_by=make_staff(roles.SALES))
    Payment.objects.filter(order=order).delete()
    made = iter(["plink_1", "plink_2"])
    rzp.payment_link.create.side_effect = lambda data, **kw: {"id": next(made), "short_url": "https://rzp.io/i/x"}
    response = sales.post(FINANCE + "payment-links/", {"order": order.number, "action": "send"}, format="json")
    assert response.status_code == 200, response.content
    assert response.json()["state"] == "sent" and response.json()["razorpay_link_id"] == "plink_1"
    assert rzp.payment_link.create.call_args.args[0]["reference_id"] == order.number
    assert (
        sales.post(FINANCE + "payment-links/", {"order": order.number, "action": "cancel"}, format="json").json()[
            "state"
        ]
        == "cancelled"
    )
    sales.post(FINANCE + "payment-links/", {"order": order.number, "action": "send"}, format="json")
    assert rzp.payment_link.create.call_args.args[0]["reference_id"] == f"{order.number}-2"  # Razorpay's once each
    rows = finance.get(FINANCE + "payment-links/").json()["results"]
    assert [(row["razorpay_link_id"], row["state"]) for row in rows] == [("plink_2", "sent"), ("plink_1", "cancelled")]
    assert rows[0]["last_sent_at"] is not None
    assert AuditEvent.objects.filter(action="order.payment_link_sent").count() == 2
    website = make_order((ProductFactory(), 1))  # the website's own: its payment page is its link
    refused = sales.post(FINANCE + "payment-links/", {"order": website.number, "action": "send"}, format="json")
    assert refused.status_code == 400 and "placed on the website" in refused.json()["non_field_errors"][0]
    assert finance.post(FINANCE + "payment-links/", {"order": order.number, "action": "send"}).status_code == 403


def b2b_invoice(name="ACC-SINV-2026-00007", outstanding=12500.0, **data):
    return ErpMirror.objects.create(
        doctype="Sales Invoice",
        name=name,
        status="Unpaid",
        data={"name": name, "customer_group": "School", "docstatus": 1, "is_return": 0,
              "outstanding_amount": outstanding, "grand_total": outstanding, **data},
    )  # fmt: skip


def test_a_b2b_invoices_link_is_made_paid_and_posted_by_hand(client, finance, rzp):
    sales = signed_in(make_staff(roles.SALES))
    b2b_invoice()
    rzp.payment_link.create.return_value = {"id": "plink_b2b", "short_url": "https://rzp.io/i/b2b"}
    ask = {"invoice": "ACC-SINV-2026-00007", "action": "send"}
    response = sales.post(FINANCE + "payment-links/", ask, format="json")
    assert response.status_code == 201, response.content
    assert response.json()["url"] == "https://rzp.io/i/b2b" and response.json()["amount"] == "12500.00"
    sent = rzp.payment_link.create.call_args.args[0]
    assert sent["amount"] == 1250000 and sent["notify"] == {"sms": False, "email": False} and "customer" not in sent
    assert sales.post(FINANCE + "payment-links/", ask, format="json").status_code == 200  # the open one again
    assert rzp.payment_link.create.call_count == 1
    link = InvoicePaymentLink.objects.get()
    payment = {"id": "pay_b2b", "order_id": "order_b2b", "amount": 1250000, "currency": "INR", "status": "captured"}
    body = json.dumps(
        {
            "event": "payment_link.paid",
            "payload": {
                "payment_link": {"entity": {"id": "plink_b2b", "status": "paid"}},
                "payment": {"entity": payment},
            },
        }
    )
    headers = {"HTTP_X_RAZORPAY_SIGNATURE": sign(body, WEBHOOK_SECRET), "HTTP_X_RAZORPAY_EVENT_ID": "evt_b2b"}
    webhook = client.post(reverse("shop:razorpay_webhook"), body, content_type="application/json", **headers)
    assert webhook.status_code == 200
    link.refresh_from_db()
    assert link.status == "paid" and link.razorpay_payment_id == "pay_b2b"
    item = InboxItem.objects.get(kind="b2b_payment", done_at=None)
    assert "ACC-SINV-2026-00007" in item.title and item.permission == "staff.reconcile_settlements"
    posted = finance.post(FINANCE + f"payment-links/invoices/{link.pk}/posted/", {"erp_name": "ACC-PAY-0001"})
    assert posted.status_code == 200 and posted.json()["erp_name"] == "ACC-PAY-0001"
    assert InboxItem.objects.get(pk=item.pk).done_at is not None
    again = finance.post(FINANCE + f"payment-links/invoices/{link.pk}/posted/", {"erp_name": "ACC-PAY-0002"})
    assert again.status_code == 400
    actions = set(AuditEvent.objects.filter(target_type="shop.invoicepaymentlink").values_list("action", flat=True))
    assert actions == {"payment.link_made", "payment.link_paid", "payment.link_posted"}
    [row] = finance.get(FINANCE + "payment-links/?kind=invoice").json()["results"]
    assert row["kind"] == "invoice" and row["state"] == "paid" and row["posted_at"]


def test_a_b2b_link_needs_a_submitted_invoice_with_something_outstanding(rzp):
    sales = signed_in(make_staff(roles.SALES))
    b2b_invoice("ACC-SINV-1", outstanding=0)
    b2b_invoice("ACC-SINV-2", docstatus=2)
    b2b_invoice("ACC-SINV-3", is_return=1)
    for name, words in [("ACC-SINV-1", "nothing outstanding"), ("ACC-SINV-2", "not submitted"),
                        ("ACC-SINV-3", "credit note"), ("ACC-SINV-404", "No B2B invoice")]:  # fmt: skip
        response = sales.post(FINANCE + "payment-links/", {"invoice": name, "action": "send"}, format="json")
        assert response.status_code == 400 and words in response.json()["non_field_errors"][0], name
    assert not rzp.payment_link.create.called


def test_a_b2b_link_lost_webhook_is_asked_of_razorpay_again(finance, rzp):
    b2b_invoice()
    link = InvoicePaymentLink.objects.create(
        invoice="ACC-SINV-2026-00007", amount=Decimal("12500.00"), razorpay_payment_link_id="plink_9",
        expires_at=timezone.now() + timedelta(days=15),
    )  # fmt: skip
    rzp.payment_link.fetch.return_value = {"status": "paid", "payments": [{"payment_id": "pay_9"}]}
    rzp.payment.fetch.return_value = {"id": "pay_9", "amount": 1250000, "status": "captured"}
    response = finance.post(FINANCE + f"payment-links/invoices/{link.pk}/reconcile/")
    assert response.status_code == 200 and response.json()["state"] == "paid"
    assert InboxItem.objects.filter(kind="b2b_payment", done_at=None).count() == 1


# Settlements


def test_settlements_their_lines_a_match_by_hand_and_a_day_fetched_as_a_job(
    settings, finance, razorpay_settlements, commit
):
    from datetime import date

    settings.RAZORPAY_KEY_ID = "rzp_live_key"
    order = make_order((ProductFactory(), 1))
    Order.objects.filter(pk=order.pk).update(livemode=True)
    Payment.objects.filter(order=order).update(livemode=True)
    services.record_capture(captured(order))
    razorpay_settlements.add(
        date(2026, 10, 9),
        "setl_X",
        {"type": "payment", "entity_id": f"pay_{order.pk}", "amount": "299.00", "fee": "7.08", "tax": "1.08"},
        {"type": "adjustment", "entity_id": "adj_X", "amount": "5.00", "debit": "5.00"},
    )
    with commit():
        response = finance.post(FINANCE + "settlements/fetch/", {"day": DAY}, format="json")
    assert response.status_code == 202 and response.json()["kind"] == "settlement_fetch"
    job = Job.objects.get()
    assert job.state == Job.State.DONE and job.result["lines"] == 2, job.errors
    [row] = finance.get(FINANCE + "settlements/").json()["results"]
    assert row["settlement_id"] == "setl_X" and row["state"] == "mismatched" and row["net"] == "286.92"
    record = finance.get(FINANCE + f"settlements/{row['id']}/").json()
    assert record["counts"] == {"lines": 2, "unmatched": 1, "payment": 1, "refund": 0, "adjustment": 1}
    [unmatched] = finance.get(FINANCE + f"settlements/{row['id']}/lines/?matched=false").json()["results"]
    assert unmatched["entity_id"] == "adj_X" and unmatched["debit"] == "5.00"
    matched = finance.get(FINANCE + f"settlements/{row['id']}/lines/?matched=true").json()["results"]
    assert matched[0]["payment"]["order"] == order.number and matched[0]["fee"] == "6.00"
    ask = {"line": unmatched["id"], "accept": True, "note": "A chargeback fee"}
    answer = finance.post(FINANCE + f"settlements/{row['id']}/match/", ask, format="json")
    assert answer.status_code == 200 and answer.json()["matched"] and answer.json()["matched_by"]
    assert finance.get(FINANCE + f"settlements/{row['id']}/").json()["state"] == "matched"  # the flow is off
    payment_row = finance.get(FINANCE + f"payments/{order.payments.get().pk}/").json()
    assert payment_row["fee"] == "6.00" and payment_row["settlement"]["settlement_id"] == "setl_X"
    for wrong in [{"day": "2026-13-01"}, {}]:
        assert finance.post(FINANCE + "settlements/fetch/", wrong, format="json").status_code == 400
    support = signed_in(make_staff(roles.SUPPORT))  # payments yes, settlements no
    assert support.get(FINANCE + "settlements/").status_code == 403
    assert support.get(FINANCE + "payments/").status_code == 200


def test_a_match_by_hand_is_refused_with_its_words(finance, settings, razorpay_settlements):
    settings.RAZORPAY_KEY_ID = "rzp_live_key"
    settlement = Settlement.objects.create(settlement_id="setl_Y", date=timezone.localdate(), livemode=True, net=1)
    line = SettlementLine.objects.create(settlement=settlement, type="payment", entity_id="pay_y", amount=1, credit=1)
    url = FINANCE + f"settlements/{settlement.pk}/match/"
    assert finance.post(url, {"line": line.pk, "accept": True}, format="json").status_code == 400  # no note
    response = finance.post(url, {"line": line.pk, "accept": True, "note": "?"}, format="json")
    assert response.status_code == 400 and "Only an adjustment" in response.json()["non_field_errors"][0]
    missing = finance.post(url, {"line": 999999, "accept": True, "note": "?"}, format="json")
    assert missing.status_code == 400 and "line" in missing.json()


# Finance today


def test_finance_today_counts_what_waits_and_leaves_test_mode_out(settings, rzp):
    settings.RAZORPAY_KEY_ID = "rzp_live_key"
    support = make_staff(roles.SUPPORT)

    def order(live, price="1500.00"):
        made = make_order((ProductFactory(price=Decimal(price)), 1))
        Order.objects.filter(pk=made.pk).update(livemode=live)
        Payment.objects.filter(order=made).update(livemode=live)
        return Order.objects.get(pk=made.pk)

    for live in (True, False):  # a refund waiting for approval on a live order and on a test one
        paid = order(live)
        Payment.objects.filter(order=paid).update(status="captured", razorpay_payment_id=f"pay_{paid.pk}")
        Order.objects.filter(pk=paid.pk).update(status="paid", placed_at=timezone.now())
        approvals.ask("order.refund", maker=support, target=paid.number, payload={"amount": "1500.00"}, reason="x")
        bank = Refund.objects.create(order=paid, payment=paid.payments.get(), amount=10, reason="x", method="bank")
        assert bank.status == Refund.Status.PENDING
        stuck = order(live)
        aged(stuck)
    settlement = Settlement.objects.create(settlement_id="setl_T", date=timezone.localdate(), livemode=True,
                                           state=Settlement.State.MISMATCHED, net=Decimal("50.00"))  # fmt: skip
    SettlementLine.objects.create(settlement=settlement, type="adjustment", entity_id="adj_T", amount=50, credit=50)
    run = ErpReconciliationRun.objects.create(date=timezone.localdate())
    ErpReconciliationDifference.objects.create(run=run, kind="payments", key="receive razorpay amount")
    rows = {row["key"]: row for row in signed_in(make_staff(roles.FINANCE)).get(FINANCE + "today/").json()["rows"]}
    assert rows["refunds_to_approve"]["count"] == 1 and rows["refunds_to_approve"]["amount"] == "1500.00"
    assert rows["bank_refunds"]["count"] == 1 and rows["stuck_payments"]["count"] == 1
    assert rows["settlements_mismatched"]["count"] == 1 and rows["settlement_lines"]["count"] == 1
    assert rows["sync_differences"]["count"] == 1
    assert rows["disputes"] == {"key": "disputes", "count": None, "oldest": None, "amount": None, "configured": False}
    assert rows["refunds_to_approve"]["oldest"] == timezone.localdate().isoformat()
    supports = {row["key"] for row in signed_in(support).get(FINANCE + "today/").json()["rows"]}
    assert "refunds_to_approve" in supports and not {"settlements_mismatched", "settlement_lines"} & supports
    assert signed_in(make_staff(roles.PACKER)).get(FINANCE + "today/").status_code == 403


# A document's ERPNext mirror


def test_a_documents_erpnext_mirror(finance, settings, rzp):
    order = make_order((ProductFactory(), 1))
    Order.objects.filter(pk=order.pk).update(livemode=True)
    settings.RAZORPAY_KEY_ID = "rzp_live_key"
    invoice = Invoice.objects.create(order=order, number="EL/2026-27/00009", financial_year="2026-27", serial=9,
                                     series="EL", document_type="bill_of_supply")  # fmt: skip
    url = FINANCE + "documents/EL-2026-27-00009/erp/"
    assert finance.get(url).json()["state"] == "off"  # ERP_SYNC_INVOICES off: nothing goes
    settings.ERP_SYNC_INVOICES = True
    assert finance.get(url).json()["state"] == "not_sent"
    ErpLink.objects.create(examleaf_ref=f"invoice:{invoice.number}", model="shop.invoice", object_id=str(invoice.pk),
                           doctype="Sales Invoice", name=invoice.number)  # fmt: skip
    body = finance.get(url).json()
    assert body["state"] == "mirrored" and body["doctype"] == "Sales Invoice" and body["kind"] == "invoice"
    assert finance.get(FINANCE + "documents/EL-2026-27-99999/erp/").status_code == 404


# Queries: a list reads as many queries with one row as with four


def queries(api, path):
    api.get(path)
    with CaptureQueriesContext(connection) as captured_:
        assert api.get(path).status_code == 200
    return len(captured_)


def test_the_lists_read_their_rows_at_once(finance, rzp):
    def rows(count):
        for _ in range(count):
            order = make_order((ProductFactory(), 1))
            services.record_capture(captured(order))
            Order.objects.filter(pk=order.pk).update(created_by=make_staff(roles.SALES))
            link = f"plink_{order.pk}"
            Payment.objects.create(order=order, method="razorpay", amount=1, razorpay_payment_link_id=link)
            Refund.objects.create(order=order, payment=order.payments.first(), amount=1, reason="x", method="bank")
            Payment.objects.create(order=order, method="offline", amount=1, reference=f"UTR{order.pk}")
            InvoicePaymentLink.objects.create(
                invoice=f"ACC-{order.pk}", amount=1, razorpay_payment_link_id=f"pl_{order.pk}",
                expires_at=timezone.now(), created_by=make_staff(roles.SALES),
            )  # fmt: skip
            settlement = Settlement.objects.create(settlement_id=f"setl_{order.pk}", date=timezone.localdate(), net=1)
            SettlementLine.objects.create(settlement=settlement, type="payment", entity_id=f"pay_{order.pk}",
                                          amount=1, payment=order.payments.first(), order=order)  # fmt: skip
        return Settlement.objects.order_by("pk").first()

    first = rows(1)
    paths = ["payments/", "payment-links/", "payment-links/?kind=invoice", "refunds/", "offline-payments/",
             "settlements/", f"settlements/{first.pk}/lines/"]  # fmt: skip
    one = {path: queries(finance, FINANCE + path) for path in paths}
    rows(3)
    SettlementLine.objects.update(settlement=first)  # four lines in one settlement
    assert {path: queries(finance, FINANCE + path) for path in paths} == one
