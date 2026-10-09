"""The shop: the printed books sold online in India, paid through Razorpay or cash on delivery.

Money is in rupees (django-money, INR only); Razorpay counts whole paise (`paise()`). Order and Payment are state
machines (django-fsm-2): a status changes only through its transitions, whose guards say from which states they may
run, and django-simple-history keeps every change (the customer's status timeline). The flows that combine several
records (stock, refunds, emails) are in services.py."""

import re
import secrets
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import NamedTuple
from urllib.parse import quote

from allauth.account.models import EmailAddress
from allauth.account.signals import email_confirmed
from django.conf import settings
from django.contrib.admin.models import LogEntry
from django.contrib.auth.signals import user_logged_in
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.files.storage import storages
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models, transaction
from django.db.models.functions import Lower
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.text import Truncator
from django_fsm import ConcurrentTransitionMixin, FSMField, transition
from djmoney.models.fields import MoneyField
from djmoney.money import Money
from localflavor.in_.in_states import STATE_CHOICES
from localflavor.in_.models import INStateField
from model_utils.models import TimeStampedModel
from phonenumber_field.modelfields import PhoneNumberField
from pictures.models import PictureField
from pictures.validators import MaxSizeValidator
from simple_history.models import HistoricalRecords
from stdnum.in_ import gstin
from treebeard.mp_tree import MP_Node

from accounts.models import DeletionRequest

INR = "INR"
STATES = dict(STATE_CHOICES)


def public_storage():
    """The public bucket (settings.STORAGES["public"]) for product pictures: a callable, so that migrations name this
    function instead of copying the storage's settings."""
    return storages["public"]


validate_pin = RegexValidator(r"^[1-9]\d{5}$", "Enter the 6-digit PIN code.")


def validate_gstin(value):
    """A GSTIN: 15 characters whose state code, PAN and check character agree (python-stdnum)."""
    if not gstin.is_valid(value):
        raise ValidationError("Enter a valid 15-character GSTIN, or leave it empty.")


def rupees(amount):
    """A Decimal rounded to the paisa, halves up (as on a bill)."""
    return Decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def paise(money):
    """Razorpay's amounts: whole paise, as an int."""
    return int(rupees(money.amount if isinstance(money, Money) else money) * 100)


class RazorpayKeys(NamedTuple):
    key_id: str
    key_secret: str
    webhook_secrets: list  # the webhook's secret (and, for 24 hours after a rotation in the panel, the previous one)


def razorpay_keys():
    """Razorpay's keys in force (integrations/README.md "Precedence"): the environment's (RAZORPAY_KEY_ID, _SECRET, the
    webhook secret of the keys' mode) until the panel holds keys of its own (credentials replaced on the connections
    page, after a passing test); then the enabled account's, and none while none is enabled (switched off there)."""
    from integrations.services import panel_keys

    panel = panel_keys("razorpay")
    if panel is None:
        key_id = settings.RAZORPAY_KEY_ID
        secret = (
            settings.RAZORPAY_WEBHOOK_SECRET_TEST
            if key_id.startswith("rzp_test_")
            else settings.RAZORPAY_WEBHOOK_SECRET
        )
        return RazorpayKeys(key_id, settings.RAZORPAY_KEY_SECRET, [secret] if secret else [])
    credentials = panel.get("credentials") or {}
    return RazorpayKeys(
        credentials.get("key_id", ""), credentials.get("key_secret", ""), panel.get("webhook_secrets", [])
    )


def live_mode():
    """Whether the site runs on Razorpay's live keys now (rzp_live_…; no keys counts as live: no test series)."""
    return not razorpay_keys().key_id.startswith("rzp_test_")


def validate_indian_mobile(number):
    if number and (number.country_code != 91 or not re.fullmatch(r"[6-9]\d{9}", str(number.national_number))):
        raise ValidationError("Enter a 10-digit Indian mobile number.")


def money_field(verbose_name, **kwargs):
    return MoneyField(
        verbose_name, max_digits=10, decimal_places=2, default_currency=INR, currency_choices=[(INR, "₹")], **kwargs
    )


