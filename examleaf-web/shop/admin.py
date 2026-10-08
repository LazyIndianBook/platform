from django import forms
from django.contrib import admin, messages
from django.core.files.uploadedfile import UploadedFile
from django.forms import formset_factory
from django.shortcuts import render
from django.urls import reverse
from django.utils.html import format_html, format_html_join
from django_fsm import TransitionNotAllowed
from import_export import fields, resources
from import_export.admin import ExportMixin
from import_export.formats.base_formats import CSV, XLSX
from localflavor.in_.in_states import STATE_CHOICES
from simple_history.admin import SimpleHistoryAdmin

from . import services
from .forms import RefundForm, ShipForm
from .models import (
    BundleItem,
    Coupon,
    CreditNote,
    Invoice,
    Order,
    OrderItem,
    Payment,
    Product,
    ProductImage,
    Refund,
    Shipment,
    ShippingRate,
)

admin.site.index_template = "shop/admin/index.html"  # the ops dashboard with the shop's numbers above it


class ReadOnlyInline(admin.TabularInline):
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


MAX_PICTURE_BYTES = 2 * 1024 * 1024


def small_picture(upload):
    """Covers and pictures load on every phone: refuse a new upload over 2 MB (Caddy stops 10 MB bodies anyway)."""
    if isinstance(upload, UploadedFile) and upload.size > MAX_PICTURE_BYTES:
        raise forms.ValidationError(
            f"This picture is {upload.size / 1048576:.1f} MB. Make it smaller than 2 MB first: it loads on every phone."
        )
    return upload


