"""Phase 6 E4 and E5: the store's admin (bulk actions, import and export of products and categories for ADMIN only,
the dashboard section, stock alerts) and the roles (CONTENT_EDITOR the catalogue and the course content, SALES offers,
staff orders, offline payments, notes, reviews and quotations, SUPPORT entitlements), and Download my data."""

from io import StringIO

import pytest
import tablib
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.urls import reverse

from accounts import roles
from accounts.factories import UserFactory
from accounts.views import export_user_data
from shop import services
from shop.admin import CategoryResource, ProductResource
from shop.factories import ProductFactory, captured, make_order, verified_user
from shop.models import Category, Product, QuoteRequest, Review, StockAlert

pytestmark = pytest.mark.django_db
PRODUCTS = reverse("admin:shop_product_changelist")


@pytest.fixture(autouse=True)
def bootstrapped():
    call_command("bootstrap_roles", stdout=StringIO())  # as every deploy does after migrate


def staff(role):
    user = UserFactory(is_staff=True)
    user.groups.set([Group.objects.get(name=role)])
    return user


def test_bulk_actions_publish_unpublish_and_set_the_stock_of_books(client):
    client.force_login(staff(roles.CONTENT_EDITOR))
    book, bundle = ProductFactory(stock=3), ProductFactory(kind=Product.Kind.BUNDLE, stock=0)
    chosen = {"_selected_action": [book.pk, bundle.pk]}
    client.post(PRODUCTS, {"action": "unpublish", **chosen})
    assert not Product.objects.filter(is_active=True).exists()
    client.post(PRODUCTS, {"action": "publish", **chosen})
    assert Product.objects.filter(is_active=True).count() == 2
    client.post(PRODUCTS, {"action": "set_stock", "stock": "40", **chosen})
    assert list(Product.objects.order_by("pk").values_list("stock", flat=True)) == [40, 0]  # bundles have none
    page = client.post(PRODUCTS, {"action": "set_stock", "stock": "", **chosen}, follow=True).content.decode()
    assert "Type the number of copies" in page


def test_products_and_categories_go_out_and_come_back_in_a_spreadsheet_for_the_admin_role_only(client):
    science = Category.objects.add_root({"name": "Science", "slug": "science"})
    product = ProductFactory(slug="physics", title="Physics", stock=7)
    product.categories.add(science)
    exported = ProductResource().export(Product.objects.all())
    row = dict(zip(exported.headers, exported[0], strict=True))
    assert (row["mrp"], row["price"], row["categories"], row["stock"]) == ("349.00", "299.00", "science", "7")
    changed = tablib.Dataset(headers=exported.headers)
    changed.append([{"title": "Physics 2027", "price": "279", "stock": "999"}.get(h, v) for h, v in row.items()])
    result = ProductResource().import_data(changed, dry_run=False)
    product.refresh_from_db()
    assert not result.has_errors() and (product.title, product.price.amount, product.stock) == ("Physics 2027", 279, 7)
    too_dear = tablib.Dataset(headers=exported.headers)
    too_dear.append([{"price": "400"}.get(h, v) for h, v in row.items()])
    assert ProductResource().import_data(too_dear, dry_run=True).has_validation_errors()  # above the MRP
    tree = tablib.Dataset(headers=["slug", "name", "description", "parent"])
    tree.extend([("class-12", "Class 12", "", "science"), ("chemistry", "Chemistry", "", "class-12")])
    assert not CategoryResource().import_data(tree, dry_run=False).has_errors()
    chemistry = Category.objects.get(slug="chemistry")
    assert [c.slug for c in Category.objects.get_ancestors(chemistry)] == ["science", "class-12"]
    out = CategoryResource().export()
    assert [(r[0], r[3]) for r in out] == [("science", ""), ("class-12", "science"), ("chemistry", "class-12")]
    orphan = tablib.Dataset(headers=["slug", "name", "description", "parent"])
    orphan.append(("lost", "Lost", "", "nowhere"))
    assert CategoryResource().import_data(orphan, dry_run=True).has_errors()
    for role in (roles.SALES, roles.CONTENT_EDITOR):
        client.force_login(staff(role))
        for url in ("admin:shop_product_export", "admin:shop_product_import", "admin:shop_category_import"):
            assert client.get(reverse(url)).status_code == 403
    client.force_login(staff(roles.ADMIN))
    assert client.get(reverse("admin:shop_category_export")).status_code == 200
    assert client.get(reverse("admin:shop_product_import")).status_code == 403  # the panel's import (Phase B)
    client.force_login(UserFactory(is_staff=True, is_superuser=True))
    assert client.get(reverse("admin:shop_product_import")).status_code == 200