class Product(TimeStampedModel):
    class Kind(models.TextChoices):
        SAMPLE_PAPERS = "sample-papers", "Sample Papers"
        SOLUTIONS = "solutions", "Solutions"
        BUNDLE = "bundle", "Bundle"
        DIGITAL = "digital", "Digital (in the app)"  # no shipping, stock or cash on delivery; opens a `learn` course

    # /shop/<slug>/review/ and /stock-alert/ would meet the category and collection pages, /shop/school-orders/ the form
    RESERVED_SLUGS = {"category", "collection", "school-orders"}

    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    subject = models.ForeignKey(
        "content.Subject",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="products",
        help_text="Gives the board and the class.",
    )
    book = models.ForeignKey(
        "content.Book",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
        help_text="The papers it holds: “what's inside” and the sample paper link on the product page.",
    )
    isbn = models.CharField("ISBN", max_length=17, blank=True)
    pages = models.PositiveSmallIntegerField(null=True, blank=True)
    description = models.TextField(blank=True, help_text="Markdown.")
    cover = PictureField(
        upload_to="products/",
        storage=public_storage,
        blank=True,
        aspect_ratios=["2/3"],
        width_field="cover_width",
        height_field="cover_height",
        validators=[MaxSizeValidator(4096, 4096)],
    )
    cover_width = models.PositiveIntegerField(null=True, editable=False)  # read from the file once, not on every page
    cover_height = models.PositiveIntegerField(null=True, editable=False)
    # link previews (og:image): its cover and title, 1200x630, made by tasks.make_og_image whenever either changes
    og_image = models.FileField(upload_to="og/", storage=public_storage, blank=True, editable=False)
    mrp = money_field("MRP")
    price = money_field("selling price")
    gst_rate = models.DecimalField(
        "GST rate (%)",
        max_digits=4,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(28)],
        help_text="Printed books are exempt: 0.",
    )
    hsn_code = models.CharField("HSN code", max_length=8, default="4901")  # 4901: printed books
    weight_grams = models.PositiveIntegerField("weight (g)", default=0)
    stock = models.PositiveIntegerField(default=0, help_text="Copies in hand. A bundle sells its books' copies.")
    is_active = models.BooleanField("on sale", default=True)
    seo_title = models.CharField("page title", max_length=70, blank=True)
    seo_description = models.CharField("meta description", max_length=160, blank=True)
    product_type = models.ForeignKey(
        "ProductType",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="products",
        help_text="Gives the product its attributes (edition year, language…), shown on its page.",
    )
    categories = models.ManyToManyField("Category", blank=True, related_name="products")
    related = models.ManyToManyField("self", blank=True, help_text="Shown on its page (and it on theirs).")

    class Meta:
        ordering = ["subject", "kind", "title"]
        permissions = [("export_product", "Can export products"), ("import_product", "Can import products")]

    def __str__(self):
        return self.title

    def get_absolute_url(self):  # the website's page (examleaf-frontend), as are the URLs below
        return f"/shop/{self.slug}/"

    def clean(self):
        if self.price and self.mrp and self.price > self.mrp:
            raise ValidationError({"price": "The selling price cannot be above the MRP."})
        if self.slug in self.RESERVED_SLUGS:
            raise ValidationError({"slug": "This address belongs to a page of the shop: choose another."})
        if self.is_digital and self.hsn_code == "4901":
            raise ValidationError({"hsn_code": "4901 is for printed books: enter the course's SAC code and GST rate."})

    def save(self, *args, **kwargs):
        """A changed slug leaves its old one in SlugHistory: the old address redirects to the new one (301)."""
        old = Product.objects.filter(pk=self.pk).values_list("slug", flat=True).first() if self.pk else None
        super().save(*args, **kwargs)
        if old and old != self.slug:
            SlugHistory.objects.update_or_create(slug=old, defaults={"product": self})

    @property
    def is_digital(self):
        return self.kind == self.Kind.DIGITAL

    @property
    def has_digital(self):
        """A digital product, or a bundle with one (a book and its course): it opens a course, so it needs an account,
        is paid online and is sold one at a time."""
        if self.kind == self.Kind.BUNDLE:
            return any(item.product.is_digital for item in self.bundle_items.select_related("product"))
        return self.is_digital

    @property
    def digital_only(self):
        """Nothing to ship or to pack: a digital product, or a bundle of digital products only (a pass for every
        subject sold as a bundle of four)."""
        if self.kind == self.Kind.BUNDLE:
            items = [item.product.is_digital for item in self.bundle_items.select_related("product")]
            return bool(items) and all(items)
        return self.is_digital

    def stock_lines(self, quantity):
        """{product id: copies} that selling `quantity` of this product takes from stock (digital ones have none)."""
        if self.kind == self.Kind.BUNDLE:
            items = self.bundle_items.select_related("product")
            return {item.product_id: item.quantity * quantity for item in items if not item.product.is_digital}
        if self.is_digital:
            return {}
        return {self.pk: quantity}

    @property
    def available(self):
        if self.digital_only:  # one per order: it opens the course for the buyer's account
            return 1
        if self.kind == self.Kind.BUNDLE:
            items = [item for item in self.bundle_items.select_related("product") if not item.product.is_digital]
            return min((item.product.stock // item.quantity for item in items), default=0)
        return self.stock

    @property
    def saving(self):  # the .price "Save ₹49 (9%)" line
        return self.mrp - self.price

    @property
    def saving_percent(self):
        return round((self.mrp.amount - self.price.amount) * 100 / self.mrp.amount) if self.mrp.amount else 0


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = PictureField(
        upload_to="products/",
        storage=public_storage,
        width_field="width",
        height_field="height",
        validators=[MaxSizeValidator(4096, 4096)],
    )
    width = models.PositiveIntegerField(null=True, editable=False)
    height = models.PositiveIntegerField(null=True, editable=False)
    alt = models.CharField("description", max_length=200, blank=True)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "pk"]

    def __str__(self):
        return self.alt or self.image.name


class BundleItem(models.Model):
    bundle = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="bundle_items")
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name="+", limit_choices_to=~models.Q(kind=Product.Kind.BUNDLE)
    )
    quantity = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1)])

    class Meta:
        constraints = [models.UniqueConstraint(fields=["bundle", "product"], name="unique_bundle_item")]

    def __str__(self):
        return f"{self.quantity} × {self.product}"


class SlugHistory(models.Model):
    """A product's earlier slug: /shop/<old>/ redirects (301) to its page (views.ProductView), so links and search
    results survive a renamed product. Written by Product.save; a slug taken again by another product moves to it."""

    slug = models.SlugField(unique=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="old_slugs")
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "slug history"

    def __str__(self):
        return self.slug


class Category(MP_Node):
    """A shelf of the shop, in a tree (django-treebeard's materialised path, as django-oscar uses: a branch is one
    query). A product may sit on several shelves; a category's page shows the products of its sub-categories too."""

    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True, help_text="Markdown, at the top of its page.")

    class Meta:
        verbose_name_plural = "categories"
        permissions = [("export_category", "Can export categories"), ("import_category", "Can import categories")]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return f"/shop/category/{self.slug}/"

    def products_on_sale(self):
        return Product.objects.filter(is_active=True, categories__in=Category.objects.get_tree(self)).distinct()


class Collection(TimeStampedModel):
    """A hand-picked list of products ("Board 2027 essentials"), in the order staff give them."""

    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True, help_text="Markdown, at the top of its page.")
    is_active = models.BooleanField("shown", default=True)
    position = models.PositiveSmallIntegerField(default=0, help_text="Collections are listed by this number.")

    class Meta:
        ordering = ["position", "name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return f"/shop/collection/{self.slug}/"

    def products_on_sale(self):
        items = self.items.filter(product__is_active=True).select_related("product")
        return [item.product for item in items]


class CollectionItem(models.Model):
    collection = models.ForeignKey(Collection, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="collection_items")
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "pk"]
        constraints = [models.UniqueConstraint(fields=["collection", "product"], name="unique_collection_product")]

    def __str__(self):
        return f"{self.product} in {self.collection}"


