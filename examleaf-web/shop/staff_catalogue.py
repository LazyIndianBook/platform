"""The Catalogue module's staff API, under /api/v1/staff/catalogue/ (API.md "Catalogue (staff)"; the rules:
shop/catalogue.py, shop/pricing.py, shop/copy_rules.py, shop/barcode.py; the module: shop/README.md "Catalogue"), on
the staff app's rules (staff.api.StaffView): a member of staff on the panel's session with a second factor, or an API
key with view_ permissions; each action's catalogued permission (none named: refused) and every refusal an
`authz_fail` event; products through `scoped()` (a person narrowed to subjects reaches theirs); cursor pages;
`Cache-Control: no-store`; every change an audit event, and a version in the record's history. Who does what (plan
5.5): SALES prices and stock, CONTENT_EDITOR the product pages and their SEO, MARKETING coupons and offers, FINANCE a
product's tax and the approvals. A price, a coupon and an offer go through staff.approvals: a 202 with the change
request beyond the maker's discount limit.

- products/: the list (filters, the chips: the tax problem, the courier's data, stock), a product (every field the
  admin edits, by section), a new one, a change (each part its own permission), pictures, a bundle's books, stock by
  hand, its versions, the prior price a proposed price would have, its EAN-13 barcode;
- stock/, stock-alerts/: levels against the low-stock line, copies held by orders, back-in-stock requests;
- coupons/, offers/, shipping-rates/: with their single-use codes and versions;
- categories/ (the tree, moved by treebeard), collections/, product-types/ with their attributes;
- import/: a CSV uploaded and its dry run started (staff.jobs; its apply and the export are jobs too);
- summary/, options/: the module's home, and the choices its forms offer."""

import hashlib
import secrets
from decimal import Decimal

import django_filters
from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction
from django.db.models import Count, Max, Prefetch, Q
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_field, inline_serializer
from rest_framework import exceptions, mixins, pagination, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.routers import SimpleRouter
from treebeard.exceptions import InvalidMoveToDescendant, InvalidPosition

from api.schema import AutoSchema
from api.shop import AnyAccept
from content.isbn import validate_isbn13
from content.review import VERSION_TYPES
from staff import approvals, audit, jobs
from staff.api import IDEMPOTENCY, StaffView, accepted
from staff.backends import scoped
from staff.models import ChangeRequest, Job
from staff.serializers import ChangeRequestSerializer, JobSerializer

from . import barcode, catalogue, pricing, tax
from .models import (
    STATES,
    Attribute,
    AttributeValue,
    BundleItem,
    Category,
    Collection,
    CollectionItem,
    Coupon,
    HsnCode,
    HsnRate,
    Offer,
    Order,
    OrderItem,
    Product,
    ProductImage,
    ProductType,
    ShippingRate,
)

VIEW = "shop.view_product"
CHANGE = "shop.change_product"
PRICE, STOCK, TAX = "staff.change_price", "staff.set_stock", "staff.change_product_tax"
PRICE_FIELDS = {"mrp", "price"}
TAX_FIELDS = {"hsn", "tax_treatment", "tax_note", "tax_note_date"}
IMPORT_MAX_BYTES = 2 * 1024 * 1024
IMPORT_MAX_ROWS = 2000
MAX_PICTURE_BYTES = 2 * 1024 * 1024  # as the admin's (shop/admin.py): every phone loads them


class StaffSchema(AutoSchema):
    def get_tags(self):
        return ["catalogue (staff)"]


class CatalogueView(StaffView):
    schema = StaffSchema()

    def by(self):
        """Who acts: the member of staff (an API key's principal has no row)."""
        return self.request.user if getattr(self.request.user, "pk", None) else None


def refused(message):
    return exceptions.ValidationError({"non_field_errors": [str(message)]})


def money(source=None, **kwargs):
    return serializers.DecimalField(source=source, max_digits=12, decimal_places=2, read_only=True, **kwargs)


def picture_of(request, file):
    """A picture's file: its address (the public bucket's, or /shop/media/), and its size."""
    if not file:
        return None
    return {"src": request.build_absolute_uri(file.url), "width": file.width, "height": file.height}


def checked_picture(upload):
    """An uploaded picture as the admin takes one (shop/admin.py): a real JPEG, PNG or WebP image (Pillow reads it),
    of 2 MB and 4096 × 4096 px at most. Raises ValidationError on `image`."""
    if upload is None:
        raise exceptions.ValidationError({"image": ["Choose a picture."]})
    if upload.size > MAX_PICTURE_BYTES:
        megabytes = upload.size / 1048576
        raise exceptions.ValidationError(
            {
                "image": [
                    f"This picture is {megabytes:.1f} MB: make it smaller than 2 MB first, it loads on every phone."
                ]
            }
        )
    try:
        serializers.ImageField().to_internal_value(upload)  # Pillow reads it, or "Upload a valid image."
    except serializers.ValidationError as error:
        raise exceptions.ValidationError({"image": error.detail}) from None
    except DjangoValidationError as error:
        raise exceptions.ValidationError({"image": error.messages}) from None
    try:
        for validator in ProductImage._meta.get_field("image").validators:
            validator(upload)
    except DjangoValidationError as error:
        raise exceptions.ValidationError({"image": error.messages}) from None
    upload.seek(0)
    return upload


class CataloguePictureSerializer(serializers.Serializer):
    src = serializers.URLField()
    width = serializers.IntegerField(allow_null=True)
    height = serializers.IntegerField(allow_null=True)


class CatalogueNamedSerializer(serializers.Serializer):
    slug = serializers.CharField()
    name = serializers.CharField()


class CatalogueRateSerializer(serializers.Serializer):
    rate = serializers.DecimalField(max_digits=4, decimal_places=2)
    taxability = serializers.CharField()
    effective_from = serializers.DateField()
    notification = serializers.CharField()


class CatalogueTaxSerializer(serializers.Serializer):
    today = CatalogueRateSerializer(allow_null=True, help_text="the master's rate of its code today; null: none")
    next_change = CatalogueRateSerializer(allow_null=True, help_text="a rate of its code that starts later")
    problem = serializers.CharField(help_text='why its GST disagrees with the master ("": it agrees): the red chip')


class CatalogueWaitingSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    action = serializers.CharField()
    status = serializers.CharField()
    rule = serializers.CharField()
    payload = serializers.JSONField()
    created = serializers.DateTimeField()


class CatalogueChangeSerializer(serializers.Serializer):
    field = serializers.CharField(help_text="a field, or a relation (its slugs before and after)")
    before = serializers.JSONField(allow_null=True)
    after = serializers.JSONField(allow_null=True)


class CatalogueVersionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    at = serializers.DateTimeField()
    by = serializers.IntegerField(allow_null=True, help_text="who: a member of staff's id (null: the site itself)")
    by_name = serializers.CharField()
    reason = serializers.CharField(help_text="why, as given (a change request's number for a price)")
    type = serializers.ChoiceField(choices=VERSION_TYPES)
    changes = CatalogueChangeSerializer(many=True, help_text="what it changed from the version before it")


VERSION_PAGE = inline_serializer(
    "CatalogueVersionPage",
    {
        "next": serializers.URLField(allow_null=True),
        "previous": serializers.URLField(allow_null=True),
        "results": CatalogueVersionSerializer(many=True),
    },
)
PAGE_PARAMETERS = [OpenApiParameter("cursor", str), OpenApiParameter("page_size", int)]


def waiting_for(target_type, target_ids):
    """The change requests waiting for approval about a record (by its id or, for a new coupon, its code)."""
    rows = ChangeRequest.objects.filter(
        target_type=target_type, target_id__in=[str(each) for each in target_ids], status=ChangeRequest.Status.PENDING
    )
    return CatalogueWaitingSerializer(rows.order_by("-pk")[:20], many=True).data


# ---- Products ----


class CatalogueProductRowSerializer(serializers.ModelSerializer):
    """A product in the list, with its chips: the GST that disagrees with the master (red), the courier's data that
    is missing, the stock against the low-stock line. No query per row: the view reads them at once."""

    mrp = money("mrp.amount")
    price = money("price.amount")
    saving_percent = serializers.IntegerField(read_only=True)
    available = serializers.SerializerMethodField(help_text="copies to sell now (a bundle: its books'; a course: 1)")
    stock_state = serializers.SerializerMethodField()
    tax_problem = serializers.SerializerMethodField(help_text='"" when its GST agrees with the master today')
    courier_problem = serializers.SerializerMethodField(help_text='"" when the courier can be quoted for it')
    cover = serializers.SerializerMethodField()
    categories = serializers.SlugRelatedField(slug_field="slug", many=True, read_only=True)

    class Meta:
        model = Product
        fields = [
            *["id", "slug", "title", "kind", "is_active", "mrp", "price", "saving_percent", "stock", "available"],
            *["stock_state", "hsn_code", "gst_rate", "tax_problem", "courier_problem", "cover", "categories"],
            "modified",
        ]
        read_only_fields = fields

    def items(self, product):
        return list(product.bundle_items.all())

    def get_available(self, product) -> int:
        return catalogue.available(product, self.items(product))

    @extend_schema_field(serializers.ChoiceField(choices=["none", "out", "low", "in_stock"]))
    def get_stock_state(self, product):
        return catalogue.stock_state(product, self.items(product))[1]

    def get_tax_problem(self, product) -> str:
        return self.context.get("problems", {}).get(product.pk, "")

    def get_courier_problem(self, product) -> str:
        return catalogue.courier_problem(product, self.items(product))

    @extend_schema_field(CataloguePictureSerializer(allow_null=True))
    def get_cover(self, product):
        return picture_of(self.context["request"], product.cover)


class CatalogueAttributeSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()
    kind = serializers.CharField()
    choices = serializers.ListField(child=serializers.CharField())
    value = serializers.CharField(allow_null=True, help_text="the product's; null: not given")


class CatalogueImageSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    src = serializers.URLField()
    width = serializers.IntegerField(allow_null=True)
    height = serializers.IntegerField(allow_null=True)
    alt = serializers.CharField()
    position = serializers.IntegerField()


class CatalogueBundleLineSerializer(serializers.Serializer):
    product = serializers.CharField(help_text="its slug")
    title = serializers.CharField()
    kind = serializers.CharField()
    quantity = serializers.IntegerField()
    stock = serializers.IntegerField()
    weight_grams = serializers.IntegerField()


class CatalogueStockSerializer(serializers.Serializer):
    stock = serializers.IntegerField(help_text="copies to sell (orders placed have taken theirs)")
    available = serializers.IntegerField()
    state = serializers.CharField()
    low_stock = serializers.IntegerField(help_text="the low-stock line (SHOP_LOW_STOCK)")
    reserved = serializers.IntegerField(
        help_text="copies orders placed have taken and not yet sent: still on the shelf"
    )
    awaiting_payment = serializers.IntegerField(help_text="copies in orders waiting for an online payment")
    alerts = serializers.IntegerField(help_text='"email me when it is back" requests waiting')
    last_alert = serializers.DateTimeField(allow_null=True)


class CataloguePriorPriceSerializer(serializers.Serializer):
    price = serializers.DecimalField(max_digits=12, decimal_places=2)
    lowest_in_30_days = serializers.DecimalField(
        max_digits=12, decimal_places=2, help_text="the lowest selling price in force in the 30 days before now"
    )
    prior_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, allow_null=True, help_text="what the website would print beside the price"
    )
    window_from = serializers.DateTimeField()
    applies = serializers.BooleanField(help_text="the rule is in force today")
    applies_from = serializers.DateField()


class CataloguePricesSerializer(serializers.Serializer):
    mrp = serializers.DecimalField(max_digits=12, decimal_places=2)
    price = serializers.DecimalField(max_digits=12, decimal_places=2)
    saving_percent = serializers.IntegerField()
    prior_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, allow_null=True, help_text="what the website shows beside the price now"
    )
    prior_price_applies = serializers.BooleanField(help_text="the rule is in force today (SHOP_PRIOR_PRICE_FROM)")
    prior_price_from = serializers.DateField()


