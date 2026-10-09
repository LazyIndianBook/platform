"""The Catalogue module's staff API (shop/staff_catalogue.py): products by section and their parts by permission (the
page's, the prices' through their approval, the tax's), the courier's data, ISBN once per format, stock by hand,
bundles, pictures, versions, the prior price before saving, the EAN-13 barcode; coupons and offers through their
approvals with the dark-pattern guardrails; shipping rates, categories, collections and product types; the home and
the forms' options; no query per row."""

import io
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from accounts import roles
from shop.factories import ProductFactory
from shop.models import (
    Attribute,
    BundleItem,
    Category,
    Collection,
    Coupon,
    HsnCode,
    Offer,
    Product,
    ProductImage,
    ShippingRate,
    SlugHistory,
    StockAlert,
)
from staff.models import ChangeRequest
from staff.tests.conftest import STAFF, events, make_staff, signed_in

pytestmark = pytest.mark.django_db
URL = STAFF + "catalogue/"


def book(**fields):
    return ProductFactory(**{"weight_grams": 300, "packaging": "flyer", **fields})


def png(size=(400, 600), kind="PNG"):
    buffer = io.BytesIO()
    Image.new("RGB", size, "#0b2a5b").save(buffer, kind)
    return SimpleUploadedFile("cover.png", buffer.getvalue(), content_type="image/png")


@pytest.fixture
def sales():
    return signed_in(make_staff(roles.SALES))


@pytest.fixture
def editor():
    return signed_in(make_staff(roles.CONTENT_EDITOR))


@pytest.fixture
def finance():
    return signed_in(make_staff(roles.FINANCE))


@pytest.fixture
def marketing():
    return signed_in(make_staff(roles.MARKETING))


# ---- Products: the list and its chips ----


def test_the_list_carries_the_chips_and_its_filters_find_them(sales):
    shelf = Category.objects.add_root(instance=Category(name="Class 12", slug="class-12"))
    on_shelf = book(slug="physics", title="Physics 2027")
    on_shelf.categories.add(shelf)
    book(slug="chemistry", stock=2)  # low (SHOP_LOW_STOCK 5)
    ProductFactory(slug="no-weight")  # incomplete for the courier
    book(slug="off-sale", is_active=False, stock=0)
    rows = {row["slug"]: row for row in sales.get(URL + "products/").json()["results"]}
    assert rows["chemistry"]["stock_state"] == "low" and rows["physics"]["stock_state"] == "in_stock"
    assert rows["no-weight"]["courier_problem"].startswith("No weight") and rows["physics"]["courier_problem"] == ""
    assert rows["physics"]["tax_problem"].startswith("Not on the HSN and SAC master")  # no code chosen yet
    found = lambda query: {row["slug"] for row in sales.get(URL + "products/" + query).json()["results"]}  # noqa: E731
    assert found("?incomplete=true") == {"no-weight"}
    assert found("?stock=low") == {"chemistry"} and found("?stock=out") == {"off-sale"}
    assert found("?published=false") == {"off-sale"} and found("?category=class-12") == {"physics"}
    assert found("?q=Physics") == {"physics"} and found("?tax_problem=false") == set()


def test_the_list_reads_its_rows_at_once(sales):
    def queries():
        sales.get(URL + "products/")
        with CaptureQueriesContext(connection) as captured:
            assert sales.get(URL + "products/").status_code == 200
        return len(captured)

    bundle = ProductFactory(kind=Product.Kind.BUNDLE, slug="set")
    BundleItem.objects.create(bundle=bundle, product=book())
    one = queries()
    for _ in range(4):
        other = ProductFactory(kind=Product.Kind.BUNDLE)
        BundleItem.objects.create(bundle=other, product=book())
        book().categories.add(Category.objects.add_root(instance=Category(name="x", slug=f"x-{other.pk}")))
    assert queries() == one


# ---- A product: by section; a new one; a change, its parts by permission ----