class ProductType(models.Model):
    """A kind of product and the attributes its products have (a printed book: edition year, language, board…)."""

    name = models.CharField(max_length=60, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Attribute(models.Model):
    class Kind(models.TextChoices):
        TEXT = "text", "text"
        NUMBER = "number", "number"
        CHOICE = "choice", "one of a list"
        BOOLEAN = "boolean", "yes or no"

    product_type = models.ForeignKey(ProductType, on_delete=models.CASCADE, related_name="attributes")
    name = models.CharField(max_length=60)
    code = models.SlugField(max_length=40, help_text="The API's filter: ?attr_<code>=… (e.g. language).")
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.TEXT)
    choices = models.TextField(blank=True, help_text="For “one of a list”: one choice per line.")
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "pk"]
        constraints = [models.UniqueConstraint(fields=["product_type", "code"], name="unique_attribute_code")]

    def __str__(self):
        return f"{self.name} ({self.product_type})"

    def normalise(self, value):
        """The value as it is stored and matched by the API's filter ("2027", "yes", a choice as listed); raises
        ValidationError when it is not one of this attribute's kind."""
        value = str(value).strip()
        if self.kind == self.Kind.NUMBER:
            try:
                number = Decimal(value)
            except ArithmeticError:  # InvalidOperation, and an exponent too large to hold
                number = None
            # 1e999999999 would overflow normalize() (a 500), and 1e999999 become a million digits (L2)
            if number is None or not number.is_finite() or abs(number.adjusted()) > 12:
                raise ValidationError("Enter a number.")
            return format(number.normalize(), "f")
        if self.kind == self.Kind.BOOLEAN:
            answer = {"yes": "yes", "true": "yes", "1": "yes", "no": "no", "false": "no", "0": "no"}
            if value.lower() not in answer:
                raise ValidationError("Enter yes or no.")
            return answer[value.lower()]
        if self.kind == self.Kind.CHOICE:
            listed = [line.strip() for line in self.choices.splitlines() if line.strip()]
            if (match := next((c for c in listed if c.lower() == value.lower()), None)) is None:
                raise ValidationError(f"Choose one of: {', '.join(listed)}.")
            return match
        if "\x00" in value:  # the API's ?attr_<code>= filter takes any text; PostgreSQL refuses a NUL byte (a 500)
            raise ValidationError("Remove the null character.")
        return value


class AttributeValue(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="attribute_values")
    attribute = models.ForeignKey(Attribute, on_delete=models.CASCADE, related_name="values")
    value = models.CharField(max_length=200)

    class Meta:
        ordering = ["attribute__position", "attribute__pk"]
        constraints = [models.UniqueConstraint(fields=["product", "attribute"], name="one_value_per_attribute")]

    def __str__(self):
        return f"{self.attribute.name}: {self.value}"

    def clean(self):
        if not self.attribute_id:
            return
        product = getattr(self, "product", None)  # an admin inline's product may not be saved yet
        if product is not None and product.product_type_id != self.attribute.product_type_id:
            raise ValidationError({"attribute": "Not an attribute of this product's type."})
        try:
            self.value = self.attribute.normalise(self.value)
        except ValidationError as error:
            raise ValidationError({"value": error.messages}) from error


class Coupon(TimeStampedModel):
    class Kind(models.TextChoices):
        PERCENT = "percent", "per cent off"
        FIXED = "fixed", "rupees off"

    code = models.CharField(max_length=30, unique=True, help_text="Stored in capitals; customers may type any case.")
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.PERCENT)
    value = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(0)])
    min_order = money_field("minimum order", default=0, help_text="Value of the books, before shipping.")
    valid_from = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField(null=True, blank=True)
    max_uses = models.PositiveIntegerField(null=True, blank=True, help_text="All customers together. Empty: no limit.")
    max_uses_per_customer = models.PositiveIntegerField(
        null=True, blank=True, default=1, help_text="Per account and per email address. Empty: no limit."
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-valid_from"]

    def __str__(self):
        return self.code

    def clean(self):
        if self.kind == self.Kind.PERCENT and self.value is not None and self.value > 100:
            raise ValidationError({"value": "At most 100 per cent."})

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    def discount_on(self, amount):
        """The discount on books worth `amount` rupees, never more than the amount."""
        return money_off(self.kind, self.value, amount)

    def problem(self, amount, user=None, email=""):
        """Why the coupon cannot be used on books worth `amount` (a message for the customer), or None."""
        now = timezone.now()
        if not self.is_active or now < self.valid_from:
            return "This coupon code is not valid."
        if self.valid_until and now > self.valid_until:
            return "This coupon has expired."
        if amount < self.min_order.amount:
            return f"This coupon needs books worth at least {self.min_order}."
        return self.limit_problem(user, email)

    def limit_problem(self, user=None, email=""):
        """Why the coupon's limits stop this customer (used up, or used before by this account or email address), or
        None. Checked when the order is made and again, under a lock on the coupon, when it is placed
        (services.claim_coupon): orders still awaiting payment do not count as uses until then."""
        used = self.orders.counted()
        if self.max_uses is not None and used.count() >= self.max_uses:
            return "This coupon has been used up."
        if self.max_uses_per_customer is not None and (user or email):
            if customers_orders(used, user, email).count() >= self.max_uses_per_customer:
                return "You have already used this coupon."
        return None


def money_off(kind, value, amount):
    """A coupon's or an offer's discount on `amount` rupees: `value` per cent or rupees, never more than the amount."""
    off = amount * value / 100 if kind == Coupon.Kind.PERCENT else value
    return min(rupees(off), amount)


def customers_orders(orders, user=None, email=""):
    """Those of `orders` made by this account or with this email address (per-customer limits)."""
    mine = models.Q(email__iexact=email or user.email) | (models.Q(user=user) if user else models.Q())
    return orders.filter(mine)


class OfferQuerySet(models.QuerySet):
    def live(self):
        now = timezone.now()
        return self.filter(models.Q(valid_until__isnull=True) | models.Q(valid_until__gte=now), valid_from__lte=now)


class Offer(TimeStampedModel):
    """An automatic discount, no code needed (cart.totals applies it after the coupon): per cent or rupees off the
    products it covers, once they reach a number of copies or a value. A combinable offer adds to the coupon and the
    other offers; one that is not applies alone, never with a coupon (the customer gets whichever saves more). Each use
    is an OrderDiscount line of the order; RUNBOOK.md "Offers"."""

    class Scope(models.TextChoices):
        CART = "cart", "the whole cart"
        PRODUCTS = "products", "the products chosen below"
        CATEGORIES = "categories", "the products of the categories below (with their sub-categories)"
        COLLECTIONS = "collections", "the products of the collections below"

    name = models.CharField(max_length=80, help_text="Customers see it on the saving's line: “Board 2027 offer”.")
    kind = models.CharField(max_length=10, choices=Coupon.Kind.choices, default=Coupon.Kind.PERCENT)
    value = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(0)])
    scope = models.CharField("on", max_length=12, choices=Scope.choices, default=Scope.CART)
    products = models.ManyToManyField(Product, blank=True, related_name="offers")
    categories = models.ManyToManyField(Category, blank=True, related_name="offers")
    collections = models.ManyToManyField(Collection, blank=True, related_name="offers")
    min_quantity = models.PositiveSmallIntegerField("minimum copies", default=0, help_text="Of the products covered.")
    min_value = money_field("minimum value", default=0, help_text="Of the products covered, after the coupon.")
    valid_from = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField(null=True, blank=True)
    max_uses = models.PositiveIntegerField(
        null=True, blank=True, help_text="Orders, all customers together. Empty: no limit."
    )
    max_uses_per_customer = models.PositiveIntegerField(
        null=True, blank=True, help_text="Per account and per email address. Empty: no limit."
    )
    combinable = models.BooleanField(
        "with coupons and other offers", default=True, help_text="Off: it applies alone, never with a coupon."
    )
    is_active = models.BooleanField(default=True)

    objects = OfferQuerySet.as_manager()

    class Meta:
        ordering = ["-valid_from"]

    def __str__(self):
        return self.name

    def clean(self):
        if self.kind == Coupon.Kind.PERCENT and self.value is not None and self.value > 100:
            raise ValidationError({"value": "At most 100 per cent."})

    def covered(self, product_ids):
        """Which of these products (ids) the offer covers."""
        if self.scope == self.Scope.CART:
            return set(product_ids)
        products = Product.objects.filter(pk__in=product_ids)
        if self.scope == self.Scope.PRODUCTS:
            products = products.filter(offers=self)
        elif self.scope == self.Scope.COLLECTIONS:
            products = products.filter(collection_items__collection__offers=self)
        else:
            shelves = models.Q(pk__in=[])
            for path in self.categories.values_list("path", flat=True):
                shelves |= models.Q(categories__path__startswith=path)
            products = products.filter(shelves)
        return set(products.values_list("pk", flat=True))

    def limit_problem(self, user=None, email=""):
        """Why the offer's usage limits stop this customer now, or None. Orders count once placed (paid, or cash on
        delivery placed) and not undone. Checked when the order is made and again, under a lock on the offer, when it
        is placed (services.claim_offers, as coupons are: M4)."""
        used = Order.objects.counted().filter(discount_lines__offer=self).distinct()
        if self.max_uses is not None and used.count() >= self.max_uses:
            return "used up"
        if self.max_uses_per_customer is not None and (user or email):
            if customers_orders(used, user, email).count() >= self.max_uses_per_customer:
                return "used by this customer"
        return None

    def discount_on(self, amount):
        return money_off(self.kind, self.value, amount)