class ProductImageForm(forms.ModelForm):
    class Meta:
        model = ProductImage
        fields = ["image", "alt", "position"]

    def clean_image(self):
        return small_picture(self.cleaned_data["image"])


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    form = ProductImageForm
    extra = 0


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [  # as in the admin's fieldsets
            *["title", "slug", "kind", "is_active", "subject", "book", "mrp", "price", "stock", "gst_rate"],
            *["hsn_code", "cover", "description", "isbn", "pages", "weight_grams", "seo_title", "seo_description"],
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # the page carries the stock it was opened with, so that saving it can tell whether stock was edited
        self.fields["stock"].show_hidden_initial = True

    def clean_cover(self):
        return small_picture(self.cleaned_data["cover"])


class BundleItemInline(admin.TabularInline):
    model = BundleItem
    fk_name = "bundle"
    extra = 0
    verbose_name = verbose_name_plural = "books in the bundle (bundles only)"


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    form = ProductForm
    list_display = ["title", "kind", "subject", "price", "mrp", "stock", "is_active"]
    list_filter = ["is_active", "kind", "subject"]
    search_fields = ["title", "isbn", "slug"]
    prepopulated_fields = {"slug": ["title"]}
    list_select_related = ["subject__board", "subject__class_level"]
    inlines = [BundleItemInline, ProductImageInline]
    fieldsets = [
        (None, {"fields": ["title", "slug", "kind", "is_active", "subject", "book"]}),
        ("Price and stock", {"fields": ["mrp", "price", "stock", "gst_rate", "hsn_code"]}),
        ("The book", {"fields": ["cover", "description", "isbn", "pages", "weight_grams"]}),
        ("Search engines", {"fields": ["seo_title", "seo_description"], "classes": ["collapse"]}),
    ]

    def save_model(self, request, obj, form, change):
        if change and "stock" not in form.changed_data:
            # The page may have been open while customers bought: saving it must not put its old copy count back.
            obj.stock = Product.objects.values_list("stock", flat=True).get(pk=obj.pk)
        super().save_model(request, obj, form, change)


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ["code", "kind", "value", "min_order", "valid_from", "valid_until", "uses", "max_uses", "is_active"]
    list_filter = ["is_active", "kind"]
    search_fields = ["code"]

    @admin.display(description="used")
    def uses(self, coupon):
        return coupon.orders.counted().count()


class ShippingRateForm(forms.ModelForm):
    states = forms.MultipleChoiceField(
        choices=sorted(STATE_CHOICES, key=lambda choice: choice[1]),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        help_text="None ticked: every state that no other active rate names.",
    )

    class Meta:
        model = ShippingRate
        fields = ["name", "states", "fee", "free_above", "is_active"]


@admin.register(ShippingRate)
class ShippingRateAdmin(admin.ModelAdmin):
    form = ShippingRateForm
    list_display = ["name", "fee", "free_above", "state_list", "is_active"]

    @admin.display(description="states")
    def state_list(self, rate):
        return ", ".join(rate.states) or "all others"


class OrderItemInline(ReadOnlyInline):
    model = OrderItem
    fields = readonly_fields = ["title", "hsn_code", "gst_rate", "mrp", "unit_price", "quantity"]


class PaymentInline(ReadOnlyInline):
    model = Payment
    fields = readonly_fields = ["method", "amount", "status", "razorpay_order_id", "razorpay_payment_id", "error"]


class ShipmentInline(admin.TabularInline):  # created by "mark shipped"; editable to correct a tracking number
    model = Shipment
    extra = 0
    can_delete = False
    fields = ["courier", "tracking_number", "tracking_url", "shipped_at", "delivered_at"]

    def has_add_permission(self, request, obj=None):
        return False


class RefundInline(ReadOnlyInline):
    model = Refund
    fields = readonly_fields = ["amount", "status", "reason", "razorpay_refund_id", "error", "created", "created_by"]


ADDRESS_COLUMNS = ["name", "phone", "city", "district", "state", "pin"]


def address_column(key):
    return fields.Field(column_name=key, dehydrate_method=lambda order: order.shipping_address.get(key, ""))


class OrderResource(resources.ModelResource):  # CSV / XLSX export: one row per order, the address in columns
    books = fields.Field(column_name="books")
    name, phone, city, district, state, pin = (address_column(key) for key in ADDRESS_COLUMNS)
    subtotal = fields.Field(attribute="subtotal__amount", column_name="books value")
    discount = fields.Field(attribute="discount__amount", column_name="discount")
    shipping_fee = fields.Field(attribute="shipping_fee__amount", column_name="shipping")
    total = fields.Field(attribute="total__amount", column_name="total")
    tracking = fields.Field(column_name="tracking")

    class Meta:
        model = Order
        fields = [
            *["number", "created", "placed_at", "status", "payment_method", "email", *ADDRESS_COLUMNS, "books"],
            *["subtotal", "discount", "shipping_fee", "total", "coupon_code", "tracking"],
        ]

    def dehydrate_books(self, order):
        return "; ".join(f"{item.quantity} x {item.title}" for item in order.items.all())

    def dehydrate_tracking(self, order):
        return "; ".join(f"{s.courier} {s.tracking_number}" for s in order.shipments.all())

    def get_export_queryset(self, request):
        return super().get_export_queryset(request).prefetch_related("items", "shipments")


@admin.register(Order)
class OrderAdmin(ExportMixin, SimpleHistoryAdmin):
    resource_classes = [OrderResource]
    export_formats = [CSV, XLSX]
    list_display = ["number", "created", "customer", "total", "payment_method", "status", "placed_at"]
    list_filter = ["status", "payment_method", "placed_at", "created"]
    search_fields = [
        "number",
        "email",
        "shipping_address__name",
        "shipping_address__phone",
        "shipments__tracking_number",
    ]
    date_hierarchy = "created"
    readonly_fields = [
        *["number", "status", "user", "email", "delivery_address", "subtotal", "discount", "shipping_fee", "total"],
        *["coupon_code", "payment_method", "placed_at", "invoice_link", "created", "modified"],
    ]
    fields = readonly_fields
    inlines = [OrderItemInline, PaymentInline, ShipmentInline, RefundInline]
    actions = ["mark_packed", "mark_shipped", "mark_delivered", "cancel", "refund"]

    def has_add_permission(self, request):  # orders come from the checkout
        return False

    def has_delete_permission(self, request, obj=None):  # tax records
        return False

    def has_refund_permission(self, request):
        return request.user.has_perm("shop.add_refund")

    @admin.display(description="customer")
    def customer(self, order):
        return f"{order.shipping_address.get('name', '')} <{order.email}>"

    @admin.display(description="deliver to")
    def delivery_address(self, order):
        return format_html_join("", "{}<br>", ((line,) for line in order.address_lines))

    @admin.display(description="invoice and credit notes")
    def invoice_link(self, order):
        invoice = getattr(order, "invoice", None)
        if not (invoice and invoice.pdf):
            return "—"
        notes = invoice.credit_notes.exclude(pdf="")
        links = [(reverse("shop:invoice", args=[order.number]), invoice.number)]
        links += [(reverse("shop:credit_note", args=[order.number, note.pk]), note.number) for note in notes]
        return format_html_join(" · ", '<a href="{}">{}</a>', links)

    def _each(self, request, queryset, step, done):
        ok, refused = 0, []
        for order in queryset:
            try:
                step(order)
                ok += 1
            except TransitionNotAllowed:
                refused.append(f"{order} ({order.get_status_display()})")
        if ok:
            self.message_user(request, f"{done}: {ok} order(s).", messages.SUCCESS)
        if refused:
            self.message_user(request, f"Not possible for {', '.join(refused)}.", messages.WARNING)

    @admin.action(description="Mark packed", permissions=["change"])
    def mark_packed(self, request, queryset):
        self._each(request, queryset, services.pack_order, "Packed")

    @admin.action(description="Mark delivered", permissions=["change"])
    def mark_delivered(self, request, queryset):
        self._each(request, queryset, services.deliver_order, "Delivered (customer emailed)")

    @admin.action(description="Cancel (stock back; online payments refunded)", permissions=["change"])
    def cancel(self, request, queryset):
        self._each(
            request,
            queryset,
            lambda o: services.cancel_order(o, "Cancelled by ExamLeaf.", by=request.user),
            "Cancelled (customer emailed)",
        )

    @admin.action(description="Mark shipped (courier and tracking number)", permissions=["change"])
    def mark_shipped(self, request, queryset):
        orders = list(queryset.filter(status=Order.Status.PACKED))
        if not orders:
            self.message_user(request, "Only packed orders can be shipped.", messages.WARNING)
            return None
        formset_class = formset_factory(ShipForm, extra=0)
        if "apply" in request.POST:
            formset = formset_class(request.POST, prefix="ship")
            if formset.is_valid():
                by_pk = {order.pk: order for order in orders}
                rows = [row for row in formset.cleaned_data if row.get("order") in by_pk]
                self._each(
                    request,
                    rows,
                    lambda row: services.ship_order(
                        by_pk[row["order"]], row["courier"], row["tracking_number"], row["tracking_url"]
                    ),
                    "Shipped (customer emailed the tracking number)",
                )
                return None
        else:
            formset = formset_class(initial=[{"order": order.pk} for order in orders], prefix="ship")
        return self._form_page(
            request, queryset, "mark_shipped", "Mark shipped", zip(formset.forms, orders, strict=False), formset
        )

    @admin.action(description="Refund in full through Razorpay (cancels what is not shipped)", permissions=["refund"])
    def refund(self, request, queryset):
        form = RefundForm(request.POST if "apply" in request.POST else None)
        if form.is_valid():
            reason, started, nothing = form.cleaned_data["reason"], [], []
            for order in queryset:
                try:
                    refund = services.refund_order(order, reason, by=request.user, amount=form.cleaned_data["amount"])
                except TransitionNotAllowed:
                    refund = None
                (started if refund else nothing).append(str(order))
            if started:
                self.message_user(request, f"Refund requested: {', '.join(started)}.", messages.SUCCESS)
            if nothing:
                self.message_user(
                    request,
                    f"Nothing refunded for {', '.join(nothing)} (not paid online, or a refund is under way; "
                    "cash on delivery is refunded by bank transfer).",
                    messages.WARNING,
                )
            return None
        return self._form_page(request, queryset, "refund", "Refund in full", [(form, None)], None)

    def _form_page(self, request, queryset, action, title, rows, formset):
        context = {
            **self.admin_site.each_context(request),
            "title": title,
            "opts": self.model._meta,
            "queryset": queryset,
            "action": action,
            "rows": list(rows),
            "formset": formset,
        }
        return render(request, "shop/admin/action_form.html", context)


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Payment)
class PaymentAdmin(ReadOnlyAdmin):
    list_display = ["order", "method", "amount", "status", "razorpay_order_id", "razorpay_payment_id", "created"]
    list_filter = ["status", "method", "created"]
    search_fields = ["order__number", "razorpay_order_id", "razorpay_payment_id"]
    list_select_related = ["order"]