class CatalogueProductSerializer(serializers.ModelSerializer):
    """A product, by section: identity (title, slug, kind, on sale, subject, book, ISBN, pages, description, type and
    attributes, shelves, collections, related products, earlier addresses); prices (MRP, selling price, the prior
    price the website shows); tax (the HSN or SAC code from the master, a bundle's treatment and the CA's note, the
    master's rate today and its next change, the red chip's words); physical (weight, dimensions, packaging, what the
    courier lacks); stock; pictures; a bundle's books; SEO; the approvals waiting about it."""

    subject = serializers.SerializerMethodField()
    book = serializers.SerializerMethodField()
    product_type = serializers.SerializerMethodField()
    attributes = serializers.SerializerMethodField()
    categories = serializers.SerializerMethodField()
    collections = serializers.SerializerMethodField()
    related = serializers.SlugRelatedField(slug_field="slug", many=True, read_only=True)
    old_slugs = serializers.SlugRelatedField(slug_field="slug", many=True, read_only=True)
    prices = serializers.SerializerMethodField()
    hsn = serializers.CharField(source="hsn_id", allow_null=True, read_only=True, help_text="its master code")
    tax = serializers.SerializerMethodField()
    courier_problem = serializers.SerializerMethodField()
    stock_info = serializers.SerializerMethodField()
    cover = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    bundle_items = serializers.SerializerMethodField()
    barcode = serializers.SerializerMethodField(help_text="its ISBN is a valid EAN-13: barcode.svg draws it")
    waiting = serializers.SerializerMethodField(help_text="price changes waiting for approval")
    web_url = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            *["id", "slug", "title", "kind", "is_active", "subject", "book", "isbn", "pages", "description"],
            *["product_type", "attributes", "categories", "collections", "related", "old_slugs", "web_url"],
            *["prices", "hsn", "hsn_code", "gst_rate", "tax_treatment", "tax_note", "tax_note_date", "tax"],
            *["weight_grams", "length_cm", "width_cm", "height_cm", "packaging", "courier_problem"],
            *["stock_info", "cover", "images", "bundle_items", "seo_title", "seo_description", "barcode"],
            *["waiting", "created", "modified"],
        ]
        read_only_fields = fields

    def items(self, product):
        return list(product.bundle_items.all())

    @extend_schema_field(
        inline_serializer("CatalogueSubject", {"id": serializers.IntegerField(), "label": serializers.CharField()})
    )
    def get_subject(self, product):
        subject = product.subject
        return {"id": subject.pk, "label": str(subject)} if subject else None

    @extend_schema_field(CatalogueNamedSerializer(allow_null=True))
    def get_book(self, product):
        return {"slug": product.book.slug, "name": product.book.title} if product.book_id else None

    @extend_schema_field(
        inline_serializer("CatalogueTypeRef", {"id": serializers.IntegerField(), "name": serializers.CharField()})
    )
    def get_product_type(self, product):
        kind = product.product_type
        return {"id": kind.pk, "name": kind.name} if kind else None

    @extend_schema_field(CatalogueAttributeSerializer(many=True))
    def get_attributes(self, product):
        if not product.product_type_id:
            return []
        values = {value.attribute_id: value.value for value in product.attribute_values.all()}
        return [
            {
                "code": attribute.code,
                "name": attribute.name,
                "kind": attribute.kind,
                "choices": [line.strip() for line in attribute.choices.splitlines() if line.strip()],
                "value": values.get(attribute.pk),
            }
            for attribute in product.product_type.attributes.all()
        ]

    @extend_schema_field(CatalogueNamedSerializer(many=True))
    def get_categories(self, product):
        return [{"slug": shelf.slug, "name": shelf.name} for shelf in product.categories.all()]

    @extend_schema_field(CatalogueNamedSerializer(many=True))
    def get_collections(self, product):
        return [{"slug": item.collection.slug, "name": item.collection.name} for item in product.collection_items.all()]

    @extend_schema_field(CataloguePricesSerializer)
    def get_prices(self, product):
        prices = {
            "mrp": product.mrp.amount,
            "price": product.price.amount,
            "saving_percent": product.saving_percent,
            "prior_price": pricing.prior_price(product),
            "prior_price_applies": pricing.in_force(),
            "prior_price_from": settings.SHOP_PRIOR_PRICE_FROM,
        }
        return CataloguePricesSerializer(prices).data

    @extend_schema_field(CatalogueTaxSerializer)
    def get_tax(self, product):
        today, rows = timezone.localdate(), None
        if product.hsn_id:
            rows = HsnRate.objects.filter(hsn_id=product.hsn_id, effective_from__gt=today).order_by("effective_from")
        current = tax.rate_on(product.hsn_id, today) if product.hsn_id else None
        upcoming = rows.first() if rows is not None else None
        brief = lambda row: (  # noqa: E731
            {
                "rate": row.rate,
                "taxability": row.taxability,
                "effective_from": row.effective_from,
                "notification": row.notification,
            }
            if row
            else None
        )
        found = {"today": brief(current), "next_change": brief(upcoming), "problem": product.tax_problem}
        return CatalogueTaxSerializer(found).data

    def get_courier_problem(self, product) -> str:
        return catalogue.courier_problem(product, self.items(product))

    @extend_schema_field(CatalogueStockSerializer)
    def get_stock_info(self, product):
        count, state = catalogue.stock_state(product, self.items(product))
        held = catalogue.held_copies([product.pk]).get(product.pk, {"reserved": 0, "awaiting": 0})
        alerts, last = catalogue.alert_counts([product.pk]).get(product.pk, (0, None))
        stock = {
            "stock": product.stock,
            "available": count,
            "state": state,
            "low_stock": settings.SHOP_LOW_STOCK,
            "reserved": held["reserved"],
            "awaiting_payment": held["awaiting"],
            "alerts": alerts,
            "last_alert": last,
        }
        return CatalogueStockSerializer(stock).data

    @extend_schema_field(CataloguePictureSerializer(allow_null=True))
    def get_cover(self, product):
        return picture_of(self.context["request"], product.cover)

    @extend_schema_field(CatalogueImageSerializer(many=True))
    def get_images(self, product):
        request = self.context["request"]
        return [
            {**picture_of(request, image.image), "id": image.pk, "alt": image.alt, "position": image.position}
            for image in product.images.all()
            if image.image
        ]

    @extend_schema_field(CatalogueBundleLineSerializer(many=True))
    def get_bundle_items(self, product):
        return [
            {
                "product": item.product.slug,
                "title": item.product.title,
                "kind": item.product.kind,
                "quantity": item.quantity,
                "stock": item.product.stock,
                "weight_grams": item.product.weight_grams,
            }
            for item in self.items(product)
        ]

    def get_barcode(self, product) -> bool:
        try:
            barcode.modules(validate_isbn13(product.isbn))
        except DjangoValidationError, ValueError:
            return False
        return True

    @extend_schema_field(CatalogueWaitingSerializer(many=True))
    def get_waiting(self, product):
        return waiting_for("shop.product", [product.pk])

    def get_web_url(self, product) -> str:
        return f"{settings.SITE_URL.rstrip('/')}{product.get_absolute_url()}"


class CatalogueStockSetSerializer(serializers.Serializer):
    stock = serializers.IntegerField(min_value=0, max_value=1_000_000, help_text="copies in hand, to sell")
    reason = serializers.CharField(max_length=500, help_text="why: the printer's delivery, a count")
    expected = serializers.IntegerField(
        required=False, min_value=0, help_text="the count you read: refused when orders changed it meanwhile"
    )


