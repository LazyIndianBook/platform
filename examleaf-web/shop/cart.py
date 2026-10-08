"""The cart. A guest's cart is a database row whose id is kept in the session; at log-in it joins the account's cart.
`totals` is the one place where money is added up: from today's prices, on the cart page, at checkout and when the
order is made (so a price changed in between is never charged from an old page)."""

from dataclasses import dataclass, field
from decimal import Decimal

from django.contrib.auth.signals import user_logged_in
from django.db import transaction
from django.dispatch import receiver

from .models import Cart, CartItem, Coupon, Product, ShippingRate

SESSION_KEY = "shop_cart"
COUNT_KEY = "shop_cart_count"  # the header's "Cart (n)" without a query on every page


def get_cart(request, create=False):
    if request.user.is_authenticated:
        if create:
            return Cart.objects.get_or_create(user=request.user)[0]
        return Cart.objects.filter(user=request.user).first()
    cart = Cart.objects.filter(pk=request.session.get(SESSION_KEY), user=None).first()
    if cart is None and create:
        cart = Cart.objects.create()
        request.session[SESSION_KEY] = cart.pk
    return cart


def remember_count(request, cart):
    request.session[COUNT_KEY] = sum(cart.items.values_list("quantity", flat=True)) if cart else 0


def set_quantity(cart, product, quantity, add=False):
    """Set (or with add=True, increase) a product's quantity, within 0..CartItem.MAX_QUANTITY; 0 removes it."""
    item = cart.items.filter(product=product).first()
    limit = 1 if product.is_digital else CartItem.MAX_QUANTITY  # a course opens once, for the buyer's account
    quantity = min(max(quantity + (item.quantity if item and add else 0), 0), limit)
    if quantity == 0:
        cart.items.filter(product=product).delete()
    else:  # update_or_create: a double click sends two requests, and both may find no row to change
        CartItem.objects.update_or_create(cart=cart, product=product, defaults={"quantity": quantity})
    cart.save(update_fields=["modified"])  # keeps an active guest cart from the daily clean-up


@dataclass
class Line:
    product: Product
    quantity: int

    @property
    def total(self):
        return self.product.price.amount * self.quantity


@dataclass
class Totals:
    lines: list = field(default_factory=list)
    coupon: Coupon | None = None  # the cart's coupon, when it may be used
    coupon_problem: str | None = None  # why the cart's coupon may not be used
    discount: Decimal = Decimal("0.00")
    shipping: Decimal | None = None  # None until the delivery state is known

    @property
    def subtotal(self):
        return sum((line.total for line in self.lines), Decimal("0.00"))

    @property
    def total(self):
        return self.subtotal - self.discount + (self.shipping or 0)

    @property
    def count(self):
        return sum(line.quantity for line in self.lines)

    def problems(self):
        """What stops this cart from being ordered: books taken off sale or short of stock."""
        found = []
        for line in self.lines:
            if not line.product.is_active:
                found.append(f"{line.product} is no longer on sale. Please remove it.")
            elif line.product.available < line.quantity:
                left = line.product.available
                found.append(
                    f"Only {left} cop{'y' if left == 1 else 'ies'} of {line.product} left."
                    if left
                    else f"{line.product} is out of stock. Please remove it."
                )
        return found


def totals(cart, state=None, user=None, email=""):
    """The cart's lines and money at today's prices; shipping once `state` (two-letter code) is known."""
    result = Totals()
    if cart is None:
        return result
    result.lines = [Line(item.product, item.quantity) for item in cart.items.select_related("product")]
    if cart.coupon:
        result.coupon_problem = cart.coupon.problem(result.subtotal, user=user, email=email)
        if not result.coupon_problem:
            result.coupon, result.discount = cart.coupon, cart.coupon.discount_on(result.subtotal)
    if state:  # digital products alone ship nothing
        physical = any(not line.product.is_digital for line in result.lines)
        result.shipping = ShippingRate.fee_for(state, result.subtotal - result.discount) if physical else Decimal("0.00")
    return result


@receiver(user_logged_in)
def merge_guest_cart(sender, request, user, **kwargs):
    """The cart filled before logging in joins the account's cart (quantities add up, the coupon carries over)."""
    if request is None or not hasattr(request, "session"):
        return
    guest = Cart.objects.filter(pk=request.session.pop(SESSION_KEY, None), user=None).first()
    with transaction.atomic():
        cart = Cart.objects.filter(user=user).first()
        if guest is not None:
            cart = cart or Cart.objects.create(user=user)
            for item in guest.items.select_related("product"):
                set_quantity(cart, item.product, item.quantity, add=True)
            if guest.coupon and not cart.coupon:
                cart.coupon = guest.coupon
                cart.save(update_fields=["coupon"])
            guest.delete()
    remember_count(request, cart)