class ShippingRate(models.Model):
    """A flat fee for a group of states (or for every state no other rate names), free from an order value up."""

    name = models.CharField(max_length=60)
    states = models.JSONField(default=list, blank=True, help_text="None ticked: every state no other rate names.")
    fee = money_field("fee", default=0)
    free_above = money_field("free from", null=True, blank=True, help_text="Books worth this much or more ship free.")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @classmethod
    def rate_for(cls, state):
        """The active rate of `state`: the one naming it, else the one for every other state; None when neither."""
        rates = list(cls.objects.filter(is_active=True))
        return next((r for r in rates if state in r.states), None) or next((r for r in rates if not r.states), None)

    @classmethod
    def fee_for(cls, state, amount):
        """Shipping (Decimal rupees) to `state` for books worth `amount`; 0 when no rate applies."""
        rate = cls.rate_for(state)
        if rate is None or (rate.free_above is not None and amount >= rate.free_above.amount):
            return Decimal("0.00")
        return rate.fee.amount

    @classmethod
    def summary(cls):
        """For "delivery from ₹40": the lowest fee and the lowest value that ships free of the active rates, as
        strings in rupees (None without rates, or without a free threshold)."""
        rates = list(cls.objects.filter(is_active=True))
        lowest = {
            "fee_from": min((r.fee.amount for r in rates), default=None),
            "free_above": min((r.free_above.amount for r in rates if r.free_above is not None), default=None),
        }
        return {key: None if value is None else f"{value:.2f}" for key, value in lowest.items()}


class PinCode(models.Model):
    """The India Post PIN code directory (data.gov.in, Government Open Data Licence), one row per PIN, loaded by
    `manage.py import_pincodes` (DEPLOYMENT.md): the address form's autofill and the check of the state, which decides
    CGST + SGST or IGST. A few PINs straddle a border: hence lists."""

    pin = models.CharField("PIN code", max_length=6, primary_key=True)
    states = models.JSONField(help_text="Two-letter state codes.")
    districts = models.JSONField()

    class Meta:
        verbose_name = "PIN code"

    def __str__(self):
        return self.pin

    @classmethod
    def state_problem(cls, pin, state):
        """Why `state` cannot be the state of `pin`, or None. PINs missing from the directory (new ones, or none loaded
        yet) are not checked."""
        states = cls.objects.filter(pin=pin).values_list("states", flat=True).first()
        if states and state not in states:
            return f"PIN code {pin} is in {' or '.join(STATES.get(code, code) for code in states)}."
        return None