def test_a_product_answers_by_section(sales):
    code = HsnCode.objects.get(code="4901")
    product = book(slug="physics", hsn=code, isbn="978-0-306-40615-7")
    product.save()
    StockAlert.objects.create(email="a@example.com", product=product)
    body = sales.get(URL + "products/physics/").json()
    assert body["prices"]["mrp"] == "349.00" and body["prices"]["prior_price"] is None
    assert body["tax"]["today"]["rate"] == "0.00" and body["tax"]["problem"] == ""
    assert body["stock_info"]["alerts"] == 1 and body["stock_info"]["low_stock"] == 5
    assert body["barcode"] is True and body["courier_problem"] == "" and body["packaging"] == "flyer"
    assert "email" not in str(body["stock_info"])  # who asked never leaves


def test_a_new_product_needs_its_weight_and_is_made_at_its_mrp_off_sale(sales, editor):
    asked = {"title": "Biology 2027", "slug": "biology", "kind": "sample-papers", "mrp": "349.00"}
    refused = sales.post(URL + "products/", asked, format="json")
    assert refused.status_code == 400 and "weight" in refused.json()["weight_grams"][0]
    made = sales.post(URL + "products/", {**asked, "weight_grams": 280, "price": "300.00"}, format="json")
    assert made.status_code == 201, made.content
    product = Product.objects.get(slug="biology")
    assert (product.packaging, product.is_active) == ("flyer", False)  # a flyer unless said; off sale until put on
    assert made.json()["price_change"]["status"] == "executed" and product.price.amount == Decimal("300.00")
    below = editor.post(
        URL + "products/", {**asked, "slug": "biology-2", "weight_grams": 1, "price": "1.00"}, format="json"
    )
    assert below.status_code == 403  # selling below the MRP is staff.change_price's
    box = sales.post(
        URL + "products/", {**asked, "slug": "boxed", "weight_grams": 900, "packaging": "box"}, format="json"
    )
    assert box.status_code == 400 and "box" in box.json()["length_cm"][0]
    halves = {**asked, "slug": "half", "weight_grams": 900, "length_cm": 30}
    assert "length, width and height" in sales.post(URL + "products/", halves, format="json").json()["length_cm"][0]
    course = {"title": "Physics course", "slug": "course", "kind": "digital", "mrp": "999.00"}
    assert "SAC" in sales.post(URL + "products/", course, format="json").json()["hsn"][0]  # a course needs its code
    assert sales.post(URL + "products/", {**course, "hsn": "999293"}, format="json").status_code == 201


def test_each_part_of_a_change_needs_its_own_permission(editor, sales, finance):
    product = book(slug="physics")
    page = editor.patch(URL + "products/physics/", {"title": "Physics 2027", "seo_title": "Physics"}, format="json")
    assert page.status_code == 200 and page.json()["title"] == "Physics 2027"
    price = editor.patch(URL + "products/physics/", {"price": "250.00", "reason": "Board offer"}, format="json")
    assert price.status_code == 403 and "staff.change_price" in price.json()["detail"]
    assert events("authz_fail").exists()
    hsn = HsnCode.objects.get(code="4901")
    assert finance.patch(URL + "products/physics/", {"hsn": hsn.code}, format="json").status_code == 200
    assert finance.patch(URL + "products/physics/", {"title": "x"}, format="json").status_code == 403
    assert (
        sales.patch(URL + "products/physics/", {"stock": 99}, format="json").json()["stock"][0].startswith("Stock is")
    )
    product.refresh_from_db()
    assert (product.title, product.hsn_id) == ("Physics 2027", "4901")


