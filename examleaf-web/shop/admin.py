from collections import Counter

from allauth.account.models import EmailAddress
from django import forms
from django.apps import apps
from django.contrib import admin, messages
from django.contrib.admin.helpers import ActionForm
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.db.models import Q
from django.forms import formset_factory
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe
from django.utils.text import Truncator
from django_fsm import TransitionNotAllowed
from djmoney.money import Money
from import_export import fields, resources, widgets
from import_export.admin import ExportActionMixin, ImportMixin
from import_export.formats.base_formats import CSV, XLSX
from localflavor.in_.in_states import STATE_CHOICES
from simple_history.admin import SimpleHistoryAdmin
from treebeard.admin import TreeAdmin
from treebeard.forms import movenodeform_factory

from ops.admin import LoggedExportMixin

from . import payments, services
from .cart import Line
from .forms import AddressForm, OfflinePaymentForm, RefundForm, ShipForm, StaffOrderForm, StaffOrderLineForm
from .models import (
    Attribute,
    AttributeValue,
    BundleItem,
    Category,
    Collection,
    CollectionItem,
    Coupon,
    CreditNote,
    Invoice,
    Offer,
    Order,
    OrderDiscount,
    OrderItem,
    OrderNote,
    Payment,
    Product,
    ProductImage,
    ProductType,
    QuoteRequest,
    Refund,
    Review,
    Shipment,
    ShippingRate,
    SlugHistory,
    StockAlert,
)
from .views import pdf_response

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
            *["product_type", "categories", "related"],
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # the page carries the stock it was opened with, so that saving it can tell whether stock was edited
        if "stock" in self.fields:  # a view-only user's page has no form fields
            self.fields["stock"].show_hidden_initial = True

    def clean_cover(self):
        return small_picture(self.cleaned_data["cover"])


class RupeesWidget(widgets.DecimalWidget):
    """A money field as a plain number of rupees (INR) in the file."""

    def render(self, value, obj=None, **kwargs):
        return super().render(value.amount if isinstance(value, Money) else value, obj, **kwargs)


class ProductResource(resources.ModelResource):
    """Products in a spreadsheet (CSV, XLSX), matched by slug: export, change prices or texts, import (ADMIN; checked
    as the form checks them). Stock is exported but never imported: use "Set stock", sales go on meanwhile."""

    mrp = fields.Field(attribute="mrp", column_name="mrp", widget=RupeesWidget())
    price = fields.Field(attribute="price", column_name="price", widget=RupeesWidget())
    stock = fields.Field(attribute="stock", column_name="stock", readonly=True)
    book = fields.Field(attribute="book", column_name="book", widget=widgets.ForeignKeyWidget("content.Book", "slug"))
    product_type = fields.Field(
        attribute="product_type", column_name="product_type", widget=widgets.ForeignKeyWidget(ProductType, "name")
    )
    categories = fields.Field(
        attribute="categories", column_name="categories", widget=widgets.ManyToManyWidget(Category, "|", "slug")
    )

    class Meta:
        model = Product
        import_id_fields = ["slug"]
        clean_model_instances = True
        fields = [
            *["slug", "title", "kind", "is_active", "subject", "book", "mrp", "price", "stock", "gst_rate"],
            *["hsn_code", "isbn", "pages", "weight_grams", "description", "seo_title", "seo_description"],
            *["product_type", "categories"],
        ]