class CatalogueProductWriteSerializer(serializers.Serializer):
    """A new product's fields, or those a change gives (each part needs its own permission: the page's
    shop.change_product, the prices' staff.change_price, the tax's staff.change_product_tax; stock is never here,
    see stock/). The courier's data is checked whenever it, or the kind, is given, and for a new product."""

    title = serializers.CharField(max_length=200)
    slug = serializers.SlugField(max_length=50)
    kind = serializers.ChoiceField(choices=Product.Kind.choices)
    is_active = serializers.BooleanField(help_text="on sale")
    subject = serializers.IntegerField(allow_null=True, help_text="a subject's id (options/)")
    book = serializers.SlugField(allow_null=True, help_text="a book's slug (options/)")
    isbn = serializers.CharField(max_length=17, allow_blank=True, help_text="ISBN-13 (hyphens may stay)")
    pages = serializers.IntegerField(min_value=1, max_value=5000, allow_null=True)
    description = serializers.CharField(allow_blank=True, max_length=20000, help_text="Markdown")
    product_type = serializers.IntegerField(allow_null=True, help_text="a product type's id")
    attributes = serializers.DictField(
        child=serializers.CharField(allow_blank=True, max_length=200), help_text='{code: value}, "" to remove one'
    )
    categories = serializers.ListField(child=serializers.SlugField(), max_length=50, help_text="its shelves' slugs")
    related = serializers.ListField(child=serializers.SlugField(), max_length=20, help_text="products' slugs")
    weight_grams = serializers.IntegerField(min_value=0, max_value=50000)
    length_cm = serializers.IntegerField(min_value=1, max_value=200, allow_null=True)
    width_cm = serializers.IntegerField(min_value=1, max_value=200, allow_null=True)
    height_cm = serializers.IntegerField(min_value=1, max_value=200, allow_null=True)
    packaging = serializers.ChoiceField(choices=Product.Packaging.choices, allow_blank=True)
    seo_title = serializers.CharField(max_length=70, allow_blank=True)
    seo_description = serializers.CharField(max_length=160, allow_blank=True)
    hsn = serializers.CharField(max_length=8, allow_null=True, help_text="a code of the HSN and SAC master")
    tax_treatment = serializers.ChoiceField(choices=Product.TaxTreatment.choices)
    tax_note = serializers.CharField(allow_blank=True, max_length=5000)
    tax_note_date = serializers.DateField(allow_null=True)
    mrp = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.01"))
    price = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.01"))
    reason = serializers.CharField(max_length=500, required=False, help_text="why the price changes (its approval)")

    def __init__(self, *args, product=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.product = product
        if product is None:  # a new product: its identity and an MRP at least
            for name in self.fields:
                self.fields[name].required = name in ("title", "slug", "kind", "mrp")

    def validate(self, data):
        if unknown := sorted(set(self.initial_data) - set(self.fields)):
            name = unknown[0]
            words = "Stock is set through stock/, with a reason." if name == "stock" else "Not a field of a product."
            raise serializers.ValidationError({name: [words]})
        product = self.product
        kind = data.get("kind", product.kind if product else None)
        if "slug" in data:
            if data["slug"] in Product.RESERVED_SLUGS:
                raise serializers.ValidationError({"slug": ["This address belongs to a page of the shop."]})
            if Product.objects.filter(slug=data["slug"]).exclude(pk=getattr(product, "pk", None)).exists():
                raise serializers.ValidationError({"slug": ["Another product has this address."]})
        if product is not None and "kind" in data and data["kind"] != product.kind:
            if OrderItem.objects.filter(product=product).exists():
                raise serializers.ValidationError({"kind": ["It has been sold: its kind stays. Make a new product."]})
        if data.get("isbn"):
            before = product.isbn if product else None
            if data["isbn"] != before or "kind" in data:
                try:
                    if problem := catalogue.isbn_problem(data["isbn"], kind, exclude=getattr(product, "pk", None)):
                        raise serializers.ValidationError({"isbn": [problem]})
                except DjangoValidationError as error:
                    raise serializers.ValidationError({"isbn": error.messages}) from None
        if "subject" in data and data["subject"] is not None:
            from content.models import Subject

            data["subject"] = Subject.objects.filter(pk=data["subject"]).first()
            if data["subject"] is None:
                raise serializers.ValidationError({"subject": ["No such subject."]})
        if "book" in data and data["book"] is not None:
            from content.models import Book

            data["book"] = Book.objects.filter(slug=data["book"]).first()
            if data["book"] is None:
                raise serializers.ValidationError({"book": ["No such book."]})
        if "product_type" in data and data["product_type"] is not None:
            data["product_type"] = ProductType.objects.filter(pk=data["product_type"]).first()
            if data["product_type"] is None:
                raise serializers.ValidationError({"product_type": ["No such product type."]})
        for name, model in (("categories", Category), ("related", Product)):
            if name in data:
                found = {obj.slug: obj for obj in model.objects.filter(slug__in=data[name])}
                if missing := [slug for slug in data[name] if slug not in found]:
                    raise serializers.ValidationError({name: [f"Not found: {', '.join(missing[:10])}."]})
                data[name] = [found[slug] for slug in dict.fromkeys(data[name])]
        if product is not None and any(other.pk == product.pk for other in data.get("related", [])):
            raise serializers.ValidationError({"related": ["Not itself."]})
        if "hsn" in data and data["hsn"] is not None:
            data["hsn"] = HsnCode.objects.filter(code=data["hsn"]).first()
            if data["hsn"] is None:
                raise serializers.ValidationError({"hsn": ["Not on the HSN and SAC master (the Tax module keeps it)."]})
            if kind != Product.Kind.BUNDLE and (data["hsn"].kind == HsnCode.Kind.SAC) != (kind == Product.Kind.DIGITAL):
                what = (
                    "a SAC code (99…): it is a service" if kind == Product.Kind.DIGITAL else "an HSN code: it is goods"
                )
                raise serializers.ValidationError({"hsn": [f"Choose {what}."]})
        mrp = data.get("mrp", product.mrp.amount if product else None)
        if "price" in data and mrp is not None and data["price"] > mrp:
            raise serializers.ValidationError({"price": [f"At most the MRP, ₹{mrp}."]})
        if "attributes" in data:
            data["attributes"] = self.attribute_values(data, product)
        physical = {"weight_grams", "length_cm", "width_cm", "height_cm", "packaging", "kind"}
        if product is None or physical & set(data):
            values = {name: data.get(name, getattr(product, name, None)) for name in physical - {"kind"}}
            values["weight_grams"] = values["weight_grams"] or 0
            values["packaging"] = values["packaging"] or ""
            if product is None and kind != Product.Kind.DIGITAL and not values["packaging"]:
                values["packaging"] = data["packaging"] = Product.Packaging.FLYER  # a flyer unless they say
            items = list(product.bundle_items.select_related("product")) if product else []
            catalogue.check_physical(kind, values, items)
        if PRICE_FIELDS & set(data) and product is not None and not str(data.get("reason") or "").strip():
            if any(data.get(name) != getattr(product, name).amount for name in PRICE_FIELDS & set(data)):
                raise serializers.ValidationError({"reason": ["Say why the price changes: its approval reads it."]})
        return data

    def attribute_values(self, data, product):
        kind = data.get("product_type", product.product_type if product else None)
        given = data["attributes"]
        if given and kind is None:
            raise serializers.ValidationError({"attributes": ["Give it a product type first: types have attributes."]})
        known = {attribute.code: attribute for attribute in kind.attributes.all()} if kind else {}
        clean = {}
        for code, value in given.items():
            if code not in known:
                raise serializers.ValidationError({"attributes": [f"{code} is not an attribute of {kind}."]})
            try:
                clean[known[code]] = known[code].normalise(value) if value.strip() else None
            except DjangoValidationError as error:
                raise serializers.ValidationError(
                    {"attributes": [f"{known[code].name}: {error.messages[0]}"]}
                ) from None
        return clean


def product_permission(view, request):
    """PATCH products/{slug}/: each part its own permission (the page's, the prices', the tax's); the first the person
    lacks is the one refused (and logged), else the page's (the empty body's too)."""
    data = getattr(request, "data", None)
    keys = set(data) if isinstance(data, dict) else set()
    needed = [CHANGE] if keys - PRICE_FIELDS - TAX_FIELDS - {"reason"} or not keys else []
    needed += [PRICE] if keys & PRICE_FIELDS else []
    needed += [TAX] if keys & TAX_FIELDS else []
    user = getattr(request, "user", None)
    lacking = [perm for perm in needed if user is None or not user.has_perm(perm)]
    return (lacking or needed or [CHANGE])[0]


def save_product(product, data, *, by, request=None, reason="", creating=False):
    """The product's page, physical and tax fields as `data` gives them (CatalogueProductWriteSerializer's), saved in
    one version with who did it, and its shelves, related products and attributes; audited with what changed. Prices
    are not here (price_change). Returns the fields changed."""
    plain = [name for name in data if name not in {"categories", "related", "attributes", "mrp", "price", "reason"}]
    changes = {}
    for name in plain:
        before = getattr(product, name) if not creating else None
        if creating or before != data[name]:
            changes[name] = [
                audit.plain(getattr(before, "pk", before)),
                audit.plain(getattr(data[name], "pk", data[name])),
            ]
            setattr(product, name, data[name])
    relations = {}
    for name in ("categories", "related"):
        if name in data:
            before = sorted(getattr(product, name).values_list("slug", flat=True)) if product.pk else []
            after = sorted(obj.slug for obj in data[name])
            if before != after:
                relations[name], changes[name] = data[name], [before, after]
    attributes = data.get("attributes", {})
    if attributes:
        held = {value.attribute_id: value.value for value in product.attribute_values.all()} if product.pk else {}
        for attribute, value in attributes.items():
            if held.get(attribute.pk) != value:
                changes[f"attributes.{attribute.code}"] = [held.get(attribute.pk), value]
    if not changes and not creating:
        return []
    with transaction.atomic():
        if changes.keys() - {"categories", "related"} - {f"attributes.{a.code}" for a in attributes} or creating:
            product._history_user, product._change_reason = by, (reason or "")[:100]
            if product.hsn_id:
                product.hsn_code = product.hsn_id  # as save() keeps it: the model's own checks read the code
            try:
                product.full_clean(exclude=["cover", "og_image", "categories", "related"], validate_unique=False)
            except DjangoValidationError as error:
                errors = error.message_dict
                if "hsn_code" in errors:  # the code the API names `hsn` (a course needs a SAC code of the master)
                    errors["hsn"] = errors.pop("hsn_code")
                raise serializers.ValidationError(errors) from None
            product.save()
        for name, chosen in relations.items():
            getattr(product, name).set(chosen)
        for attribute, value in attributes.items():
            if value is None:
                AttributeValue.objects.filter(product=product, attribute=attribute).delete()
            else:
                AttributeValue.objects.update_or_create(product=product, attribute=attribute, defaults={"value": value})
        action = "catalogue.product_created" if creating else "catalogue.product_changed"
        audit.record(action, request=request, actor=by, target=product, changes=changes, reason=reason)
    return sorted(changes)


def price_change(product, data, *, maker, request=None, key=""):
    """The MRP and selling price `data` gives, through the approval product.price (staff.approvals.Price): run at once
    within the maker's discount limit, else waiting for FINANCE. None when neither changes."""
    asked = {name: str(data[name]) for name in PRICE_FIELDS & set(data)}
    if all(Decimal(value) == getattr(product, name).amount for name, value in asked.items()):
        return None
    change_request, _ = approvals.ask(
        "product.price",
        maker=maker,
        target=product.slug,
        payload=asked,
        reason=data.get("reason") or "A new product's price",
        idempotency_key=key,
        request=request,
    )
    return change_request


class ProductFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(method="search", help_text="words of its title, its slug, or its ISBN's digits")
    category = django_filters.CharFilter(method="on_shelf", help_text="a category's slug, with its sub-categories")
    collection = django_filters.CharFilter(field_name="collection_items__collection__slug")
    published = django_filters.BooleanFilter(field_name="is_active", help_text="on sale")
    stock = django_filters.ChoiceFilter(
        choices=[("out", "out"), ("low", "low"), ("in_stock", "in_stock")], method="by_stock", help_text="books only"
    )
    tax_problem = django_filters.BooleanFilter(method="by_tax", help_text="its GST disagrees with the master today")
    incomplete = django_filters.BooleanFilter(method="by_courier", help_text="the courier cannot be quoted for it")

    class Meta:
        model = Product
        fields = ["kind"]

    def search(self, queryset, name, value):
        value = " ".join(value.split())[:100]
        if not value:
            return queryset
        digits = value.replace("-", "").replace(" ", "")
        found = Q(slug__icontains=value) | Q(isbn__icontains=digits[-13:] if digits.isdigit() else value)
        for word in value.split()[:5]:
            found |= Q(title__icontains=word)
        return queryset.filter(found)

    def on_shelf(self, queryset, name, value):
        shelf = Category.objects.filter(slug=value).first()
        return queryset.filter(categories__in=Category.objects.get_tree(shelf)).distinct() if shelf else queryset.none()

    def by_stock(self, queryset, name, value):
        return catalogue.stock_filter(queryset, value)

    def by_tax(self, queryset, name, value):
        # ponytail: the whole (filtered) catalogue is checked at once, as the Tax module's problems/ does; hundreds of
        # products. A stored chip if it grows to thousands.
        problems = tax.problems(queryset.select_related(None))
        return queryset.filter(pk__in=problems) if value else queryset.exclude(pk__in=problems)

    def by_courier(self, queryset, name, value):
        return catalogue.incomplete(queryset) if value else queryset.exclude(pk__in=catalogue.incomplete(queryset))


BUNDLE_LINES = Prefetch("bundle_items", queryset=BundleItem.objects.select_related("product").order_by("pk"))


class ProductViewSet(CatalogueView, viewsets.GenericViewSet):
    """Products: the list with its chips, a product by section, a new one, a change (its parts by permission: a price
    through its approval), pictures, a bundle's books, stock by hand, its versions, a proposed price's prior price,
    the EAN-13 barcode."""

    serializer_class = CatalogueProductRowSerializer
    filterset_class = ProductFilter
    lookup_field = "slug"
    lookup_value_regex = "[-a-zA-Z0-9_]+"
    permissions = {
        **dict.fromkeys(["list", "retrieve", "history", "prior_price", "barcode"], VIEW),
        "create": "shop.add_product",
        "partial_update": product_permission,
        "pictures": "shop.add_productimage",
        "picture": lambda view, request: (
            "shop.change_productimage" if request.method == "PATCH" else ("shop.delete_productimage")
        ),
        "bundle": CHANGE,
        "stock": STOCK,
    }
    throttle_scopes = {"partial_update": "staff_money", "create": "staff_money"}

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Product.objects.none()
        products = scoped(Product.objects.all(), self.request.user, VIEW)
        if self.action == "list":
            return products.prefetch_related(BUNDLE_LINES, "categories").order_by("-pk")
        return products.select_related(
            "subject__board", "subject__class_level", "book", "product_type"
        ).prefetch_related(
            BUNDLE_LINES,
            "categories",
            "related",
            "old_slugs",
            "images",
            Prefetch("collection_items", queryset=CollectionItem.objects.select_related("collection")),
            Prefetch("attribute_values", queryset=AttributeValue.objects.select_related("attribute")),
            "product_type__attributes",
        )

    def answer(self, product, code=status.HTTP_200_OK, **extra):
        product = self.get_queryset().get(pk=product.pk)
        body = CatalogueProductSerializer(product, context=self.get_serializer_context()).data
        return Response({**body, **extra}, status=code)

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        context = {**self.get_serializer_context(), "problems": tax.problems(page)}
        return self.get_paginated_response(CatalogueProductRowSerializer(page, many=True, context=context).data)

    @extend_schema(responses=CatalogueProductSerializer)
    def retrieve(self, request, *args, **kwargs):
        return self.answer(self.get_object())

    @extend_schema(
        request=CatalogueProductWriteSerializer,
        responses={
            201: inline_serializer(
                "CatalogueProductMade",
                {"product": CatalogueProductSerializer(), "price_change": ChangeRequestSerializer(allow_null=True)},
            )
        },
        parameters=[IDEMPOTENCY],
    )
    def create(self, request, *args, **kwargs):
        """A new product: made at its MRP, off sale unless said; a selling price below the MRP follows through the
        approval product.price (staff.change_price; beyond your discount limit it waits for FINANCE)."""
        user = self.human()
        asked = CatalogueProductWriteSerializer(data=request.data)
        asked.is_valid(raise_exception=True)
        data = dict(asked.validated_data)
        price = data.pop("price", None)
        if price is not None and price != data["mrp"] and not user.has_perm(PRICE):
            raise exceptions.PermissionDenied(f"You need the permission {PRICE} to sell below the MRP.")
        product = Product(mrp=data.pop("mrp"), is_active=data.pop("is_active", False))
        product.price = product.mrp
        try:
            with transaction.atomic():
                save_product(product, data, by=user, request=request, creating=True)
        except IntegrityError:
            raise exceptions.ValidationError({"slug": ["Another product has this address."]}) from None
        waiting = None
        if price is not None and price != product.mrp.amount:
            waiting = price_change(
                product,
                {"price": price, "reason": asked.validated_data.get("reason", "")},
                maker=user,
                request=request,
                key=request.headers.get("Idempotency-Key", ""),
            )
        body = CatalogueProductSerializer(self.get_queryset().get(pk=product.pk), context=self.get_serializer_context())
        change = ChangeRequestSerializer(waiting, context=self.get_serializer_context()).data if waiting else None
        return Response({"product": body.data, "price_change": change}, status=status.HTTP_201_CREATED)

    @extend_schema(
        request=CatalogueProductWriteSerializer,
        responses={
            200: CatalogueProductSerializer,
            202: inline_serializer(
                "CatalogueProductPriceWaiting",
                {"price_change": ChangeRequestSerializer(), "slug": serializers.CharField()},
            ),
        },
        parameters=[IDEMPOTENCY],
    )
    def partial_update(self, request, *args, **kwargs):
        """A change: the page's fields save at once; the MRP and selling price go through product.price (with a
        `reason`): within your discount limit at once (200), beyond it 202 with the change request, the rest saved."""
        user, product = self.human(), self.get_object()
        asked = CatalogueProductWriteSerializer(data=request.data, product=product, partial=True)
        asked.is_valid(raise_exception=True)
        data = dict(asked.validated_data)
        prices = {name: data.pop(name) for name in list(data) if name in PRICE_FIELDS}
        prices = {name: value for name, value in prices.items() if value != getattr(product, name).amount}
        if prices:  # the price's own rules first: nothing is saved when it is refused
            approvals.ACTIONS["product.price"].validate(user, product.slug, {k: str(v) for k, v in prices.items()})
        try:
            with transaction.atomic():
                save_product(product, data, by=user, request=request, reason=data.get("reason", ""))
        except IntegrityError:
            raise exceptions.ValidationError({"slug": ["Another product has this address."]}) from None
        waiting = None
        if prices:
            prices["reason"] = asked.validated_data.get("reason", "")
            waiting = price_change(
                product, prices, maker=user, request=request, key=request.headers.get("Idempotency-Key", "")
            )
        if waiting is not None and waiting.status == ChangeRequest.Status.FAILED:
            raise refused(waiting.result.get("error", "The price did not change."))
        if waiting is not None and waiting.status == ChangeRequest.Status.PENDING:
            change = ChangeRequestSerializer(waiting, context=self.get_serializer_context()).data
            return Response({"price_change": change, "slug": product.slug}, status=status.HTTP_202_ACCEPTED)
        return self.answer(product)

    @extend_schema(
        request={
            "multipart/form-data": inline_serializer(
                "CataloguePictureUpload",
                {
                    "image": serializers.ImageField(),
                    "alt": serializers.CharField(required=False),
                    "position": serializers.IntegerField(required=False),
                    "as_cover": serializers.BooleanField(required=False),
                },
            )
        },
        responses={201: CatalogueProductSerializer},
    )
    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser, FormParser])
    def pictures(self, request, *args, **kwargs):
        """A picture (JPEG, PNG or WebP of 2 MB and 4096 px at most: the admin's rule), kept in the public storage
        with its AVIF and WebP sizes made by the worker; `as_cover` makes it the cover (2:3; shop.change_product)."""
        product = self.get_object()
        as_cover = str(request.data.get("as_cover", "")).lower() in ("1", "true", "on")
        if as_cover and not request.user.has_perm(CHANGE):
            raise exceptions.PermissionDenied(f"You need the permission {CHANGE} to change the cover.")
        upload = checked_picture(request.FILES.get("image"))
        alt = " ".join(str(request.data.get("alt", "")).split())[:200]
        position = request.data.get("position", "0")
        if not str(position).isdigit() or int(position) > 32767:
            raise exceptions.ValidationError({"position": ["A whole number from 0."]})
        with transaction.atomic():
            if as_cover:
                product.cover = upload
                product._history_user = self.by()
                product.save()  # its sizes made by the worker (django-pictures), its link preview again
                audit.record("catalogue.cover_changed", request=request, target=product)
            else:
                picture = ProductImage.objects.create(product=product, image=upload, alt=alt, position=int(position))
                audit.record(
                    "catalogue.picture_added", request=request, target=product, details={"picture": picture.pk}
                )
        return self.answer(product, status.HTTP_201_CREATED)

    @extend_schema(
        request=inline_serializer(
            "CataloguePictureChange",
            {"alt": serializers.CharField(required=False), "position": serializers.IntegerField(required=False)},
        ),
        responses={200: CatalogueProductSerializer, 204: None},
        parameters=[OpenApiParameter("picture", int, OpenApiParameter.PATH)],
    )
    @action(detail=True, methods=["patch", "delete"], url_path=r"pictures/(?P<picture>\d+)")
    def picture(self, request, picture=None, *args, **kwargs):
        """A picture's description (its alt text) and place among the others; or the picture taken off."""
        product = self.get_object()
        image = product.images.filter(pk=picture).first()
        if image is None:
            raise exceptions.NotFound("No such picture of this product.")
        if request.method == "DELETE":
            with transaction.atomic():
                image.delete()
                audit.record(
                    "catalogue.picture_removed", request=request, target=product, details={"picture": int(picture)}
                )
            return Response(status=status.HTTP_204_NO_CONTENT)
        changes = {}
        if "alt" in request.data:
            changes["alt"] = [image.alt, " ".join(str(request.data["alt"]).split())[:200]]
        if "position" in request.data:
            if not str(request.data["position"]).isdigit() or int(request.data["position"]) > 32767:
                raise exceptions.ValidationError({"position": ["A whole number from 0."]})
            changes["position"] = [image.position, int(request.data["position"])]
        with transaction.atomic():
            for name, (_before, after) in changes.items():
                setattr(image, name, after)
            image.save(update_fields=list(changes) or None)
            audit.record(
                "catalogue.picture_changed",
                request=request,
                target=product,
                changes=changes,
                details={"picture": image.pk},
            )
        return self.answer(product)

    @extend_schema(
        request=inline_serializer(
            "CatalogueBundleLines",
            {
                "lines": inline_serializer(
                    "CatalogueBundleLine",
                    {
                        "product": serializers.SlugField(),
                        "quantity": serializers.IntegerField(min_value=1, max_value=99),
                    },
                    many=True,
                )
            },
        ),
        responses=CatalogueProductSerializer,
    )
    @action(detail=True, methods=["put"])
    def bundle(self, request, *args, **kwargs):
        """A bundle's books and copies of each, all at once (1 to 50; no bundle in a bundle, each once): it sells their
        copies (an order takes each book's from stock) and its tax follows its treatment."""
        product = self.get_object()
        if product.kind != Product.Kind.BUNDLE:
            raise refused("Only a bundle holds books.")
        lines = request.data.get("lines")
        if not isinstance(lines, list) or not 1 <= len(lines) <= 50:
            raise exceptions.ValidationError({"lines": ["1 to 50 lines: a product's slug and its copies."]})
        wanted = {}
        for line in lines:
            if not isinstance(line, dict) or not isinstance(line.get("product"), str):
                raise exceptions.ValidationError({"lines": ["Each line: {product, quantity}."]})
            quantity = line.get("quantity", 1)
            if isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= 99:
                raise exceptions.ValidationError({"lines": [f"{line['product']}: 1 to 99 copies."]})
            if line["product"] in wanted:
                raise exceptions.ValidationError({"lines": [f"{line['product']} twice: once, with its copies."]})
            wanted[line["product"]] = quantity
        found = {item.slug: item for item in Product.objects.filter(slug__in=wanted)}
        if missing := [slug for slug in wanted if slug not in found]:
            raise exceptions.ValidationError({"lines": [f"Not found: {', '.join(missing)}."]})
        if any(item.kind == Product.Kind.BUNDLE for item in found.values()):
            raise exceptions.ValidationError({"lines": ["A bundle holds books and courses, not bundles."]})
        before = sorted([item.product.slug, item.quantity] for item in product.bundle_items.select_related("product"))
        after = sorted([slug, quantity] for slug, quantity in wanted.items())
        if before != after:
            with transaction.atomic():
                Product.objects.select_for_update().get(pk=product.pk)  # one change of its lines at a time
                if OrderItem.objects.filter(product=product, order__stock_reserved=True).exists():
                    # a cancellation or a return gives back the books of its lines as they are then
                    raise refused(
                        "Orders have taken this bundle's books from stock, and a cancellation or a return gives back "
                        "the books it holds: its books stay as they are. Make a new bundle for other books."
                    )
                for item in product.bundle_items.all():  # one at a time: the erp app's outbox hears each
                    item.delete()
                for slug, quantity in wanted.items():
                    BundleItem.objects.create(bundle=product, product=found[slug], quantity=quantity)
                audit.record(
                    "catalogue.bundle_changed", request=request, target=product, changes={"lines": [before, after]}
                )
        return self.answer(product)

    @extend_schema(request=CatalogueStockSetSerializer, responses=CatalogueProductSerializer)
    @action(detail=True, methods=["post"])
    def stock(self, request, *args, **kwargs):
        """A book's copies set by hand, with the reason (audited): refused when orders changed the count since you read
        it (`expected`). A bundle's are its books', a course has none. Back in stock: the hourly email follows."""
        product = self.get_object()
        asked = CatalogueStockSetSerializer(data=request.data)
        asked.is_valid(raise_exception=True)
        values = asked.validated_data
        catalogue.set_stock(
            product, values["stock"], values["reason"], by=self.by(), request=request, expected=values.get("expected")
        )
        return self.answer(product)

    @extend_schema(responses=VERSION_PAGE, parameters=PAGE_PARAMETERS)
    @action(detail=True, filter_backends=[])
    def history(self, request, *args, **kwargs):
        """Its versions, newest first: what each changed (field, before, after), who, when and why; the prices too
        (the prior price is read from them)."""
        return history_page(self, self.get_object(), "", {})

    @extend_schema(
        parameters=[OpenApiParameter("price", str, required=True, description="the price proposed, in rupees")],
        responses=CataloguePriorPriceSerializer,
    )
    @action(detail=True, url_path="prior-price", filter_backends=[])
    def prior_price(self, request, *args, **kwargs):
        """What a selling price would show if set now: the lowest price of the 30 days before (the prior price the
        website would print beside it, when it is below that), and whether the rule applies today. Nothing changes."""
        product = self.get_object()
        try:
            price = Decimal(request.query_params.get("price", "")).quantize(Decimal("0.01"))
            if not price.is_finite() or price <= 0 or price >= Decimal("1000000"):
                raise ValueError
        except ArithmeticError, ValueError:
            raise exceptions.ValidationError({"price": ["A price in rupees, above 0."]}) from None
        return Response(CataloguePriorPriceSerializer(pricing.proposal(product, price)).data)

    @extend_schema(responses={(200, "image/svg+xml"): OpenApiTypes.STR})
    @action(detail=True, url_path="barcode.svg", content_negotiation_class=AnyAccept, filter_backends=[])
    def barcode(self, request, *args, **kwargs):
        """Its ISBN as an EAN-13 barcode (SVG, sized for print: 37.29 mm wide), for the printer and the packing slip;
        404 without a valid ISBN-13."""
        product = self.get_object()
        try:
            drawing = barcode.svg(validate_isbn13(product.isbn))
        except DjangoValidationError, ValueError:
            raise exceptions.NotFound("No valid ISBN-13: no barcode.") from None
        response = HttpResponse(drawing, content_type="image/svg+xml")
        response["Content-Disposition"] = f'inline; filename="{product.slug}-ean13.svg"'
        return response