def test_a_price_within_the_limit_saves_and_beyond_it_waits_with_the_rest_saved(sales):
    product = book(slug="physics", mrp=Decimal("400.00"), price=Decimal("380.00"))
    within = sales.patch(URL + "products/physics/", {"price": "340.00", "reason": "Board offer"}, format="json")
    assert within.status_code == 200 and within.json()["prices"]["price"] == "340.00"  # 15% off: SALES has 20%
    no_reason = sales.patch(URL + "products/physics/", {"price": "330.00"}, format="json")
    assert no_reason.status_code == 400 and "reason" in no_reason.json()
    beyond = sales.patch(
        URL + "products/physics/", {"price": "200.00", "title": "Physics, cheaper", "reason": "Sale"}, format="json"
    )
    assert beyond.status_code == 202, beyond.content
    change = beyond.json()["price_change"]
    assert change["status"] == "pending" and change["checker"] == "staff.approve_discount"
    product.refresh_from_db()
    assert (product.price.amount, product.title) == (Decimal("340.00"), "Physics, cheaper")  # the rest saved at once
    raised = sales.patch(URL + "products/physics/", {"mrp": "700.00", "reason": "Reprint"}, format="json")
    assert raised.status_code == 202  # a higher MRP shows a deeper saving: 51% off, beyond the limit
    history = sales.get(URL + "products/physics/history/").json()["results"]
    priced = next(v for v in history if any(c["field"] == "price" for c in v["changes"]))
    assert [c for c in priced["changes"] if c["field"] == "price"][0] == {
        "field": "price",
        "before": "380.00",
        "after": "340.00",
    }
    assert priced["by"] is not None and priced["reason"].startswith("Change request #")


def test_an_isbn_is_checked_and_held_once_per_format(sales):
    book(slug="physics", isbn="978-0-306-40615-7")
    ProductFactory(slug="solutions", kind="solutions", weight_grams=200, packaging="flyer")
    twice = sales.patch(URL + "products/solutions/", {"isbn": "9780306406157"}, format="json")
    assert twice.status_code == 200  # another format: its own ISBN may be the same digits? no: other kind is allowed
    clash = book(slug="physics-2")
    answer = sales.patch(URL + f"products/{clash.slug}/", {"isbn": "978-0-306-40615-7"}, format="json")
    assert answer.status_code == 400 and "one ISBN for each format" in answer.json()["isbn"][0]
    bad = sales.patch(URL + f"products/{clash.slug}/", {"isbn": "978-0-306-40615-8"}, format="json")
    assert bad.status_code == 400 and "Not a valid ISBN-13" in bad.json()["isbn"][0]


def test_a_renamed_product_keeps_its_old_address(sales):
    book(slug="physics")
    assert sales.patch(URL + "products/physics/", {"slug": "physics-2027"}, format="json").status_code == 200
    assert SlugHistory.objects.filter(slug="physics", product__slug="physics-2027").exists()
    moved = APIClient().get("/api/v1/products/physics/")
    assert moved.status_code == 301 and moved.json()["redirect_to"] == "physics-2027"
    assert sales.patch(URL + "products/physics-2027/", {"slug": "category"}, format="json").status_code == 400


def test_stock_is_set_by_hand_with_a_reason_and_never_over_a_sale(sales, editor):
    product = book(slug="physics", stock=8)
    asked = {"stock": 40, "reason": "The printer delivered", "expected": 8}
    assert editor.post(URL + "products/physics/stock/", asked, format="json").status_code == 403
    assert sales.post(URL + "products/physics/stock/", asked, format="json").json()["stock_info"]["stock"] == 40
    event = events("catalogue.stock_set").get()
    assert event.changes == {"stock": [8, 40]} and event.reason == "The printer delivered"
    stale = sales.post(URL + "products/physics/stock/", {**asked, "stock": 50, "expected": 8}, format="json")
    assert stale.status_code == 400 and "40 now" in stale.json()["expected"][0]  # a sale meanwhile: read it again
    bundle = ProductFactory(kind=Product.Kind.BUNDLE, slug="set")
    answer = sales.post(URL + "products/set/stock/", {"stock": 3, "reason": "count"}, format="json")
    assert answer.status_code == 400 and bundle.stock == 10  # a bundle's copies are its books'
    product.refresh_from_db()
    assert product.stock == 40


