"""Parcels and couriers (research-integrations.md section 3). A parcel is shop.Shipment, as before; its courier side is
ShipmentDetail, one to one, so that shop's model and migrations stay as they were:

- ShipmentDetail: the carrier and its account, our status (status.py), the carrier's ids, the courier, the label and
  the photograph of the parcel on the scale (kept by us, in the private storage), the weights, the quote, the cash to
  collect, the pickup;
- ShipmentEvent: the parcel's timeline, one row per courier scan, deduplicated by a digest of the scan;
- PickupLocation: our pickup addresses, by the nickname the carrier knows them by;
- ShipmentCharge: the carrier's wallet statement, line by line (freight, COD, RTO, excess weight, their reversals);
- CodRemittance: the cash a courier collected for us, expected then remitted;
- ShippingException: what staff must deal with, with a deadline (pickup problems, failed deliveries, returns, losses,
  weight disputes, overdue COD, parcels that stopped moving); exception_opened tells the staff inbox;
- PinServiceability: which couriers serve a PIN (the survey of the North-East's PINs);
- PostalTariff: India Post's prices by weight, from a fixture of the published tariff (verify at the counter).
Each model has a stable `kind` (a field where it has kinds of its own) for the staff inbox and the audit log."""

from datetime import timedelta

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone
from model_utils.models import TimeStampedModel

from integrations.models import IntegrationAccount

from . import signals
from .status import BEFORE_PICKUP, FINAL, LEFT, Status


def money(verbose_name, **kwargs):
    return models.DecimalField(verbose_name, max_digits=10, decimal_places=2, **kwargs)


class PickupLocation(TimeStampedModel):
    """One of our pickup addresses, as the carrier knows it: Shiprocket's `pickup_location` nickname (36 characters at
    most), which a booking must name. One row until a second store exists; the default one is used unless staff
    choose."""

    kind = "pickup_location"

    nickname = models.CharField(max_length=36, unique=True)
    external_id = models.CharField("carrier's id", max_length=40, blank=True)
    address = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=80, blank=True)
    state = models.CharField(max_length=80, blank=True)
    pin_code = models.CharField("PIN code", max_length=6)
    phone = models.CharField(max_length=20, blank=True)
    is_default = models.BooleanField(default=False)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-is_default", "nickname"]
        constraints = [
            models.UniqueConstraint(
                fields=["is_default"], condition=models.Q(is_default=True), name="one_default_pickup"
            )
        ]

    def __str__(self):
        return f"{self.nickname} ({self.pin_code})"

    @classmethod
    def default(cls):
        return cls.objects.filter(active=True).order_by("-is_default", "pk").first()


