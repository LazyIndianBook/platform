"""The storefront API's hot paths read the same number of rows' queries whatever the number of rows (no query per
line, per order or per picture): each request counted with one row, then with four (RESILIENCE.md, the database)."""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from shop.factories import ProductFactory, make_cart, make_order, picture, verified_user
from shop.models import Cart, ProductImage

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning"),  # the short development SECRET_KEY
]


def queries(api, path):
    """The queries of a request, after a first one has put in the cache what it keeps (the site's switches)."""
    api.get(path)
    with CaptureQueriesContext(connection) as captured:
        assert api.get(path).status_code == 200
    return len(captured)


def signed_in(user):
    from rest_framework_simplejwt.tokens import RefreshToken

    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return api


def test_a_product_page_reads_its_pictures_at_once():
    product = ProductFactory(slug="physics")
    ProductImage.objects.create(product=product, image=picture("products/a.jpg"), alt="A page")
    one = queries(APIClient(), "/api/v1/products/physics/")
    for name in "bcd":
        ProductImage.objects.create(product=product, image=picture(f"products/{name}.jpg"), alt="A page")
    assert queries(APIClient(), "/api/v1/products/physics/") == one


def test_a_cart_reads_its_lines_at_once():
    user = verified_user("rahul@example.com")
    make_cart((ProductFactory(), 1), user=user)
    one = queries(signed_in(user), "/api/v1/cart/")
    cart = Cart.objects.get(user=user)
    for _ in range(3):
        make_cart((ProductFactory(), 2)).items.update(cart=cart)  # three more lines in the same cart
    assert cart.items.count() == 4 and queries(signed_in(user), "/api/v1/cart/") == one


def test_orders_and_an_order_read_their_lines_at_once():
    user = verified_user("rahul@example.com")

    def order(lines):
        Cart.objects.filter(user=user).delete()  # one cart per account: each order is made from a new one
        return make_order(*[(ProductFactory(), 1) for _ in range(lines)], user=user)

    first = order(1)
    list_one, detail_one = (
        queries(signed_in(user), "/api/v1/orders/"),
        queries(signed_in(user), f"/api/v1/orders/{first.number}/"),
    )
    link_one = queries(APIClient(), f"/api/v1/orders/t/{first.token}/")
    many = order(4)
    order(1), order(1)
    assert queries(signed_in(user), "/api/v1/orders/") == list_one
    assert queries(signed_in(user), f"/api/v1/orders/{many.number}/") == detail_one
    assert queries(APIClient(), f"/api/v1/orders/t/{many.token}/") == link_one