def test_a_bundle_holds_books_and_takes_its_copies_from_them(sales, rzp):
    from shop import services
    from shop.factories import captured, make_order

    physics, chemistry = book(slug="physics", stock=5), book(slug="chemistry", stock=5)
    bundle = ProductFactory(kind=Product.Kind.BUNDLE, slug="set", stock=0)
    lines = {"lines": [{"product": "physics", "quantity": 1}, {"product": "chemistry", "quantity": 2}]}
    assert sales.put(URL + "products/set/bundle/", lines, format="json").json()["bundle_items"][1]["quantity"] == 2
    assert (
        sales.put(
            URL + "products/set/bundle/", {"lines": [{"product": "set", "quantity": 1}]}, format="json"
        ).status_code
        == 400
    )
    order = make_order((bundle, 2))
    services.record_capture(captured(order))  # paid: the bundle's books leave the shelf
    physics.refresh_from_db(), chemistry.refresh_from_db()
    assert (physics.stock, chemistry.stock) == (3, 1)
    assert sales.get(URL + "products/set/").json()["stock_info"]["available"] == 0  # chemistry: 1 copy, 2 a set
    swapped = {"lines": [{"product": "physics", "quantity": 1}]}
    refused = sales.put(URL + "products/set/bundle/", swapped, format="json")
    assert refused.status_code == 400 and "Make a new bundle" in str(refused.json())  # its copies would come back
    services.cancel_order(order, "Not wanted", email=False)
    physics.refresh_from_db(), chemistry.refresh_from_db()
    assert (physics.stock, chemistry.stock) == (5, 5)
    assert sales.put(URL + "products/set/bundle/", swapped, format="json").status_code == 200  # nothing taken now


def test_erpnext_still_hears_of_a_product_changed_here(sales, settings):
    from erp.models import ErpOutbox

    settings.ERP_MODE, settings.ERP_ENABLED, settings.ERP_SYNC_CATALOGUE = "fake", True, True
    physics, chemistry = book(slug="physics"), book(slug="chemistry")
    bundle = ProductFactory(kind=Product.Kind.BUNDLE, slug="set", weight_grams=0)
    rows = ErpOutbox.objects.filter(examleaf_ref=f"item:{physics.pk}", event="item.upserted")
    first = rows.count()
    assert sales.patch(URL + "products/physics/", {"weight_grams": 450}, format="json").status_code == 200
    assert rows.count() == first + 1 and rows.latest("pk").payload["weight_grams"] == 450
    lines = {"lines": [{"product": "physics", "quantity": 1}, {"product": "chemistry", "quantity": 1}]}
    assert sales.put(URL + "products/set/bundle/", lines, format="json").status_code == 200
    sent = ErpOutbox.objects.filter(examleaf_ref=f"bundle:{bundle.pk}", event="bundle.upserted").latest("pk")
    assert [line["qty"] for line in sent.payload["items"]] == [1, 1] and chemistry.pk


def test_pictures_go_up_as_the_admins_do(editor, sales):
    product = book(slug="physics")
    added = editor.post(URL + "products/physics/pictures/", {"image": png(), "alt": "A page"}, format="multipart")
    assert added.status_code == 201 and added.json()["images"][0]["alt"] == "A page"
    picture = ProductImage.objects.get(product=product)
    assert (
        editor.patch(URL + f"products/physics/pictures/{picture.pk}/", {"position": 3}, format="json").status_code
        == 200
    )
    cover = editor.post(URL + "products/physics/pictures/", {"image": png(), "as_cover": "true"}, format="multipart")
    assert cover.status_code == 201 and cover.json()["cover"] is not None
    nonsense = SimpleUploadedFile("x.png", b"not a picture", content_type="image/png")
    assert editor.post(URL + "products/physics/pictures/", {"image": nonsense}, format="multipart").status_code == 400
    huge = editor.post(URL + "products/physics/pictures/", {"image": png((4200, 100))}, format="multipart")
    assert huge.status_code == 400
    assert editor.delete(URL + f"products/physics/pictures/{picture.pk}/").status_code == 204
    finance = signed_in(make_staff(roles.FINANCE))
    assert finance.post(URL + "products/physics/pictures/", {"image": png()}, format="multipart").status_code == 403


