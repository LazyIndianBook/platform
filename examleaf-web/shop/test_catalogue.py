"""Phase 6 E1: the category tree, collections, product types and attributes (page and API filters), slug history,
related products, and digital products (no shipping, stock or cash on delivery; the `learn` hook on payment)."""

import logging
import sys
import types
from decimal import Decimal

import pytest
from django.core import mail
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from content.tests import make_paper
from shop import services
from shop.factories import ProductFactory, ShippingRateFactory, captured, make_cart, make_order, verified_user
from shop.models import (
    Attribute,
    AttributeValue,
    BundleItem,
    Cart,
    Category,
    Collection,
    CollectionItem,
    Order,
    Product,
    ProductType,
)

pytestmark = pytest.mark.django_db


def tree():
    """Books > Class 12 > Science, and Books > Class 11."""
    books = Category.objects.add_root({"name": "Books", "slug": "books"})
    class12 = Category.objects.add_child(books, {"name": "Class 12", "slug": "class-12"})
    Category.objects.add_child(class12, {"name": "Science", "slug": "science"})
    Category.objects.add_child(Category.objects.get(pk=books.pk), {"name": "Class 11", "slug": "class-11"})
    return {c.slug: c for c in Category.objects.all()}


def book_type():
    kind = ProductType.objects.create(name="Printed book")
    year = Attribute.objects.create(product_type=kind, name="Edition year", code="year", kind=Attribute.Kind.NUMBER)
    language = Attribute.objects.create(
        product_type=kind, name="Language", code="language", kind=Attribute.Kind.CHOICE, choices="English\nAssamese"
    )
    return kind, year, language


def test_a_shelf_shows_its_sub_shelves_products_and_the_catalogue_its_top_shelves(client):
    shelves = tree()
    physics = ProductFactory(title="Physics Sample Papers", slug="physics")
    physics.categories.add(shelves["science"], shelves["class-12"])  # two shelves of one branch: listed once
    ProductFactory(title="Class 11 Papers").categories.add(shelves["class-11"])
    ProductFactory(title="Hidden", is_active=False).categories.add(shelves["science"])
    page = client.get("/shop/category/class-12/").content.decode()
    assert page.count('href="/shop/physics/"') == 1 and "Class 11 Papers" not in page and "Hidden" not in page
    assert '<a href="/shop/category/science/">Science</a>' in page  # its sub-shelf
    assert '<a href="/shop/category/books/">Books</a>' in page and 'aria-current="page">Class 12' in page
    assert client.get("/shop/category/books/").content.decode().count('href="/shop/physics/"') == 1
    assert '<a href="/shop/category/books/">Books</a>' in client.get("/shop/").content.decode()
    assert client.get("/shop/category/nothing/").status_code == 404
    assert 'href="/shop/physics/"' not in client.get("/shop/category/class-12/?kind=solutions").content.decode()
    ProductFactory(title="Physics Solutions", kind=Product.Kind.SOLUTIONS).categories.add(shelves["class-12"])
    page = client.get("/shop/category/class-12/?kind=solutions").content.decode()  # the kind links set ?kind=
    assert '<a href="/shop/category/class-12/">All</a>' in page and "Physics Solutions" in page
    assert '<a href="?kind=solutions" aria-current="page">Solutions</a>' in page and "Physics Sample" not in page


def test_a_collection_lists_its_products_in_the_staffs_order(client):
    essentials = Collection.objects.create(name="Board 2027 essentials", slug="essentials")
    for position, title in ((2, "Chemistry"), (1, "Physics"), (0, "Off sale")):
        product = ProductFactory(title=title, is_active=title != "Off sale")
        CollectionItem.objects.create(collection=essentials, product=product, position=position)
    page = client.get("/shop/collection/essentials/").content.decode()
    assert page.index("Physics") < page.index("Chemistry") and "Off sale" not in page
    assert '<a href="/shop/collection/essentials/">Board 2027 essentials</a>' in client.get("/shop/").content.decode()
    essentials.is_active = False
    essentials.save()
    assert client.get("/shop/collection/essentials/").status_code == 404


def test_the_sitemap_lists_the_shop_its_shelves_and_collections(client):
    tree()
    Collection.objects.create(name="Essentials", slug="essentials")
    Collection.objects.create(name="Hidden", slug="hidden", is_active=False)
    sitemap = client.get("/sitemap.xml").text
    for path in ["/shop/", "/shop/school-orders/", "/shop/category/science/", "/shop/collection/essentials/"]:
        assert f"<loc>http://testserver{path}</loc>" in sitemap, path
    assert "/shop/collection/hidden/" not in sitemap


