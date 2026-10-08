"""Smaller findings of SECURITY_REVIEW_PHASE5_6.md in the shop: attribute filters (L2), the PIN lookup's caching (L9),
staff orders for a student waiting for a parent (L11), category imports (I4), email subjects from forms (I2)."""

from datetime import date

import pytest
import tablib
from django.core import mail
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from accounts.factories import UserFactory
from shop import services
from shop.admin import CategoryResource
from shop.cart import Line
from shop.factories import ADDRESS, ProductFactory
from shop.models import Attribute, AttributeValue, Category, ProductType

pytestmark = pytest.mark.django_db


def test_number_filters_refuse_huge_exponents_and_a_request_takes_five_filters_at_most():
    kind = ProductType.objects.create(name="Printed book")
    year = Attribute.objects.create(product_type=kind, name="Year", code="year", kind=Attribute.Kind.NUMBER)
    AttributeValue.objects.create(product=ProductFactory(product_type=kind), attribute=year, value="2027")
    for huge in ["1e999999999", "1e999999", "1e99999999999999999999"]:
        with pytest.raises(ValidationError):
            year.normalise(huge)
    api = APIClient()
    assert api.get("/api/v1/products/?attr_year=1e999999999").json()["results"] == []  # was a 500
    assert len(api.get("/api/v1/products/?attr_year=2027.0").json()["results"]) == 1
    many = "&".join(f"attr_x{n}=1" for n in range(6))
    assert api.get(f"/api/v1/products/?{many}").status_code == 400


def test_staff_cannot_sell_to_a_student_whose_parent_has_not_confirmed(settings):
    settings.PARENTAL_CONSENT_MODE = "verified"
    staff = UserFactory(is_staff=True, is_superuser=True)
    student = UserFactory(date_of_birth=date(date.today().year - 15, 1, 1))
    assert student.consent_pending
    with pytest.raises(services.ShopError, match="parent has not confirmed"):
        services.create_staff_order(
            [Line(ProductFactory(), 1)], by=staff, email=student.email, address=ADDRESS, user=student
        )


def test_a_category_import_checks_each_slug():
    bad = tablib.Dataset(headers=["slug", "name", "description", "parent"])
    bad.append(("class 12/x", "Class 12", "", ""))
    assert CategoryResource().import_data(bad, dry_run=False).has_validation_errors()
    assert not Category.objects.exists()


def test_a_line_break_typed_into_a_form_does_not_lose_the_staff_email(client, commit):
    UserFactory(is_staff=True, is_superuser=True, email="sales@example.com")
    with commit():
        services.email_staff("Quotation asked for: School\nBcc: someone@example.com", "shop/email/low_stock.txt", {})
    [message] = mail.outbox
    assert message.subject == "[ExamLeaf] Quotation asked for: School Bcc: someone@example.com"
    assert message.to == ["sales@example.com"] and not message.bcc


def test_the_public_buckets_storage_keeps_its_key_out_of_the_picture_tasks(settings):
    """L12: django-pictures queues storage.deconstruct() with each picture; S3Storage's held the secret key."""
    from pictures.utils import reconstruct

    from examleaf.storage import PublicS3Storage

    options = {"bucket_name": "examleaf-public", "access_key": "AKIATEST", "secret_key": "the-secret-key"}
    settings.STORAGES = {
        **settings.STORAGES,
        "public": {"BACKEND": "examleaf.storage.PublicS3Storage", "OPTIONS": options},
    }
    deconstructed = PublicS3Storage(**options).deconstruct()
    assert deconstructed == ("examleaf.storage.PublicS3Storage", (), {}) and "the-secret-key" not in repr(deconstructed)
    rebuilt = reconstruct(*deconstructed)  # as the worker does
    assert (rebuilt.bucket_name, rebuilt.secret_key) == ("examleaf-public", "the-secret-key")