def history_page(view, obj, owner, relations):
    """A record's versions as a cursor page (newest first), each against the one before it."""
    paginator = view.pagination_class()
    page = paginator.paginate_queryset(obj.history.select_related("history_user"), view.request, view=view)
    older = obj.history.filter(history_id__lt=page[-1].history_id).order_by("-history_id").first() if page else None
    return paginator.get_paginated_response(catalogue.versions(page, older, owner, relations))


# ---- Stock ----


class CatalogueStockRowSerializer(serializers.ModelSerializer):
    reserved = serializers.SerializerMethodField(help_text="taken by orders placed, not yet sent (still on the shelf)")
    awaiting_payment = serializers.SerializerMethodField()
    state = serializers.SerializerMethodField()
    alerts = serializers.SerializerMethodField(help_text='"email me when it is back" requests waiting')

    class Meta:
        model = Product
        fields = [
            "id",
            "slug",
            "title",
            "kind",
            "is_active",
            "stock",
            "reserved",
            "awaiting_payment",
            "state",
            "alerts",
        ]
        read_only_fields = fields

    def get_reserved(self, product) -> int:
        return self.context["held"].get(product.pk, {}).get("reserved", 0)

    def get_awaiting_payment(self, product) -> int:
        return self.context["held"].get(product.pk, {}).get("awaiting", 0)

    @extend_schema_field(serializers.ChoiceField(choices=["out", "low", "in_stock"]))
    def get_state(self, product):
        return catalogue.stock_state(product, [])[1]

    def get_alerts(self, product) -> int:
        return self.context["alerts"].get(product.pk, (0, None))[0]


class StockFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(method="search", help_text="words of its title, or its slug")
    state = django_filters.ChoiceFilter(
        choices=[("out", "out"), ("low", "low"), ("in_stock", "in_stock")], method="by_state"
    )
    published = django_filters.BooleanFilter(field_name="is_active")

    class Meta:
        model = Product
        fields = []

    def search(self, queryset, name, value):
        return ProductFilter.search(self, queryset, name, value)

    def by_state(self, queryset, name, value):
        return catalogue.stock_filter(queryset, value)


class StockViewSet(CatalogueView, mixins.ListModelMixin, viewsets.GenericViewSet):
    """The books' stock (copies of their own), the fewest first: the low-stock line (SHOP_LOW_STOCK, as the
    morning's email), the copies orders hold, the back-in-stock requests. A copy count is set on a product
    (products/{slug}/stock/); ERPNext's stock by warehouse and batch comes in Phase C."""

    serializer_class = CatalogueStockRowSerializer
    filterset_class = StockFilter
    permissions = {"list": VIEW}

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Product.objects.none()
        return scoped(Product.objects.filter(kind__in=catalogue.GOODS), self.request.user, VIEW)

    def list(self, request, *args, **kwargs):
        paginator = ByStock()
        page = paginator.paginate_queryset(self.filter_queryset(self.get_queryset()), request, view=self)
        ids = [product.pk for product in page]
        context = {
            **self.get_serializer_context(),
            "held": catalogue.held_copies(ids),
            "alerts": catalogue.alert_counts(ids),
        }
        return paginator.get_paginated_response(CatalogueStockRowSerializer(page, many=True, context=context).data)