def test_a_renamed_product_redirects_from_its_old_address_and_slugs_of_shop_pages_are_refused(client):
    product = ProductFactory(slug="physics-2026")
    product.slug = "physics-2027"
    product.save()
    response = client.get("/shop/physics-2026/")
    assert response.status_code == 301 and response["Location"] == "/shop/physics-2027/"
    other = ProductFactory(slug="chemistry")
    other.slug = "physics-2026"  # an old slug taken again: the product's own page wins
    other.save()
    assert client.get("/shop/physics-2026/").status_code == 200
    assert client.get("/shop/chemistry/")["Location"] == "/shop/physics-2026/"
    with pytest.raises(ValidationError, match="page of the shop"):
        ProductFactory.build(slug="category").clean()


def test_attributes_keep_their_kind_and_show_on_the_page_with_related_products(client):
    kind, year, language = book_type()
    assert (year.normalise("2027.0"), year.normalise(" 1.50 ")) == ("2027", "1.5")
    assert language.normalise("assamese") == "Assamese"
    for attribute, value in ((year, "soon"), (year, "NaN"), (language, "Hindi")):
        with pytest.raises(ValidationError):
            attribute.normalise(value)
    yes_no = Attribute(kind=Attribute.Kind.BOOLEAN)
    assert (yes_no.normalise("True"), yes_no.normalise("0")) == ("yes", "no")
    product = ProductFactory(slug="physics", product_type=kind)
    value = AttributeValue(product=product, attribute=year, value="2027.00")
    value.full_clean()
    value.save()
    assert value.value == "2027"
    stranger = Attribute.objects.create(product_type=ProductType.objects.create(name="Other"), name="X", code="x")
    with pytest.raises(ValidationError, match="product's type"):
        AttributeValue(product=product, attribute=stranger, value="1").full_clean()
    product.related.add(ProductFactory(title="Chemistry Sample Papers"))
    page = client.get("/shop/physics/").content.decode()
    assert "<dt>Edition year</dt><dd>2027</dd>" in page
    assert "You may also need" in page and "Chemistry Sample Papers" in page


def test_the_api_lists_categories_and_collections_and_filters_products_by_them_and_by_attributes():
    api, shelves = APIClient(), tree()
    kind, year, language = book_type()
    physics = ProductFactory(slug="physics", product_type=kind)
    chemistry = ProductFactory(slug="chemistry", product_type=kind)
    physics.categories.add(shelves["science"])
    chemistry.categories.add(shelves["class-11"])
    for product, (edition, tongue) in ((physics, ("2027", "Assamese")), (chemistry, ("2026", "Assamese"))):
        AttributeValue.objects.create(product=product, attribute=year, value=edition)
        AttributeValue.objects.create(product=product, attribute=language, value=tongue)
    essentials = Collection.objects.create(name="Essentials", slug="essentials")
    CollectionItem.objects.create(collection=essentials, product=chemistry)
    categories = api.get("/api/v1/categories/").json()["results"]
    assert [(c["slug"], c["depth"], c["parent"]) for c in categories] == [
        ("books", 1, None),
        ("class-12", 2, "books"),
        ("science", 3, "class-12"),
        ("class-11", 2, "books"),
    ]
    assert api.get("/api/v1/collections/essentials/").json()["products"] == ["chemistry"]

    def slugs(query):
        return sorted(p["slug"] for p in api.get(f"/api/v1/products/?{query}").json()["results"])

    assert slugs("category=class-12") == ["physics"] and slugs("category=books") == ["chemistry", "physics"]
    assert slugs("collection=essentials") == ["chemistry"] and slugs("category=none") == []
    assert slugs("attr_year=2027.0") == ["physics"] and slugs("attr_language=assamese") == ["chemistry", "physics"]
    assert slugs("attr_language=Assamese&attr_year=2026") == ["chemistry"]
    assert slugs("attr_year=soon") == [] and slugs("attr_unknown=1") == []
    data = api.get("/api/v1/products/physics/").json()
    assert data["categories"] == ["science"]
    assert {(a["code"], a["value"]) for a in data["attributes"]} == {("year", "2027"), ("language", "Assamese")}
    note = Attribute.objects.create(product_type=kind, name="Note", code="note")  # text: any value reaches the query
    AttributeValue.objects.create(product=physics, attribute=note, value="x' OR '1'='1")
    assert slugs("attr_note=x' OR '1'='1") == ["physics"] and slugs("attr_note=%27 OR 1=1 --") == []
    assert slugs("attr_note=a%00b") == []  # PostgreSQL refuses a NUL byte in a query: this was a 500 there
    with pytest.raises(ValidationError, match="null character"):
        note.normalise("a\x00b")