def test_prices_tax_coupons_and_offers_change_in_the_panel_and_staff_only_see_them_here(client):
    """Phase B: catalogue. The admin cannot go round the panel's approvals: a price, the tax, a coupon, an offer."""
    product = ProductFactory(title="Physics", stock=3)
    client.force_login(staff(roles.SALES))
    page = client.get(reverse("admin:shop_product_change", args=[product.pk])).content.decode()
    assert 'name="price_0"' not in page and 'name="mrp_0"' not in page and 'name="title"' in page
    assert client.get(reverse("admin:shop_product_add")).status_code == 403
    for name in ("coupon", "offer"):
        assert client.get(reverse(f"admin:shop_{name}_changelist")).status_code == 200
        assert client.get(reverse(f"admin:shop_{name}_add")).status_code == 403
    client.force_login(UserFactory(is_staff=True, is_superuser=True))
    page = client.get(reverse("admin:shop_product_change", args=[product.pk])).content.decode()
    assert 'name="price_0"' in page and client.get(reverse("admin:shop_coupon_add")).status_code == 200


def test_the_dashboard_shows_sales_by_day_best_sellers_low_stock_and_what_waits(client, rzp):
    order = make_order((ProductFactory(title="Physics", stock=3), 2))
    services.record_capture(captured(order))
    QuoteRequest.objects.create(
        school="Cotton School",
        contact_name="A",
        email="a@example.com",
        phone="+919864012345",
        items=[],
        delivery_pin="781001",
    )
    Review.objects.create(product=ProductFactory(), user=UserFactory(), rating=5)
    client.force_login(staff(roles.SALES))
    page = client.get(reverse("admin:index")).content.decode()
    assert "Sales by day" in page and "₹598.00" in page and '<th scope="row">Physics</th><td>2</td>' in page
    assert "Running out" in page and "1 review to read" in page and "1 quotation request" in page


def test_a_role_that_may_only_look_opens_the_product_page(client):
    """SUPPORT may view products, not change them: its page has no form fields (the stock field's hidden initial value
    made it a server error)."""
    product = ProductFactory(title="Physics", stock=3)
    support = staff(roles.SUPPORT)
    assert support.has_perm("shop.view_product") and not support.has_perm("shop.change_product")
    client.force_login(support)
    page = client.get(reverse("admin:shop_product_change", args=[product.pk]))
    assert page.status_code == 200 and "Physics" in page.content.decode()


def test_roles_give_the_catalogue_and_course_to_editors_and_the_orders_to_sales(client):
    editor, sales, support = staff(roles.CONTENT_EDITOR), staff(roles.SALES), staff(roles.SUPPORT)
    assert editor.has_perms(["shop.change_product", "shop.add_category", "shop.delete_attribute", "learn.add_clip"])
    assert editor.has_perms(["learn.change_chapter", "learn.delete_quizitem", "shop.change_collection"])
    assert not editor.has_perm("shop.view_order") and not editor.has_perm("learn.view_entitlement")
    assert sales.has_perms(["shop.add_order", "shop.add_payment", "shop.add_offer", "shop.add_ordernote"])
    assert sales.has_perms(["shop.change_review", "shop.change_quoterequest", "shop.view_stockalert"])
    assert not sales.has_perm("shop.delete_review") and not sales.has_perm("shop.add_category")
    assert support.has_perms(["learn.add_entitlement", "learn.view_bookcode", "shop.view_ordernote"])
    assert not support.has_perm("shop.add_order") and not support.has_perm("shop.export_product")
    for role, url, status in (
        (sales, reverse("admin:shop_stockalert_changelist"), 200),
        (sales, reverse("admin:shop_order_add"), 200),
        (editor, reverse("admin:shop_category_changelist"), 200),
        (support, reverse("admin:shop_order_add"), 403),
    ):
        client.force_login(role)
        assert client.get(url).status_code == status, url


def test_download_my_data_holds_reviews_quotation_requests_stock_alerts_and_the_course():
    user = verified_user("rahul@example.com")
    product = ProductFactory(title="Physics")
    Review.objects.create(product=product, user=user, rating=4, text="Clear answers.")
    QuoteRequest.objects.create(
        school="Cotton School",
        contact_name="Rahul",
        email="Rahul@Example.com",
        phone="+919864012345",
        items=[{"product": "physics", "title": "Physics", "quantity": 40}],
        delivery_pin="781001",
    )
    StockAlert.objects.create(email="rahul@example.com", product=product)
    data = export_user_data(user)
    assert data["reviews"][0]["text"] == "Clear answers." and data["stock_alerts"][0]["product__title"] == "Physics"
    assert data["quote_requests"][0]["phone"] == "+919864012345" and data["quote_requests"][0]["items"][0]["quantity"]
    assert data["learning"]["entitlements"] == []  # the course's own part (learn.services.export_learning)