class ByStock(pagination.CursorPagination):
    page_size, page_size_query_param, max_page_size, ordering = 50, "page_size", 200, ("stock", "pk")


class CatalogueAlertRowSerializer(serializers.Serializer):
    product = serializers.CharField(source="slug")
    title = serializers.CharField()
    requests = serializers.IntegerField(source="alert_count")
    last_asked = serializers.DateTimeField(source="alert_last")
    available = serializers.IntegerField()


class StockAlertViewSet(CatalogueView, mixins.ListModelMixin, viewsets.GenericViewSet):
    """Back-in-stock requests ("email me when it is back") by product: how many wait and the latest one's time, never
    who asked. Each address gets one email within the hour once copies are back (shop.tasks.send_stock_alerts)."""

    serializer_class = CatalogueAlertRowSerializer
    permissions = {"list": "shop.view_stockalert"}
    filter_backends = []

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Product.objects.none()
        products = scoped(Product.objects.all(), self.request.user, VIEW).filter(stock_alerts__isnull=False)
        return products.annotate(alert_count=Count("stock_alerts"), alert_last=Max("stock_alerts__created"))

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.get_queryset().prefetch_related(BUNDLE_LINES).order_by("-pk"))
        for product in page:
            product.available = catalogue.available(product, list(product.bundle_items.all()))
        return self.get_paginated_response(CatalogueAlertRowSerializer(page, many=True).data)


# ---- Coupons ----


class CatalogueCouponSerializer(serializers.ModelSerializer):
    """A coupon: its terms, what it applies to, its single-use codes and its uses (orders placed, test orders out);
    no field names an account, nor could one (plan 10.1: different prices only through published channels)."""

    value = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True)
    min_order = money("min_order.amount")
    include_products = serializers.SlugRelatedField(slug_field="slug", many=True, read_only=True)
    include_categories = serializers.SlugRelatedField(slug_field="slug", many=True, read_only=True)
    exclude_products = serializers.SlugRelatedField(slug_field="slug", many=True, read_only=True)
    exclude_categories = serializers.SlugRelatedField(slug_field="slug", many=True, read_only=True)
    state = serializers.SerializerMethodField()
    uses = serializers.SerializerMethodField(help_text="orders placed with it, not undone (test orders out)")
    codes = serializers.SerializerMethodField()
    waiting = serializers.SerializerMethodField()

    class Meta:
        model = Coupon
        fields = [
            *["id", "code", "kind", "value", "min_order", "valid_from", "valid_until", "max_uses"],
            *["max_uses_per_customer", "is_active", "description", "note", "include_products", "include_categories"],
            *["exclude_products", "exclude_categories", "first_order_only", "stackable", "single_use", "state", "uses"],
            *["codes", "waiting", "created", "modified"],
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.ChoiceField(choices=["live", "scheduled", "ended", "inactive"]))
    def get_state(self, obj):
        return term_state(obj)

    def get_uses(self, obj) -> int:
        return getattr(obj, "use_count", 0)

    @extend_schema_field(
        inline_serializer(
            "CatalogueCodeCounts",
            {
                "made": serializers.IntegerField(),
                "used": serializers.IntegerField(),
                "batches": serializers.ListField(
                    child=inline_serializer(
                        "CatalogueCodeBatch",
                        {
                            "job": serializers.IntegerField(allow_null=True),
                            "note": serializers.CharField(),
                            "made": serializers.IntegerField(),
                            "used": serializers.IntegerField(),
                            "created": serializers.DateTimeField(),
                        },
                    )
                ),
            },
        )
    )
    def get_codes(self, coupon):
        if not self.context.get("detail"):
            made = getattr(coupon, "code_count", None)
            return {"made": made or 0, "used": getattr(coupon, "code_used", 0) or 0, "batches": []}
        rows = coupon.codes.values("job", "note").annotate(
            made=Count("pk"), used=Count("pk", filter=Q(order__isnull=False)), made_at=Max("created")
        )
        batches = sorted(
            (
                {
                    "job": row["job"],
                    "note": row["note"],
                    "made": row["made"],
                    "used": row["used"],
                    "created": row["made_at"],
                }
                for row in rows
            ),
            key=lambda row: row["created"],
            reverse=True,
        )
        return {
            "made": sum(row["made"] for row in batches),
            "used": sum(row["used"] for row in batches),
            "batches": batches,
        }

    @extend_schema_field(CatalogueWaitingSerializer(many=True))
    def get_waiting(self, coupon):
        if not self.context.get("detail"):
            return []
        return waiting_for("shop.coupon", [coupon.pk, coupon.code])


def term_state(obj):
    """A coupon's or an offer's state now: inactive (switched off), scheduled, ended or live."""
    now = timezone.now()
    if not obj.is_active:
        return "inactive"
    if obj.valid_from > now:
        return "scheduled"
    if obj.valid_until and obj.valid_until < now:
        return "ended"
    return "live"


def by_state(queryset, value):
    now = timezone.now()
    if value == "inactive":
        return queryset.filter(is_active=False)
    queryset = queryset.filter(is_active=True)
    if value == "scheduled":
        return queryset.filter(valid_from__gt=now)
    if value == "ended":
        return queryset.filter(valid_until__lt=now)
    return queryset.filter(Q(valid_until__isnull=True) | Q(valid_until__gte=now), valid_from__lte=now)


STATES_CHOICES = [("live", "live"), ("scheduled", "scheduled"), ("ended", "ended"), ("inactive", "inactive")]


class CouponFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(field_name="code", lookup_expr="icontains", help_text="part of its code")
    state = django_filters.ChoiceFilter(choices=STATES_CHOICES, method="by_state")

    class Meta:
        model = Coupon
        fields = ["kind", "single_use"]

    def by_state(self, queryset, name, value):
        return by_state(queryset, value)


def optional(field, **kwargs):
    return field(required=False, **kwargs)


TERM_DATES = {"help_text": "ISO 8601 (a day alone: its start in India)", "allow_null": True}


class CatalogueCouponWriteSerializer(serializers.Serializer):
    """A coupon's fields as asked (a new one: its `code` and `value` at least; a change: those that change), checked
    by shop.catalogue.coupon_fields (no field names an account), and the `reason` its approval reads."""

    code = optional(serializers.CharField, max_length=30, help_text="a new one's: 3 to 30 capitals, figures, hyphens")
    kind = optional(serializers.ChoiceField, choices=Coupon.Kind.choices)
    value = optional(serializers.DecimalField, max_digits=8, decimal_places=2, help_text="per cent, or rupees off")
    min_order = optional(serializers.DecimalField, max_digits=10, decimal_places=2, help_text="of the books it covers")
    valid_from = optional(serializers.DateTimeField, **TERM_DATES)
    valid_until = optional(serializers.DateTimeField, **TERM_DATES)
    max_uses = optional(serializers.IntegerField, allow_null=True, help_text="orders, all customers together")
    max_uses_per_customer = optional(serializers.IntegerField, allow_null=True, help_text="per account and email")
    is_active = optional(serializers.BooleanField)
    description = optional(
        serializers.CharField, max_length=200, allow_blank=True, help_text="checked for dark patterns"
    )
    note = optional(serializers.CharField, max_length=200, allow_blank=True, help_text="staff's own: who it is for")
    include_products = optional(serializers.ListField, child=serializers.SlugField())
    include_categories = optional(serializers.ListField, child=serializers.SlugField())
    exclude_products = optional(serializers.ListField, child=serializers.SlugField())
    exclude_categories = optional(serializers.ListField, child=serializers.SlugField())
    first_order_only = optional(serializers.BooleanField)
    stackable = optional(serializers.BooleanField, help_text="with automatic offers")
    single_use = optional(serializers.BooleanField, help_text="only through its single-use codes")
    reason = serializers.CharField(max_length=500, help_text="why: its approval reads it")


class CatalogueOfferWriteSerializer(serializers.Serializer):
    """An offer's fields as asked (a new one: its `name` and `value` at least; a change: those that change), checked
    by shop.catalogue.offer_fields (the dark-pattern guardrails), and the `reason` its approval reads."""

    name = optional(serializers.CharField, max_length=80)
    banner = optional(serializers.CharField, max_length=160, allow_blank=True)
    kind = optional(serializers.ChoiceField, choices=Coupon.Kind.choices)
    value = optional(serializers.DecimalField, max_digits=8, decimal_places=2)
    scope = optional(serializers.ChoiceField, choices=Offer.Scope.choices)
    products = optional(serializers.ListField, child=serializers.SlugField())
    categories = optional(serializers.ListField, child=serializers.SlugField())
    collections = optional(serializers.ListField, child=serializers.SlugField())
    min_quantity = optional(serializers.IntegerField)
    min_value = optional(serializers.DecimalField, max_digits=10, decimal_places=2)
    valid_from = optional(serializers.DateTimeField, **TERM_DATES)
    valid_until = optional(serializers.DateTimeField, **TERM_DATES)
    max_uses = optional(serializers.IntegerField, allow_null=True)
    max_uses_per_customer = optional(serializers.IntegerField, allow_null=True)
    combinable = optional(serializers.BooleanField, help_text="with coupons and other offers")
    is_active = optional(serializers.BooleanField)
    show_countdown = optional(serializers.BooleanField, help_text="only with a real end date (valid_until)")
    reason = serializers.CharField(max_length=500, help_text="why: its approval reads it")


def counted(orders):
    """Orders that count as uses (placed, not undone), test orders left out on the live site."""
    from .models import live_mode

    orders = orders.counted()
    return orders.filter(livemode=True) if live_mode() else orders


def coupon_uses(coupons):
    """{coupon id: uses} at once (orders placed, not undone, test orders out)."""
    rows = counted(Order.objects).filter(coupon__in=coupons).values("coupon").annotate(count=Count("pk"))
    return {row["coupon"]: row["count"] for row in rows}


class CouponViewSet(CatalogueView, viewsets.GenericViewSet):
    """Coupons: made and changed through their approvals (coupon.create, coupon.change: beyond your discount limit
    FINANCE approves), their single-use codes (a batch is the job coupon_codes), their versions."""

    serializer_class = CatalogueCouponSerializer
    filterset_class = CouponFilter
    lookup_field = "code"
    lookup_value_regex = "[-a-zA-Z0-9]+"
    permissions = {
        **dict.fromkeys(["list", "retrieve", "history"], "shop.view_coupon"),
        "create": "shop.add_coupon",
        "partial_update": "shop.change_coupon",
        "codes": "shop.view_couponcode",
    }
    throttle_scopes = dict.fromkeys(["create", "partial_update"], "staff_money")

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Coupon.objects.none()
        coupons = scoped(Coupon.objects.all(), self.request.user, "shop.view_coupon")
        coupons = coupons.prefetch_related(
            "include_products", "include_categories", "exclude_products", "exclude_categories"
        )
        return coupons.annotate(
            code_count=Count("codes"), code_used=Count("codes", filter=Q(codes__order__isnull=False))
        )

    def get_object(self):
        found = self.get_queryset().filter(code=str(self.kwargs["code"]).upper()).first()
        if found is None:
            raise exceptions.NotFound()
        return found

    def answer(self, coupons, detail=False):
        uses = coupon_uses(coupons)
        for coupon in coupons:
            coupon.use_count = uses.get(coupon.pk, 0)
        context = {**self.get_serializer_context(), "detail": detail}
        return CatalogueCouponSerializer(coupons, many=True, context=context).data

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()).order_by("-pk"))
        return self.get_paginated_response(self.answer(page))

    @extend_schema(responses=CatalogueCouponSerializer)
    def retrieve(self, request, *args, **kwargs):
        return Response(self.answer([self.get_object()], detail=True)[0])

    @extend_schema(
        request=CatalogueCouponWriteSerializer,
        responses={201: ChangeRequestSerializer, 202: ChangeRequestSerializer},
        parameters=[IDEMPOTENCY],
    )
    def create(self, request, *args, **kwargs):
        """A new coupon (its code, the terms of coupon_fields and the `reason`): 201 made at once within your discount
        limit (its change request executed), 202 waiting for FINANCE beyond it."""
        return ask_terms(self, "coupon.create", request.data.get("code"), request.data)

    @extend_schema(
        request=CatalogueCouponWriteSerializer,
        responses={200: ChangeRequestSerializer, 202: ChangeRequestSerializer},
        parameters=[IDEMPOTENCY],
    )
    def partial_update(self, request, *args, **kwargs):
        """The fields that change and the `reason`: at once (200), or 202 when it makes the discount deeper beyond your
        limit (a coupon switched back on counts). Its code never changes: customers hold it."""
        coupon = self.get_object()
        if "code" in request.data and str(request.data["code"]).upper() != coupon.code:
            raise exceptions.ValidationError({"code": ["A coupon's code stays: customers hold it. Make a new coupon."]})
        return ask_terms(self, "coupon.change", coupon.code, {k: v for k, v in request.data.items() if k != "code"})

    @extend_schema(
        responses=inline_serializer(
            "CatalogueCodePage",
            {
                "next": serializers.URLField(allow_null=True),
                "previous": serializers.URLField(allow_null=True),
                "results": inline_serializer(
                    "CatalogueCode",
                    {
                        "code": serializers.CharField(),
                        "note": serializers.CharField(),
                        "job": serializers.IntegerField(allow_null=True),
                        "created": serializers.DateTimeField(),
                        "used": serializers.BooleanField(),
                        "used_at": serializers.DateTimeField(allow_null=True),
                        "order": serializers.CharField(allow_null=True),
                    },
                    many=True,
                ),
            },
        ),
        parameters=[OpenApiParameter("used", bool), OpenApiParameter("job", int), OpenApiParameter("cursor", str)],
    )
    @action(detail=True, filter_backends=[])
    def codes(self, request, *args, **kwargs):
        """Its single-use codes, newest first (`?used=`, `?job=` a batch): used or not and by which order's number
        (never who: the order has that)."""
        coupon = self.get_object()
        codes = coupon.codes.select_related("order").order_by("-pk")
        if (used := request.query_params.get("used")) in ("true", "1", "false", "0"):
            codes = codes.filter(order__isnull=used in ("false", "0"))
        if (batch := request.query_params.get("job", "")).isdigit():
            codes = codes.filter(job_id=int(batch))
        page = self.paginate_queryset(codes)
        rows = [
            {
                "code": code.code,
                "note": code.note,
                "job": code.job_id,
                "created": code.created,
                "used": code.used,
                "used_at": code.used_at,
                "order": code.order.number if code.order_id else None,
            }
            for code in page
        ]
        return self.get_paginated_response(rows)

    @extend_schema(responses=VERSION_PAGE, parameters=PAGE_PARAMETERS)
    @action(detail=True, filter_backends=[])
    def history(self, request, *args, **kwargs):
        """Its versions, newest first (what changed, who, when, the change request's reason)."""
        return history_page(self, self.get_object(), "coupon", catalogue.COUPON_LISTS)