class ShipmentDetail(TimeStampedModel):
    """The courier side of a parcel (shop.Shipment). Its status is null until the carrier has booked it; its AWB is
    the shipment's tracking_number. `reference` is the order id we gave the carrier (the order number, "-R1" for the
    first re-shipment): a carrier never takes the same one twice. `locked_until` marks a worker talking to the carrier
    about it (claim()), so that two never book it at once; no transaction is held during the call."""

    kind = "parcel"

    class Carrier(models.TextChoices):
        MANUAL = "manual", "by hand (staff type the courier and number)"
        SHIPROCKET = "shiprocket", "Shiprocket"

    shipment = models.OneToOneField("shop.Shipment", on_delete=models.CASCADE, related_name="detail")
    carrier = models.CharField(max_length=20, choices=Carrier.choices)
    account = models.ForeignKey(
        IntegrationAccount, on_delete=models.PROTECT, null=True, blank=True, related_name="parcels"
    )
    status = models.CharField(max_length=20, choices=Status.choices, null=True, blank=True, db_index=True)  # noqa: DJ001
    reference = models.CharField("our order id at the carrier", max_length=50, blank=True)
    external_order_id = models.CharField("carrier's order id", max_length=40, blank=True)
    external_shipment_id = models.CharField("carrier's shipment id", max_length=40, blank=True)
    courier_company_id = models.PositiveIntegerField(null=True, blank=True)
    courier_name = models.CharField(max_length=80, blank=True)
    label = models.FileField(upload_to="shipping/labels/", blank=True)  # the default storage: private, signed links
    parcel_photo = models.FileField(
        upload_to="shipping/photos/", blank=True, help_text="The parcel on the scale, label side up: the evidence."
    )
    weight_g = models.PositiveIntegerField("weight (g)", null=True, blank=True, help_text="As weighed at packing.")
    length_cm = models.PositiveSmallIntegerField(null=True, blank=True)
    breadth_cm = models.PositiveSmallIntegerField(null=True, blank=True)
    height_cm = models.PositiveSmallIntegerField(null=True, blank=True)
    charged_weight_g = models.PositiveIntegerField("charged weight (g)", null=True, blank=True)
    quoted_rate = money("quoted rate (₹)", null=True, blank=True)
    cod_amount = money("cash to collect (₹)", null=True, blank=True, help_text="Empty: prepaid.")
    declared_value = money("declared value (₹)", null=True, blank=True)
    last_event_at = models.DateTimeField(null=True, blank=True, db_index=True)
    pickup_location = models.ForeignKey(
        PickupLocation, on_delete=models.PROTECT, null=True, blank=True, related_name="parcels"
    )
    pickup_date = models.DateField(null=True, blank=True)
    manifested_at = models.DateTimeField(null=True, blank=True)
    locked_until = models.DateTimeField(null=True, blank=True, editable=False)
    sms_held = models.CharField(
        max_length=30, blank=True, editable=False, help_text="An SMS kept for the morning (none from 21:00 to 08:00)."
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["carrier", "reference"], condition=~models.Q(reference=""), name="one_parcel_per_reference"
            )
        ]

    def __str__(self):
        return f"{self.shipment} ({self.get_status_display() or 'not booked yet'})"

    @property
    def is_final(self):
        return self.status in FINAL

    @property
    def has_left(self):
        """On its way to the customer (or back): shown on the customer's order page."""
        return self.status in LEFT

    @property
    def cancellable(self):
        return self.status is None or self.status in BEFORE_PICKUP

    def claim(self, minutes=5):
        """Mark a worker talking to the carrier about this parcel; False if another one is (and not for too long)."""
        now = timezone.now()
        free = models.Q(locked_until__isnull=True) | models.Q(locked_until__lt=now)
        claimed = type(self).objects.filter(free, pk=self.pk).update(locked_until=now + timedelta(minutes=minutes))
        return bool(claimed)

    def release(self):
        type(self).objects.filter(pk=self.pk).update(locked_until=None)

    def change(self, **fields):
        """Save these fields now, alone (a step of a booking that must not be lost if the next one fails)."""
        for name, value in fields.items():
            setattr(self, name, value)
        type(self).objects.filter(pk=self.pk).update(**fields, modified=timezone.now())