class Address(TimeStampedModel):
    """A saved delivery address. Deleted with the account (see the receiver at the end); orders keep a copy."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="addresses")
    name = models.CharField("full name", max_length=120)
    phone = PhoneNumberField("mobile number", region="IN", validators=[validate_indian_mobile])
    line1 = models.CharField("house and street", max_length=200)
    line2 = models.CharField("area or landmark", max_length=200, blank=True)
    city = models.CharField("city, town or village", max_length=80)
    district = models.CharField(max_length=80)
    state = INStateField(default="AS")
    pin = models.CharField("PIN code", max_length=6, validators=[validate_pin])
    is_default = models.BooleanField("use by default", default=False)

    FIELDS = ["name", "phone", "line1", "line2", "city", "district", "state", "pin"]

    class Meta:
        ordering = ["-is_default", "-modified"]
        verbose_name_plural = "addresses"

    def __str__(self):
        return f"{self.name}, {self.city} {self.pin}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_default:
            self.user.addresses.exclude(pk=self.pk).update(is_default=False)

    def snapshot(self):
        return {name: str(getattr(self, name)) for name in self.FIELDS}

    @property
    def lines(self):
        return address_lines(self.snapshot())


def address_lines(snapshot):
    """The lines of an address snapshot (Order.shipping_address), for pages, emails and the invoice."""
    s = snapshot
    return [
        s["name"],
        s["line1"],
        *([s["line2"]] if s.get("line2") else []),
        f"{s['city']}, {s['district']} district",
        f"{STATES.get(s['state'], s['state'])} {s['pin']}",
        f"Mobile {s['phone']}",
    ]


class Cart(TimeStampedModel):
    """A user's cart, or a guest's (no user; its id is kept in the session and joins the user's cart at log-in). An API
    client without cookies holds a guest cart by a token instead (X-Cart-Token, shop.cart.issue_token): only its hash
    is kept, until `token_expires`."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="cart"
    )
    coupon = models.ForeignKey(Coupon, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    token = models.CharField(max_length=64, unique=True, null=True, blank=True, editable=False)  # SHA-256, hex
    token_expires = models.DateTimeField(null=True, blank=True, editable=False)

    def __str__(self):
        return f"Cart #{self.pk}"


class CartItem(models.Model):
    MAX_QUANTITY = 20

    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="+")
    quantity = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1)])

    class Meta:
        ordering = ["pk"]
        constraints = [models.UniqueConstraint(fields=["cart", "product"], name="unique_cart_product")]

    def __str__(self):
        return f"{self.quantity} × {self.product}"


def order_token():
    return secrets.token_urlsafe(16)


class OrderQuerySet(models.QuerySet):
    def counted(self):
        """Orders that count as sales (and as coupon uses): paid, or placed with cash on delivery, and not undone."""
        return self.filter(placed_at__isnull=False).exclude(status__in=[Order.Status.CANCELLED, Order.Status.REFUNDED])