@pytest.fixture
def course():
    return ProductFactory(
        title="Physics Revision Pass", slug="physics-pass", kind=Product.Kind.DIGITAL, stock=0, hsn_code="999293"
    )


@pytest.fixture
def hooks(monkeypatch):
    """learn.services' hooks for the shop replaced: the orders each one was called with."""
    calls = types.SimpleNamespace(granted=[], revoked=[])
    module = types.SimpleNamespace(grant_for_order=calls.granted.append, revoke_for_order=calls.revoked.append)
    monkeypatch.setitem(sys.modules, "learn.services", module)
    return calls


def test_a_digital_product_has_one_copy_no_shipping_and_no_cash_on_delivery(course, settings):
    settings.SHOP_COD_ENABLED = True
    ShippingRateFactory(free_above=None)
    with pytest.raises(ValidationError, match="printed books"):
        ProductFactory.build(kind=Product.Kind.DIGITAL).clean()  # HSN 4901
    cart = make_cart((course, 3))
    assert cart.items.get().quantity == 1
    assert services.cart_totals(cart, state="AS").shipping == 0
    assert services.cart_totals(make_cart((course, 1), (ProductFactory(), 1)), state="AS").shipping == 40
    user = verified_user("rahul@example.com")
    with pytest.raises(services.ShopError, match="Cash on delivery"):
        make_order((course, 1), method="cod", user=user)
    with pytest.raises(services.ShopError, match="log in"):
        make_order((course, 1))  # a guest: the course needs an account


def test_a_course_page_says_it_opens_in_the_app_and_claims_no_book_or_shipping(course, client):
    page = client.get("/shop/physics-pass/").content.decode()
    assert "In the ExamLeaf app" in page and "Only 1 left" not in page
    assert '"Book"' not in page and "shippingDetails" not in page and '"@type": "Product"' in page


def test_a_course_alone_is_never_spoken_of_as_books_copies_shipping_or_delivery(course, rzp, commit, client):
    page = client.get("/shop/physics-pass/").text
    assert '<input type="hidden" name="quantity" value="1">' in page and '<label for="quantity">Copies' not in page
    assert "About the course" in page and "delivered across India" not in page
    client.post(f"/cart/add/{course.pk}/")
    cart = client.get("/cart/").text
    assert "The revision course is in your cart" in cart and "Total before shipping" not in cart
    assert "The course opens in your ExamLeaf account" in cart and "No account needed" not in cart  # a guest
    user = verified_user("rahul@example.com")
    client.force_login(user)
    client.post(f"/cart/add/{course.pk}/")
    checkout = client.get("/checkout/").text
    assert "Access is granted as soon as the payment is confirmed" in checkout and "free on books worth" not in checkout
    assert "<dt>Course</dt>" in checkout and "Total before shipping" not in checkout
    Cart.objects.filter(user=user).delete()
    order = make_order((course, 1), user=user)
    with commit():
        services.record_capture(captured(order))
    page = client.get(order.get_absolute_url()).text
    assert "<dt>Course</dt>" in page and "<dt>Shipping</dt>" not in page and "Delivery to" not in page


def test_paying_for_a_course_opens_it_and_delivers_an_order_of_digital_products_only(course, hooks, rzp, commit):
    granted = hooks.granted
    user, book = verified_user("rahul@example.com"), ProductFactory(stock=5)
    order = make_order((course, 1), user=user)
    with commit():
        services.record_capture(captured(order))
    order.refresh_from_db()
    assert granted == [order] and order.status == Order.Status.DELIVERED and order.placed_at
    assert [label for label, _ in order.timeline()] == ["ordered", "paid", "delivered"]
    Cart.objects.filter(user=user).delete()  # make_order's cart of the first order
    mixed = make_order((course, 1), (book, 2), user=user)
    with commit():
        services.record_capture(captured(mixed))
    mixed.refresh_from_db()
    assert granted[-1] == mixed and mixed.status == Order.Status.PAID  # the books still go by post
    book.refresh_from_db()
    assert book.stock == 3


def test_the_order_and_its_delivered_email_lead_to_the_papers_and_the_course(course, rzp, commit, client, settings):
    book = ProductFactory(title="Physics Sample Papers", stock=5, book=make_paper().book)
    user = verified_user("rahul@example.com")
    order = make_order((course, 1), (book, 1), user=user)
    with commit():
        services.record_capture(captured(order))
    client.force_login(user)
    page = client.get(order.get_absolute_url()).text
    qr = "Scan the QR code on each paper for its solutions."
    assert f'<a href="/books/physics-2027/">Physics Sample Papers</a>. {qr}' in page
    assert '<a href="/revision/">Physics Revision Pass</a>: the revision course, in the ExamLeaf app.' in page
    order = services.pack_order(Order.objects.get(pk=order.pk))
    services.ship_order(order, "India Post", "EA1IN")
    with commit():
        services.deliver_order(order)
    body, site = mail.outbox[-1].body, settings.SITE_URL
    assert f"Physics Sample Papers: {site}/books/physics-2027/\n{qr}" in body
    assert f"Physics Revision Pass: the revision course, in the ExamLeaf app: {site}/revision/" in body