class ShipmentEvent(models.Model):
    """One scan of a parcel, from the carrier's webhook, a poll of its tracking, or staff. The digest of the AWB, the
    courier's code, the time and the activity is unique: a scan repeated in later payloads, or read again by a poll,
    is kept once. `status` is ours (null when the code means nothing to us); `raw` the scan as the carrier sent it."""

    kind = "parcel_event"

    class Source(models.TextChoices):
        WEBHOOK = "webhook", "webhook"
        POLL = "poll", "tracking read"
        MANUAL = "manual", "staff"

    shipment = models.ForeignKey("shop.Shipment", on_delete=models.CASCADE, related_name="events")
    source = models.CharField(max_length=10, choices=Source.choices)
    carrier_code = models.CharField(max_length=40, blank=True, help_text="Shiprocket's status code, e.g. 18.")
    carrier_label = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, null=True, blank=True)  # noqa: DJ001
    occurred_at = models.DateTimeField()
    location = models.CharField(max_length=200, blank=True)
    activity = models.CharField(max_length=300, blank=True)
    raw = models.JSONField(default=dict, blank=True)
    digest = models.CharField(max_length=64, unique=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["occurred_at", "pk"]

    def __str__(self):
        return f"{self.carrier_label or self.get_status_display()} at {self.occurred_at:%d %b %H:%M}"


class ShipmentCharge(models.Model):
    """One line of the carrier's wallet statement: a charge (positive) or a reversal (negative), unique by the line's
    id, matched to its parcel by the AWB. Kept even when no parcel of ours matches (a booking made in the carrier's
    own panel): the money is ours all the same."""

    class Kind(models.TextChoices):
        FREIGHT = "freight", "freight"
        FREIGHT_REVERSAL = "freight_reversal", "freight reversed"
        COD = "cod", "COD charge"
        COD_REVERSAL = "cod_reversal", "COD charge reversed"
        RTO_FREIGHT = "rto_freight", "RTO freight"
        RTO_FREIGHT_REVERSAL = "rto_freight_reversal", "RTO freight reversed"
        EXCESS_WEIGHT = "excess_weight", "excess weight"
        EXCESS_WEIGHT_REVERSAL = "excess_weight_reversal", "excess weight reversed"
        OTHER = "other", "other"

    shipment = models.ForeignKey(
        "shop.Shipment", on_delete=models.SET_NULL, null=True, blank=True, related_name="charges"
    )
    account = models.ForeignKey(IntegrationAccount, on_delete=models.PROTECT, related_name="charges")
    kind = models.CharField(max_length=30, choices=Kind.choices)
    amount = money("amount (₹)", help_text="Positive: charged to us; negative: given back.")
    statement_line_id = models.CharField(max_length=64, unique=True)
    charged_weight_g = models.PositiveIntegerField(null=True, blank=True)
    awb = models.CharField("AWB", max_length=40, blank=True)
    description = models.CharField(max_length=200, blank=True)
    charged_at = models.DateTimeField()
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-charged_at"]

    def __str__(self):
        return f"{self.get_kind_display()} ₹{self.amount} ({self.awb or 'no AWB'})"


class CodRemittance(TimeStampedModel):
    """The cash a courier collected on delivery: expected (the amount and the day: delivered + 10 working days), then
    remitted (the amount and the bank's UTR), overdue (2 working days past the day), mismatched (another amount), or
    not expected (the parcel came back, was lost, or the booking was cancelled)."""

    kind = "cod_remittance"

    class State(models.TextChoices):
        EXPECTED = "expected", "expected"
        OVERDUE = "overdue", "overdue"
        REMITTED = "remitted", "remitted"
        MISMATCH = "mismatch", "remitted, another amount"
        NOT_EXPECTED = "not_expected", "not expected"

    shipment = models.OneToOneField("shop.Shipment", on_delete=models.PROTECT, related_name="cod_remittance")
    expected_amount = money("expected (₹)")
    expected_on = models.DateField()
    remitted_amount = money("remitted (₹)", null=True, blank=True)
    utr = models.CharField("UTR", max_length=60, blank=True)
    remitted_at = models.DateField(null=True, blank=True)
    state = models.CharField(max_length=15, choices=State.choices, default=State.EXPECTED, db_index=True)
    checked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["expected_on"]

    def __str__(self):
        return f"COD ₹{self.expected_amount} for {self.shipment} ({self.get_state_display()})"


class ShippingException(TimeStampedModel):
    """Something about a parcel that staff must deal with by `due_at`; one open per parcel and kind (a second failed
    attempt updates the first), and `reference` (the carrier's id of a weight dispute) makes it once for good.
    Resolved with what was done, or dismissed. exception_opened tells the staff inbox."""

    class Kind(models.TextChoices):
        PICKUP_PROBLEM = "pickup_problem", "pickup problem"
        NDR = "ndr", "delivery failed (NDR)"
        RTO = "rto", "returning or returned (RTO)"
        LOST = "lost", "lost or damaged"
        PARTIAL = "partial", "partly delivered"
        WEIGHT_DISPUTE = "weight_dispute", "weight dispute"
        COD_OVERDUE = "cod_overdue", "COD overdue or mismatched"
        NO_MOVEMENT = "no_movement", "no movement"

    class State(models.TextChoices):
        OPEN = "open", "open"
        RESOLVED = "resolved", "resolved"
        DISMISSED = "dismissed", "dismissed"

    kind = models.CharField(max_length=20, choices=Kind.choices)
    shipment = models.ForeignKey("shop.Shipment", on_delete=models.CASCADE, related_name="exceptions")
    due_at = models.DateTimeField(db_index=True)
    state = models.CharField(max_length=10, choices=State.choices, default=State.OPEN, db_index=True)
    reference = models.CharField(max_length=64, blank=True, help_text="The carrier's id of it, if it has one.")
    data = models.JSONField(default=dict, blank=True)
    resolution = models.CharField(max_length=300, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["due_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["kind", "reference"], condition=~models.Q(reference=""), name="one_exception_per_reference"
            )
        ]

    def __str__(self):
        return f"{self.get_kind_display()}: {self.shipment} (due {timezone.localtime(self.due_at):%d %b %H:%M})"

    def opened(self):
        """Tell the staff inbox, once the transaction is committed."""
        transaction.on_commit(
            lambda: signals.exception_opened.send(sender=type(self), exception=self, kind=self.kind), robust=True
        )


class PinServiceability(models.Model):
    """What a courier answered for a PIN in the last survey (manage.py shipping_survey_pins): COD and prepaid, the
    rate of a 500 g parcel from our pickup and the days it takes. courier_company_id 0: no courier at all."""

    kind = "pin_serviceability"
    NONE = 0

    pin = models.CharField("PIN code", max_length=6, db_index=True)
    courier_company_id = models.PositiveIntegerField()
    courier_name = models.CharField(max_length=80, blank=True)
    cod = models.BooleanField(default=False)
    prepaid = models.BooleanField(default=False)
    rate = money("rate (₹)", null=True, blank=True)
    etd_days = models.PositiveSmallIntegerField("days to deliver", null=True, blank=True)
    surveyed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["pin", "rate"]
        verbose_name_plural = "PIN serviceability"
        constraints = [models.UniqueConstraint(fields=["pin", "courier_company_id"], name="one_answer_per_pin")]

    def __str__(self):
        return f"{self.pin}: {self.courier_name or 'no courier'}"


class PostalTariff(models.Model):
    """India Post's price of a weight slab (up to `weight_to_g`) from a date. Loaded from shipping/fixtures/
    postal_tariffs.json, the published tariff as the research read it (verify at the counter); none in a migration."""

    kind = "postal_tariff"

    class Service(models.TextChoices):
        BOOK_POST = "book_post", "Book Post (open, untracked)"
        GYAN_POST = "gyan_post", "Gyan Post (tracked, surface)"
        SPEED_POST = "speed_post", "Speed Post"

    service = models.CharField(max_length=12, choices=Service.choices)
    weight_to_g = models.PositiveIntegerField("up to (g)")
    price = models.DecimalField("price (₹)", max_digits=8, decimal_places=2)
    effective_from = models.DateField()
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["service", "-effective_from", "weight_to_g"]
        constraints = [
            models.UniqueConstraint(fields=["service", "weight_to_g", "effective_from"], name="one_price_per_slab")
        ]

    def __str__(self):
        return f"{self.get_service_display()} up to {self.weight_to_g} g: ₹{self.price}"

    @classmethod
    def price_for(cls, service, weight_g, on=None):
        """The price of the smallest slab that holds `weight_g` in the tariff in force `on` (today), or None."""
        on = on or timezone.localdate()
        current = cls.objects.filter(service=service, effective_from__lte=on).order_by("-effective_from").first()
        if current is None:
            return None
        slab = (
            cls.objects.filter(service=service, effective_from=current.effective_from, weight_to_g__gte=weight_g)
            .order_by("weight_to_g")
            .first()
        )
        return slab.price if slab else None
