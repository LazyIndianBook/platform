"""The approval paths of Phase B's actions (plan 9.2; research 1.5: maker-checker, what you see is what you sign).
Each action that can wait (a coupon or an offer made or changed beyond the maker's discount limit, a price) keeps four
rules: its maker never approves it, its checker approves only the payload they read (its hash), an expired request is
refused, and its execution checks its preconditions again and fails rather than do something else. The actions that
never wait on their own (the course's grants, extensions, revocations and the quiz bank's metadata; the customers'
suspensions, sign-outs and consent links: bulk actions, whose job waits as a whole) check their preconditions again
when they run, and the job's own request (job.run) keeps the four rules."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from accounts import roles
from accounts.factories import UserFactory
from shop.factories import CouponFactory, ProductFactory
from shop.models import Coupon, Offer, Product
from staff import approvals, jobs
from staff.models import ChangeRequest, Job

from .conftest import make_staff

pytestmark = pytest.mark.django_db
Status = ChangeRequest.Status


def coupon_change():
    coupon = CouponFactory(code="DEEPER", value=Decimal(10))
    return make_staff(roles.MARKETING), "DEEPER", {"value": "40"}, lambda: Coupon.objects.filter(
        pk=coupon.pk).update(value=Decimal(15))  # fmt: skip


def offer_change():
    offer = Offer.objects.create(name="A spring offer", value=10)
    return make_staff(roles.MARKETING), str(offer.pk), {"value": "40"}, lambda: Offer.objects.filter(
        pk=offer.pk).update(value=15)  # fmt: skip


def offer_create():
    def tamper():  # the stored payload changed after the approval: the hash no longer matches
        ChangeRequest.objects.filter(action="offer.create").update(payload={"name": "Another", "value": "90"})

    return make_staff(roles.MARKETING), "", {"name": "A big sale", "value": "50"}, tamper


def coupon_create():
    return make_staff(roles.MARKETING), "BIG50", {"kind": "percent", "value": "50"}, lambda: CouponFactory(code="BIG50")


def price():
    product = ProductFactory(slug="priced", mrp=Decimal(349), price=Decimal(349))
    return make_staff(roles.SALES), "priced", {"price": "200.00"}, lambda: Product.objects.filter(
        pk=product.pk).update(price=Decimal(300))  # fmt: skip


WAITING = {  # an action: (its maker, target, payload beyond the maker's limit, a change to the world meanwhile)
    "coupon.change": coupon_change,
    "offer.change": offer_change,
    "offer.create": offer_create,
    "coupon.create": coupon_create,
    "product.price": price,
}


def asked(name, maker, target, payload, key):
    change, _ = approvals.ask(name, maker=maker, target=target, payload=payload, reason="Testing", idempotency_key=key)
    return change


@pytest.mark.parametrize("name", sorted(WAITING))
def test_an_action_that_waits_keeps_the_four_rules(name):
    maker, target, payload, meanwhile = WAITING[name]()
    change = asked(name, maker, target, payload, "first")
    assert change.status == Status.PENDING, change.rule
    checker = make_staff(roles.FINANCE)  # staff.approve_discount
    with pytest.raises(PermissionDenied):  # the maker never approves
        approvals.approve(change, user=maker, payload_sha256=change.payload_sha256)
    with pytest.raises(ValidationError):  # the checker approves what they read, by its hash
        approvals.approve(change, user=checker, payload_sha256="0" * 64)
    ChangeRequest.objects.filter(pk=change.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
    with pytest.raises(ValidationError):  # expired: refused
        approvals.approve(change, user=checker, payload_sha256=change.payload_sha256)
    assert ChangeRequest.objects.get(pk=change.pk).status == Status.EXPIRED
    again = asked(name, maker, target, payload, "second")
    approvals.approve(again, user=checker, payload_sha256=again.payload_sha256)
    meanwhile()  # the world changed between the approval and the run
    done = approvals.execute(ChangeRequest.objects.get(pk=again.pk), by=checker)
    assert done.status == Status.FAILED, done.result


def a_minor(**fields):
    today = date.today()
    return UserFactory(date_of_birth=today.replace(year=today.year - 15), parent_contact="parent@example.com", **fields)


def course_subject():
    from content.conftest import make_paper
    from content.models import Subject

    return Subject.objects.filter(code="PHY").first() or make_paper().book.subject


def entitlement():
    from learn.models import Entitlement

    return Entitlement.objects.create(user=UserFactory(), subject=course_subject(),
                                      valid_until=timezone.localdate() + timedelta(days=30))  # fmt: skip


def quiz_item():
    from learn.models import QuizItem
    from learn.tests import make_course

    make_course(subject=course_subject(), chapters=1, clips=1)
    return QuizItem.objects.filter(chapter__subject__code="PHY").first()


def gone(model, pk):
    return lambda: model._base_manager.filter(pk=pk).update(**({"deleted_at": timezone.now()}))


def never_waits():
    """(an action: its maker's role, the target, the payload, a change to the world that its run refuses)."""
    from accounts.models import ConsentRecord, User
    from learn.models import Entitlement, QuizItem

    customer, suspended, child = UserFactory(), UserFactory(is_active=False), a_minor()
    grant_to, extend, revoke, item = UserFactory(), entitlement(), entitlement(), quiz_item()
    return {
        "entitlement.grant": (roles.ADMIN, grant_to.pk, {"subject": "PHY"},
                              lambda: User.objects.filter(pk=grant_to.pk).update(is_active=False)),
        "entitlement.extend": (roles.ADMIN, extend.pk, {"days": 7},
                               lambda: Entitlement.objects.filter(pk=extend.pk).update(revoked_at=timezone.now())),
        "entitlement.revoke": (roles.ADMIN, revoke.pk, {},
                               lambda: Entitlement.objects.filter(pk=revoke.pk).update(revoked_at=timezone.now())),
        "item_metadata": (roles.ADMIN, item.pk, {"marks": 2}, gone(QuizItem, item.pk)),
        "user.suspend": (roles.ADMIN, customer.pk, {}, lambda: User.objects.filter(pk=customer.pk).update(
            is_active=False)),
        "user.unsuspend": (roles.ADMIN, suspended.pk, {}, lambda: User.objects.filter(pk=suspended.pk).update(
            is_active=True)),
        "user.end_sessions": (roles.ADMIN, customer.pk, {}, lambda: User.objects.filter(pk=customer.pk).delete()),
        "user.resend_consent": (roles.ADMIN, child.pk, {}, lambda: ConsentRecord.objects.create(
            user=child, event=ConsentRecord.Event.GIVEN, by_parent=True, verified_at=timezone.now())),
    }  # fmt: skip


REFUSED = {  # what each says when its precondition went meanwhile
    "entitlement.grant": "This account is closed",
    "entitlement.extend": "It was revoked",
    "entitlement.revoke": "It was revoked already",
    "item_metadata": "The quiz item is gone",
    "user.suspend": "suspended already",
    "user.unsuspend": "not suspended",
    "user.end_sessions": "The account is gone",
    "user.resend_consent": "No parent's consent is pending",
}
NEVER_WAIT = list(REFUSED)


def test_the_list_holds_every_action_phase_b_added():
    phase_a = {"order.refund", "order.offline_payment", "order.staff_discount", "staff.grant_role", "staff.invite"}
    phase_a |= {"user.reset_mfa", "user.erase", "job.run"}
    assert set(approvals.ACTIONS) - phase_a == set(WAITING) | set(NEVER_WAIT)


@pytest.mark.parametrize("name", NEVER_WAIT)
def test_an_action_that_never_waits_on_its_own_checks_its_preconditions_again_when_it_runs(name, settings):
    settings.PARENTAL_CONSENT_MODE = "verified"
    role, target, payload, meanwhile = never_waits()[name]
    maker, action = make_staff(role), approvals.ACTIONS[name]
    _, clean, _ = action.validate(maker, str(target), payload)
    clean = approvals.plain(clean)
    change = ChangeRequest.objects.create(
        action=name, payload=clean, payload_sha256=approvals.digest(clean), maker=maker, reason="Testing",
        status=Status.APPROVED, expires_at=timezone.now() + timedelta(days=1),
    )  # fmt: skip
    assert action.rule(maker, change) is None  # (the job waits as a whole: job.run, below)
    meanwhile()
    done = approvals.execute(change, by=maker)
    assert done.status == Status.FAILED and done.result["error"], done.result
    assert REFUSED[name] in done.result["error"], done.result


def test_a_bulk_action_on_a_child_waits_as_a_job_whose_request_keeps_the_four_rules():
    child, admin, owner = a_minor(), make_staff(roles.ADMIN), make_staff(roles.OWNER)
    params = {"action": "user.suspend", "targets": [child.pk], "reason": "Abuse of the reviews"}
    job = jobs.start(Job.Kind.BULK_ACTION, params, user=admin)
    change = job.change_request
    assert change.status == Status.PENDING and change.payload["minors"] == 1  # one child: an approver, however few
    with pytest.raises(PermissionDenied):
        approvals.approve(change, user=admin, payload_sha256=change.payload_sha256)
    with pytest.raises(ValidationError):
        approvals.approve(change, user=owner, payload_sha256="0" * 64)
    ChangeRequest.objects.filter(pk=change.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
    with pytest.raises(ValidationError):
        approvals.approve(change, user=owner, payload_sha256=change.payload_sha256)
    again = jobs.start(Job.Kind.BULK_ACTION, params, user=admin).change_request
    approvals.approve(again, user=owner, payload_sha256=again.payload_sha256)
    Job.objects.filter(change_request=again).update(cancel_requested=True)  # cancelled meanwhile
    assert approvals.execute(ChangeRequest.objects.get(pk=again.pk), by=owner).status == Status.FAILED
