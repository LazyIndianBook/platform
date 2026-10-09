"""The metrics (insights/metrics.py): each on a fixture, with the test-mode order left out, the period's days India's, a
person's scope narrowing what they count, and the definition (the docstring) that the panel shows."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from accounts import roles
from content.models import ErrorReport, Subject
from insights import metrics
from insights.metrics import Absent, Period
from learn.models import BookCode, CardReview, Chapter, Clip, FlashCard, Progress, QuizAttempt, QuizItem, Revision
from shipping.models import CodRemittance
from shop.factories import ProductFactory
from shop.models import Order, QuoteRequest, Shipment
from staff.models import ChangeRequest, StaffScope
from staff.tests.conftest import make_staff
from support import services as support
from support.models import Ticket

from .helpers import as_test, at, give_back, learners, pay, sell

pytestmark = pytest.mark.django_db
OCT = Period(date(2026, 10, 1), date(2026, 10, 7))


@pytest.fixture(autouse=True)
def live_site(settings):
    settings.RAZORPAY_KEY_ID = ""  # no keys counts as live: test-mode orders (livemode off) are then left out
    settings.SUPPORT_EMAIL = "help@examleaf.in"


@pytest.fixture
def book(physics):
    return ProductFactory(subject=physics, price=Decimal("300.00"))


def test_every_metric_has_a_definition_a_card_and_a_label():
    assert set(metrics.SPECS) >= {
        *["net_revenue", "orders_placed", "orders_to_pack", "codes_redeemed", "active_learners", "clips_completed"],
        *["quotes_open", "tickets_due", "tickets_breached", "reports_open", "items_flagged", "refunds_to_approve"],
        *["bank_refunds_to_pay", "settlement_items_unmatched", "cod_overdue"],
    }
    for key, spec in metrics.SPECS.items():
        assert spec.definition.endswith("."), key  # a docstring that is a sentence, shown on hover
        assert spec.label and spec.roles and spec.needs and spec.href.startswith("/"), key
        assert spec.group in ("measure", "queue"), key


def test_periods_are_india_days_both_ends_included():
    assert (OCT.days, OCT.previous()) == (7, Period(date(2026, 9, 24), date(2026, 9, 30)))
    assert (OCT.since, OCT.until) == (at(date(2026, 10, 1), 0), at(date(2026, 10, 8), 0))
    assert metrics.last_days(1, today=date(2026, 3, 1)) == Period(date(2026, 3, 1), date(2026, 3, 1))
    assert metrics.last_days(30, today=date(2026, 3, 1)).start == date(2026, 1, 31)  # across a month end


def test_net_revenue_is_the_money_in_less_the_money_back_in_the_period(book):
    first = pay(sell(book, date(2026, 10, 3)), when=at(date(2026, 10, 3), 23, 30))
    pay(sell(book, date(2026, 10, 7)), when=at(date(2026, 10, 7), 23, 59))  # the last day, a minute before midnight
    pay(sell(book, date(2026, 10, 8)), when=at(date(2026, 10, 8), 0, 5))  # the next day: the next period's
    earlier = pay(sell(book, date(2026, 9, 30)), when=at(date(2026, 9, 30), 23, 59))
    test = pay(as_test(sell(book, date(2026, 10, 4))), when=at(date(2026, 10, 4)))  # made with test keys: left out
    give_back(first, 100, when=at(date(2026, 10, 5)))  # money back in the period
    give_back(earlier, 50, when=at(date(2026, 10, 6)))  # of an earlier payment, but processed in this period
    give_back(first, 10, status="pending")  # asked for, not processed: no money moved
    give_back(first, 20, when=at(date(2026, 10, 5)), method="none")  # a credit note alone: no money moved
    give_back(test, 77, when=at(date(2026, 10, 5)))  # of a test payment
    now = metrics.net_revenue(None, OCT)
    assert (now.value, now.unit, now.test_mode) == (Decimal("450.00"), "inr", False)  # 600 in, 150 back
    assert now.definition.startswith("Money received less money returned") and now.period == OCT
    assert metrics.net_revenue(None, OCT.previous()).value == Decimal("300.00")
    assert metrics.net_revenue(None, Period(date(2026, 10, 8), date(2026, 10, 8))).value == Decimal("300.00")


def test_a_payment_without_a_history_row_is_dated_by_its_last_change(book):
    order = sell(book, date(2026, 10, 3))
    payment = pay(order)
    payment.history.all().delete()  # saved before its history was kept
    from shop.models import Payment

    Payment.objects.filter(pk=payment.pk).update(modified=at(date(2026, 10, 3)))
    assert metrics.net_revenue(None, OCT).value == Decimal("300.00")
    assert metrics.net_revenue(None, OCT.previous()).value == Decimal("0.00")


def test_a_site_on_test_keys_counts_every_order_and_says_so(book, settings):
    pay(as_test(sell(book, date(2026, 10, 3))), when=at(date(2026, 10, 3)))
    assert metrics.net_revenue(None, OCT).value == Decimal("0.00")
    settings.RAZORPAY_KEY_ID = "rzp_test_abc"
    found = metrics.net_revenue(None, OCT)
    assert (found.value, found.test_mode) == (
        Decimal("300.00"),
        True,
    )  # nothing to tell from the rest: all of it is test


def test_orders_placed_are_the_live_ones_not_undone_by_india_day(book):
    sell(book, date(2026, 10, 1))
    sell(book, date(2026, 10, 7), method="cod")  # placed to pay on delivery
    sell(book, date(2026, 10, 8))
    undone = sell(book, date(2026, 10, 2))
    Order.objects.filter(pk=undone.pk).update(status="cancelled")
    as_test(sell(book, date(2026, 10, 3)))
    Order.objects.filter(pk=sell(book, date(2026, 10, 4)).pk).update(placed_at=at(date(2026, 10, 7), 23, 59))
    Order.objects.filter(pk=sell(book, date(2026, 10, 5)).pk).update(placed_at=at(date(2026, 10, 8), 0, 0))
    assert metrics.orders_placed(None, OCT).value == 3  # 1 Oct, 7 Oct cod and the one at 23:59 on the 7th; not 8 Oct
    assert metrics.orders_placed(None, OCT.previous()).value == 0


def test_orders_to_pack_are_the_lists_to_pack_tab_without_test_orders(book):
    sell(book, date(2026, 10, 1))
    sell(book, date(2026, 10, 2), method="cod")
    Order.objects.filter(pk=sell(book, date(2026, 10, 3)).pk).update(held_at=timezone.now())  # on hold
    Order.objects.filter(pk=sell(book, date(2026, 10, 4)).pk).update(status="packed")
    Order.objects.filter(pk=sell(book, date(2026, 10, 5)).pk).update(placed_at=None, status="pending")  # unpaid
    as_test(sell(book, date(2026, 10, 6)))
    assert metrics.orders_to_pack(None).value == 2
    assert metrics.orders_to_pack(make_staff(roles.PACKER)).value == 2  # a packer's scope holds both
    assert metrics.orders_to_pack(make_staff(roles.SALES)).value == 2
    narrowed = make_staff(roles.SALES)
    StaffScope.objects.create(user=narrowed, kind="order_status", value="packed")
    assert metrics.orders_to_pack(narrowed).value == 0  # a person scoped to packed orders sees none to pack


def test_orders_on_the_way_leave_out_test_orders(book):
    Order.objects.filter(pk=sell(book, date(2026, 10, 1)).pk).update(status="shipped")
    Order.objects.filter(pk=as_test(sell(book, date(2026, 10, 2))).pk).update(status="shipped")
    assert metrics.orders_on_the_way(None).value == 1


def make_activity(physics):
    chapter = Chapter.objects.create(subject=physics, number=1, title="Electric Charges")
    clip = Clip.objects.create(revision=Revision.objects.create(chapter=chapter, title="Revise"), title="Gauss")
    return (
        clip,
        QuizItem.objects.create(chapter=chapter, kind="true_false", text="T", answer="true"),
        FlashCard.objects.create(chapter=chapter, front="f", back="b"),
    )


def test_codes_redeemed_in_the_period(physics):
    redeemer = learners(1)[0]
    for number, day in enumerate([date(2026, 10, 2), date(2026, 10, 7), date(2026, 10, 8), None]):
        BookCode.objects.create(
            digest=f"{number}" * 64,
            batch="PHY-2027-1",
            subject=physics,
            redeemed_by=redeemer if day else None,
            redeemed_at=at(day) if day else None,
        )
    assert metrics.codes_redeemed(None, OCT).value == 2
    assert metrics.codes_redeemed(None, OCT.previous()).value == 0


def test_active_learners_count_an_account_once_whatever_it_did_and_not_staff(physics):
    clip, item, card = make_activity(physics)
    a, b, c, d = learners(4)
    staff = make_staff(roles.CONTENT_EDITOR)
    now = timezone.now()
    QuizAttempt.objects.create(user=a, item=item, correct=True)  # a: a quiz answer and a card and a clip: one learner
    CardReview.objects.create(user=a, card=card, known=True)
    Progress.objects.create(user=a, clip=clip)
    CardReview.objects.create(user=b, card=card, known=False)
    QuizAttempt.objects.create(user=staff, item=item, correct=True)  # staff preview the course: not a learner
    QuizAttempt.objects.create(user=c, item=item, correct=True, created=now - timedelta(days=9))  # too long ago
    Progress.objects.create(user=d, clip=clip)
    Progress.objects.filter(user=d).update(updated=now - timedelta(days=8))
    found = metrics.active_learners(None, None)
    assert found.value == 2 and found.period == metrics.last_days(7)  # a window of its own: the last 7 days
    assert metrics.active_learners(None, metrics.last_days(7).previous()).value == 2  # c and d, the 7 days before
    assert metrics.active_learners(make_staff(roles.SUPPORT), None).value == 0  # no learn.view_progress


def test_clips_completed_are_counted_on_their_last_progress_without_staff(physics):
    clip, _, _ = make_activity(physics)
    a, b, c = learners(3)
    staff = make_staff(roles.CONTENT_EDITOR)
    for user, done, day in [
        (a, True, date(2026, 10, 2)),
        (b, False, date(2026, 10, 3)),
        (c, True, date(2026, 10, 9)),
        (staff, True, date(2026, 10, 4)),
    ]:
        Progress.objects.create(user=user, clip=clip, completed=done)
        Progress.objects.filter(user=user).update(updated=at(day))
    assert metrics.clips_completed(None, OCT).value == 1


def test_quotes_open_are_the_new_ones():
    for status in ("new", "new", "quoted", "ordered", "closed"):
        QuoteRequest.objects.create(
            school="Cotton Collegiate",
            contact_name="Anita Das",
            email="o@example.com",
            phone="+919864012345",
            delivery_pin="781001",
            items=[{"product": "x", "title": "X", "quantity": 1}],
            status=status,
        )
    assert metrics.quotes_open(None, None).value == 2
    assert metrics.quotes_open(make_staff(roles.SALES), None).value == 2


def ticket(**fields):
    made = support.create_ticket(
        source="email", channel="email", subject="Parcel", body="Where is it?", email="a@example.com", category="order"
    )
    Ticket.objects.filter(pk=made.pk).update(**fields)
    return made


def test_tickets_due_today_and_breached_leave_out_spam_done_and_test_orders(book):
    now = timezone.now()
    end_of_day = metrics.day_start(timezone.localdate() + timedelta(days=1))
    today = now + (end_of_day - now) / 2  # later today, whenever the test runs
    ticket(next_due_at=today)  # due today
    ticket(next_due_at=today, status="waiting_customer")  # a clock that runs
    ticket(next_due_at=end_of_day + timedelta(hours=1))  # tomorrow: neither
    ticket(next_due_at=now - timedelta(hours=1))  # breached
    ticket(next_due_at=now - timedelta(days=3), status="open")  # breached
    ticket(next_due_at=now - timedelta(hours=2), status="resolved")  # done: no clock
    ticket(next_due_at=now - timedelta(hours=2), status="spam")  # quarantined
    test_order = as_test(sell(book, date(2026, 10, 1)))
    ticket(next_due_at=now - timedelta(hours=2), order=test_order)  # about a test order
    ticket(next_due_at=today, order=test_order)
    assert metrics.tickets_due(None, None).value == 2
    assert metrics.tickets_breached(None, None).value == 2
    sales = make_staff(roles.SALES)  # SALES reaches the order, payment and school-order tickets
    assert metrics.tickets_breached(sales, None).value == 2
    assert metrics.tickets_breached(make_staff(roles.PACKER), None).value == 0  # no support.view_ticket


def test_reports_open_and_items_flagged_are_the_open_ones_in_the_persons_subjects(physics):
    other = Subject.objects.create(name="Chemistry", code="CHE", board=physics.board, class_level=physics.class_level)
    target = ContentType.objects.get_for_model(Subject)
    for subject, category, state, spam in [
        (physics, "typo", "reported", False),
        (physics, "item_analysis", "confirmed", False),
        (physics, "typo", "fixed_online", False),
        (physics, "typo", "rejected", False),
        (physics, "typo", "reported", True),
        (other, "item_analysis", "reported", False),
    ]:
        ErrorReport.objects.create(
            target_type=target, target_id=subject.pk, subject=subject, category=category, state=state, spam=spam
        )
    assert metrics.reports_open(None, None).value == 3 and metrics.items_flagged(None, None).value == 2
    editor = make_staff(roles.CONTENT_EDITOR)
    StaffScope.objects.create(user=editor, kind="subject", value="PHY")
    assert metrics.reports_open(editor, None).value == 2 and metrics.items_flagged(editor, None).value == 1


def test_refunds_to_approve_are_the_pending_ones_not_the_persons_own_and_not_test_orders(book):
    maker, approver = make_staff(roles.SALES), make_staff(roles.FINANCE)
    live, test = sell(book, date(2026, 10, 1)), as_test(sell(book, date(2026, 10, 2)))

    def ask(order, maker_=maker, status="pending", hours=24):
        return ChangeRequest.objects.create(
            action="order.refund",
            target_type="shop.order",
            target_id=str(order.pk),
            target_label=order.number,
            payload={},
            payload_sha256="0" * 64,
            maker=maker_,
            reason="Damaged",
            status=status,
            expires_at=timezone.now() + timedelta(hours=hours),
        )

    ask(live), ask(live, status="executed"), ask(live, hours=-1), ask(test), ask(live, maker_=approver)
    other = ChangeRequest.objects.create(
        action="product.price",
        target_type="shop.product",
        target_id="1",
        payload={},
        payload_sha256="0" * 64,
        maker=maker,
        reason="x",
        expires_at=timezone.now() + timedelta(hours=1),
    )
    assert other.pk and metrics.refunds_to_approve(None, None).value == 2  # live, and the approver's own
    assert metrics.refunds_to_approve(approver, None).value == 1  # not the one they made themselves


def test_bank_refunds_to_pay_and_cod_overdue_leave_out_test_orders(book):
    live, test = sell(book, date(2026, 10, 1)), as_test(sell(book, date(2026, 10, 2)))
    for order in (live, test):
        payment = pay(order)
        give_back(payment, 50, status="pending", method="bank")
        give_back(payment, 60, status="pending")  # to the source: Razorpay's, not a transfer
        give_back(payment, 70, status="processed", method="bank", when=timezone.now())  # already paid
        shipment = Shipment.objects.create(order=order, courier="India Post", tracking_number=f"T{order.pk}")
        CodRemittance.objects.create(
            shipment=shipment, expected_amount=300, expected_on=date(2026, 10, 1), state="overdue"
        )
        shipment = Shipment.objects.create(order=order, courier="India Post", tracking_number=f"U{order.pk}")
        CodRemittance.objects.create(shipment=shipment, expected_amount=300, expected_on=date(2026, 10, 1))
    assert metrics.bank_refunds_to_pay(None, None).value == 1
    assert metrics.cod_overdue(None, None).value == 1
    assert metrics.cod_overdue(make_staff(roles.FINANCE), None).value == 1


def test_a_metric_whose_source_is_not_installed_is_absent_not_zero(monkeypatch):
    with pytest.raises(Absent):
        metrics.model("finance.Nothing")
    real = metrics.model

    def without_finance(label):  # the Finance module's settlements, as before it was merged
        if label.startswith("shop.Settlement"):
            raise Absent(label)
        return real(label)

    monkeypatch.setattr(metrics, "model", without_finance)
    with pytest.raises(Absent):
        metrics.settlement_items_unmatched(None, None)


def test_every_order_metric_leaves_the_test_order_out_by_construction(book):
    """One fixture of nothing but test-mode rows: every metric that reads orders counts none of it."""
    order = as_test(sell(book, date(2026, 10, 3)))
    payment = pay(order, when=at(date(2026, 10, 3)))
    give_back(payment, 100, when=at(date(2026, 10, 4)))
    give_back(payment, 50, status="pending", method="bank")
    shipment = Shipment.objects.create(order=order, courier="India Post", tracking_number="T1")
    CodRemittance.objects.create(shipment=shipment, expected_amount=300, expected_on=date(2026, 10, 1), state="overdue")
    ChangeRequest.objects.create(
        action="order.refund",
        target_type="shop.order",
        target_id=str(order.pk),
        payload={},
        payload_sha256="0" * 64,
        maker=make_staff(roles.SALES),
        reason="x",
        expires_at=timezone.now() + timedelta(hours=1),
    )
    Order.objects.filter(pk=order.pk).update(status="shipped")
    for key, spec in metrics.SPECS.items():
        if spec.orders:
            assert spec.run(None, OCT).value == 0, key
