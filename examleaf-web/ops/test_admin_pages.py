"""Every page of the admin opens for a superuser, whatever data is behind it: each registered model's list, add form
and, once it has a row, change form, history and delete page. A 403 is only where the model is deliberately read-only
(orders, invoices, consent records ...); anything else that is not a 200 fails."""

import pytest
from allauth.account.models import EmailAddress
from django.contrib import admin
from django.test import RequestFactory
from django.urls import reverse
from django_celery_beat.models import PeriodicTask
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.factories import UserFactory
from accounts.models import ConsentRecord, DeletionRequest, TeacherProfile
from content.tests import make_paper
from practice.models import Attempt
from shop.factories import CouponFactory, ProductFactory, ShippingRateFactory, make_order
from shop.models import (
    Address,
    BundleItem,
    CreditNote,
    Invoice,
    ProductImage,
    Refund,
    Shipment,
    WebhookEvent,
)

pytestmark = [pytest.mark.django_db, pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning")]


def one_of_everything(user):
    """A row for each model that can have one, so that every change form has something to show."""
    paper = make_paper()
    Attempt.objects.create(user=user, paper=paper, marks_obtained=50)
    EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
    TeacherProfile.objects.create(user=user, school_name="School", district="Kamrup", subject="Physics")
    ConsentRecord.objects.create(user=user, notice_version="1")
    DeletionRequest.objects.create(user=UserFactory())
    RefreshToken.for_user(user)
    book, other = ProductFactory(subject=paper.book.subject, book=paper.book), ProductFactory()
    bundle = ProductFactory(kind="bundle")
    BundleItem.objects.create(bundle=bundle, product=book)
    ProductImage.objects.create(product=book, image="products/inside.jpg", alt="A page")
    ShippingRateFactory()
    coupon = CouponFactory()
    order = make_order((book, 2), (other, 1), user=user, coupon=coupon)
    payment = order.payments.get()
    refund = Refund.objects.create(order=order, payment=payment, amount=100, reason="Test")
    CreditNote.for_refund(refund, Invoice.for_order(order))
    Shipment.objects.create(order=order, courier="India Post", tracking_number="EA1")
    WebhookEvent.objects.create(event_id="evt_1", digest="0" * 64, name="payment.captured")
    Address.objects.create(user=user, name="A", phone="+919864012345", line1="x", city="G", district="K", pin="781001")


def test_every_admin_page_opens_for_a_superuser(client):
    superuser = UserFactory(is_staff=True, is_superuser=True)
    one_of_everything(superuser)
    client.force_login(superuser)
    request = RequestFactory().get("/")
    request.user = superuser
    problems, opened, with_rows = [], 0, 0
    for model, model_admin in admin.site._registry.items():
        base = f"admin:{model._meta.app_label}_{model._meta.model_name}"
        pages = [(reverse(f"{base}_changelist"), 200), (reverse(f"{base}_changelist") + "?q=a&o=1", 200)]
        pages.append((reverse(f"{base}_add"), 200 if model_admin.has_add_permission(request) else 403))
        if row := model._default_manager.order_by("pk").first():
            with_rows += 1
            delete = 200 if model_admin.has_delete_permission(request, row) else 403
            pages += [(reverse(f"{base}_change", args=[row.pk]), 200), (reverse(f"{base}_history", args=[row.pk]), 200)]
            pages.append((reverse(f"{base}_delete", args=[row.pk]), delete))
        for url, expected in pages:
            opened += 1
            if (status := client.get(url).status_code) != expected:
                problems.append((url, status, expected))
    assert not problems, problems
    assert opened > 150 and with_rows > 25, (opened, with_rows)
    assert client.get(reverse("admin:index")).status_code == 200
    assert PeriodicTask.objects.exists() and OutstandingToken.objects.exists()
