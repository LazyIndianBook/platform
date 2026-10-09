"""The shipping app's staff API, under /api/v1/shipping/ (API.md "Shipping (staff)"), on the staff app's rules
(staff.api.StaffAppView: the panel's session or an API key, the permission each action names, the admin host only,
every refusal and every change in the audit log). Everything goes through shipping.services: a booking and a label
are queued (Celery); the quote (3 seconds at most), a pickup, a manifest, a cancellation and an NDR action are
answered at once. A refusal of ours, or the courier's own, is a 400 (non_field_errors); a courier that cannot be
reached, a 503."""

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
from staff import audit
from staff.api import StaffAppView
from staff.backends import scoped

from . import services, tasks
from .api_serializers import (
    BookSerializer,
    CodReconcileSerializer,
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


class Staff(StaffAppView):
    """Each view's `permissions` per action (staff.catalogue: view_parcels, book_parcel, act_on_exception, view_cod,
    reconcile_cod, manage_pickup_locations); its objects through `scoped()` with the action's permission (a PACKER's
    parcels are those of the orders to pack and on their way)."""

    schema = StaffSchema()

    def get_queryset(self):
        return scoped(super().get_queryset(), self.request.user, self.required_permission(self.request))

    def log(self, event, target, /, **details):
        audit.record(event, request=self.request, target=target, details=details)


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
    permissions = {
        **dict.fromkeys(["list", "retrieve", "events"], "staff.view_parcels"),
        **dict.fromkeys(["create", "label", "pickup", "cancel", "photo"], "staff.book_parcel"),
        "ndr_action": "staff.act_on_exception",
    }

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
            self.log("shipping.shipped_by_hand", shipment.order, shipment=shipment.pk, courier=data["courier"])
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
        self.log(
            "shipping.booked",
            shipment.order,
            shipment=shipment.pk,
            courier_company_id=courier,
            courier_name=data["courier_name"],
            weight_g=data.get("weight_g"),
        )
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
            self.log("shipping.label_requested", shipment.order, shipment=shipment.pk)
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
        shipment = self.courier_parcel()
        day = courier_call(services.schedule_pickup, shipment, asked.validated_data.get("date"))
        self.log("shipping.pickup_scheduled", shipment.order, shipment=shipment.pk, pickup_date=day)
        return Response(PickupResultSerializer({"pickup_date": day}).data)

    @extend_schema(request=None, responses=ParcelSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, *args, **kwargs):
        """Cancel the booking, until the courier is out to collect it."""
        shipment = courier_call(services.cancel, self.courier_parcel(), by=request.user)
        self.log("shipping.cancelled", shipment.order, shipment=shipment.pk)
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
        shipment = self.courier_parcel()
        exception = courier_call(services.ndr_action, shipment, action_, comments, by=request.user, **fields)
        # which details changed, never the details (a phone, an address)
        self.log("shipping.ndr_action", shipment.order, shipment=shipment.pk, action=action_, changed=sorted(fields))
        return Response(ShippingExceptionSerializer(exception).data)

    @extend_schema(responses=ShipmentEventSerializer(many=True))
    @action(detail=True, pagination_class=None, filter_backends=[])  # the whole timeline
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
        self.log("shipping.photo_added", shipment.order, shipment=shipment.pk)
        return Response(ParcelSerializer(services.parcel(shipment)).data)


class OrderQuoteView(Staff, generics.GenericAPIView):
    """The couriers for an order's parcel, ranked, with India Post's prices for a prepaid order."""

    serializer_class = QuoteResultSerializer
    queryset = Order.objects.all()
    lookup_field = "number"
    permissions = {"GET": "staff.book_parcel"}  # (a read, but a courier's answer for a booking)

    @extend_schema(parameters=[QuoteQuerySerializer])
    def get(self, request, *args, **kwargs):
        query = QuoteQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        result = courier_call(services.quote, self.get_object(), weight_g=query.validated_data.get("weight_g"))
        return Response(QuoteResultSerializer(result).data)


class ManifestView(Staff, generics.GenericAPIView):
    """The handover list of booked parcels (one courier account): the carrier's PDF."""

    serializer_class = ManifestRequestSerializer
    queryset = Shipment.objects.filter(detail__isnull=False)
    permissions = {"POST": "staff.book_parcel"}

    @extend_schema(responses=ManifestSerializer)
    def post(self, request, *args, **kwargs):
        asked = ManifestRequestSerializer(data=request.data)
        asked.is_valid(raise_exception=True)
        ids = set(asked.validated_data["shipments"])
        shipments = list(self.get_queryset().filter(pk__in=ids))
        if len(shipments) != len(ids):
            raise refused("Some of these parcels do not exist or were typed by hand.")
        url = courier_call(services.manifest, shipments)
        self.log("shipping.manifested", None, shipments=sorted(ids))
        return Response(ManifestSerializer({"url": url}).data)


class ExceptionViewSet(Staff, viewsets.ReadOnlyModelViewSet):
    """What parcels need from staff, by deadline (filters kind, state, shipment); resolve or dismiss one."""

    queryset = ShippingException.objects.select_related("shipment__order")
    serializer_class = ShippingExceptionSerializer
    filterset_fields = ["kind", "state", "shipment"]
    ordering_fields = ["due_at", "created"]
    permissions = {"list": "staff.view_parcels", "retrieve": "staff.view_parcels", "resolve": "staff.act_on_exception"}

    @extend_schema(request=ResolveSerializer, responses=ShippingExceptionSerializer)
    @action(detail=True, methods=["post"])
    def resolve(self, request, *args, **kwargs):
        asked = ResolveSerializer(data=request.data)
        asked.is_valid(raise_exception=True)
        exception = self.get_object()
        done = courier_call(services.resolve_exception, exception, **asked.validated_data, by=request.user)
        if not done:
            raise refused("Already resolved or dismissed.")
        verb = "dismissed" if asked.validated_data["dismiss"] else "resolved"
        self.log(f"shipping.exception_{verb}", exception.shipment.order, exception=exception.pk, kind=exception.kind)
        return Response(ShippingExceptionSerializer(exception).data)


class CodRemittanceViewSet(Staff, viewsets.ReadOnlyModelViewSet):
    """Cash on delivery: expected, overdue, remitted, mismatched (filter state); reconcile one with the bank."""

    queryset = CodRemittance.objects.select_related("shipment__order")
    serializer_class = CodRemittanceSerializer
    filterset_fields = ["state"]
    ordering_fields = ["expected_on", "created"]
    permissions = {"list": "staff.view_cod", "retrieve": "staff.view_cod", "reconcile": "staff.reconcile_cod"}

    @extend_schema(request=CodReconcileSerializer, responses=CodRemittanceSerializer)
    @action(detail=True, methods=["post"])
    def reconcile(self, request, *args, **kwargs):
        """The bank's credit for this parcel's cash, matched by its UTR: remitted at the amount expected, otherwise a
        mismatch (and its exception)."""
        asked = CodReconcileSerializer(data=request.data)
        asked.is_valid(raise_exception=True)
        remittance = courier_call(services.reconcile_cod, self.get_object(), **asked.validated_data)
        self.log(  # a money event (the 8 years' chain)
            "payment.cod_reconciled",
            remittance.shipment.order,
            remittance=remittance.pk,
            utr=remittance.utr,
            amount=remittance.remitted_amount,
            state=remittance.state,
        )
        return Response(CodRemittanceSerializer(remittance).data)


class ChargeViewSet(Staff, viewsets.ReadOnlyModelViewSet):
    """What the courier account charged and gave back, line by line (filters kind, shipment)."""

    queryset = ShipmentCharge.objects.all()
    serializer_class = ShipmentChargeSerializer
    filterset_fields = ["kind", "shipment"]
    ordering_fields = ["charged_at"]
    permissions = {"list": "staff.view_cod", "retrieve": "staff.view_cod"}


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
    permissions = {
        **dict.fromkeys(["list", "retrieve"], "staff.view_parcels"),
        **dict.fromkeys(["create", "update", "partial_update", "sync"], "staff.manage_pickup_locations"),
    }

    def perform_save(self, serializer):
        with transaction.atomic():
            if serializer.validated_data.get("is_default"):
                PickupLocation.objects.exclude(pk=getattr(serializer.instance, "pk", None)).update(is_default=False)
            place = serializer.save()
            self.log("shipping.pickup_location_saved", place, fields=sorted(serializer.validated_data))

    perform_create = perform_update = perform_save

    @extend_schema(request=None, responses=PickupLocationSerializer(many=True))
    @action(detail=False, methods=["post"], pagination_class=None, filter_backends=[])
    def sync(self, request, *args, **kwargs):
        account = IntegrationAccount.enabled_for("shiprocket")
        if account is None:
            raise refused("No courier account is enabled (Integrations).")
        places = courier_call(services.sync_pickup_locations, account)
        self.log("shipping.pickup_locations_synced", None, places=len(places))
        return Response(PickupLocationSerializer(places, many=True).data)
