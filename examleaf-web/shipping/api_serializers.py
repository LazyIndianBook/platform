"""The serializers of the shipping app's staff API (shipping/api.py; API.md "Shipping (staff)"), for the staff app to
reuse: a parcel with its courier side, timeline, exceptions, charges and COD remittance; the quotes; the requests of
the actions."""

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from shop.models import Order, Shipment

from .models import CodRemittance, PickupLocation, ShipmentCharge, ShipmentDetail, ShipmentEvent, ShippingException
from .services import NDR_ACTIONS


def rupees(**kwargs):
    return serializers.DecimalField(max_digits=10, decimal_places=2, **kwargs)


class ShipmentEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShipmentEvent
        fields = ["source", "carrier_code", "carrier_label", "status", "occurred_at", "location", "activity"]


class ShippingExceptionSerializer(serializers.ModelSerializer):
    order = serializers.CharField(source="shipment.order.number", read_only=True)

    class Meta:
        model = ShippingException
        fields = [
            *["id", "kind", "shipment", "order", "due_at", "state", "reference", "data", "resolution", "resolved_at"],
            *["resolved_by", "created"],
        ]
        read_only_fields = fields


class ShipmentChargeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShipmentCharge
        fields = [
            *["id", "shipment", "kind", "amount", "charged_weight_g", "awb", "description", "statement_line_id"],
            "charged_at",
        ]
        read_only_fields = fields


class CodRemittanceSerializer(serializers.ModelSerializer):
    order = serializers.CharField(source="shipment.order.number", read_only=True)

    class Meta:
        model = CodRemittance
        fields = [
            *["id", "shipment", "order", "expected_amount", "expected_on", "remitted_amount", "utr", "remitted_at"],
            *["state", "checked_at"],
        ]
        read_only_fields = fields


class PickupLocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = PickupLocation
        fields = [
            "id",
            "nickname",
            "address",
            "city",
            "state",
            "pin_code",
            "phone",
            "is_default",
            "active",
            "external_id",
        ]
        read_only_fields = ["external_id"]
        extra_kwargs = {"is_default": {"validators": []}}  # a new default takes over: the view unsets the old one


class ParcelDetailSerializer(serializers.ModelSerializer):
    has_label = serializers.SerializerMethodField()
    has_photo = serializers.SerializerMethodField()

    class Meta:
        model = ShipmentDetail
        fields = [
            *["carrier", "account", "status", "reference", "external_order_id", "external_shipment_id"],
            *["courier_company_id", "courier_name", "weight_g", "length_cm", "breadth_cm", "height_cm"],
            *["charged_weight_g", "quoted_rate", "cod_amount", "declared_value", "last_event_at", "pickup_location"],
            *["pickup_date", "manifested_at", "has_label", "has_photo"],
        ]
        read_only_fields = fields

    def get_has_label(self, detail) -> bool:
        return bool(detail.label)

    def get_has_photo(self, detail) -> bool:
        return bool(detail.parcel_photo)


class ParcelSerializer(serializers.ModelSerializer):
    """A parcel: the shop's shipment (courier, tracking number and link, sent and delivered) and its courier side
    (`detail`), null for a parcel typed by hand in the admin."""

    order = serializers.CharField(source="order.number", read_only=True)
    detail = serializers.SerializerMethodField()

    class Meta:
        model = Shipment
        fields = ["id", "order", "courier", "tracking_number", "tracking_url", "shipped_at", "delivered_at", "detail"]
        read_only_fields = fields

    @extend_schema_field(ParcelDetailSerializer(allow_null=True))
    def get_detail(self, shipment):
        detail = getattr(shipment, "detail", None)  # none: RelatedObjectDoesNotExist is an AttributeError
        return ParcelDetailSerializer(detail).data if detail else None


class ParcelHistorySerializer(ParcelSerializer):
    """A parcel with its timeline, exceptions, charges and COD remittance."""

    events = ShipmentEventSerializer(many=True, read_only=True)
    exceptions = ShippingExceptionSerializer(many=True, read_only=True)
    charges = ShipmentChargeSerializer(many=True, read_only=True)
    cod_remittance = serializers.SerializerMethodField()

    class Meta(ParcelSerializer.Meta):
        fields = [*ParcelSerializer.Meta.fields, "events", "exceptions", "charges", "cod_remittance"]
        read_only_fields = fields

    @extend_schema_field(CodRemittanceSerializer(allow_null=True))
    def get_cod_remittance(self, shipment):
        remittance = CodRemittance.objects.filter(shipment=shipment).first()
        return CodRemittanceSerializer(remittance).data if remittance else None


