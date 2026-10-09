"""Parcels and their money in the admin, read-mostly. The shop's shipments get a list of their own (filters by
status, carrier and courier) with their courier side, timeline, exceptions, charges and COD remittance as inlines,
and actions to read the tracking now, fetch labels and cancel bookings; the parcel's photograph is the one thing
uploaded here. Exceptions are resolved or dismissed with what was done; charges, COD remittances and the PIN survey
are records; the pickup locations and India Post's tariff are edited."""

from collections import defaultdict

from django import forms
from django.contrib import admin, messages
from django.db import transaction
from django.urls import reverse
from django.utils.html import format_html

from integrations.admin import ReadOnlyAdmin, action_page
from integrations.client import IntegrationError
from shop.models import Shipment

from . import services, tasks
from .carriers import carrier_for
from .models import (
    CodRemittance,
    PickupLocation,
    PinServiceability,
    PostalTariff,
    ShipmentCharge,
    ShipmentDetail,
    ShipmentEvent,
    ShippingException,
)


class ReadOnlyInline(admin.TabularInline):
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class DetailInline(admin.StackedInline):
    model = ShipmentDetail
    can_delete = False
    extra = 0
    max_num = 1
    fields = [
        *["carrier", "account", "status", "reference", "external_order_id", "external_shipment_id"],
        *["courier_company_id", "courier_name", "weight_g", "charged_weight_g", "quoted_rate", "cod_amount"],
        *[
            "declared_value",
            "pickup_location",
            "pickup_date",
            "manifested_at",
            "last_event_at",
            "label",
            "parcel_photo",
        ],
    ]
    readonly_fields = [name for name in fields if name != "parcel_photo"]  # the photograph: uploaded at packing

    def has_add_permission(self, request, obj=None):
        return False


class EventInline(ReadOnlyInline):
    model = ShipmentEvent
    fields = readonly_fields = ["occurred_at", "source", "carrier_code", "carrier_label", "status", "location"]
    verbose_name_plural = "timeline"


class ExceptionInline(ReadOnlyInline):
    model = ShippingException
    fields = readonly_fields = ["kind", "due_at", "state", "resolution", "resolved_by"]


class ChargeInline(ReadOnlyInline):
    model = ShipmentCharge
    fields = readonly_fields = ["charged_at", "kind", "amount", "charged_weight_g", "description"]


class CodInline(ReadOnlyInline):
    model = CodRemittance
    fields = readonly_fields = ["expected_amount", "expected_on", "state", "remitted_amount", "utr", "remitted_at"]


@admin.register(Shipment)
class ParcelAdmin(admin.ModelAdmin):
    list_display = ["__str__", "order_link", "parcel_status", "courier_name", "last_event_at", "shipped_at"]
    list_filter = ["detail__status", "detail__carrier", "detail__courier_name", "courier"]
    search_fields = ["tracking_number", "order__number", "detail__reference"]
    list_select_related = ["order", "detail"]
    fields = readonly_fields = ["order", "courier", "tracking_number", "tracking_url", "shipped_at", "delivered_at"]
    inlines = [DetailInline, EventInline, ExceptionInline, ChargeInline, CodInline]
    actions = ["read_tracking", "fetch_labels", "cancel_bookings"]

    def has_add_permission(self, request):  # parcels are booked (Shipping API) or marked shipped (Orders)
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="order", ordering="order__number")
    def order_link(self, shipment):
        url = reverse("admin:shop_order_change", args=[shipment.order_id])
        return format_html('<a href="{}">{}</a>', url, shipment.order)

    @admin.display(description="status", ordering="detail__status")
    def parcel_status(self, shipment):
        detail = getattr(shipment, "detail", None)
        return detail.get_status_display() if detail and detail.status else ("typed by hand" if not detail else "—")

    @admin.display(description="courier", ordering="detail__courier_name")
    def courier_name(self, shipment):
        detail = getattr(shipment, "detail", None)
        return (detail.courier_name if detail else "") or shipment.get_courier_display()

    @admin.display(description="last scan", ordering="detail__last_event_at")
    def last_event_at(self, shipment):
        detail = getattr(shipment, "detail", None)
        return detail.last_event_at if detail else None

    @admin.action(description="Read the tracking now", permissions=["change"])
    def read_tracking(self, request, queryset):
        by_account = defaultdict(list)
        for shipment in queryset.filter(detail__account__isnull=False).exclude(tracking_number=""):
            by_account[shipment.detail.account].append(shipment)
        read = 0
        for account, shipments in by_account.items():
            try:
                answers = carrier_for(account).track([shipment.tracking_number for shipment in shipments])
            except IntegrationError as error:
                self.message_user(request, f"{account}: {error}", messages.ERROR)
                continue
            for shipment in shipments:
                services.apply_events(shipment, answers.get(shipment.tracking_number, []), ShipmentEvent.Source.POLL)
                read += 1
        self.message_user(request, f"Tracking read for {read} parcel(s).")

    @admin.action(description="Fetch the labels", permissions=["change"])
    def fetch_labels(self, request, queryset):
        booked = list(queryset.filter(detail__status__isnull=False, detail__label=""))
        for shipment in booked:
            transaction.on_commit(lambda pk=shipment.pk: tasks.fetch_label.delay(pk), robust=True)
        self.message_user(request, f"Labels on their way for {len(booked)} parcel(s).")

    @admin.action(description="Cancel the bookings (before pickup)", permissions=["change"])
    def cancel_bookings(self, request, queryset):
        for shipment in queryset.filter(detail__isnull=False):
            try:
                services.cancel(shipment, by=request.user)
                self.message_user(request, f"Cancelled: {shipment}.")
            except (services.ShippingError, IntegrationError) as error:
                self.message_user(request, f"{shipment}: {error}", messages.WARNING)