def test_the_barcode_is_the_isbns_ean13(sales):
    book(slug="physics", isbn="978-0-306-40615-7")
    drawing = sales.get(URL + "products/physics/barcode.svg/")
    assert drawing.status_code == 200 and drawing["Content-Type"] == "image/svg+xml"
    assert b"EAN-13 barcode 9780306406157" in drawing.content
    book(slug="no-isbn")
    assert sales.get(URL + "products/no-isbn/barcode.svg/").status_code == 404


def test_a_proposed_price_shows_its_prior_price_before_saving(sales):
    book(slug="physics", price=Decimal("300.00"))
    answer = sales.get(URL + "products/physics/prior-price/?price=250").json()
    assert (answer["lowest_in_30_days"], answer["prior_price"]) == ("300.00", "300.00")
    assert sales.get(URL + "products/physics/prior-price/?price=x").status_code == 400
    assert Product.objects.get(slug="physics").price.amount == Decimal("300.00")


# ---- Coupons and offers through their approvals ----


def test_coupons_are_made_and_changed_through_their_approvals(marketing):
    small = marketing.post(URL + "coupons/", {"code": "diwali10", "value": "10", "reason": "Diwali"}, format="json")
    assert small.status_code == 201 and Coupon.objects.filter(code="DIWALI10").exists()
    large = marketing.post(URL + "coupons/", {"code": "HALF", "value": "50", "reason": "Clearance"}, format="json")
    assert large.status_code == 202 and not Coupon.objects.filter(code="HALF").exists()
    deeper = marketing.patch(URL + "coupons/DIWALI10/", {"value": "30", "reason": "More"}, format="json")
    assert deeper.status_code == 202 and Coupon.objects.get(code="DIWALI10").value == 10
    plainer = marketing.patch(
        URL + "coupons/DIWALI10/", {"description": "Ten per cent off for Diwali", "reason": "words"}, format="json"
    )
    assert plainer.status_code == 200 and Coupon.objects.get(code="DIWALI10").description.startswith("Ten")
    guilt = marketing.patch(
        URL + "coupons/DIWALI10/", {"description": "Hurry, last chance!", "reason": "x"}, format="json"
    )
    assert guilt.status_code == 400 and "false urgency" in guilt.json()["description"][0]
    account = marketing.post(
        URL + "coupons/", {"code": "JUSTYOU", "value": "5", "user": 7, "reason": "x"}, format="json"
    )
    assert account.status_code == 400 and account.json()["user"] == ["Not a field of a coupon."]
    assert (
        marketing.patch(URL + "coupons/DIWALI10/", {"code": "OTHER", "reason": "x"}, format="json").status_code == 400
    )
    detail = marketing.get(URL + "coupons/DIWALI10/").json()
    assert detail["state"] == "live" and len(detail["waiting"]) == 1


