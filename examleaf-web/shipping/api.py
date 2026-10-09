"""The shipping app's staff API, under /api/v1/shipping/ (API.md "Shipping (staff)"). Its permission is a placeholder,
StaffOnly (an active member of staff), until the staff app replaces it with its catalogued permissions. Everything
goes through shipping.services: a booking and a label are queued (Celery); the quote (3 seconds at most), a pickup, a
manifest, a cancellation and an NDR action are answered at once. A refusal of ours, or the courier's own, is a 400
(non_field_errors); a courier that cannot be reached, a 503."""

from pathlib import Path

import django_filters
from django.db import transaction
from django.http import FileResponse, Http404
from django_fsm import TransitionNotAllowed
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import exceptions, generics, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from api.schema import AutoSchema
from api.shop import AnyAccept
from api.views import DetailSerializer
from integrations.client import IntegrationError, IntegrationUnavailable
from integrations.models import IntegrationAccount
from shop.models import Order, Shipment

from . import services, tasks
from .api_serializers import (
    BookSerializer,
    CodRemittanceSerializer,
    ManifestRequestSerializer,
    ManifestSerializer,
    NdrActionSerializer,
    ParcelHistorySerializer,
    ParcelSerializer,
    PhotoSerializer,
    PickupLocationSerializer,
    PickupRequestSerializer,
    PickupResultSerializer,
    QuoteQuerySerializer,
    QuoteResultSerializer,
    ResolveSerializer,
    ShipmentChargeSerializer,
    ShipmentEventSerializer,
    ShippingExceptionSerializer,
)
from .carriers import NotSupported
from .models import CodRemittance, PickupLocation, ShipmentCharge, ShipmentDetail, ShippingException
from .permissions import StaffOnly
from .status import Status

PDF = {(200, "application/pdf"): OpenApiTypes.BINARY}
PHOTO_TYPES = {".jpg", ".jpeg", ".png", ".webp"}


class StaffSchema(AutoSchema):
    def get_tags(self):
        return ["shipping (staff)"]