class ResolveForm(forms.Form):
    resolution = forms.CharField(max_length=300, help_text="What was done (or why it is dismissed).")


@admin.register(ShippingException)
class ShippingExceptionAdmin(ReadOnlyAdmin):
    list_display = ["kind", "shipment", "due_at", "state", "resolution"]
    list_filter = ["state", "kind"]
    search_fields = ["shipment__tracking_number", "shipment__order__number", "reference"]
    list_select_related = ["shipment"]
    actions = ["resolve", "dismiss"]

    def has_resolve_permission(self, request):
        return request.user.has_perm("shipping.change_shippingexception")

    def _close(self, request, queryset, dismiss):
        form = ResolveForm(request.POST if "apply" in request.POST else None)
        if form.is_valid():
            text = form.cleaned_data["resolution"]
            done = [e for e in queryset if services.resolve_exception(e, text, by=request.user, dismiss=dismiss)]
            self.message_user(request, f"{'Dismissed' if dismiss else 'Resolved'}: {len(done)} exception(s).")
            return None
        action, title = ("dismiss", "Dismiss exceptions") if dismiss else ("resolve", "Resolve exceptions")
        return action_page(self, request, queryset, action, title, form)

    @admin.action(description="Resolve (say what was done)", permissions=["resolve"])
    def resolve(self, request, queryset):
        return self._close(request, queryset, dismiss=False)

    @admin.action(description="Dismiss (say why)", permissions=["resolve"])
    def dismiss(self, request, queryset):
        return self._close(request, queryset, dismiss=True)


@admin.register(ShipmentCharge)
class ShipmentChargeAdmin(ReadOnlyAdmin):
    list_display = ["charged_at", "kind", "amount", "awb", "shipment", "charged_weight_g", "description"]
    list_filter = ["kind", "account"]
    search_fields = ["awb", "statement_line_id", "description"]
    date_hierarchy = "charged_at"


@admin.register(CodRemittance)
class CodRemittanceAdmin(ReadOnlyAdmin):
    list_display = ["shipment", "expected_amount", "expected_on", "state", "remitted_amount", "utr", "remitted_at"]
    list_filter = ["state"]
    search_fields = ["utr", "shipment__tracking_number", "shipment__order__number"]


@admin.register(PickupLocation)
class PickupLocationAdmin(admin.ModelAdmin):
    list_display = ["nickname", "city", "pin_code", "is_default", "active"]
    search_fields = ["nickname", "city", "pin_code"]


@admin.register(PinServiceability)
class PinServiceabilityAdmin(ReadOnlyAdmin):
    list_display = ["pin", "courier_name", "cod", "prepaid", "rate", "etd_days", "surveyed_at"]
    list_filter = ["cod", "prepaid", "courier_name"]
    search_fields = ["pin"]


@admin.register(PostalTariff)
class PostalTariffAdmin(admin.ModelAdmin):
    list_display = ["service", "weight_to_g", "price", "effective_from", "note"]
    list_filter = ["service", "effective_from"]
    search_fields = ["note"]