def test_an_offer_shows_a_countdown_only_to_a_real_end_that_never_moves_later(marketing):
    ends = (timezone.now() + timedelta(days=5)).isoformat()
    asked = {"name": "Board 2027 offer", "value": "10", "show_countdown": True, "reason": "Board season"}
    refused = marketing.post(URL + "offers/", asked, format="json")
    assert refused.status_code == 400 and "real end date" in refused.json()["show_countdown"][0]
    made = marketing.post(URL + "offers/", {**asked, "valid_until": ends}, format="json")
    assert made.status_code == 201, made.content
    offer = Offer.objects.get()
    later = (timezone.now() + timedelta(days=9)).isoformat()
    moved = marketing.patch(URL + f"offers/{offer.pk}/", {"valid_until": later, "reason": "longer"}, format="json")
    assert moved.status_code == 400 and "does not move later" in moved.json()["valid_until"][0]
    off = marketing.patch(
        URL + f"offers/{offer.pk}/", {"show_countdown": False, "reason": "no countdown"}, format="json"
    )
    assert off.status_code == 200
    again = marketing.patch(URL + f"offers/{offer.pk}/", {"valid_until": later, "reason": "longer"}, format="json")
    assert again.status_code == 400  # it showed a countdown while it ran: still a real end
    earlier = (timezone.now() + timedelta(days=2)).isoformat()
    assert (
        marketing.patch(
            URL + f"offers/{offer.pk}/", {"valid_until": earlier, "reason": "end sooner"}, format="json"
        ).status_code
        == 200
    )
    shamed = marketing.post(
        URL + "offers/", {"name": "Only fools miss this", "value": "5", "reason": "x"}, format="json"
    )
    assert shamed.status_code == 400 and "confirm shaming" in shamed.json()["name"][0]
    dated = marketing.post(
        URL + "offers/", {"name": "Limited time", "value": "5", "valid_until": ends, "reason": "x"}, format="json"
    )
    assert dated.status_code == 201  # "limited time" is true of an offer with an end date
    assert (
        marketing.post(
            URL + "offers/", {"name": "Limited time", "value": "5", "reason": "x"}, format="json"
        ).status_code
        == 400
    )
    beyond = marketing.post(URL + "offers/", {"name": "Half off", "value": "50", "reason": "clearance"}, format="json")
    assert beyond.status_code == 202 and beyond.json()["checker"] == "staff.approve_discount"


def test_coupons_and_offers_name_no_account(marketing):
    from shop.staff_catalogue import (
        CatalogueCouponSerializer,
        CatalogueCouponWriteSerializer,
        CatalogueOfferSerializer,
        CatalogueOfferWriteSerializer,
    )

    for serializer in (
        CatalogueCouponSerializer,
        CatalogueCouponWriteSerializer,
        CatalogueOfferSerializer,
        CatalogueOfferWriteSerializer,
    ):
        names = set(serializer().fields)
        assert not names & {"user", "users", "account", "accounts", "customer", "customers", "email", "emails"}
    from django.contrib.auth import get_user_model

    for model in (Coupon, Offer):
        assert not [f for f in model._meta.get_fields() if getattr(f, "related_model", None) is get_user_model()]


# ---- Shipping rates, the tree, collections, types ----


def test_shipping_rates_keep_states_apart_and_their_history(sales):
    made = sales.post(
        URL + "shipping-rates/",
        {"name": "North East", "states": ["AS", "ML"], "fee": "40.00", "free_above": "499.00", "reason": "Launch"},
        format="json",
    )
    assert made.status_code == 201, made.content
    clash = sales.post(URL + "shipping-rates/", {"name": "Assam", "states": ["AS"], "fee": "30"}, format="json")
    assert clash.status_code == 400 and "North East" in clash.json()["states"][0]
    rate = ShippingRate.objects.get()
    assert (
        sales.patch(
            URL + f"shipping-rates/{rate.pk}/", {"fee": "50.00", "reason": "Courier rates"}, format="json"
        ).json()["fee"]
        == "50.00"
    )
    versions = sales.get(URL + f"shipping-rates/{rate.pk}/history/").json()["results"]
    assert versions[0]["changes"] == [{"field": "fee", "before": "40.00", "after": "50.00"}]
    assert versions[0]["reason"] == "Courier rates"