class Unavailable(exceptions.APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "The courier could not be reached: try again in a few minutes."


def refused(message):
    return exceptions.ValidationError({"non_field_errors": [message]})


def courier_call(function, *args, **kwargs):
    """Run a service, its refusals as the API's errors."""
    try:
        return function(*args, **kwargs)
    except (services.ShippingError, TransitionNotAllowed) as error:
        raise refused(str(error) or "Not possible for this order now.") from error
    except NotSupported as error:
        raise refused(f"Not possible with this carrier ({error}).") from error
    except IntegrationUnavailable as error:
        raise Unavailable() from error
    except IntegrationError as error:  # the courier refused, or its credentials did not work
        raise refused(str(error)) from error


class Staff:
    permission_classes = [StaffOnly]
    schema = StaffSchema()


class ShipmentFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(field_name="detail__status", choices=Status.choices)
    carrier = django_filters.ChoiceFilter(field_name="detail__carrier", choices=ShipmentDetail.Carrier.choices)
    courier_company_id = django_filters.NumberFilter(field_name="detail__courier_company_id")
    order = django_filters.CharFilter(field_name="order__number")

    class Meta:
        model = Shipment
        fields = []


class ShipmentViewSet(Staff, mixins.CreateModelMixin, viewsets.ReadOnlyModelViewSet):
    """Parcels: the list (filters status, carrier, courier, order; search by AWB, order or our reference), one with
    its timeline, exceptions, charges and COD remittance; booking (POST) and the packing room's actions."""

    queryset = Shipment.objects.select_related("order", "detail").order_by("-pk")
    filterset_class = ShipmentFilter
    search_fields = ["tracking_number", "order__number", "detail__reference"]
    ordering_fields = ["pk", "shipped_at"]

    def get_serializer_class(self):
        return {"retrieve": ParcelHistorySerializer, "create": BookSerializer}.get(self.action, ParcelSerializer)

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action == "retrieve":
            queryset = queryset.prefetch_related("events", "exceptions__shipment__order", "charges")
        return queryset

    def courier_parcel(self):
        shipment = self.get_object()
        if getattr(shipment, "detail", None) is None:
            raise refused("This parcel was typed by hand in the admin: nothing to ask a courier.")
        return shipment

    @extend_schema(request=BookSerializer, responses={201: ParcelSerializer, 202: ParcelSerializer})
    def create(self, request, *args, **kwargs):
        """Book a parcel for a packed order: with a courier of the quote, prepared now and booked by a task (202; its
        status becomes "booked" with its AWB), or sent by hand, shipped at once (201)."""
        book = BookSerializer(data=request.data)
        book.is_valid(raise_exception=True)
        data = book.validated_data
        if data.get("tracking_number"):
            shipment = courier_call(
                services.ship_by_hand,
                data["order"],
                data["courier"],
                data["tracking_number"],
                data["tracking_url"],
                by=request.user,
            )
            return Response(ParcelSerializer(shipment).data, status=status.HTTP_201_CREATED)
        account = IntegrationAccount.enabled_for("shiprocket")
        if account is None:
            raise refused("No courier account is enabled (Integrations).")
        sizes = [data[name] for name in ("length_cm", "breadth_cm", "height_cm")] if data.get("length_cm") else None
        shipment = courier_call(
            services.prepare,
            data["order"],
            account=account,
            courier_company_id=data["courier_company_id"],
            courier_name=data["courier_name"],
            quoted_rate=data["quoted_rate"],
            weight_g=data.get("weight_g"),
            dims=sizes,
            pickup=data["pickup_location"],
        )
        courier = data["courier_company_id"]
        transaction.on_commit(lambda: tasks.book_shipment.delay(shipment.pk, courier), robust=True)
        return Response(ParcelSerializer(services.parcel(shipment)).data, status=status.HTTP_202_ACCEPTED)

    @extend_schema(methods=["GET"], responses=PDF)
    @extend_schema(methods=["POST"], request=None, responses={202: DetailSerializer})
    @action(detail=True, methods=["get", "post"], content_negotiation_class=AnyAccept)
    def label(self, request, *args, **kwargs):
        """GET: the label's PDF, kept with us (404 until fetched). POST: fetch it (a task)."""
        shipment = self.courier_parcel()
        detail = shipment.detail
        if request.method == "POST":
            if detail.status is None:
                raise refused("Not booked yet: no label.")
            transaction.on_commit(lambda: tasks.fetch_label.delay(shipment.pk), robust=True)
            return Response({"detail": "The label is on its way."}, status=status.HTTP_202_ACCEPTED)
        if not detail.label:
            raise Http404
        return FileResponse(detail.label.open("rb"), as_attachment=True, filename=f"label-{detail.reference}.pdf")

    @extend_schema(request=PickupRequestSerializer, responses=PickupResultSerializer)
    @action(detail=True, methods=["post"])
    def pickup(self, request, *args, **kwargs):
        """Ask the courier to collect the parcel (on a date, or the next possible day)."""
        asked = PickupRequestSerializer(data=request.data)
        asked.is_valid(raise_exception=True)
        day = courier_call(services.schedule_pickup, self.courier_parcel(), asked.validated_data.get("date"))
        return Response(PickupResultSerializer({"pickup_date": day}).data)

    @extend_schema(request=None, responses=ParcelSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, *args, **kwargs):
        """Cancel the booking, until the courier is out to collect it."""
        shipment = courier_call(services.cancel, self.courier_parcel(), by=request.user)
        return Response(ParcelSerializer(shipment).data)

    @extend_schema(request=NdrActionSerializer, responses=ShippingExceptionSerializer)
    @action(detail=True, methods=["post"], url_path="ndr-action")
    def ndr_action(self, request, *args, **kwargs):
        """After a failed delivery: re-attempt (a date, phone or address), fake-attempt (disputed), or return."""
        asked = NdrActionSerializer(data=request.data)
        asked.is_valid(raise_exception=True)
        fields = dict(asked.validated_data)
        action_, comments = fields.pop("action"), fields.pop("comments")
        if day := fields.get("deferred_date"):
            fields["deferred_date"] = day.isoformat()
        exception = courier_call(
            services.ndr_action, self.courier_parcel(), action_, comments, by=request.user, **fields
        )
        return Response(ShippingExceptionSerializer(exception).data)

    @extend_schema(responses=ShipmentEventSerializer(many=True))
    @action(detail=True)
    def events(self, request, *args, **kwargs):
        """The parcel's timeline, oldest first."""
        return Response(ShipmentEventSerializer(self.get_object().events.all(), many=True).data)

    @extend_schema(request={"multipart/form-data": PhotoSerializer}, responses=ParcelSerializer)
    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser])
    def photo(self, request, *args, **kwargs):
        """The parcel on the scale, label side up: the evidence for a weight dispute or a fake attempt."""
        shipment = self.courier_parcel()
        upload = PhotoSerializer(data=request.data)
        upload.is_valid(raise_exception=True)
        photo, detail = upload.validated_data["photo"], shipment.detail
        suffix = Path(photo.name).suffix.lower()
        name = f"{detail.reference or shipment.pk}{suffix if suffix in PHOTO_TYPES else '.jpg'}"
        detail.parcel_photo.save(name, photo, save=False)
        detail.change(parcel_photo=detail.parcel_photo.name)
        return Response(ParcelSerializer(services.parcel(shipment)).data)