class CategoryResource(resources.ModelResource):
    """The category tree in a spreadsheet, a parent before its children (`parent`: its slug, empty at the top). An
    import adds new categories where their parent says and updates names and descriptions; it moves none (drag
    them in the admin)."""

    parent = fields.Field(column_name="parent", readonly=True)

    class Meta:
        model = Category
        import_id_fields = ["slug"]
        fields = ["slug", "name", "description", "parent"]

    def validate_instance(self, instance, import_validation_errors=None, validate_unique=True):
        """The model's own checks of what a row sets (a slug with a space or a slash would break the shop's links:
        I4); the tree's fields are set when the row's category is placed (do_instance_save)."""
        errors = dict(import_validation_errors or {})
        try:
            instance.full_clean(exclude=[*errors, "path", "depth", "numchild"], validate_unique=validate_unique)
        except ValidationError as error:
            errors = error.update_error_dict(errors)
        if errors:
            raise ValidationError(errors)

    def get_export_queryset(self, request):
        return Category.objects.order_by("path")

    def dehydrate_parent(self, category):
        parent = Category.objects.get_parent(category)
        return parent.slug if parent else ""

    def before_save_instance(self, instance, row, **kwargs):
        self.parent_slug = row.get("parent") or ""

    def do_instance_save(self, instance, is_create):
        if not is_create:
            return super().do_instance_save(instance, is_create)
        if not self.parent_slug:
            return Category.objects.add_root(instance=instance)
        if parent := Category.objects.filter(slug=self.parent_slug).first():
            return Category.objects.add_child(parent, instance=instance)
        raise ValueError(f"No category {self.parent_slug} to put it under: add that one first (an earlier row).")


class ProductActionForm(ActionForm):
    stock = forms.IntegerField(label="Copies (for “Set stock”)", required=False, min_value=0)


class BundleItemInline(admin.TabularInline):
    model = BundleItem
    fk_name = "bundle"
    extra = 0
    verbose_name = verbose_name_plural = "books in the bundle (bundles only)"


class AttributeValueInline(admin.TabularInline):
    model = AttributeValue
    extra = 0
    verbose_name_plural = "attributes (those of its product type)"


class SlugHistoryInline(ReadOnlyInline):
    model = SlugHistory
    fields = readonly_fields = ["slug", "created"]
    verbose_name_plural = "earlier addresses (they redirect here)"


@admin.register(Product)
class ProductAdmin(ImportMixin, ExportActionMixin, LoggedExportMixin, admin.ModelAdmin):
    """Products; import and export (ADMIN: shop.import_product, shop.export_product, logged), bulk actions."""

    resource_classes = [ProductResource]
    import_formats = export_formats = [CSV, XLSX]
    action_form = ProductActionForm
    actions = ["publish", "unpublish", "set_stock"]
    form = ProductForm
    list_display = ["title", "kind", "subject", "price", "mrp", "stock", "is_active"]
    list_filter = ["is_active", "kind", "subject", "product_type", "categories"]
    search_fields = ["title", "isbn", "slug"]
    prepopulated_fields = {"slug": ["title"]}
    list_select_related = ["subject__board", "subject__class_level"]
    filter_horizontal = ["categories", "related"]
    inlines = [BundleItemInline, AttributeValueInline, ProductImageInline, SlugHistoryInline]
    fieldsets = [
        (None, {"fields": ["title", "slug", "kind", "is_active", "subject", "book"]}),
        ("Price and stock", {"fields": ["mrp", "price", "stock", "gst_rate", "hsn_code"]}),
        ("The book", {"fields": ["cover", "description", "isbn", "pages", "weight_grams"]}),
        ("Shelves, type and related products", {"fields": ["categories", "product_type", "related"]}),
        ("Search engines", {"fields": ["seo_title", "seo_description"], "classes": ["collapse"]}),
    ]

    @admin.action(description="Put on sale", permissions=["change"])
    def publish(self, request, queryset):
        self.message_user(request, f"{queryset.update(is_active=True)} product(s) on sale.", messages.SUCCESS)

    @admin.action(description="Take off sale", permissions=["change"])
    def unpublish(self, request, queryset):
        self.message_user(request, f"{queryset.update(is_active=False)} product(s) off sale.", messages.SUCCESS)

    @admin.action(description="Set stock to the copies typed beside the action", permissions=["change"])
    def set_stock(self, request, queryset):
        copies = request.POST.get("stock", "")
        if not copies.isdigit():
            self.message_user(request, "Type the number of copies in hand beside the action first.", messages.ERROR)
            return
        books = queryset.exclude(kind__in=[Product.Kind.BUNDLE, Product.Kind.DIGITAL])  # no copies of their own
        self.message_user(request, f"Stock set to {copies} for {books.update(stock=int(copies))} book(s).")

    def save_model(self, request, obj, form, change):
        if change and "stock" not in form.changed_data:
            # The page may have been open while customers bought: saving it must not put its old copy count back.
            obj.stock = Product.objects.values_list("stock", flat=True).get(pk=obj.pk)
        super().save_model(request, obj, form, change)

    def change_view(self, request, object_id, form_url="", extra_context=None):
        """A note while the worker is still making the pictures' AVIF and WebP sizes (django-pictures: the files it
        will write are known, so a missing one means not done yet)."""
        product = self.get_object(request, object_id) if request.method == "GET" else None
        if product and not pictures_ready(product):
            messages.info(
                request,
                "The pictures' smaller sizes are still being made: the shop shows the uploaded files until they are "
                "ready, in a minute or two. If this note stays after a reload, save the product again.",
            )
        return super().change_view(request, object_id, form_url, extra_context)