def ask_terms(view, name, target, body):
    """A coupon's or an offer's approval asked with the body's fields (all but `reason`): the change request as
    staff.api's change-requests/ answers it (201 at once, 202 waiting, 400 failed)."""
    reason = str(body.get("reason") or "").strip()
    if not reason:
        raise exceptions.ValidationError({"reason": ["Say why: its approval reads it."]})
    payload = {key: value for key, value in body.items() if key not in ("reason", "code")}
    change_request, created = approvals.ask(
        name,
        maker=view.human(),
        target=target or "",
        payload=payload,
        reason=reason,
        idempotency_key=view.request.headers.get("Idempotency-Key", ""),
        request=view.request,
    )
    response = accepted(change_request, view)
    if created and response.status_code == status.HTTP_200_OK and name.endswith(".create"):
        response.status_code = status.HTTP_201_CREATED
    return response


# ---- Offers ----


class CatalogueOfferSerializer(serializers.ModelSerializer):
    """An automatic offer: its terms, what it covers, its countdown (only with a real end date), its uses."""

    value = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True)
    min_value = money("min_value.amount")
    products = serializers.SlugRelatedField(slug_field="slug", many=True, read_only=True)
    categories = serializers.SlugRelatedField(slug_field="slug", many=True, read_only=True)
    collections = serializers.SlugRelatedField(slug_field="slug", many=True, read_only=True)
    state = serializers.SerializerMethodField()
    uses = serializers.SerializerMethodField(help_text="orders placed with it, not undone (test orders out)")
    waiting = serializers.SerializerMethodField()

    class Meta:
        model = Offer
        fields = [
            *["id", "name", "banner", "kind", "value", "scope", "products", "categories", "collections"],
            *["min_quantity", "min_value", "valid_from", "valid_until", "max_uses", "max_uses_per_customer"],
            *["combinable", "is_active", "show_countdown", "state", "uses", "waiting", "created", "modified"],
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.ChoiceField(choices=["live", "scheduled", "ended", "inactive"]))
    def get_state(self, obj):
        return term_state(obj)

    def get_uses(self, obj) -> int:
        return getattr(obj, "use_count", 0)

    @extend_schema_field(CatalogueWaitingSerializer(many=True))
    def get_waiting(self, offer):
        return waiting_for("shop.offer", [offer.pk]) if self.context.get("detail") else []


class OfferFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(field_name="name", lookup_expr="icontains", help_text="part of its name")
    state = django_filters.ChoiceFilter(choices=STATES_CHOICES, method="by_state")

    class Meta:
        model = Offer
        fields = ["scope", "combinable"]

    def by_state(self, queryset, name, value):
        return by_state(queryset, value)


class OfferViewSet(CatalogueView, viewsets.GenericViewSet):
    """Automatic offers: made and changed through their approvals (offer.create, offer.change), with the dark-pattern
    guardrails as validation (a countdown only with a real end date that never moves later once shown; no
    guilt-trip or false-urgency words), and their versions."""

    serializer_class = CatalogueOfferSerializer
    filterset_class = OfferFilter
    permissions = {
        **dict.fromkeys(["list", "retrieve", "history"], "shop.view_offer"),
        "create": "shop.add_offer",
        "partial_update": "shop.change_offer",
    }
    throttle_scopes = dict.fromkeys(["create", "partial_update"], "staff_money")

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Offer.objects.none()
        offers = scoped(Offer.objects.all(), self.request.user, "shop.view_offer")
        return offers.prefetch_related("products", "categories", "collections")

    def answer(self, offers, detail=False):
        rows = counted(Order.objects).filter(discount_lines__offer__in=offers).values("discount_lines__offer")
        uses = {row["discount_lines__offer"]: row["count"] for row in rows.annotate(count=Count("pk", distinct=True))}
        for offer in offers:
            offer.use_count = uses.get(offer.pk, 0)
        context = {**self.get_serializer_context(), "detail": detail}
        return CatalogueOfferSerializer(offers, many=True, context=context).data

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()).order_by("-pk"))
        return self.get_paginated_response(self.answer(page))

    @extend_schema(responses=CatalogueOfferSerializer)
    def retrieve(self, request, *args, **kwargs):
        return Response(self.answer([self.get_object()], detail=True)[0])

    @extend_schema(
        request=CatalogueOfferWriteSerializer,
        responses={201: ChangeRequestSerializer, 202: ChangeRequestSerializer},
        parameters=[IDEMPOTENCY],
    )
    def create(self, request, *args, **kwargs):
        """A new offer (the terms of offer_fields and the `reason`): 201 made at once, 202 waiting beyond your limit."""
        return ask_terms(self, "offer.create", "new", request.data)

    @extend_schema(
        request=CatalogueOfferWriteSerializer,
        responses={200: ChangeRequestSerializer, 202: ChangeRequestSerializer},
        parameters=[IDEMPOTENCY],
    )
    def partial_update(self, request, *args, **kwargs):
        """The fields that change and the `reason`: at once, or 202 when it makes the discount deeper beyond your
        limit."""
        return ask_terms(self, "offer.change", str(self.get_object().pk), request.data)

    @extend_schema(responses=VERSION_PAGE, parameters=PAGE_PARAMETERS)
    @action(detail=True, filter_backends=[])
    def history(self, request, *args, **kwargs):
        """Its versions, newest first (its scope's products, categories and collections among the changes)."""
        return history_page(self, self.get_object(), "offer", catalogue.OFFER_LISTS)


# ---- Shipping rates ----


class CatalogueShippingRateSerializer(serializers.ModelSerializer):
    """A flat fee for a group of states (none: every state no other active rate names), free from a value of books.
    The cart shows it, and the line it ships free from, before checkout."""

    fee = money("fee.amount")
    free_above = serializers.SerializerMethodField(help_text="books worth this much or more ship free; null: never")

    class Meta:
        model = ShippingRate
        fields = ["id", "name", "states", "fee", "free_above", "is_active"]
        read_only_fields = fields

    @extend_schema_field(serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True))
    def get_free_above(self, rate):
        return f"{rate.free_above.amount:.2f}" if rate.free_above is not None else None


STATE_CODES = sorted(STATES)  # (the schema names its enum CatalogueStatesEnum: settings.py)


