"""The shop: the printed books sold online in India, paid through Razorpay or cash on delivery.

Money is in rupees (django-money, INR only); Razorpay counts whole paise (`paise()`). Order and Payment are state
machines (django-fsm-2): a status changes only through its transitions, whose guards say from which states they may
run, and django-simple-history keeps every change (the customer's status timeline). The flows that combine several
records (stock, refunds, emails) are in services.py."""

import re
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.contrib.admin.models import LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone
from django_fsm import ConcurrentTransitionMixin, FSMField, transition
from djmoney.models.fields import MoneyField
from djmoney.money import Money
from localflavor.in_.in_states import STATE_CHOICES
from localflavor.in_.models import INStateField
from model_utils.models import TimeStampedModel
from phonenumber_field.modelfields import PhoneNumberField
from simple_history.models import HistoricalRecords

from accounts.models import DeletionRequest

INR = "INR"
STATES = dict(STATE_CHOICES)
validate_pin = RegexValidator(r"^[1-9]\d{5}$", "Enter the 6-digit PIN code.")


def rupees(amount):
    """A Decimal rounded to the paisa, halves up (as on a bill)."""
    return Decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def paise(money):
    """Razorpay's amounts: whole paise, as an int."""
    return int(rupees(money.amount if isinstance(money, Money) else money) * 100)


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
    cover = models.ImageField(upload_to="products/", blank=True)
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

    class Meta:
        ordering = ["subject", "kind", "title"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("shop:product", args=[self.slug])

    def clean(self):
        if self.price and self.mrp and self.price > self.mrp:
            raise ValidationError({"price": "The selling price cannot be above the MRP."})

    def stock_lines(self, quantity):
        """{product id: copies} that selling `quantity` of this product takes from stock."""
        if self.kind == self.Kind.BUNDLE:
            return {item.product_id: item.quantity * quantity for item in self.bundle_items.all()}
        return {self.pk: quantity}

    @property
    def available(self):
        if self.kind == self.Kind.BUNDLE:
            items = self.bundle_items.select_related("product")
            return min((item.product.stock // item.quantity for item in items), default=0)
        return self.stock

    @property
    def saving_percent(self):
        return round((self.mrp.amount - self.price.amount) * 100 / self.mrp.amount) if self.mrp.amount else 0


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="products/")
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
        off = amount * self.value / 100 if self.kind == self.Kind.PERCENT else self.value
        return min(rupees(off), amount)

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
            mine = models.Q(email__iexact=email or user.email) | (models.Q(user=user) if user else models.Q())
            if used.filter(mine).count() >= self.max_uses_per_customer:
                return "You have already used this coupon."
        return None


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
    def fee_for(cls, state, amount):
        """Shipping (Decimal rupees) to `state` for books worth `amount`; 0 when no rate applies."""
        rates = list(cls.objects.filter(is_active=True))
        rate = next((r for r in rates if state in r.states), None) or next((r for r in rates if not r.states), None)
        if rate is None or (rate.free_above is not None and amount >= rate.free_above.amount):
            return Decimal("0.00")
        return rate.fee.amount


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
    """A user's cart, or a guest's (no user; its id is kept in the session and joins the user's cart at log-in)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="cart"
    )
    coupon = models.ForeignKey(Coupon, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

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

    number = models.CharField(max_length=20, unique=True, null=True, editable=False)  # noqa: DJ001  null until saved
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
    history = HistoricalRecords(excluded_fields=["shipping_address"])

    objects = OrderQuerySet.as_manager()

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return self.number or f"Order #{self.pk}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.number:
            self.number = f"EL-{timezone.localdate(self.created).year}-{self.pk:06d}"
            Order.objects.filter(pk=self.pk).update(number=self.number)

    def get_absolute_url(self):
        return reverse("shop:order", args=[self.number])

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

    def ready_to_pack(self):
        return self.status == self.Status.PAID or (self.is_cod and self.placed_at is not None)

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

    @transition(status, source=Status.PACKED, target=Status.SHIPPED)
    def ship(self):
        pass

    @transition(status, source=Status.SHIPPED, target=Status.DELIVERED)
    def deliver(self):
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

    class Meta:
        ordering = ["pk"]

    def __str__(self):
        return f"{self.quantity} × {self.title}"

    @property
    def line_total(self):
        return self.unit_price * self.quantity


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
    status = FSMField(default=Status.CREATED, choices=Status.choices, protected=True)
    error = models.CharField(max_length=255, blank=True, help_text="Why the last attempt failed (from Razorpay).")
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
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="shipments")
    courier = models.CharField(max_length=80)
    tracking_number = models.CharField(max_length=80)
    tracking_url = models.URLField(blank=True)
    shipped_at = models.DateTimeField(default=timezone.now)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-shipped_at"]

    def __str__(self):
        return f"{self.courier} {self.tracking_number}"


def financial_year(day):
    """Indian financial year (April to March) of a date: '2026-27'."""
    start = day.year if day.month >= 4 else day.year - 1
    return f"{start}-{(start + 1) % 100:02d}"


def next_number(model, prefix, test_prefix):
    """The next number of an invoice or credit note: per financial year, at most 16 characters as GST requires
    (EL/2026-27/00001). With Razorpay test keys a separate series (T before the year, `test_prefix` in the number), so
    the real numbering starts at 00001 when the shop goes live. The unique constraint stops two taking one number."""
    year = financial_year(timezone.localdate())
    test = settings.RAZORPAY_KEY_ID.startswith("rzp_test_")
    series = f"T{year}" if test else year
    last = model.objects.filter(financial_year=series).order_by("-serial").values_list("serial", flat=True).first()
    serial = (last or 0) + 1
    return {
        "financial_year": series,
        "serial": serial,
        "number": f"{test_prefix if test else prefix}/{year}/{serial:05d}",
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
        """The order's invoice, numbered now if it has none."""
        if invoice := cls.objects.filter(order=order).first():
            return invoice
        return cls.objects.create(order=order, **next_number(cls, "EL", "T"))


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
        if note := cls.objects.filter(refund=refund).first():
            return note
        return cls.objects.create(refund=refund, invoice=invoice, **next_number(cls, "CN", "TC"))


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


@receiver(post_save, sender=DeletionRequest)
def forget_shop_details(sender, instance, **kwargs):
    """Account deletion (accounts.DeletionRequest.complete): saved addresses and the cart go; orders stay as tax
    records, with the address copied into them."""
    if instance.status == DeletionRequest.Status.DONE:
        addresses = Address.objects.filter(user=instance.user_id)
        LogEntry.objects.filter(  # admin history rows name an address by its text: the name, the town, the PIN
            content_type=ContentType.objects.get_for_model(Address),
            object_id__in=[str(pk) for pk in addresses.values_list("pk", flat=True)],
        ).update(object_repr=f"deleted address of account #{instance.user_id}")
        addresses.delete()
        Cart.objects.filter(user=instance.user_id).delete()
