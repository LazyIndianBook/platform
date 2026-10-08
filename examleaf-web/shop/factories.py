import hashlib
import hmac
import json
from decimal import Decimal

import factory
from allauth.account.models import EmailAddress
from django.urls import reverse

from accounts.models import User

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


def verified_user(email):
    """The account with this email address (made if there is none), its address confirmed."""
    from accounts.factories import UserFactory

    user = User.objects.filter(email__iexact=email).first() or UserFactory(email=email)
    EmailAddress.objects.get_or_create(user=user, email=user.email, defaults={"verified": True, "primary": True})
    return user


def make_order(*lines, method="razorpay", email="rahul@example.com", user=None, coupon=None, **address):
    """A pending order made through the checkout service; online ones get their Razorpay order id. Cash on delivery
    needs an account with a confirmed email address: one is made for `email` when no `user` is given."""
    from .services import create_order

    cart = make_cart(*lines, coupon=coupon, user=user)
    if method == "cod" and user is None:  # after the cart: one account may have several such orders made
        user = verified_user(email)
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


def post_webhook(client, event, entity, kind="payment", secret=WEBHOOK_SECRET, event_id="", **fields):
    """A signed webhook; `fields` go into the body (e.g. created_at), `event_id` into X-Razorpay-Event-Id."""
    body = json.dumps({"event": event, "payload": {kind: {"entity": entity}}, **fields})
    headers = {"HTTP_X_RAZORPAY_SIGNATURE": sign(body, secret), "HTTP_X_RAZORPAY_EVENT_ID": event_id}
    return client.post(reverse("shop:razorpay_webhook"), body, content_type="application/json", **headers)
