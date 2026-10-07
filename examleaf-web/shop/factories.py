import hashlib
import hmac
import json
from decimal import Decimal

import factory
from django.urls import reverse

from .cart import set_quantity
from .models import Cart, Coupon, Payment, Product, ShippingRate, paise

KEY, SECRET, WEBHOOK_SECRET = "rzp_test_key", "test-key-secret", "test-webhook-secret"  # tests' Razorpay settings

ADDRESS = {
    "name": "Rahul Das",
    "phone": "+919864012345",
    "line1": "House 4, Zoo Road",
    "line2": "",
    "city": "Guwahati",
    "district": "Kamrup Metro",
    "state": "AS",
    "pin": "781001",
}


class ProductFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Product

    title = factory.Sequence(lambda n: f"Sample Papers {n}")
    slug = factory.Sequence(lambda n: f"sample-papers-{n}")
    kind = Product.Kind.SAMPLE_PAPERS
    mrp = Decimal("349.00")
    price = Decimal("299.00")
    stock = 10


class CouponFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Coupon

    code = factory.Sequence(lambda n: f"SAVE{n}")
    value = Decimal("10")


class ShippingRateFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ShippingRate

    name = "Assam"
    states = ["AS"]
    fee = Decimal("40.00")
    free_above = Decimal("499.00")


def make_cart(*lines, coupon=None, user=None):
    """A cart with (product, quantity) lines."""
    cart = Cart.objects.create(user=user, coupon=coupon)
    for product, quantity in lines:
        set_quantity(cart, product, quantity)
    return cart


def make_order(*lines, method="razorpay", email="rahul@example.com", user=None, coupon=None, **address):
    """A pending order made through the checkout service; online ones get their Razorpay order id."""
    from .services import create_order

    cart = make_cart(*lines, coupon=coupon, user=user)
    order = create_order(cart, user=user, email=email, address={**ADDRESS, **address}, method=method)
    if method == "razorpay":
        Payment.objects.filter(order=order).update(razorpay_order_id=f"order_{order.pk}")
    return order


def sign(message, secret):
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


def captured(order, **changes):
    """Razorpay's payment entity for the order's (whole) payment."""
    payment = order.payments.get()
    entity = {
        "id": f"pay_{order.pk}",
        "order_id": payment.razorpay_order_id,
        "amount": paise(payment.amount),
        "currency": "INR",
        "status": "captured",
    }
    return {**entity, **changes}


def post_webhook(client, event, entity, kind="payment", secret=WEBHOOK_SECRET):
    body = json.dumps({"event": event, "payload": {kind: {"entity": entity}}})
    url = reverse("shop:razorpay_webhook")
    return client.post(url, body, content_type="application/json", HTTP_X_RAZORPAY_SIGNATURE=sign(body, secret))