def test_a_refunded_or_cancelled_course_order_closes_the_course_and_a_bundle_sells_book_and_course(
    course, hooks, rzp, commit, settings
):
    settings.SHOP_COD_ENABLED = True
    user = verified_user("rahul@example.com")
    order = make_order((course, 1), user=user)
    with commit():
        services.record_capture(captured(order))
    with commit():
        services.refund_order(Order.objects.get(pk=order.pk), "Changed my mind.")
    assert Order.objects.get(pk=order.pk).status == Order.Status.REFUNDED and hooks.revoked == [order]
    book = ProductFactory(stock=5)
    bundle = ProductFactory(slug="physics-with-course", kind=Product.Kind.BUNDLE, stock=0)
    BundleItem.objects.create(bundle=bundle, product=book)
    BundleItem.objects.create(bundle=bundle, product=course)
    assert bundle.available == 5 and bundle.has_digital and not book.has_digital
    Cart.objects.filter(user=user).delete()
    with pytest.raises(services.ShopError, match="Cash on delivery"):
        make_order((bundle, 1), method="cod", user=user)
    Cart.objects.filter(user=user).delete()
    paid = make_order((bundle, 3), user=user)
    assert paid.items.get().quantity == 1  # one course per order
    with commit():
        services.record_capture(captured(paid))
    book.refresh_from_db()
    assert hooks.granted[-1] == paid and book.stock == 4 and Order.objects.get(pk=paid.pk).status == "paid"
    with commit():
        services.cancel_order(paid, "Cancelled by the customer.")
    book.refresh_from_db()
    assert hooks.revoked[-1] == paid and book.stock == 5


def test_a_bundle_of_digital_products_only_is_a_course_too(course, hooks, rzp, commit):
    """A pass for two subjects sold as a bundle of two courses: no copies to count, no shipping, nothing to pack."""
    ShippingRateFactory(free_above=None)
    other = ProductFactory(title="Chemistry Revision Pass", slug="chemistry-pass", kind=Product.Kind.DIGITAL, stock=0)
    both = ProductFactory(slug="both-passes", kind=Product.Kind.BUNDLE, stock=0)
    BundleItem.objects.create(bundle=both, product=course)
    BundleItem.objects.create(bundle=both, product=other)
    assert both.digital_only and both.has_digital and both.available == 1 and not ProductFactory().digital_only
    assert services.cart_totals(make_cart((both, 1)), state="AS").shipping == 0
    assert services.cart_totals(make_cart((both, 1), user=verified_user("a@example.com"))).digital_only
    assert not services.cart_totals(
        make_cart((both, 1), (ProductFactory(), 1), user=verified_user("b@example.com"))
    ).digital_only
    assert not services.cart_totals(None).digital_only
    page = APIClient().get("/api/v1/products/both-passes/").json()
    assert page["in_stock"] is True
    order = make_order((both, 1), user=verified_user("rahul@example.com"))
    with commit():
        services.record_capture(captured(order))
    order.refresh_from_db()
    assert order.is_digital and order.status == Order.Status.DELIVERED and hooks.granted == [order]


def test_a_part_refund_leaves_the_course_open(course, hooks, rzp, commit):
    """Only a refund in full closes a course; a goodwill part-refund (or a refused parcel refunded less its shipping)
    marks the order refunded and leaves what it opened."""
    order = make_order((course, 1), user=verified_user("rahul@example.com"))
    with commit():
        services.record_capture(captured(order))
    with commit():
        refund = services.refund_order(Order.objects.get(pk=order.pk), "Goodwill.", amount=Decimal("10"))
    assert refund.amount.amount == 10 and Order.objects.get(pk=order.pk).status == Order.Status.REFUNDED
    assert hooks.revoked == [] and not services.refunded_in_full(order)


def test_without_the_learn_app_a_course_order_is_still_paid_and_logged(course, rzp, monkeypatch, caplog):
    monkeypatch.setitem(sys.modules, "learn.services", None)  # import fails
    order = make_order((course, 1), user=verified_user("rahul@example.com"))
    with caplog.at_level(logging.ERROR):
        services.record_capture(captured(order))
    order.refresh_from_db()
    assert order.status == Order.Status.DELIVERED and "grant_for_order is missing" in caplog.text