class OrderQuoteView(Staff, generics.GenericAPIView):
    """The couriers for an order's parcel, ranked, with India Post's prices for a prepaid order."""

    serializer_class = QuoteResultSerializer
    queryset = Order.objects.all()
    lookup_field = "number"

    @extend_schema(parameters=[QuoteQuerySerializer])
    def get(self, request, *args, **kwargs):
        query = QuoteQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        result = courier_call(services.quote, self.get_object(), weight_g=query.validated_data.get("weight_g"))
        return Response(QuoteResultSerializer(result).data)


class ManifestView(Staff, generics.GenericAPIView):
    """The handover list of booked parcels (one courier account): the carrier's PDF."""

    serializer_class = ManifestRequestSerializer

    @extend_schema(responses=ManifestSerializer)
    def post(self, request, *args, **kwargs):
        asked = ManifestRequestSerializer(data=request.data)
        asked.is_valid(raise_exception=True)
        ids = set(asked.validated_data["shipments"])
        shipments = list(Shipment.objects.filter(pk__in=ids, detail__isnull=False))
        if len(shipments) != len(ids):
            raise refused("Some of these parcels do not exist or were typed by hand.")
        return Response(ManifestSerializer({"url": courier_call(services.manifest, shipments)}).data)


class ExceptionViewSet(Staff, viewsets.ReadOnlyModelViewSet):
    """What parcels need from staff, by deadline (filters kind, state, shipment); resolve or dismiss one."""

    queryset = ShippingException.objects.select_related("shipment__order")
    serializer_class = ShippingExceptionSerializer
    filterset_fields = ["kind", "state", "shipment"]
    ordering_fields = ["due_at", "created"]

    @extend_schema(request=ResolveSerializer, responses=ShippingExceptionSerializer)
    @action(detail=True, methods=["post"])
    def resolve(self, request, *args, **kwargs):
        asked = ResolveSerializer(data=request.data)
        asked.is_valid(raise_exception=True)
        exception = self.get_object()
        done = courier_call(services.resolve_exception, exception, **asked.validated_data, by=request.user)
        if not done:
            raise refused("Already resolved or dismissed.")
        return Response(ShippingExceptionSerializer(exception).data)


class CodRemittanceViewSet(Staff, viewsets.ReadOnlyModelViewSet):
    """Cash on delivery: expected, overdue, remitted, mismatched (filter state)."""

    queryset = CodRemittance.objects.select_related("shipment__order")
    serializer_class = CodRemittanceSerializer
    filterset_fields = ["state"]
    ordering_fields = ["expected_on", "created"]


class ChargeViewSet(Staff, viewsets.ReadOnlyModelViewSet):
    """What the courier account charged and gave back, line by line (filters kind, shipment)."""

    queryset = ShipmentCharge.objects.all()
    serializer_class = ShipmentChargeSerializer
    filterset_fields = ["kind", "shipment"]
    ordering_fields = ["charged_at"]


class PickupLocationViewSet(
    Staff,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Our pickup addresses by the courier's nicknames; `sync` reads them from the courier account."""

    queryset = PickupLocation.objects.all()
    serializer_class = PickupLocationSerializer

    def perform_save(self, serializer):
        with transaction.atomic():
            if serializer.validated_data.get("is_default"):
                PickupLocation.objects.exclude(pk=getattr(serializer.instance, "pk", None)).update(is_default=False)
            serializer.save()

    perform_create = perform_update = perform_save

    @extend_schema(request=None, responses=PickupLocationSerializer(many=True))
    @action(detail=False, methods=["post"])
    def sync(self, request, *args, **kwargs):
        account = IntegrationAccount.enabled_for("shiprocket")
        if account is None:
            raise refused("No courier account is enabled (Integrations).")
        places = courier_call(services.sync_pickup_locations, account)
        return Response(PickupLocationSerializer(places, many=True).data)
