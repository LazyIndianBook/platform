"""Scopes (research 1.9): `scoped(queryset, user, perm)` and `user.has_perm(perm, obj)` reach the same objects, for
each kind: subject, board and class, order status (a person's rows, or a role's: PACKER), school, work queue, and a
warehouse (no model carries one yet)."""

from datetime import timedelta

import pytest
from django.utils import timezone

from accounts import roles
from accounts.factories import UserFactory
from content.models import Paper, Subject
from content.tests import make_paper
from shop.factories import ProductFactory, make_order
from shop.models import Order, QuoteRequest
from staff import backends
from staff.backends import scoped
from staff.models import InboxItem, StaffScope

from .conftest import make_staff

pytestmark = pytest.mark.django_db


def scope(user, kind, value, **fields):
    return StaffScope.objects.create(user=user, kind=kind, value=value, **fields)


def two_papers():
    physics = make_paper()  # PHY-E01 (ASSEB, class 12)
    board, level = physics.book.subject.board, physics.book.subject.class_level
    subject = Subject.objects.create(name="Chemistry", code="CHE", board=board, class_level=level)
    book = physics.book.__class__.objects.create(title="Chemistry", subject=subject, slug="chemistry-2027")
    chemistry = Paper.objects.create(book=book, code="CHE-E01", tier="E", number=1, title="Chemistry E01",
                                     full_marks=70, pass_marks=21, time_text="3 hours")  # fmt: skip
    return physics, chemistry


def test_subject_scope_narrows_an_editor_to_physics():
    physics, chemistry = two_papers()
    editor = make_staff(roles.CONTENT_EDITOR)
    assert set(scoped(Paper.objects.all(), editor, "content.change_paper")) == {physics, chemistry}  # unscoped
    scope(editor, StaffScope.Kind.SUBJECT, "PHY")
    editor = type(editor).objects.get(pk=editor.pk)
    assert list(scoped(Paper.objects.all(), editor, "content.change_paper")) == [physics]
    assert editor.has_perm("content.change_paper", physics) and not editor.has_perm("content.change_paper", chemistry)
    assert editor.has_perm("content.change_paper")  # the model permission itself stays
    assert list(scoped(Subject.objects.all(), editor, "content.view_subject")) == [physics.book.subject]
    assert not scoped(Paper.objects.all(), editor, "content.delete_paper").exists()  # no permission: nothing


def test_an_expired_scope_no_longer_narrows():
    physics, chemistry = two_papers()
    editor = make_staff(roles.CONTENT_EDITOR)
    scope(editor, StaffScope.Kind.SUBJECT, "PHY", expires_at=timezone.now() - timedelta(minutes=1))
    assert scoped(Paper.objects.all(), editor, "content.view_paper").count() == 2


def test_board_and_class_scope():
    physics, chemistry = two_papers()
    reviewer = make_staff(roles.REVIEWER)
    scope(reviewer, StaffScope.Kind.BOARD_CLASS, "CBSE:12")
    assert not scoped(Paper.objects.all(), reviewer, "content.view_paper").exists()
    reviewer = type(reviewer).objects.get(pk=reviewer.pk)
    scope(reviewer, StaffScope.Kind.BOARD_CLASS, f"{physics.book.subject.board.short_name}:12")
    assert scoped(Paper.objects.all(), reviewer, "content.view_paper").count() == 2
    assert reviewer.has_perm("content.view_paper", chemistry)


def test_a_packer_sees_the_orders_to_pack_and_on_their_way_only():
    pending, paid = make_order((ProductFactory(), 1)), make_order((ProductFactory(), 1))
    Order.objects.filter(pk=paid.pk).update(status=Order.Status.PAID)
    packer = make_staff(roles.PACKER)
    assert list(scoped(Order.objects.all(), packer, "shop.view_order")) == [paid]  # ROLE_SCOPES
    assert not packer.has_perm("shop.view_order", pending) and packer.has_perm("shop.view_order", paid)
    both = make_staff(roles.PACKER, roles.SALES)  # SALES gives the same permission without a scope: every order
    assert scoped(Order.objects.all(), both, "shop.view_order").count() == 2
    rows = make_staff(roles.SALES)
    scope(rows, StaffScope.Kind.ORDER_STATUS, "pending")  # a person's own rows narrow even SALES
    assert list(scoped(Order.objects.all(), rows, "shop.view_order")) == [pending]
    items = scoped(paid.items.model.objects.all(), packer, "shop.view_orderitem")
    assert {item.order_id for item in items} == {paid.pk}  # the orders' lines follow the orders


def test_school_scope_reaches_that_schools_quotations_in_any_case():
    def quote(school):
        return QuoteRequest.objects.create(school=school, contact_name="A", email="a@example.com", phone="9864012345",
                                           delivery_pin="781001", items={})  # fmt: skip

    cotton, other = quote("Cotton Collegiate HS School"), quote("Don Bosco School")
    rep = make_staff(roles.SALES_REP)
    scope(rep, StaffScope.Kind.SCHOOL, "cotton collegiate hs school")
    assert list(scoped(QuoteRequest.objects.all(), rep, "shop.view_quoterequest")) == [cotton]
    assert not rep.has_perm("shop.change_quoterequest", other)


def test_a_work_queue_scope_narrows_the_inbox():
    support = make_staff(roles.SUPPORT)
    for kind in ["data_request", "teacher_request"]:
        InboxItem.objects.create(kind=kind, title=kind, permission="staff.view_inbox", target_type="t", target_id=kind)
    scope(support, StaffScope.Kind.TICKET_QUEUE, "data_request")
    items = scoped(InboxItem.objects.all(), support, "staff.view_inbox")
    assert [item.kind for item in items] == ["data_request"]


def test_a_warehouse_scope_is_kept_and_narrows_what_names_one(monkeypatch):
    """No platform model carries a warehouse yet (stock is ERPNext's): the scope is stored and in the manifest, and
    narrows any model the stock views map to it."""
    packer = make_staff(roles.PACKER)
    scope(packer, StaffScope.Kind.WAREHOUSE, "GHY")
    assert backends.staff_scopes(packer) == {"warehouse": {"GHY"}}  # what the manifest lists
    first, second = ProductFactory(), ProductFactory()
    products = type(first).objects.all()
    assert scoped(products, packer, "shop.view_product").count() == 2  # no model names a warehouse: not narrowed
    monkeypatch.setitem(backends.MODEL_SCOPES, "shop.product", {StaffScope.Kind.WAREHOUSE: "slug"})  # a stock view
    packer = type(packer).objects.get(pk=packer.pk)
    scope(packer, StaffScope.Kind.WAREHOUSE, second.slug)
    assert list(scoped(products, packer, "shop.view_product")) == [second]


def test_break_glass_accounts_are_not_narrowed_nor_is_an_owner_without_scope_rows():
    physics, chemistry = two_papers()
    sealed = UserFactory(is_staff=True, is_superuser=True)
    scope(sealed, StaffScope.Kind.SUBJECT, "PHY")
    assert scoped(Paper.objects.all(), sealed, "content.view_paper").count() == 2
    assert sealed.has_perm("content.view_paper", chemistry)
    owner = make_staff(roles.OWNER)  # the founder's role: no ROLE_SCOPES
    assert scoped(Paper.objects.all(), owner, "content.view_paper").count() == 2