def test_the_category_tree_is_kept_and_moved(editor, marketing):
    for slug in ("books", "class-12"):
        assert editor.post(URL + "categories/", {"name": slug.title(), "slug": slug}, format="json").status_code == 201
    child = editor.post(
        URL + "categories/", {"name": "Physics", "slug": "physics", "parent": "class-12"}, format="json"
    )
    assert child.json()["parent"] == "class-12" and child.json()["depth"] == 2
    tree = editor.post(URL + "categories/class-12/move/", {"target": "books", "position": "last-child"}, format="json")
    assert [(row["slug"], row["parent"]) for row in tree.json()] == [
        ("books", None),
        ("class-12", "books"),
        ("physics", "class-12"),
    ]
    under_itself = editor.post(
        URL + "categories/books/move/", {"target": "physics", "position": "last-child"}, format="json"
    )
    assert under_itself.status_code == 400
    assert marketing.get(URL + "categories/").status_code == 200  # an offer's shelves are chosen from it
    assert marketing.post(URL + "categories/", {"name": "x", "slug": "x"}, format="json").status_code == 403


def test_collections_keep_their_products_order(editor):
    book(slug="physics"), book(slug="chemistry")
    made = editor.post(
        URL + "collections/",
        {"name": "Board 2027", "slug": "board-2027", "products": ["chemistry", "physics"]},
        format="json",
    )
    assert made.status_code == 201 and made.json()["products"] == ["chemistry", "physics"]
    flipped = editor.patch(URL + "collections/board-2027/", {"products": ["physics", "chemistry"]}, format="json")
    assert flipped.json()["products"] == ["physics", "chemistry"]
    assert list(Collection.objects.get().items.values_list("position", flat=True)) == [0, 1]


def test_product_types_and_their_attributes(editor):
    kind = editor.post(URL + "product-types/", {"name": "Printed book"}, format="json").json()
    added = editor.post(
        URL + f"product-types/{kind['id']}/attributes/",
        {"name": "Edition year", "code": "year", "kind": "number"},
        format="json",
    )
    assert added.status_code == 201
    product = book(slug="physics")
    attribute = Attribute.objects.get()
    assert (
        editor.patch(
            URL + "products/physics/", {"product_type": kind["id"], "attributes": {"year": "2027"}}, format="json"
        ).json()["attributes"][0]["value"]
        == "2027"
    )
    assert editor.patch(URL + "products/physics/", {"attributes": {"year": "soon"}}, format="json").status_code == 400
    code = editor.patch(
        URL + f"product-types/{kind['id']}/attributes/{attribute.pk}/", {"code": "edition"}, format="json"
    )
    assert code.status_code == 400 and "its code stays" in code.json()["code"][0]
    assert product.attribute_values.get().value == "2027"


# ---- The home and the options ----


def test_the_home_counts_what_waits(sales, marketing):
    book(slug="physics", stock=0)
    ProductFactory(slug="no-weight")
    summary = sales.get(URL + "summary/").json()
    assert (summary["incomplete"], summary["out_of_stock"], summary["stock_alerts"]) == (1, 1, 0)
    assert summary["prior_price_from"] == "2027-01-01"
    assert marketing.get(URL + "summary/").json()["stock_alerts"] is None  # not theirs to see
    options = sales.get(URL + "options/").json()
    assert {"flyer", "box"} == {row["value"] for row in options["packaging"]} and options["hsn_codes"]
    assert marketing.get(URL + "options/").json()["hsn_codes"] is None


def test_a_waiting_price_is_named_on_its_product(sales):
    book(slug="physics", mrp=Decimal("400.00"), price=Decimal("380.00"))
    sales.patch(URL + "products/physics/", {"price": "100.00", "reason": "Clearance"}, format="json")
    waiting = sales.get(URL + "products/physics/").json()["waiting"]
    assert waiting[0]["action"] == "product.price" and waiting[0]["status"] == "pending"
    assert ChangeRequest.objects.filter(action="product.price", status="pending").count() == 1