class Order(ConcurrentTransitionMixin, TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "awaiting payment"
        PAID = "paid", "paid"
        PACKED = "packed", "packed"
        SHIPPED = "shipped", "shipped"
        DELIVERED = "delivered", "delivered"
        CANCELLED = "cancelled", "cancelled"
        REFUNDED = "refunded", "refunded"

    class Method(models.TextChoices):
        RAZORPAY = "razorpay", "online (UPI, card, net banking)"
        COD = "cod", "cash on delivery"
        OFFLINE = "offline", "bank transfer or UPI to our account"  # recorded by staff: services.record_offline_payment

    number = models.CharField(max_length=20, unique=True, null=True, editable=False)  # noqa: DJ001  null until saved
    # The secret of the link in the order's emails (/orders/t/<token>/): it opens the order without an account.
    token = models.CharField(max_length=32, unique=True, default=order_token, editable=False)
    user = models.ForeignKey(  # SET_NULL: orders are tax records and outlive accounts (deletion only anonymises)
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders"
    )
    email = models.EmailField(help_text="The account's address, or the guest's.")
    shipping_address = models.JSONField(help_text="A copy of the address as it was when ordering.")
    subtotal = money_field("books")
    discount = money_field("discount", default=0)
    shipping_fee = money_field("shipping", default=0)
    total = money_field("total")
    coupon = models.ForeignKey(Coupon, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders")
    coupon_code = models.CharField(max_length=30, blank=True)
    payment_method = models.CharField(max_length=10, choices=Method.choices, default=Method.RAZORPAY)
    status = FSMField(default=Status.PENDING, choices=Status.choices, protected=True, db_index=True)
    placed_at = models.DateTimeField(
        null=True, blank=True, db_index=True, help_text="Paid online, or placed with cash on delivery."
    )
    stock_reserved = models.BooleanField(default=False, editable=False)
    livemode = models.BooleanField(
        "live mode", default=False, editable=False, help_text="Made with live Razorpay keys (its payment's mode)."
    )
    created_by = models.ForeignKey(  # a phone or school order made in the admin (services.create_staff_order)
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+", editable=False
    )
    history = HistoricalRecords(excluded_fields=["shipping_address", "token"])

    objects = OrderQuerySet.as_manager()

    class Meta:
        ordering = ["-created"]
        permissions = [("export_order", "Can export orders")]  # the admin's CSV/XLSX export (ADMIN role)

    def __str__(self):
        return self.number or f"Order #{self.pk}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.number:
            self.number = f"EL-{timezone.localdate(self.created).year}-{self.pk:06d}"
            Order.objects.filter(pk=self.pk).update(number=self.number)

    def get_absolute_url(self):
        return f"/account/orders/{self.number}/"

    def get_link_url(self):  # the emails' link, for guests and owners alike
        return f"/orders/t/{self.token}/"

    @property
    def is_cod(self):
        return self.payment_method == self.Method.COD

    @property
    def address_lines(self):
        return address_lines(self.shipping_address)

    @property
    def status_label(self):
        if self.status == self.Status.PENDING and self.is_cod and self.placed_at:
            return "placed (pay on delivery)"
        return self.get_status_display()

    @property
    def can_cancel(self):  # by the customer; staff may also cancel a packed order (admin)
        return self.status in (self.Status.PENDING, self.Status.PAID)

    @property
    def is_test(self):
        """Made with test keys while the site runs on live ones: marked TEST in the admin, never packed or shipped."""
        return not self.livemode and live_mode()

    @property
    def is_digital(self):
        """Only digital products: nothing to pack or ship, delivered once paid (services.mark_paid)."""
        return all(item.product.digital_only for item in self.items.select_related("product"))

    @property
    def has_digital(self):
        """A digital product among its lines, alone or in a bundle (learn.services.grant_for_order opens both)."""
        digital = models.Q(product__kind=Product.Kind.DIGITAL)
        return self.items.filter(digital | models.Q(product__bundle_items__product__kind=Product.Kind.DIGITAL)).exists()

    @property
    def payment_reference(self):
        """The bank or UPI reference of a payment recorded by staff (printed on the invoice), or ""."""
        offline = self.payments.filter(method=self.Method.OFFLINE, status=Payment.Status.CAPTURED)
        return offline.values_list("reference", flat=True).first() or ""

    @property
    def savings(self):
        """(label, Money) for each of its discounts: coupon, offers, staff discount. Orders made before these lines
        were kept have their coupon only."""
        lines = [(line.label, line.amount) for line in self.discount_lines.all()]
        if not lines and self.discount.amount:
            lines = [(f"Coupon {self.coupon_code}" if self.coupon_code else "Discount", self.discount)]
        return lines

    def ready_to_pack(self):
        return (self.status == self.Status.PAID or (self.is_cod and self.placed_at is not None)) and not self.is_test

    def timeline(self):
        """(status, time) for each change of status, from the order's history."""
        events = []
        for record in self.history.order_by("history_date").only("status", "history_date"):
            if not events or events[-1][0] != record.status:
                events.append((record.status, record.history_date))
        labels = {**dict(self.Status.choices), self.Status.PENDING: "ordered"}
        return [(labels[status], when) for status, when in events]

    # Transitions. Callers lock the row (select_for_update) and save; services.py adds stock, refunds and emails.
    @transition(status, source=Status.PENDING, target=Status.PAID, conditions=[lambda o: not o.is_cod])
    def pay(self):
        self.placed_at = timezone.now()

    @transition(status, source=[Status.PAID, Status.PENDING], target=Status.PACKED, conditions=[ready_to_pack])
    def pack(self):
        pass

    @transition(status, source=Status.PACKED, target=Status.SHIPPED, conditions=[lambda o: not o.is_test])
    def ship(self):
        pass

    @transition(status, source=Status.SHIPPED, target=Status.DELIVERED)
    def deliver(self):
        pass

    @transition(status, source=Status.PAID, target=Status.DELIVERED, conditions=[lambda o: o.is_digital])
    def deliver_digital(self):
        pass

    @transition(status, source=[Status.PENDING, Status.PAID, Status.PACKED], target=Status.CANCELLED)
    def cancel(self):
        pass

    @transition(
        status,
        source=[Status.PAID, Status.PACKED, Status.SHIPPED, Status.DELIVERED, Status.CANCELLED],
        target=Status.REFUNDED,
    )
    def mark_refunded(self):
        pass


class OrderItem(models.Model):
    """A line of an order, with the product's details and price as they were when ordering."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="+")
    title = models.CharField(max_length=200)
    hsn_code = models.CharField("HSN", max_length=8)
    gst_rate = models.DecimalField("GST %", max_digits=4, decimal_places=2)
    mrp = money_field("MRP")
    unit_price = money_field("price")
    quantity = models.PositiveSmallIntegerField()
    # the line's share of the order's discounts, as cart.totals split them (invoices print it); empty on orders made
    # before it was kept, whose documents share the discount out as they always did (invoices.context)
    discount = money_field("discount", null=True, blank=True)

    class Meta:
        ordering = ["pk"]

    def __str__(self):
        return f"{self.quantity} × {self.title}"

    @property
    def line_total(self):
        return self.unit_price * self.quantity


class OrderDiscount(models.Model):
    """One saving of an order as the customer saw it: its coupon, an automatic offer, a staff discount. The offers'
    usage limits count these lines."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="discount_lines")
    offer = models.ForeignKey(Offer, on_delete=models.SET_NULL, null=True, blank=True, related_name="order_lines")
    label = models.CharField(max_length=100)
    amount = money_field("amount")

    class Meta:
        ordering = ["pk"]

    def __str__(self):
        return f"{self.label} −{self.amount}"


class Payment(ConcurrentTransitionMixin, TimeStampedModel):
    """One way of paying an order: a Razorpay order (its payment attempts end here), or cash on delivery."""

    class Status(models.TextChoices):
        CREATED = "created", "created"
        AUTHORIZED = "authorized", "authorized"
        CAPTURED = "captured", "captured"
        FAILED = "failed", "failed"
        REFUNDED = "refunded", "refunded"

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="payments")
    method = models.CharField(max_length=10, choices=Order.Method.choices)
    amount = money_field("amount")
    razorpay_order_id = models.CharField(max_length=40, unique=True, null=True, blank=True)
    razorpay_payment_id = models.CharField(max_length=40, unique=True, null=True, blank=True)
    razorpay_signature = models.CharField(max_length=128, blank=True)
    # a Razorpay Payment Link sent for a staff order (payments.send_payment_link): its own Payment, whose Razorpay order
    # (made by the link) is known once it is paid (services.record_link_payment)
    razorpay_payment_link_id = models.CharField(max_length=40, unique=True, null=True, blank=True)
    payment_link_url = models.URLField(blank=True)
    reference = models.CharField(
        "bank or UPI reference", max_length=60, blank=True, help_text="A payment recorded by staff (offline)."
    )
    status = FSMField(default=Status.CREATED, choices=Status.choices, protected=True)
    error = models.CharField(max_length=255, blank=True, help_text="Why the last attempt failed (from Razorpay).")
    livemode = models.BooleanField(
        "live mode", default=False, editable=False, help_text="Made with live Razorpay keys (the key of its order)."
    )
    # Of the last webhook's payment entity only these fields are kept (no email, phone, UPI ID, card or bank details),
    # and only for PAYLOAD_DAYS (tasks.clean_up). Not shown in the admin.
    PAYLOAD_FIELDS = "id order_id status method amount currency error_code error_description created_at".split()
    PAYLOAD_DAYS = 180
    raw_payload = models.JSONField("last webhook", null=True, blank=True)
    history = HistoricalRecords(excluded_fields=["raw_payload"])

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return f"Payment #{self.pk} ({self.get_method_display()})"

    @transition(status, source=[Status.CREATED, Status.FAILED], target=Status.AUTHORIZED)
    def authorize(self):
        pass

    @transition(status, source=[Status.CREATED, Status.AUTHORIZED, Status.FAILED], target=Status.CAPTURED)
    def capture(self):
        self.error = ""

    @transition(status, source=[Status.CREATED, Status.AUTHORIZED, Status.FAILED], target=Status.FAILED)
    def fail(self, reason=""):
        self.error = reason[:255]

    @transition(status, source=Status.CAPTURED, target=Status.REFUNDED)
    def refund(self):
        pass


class OrderNote(TimeStampedModel):
    """Staff's internal note on an order (a phone call, a promise, a school's purchase order): never shown to the
    customer; its changes are kept (history). Deleted with the order's customer details (services.forget_orders)."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="notes")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+", editable=False
    )
    text = models.TextField(max_length=2000)
    history = HistoricalRecords()

    class Meta:
        ordering = ["created"]

    def __str__(self):
        return Truncator(self.text).chars(60)


class Refund(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "requested"
        PROCESSED = "processed", "processed"
        FAILED = "failed", "failed"

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="refunds")
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name="refunds")
    amount = money_field("amount")
    reason = models.CharField(max_length=200)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    razorpay_refund_id = models.CharField(max_length=40, unique=True, null=True, blank=True)
    error = models.CharField(max_length=255, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="The staff member; empty when the customer cancelled or the site refunded by itself.",
    )

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return f"Refund #{self.pk}"


class Shipment(TimeStampedModel):
    class Courier(models.TextChoices):
        INDIA_POST = "India Post", "India Post"
        DELHIVERY = "Delhivery", "Delhivery"
        BLUE_DART = "Blue Dart", "Blue Dart"
        EKART = "Ekart", "Ekart"
        DTDC = "DTDC", "DTDC"
        XPRESSBEES = "Xpressbees", "Xpressbees"
        OTHER = "Other", "another courier"

    # Couriers whose tracking page takes the number in its address (each answered a test number on 2026-10-08: open a
    # real one before relying on it). The rest, India Post (its page needs a CAPTCHA) included: 17TRACK.
    TRACKING_URLS = {
        Courier.DELHIVERY: "https://www.delhivery.com/track-v2/package/{number}",
        Courier.BLUE_DART: "https://www.bluedart.com/trackdartresult?trackFor=0&trackNo={number}",
        Courier.EKART: "https://ekartlogistics.com/shipmenttrack/{number}",
    }
    OTHER_TRACKING_URL = "https://t.17track.net/en#nums={number}"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="shipments")
    courier = models.CharField(max_length=80, choices=Courier.choices, default=Courier.INDIA_POST)
    tracking_number = models.CharField(max_length=80)
    tracking_url = models.URLField(blank=True, help_text="Empty: the courier's tracking page, or 17TRACK's.")
    shipped_at = models.DateTimeField(default=timezone.now)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-shipped_at"]

    def __str__(self):
        return f"{self.courier} {self.tracking_number}"

    @classmethod
    def tracking_url_for(cls, courier, number):
        return cls.TRACKING_URLS.get(courier, cls.OTHER_TRACKING_URL).format(number=quote(number.strip(), safe=""))


class Review(TimeStampedModel):
    """A buyer's review: only from an account with a delivered order of the product, one per product and account,
    shown once staff approve it (admin, Reviews). The page says "Verified buyer", never a name: many buyers are minors.
    Deleted with the account (forget_shop_details)."""

    class Status(models.TextChoices):
        PENDING = "pending", "waiting for approval"
        APPROVED = "approved", "approved"
        REJECTED = "rejected", "rejected"

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="reviews")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews")
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    text = models.TextField(max_length=1000, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["-created"]
        constraints = [
            models.UniqueConstraint(fields=["product", "user"], name="one_review_per_product_and_user"),
            models.CheckConstraint(condition=models.Q(rating__gte=1, rating__lte=5), name="review_rating_1_to_5"),
        ]

    def __str__(self):
        return f"{self.rating}/5 for {self.product}"

    @property
    def stars(self):
        return "★" * self.rating + "☆" * (5 - self.rating)

    @staticmethod
    def can_review(user, product):
        """Whether this account may review the product: it received an order of it and has not reviewed it yet."""
        if not user.is_authenticated or Review.objects.filter(user=user, product=product).exists():
            return False
        return Order.objects.filter(user=user, status=Order.Status.DELIVERED, items__product=product).exists()


def financial_year(day):
    """Indian financial year (April to March) of a date: '2026-27'."""
    start = day.year if day.month >= 4 else day.year - 1
    return f"{start}-{(start + 1) % 100:02d}"


def next_number(model, prefix, test_prefix, live):
    """The next number of an invoice or credit note: per financial year, at most 16 characters as GST requires
    (EL/2026-27/00001). An order made with Razorpay test keys (`live` False: the mode of its payment, whatever keys the
    site runs on now) has a separate series (T before the year, `test_prefix` in the number), so the real numbering
    starts at 00001 when the shop goes live. The unique constraint stops two taking one number."""
    year = financial_year(timezone.localdate())
    series = year if live else f"T{year}"
    last = model.objects.filter(financial_year=series).order_by("-serial").values_list("serial", flat=True).first()
    serial = (last or 0) + 1
    return {
        "financial_year": series,
        "serial": serial,
        "number": f"{prefix if live else test_prefix}/{year}/{serial:05d}",
    }


class Invoice(TimeStampedModel):
    """The GST invoice (a bill of supply while every book is exempt): EL/2026-27/00001, T/2026-27/00001 in the test
    series (next_number)."""

    order = models.OneToOneField(Order, on_delete=models.PROTECT, related_name="invoice")
    number = models.CharField(max_length=16, unique=True)
    financial_year = models.CharField(max_length=8, help_text="T before it: the test series.")
    serial = models.PositiveIntegerField()
    pdf = models.FileField(upload_to="invoices/", blank=True)

    class Meta:
        ordering = ["-created"]
        constraints = [models.UniqueConstraint(fields=["financial_year", "serial"], name="unique_invoice_serial")]

    def __str__(self):
        return self.number

    @property
    def is_test(self):
        return self.financial_year.startswith("T")

    @classmethod
    def for_order(cls, order):
        """The order's invoice, numbered now if it has none (in one transaction with what its post_save receivers
        write: the erp app's outbox row)."""
        if invoice := cls.objects.filter(order=order).first():
            return invoice
        with transaction.atomic():
            return cls.objects.create(order=order, **next_number(cls, "EL", "T", live=order.livemode))


class CreditNote(TimeStampedModel):
    """The credit note for a refund of an invoiced order (in full or in part): it reduces the invoice for GST. Its own
    series: CN/2026-27/00001, TC/2026-27/00001 with test keys (next_number)."""

    refund = models.OneToOneField(Refund, on_delete=models.PROTECT, related_name="credit_note")
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="credit_notes")
    number = models.CharField(max_length=16, unique=True)
    financial_year = models.CharField(max_length=8, help_text="T before it: the test series.")
    serial = models.PositiveIntegerField()
    pdf = models.FileField(upload_to="credit-notes/", blank=True)

    class Meta:
        ordering = ["created"]
        constraints = [models.UniqueConstraint(fields=["financial_year", "serial"], name="unique_credit_note_serial")]

    def __str__(self):
        return self.number

    @property
    def is_test(self):
        return self.financial_year.startswith("T")

    @classmethod
    def for_refund(cls, refund, invoice):
        """The refund's credit note, numbered now if it has none (in one transaction with what its post_save receivers
        write: the erp app's outbox row)."""
        if note := cls.objects.filter(refund=refund).first():
            return note
        live = not invoice.is_test  # the note follows its invoice's series
        with transaction.atomic():
            return cls.objects.create(refund=refund, invoice=invoice, **next_number(cls, "CN", "TC", live=live))