class QuoteSerializer(serializers.Serializer):
    courier_company_id = serializers.IntegerField()
    courier_name = serializers.CharField()
    rate = rupees()
    etd_days = serializers.IntegerField(allow_null=True, help_text="days to deliver, as the courier says")
    rating = serializers.FloatField(allow_null=True)
    cod = serializers.BooleanField()
    cod_charges = rupees()
    rto_charges = rupees(help_text="what a return would cost")
    recommended = serializers.BooleanField(help_text="the carrier's own pick")


class PostalPriceSerializer(serializers.Serializer):
    service = serializers.CharField()
    label = serializers.CharField()
    price = rupees()


class QuoteResultSerializer(serializers.Serializer):
    couriers = QuoteSerializer(many=True, help_text="the top three, ranked (research 3.4)")
    india_post = PostalPriceSerializer(many=True, help_text="prepaid orders only, from the tariff table")
    weight_g = serializers.IntegerField()
    stale = serializers.BooleanField(help_text="the carrier could not be asked: its last answer for this parcel")
    error = serializers.CharField(allow_blank=True)


class QuoteQuerySerializer(serializers.Serializer):
    weight_g = serializers.IntegerField(required=False, min_value=1, max_value=50000, help_text="as weighed")


class BookSerializer(serializers.Serializer):
    """Book a parcel for a packed order: with a courier of the quote (`courier_company_id`), booked by a task; or
    sent by hand (India Post, a courier without an API): `courier` and `tracking_number`, shipped at once."""

    order = serializers.SlugRelatedField(slug_field="number", queryset=Order.objects.all())
    courier_company_id = serializers.IntegerField(required=False, min_value=1)
    courier_name = serializers.CharField(required=False, max_length=80, default="")
    quoted_rate = rupees(required=False, allow_null=True, default=None)
    weight_g = serializers.IntegerField(required=False, min_value=1, max_value=50000)
    length_cm = serializers.IntegerField(required=False, min_value=1, max_value=200)
    breadth_cm = serializers.IntegerField(required=False, min_value=1, max_value=200)
    height_cm = serializers.IntegerField(required=False, min_value=1, max_value=200)
    pickup_location = serializers.PrimaryKeyRelatedField(
        queryset=PickupLocation.objects.filter(active=True), required=False, allow_null=True, default=None
    )
    courier = serializers.ChoiceField(choices=Shipment.Courier.choices, required=False, help_text="sent by hand")
    tracking_number = serializers.CharField(required=False, max_length=80, help_text="sent by hand")
    tracking_url = serializers.URLField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        by_hand = bool(attrs.get("tracking_number"))
        if by_hand and not attrs.get("courier"):
            raise serializers.ValidationError({"courier": ["Which courier took it?"]})
        if not by_hand and not attrs.get("courier_company_id"):
            raise serializers.ValidationError(
                {"courier_company_id": ["A courier of the quote, or courier and tracking_number for one sent by hand."]}
            )
        sizes = [attrs.get(name) for name in ("length_cm", "breadth_cm", "height_cm")]
        if any(sizes) and not all(sizes):
            raise serializers.ValidationError({"length_cm": ["Give all three dimensions, or none (a flyer)."]})
        return attrs


class PickupRequestSerializer(serializers.Serializer):
    date = serializers.DateField(required=False, help_text="empty: the next possible day")


class PickupResultSerializer(serializers.Serializer):
    pickup_date = serializers.DateField(allow_null=True)


class ManifestRequestSerializer(serializers.Serializer):
    shipments = serializers.ListField(child=serializers.IntegerField(min_value=1), min_length=1, max_length=200)


class ManifestSerializer(serializers.Serializer):
    url = serializers.URLField(help_text="the carrier's PDF of the handover list")


class NdrActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=NDR_ACTIONS)
    comments = serializers.CharField(max_length=300)
    deferred_date = serializers.DateField(required=False)
    phone = serializers.RegexField(r"^[6-9]\d{9}$", required=False, help_text="a corrected number, 10 digits")
    address1 = serializers.CharField(required=False, max_length=200)
    address2 = serializers.CharField(required=False, max_length=200)


class ResolveSerializer(serializers.Serializer):
    resolution = serializers.CharField(max_length=300, help_text="what was done, or why it is dismissed")
    dismiss = serializers.BooleanField(default=False)


class PhotoSerializer(serializers.Serializer):
    photo = serializers.ImageField(help_text="the parcel on the scale, label side up; JPEG or PNG, 5 MB at most")

    def validate_photo(self, photo):
        if photo.size > 5 * 1024 * 1024:
            raise serializers.ValidationError("5 MB at most.")
        return photo