@admin.register(Refund)
class RefundAdmin(ReadOnlyAdmin):
    list_display = ["order", "amount", "status", "reason", "razorpay_refund_id", "created", "processed_at"]
    list_filter = ["status", "created"]
    search_fields = ["order__number", "razorpay_refund_id"]
    list_select_related = ["order"]


@admin.register(Invoice)
class InvoiceAdmin(ReadOnlyAdmin):
    list_display = ["number", "order", "created", "pdf_link"]
    search_fields = ["number", "order__number"]
    list_select_related = ["order"]

    @admin.display(description="PDF")
    def pdf_link(self, invoice):
        if not invoice.pdf:
            return "being made"
        return format_html('<a href="{}">download</a>', reverse("shop:invoice", args=[invoice.order.number]))


@admin.register(CreditNote)
class CreditNoteAdmin(ReadOnlyAdmin):
    list_display = ["number", "invoice", "refund_amount", "created", "pdf_link"]
    search_fields = ["number", "invoice__number", "invoice__order__number"]
    list_select_related = ["invoice__order", "refund"]

    @admin.display(description="amount")
    def refund_amount(self, note):
        return note.refund.amount

    @admin.display(description="PDF")
    def pdf_link(self, note):
        if not note.pdf:
            return "being made"
        url = reverse("shop:credit_note", args=[note.invoice.order.number, note.pk])
        return format_html('<a href="{}">download</a>', url)