class StockAlert(models.Model):
    """A request "email me when it is back" on the page of a product out of stock: one email once it has copies
    again (tasks.send_stock_alerts, hourly), then the row is deleted; one never sent goes after a year (clean_up)."""

    email = models.EmailField()
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="stock_alerts")
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["email", "product"], name="one_stock_alert_per_email")]

    def __str__(self):
        return f"{self.product} for {self.email}"


class QuoteRequest(TimeStampedModel):
    """A school's or bookseller's request for many copies (the public form at /shop/school-orders/): staff are emailed,
    answer with a quotation PDF (admin action, valid VALID_DAYS days, kept in the private storage) and take the payment
    outside the site (NEFT, UPI or a Razorpay Payment Link); RUNBOOK.md "School and bulk orders"."""

    VALID_DAYS = 15

    class Status(models.TextChoices):
        NEW = "new", "new"
        QUOTED = "quoted", "quotation made"
        ORDERED = "ordered", "ordered"
        CLOSED = "closed", "closed"

    school = models.CharField("school or organisation", max_length=200)
    contact_name = models.CharField("contact person", max_length=120)
    email = models.EmailField()
    phone = PhoneNumberField("mobile number", region="IN", validators=[validate_indian_mobile])
    gstin = models.CharField("GSTIN", max_length=15, blank=True, validators=[validate_gstin])
    items = models.JSONField(help_text="The books asked for: [{product (slug), title, quantity}].")
    delivery_pin = models.CharField("delivery PIN code", max_length=6, validators=[validate_pin])
    note = models.TextField(max_length=1000, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.NEW, db_index=True)
    discount_percent = models.DecimalField(
        "discount (%)",
        max_digits=4,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(50)],
        help_text="On the books, in the next quotation.",
    )
    shipping_fee = models.DecimalField("shipping (₹)", max_digits=8, decimal_places=2, default=0)
    quotation = models.FileField(upload_to="quotations/", blank=True, editable=False)  # the private storage
    quoted_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return f"{self.number} {self.school}"

    @property
    def number(self):
        return f"QT-{timezone.localdate(self.created).year}-{self.pk:05d}"

    @property
    def copies(self):
        return sum(item["quantity"] for item in self.items)

    @property
    def valid_until(self):
        return timezone.localdate(self.quoted_at) + timedelta(days=self.VALID_DAYS) if self.quoted_at else None