class CatalogueShippingRateWriteSerializer(serializers.Serializer):
    """A rate's fields as given (a new one: its name and fee at least), checked against the other active rates: no
    state in two of them, one rate at most for every other state. `reason` goes into its history."""

    name = serializers.CharField(max_length=60)
    states = serializers.ListField(child=serializers.ChoiceField(choices=STATE_CODES), max_length=40)
    fee = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal(0), max_value=Decimal(99999))
    free_above = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal(0), allow_null=True)
    is_active = serializers.BooleanField()
    reason = serializers.CharField(max_length=500, required=False)

    def __init__(self, *args, rate=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.rate = rate
        if rate is None:
            for name in ("states", "free_above", "is_active"):
                self.fields[name].required = False

    def validate(self, data):
        rate = self.rate
        active = data.get("is_active", rate.is_active if rate else True)
        states = sorted(set(data.get("states", rate.states if rate else [])))
        if "states" in data:
            data["states"] = states
        others = ShippingRate.objects.filter(is_active=True).exclude(pk=getattr(rate, "pk", None))
        if active:
            for other in others:
                if both := set(states) & set(other.states):
                    names = ", ".join(STATES.get(code, code) for code in sorted(both))
                    raise serializers.ValidationError({"states": [f"{names}: in the rate “{other.name}” already."]})
                if not states and not other.states:
                    raise serializers.ValidationError(
                        {"states": [f"“{other.name}” is the rate of every other state already: name the states."]}
                    )
        return data


class ShippingRateViewSet(CatalogueView, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """The delivery rates (no state in two active rates; one rate at most for every other state), with their
    versions. A change applies to carts at once; orders keep the shipping they were charged."""

    serializer_class = CatalogueShippingRateSerializer
    filter_backends = []
    permissions = {
        **dict.fromkeys(["list", "retrieve", "history"], "shop.view_shippingrate"),
        "create": "shop.add_shippingrate",
        "partial_update": "shop.change_shippingrate",
    }

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ShippingRate.objects.none()
        return scoped(ShippingRate.objects.all(), self.request.user, "shop.view_shippingrate").order_by("-pk")

    def write(self, rate, data):
        reason, created = data.pop("reason", ""), rate.pk is None
        changes = {}
        for name, value in data.items():
            held = None if created else getattr(rate, name)
            before = held.amount if hasattr(held, "amount") else held
            if created or before != value:
                changes[name] = [audit.plain(before), audit.plain(value)]
                setattr(rate, name, value)
        if changes:
            with transaction.atomic():
                rate._history_user, rate._change_reason = self.by(), reason[:100]
                rate.save()
                audit.record(
                    f"catalogue.rate_{'created' if created else 'changed'}",
                    request=self.request,
                    target=("shop.shippingrate", rate.pk, rate.name),
                    changes=changes,
                    reason=reason,
                )
        return Response(
            CatalogueShippingRateSerializer(rate).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @extend_schema(request=CatalogueShippingRateWriteSerializer, responses={201: CatalogueShippingRateSerializer})
    def create(self, request, *args, **kwargs):
        asked = CatalogueShippingRateWriteSerializer(data=request.data)
        asked.is_valid(raise_exception=True)
        return self.write(ShippingRate(), dict(asked.validated_data))

    @extend_schema(request=CatalogueShippingRateWriteSerializer, responses=CatalogueShippingRateSerializer)
    def partial_update(self, request, *args, **kwargs):
        rate = self.get_object()
        asked = CatalogueShippingRateWriteSerializer(data=request.data, rate=rate, partial=True)
        asked.is_valid(raise_exception=True)
        return self.write(rate, dict(asked.validated_data))

    @extend_schema(responses=VERSION_PAGE, parameters=PAGE_PARAMETERS)
    @action(detail=True, filter_backends=[])
    def history(self, request, *args, **kwargs):
        """Its versions, newest first."""
        return history_page(self, self.get_object(), "", {})


# ---- Categories, collections, product types and attributes ----


class CatalogueCategorySerializer(serializers.ModelSerializer):
    """A shelf of the tree: `depth` 1 at the top, `parent` the slug above it; its products (on it, not below it)."""

    parent = serializers.SerializerMethodField()
    products = serializers.SerializerMethodField(help_text="on it (not below it)")

    class Meta:
        model = Category
        fields = ["id", "slug", "name", "description", "depth", "parent", "products"]
        read_only_fields = ["id", "depth", "parent", "products"]

    def get_parent(self, category) -> str | None:
        return self.context.get("slugs", {}).get(category.path[: -Category.steplen])

    def get_products(self, category) -> int:
        return getattr(category, "product_count", 0)


class CatalogueCategoryWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    slug = serializers.SlugField(max_length=50)
    description = serializers.CharField(allow_blank=True, max_length=5000, required=False)
    parent = serializers.SlugField(allow_null=True, required=False, help_text="a new one's place: under this one")


MOVES = ["first-child", "last-child", "left", "right"]


class CategoryViewSet(CatalogueView, viewsets.GenericViewSet):
    """The shelves as a tree, in tree order (each followed by those under it): a new one under another (or at the
    top), its name, address and description, and a move with what is under it (treebeard's own move). A product's
    shelves are set on the product."""

    serializer_class = CatalogueCategorySerializer
    lookup_field = "slug"
    filter_backends = []
    pagination_class = None
    permissions = {
        **dict.fromkeys(["list", "retrieve"], "shop.view_category"),
        "create": "shop.add_category",
        **dict.fromkeys(["partial_update", "move"], "shop.change_category"),
    }

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Category.objects.none()
        categories = scoped(Category.objects.all(), self.request.user, "shop.view_category")
        return categories.annotate(product_count=Count("products")).order_by("path")

    def tree(self, categories):
        context = {**self.get_serializer_context(), "slugs": dict(Category.objects.values_list("path", "slug"))}
        return CatalogueCategorySerializer(categories, many=True, context=context).data

    def list(self, request, *args, **kwargs):
        return Response(self.tree(self.get_queryset()))

    @extend_schema(responses=CatalogueCategorySerializer)
    def retrieve(self, request, *args, **kwargs):
        return Response(self.tree([self.get_object()])[0])

    @extend_schema(request=CatalogueCategoryWriteSerializer, responses={201: CatalogueCategorySerializer})
    def create(self, request, *args, **kwargs):
        asked = CatalogueCategoryWriteSerializer(data=request.data)
        asked.is_valid(raise_exception=True)
        data = dict(asked.validated_data)
        parent_slug = data.pop("parent", None)
        if Category.objects.filter(slug=data["slug"]).exists():
            raise exceptions.ValidationError({"slug": ["Another shelf has this address."]})
        parent = Category.objects.filter(slug=parent_slug).first() if parent_slug else None
        if parent_slug and parent is None:
            raise exceptions.ValidationError({"parent": ["No such shelf."]})
        with transaction.atomic():
            node = Category(**data)
            if parent is not None:
                node = Category.objects.add_child(parent, instance=node)
            else:
                node = Category.objects.add_root(instance=node)
            audit.record("catalogue.category_created", request=request, target=("shop.category", node.pk, node.slug))
        return Response(self.tree([self.get_queryset().get(pk=node.pk)])[0], status=status.HTTP_201_CREATED)

    @extend_schema(request=CatalogueCategoryWriteSerializer, responses=CatalogueCategorySerializer)
    def partial_update(self, request, *args, **kwargs):
        """Its name, address (the shop's /shop/category/<slug>/: an old address then answers 404) and description."""
        node = self.get_object()
        asked = CatalogueCategoryWriteSerializer(data=request.data, partial=True)
        asked.is_valid(raise_exception=True)
        data = {key: value for key, value in asked.validated_data.items() if key != "parent"}
        if "slug" in data and Category.objects.filter(slug=data["slug"]).exclude(pk=node.pk).exists():
            raise exceptions.ValidationError({"slug": ["Another shelf has this address."]})
        changes = {name: [getattr(node, name), value] for name, value in data.items() if getattr(node, name) != value}
        if changes:
            with transaction.atomic():
                Category.objects.filter(pk=node.pk).update(**{name: after for name, (_b, after) in changes.items()})
                audit.record(
                    "catalogue.category_changed",
                    request=request,
                    changes=changes,
                    target=("shop.category", node.pk, data.get("slug", node.slug)),
                )
        return Response(self.tree([self.get_queryset().get(pk=node.pk)])[0])

    @extend_schema(
        request=inline_serializer(
            "CatalogueCategoryMove",
            {
                "target": serializers.SlugField(
                    allow_null=True, help_text="the shelf it moves under or beside; null: the top level"
                ),
                "position": serializers.ChoiceField(
                    choices=MOVES, help_text="under the target (first or last), or beside it (left or right)"
                ),
            },
        ),
        responses=CatalogueCategorySerializer(many=True),
    )
    @action(detail=True, methods=["post"])
    def move(self, request, *args, **kwargs):
        """It moves, with every shelf under it: under another (first or last), beside one (left or right), or to the
        top level (no target: first or last there); never under itself. Answers the whole tree."""
        node, target_slug = self.get_object(), request.data.get("target")
        position = request.data.get("position")
        if position not in MOVES:
            raise exceptions.ValidationError({"position": [f"One of {', '.join(MOVES)}."]})
        if target_slug in (None, ""):  # the top level: first (first-child, left) or last there
            first = position in ("first-child", "left")
            target = Category.objects.get_first_root_node() if first else Category.objects.get_last_root_node()
            position = "first-sibling" if first else "last-sibling"
        else:
            target = Category.objects.filter(slug=target_slug).first()
            if target is None:
                raise exceptions.ValidationError({"target": ["No such shelf."]})
            if target.pk == node.pk:
                raise exceptions.ValidationError({"target": ["Not itself."]})
        before = Category.objects.get_parent(node)
        try:
            with transaction.atomic():
                Category.objects.move(node, target, position)
                node.refresh_from_db()
                after = Category.objects.get_parent(node)
                audit.record(
                    "catalogue.category_moved",
                    request=request,
                    target=("shop.category", node.pk, node.slug),
                    changes={"parent": [getattr(before, "slug", None), getattr(after, "slug", None)]},
                )
        except InvalidMoveToDescendant:
            raise exceptions.ValidationError({"target": ["Not under itself, nor under a shelf of its own."]}) from None
        except InvalidPosition:
            raise exceptions.ValidationError({"position": [f"One of {', '.join(MOVES)}."]}) from None
        return Response(self.tree(self.get_queryset()))


class CatalogueCollectionSerializer(serializers.ModelSerializer):
    """A hand-picked list of products in the order staff give them (`products`, slugs)."""

    products = serializers.SerializerMethodField()

    class Meta:
        model = Collection
        fields = ["id", "slug", "name", "description", "is_active", "position", "products", "created", "modified"]
        read_only_fields = ["id", "products", "created", "modified"]

    def get_products(self, collection) -> list[str]:
        return [item.product.slug for item in collection.items.all()]


class CatalogueCollectionWriteSerializer(serializers.ModelSerializer):
    products = serializers.ListField(child=serializers.SlugField(), max_length=200, required=False)

    class Meta:
        model = Collection
        fields = ["slug", "name", "description", "is_active", "position", "products"]


class CollectionViewSet(CatalogueView, viewsets.GenericViewSet):
    """Collections: a new one, its words, whether it is shown, its place among them, its products in their order."""

    serializer_class = CatalogueCollectionSerializer
    lookup_field = "slug"
    filter_backends = []
    permissions = {
        **dict.fromkeys(["list", "retrieve"], "shop.view_collection"),
        "create": "shop.add_collection",
        "partial_update": "shop.change_collection",
    }

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Collection.objects.none()
        collections = scoped(Collection.objects.all(), self.request.user, "shop.view_collection")
        items = Prefetch("items", queryset=CollectionItem.objects.select_related("product").order_by("position", "pk"))
        return collections.prefetch_related(items).order_by("-pk")

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.get_queryset())
        return self.get_paginated_response(CatalogueCollectionSerializer(page, many=True).data)

    @extend_schema(responses=CatalogueCollectionSerializer)
    def retrieve(self, request, *args, **kwargs):
        return Response(CatalogueCollectionSerializer(self.get_object()).data)

    def write(self, collection, data, created):
        slugs = data.pop("products", None)
        products = []
        if slugs is not None:
            found = {product.slug: product for product in Product.objects.filter(slug__in=slugs)}
            if missing := [slug for slug in slugs if slug not in found]:
                raise exceptions.ValidationError({"products": [f"Not found: {', '.join(missing[:10])}."]})
            products = [found[slug] for slug in dict.fromkeys(slugs)]
        changes = {}
        for name, value in data.items():
            if created or getattr(collection, name) != value:
                changes[name] = [None if created else getattr(collection, name), value]
                setattr(collection, name, value)
        with transaction.atomic():
            collection.save()
            if slugs is not None:
                before = [
                    item.product.slug for item in collection.items.select_related("product").order_by("position", "pk")
                ]
                if before != [product.slug for product in products]:
                    collection.items.all().delete()
                    CollectionItem.objects.bulk_create(
                        CollectionItem(collection=collection, product=product, position=index)
                        for index, product in enumerate(products)
                    )
                    changes["products"] = [before, [product.slug for product in products]]
            if changes:
                verb = "created" if created else "changed"
                audit.record(
                    f"catalogue.collection_{verb}",
                    request=self.request,
                    changes=changes,
                    target=("shop.collection", collection.pk, collection.slug),
                )
        return Response(
            CatalogueCollectionSerializer(self.get_queryset().get(pk=collection.pk)).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @extend_schema(request=CatalogueCollectionWriteSerializer, responses={201: CatalogueCollectionSerializer})
    def create(self, request, *args, **kwargs):
        asked = CatalogueCollectionWriteSerializer(data=request.data)
        asked.is_valid(raise_exception=True)
        return self.write(Collection(), dict(asked.validated_data), created=True)

    @extend_schema(request=CatalogueCollectionWriteSerializer, responses=CatalogueCollectionSerializer)
    def partial_update(self, request, *args, **kwargs):
        collection = self.get_object()
        asked = CatalogueCollectionWriteSerializer(collection, data=request.data, partial=True)
        asked.is_valid(raise_exception=True)
        return self.write(collection, dict(asked.validated_data), created=False)


class CatalogueAttributeDefSerializer(serializers.ModelSerializer):
    values = serializers.SerializerMethodField(help_text="products with a value for it")

    class Meta:
        model = Attribute
        fields = ["id", "name", "code", "kind", "choices", "position", "values"]
        read_only_fields = ["id", "values"]

    def get_values(self, attribute) -> int:
        return getattr(attribute, "value_count", 0)


class CatalogueProductTypeSerializer(serializers.ModelSerializer):
    attributes = CatalogueAttributeDefSerializer(many=True, read_only=True)
    products = serializers.SerializerMethodField(help_text="products of the type")

    class Meta:
        model = ProductType
        fields = ["id", "name", "attributes", "products"]
        read_only_fields = ["id", "attributes", "products"]

    def get_products(self, kind) -> int:
        return getattr(kind, "product_count", 0)


class ProductTypeViewSet(CatalogueView, viewsets.GenericViewSet):
    """Product types and the attributes their products have (a printed book: edition year, language …): a new type,
    its name; an attribute added or changed (its code stays once products have values for it: the app filters by
    it; its kind changes only when every value fits the new one)."""

    serializer_class = CatalogueProductTypeSerializer
    filter_backends = []
    pagination_class = None
    permissions = {
        **dict.fromkeys(["list", "retrieve"], "shop.view_producttype"),
        "create": "shop.add_producttype",
        "partial_update": "shop.change_producttype",
        "attributes": "shop.add_attribute",
        "attribute": "shop.change_attribute",
    }

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ProductType.objects.none()
        attributes = Prefetch("attributes", queryset=Attribute.objects.annotate(value_count=Count("values")))
        kinds = scoped(ProductType.objects.all(), self.request.user, "shop.view_producttype")
        return kinds.annotate(product_count=Count("products")).prefetch_related(attributes).order_by("name")

    def answer(self, kind, code=status.HTTP_200_OK):
        return Response(CatalogueProductTypeSerializer(self.get_queryset().get(pk=kind.pk)).data, status=code)

    def list(self, request, *args, **kwargs):
        return Response(CatalogueProductTypeSerializer(self.get_queryset(), many=True).data)

    @extend_schema(responses=CatalogueProductTypeSerializer)
    def retrieve(self, request, *args, **kwargs):
        return Response(CatalogueProductTypeSerializer(self.get_object()).data)

    @extend_schema(
        request=inline_serializer("CatalogueTypeName", {"name": serializers.CharField(max_length=60)}),
        responses={201: CatalogueProductTypeSerializer},
    )
    def create(self, request, *args, **kwargs):
        name = " ".join(str(request.data.get("name", "")).split())[:60]
        if not name:
            raise exceptions.ValidationError({"name": ["Required."]})
        if ProductType.objects.filter(name__iexact=name).exists():
            raise exceptions.ValidationError({"name": ["A type has this name."]})
        with transaction.atomic():
            kind = ProductType.objects.create(name=name)
            audit.record("catalogue.type_created", request=request, target=("shop.producttype", kind.pk, kind.name))
        return self.answer(kind, status.HTTP_201_CREATED)

    @extend_schema(
        request=inline_serializer("CatalogueTypeRename", {"name": serializers.CharField(max_length=60)}),
        responses=CatalogueProductTypeSerializer,
    )
    def partial_update(self, request, *args, **kwargs):
        kind = self.get_object()
        name = " ".join(str(request.data.get("name", kind.name)).split())[:60]
        if not name or ProductType.objects.filter(name__iexact=name).exclude(pk=kind.pk).exists():
            raise exceptions.ValidationError({"name": ["A name no other type has."]})
        if name != kind.name:
            with transaction.atomic():
                changes = {"name": [kind.name, name]}
                kind.name = name
                kind.save(update_fields=["name"])
                audit.record(
                    "catalogue.type_changed",
                    request=request,
                    changes=changes,
                    target=("shop.producttype", kind.pk, kind.name),
                )
        return self.answer(kind)

    def check_attribute(self, attribute):
        try:
            attribute.full_clean(exclude=["product_type"])
        except DjangoValidationError as error:
            raise exceptions.ValidationError(error.message_dict) from None
        if attribute.kind == Attribute.Kind.CHOICE and not attribute.choices.strip():
            raise exceptions.ValidationError({"choices": ["List the choices, one a line."]})
        same = Attribute.objects.filter(product_type=attribute.product_type, code=attribute.code)
        if same.exclude(pk=attribute.pk).exists():
            raise exceptions.ValidationError({"code": ["Another attribute of this type has this code."]})

    @extend_schema(request=CatalogueAttributeDefSerializer, responses={201: CatalogueProductTypeSerializer})
    @action(detail=True, methods=["post"])
    def attributes(self, request, *args, **kwargs):
        """A new attribute of the type: its name, code (the app's filter ?attr_<code>=), kind and choices."""
        kind = self.get_object()
        asked = CatalogueAttributeDefSerializer(data=request.data)
        asked.is_valid(raise_exception=True)
        attribute = Attribute(product_type=kind, **asked.validated_data)
        self.check_attribute(attribute)
        with transaction.atomic():
            attribute.save()
            audit.record(
                "catalogue.attribute_created",
                request=request,
                target=("shop.producttype", kind.pk, kind.name),
                details={"attribute": attribute.code},
            )
        return self.answer(kind, status.HTTP_201_CREATED)

    @extend_schema(
        request=CatalogueAttributeDefSerializer,
        responses=CatalogueProductTypeSerializer,
        parameters=[OpenApiParameter("attribute", int, OpenApiParameter.PATH)],
    )
    @action(detail=True, methods=["patch"], url_path=r"attributes/(?P<attribute>\d+)")
    def attribute(self, request, attribute=None, *args, **kwargs):
        """An attribute changed: its name, choices and place; its code only while no product has a value for it; its
        kind only when every value fits the new kind."""
        kind = self.get_object()
        found = kind.attributes.filter(pk=attribute).first()
        if found is None:
            raise exceptions.NotFound("No such attribute of this type.")
        asked = CatalogueAttributeDefSerializer(found, data=request.data, partial=True)
        asked.is_valid(raise_exception=True)
        data = asked.validated_data
        values = list(found.values.all())
        if "code" in data and data["code"] != found.code and values:
            raise exceptions.ValidationError(
                {"code": ["Products have values for it: its code stays (the app filters by it)."]}
            )
        before = {name: getattr(found, name) for name in data}
        for name, value in data.items():
            setattr(found, name, value)
        self.check_attribute(found)
        for value in values:
            try:
                found.normalise(value.value)
            except DjangoValidationError:
                raise exceptions.ValidationError(
                    {"kind": [f"“{value.value}” does not fit it: change that first."]}
                ) from None
        changes = {name: [before[name], getattr(found, name)] for name in data if before[name] != getattr(found, name)}
        if changes:
            with transaction.atomic():
                found.save()
                audit.record(
                    "catalogue.attribute_changed",
                    request=request,
                    changes=changes,
                    target=("shop.producttype", kind.pk, kind.name),
                    details={"attribute": found.code},
                )
        return self.answer(kind)


# ---- The module's home, its forms' choices, the import ----


class CatalogueSummarySerializer(serializers.Serializer):
    products = serializers.IntegerField(help_text="on sale")
    incomplete = serializers.IntegerField(help_text="the courier cannot be quoted for them (products/?incomplete=1)")
    tax_problems = serializers.IntegerField(help_text="their GST disagrees with the master (products/?tax_problem=1)")
    low_stock = serializers.IntegerField(help_text="books on sale below the low-stock line")
    out_of_stock = serializers.IntegerField(help_text="books on sale with no copy")
    low_stock_line = serializers.IntegerField()
    stock_alerts = serializers.IntegerField(
        allow_null=True, help_text="back-in-stock requests waiting (null: not yours)"
    )
    approvals = serializers.IntegerField(help_text="price, coupon and offer changes waiting for approval")
    prior_price_applies = serializers.BooleanField()
    prior_price_from = serializers.DateField()


TERMS_ACTIONS = ["product.price", "coupon.create", "coupon.change", "offer.create", "offer.change"]


class SummaryView(CatalogueView, viewsets.GenericViewSet):
    """The module's home: what waits (products the courier cannot be quoted for, GST disagreeing with the master, low
    and empty stock, back-in-stock requests, approvals waiting) and whether the prior-price rule is in force."""

    queryset = Product.objects.none()  # (the schema's: it counts the catalogue)
    serializer_class = CatalogueSummarySerializer
    pagination_class = None
    filter_backends = []
    permissions = {"list": VIEW}

    @extend_schema(responses=CatalogueSummarySerializer)
    def list(self, request, *args, **kwargs):
        products = scoped(Product.objects.all(), request.user, VIEW)
        on_sale = products.filter(is_active=True)
        books = on_sale.filter(kind__in=catalogue.GOODS)
        alerts = None
        if request.user.has_perm("shop.view_stockalert"):
            from .models import StockAlert

            alerts = StockAlert.objects.filter(product__in=products).count()
        data = {
            "products": on_sale.count(),
            "incomplete": catalogue.incomplete(on_sale).count(),
            "tax_problems": len(tax.problems(on_sale)),
            "low_stock": books.filter(stock__gt=0, stock__lt=settings.SHOP_LOW_STOCK).count(),
            "out_of_stock": books.filter(stock=0).count(),
            "low_stock_line": settings.SHOP_LOW_STOCK,
            "stock_alerts": alerts,
            "approvals": ChangeRequest.objects.filter(
                action__in=TERMS_ACTIONS, status=ChangeRequest.Status.PENDING
            ).count(),
            "prior_price_applies": pricing.in_force(),
            "prior_price_from": settings.SHOP_PRIOR_PRICE_FROM,
        }
        return Response(CatalogueSummarySerializer(data).data)


class CatalogueOptionSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()


class CatalogueOptionsSerializer(serializers.Serializer):
    kinds = CatalogueOptionSerializer(many=True)
    packaging = CatalogueOptionSerializer(many=True)
    tax_treatments = CatalogueOptionSerializer(many=True)
    subjects = CatalogueOptionSerializer(many=True)
    books = CatalogueOptionSerializer(many=True)
    product_types = CatalogueOptionSerializer(many=True)
    categories = CatalogueOptionSerializer(many=True, help_text="in tree order, the label indented by depth")
    collections = CatalogueOptionSerializer(many=True)
    hsn_codes = CatalogueOptionSerializer(many=True, allow_null=True, help_text="the master's (null: not yours)")
    states = CatalogueOptionSerializer(many=True)


class OptionsView(CatalogueView, viewsets.GenericViewSet):
    """The choices the module's forms offer, in one answer: kinds, packaging, tax treatments, subjects, books,
    product types, shelves, collections, the master's codes (for whoever reads it) and the states."""

    queryset = Product.objects.none()  # (the schema's)
    serializer_class = CatalogueOptionsSerializer
    pagination_class = None
    filter_backends = []
    permissions = {"list": VIEW}

    @extend_schema(responses=CatalogueOptionsSerializer)
    def list(self, request, *args, **kwargs):
        from content.models import Book, Subject

        option = lambda value, label: {"value": str(value), "label": str(label)}  # noqa: E731
        hsn = None
        if request.user.has_perm("shop.view_hsncode"):
            hsn = [option(code.code, f"{code.code} {code.description}") for code in HsnCode.objects.order_by("code")]
        data = {
            "kinds": [option(*choice) for choice in Product.Kind.choices],
            "packaging": [option(*choice) for choice in Product.Packaging.choices],
            "tax_treatments": [option(*choice) for choice in Product.TaxTreatment.choices],
            "subjects": [
                option(subject.pk, subject) for subject in Subject.objects.select_related("board", "class_level")
            ],
            "books": [option(book.slug, book.title) for book in Book.objects.order_by("title")],
            "product_types": [option(kind.pk, kind.name) for kind in ProductType.objects.order_by("name")],
            "categories": [
                option(shelf.slug, f"{'  ' * (shelf.depth - 1)}{shelf.name}")
                for shelf in Category.objects.order_by("path")
            ],
            "collections": [option(item.slug, item.name) for item in Collection.objects.order_by("position", "name")],
            "hsn_codes": hsn,
            "states": [option(code, name) for code, name in sorted(STATES.items(), key=lambda pair: pair[1])],
        }
        return Response(CatalogueOptionsSerializer(data).data)


class ImportView(CatalogueView, viewsets.GenericViewSet):
    """A product CSV (the admin's export format, shop/admin.py ProductResource, with the physical columns) uploaded
    and its dry run started (the job product_import): what each row would make, change or leave, and its errors.
    Its apply is the same job without dry_run, naming the dry run (`dry_run_job`), within 24 hours."""

    queryset = Job.objects.none()  # (the schema's)
    serializer_class = JobSerializer
    permissions = {"create": "shop.import_product"}
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    throttle_scopes = {"create": "staff_bulk"}

    @extend_schema(
        request={"multipart/form-data": inline_serializer("CatalogueImportUpload", {"file": serializers.FileField()})},
        responses={202: JobSerializer},
    )
    def create(self, request, *args, **kwargs):
        user, upload = self.human(), request.FILES.get("file")
        if upload is None:
            raise exceptions.ValidationError({"file": ["Choose a CSV file."]})
        if upload.size > IMPORT_MAX_BYTES:
            raise exceptions.ValidationError({"file": ["At most 2 MB: split the file."]})
        raw = upload.read()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise exceptions.ValidationError(
                {"file": ["Save it as CSV in UTF-8 (a spreadsheet's “CSV UTF-8”)."]}
            ) from None
        from .catalogue_jobs import read_rows

        try:
            rows = read_rows(text)
        except ValueError as error:
            raise exceptions.ValidationError({"file": [str(error)]}) from None
        if len(rows) > IMPORT_MAX_ROWS:
            raise exceptions.ValidationError({"file": [f"At most {IMPORT_MAX_ROWS:,} rows: split the file."]})
        token, digest = secrets.token_hex(16), hashlib.sha256(raw).hexdigest()
        default_storage.save(f"staff/imports/products/{token}.csv", ContentFile(raw))
        audit.record("catalogue.import_uploaded", request=request, details={"rows": len(rows), "sha256": digest})
        job = jobs.start(
            Job.Kind.PRODUCT_IMPORT, {"file": token, "sha256": digest}, user=user, dry_run=True, request=request
        )
        return Response(JobSerializer(job, context={"request": request}).data, status=status.HTTP_202_ACCEPTED)


router = SimpleRouter()
router.register("products", ProductViewSet, basename="catalogue-product")
router.register("stock", StockViewSet, basename="catalogue-stock")
router.register("stock-alerts", StockAlertViewSet, basename="catalogue-stock-alert")
router.register("coupons", CouponViewSet, basename="catalogue-coupon")
router.register("offers", OfferViewSet, basename="catalogue-offer")
router.register("shipping-rates", ShippingRateViewSet, basename="catalogue-shipping-rate")
router.register("categories", CategoryViewSet, basename="catalogue-category")
router.register("collections", CollectionViewSet, basename="catalogue-collection")
router.register("product-types", ProductTypeViewSet, basename="catalogue-product-type")
router.register("summary", SummaryView, basename="catalogue-summary")
router.register("options", OptionsView, basename="catalogue-options")
router.register("import", ImportView, basename="catalogue-import")

urlpatterns = router.urls
