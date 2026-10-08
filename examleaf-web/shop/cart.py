"""The cart. A guest's cart is a database row whose id is kept in the session; at log-in it joins the account's cart.
`totals` is the one place where money is added up: from today's prices, on the cart page, at checkout and when the
order is made (so a price changed in between is never charged from an old page). Discounts come in this order: the
coupon, then the automatic offers (models.Offer), then a staff discount; each is shared out over the lines it covers
(`split`), so that every order line keeps its exact share for the invoice and credit notes."""

from dataclasses import dataclass, field
from decimal import Decimal

from django.contrib.auth.signals import user_logged_in
from django.db import transaction
from django.dispatch import receiver

from .models import Cart, CartItem, Coupon, Offer, Product, ShippingRate, rupees

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
    limit = 1 if product.has_digital else CartItem.MAX_QUANTITY  # a course opens once, for the buyer's account
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
    discount: Decimal = Decimal("0.00")  # its share of the discounts

    @property
    def total(self):
        return self.product.price.amount * self.quantity


@dataclass
class Saving:
    """One discount (a line of its own on the cart page, the order and the invoice) and its share of each cart line."""

    label: str
    amount: Decimal
    shares: list
    offer: Offer | None = None


def split(amount, values):
    """`amount` shared out over `values` in proportion, in whole paise, the shares adding up to `amount` exactly. The
    odd paise go to the largest remainders, so no share is above its value while `amount` is not above their sum."""
    total, paise = sum(values), int(amount * 100)
    if not total:
        return [Decimal("0.00")] * len(values)
    exact = [paise * value / total for value in values]
    shares = [int(part) for part in exact]
    for index in sorted(range(len(values)), key=lambda i: exact[i] - shares[i], reverse=True)[: paise - sum(shares)]:
        shares[index] += 1
    return [Decimal(share).scaleb(-2) for share in shares]


@dataclass
class Totals:
    lines: list = field(default_factory=list)
    coupon: Coupon | None = None  # the cart's coupon, when it may be used
    coupon_problem: str | None = None  # why the cart's coupon may not be used
    savings: list = field(default_factory=list)  # Saving: the coupon's, the offers', the staff discount
    shipping: Decimal | None = None  # None until the delivery state is known

    @property
    def subtotal(self):
        return sum((line.total for line in self.lines), Decimal("0.00"))

    @property
    def discount(self):
        return sum((saving.amount for saving in self.savings), Decimal("0.00"))

    def take(self, label, amount, indexes, offer=None):
        """A discount of `amount` over the lines at `indexes` (shared out by what is left of them to pay)."""
        if amount <= 0:
            return
        parts = split(amount, [self.lines[i].total - self.lines[i].discount for i in indexes])
        shares = [Decimal("0.00")] * len(self.lines)
        for index, part in zip(indexes, parts, strict=True):
            shares[index] = part
            self.lines[index].discount += part
        self.savings.append(Saving(label, amount, shares, offer))

    @property
    def total(self):
        return self.subtotal - self.discount + (self.shipping or 0)

    @property
    def count(self):
        return sum(line.quantity for line in self.lines)

    @property
    def digital_only(self):
        """Courses only: nothing to ship, so the pages say nothing of copies, shipping or delivery."""
        return bool(self.lines) and all(line.product.digital_only for line in self.lines)

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
    if cart is None:
        return Totals()
    lines = [Line(item.product, item.quantity) for item in cart.items.select_related("product")]
    return price(lines, cart.coupon, state=state, user=user, email=email)


def price(lines, coupon=None, state=None, user=None, email="", staff_discount=0):
    """The money of these lines (Line) at today's prices: the coupon, the offers, a staff discount in rupees (orders
    made in the admin), and the shipping once `state` is known."""
    result, everything = Totals(lines=lines), range(len(lines))
    if coupon:
        result.coupon_problem = coupon.problem(result.subtotal, user=user, email=email)
        if not result.coupon_problem:
            result.coupon = coupon
            result.take(f"Coupon {coupon.code}", coupon.discount_on(result.subtotal), everything)
    apply_offers(result, user, email)
    if staff_discount:
        result.take("Discount", min(rupees(staff_discount), result.subtotal - result.discount), everything)
    if state:  # digital products alone ship nothing
        physical = any(not line.product.digital_only for line in result.lines)
        result.shipping = ShippingRate.fee_for(state, result.subtotal - result.discount) if physical else Decimal(0)
    return result


def apply_offers(result, user=None, email=""):
    """The automatic offers these lines earn (models.Offer), after the coupon: with a coupon, the combinable offers;
    without one, all the combinable offers together or the best offer that applies alone, whichever saves more."""
    if not result.lines:
        return
    offers = [o for o in Offer.objects.live().filter(is_active=True) if o.limit_problem(user, email) is None]
    choices = [[o for o in offers if o.combinable]]
    if result.coupon is None:
        choices += [[o] for o in offers if not o.combinable]
    ids = [line.product.pk for line in result.lines]
    covered = {offer.pk: offer.covered(ids) for offer in offers}
    best = result
    for choice in choices:
        trial = Totals(lines=[Line(x.product, x.quantity, x.discount) for x in result.lines], savings=[*result.savings])
        for offer in choice:
            indexes = [i for i, line in enumerate(trial.lines) if line.product.pk in covered[offer.pk]]
            copies = sum(trial.lines[i].quantity for i in indexes)
            value = sum(trial.lines[i].total - trial.lines[i].discount for i in indexes)
            if indexes and copies >= offer.min_quantity and value >= offer.min_value.amount:
                trial.take(offer.name, offer.discount_on(value), indexes, offer)
        if trial.discount > best.discount:
            best = trial
    result.lines, result.savings = best.lines, best.savings


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