class WebhookEvent(models.Model):
    """A Razorpay webhook already handled: its event id (X-Razorpay-Event-Id) and the hash of its signed body, so that
    a repeat, or a replay under another id, is acknowledged and ignored (payments.handle_webhook). Events older than
    WEBHOOK_MAX_AGE are refused by their signed time, so rows are deleted after that (tasks.clean_up)."""

    event_id = models.CharField(max_length=64, unique=True)
    digest = models.CharField("SHA-256 of the body", max_length=64, unique=True)
    name = models.CharField(max_length=40)
    received_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return self.event_id


@receiver(post_save, sender=Product)
def queue_og_image(sender, instance, update_fields=None, **kwargs):
    """A new link-preview picture once the product's title or cover may have changed (tasks.make_og_image)."""
    if update_fields is None or {"title", "cover"} & set(update_fields):
        from .tasks import make_og_image

        transaction.on_commit(lambda: make_og_image.delay(instance.pk), robust=True)


@receiver(post_save, sender=DeletionRequest)
def forget_shop_details(sender, instance, **kwargs):
    """Account deletion (accounts.DeletionRequest.complete): saved addresses, the cart and the reviews (with their
    history) go; orders stay as tax records, with the address copied into them."""
    if instance.status == DeletionRequest.Status.DONE:
        Review.objects.filter(user=instance.user_id).delete()
        Review.history.filter(user_id=instance.user_id).delete()
        addresses = Address.objects.filter(user=instance.user_id)
        LogEntry.objects.filter(  # admin history rows name an address by its text: the name, the town, the PIN
            content_type=ContentType.objects.get_for_model(Address),
            object_id__in=[str(pk) for pk in addresses.values_list("pk", flat=True)],
        ).update(object_repr=f"deleted address of account #{instance.user_id}")
        addresses.delete()
        Cart.objects.filter(user=instance.user_id).delete()


def claim_guest_orders(user, emails):
    """Orders placed without an account (or by staff for a customer without one) with one of these addresses, in any
    case, join the account, so that My orders lists them. Only confirmed addresses are given: whoever confirmed one
    reads its mail, the order emails included."""
    emails = {email.lower() for email in emails}
    for order in Order.objects.alias(address=Lower("email")).filter(user=None, address__in=emails) if emails else ():
        order.user = user
        order.save(update_fields=["user", "modified"])  # through save: the order's history records it


@receiver(email_confirmed)  # the code of a sign-up or of a new address typed in
def claim_orders_of_a_confirmed_address(sender, request, email_address, **kwargs):
    if email_address.user_id:
        claim_guest_orders(email_address.user, [email_address.email])


@receiver(user_logged_in)  # every log-in (website, admin, API), for an account made before this existed
def claim_orders_at_log_in(sender, request, user, **kwargs):
    claim_guest_orders(user, EmailAddress.objects.filter(user=user, verified=True).values_list("email", flat=True))