def pictures_ready(product):
    """Whether every AVIF and WebP size of the product's cover and other pictures exists in its storage."""
    files = [product.cover, *(picture.image for picture in product.images.all())]
    return all(file.storage.exists(size.name) for file in files if file for size in file.get_picture_files_list())


@admin.register(Category)
class CategoryAdmin(ImportMixin, LoggedExportMixin, TreeAdmin):
    """The shop's shelves as a tree: drag a row to move it (with its sub-categories), or set its place in the form.
    Import and export: ADMIN (shop.import_category, shop.export_category)."""

    resource_classes = [CategoryResource]
    import_formats = export_formats = [CSV, XLSX]
    form = movenodeform_factory(Category)
    list_display = ["name", "slug", "product_count"]
    search_fields = ["name", "slug"]
    prepopulated_fields = {"slug": ["name"]}

    @admin.display(description="products")
    def product_count(self, category):
        return category.products.count()


class CollectionItemInline(admin.TabularInline):
    model = CollectionItem
    extra = 0
    verbose_name_plural = "products (in the order of their position)"


@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "position", "is_active"]
    list_editable = ["position", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["name", "slug", "items__product__title"]
    prepopulated_fields = {"slug": ["name"]}
    inlines = [CollectionItemInline]


class AttributeInline(admin.TabularInline):
    model = Attribute
    extra = 0
    prepopulated_fields = {"code": ["name"]}


@admin.register(ProductType)
class ProductTypeAdmin(admin.ModelAdmin):
    """What a kind of product has to say about itself (a printed book: edition year, language…): each product of the
    type gets these attributes on its page (Products → attributes) and in the API's filters."""

    list_display = ["name", "attribute_list"]
    search_fields = ["name", "attributes__name", "attributes__code"]
    inlines = [AttributeInline]

    @admin.display(description="attributes")
    def attribute_list(self, product_type):
        return ", ".join(attribute.name for attribute in product_type.attributes.all())

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("attributes")


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ["code", "kind", "value", "min_order", "valid_from", "valid_until", "uses", "max_uses", "is_active"]
    list_filter = ["is_active", "kind"]
    search_fields = ["code"]

    @admin.display(description="used")
    def uses(self, coupon):
        return coupon.orders.counted().count()


@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    """Automatic discounts, no code needed (RUNBOOK.md "Offers"); the cart applies them after the coupon."""

    list_display = ["name", "kind", "value", "scope", "valid_from", "valid_until", "uses", "max_uses", "is_active"]
    list_filter = ["is_active", "scope", "kind", "combinable", "valid_from"]
    search_fields = ["name", "products__title", "categories__name", "collections__name"]
    filter_horizontal = ["products", "categories", "collections"]
    fieldsets = [
        (None, {"fields": ["name", "is_active", "kind", "value", "combinable"]}),
        ("What it covers", {"fields": ["scope", "products", "categories", "collections"]}),
        ("When it applies", {"fields": ["min_quantity", "min_value", "valid_from", "valid_until"]}),
        ("Limits", {"fields": ["max_uses", "max_uses_per_customer"]}),
    ]

    @admin.display(description="used")
    def uses(self, offer):
        return Order.objects.counted().filter(discount_lines__offer=offer).count()


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
    list_filter = ["is_active"]
    search_fields = ["name"]

    @admin.display(description="states")
    def state_list(self, rate):
        return ", ".join(rate.states) or "all others"


class OrderItemInline(ReadOnlyInline):
    model = OrderItem
    fields = readonly_fields = ["title", "hsn_code", "gst_rate", "mrp", "unit_price", "quantity", "discount"]


class OrderDiscountInline(ReadOnlyInline):
    model = OrderDiscount
    fields = readonly_fields = ["label", "amount", "offer"]
    verbose_name_plural = "discounts"


class PaymentInline(ReadOnlyInline):
    model = Payment
    fields = readonly_fields = ["method", "amount", "status", "razorpay_order_id", "razorpay_payment_id", "error"]


class ShipmentForm(forms.ModelForm):
    """A parcel booked with a courier through the shipping app is the courier's (its AWB, its status): shown here,
    never changed (nor checked: it has no tracking number while it is being booked)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        detail = getattr(self.instance, "detail", None)
        if detail is not None and detail.carrier != "manual":
            for field in self.fields.values():
                field.disabled, field.required = True, False


class ShipmentInline(admin.TabularInline):  # created by "mark shipped"; editable to correct a tracking number
    model = Shipment
    form = ShipmentForm
    extra = 0
    can_delete = False
    fields = ["courier", "tracking_number", "tracking_url", "shipped_at", "delivered_at", "parcel_status"]
    readonly_fields = ["parcel_status"]

    def has_add_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("detail")

    @admin.display(description="courier's status")
    def parcel_status(self, shipment):
        detail = getattr(shipment, "detail", None)
        if detail is None or detail.carrier == "manual":
            return "sent by hand"
        return detail.get_status_display() or "being booked"


class RefundInline(ReadOnlyInline):
    model = Refund
    fields = readonly_fields = ["amount", "status", "reason", "razorpay_refund_id", "error", "created", "created_by"]


class OrderNoteInline(admin.TabularInline):
    """Staff's internal notes (never shown to the customer); OrderAdmin.save_formset signs new ones."""

    model = OrderNote
    extra = 1
    fields = ["text", "author", "created"]
    readonly_fields = ["author", "created"]
    verbose_name_plural = "internal notes (the customer never sees them)"


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
class OrderAdmin(LoggedExportMixin, SimpleHistoryAdmin):  # export: shop.export_order (ADMIN), logged
    resource_classes = [OrderResource]
    export_formats = [CSV, XLSX]
    list_display = ["order_number", "created", "customer", "total", "payment_method", "status", "placed_at"]
    list_filter = [
        "status",
        "payment_method",
        ("created_by", admin.EmptyFieldListFilter),  # not empty: made by staff (phone and school orders)
        "livemode",
        "placed_at",
        "created",
    ]
    search_fields = [
        "number",
        "email",
        "shipping_address__name",
        "shipping_address__phone",
        "shipments__tracking_number",
    ]
    date_hierarchy = "created"
    readonly_fields = [
        *["order_number", "status", "customer_page", "email", "delivery_address", "subtotal", "discount"],
        *["shipping_fee", "total", "coupon_code", "payment_method", "livemode", "placed_at", "invoice_link"],
        *["created_by", "status_timeline", "created", "modified"],
    ]
    fields = readonly_fields
    inlines = [OrderItemInline, OrderDiscountInline, PaymentInline, ShipmentInline, RefundInline, OrderNoteInline]
    actions = [
        *["mark_packed", "mark_shipped", "mark_delivered", "cancel", "refund", "payment_link"],
        "offline_payment",
    ]

    def has_delete_permission(self, request, obj=None):  # tax records
        return False

    def has_refund_permission(self, request):
        return request.user.has_perm("shop.add_refund")

    def has_record_payment_permission(self, request):
        return request.user.has_perm("shop.add_payment")

    def has_pack_permission(self, request):  # packing and shipping are PACKER's (and ADMIN's), not SALES' (plan 4.1)
        return request.user.has_perm("staff.pack_order")

    def get_urls(self):
        customer = self.admin_site.admin_view(self.customer_view)
        return [path("customer/<int:user_id>/", customer, name="shop_customer"), *super().get_urls()]

    def save_formset(self, request, form, formset, change):
        if formset.model is not OrderNote:
            return super().save_formset(request, form, formset, change)
        for note in formset.save(commit=False):  # signed by its author; the history keeps every change
            if note._state.adding:
                note.author = request.user
            note.save()
        for note in formset.deleted_objects:
            note.delete()
        return None

    @admin.display(description="customer")
    def customer_page(self, order):
        if not order.user_id:
            return "a guest (no account)"
        url = reverse("admin:shop_customer", args=[order.user_id])
        return format_html('<a href="{}">{}</a> (orders, addresses, reviews…)', url, order.user)

    @admin.display(description="timeline")
    def status_timeline(self, order):
        rows = ((label, timezone.localtime(when).strftime("%d %b %Y %H:%M")) for label, when in order.timeline())
        return format_html_join(mark_safe("<br>"), "{} · {}", rows)

    @admin.display(description="number", ordering="number")
    def order_number(self, order):
        if order.is_test:  # made with test keys, the site now runs on live ones: never packed or shipped
            return format_html("{} <strong>TEST</strong>", order.number)
        return order.number

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
        links = [(pdf_url(document), document.number) for document in [invoice, *notes]]
        return format_html_join(" · ", '<a href="{}">{}</a>', links)

    def _each(self, request, queryset, step, done):
        ok, refused = 0, []
        for order in queryset:
            try:
                step(order)
                ok += 1
            except TransitionNotAllowed:
                refused.append(f"{order} ({'a test order' if order.is_test else order.get_status_display()})")
        if ok:
            self.message_user(request, f"{done}: {ok} order(s).", messages.SUCCESS)
        if refused:
            self.message_user(request, f"Not possible for {', '.join(refused)}.", messages.WARNING)

    @admin.action(description="Mark packed", permissions=["pack"])
    def mark_packed(self, request, queryset):
        self._each(request, queryset, services.pack_order, "Packed")

    @admin.action(description="Mark delivered", permissions=["pack"])
    def mark_delivered(self, request, queryset):
        self._each(request, queryset, services.deliver_order, "Delivered (customer emailed)")

    @admin.action(
        description="Cancel (stock back; an online payment refunded within your limit, FINANCE approves above it)",
        permissions=["change"],
    )
    def cancel(self, request, queryset):
        """An order paid online is cancelled by its refund, as in the panel (staff.approvals' "order.refund": the
        refund cancels what is not shipped): the maker's limit applies, and above it the cancellation waits for
        FINANCE. Any other order is cancelled at once."""
        from staff.approvals import Refund as PanelRefund

        reason, unpaid = "Cancelled by ExamLeaf.", []
        for order in queryset:
            if PanelRefund._paid(order) is None:  # nothing paid online to give back
                unpaid.append(order)
            else:
                self._ask_refund(request, order, reason)
        self._each(
            request,
            unpaid,
            lambda o: services.cancel_order(o, reason, by=request.user),
            "Cancelled (customer emailed)",
        )

    @admin.action(description="Mark shipped (courier and tracking number)", permissions=["pack"])
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
                rows = {row["order"]: row for row in formset.cleaned_data if row.get("order") in by_pk}
                self._each(
                    request,
                    [by_pk[pk] for pk in rows],
                    lambda o: services.ship_order(
                        o, rows[o.pk]["courier"], rows[o.pk]["tracking_number"], rows[o.pk]["tracking_url"]
                    ),
                    "Shipped (customer emailed the tracking number)",
                )
                return None
        else:
            formset = formset_class(initial=[{"order": order.pk} for order in orders], prefix="ship")
        return self._form_page(
            request, queryset, "mark_shipped", "Mark shipped", zip(formset.forms, orders, strict=False), formset
        )

    @admin.action(
        description="Refund through Razorpay, within your limit (above it FINANCE approves; cancels if not shipped)",
        permissions=["refund"],
    )
    def refund(self, request, queryset):
        form = RefundForm(request.POST if "apply" in request.POST else None)
        if form.is_valid():
            for order in queryset:
                self._ask_refund(request, order, form.cleaned_data["reason"], form.cleaned_data["amount"])
            return None
        return self._form_page(request, queryset, "refund", "Refund", [(form, None)], None)

    def _ask_refund(self, request, order, reason, amount=None):
        """The panel's refund, not one of its own (staff.approvals' "order.refund", staff/README.md "Approvals"): within
        the maker's refund limit (accounts.roles.ROLE_LIMITS) it runs at once; above it, it waits as a change request
        for FINANCE's approval in the panel. Each step is in the audit log."""
        from rest_framework.exceptions import APIException

        from staff import approvals

        payload = {"amount": None if amount is None else str(amount)}
        try:
            change, _ = approvals.ask(
                "order.refund", maker=request.user, target=order.number, payload=payload, reason=reason, request=request
            )
        except APIException as error:  # refused: nothing paid online, a refund under way, not the maker's to ask
            detail = error.detail
            while isinstance(detail, dict | list):
                detail = next(iter(detail.values() if isinstance(detail, dict) else detail), "")
            self.message_user(request, f"Nothing refunded for {order} ({detail})", messages.WARNING)
            return
        if change.status == change.Status.EXECUTED:
            self.message_user(request, f"Refund requested from Razorpay: {order}.", messages.SUCCESS)
        elif change.status == change.Status.PENDING:
            text = f"{order}: {change.rule} It waits for FINANCE's approval in the panel (change request #{change.pk})."
            self.message_user(request, text, messages.WARNING)
        else:
            self.message_user(
                request, f"Nothing refunded for {order} ({change.result.get('error', '')})", messages.ERROR
            )

    def add_view(self, request, form_url="", extra_context=None):
        """ "Add order": a phone or school order at today's prices (services.create_staff_order), then its payment
        link, or a payment recorded offline later (RUNBOOK.md "Staff orders")."""
        if not self.has_add_permission(request):
            raise PermissionDenied
        data = request.POST or None
        lines = formset_factory(StaffOrderLineForm, extra=5)(data, prefix="lines")
        form, address = StaffOrderForm(data), AddressForm(data, prefix="address")
        if request.method == "POST" and all([form.is_valid(), address.is_valid(), lines.is_valid()]):
            chosen = Counter()
            for row in lines.cleaned_data:
                if row:
                    chosen[row["product"]] += row["quantity"]
            email = form.cleaned_data["email"]
            confirmed = EmailAddress.objects.filter(email__iexact=email, verified=True).select_related("user").first()
            try:
                if not chosen:
                    raise services.ShopError("Choose at least one product.")
                order = services.create_staff_order(
                    [Line(product, quantity) for product, quantity in chosen.items()],
                    by=request.user,
                    email=email,
                    address=address.save(commit=False).snapshot(),
                    user=confirmed.user if confirmed else None,
                    discount=form.cleaned_data["discount"] or 0,
                    shipping=form.cleaned_data["shipping"],
                )
            except services.ShopError as error:
                form.add_error(None, str(error))
            else:
                self.log_addition(request, order, [{"added": {}}])
                if note := form.cleaned_data["note"]:
                    OrderNote.objects.create(order=order, author=request.user, text=note)
                if form.cleaned_data["send_link"]:
                    self._send_link(request, order)
                return redirect("admin:shop_order_change", order.pk)
        context = {
            **self.admin_site.each_context(request),
            "title": "New phone or school order",
            "opts": self.model._meta,
            "form": form,
            "address_form": address,
            "lines": lines,
        }
        return render(request, "shop/admin/staff_order.html", context)

    def _send_link(self, request, order):
        if order.status != Order.Status.PENDING or order.placed_at or order.is_cod:
            self.message_user(request, f"{order} is not waiting for an online payment.", messages.WARNING)
            return
        try:
            payment = payments.send_payment_link(order)
        except payments.Unavailable as error:
            self.message_user(request, f"No payment link for {order}: {error}", messages.ERROR)
        else:
            text = f"Payment link for {order} emailed to {order.email}: {payment.payment_link_url}"
            self.message_user(request, text, messages.SUCCESS)

    @admin.action(description="Email a Razorpay payment link (orders waiting for payment)", permissions=["change"])
    def payment_link(self, request, queryset):
        for order in queryset:
            self._send_link(request, order)

    @admin.action(description="Record a payment received offline (bank transfer, UPI)", permissions=["record_payment"])
    def offline_payment(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, "Choose one order: a reference belongs to one payment.", messages.WARNING)
            return None
        form = OfflinePaymentForm(request.POST if "apply" in request.POST else None)
        if form.is_valid():
            order = queryset.get()
            try:
                services.record_offline_payment(order, form.cleaned_data["reference"])
            except services.ShopError as error:
                self.message_user(request, f"{order}: {error}", messages.ERROR)
            else:
                self.message_user(request, f"{order} is paid (customer emailed, invoice on its way).", messages.SUCCESS)
            return None
        return self._form_page(request, queryset, "offline_payment", "Record the payment", [(form, None)], None)

    def customer_view(self, request, user_id):
        """One customer: the account, its orders (and guest orders with its address), saved addresses, reviews,
        quotation requests, stock alerts and course entitlements, each shown to staff who may view them."""
        if not self.has_view_permission(request):
            raise PermissionDenied
        customer = get_object_or_404(get_user_model(), pk=user_id)
        try:
            entitlements = apps.get_model("learn", "Entitlement").objects.filter(user=customer)
        except LookupError:  # the learn app (Phase 6 D) is not installed
            entitlements = None
        context = {
            **self.admin_site.each_context(request),
            "title": f"Customer: {customer}",
            "opts": self.model._meta,
            "customer": customer,
            "orders": Order.objects.filter(Q(user=customer) | Q(email__iexact=customer.email)),
            "addresses": customer.addresses.all(),
            "reviews": customer.reviews.select_related("product"),
            "quotes": QuoteRequest.objects.filter(email__iexact=customer.email),
            "alerts": StockAlert.objects.filter(email__iexact=customer.email).select_related("product"),
            "entitlements": entitlements,
        }
        return render(request, "shop/admin/customer.html", context)

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
    exclude = ["raw_payload"]  # what Razorpay sent: for disputes, from the database only (180 days)
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


class DocumentAdmin(ReadOnlyAdmin):
    """An invoice's or a credit note's PDF, for staff who may view them: <pk>/pdf/ (admin:shop_invoice_pdf,
    admin:shop_creditnote_pdf), linked from the list and from the order."""

    def get_urls(self):
        name = f"{self.opts.app_label}_{self.opts.model_name}_pdf"
        return [path("<int:pk>/pdf/", self.admin_site.admin_view(self.pdf_view), name=name), *super().get_urls()]

    def pdf_view(self, request, pk):
        if not self.has_view_permission(request):
            raise PermissionDenied
        return pdf_response(self.model.objects.filter(pk=pk).first())

    @admin.display(description="PDF")
    def pdf_link(self, document):
        if not document.pdf:
            return "being made"
        return format_html('<a href="{}">download</a>', pdf_url(document))


def pdf_url(document):
    return reverse(f"admin:shop_{document._meta.model_name}_pdf", args=[document.pk])


@admin.register(Invoice)
class InvoiceAdmin(DocumentAdmin):
    list_display = ["number", "order", "created", "pdf_link"]
    list_filter = ["financial_year", "created"]
    search_fields = ["number", "order__number"]
    list_select_related = ["order"]


@admin.register(CreditNote)
class CreditNoteAdmin(DocumentAdmin):
    list_display = ["number", "invoice", "refund_amount", "created", "pdf_link"]
    list_filter = ["financial_year", "created"]
    search_fields = ["number", "invoice__number", "invoice__order__number"]
    list_select_related = ["invoice__order", "refund"]

    @admin.display(description="amount")
    def refund_amount(self, note):
        return note.refund.amount


@admin.register(Review)
class ReviewAdmin(SimpleHistoryAdmin):
    """Buyers' reviews, shown on the product page once approved (RUNBOOK.md "Reviews")."""

    list_display = ["product", "rating", "excerpt", "status", "created"]
    list_filter = ["status", "rating", "product"]
    search_fields = ["text", "product__title", "user__email"]
    list_select_related = ["product"]
    readonly_fields = ["product", "user", "rating", "text", "created"]
    fields = [*readonly_fields, "status"]
    actions = ["approve", "reject"]

    def has_add_permission(self, request):  # reviews come from buyers
        return False

    @admin.display(description="review")
    def excerpt(self, review):
        return Truncator(review.text).chars(80)

    @admin.action(description="Approve (shown on the product page)", permissions=["change"])
    def approve(self, request, queryset):
        self._set_status(request, queryset, Review.Status.APPROVED)

    @admin.action(description="Reject (never shown)", permissions=["change"])
    def reject(self, request, queryset):
        self._set_status(request, queryset, Review.Status.REJECTED)

    def _set_status(self, request, queryset, status):
        reviews = list(queryset)
        for review in reviews:  # one by one: the history records each change and who made it
            review.status = status
            review.save(update_fields=["status", "modified"])
        self.message_user(request, f"{len(reviews)} review(s) {status}.", messages.SUCCESS)


@admin.register(QuoteRequest)
class QuoteRequestAdmin(admin.ModelAdmin):
    """School and bulk orders: set the discount and shipping, make the quotation PDF, send it to the contact, record
    the payment outside the site (RUNBOOK.md "School and bulk orders")."""

    list_display = ["number", "school", "contact_name", "copies", "status", "created", "quotation_link"]
    list_filter = ["status", "created"]
    search_fields = ["school", "contact_name", "email", "gstin"]
    readonly_fields = [
        *["number", "school", "contact_name", "email", "phone", "gstin", "delivery_pin", "books", "note"],
        *["created", "quoted_at", "quotation_link"],
    ]
    fields = [*readonly_fields, "status", "discount_percent", "shipping_fee"]
    actions = ["make_quotation"]

    def has_add_permission(self, request):  # requests come from the website's form
        return False

    @admin.display(description="books")
    def books(self, quote):
        return format_html_join(mark_safe("<br>"), "{} × {}", ((i["quantity"], i["title"]) for i in quote.items))

    @admin.display(description="quotation")
    def quotation_link(self, quote):
        if not quote.quotation:
            return "—"
        url = reverse("admin:shop_quoterequest_quotation", args=[quote.pk])
        until = f"{quote.valid_until:%d %b %Y}"  # format_html makes its arguments text first
        return format_html('<a href="{}">{}.pdf</a>, valid until {}', url, quote.number, until)

    def get_urls(self):
        download = self.admin_site.admin_view(self.download_quotation)
        return [path("<int:pk>/quotation/", download, name="shop_quoterequest_quotation"), *super().get_urls()]

    def download_quotation(self, request, pk):
        quote = get_object_or_404(QuoteRequest, pk=pk)
        if not (self.has_view_permission(request, quote) and quote.quotation):
            raise Http404
        return FileResponse(quote.quotation.open("rb"), as_attachment=True, filename=f"ExamLeaf-{quote.number}.pdf")

    @admin.action(description="Make the quotation PDF (today's prices, valid 15 days)", permissions=["change"])
    def make_quotation(self, request, queryset):
        quotes = [services.make_quotation(quote) for quote in queryset]
        self.message_user(request, f"Quotation made: {', '.join(q.number for q in quotes)}.", messages.SUCCESS)


@admin.register(StockAlert)
class StockAlertAdmin(admin.ModelAdmin):
    """Who waits for which book to be back (tasks.send_stock_alerts emails them once, hourly): what to reprint first."""

    list_display = ["product", "email", "created"]
    list_filter = ["product", "created"]
    search_fields = ["email", "product__title"]
    list_select_related = ["product"]

    def has_add_permission(self, request):  # from the product pages
        return False

    def has_change_permission(self, request, obj=None):
        return False
