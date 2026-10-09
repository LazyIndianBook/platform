"""The tax module's staff API, under /api/v1/staff/tax/ (API.md "Tax (staff)"; the rules: shop/tax.py), on the staff
app's rules (staff.api.StaffView): a member of staff on the panel's session with a second factor, or an API key with
the view_ permissions; each action's catalogued permission; the admin host only and every refusal an `authz_fail`
event (staff.middleware, by the path); cursor pages; `Cache-Control: no-store`. FINANCE and the owners keep the HSN and
SAC master, cancel documents and run the GSTR-1 export; AUDITOR reads. Each change is an audit event (tax.code_added,
tax.rate_added, tax.document_cancelled; opening a document's PDF, which carries the buyer's name and address, is a
`sensitive_read`). The serializers are the panel's contract."""

from datetime import date

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Count, OuterRef, Q, Subquery
from django.http import Http404
from django.urls import path
from django.utils import timezone
from django_filters import rest_framework as django_filters
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_field
from rest_framework import exceptions, generics, mixins, negotiation, pagination, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.routers import SimpleRouter

from api.schema import AutoSchema
from staff import audit, jobs
from staff.api import StaffView
from staff.backends import scoped
from staff.config import site_setting
from staff.models import Job
from staff.serializers import JobSerializer

from . import invoices, tax
from .models import (
    CreditNote,
    DocumentSeries,
    DocumentType,
    HsnCode,
    HsnRate,
    Invoice,
    Product,
    Taxability,
    TaxThreshold,
    financial_year,
)
from .views import pdf_response

VIEW_HSN, CHANGE_HSN = "shop.view_hsncode", "shop.change_hsncode"
VIEW_SERIES, VIEW_THRESHOLDS = "shop.view_documentseries", "shop.view_taxthreshold"


class StaffSchema(AutoSchema):
    def get_tags(self):
        return ["tax (staff)"]


class TaxView(StaffView):
    schema = StaffSchema()

    def by(self):
        """Who acts: the member of staff (an API key's principal has no row)."""
        return self.request.user if getattr(self.request.user, "pk", None) else None


class AnyAccept(negotiation.DefaultContentNegotiation):
    """A PDF's request may ask for application/pdf: the file answers whatever it accepts (errors stay JSON)."""

    def select_renderer(self, request, renderers, format_suffix=None):
        return renderers[0], renderers[0].media_type


def refused(message):
    return exceptions.ValidationError({"non_field_errors": [message]})


def month_param(value, name="month"):
    """A month of a query ("2026-10"), or None for none; 400 for anything else."""
    if not value:
        return None
    try:
        return date.fromisoformat(f"{value}-01")
    except ValueError:
        raise exceptions.ValidationError({name: ["A month: YYYY-MM."]}) from None


def year_param(value):
    if not value:
        return None
    if not tax.KEY.match(f"XX-{value}-00001"):
        raise exceptions.ValidationError({"financial_year": ["A financial year: 2026-27."]})
    return value


# The HSN and SAC master


class HsnRateSerializer(serializers.ModelSerializer):
    until = serializers.DateField(read_only=True, allow_null=True, help_text="its end, or the day before the next")
    created_by = serializers.IntegerField(source="created_by_id", read_only=True, allow_null=True)

    class Meta:
        model = HsnRate
        fields = ["id", "rate", "taxability", "effective_from", "effective_to", "until", "notification", "serial"]
        fields += ["note", "created", "created_by"]
        read_only_fields = fields


class NewHsnRateSerializer(serializers.ModelSerializer):
    """A new rate of a code: from a day after its latest rate's start (its history is never rewritten), citing the
    notification and serial number that set it."""

    class Meta:
        model = HsnRate
        fields = ["rate", "taxability", "effective_from", "effective_to", "notification", "serial", "note"]
        extra_kwargs = {"serial": {"required": False}, "note": {"required": False}}

    def validate(self, data):
        rate, taxability = data["rate"], data["taxability"]
        if taxability == Taxability.TAXABLE and rate <= 0:
            raise serializers.ValidationError({"rate": ["A taxable supply has a rate above 0."]})
        if taxability != Taxability.TAXABLE and rate != 0:
            raise serializers.ValidationError({"rate": ["Nil-rated, exempt and non-GST supplies are at 0."]})
        if data.get("effective_to") and data["effective_to"] < data["effective_from"]:
            raise serializers.ValidationError({"effective_to": ["It ends after it starts."]})
        code = self.context.get("code")
        latest = HsnRate.objects.filter(hsn_id=code).order_by("-effective_from").first() if code else None
        if latest is not None and data["effective_from"] <= latest.effective_from:
            raise serializers.ValidationError(
                {
                    "effective_from": [
                        f"A new rate starts after the latest one ({tax.long_date(latest.effective_from)}): "
                        "the history is not rewritten."
                    ]
                }  # fmt: skip
            )
        if latest is not None and latest.effective_to and data["effective_from"] <= latest.effective_to:
            raise serializers.ValidationError(
                {
                    "effective_from": [
                        f"The rate from {tax.long_date(latest.effective_from)} runs until "
                        f"{tax.long_date(latest.effective_to)}: start after it."
                    ]
                }  # fmt: skip
            )
        return data


class HsnRateBriefSerializer(serializers.Serializer):
    rate = serializers.DecimalField(max_digits=4, decimal_places=2)
    taxability = serializers.ChoiceField(choices=Taxability.choices)
    effective_from = serializers.DateField()
    notification = serializers.CharField()


class HsnCodeSerializer(serializers.ModelSerializer):
    today = serializers.SerializerMethodField(help_text="its rate today: null when the master has none")
    next_change = serializers.SerializerMethodField(help_text="a rate that starts later, if one is set")
    products = serializers.IntegerField(source="product_count", read_only=True, help_text="the products on it")

    class Meta:
        model = HsnCode
        fields = ["code", "kind", "description", "uqc", "today", "next_change", "products", "created"]
        read_only_fields = fields

    @extend_schema_field(HsnRateBriefSerializer(allow_null=True))
    def get_today(self, code):
        row = self.context.get("today", {}).get(code.code)
        return HsnRateBriefSerializer(row).data if row else None

    @extend_schema_field(HsnRateBriefSerializer(allow_null=True))
    def get_next_change(self, code):
        row = self.context.get("next", {}).get(code.code)
        return HsnRateBriefSerializer(row).data if row else None


class HsnProductSerializer(serializers.ModelSerializer):
    problem = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ["id", "slug", "title", "kind", "gst_rate", "is_active", "problem"]
        read_only_fields = fields

    def get_problem(self, product) -> str:
        return self.context.get("problems", {}).get(product.pk, "")


class HsnCodeDetailSerializer(HsnCodeSerializer):
    rates = serializers.SerializerMethodField(help_text="its history, oldest first")
    linked = serializers.SerializerMethodField(help_text="the products on it, with their disagreement")

    class Meta(HsnCodeSerializer.Meta):
        fields = [*HsnCodeSerializer.Meta.fields, "rates", "linked"]
        read_only_fields = fields

    @extend_schema_field(HsnRateSerializer(many=True))
    def get_rates(self, code):
        return HsnRateSerializer(tax.history(code.code), many=True).data

    @extend_schema_field(HsnProductSerializer(many=True))
    def get_linked(self, code):
        products = list(code.products.order_by("title"))
        context = {"problems": tax.problems(products)}
        return HsnProductSerializer(products, many=True, context=context).data


class NewHsnCodeSerializer(serializers.ModelSerializer):
    """A code new to the master, with its first rate."""

    first_rate = NewHsnRateSerializer()

    class Meta:
        model = HsnCode
        fields = ["code", "kind", "description", "uqc", "first_rate"]
        extra_kwargs = {"uqc": {"required": False}}

    def validate(self, data):
        if (data["kind"] == HsnCode.Kind.SAC) != data["code"].startswith("99"):
            raise serializers.ValidationError({"code": ["A SAC code begins with 99, an HSN code never does."]})
        return data


class ByCode(pagination.CursorPagination):
    page_size, page_size_query_param, max_page_size, ordering = 50, "page_size", 200, "code"


class HsnFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(method="search", label="a code's first digits, or words of its description")
    taxability = django_filters.ChoiceFilter(choices=Taxability.choices, method="today", label="taxability today")

    class Meta:
        model = HsnCode
        fields = ["kind"]

    def search(self, queryset, name, value):
        value = value.strip()[:50]
        return queryset.filter(Q(code__startswith=value) | Q(description__icontains=value)) if value else queryset

    def today(self, queryset, name, value):
        latest = HsnRate.objects.filter(hsn=OuterRef("pk"), effective_from__lte=timezone.localdate())
        latest = latest.order_by("-effective_from").values("taxability")[:1]
        return queryset.annotate(taxability_now=Subquery(latest)).filter(taxability_now=value)


class HsnViewSet(TaxView, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                 viewsets.GenericViewSet):  # fmt: skip
    """The HSN and SAC master: codes with their rate today and any scheduled change (filters kind, taxability today,
    q); one with its history and the products on it; a new code with its first rate, a new rate of a code (FINANCE:
    shop.change_hsncode). Rates are never edited or deleted."""

    queryset = HsnCode.objects.annotate(product_count=Count("products"))
    serializer_class = HsnCodeSerializer
    pagination_class = ByCode
    filterset_class = HsnFilter
    lookup_field = "code"
    permissions = {**dict.fromkeys(["list", "retrieve"], VIEW_HSN), **dict.fromkeys(["create", "rates"], CHANGE_HSN)}

    def get_serializer_class(self):
        return HsnCodeDetailSerializer if self.action == "retrieve" else HsnCodeSerializer

    def context_for(self, codes):
        today = timezone.localdate()
        upcoming = {}
        for row in HsnRate.objects.filter(hsn_id__in=codes, effective_from__gt=today).order_by("-effective_from"):
            upcoming[row.hsn_id] = row  # the soonest wins: read last
        return {**self.get_serializer_context(), "today": tax.rates_on(codes, today), "next": upcoming}

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        context = self.context_for([code.code for code in page])
        return self.get_paginated_response(HsnCodeSerializer(page, many=True, context=context).data)

    def retrieve(self, request, *args, **kwargs):
        code = self.get_object()
        return Response(HsnCodeDetailSerializer(code, context=self.context_for([code.code])).data)

    def detail_of(self, code, created=False):
        code = self.get_queryset().get(pk=code)
        data = HsnCodeDetailSerializer(code, context=self.context_for([code.code])).data
        return Response(data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @extend_schema(request=NewHsnCodeSerializer, responses={201: HsnCodeDetailSerializer})
    def create(self, request, *args, **kwargs):
        asked = NewHsnCodeSerializer(data=request.data)
        asked.is_valid(raise_exception=True)
        data, user = asked.validated_data, self.by()
        first = data.pop("first_rate")
        try:
            with transaction.atomic():
                code = HsnCode.objects.create(**data)
                HsnRate.objects.create(hsn=code, created_by=user, **first)
                audit.record("tax.code_added", request=request, target=code, details=audit.plain(first))
        except IntegrityError:
            raise exceptions.ValidationError({"code": [f"{data['code']} is on the master already."]}) from None
        return self.detail_of(code.code, created=True)

    @extend_schema(request=NewHsnRateSerializer, responses={201: HsnCodeDetailSerializer})
    @action(detail=True, methods=["post"])
    def rates(self, request, *args, **kwargs):
        code = self.get_object()
        with transaction.atomic():
            HsnCode.objects.select_for_update().get(pk=code.pk)  # one new rate at a time per code
            asked = NewHsnRateSerializer(data=request.data, context={"code": code.code})
            asked.is_valid(raise_exception=True)
            row = HsnRate.objects.create(hsn=code, created_by=self.by(), **asked.validated_data)
            details = {"rate": row.pk, **audit.plain(asked.validated_data)}
            audit.record("tax.rate_added", request=request, target=code, details=details)
        return self.detail_of(code.code, created=True)


class TaxProblemSerializer(serializers.ModelSerializer):
    problem = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ["id", "slug", "title", "kind", "hsn_code", "gst_rate", "is_active", "tax_treatment", "problem"]
        read_only_fields = fields

    def get_problem(self, product) -> str:
        return self.context["problems"][product.pk]


class ProblemsView(TaxView, generics.GenericAPIView):
    """The products whose GST disagrees with the master today, with why (the catalogue's red chip; ?all=true: the
    ones off sale too). Not paged: the whole catalogue is checked at once."""

    queryset = Product.objects.none()  # (for the schema: the view reads the whole catalogue)
    serializer_class = TaxProblemSerializer
    permissions = {"GET": VIEW_HSN}
    pagination_class = None

    @extend_schema(
        parameters=[OpenApiParameter("all", bool, description="also the products off sale")],
        responses=TaxProblemSerializer(many=True),
    )
    def get(self, request, *args, **kwargs):
        # ponytail: the catalogue in memory (tens of products); page it past a few thousand
        products = Product.objects.order_by("title")
        if request.query_params.get("all") not in ("true", "1"):
            products = products.filter(is_active=True)
        products = list(products)
        found = tax.problems(products)
        rows = [product for product in products if product.pk in found]
        return Response(TaxProblemSerializer(rows, many=True, context={"problems": found}).data)


# Documents


DOCUMENT_KINDS = [("invoice", "invoice"), ("credit_note", "credit note")]


class TaxDocumentSerializer(serializers.Serializer):
    key = serializers.CharField(help_text="its number with dashes: the address of tax/documents/{number}/")
    kind = serializers.ChoiceField(choices=DOCUMENT_KINDS)
    id = serializers.IntegerField()
    number = serializers.CharField()
    series = serializers.CharField()
    financial_year = serializers.CharField()
    serial = serializers.IntegerField()
    document_type = serializers.ChoiceField(choices=DocumentType.choices, allow_blank=True)
    test = serializers.BooleanField(help_text="the test series: not a tax document")
    date = serializers.DateField()
    order = serializers.CharField(help_text="the order's number")
    against = serializers.CharField(allow_null=True, help_text="a credit note's invoice")
    place_of_supply = serializers.CharField(help_text="a state code: the billing state")
    total = serializers.DecimalField(max_digits=12, decimal_places=2)
    taxable_value = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True)
    exempt_value = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True)
    tax_amount = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True)
    cancelled_at = serializers.DateTimeField(allow_null=True)
    cancel_reason = serializers.CharField()
    cancelled_by = serializers.IntegerField(allow_null=True)
    has_pdf = serializers.BooleanField()

    def to_representation(self, document):
        note = isinstance(document, CreditNote)
        order = document.invoice.order if note else document.order
        total = min(document.refund.amount.amount, order.total.amount) if note else order.total.amount
        return super().to_representation(
            {
                "key": tax.key_of(document),
                "kind": "credit_note" if note else "invoice",
                "id": document.pk,
                "number": document.number,
                "series": document.series,
                "financial_year": document.financial_year.removeprefix("T"),
                "serial": document.serial,
                "document_type": document.document_type,
                "test": document.is_test,
                "date": timezone.localdate(document.created),
                "order": order.number,
                "against": document.invoice.number if note else None,
                "place_of_supply": invoices.place(order),
                "total": total,
                "taxable_value": document.taxable_value,
                "exempt_value": document.exempt_value,
                "tax_amount": document.tax_amount,
                "cancelled_at": document.cancelled_at,
                "cancel_reason": document.cancel_reason,
                "cancelled_by": document.cancelled_by_id,
                "has_pdf": bool(document.pdf),
            }
        )


class TaxLineSerializer(serializers.Serializer):
    title = serializers.CharField()
    bundle = serializers.CharField(help_text="a split bundle's title, for its components")
    hsn_code = serializers.CharField()
    quantity = serializers.IntegerField()
    rate = serializers.DecimalField(max_digits=4, decimal_places=2)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, help_text="after its discount, tax included")
    taxable = serializers.DecimalField(max_digits=12, decimal_places=2)
    tax = serializers.DecimalField(max_digits=12, decimal_places=2)


class TaxChargeSerializer(serializers.Serializer):
    label = serializers.CharField()
    rate = serializers.DecimalField(max_digits=4, decimal_places=2)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    taxable = serializers.DecimalField(max_digits=12, decimal_places=2)
    tax = serializers.DecimalField(max_digits=12, decimal_places=2)


class TaxDocumentDetailSerializer(TaxDocumentSerializer):
    title = serializers.CharField()
    lines = TaxLineSerializer(many=True)
    charges = TaxChargeSerializer(many=True, help_text="the shipping, following the goods it carries")
    round_off = serializers.DecimalField(max_digits=12, decimal_places=2)
    checks = serializers.ListField(child=serializers.CharField(), help_text="what Rule 46 asks that it misses")
    credit_notes = serializers.ListField(child=serializers.CharField(), help_text="an invoice's credit notes")

    def to_representation(self, document):
        note = isinstance(document, CreditNote)
        data = invoices.credit_note_context(document) if note else invoices.context(document)
        lines = [
            {
                "title": entry["item"].title,
                "bundle": entry["bundle"],
                "hsn_code": entry["item"].hsn_code,
                "quantity": entry["item"].quantity,
                "rate": entry["item"].gst_rate,
                "amount": entry["amount"],
                "taxable": entry["taxable"],
                "tax": entry["cgst"] + entry["sgst"] + entry["igst"],
            }
            for entry in data["lines"]
        ]
        charges = [{**charge, "tax": charge["cgst"] + charge["sgst"] + charge["igst"]} for charge in data["charges"]]
        base = TaxDocumentSerializer(document).data
        extra = {
            "title": data["title"],
            "lines": TaxLineSerializer(lines, many=True).data,
            "charges": TaxChargeSerializer(charges, many=True).data,
            "round_off": f"{(0 if note else data['round_off']):.2f}",
            "checks": tax.document_checks(document, data),
            "credit_notes": [] if note else list(document.credit_notes.order_by("pk").values_list("number", flat=True)),
        }
        return {**base, **extra}


class CancelSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=5, max_length=300, help_text="why: kept with the document")


DOCUMENT_FILTERS = [
    OpenApiParameter("kind", str, enum=["invoice", "credit_note"], description="invoices (by default) or credit notes"),
    OpenApiParameter("series", str, description="a prefix: EL, CN, TI …"),
    OpenApiParameter("document_type", str, enum=DocumentType.values),
    OpenApiParameter("month", str, description="YYYY-MM: the documents dated in it"),
    OpenApiParameter("financial_year", str, description="2026-27"),
    OpenApiParameter("cancelled", bool),
    OpenApiParameter("test", bool, description="the test series instead of the real one"),
    OpenApiParameter("search", str, description="a number's beginning, or an order's number"),
]


def documents(kind, params):
    """The documents of a kind as the list's filters narrow them (newest first)."""
    note = kind == "credit_note"
    model = CreditNote if note else Invoice
    rows = model.objects.select_related(*(["invoice__order", "refund"] if note else ["order"]))
    test = params.get("test") in ("true", "1")
    rows = rows.filter(financial_year__startswith="T") if test else rows.exclude(financial_year__startswith="T")
    if series := params.get("series"):
        rows = rows.filter(series=series.upper()[:2])
    if kind_of := params.get("document_type"):
        if kind_of not in DocumentType.values:
            raise exceptions.ValidationError({"document_type": [f"One of: {', '.join(DocumentType.values)}."]})
        rows = rows.filter(document_type=kind_of)
    if month := month_param(params.get("month")):
        rows = rows.filter(created__year=month.year, created__month=month.month)
    if year := year_param(params.get("financial_year")):
        rows = rows.filter(financial_year=f"T{year}" if test else year)
    if (cancelled := params.get("cancelled")) in ("true", "1", "false", "0"):
        rows = rows.filter(cancelled_at__isnull=cancelled in ("false", "0"))
    if search := str(params.get("search") or "").strip()[:20]:
        order = "invoice__order__number" if note else "order__number"
        number = tax.parse_key(search) or search.upper()
        rows = rows.filter(Q(number__startswith=number) | Q(**{order: search.upper()}))
    return rows


class DocumentViewSet(TaxView, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """The storefront's tax documents, newest first: invoices (by default) or credit notes (?kind=credit_note), by
    series, type, month, year, cancelled or not; the test series only with ?test=true. One by its number (dashes for
    its slashes: EL-2026-27-00001) with its lines, charges and Rule 46 checks; its PDF (a look at the buyer's name and
    address: audited); cancel one with a reason (staff.cancel_document, high: re-authenticated). A cancelled document
    keeps its number; the order and its refunds are left as they are."""

    serializer_class = TaxDocumentSerializer
    lookup_field = "number"
    lookup_value_regex = r"[A-Za-z0-9-]+"
    filter_backends = []
    permissions = {
        **dict.fromkeys(["list", "retrieve", "pdf"], VIEW_SERIES),
        "cancel": "staff.cancel_document",
    }

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Invoice.objects.none()
        kind = self.request.query_params.get("kind") or "invoice"
        if kind not in ("invoice", "credit_note"):
            raise exceptions.ValidationError({"kind": ["invoice or credit_note."]})
        return scoped(documents(kind, self.request.query_params), self.request.user, VIEW_SERIES)

    @extend_schema(parameters=DOCUMENT_FILTERS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_object(self):
        number = tax.parse_key(self.kwargs["number"])
        if number is None:
            raise Http404
        for model, related in ((Invoice, ["order"]), (CreditNote, ["invoice__order", "refund"])):
            found = scoped(model.objects.select_related(*related).filter(number=number), self.request.user, VIEW_SERIES)
            if document := found.first():
                return document
        raise Http404

    @extend_schema(responses=TaxDocumentDetailSerializer)
    def retrieve(self, request, *args, **kwargs):
        return Response(TaxDocumentDetailSerializer(self.get_object()).data)

    @extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"], content_negotiation_class=AnyAccept)
    def pdf(self, request, *args, **kwargs):
        """The document's PDF as issued (cancelled: marked so): it names the buyer, so the look is audited."""
        document = self.get_object()
        response = pdf_response(document)
        audit.record("sensitive_read", request=request, target=tax.document_target(document), details={"what": "pdf"})
        return response

    @extend_schema(request=CancelSerializer, responses=TaxDocumentSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, *args, **kwargs):
        asked = CancelSerializer(data=request.data)
        asked.is_valid(raise_exception=True)
        try:
            document = tax.cancel(self.get_object(), asked.validated_data["reason"], by=self.human(), request=request)
        except ValueError as error:
            raise refused(str(error)) from error
        return Response(TaxDocumentSerializer(document).data)


# Table 13, the thresholds, the calendar


class SeriesRowSerializer(serializers.Serializer):
    series = serializers.CharField()
    nature = serializers.CharField(help_text="table 13's nature of document")
    document_type = serializers.ChoiceField(choices=DocumentSeries.Type.choices)
    financial_year = serializers.CharField()
    first = serializers.CharField(help_text="Sr. No. from")
    last = serializers.CharField(help_text="Sr. No. to")
    total = serializers.IntegerField()
    cancelled = serializers.IntegerField()
    next_number = serializers.IntegerField(allow_null=True, help_text="the series' next serial")


class SeriesRegisterSerializer(serializers.Serializer):
    financial_year = serializers.CharField()
    month = serializers.CharField(allow_null=True)
    series_from = serializers.CharField(help_text="SHOP_SERIES_FROM_FY: one series a type from this year")
    prefixes = serializers.DictField(child=serializers.CharField(), help_text="SHOP_SERIES_PREFIXES")
    rows = SeriesRowSerializer(many=True)


class SeriesView(TaxView, generics.GenericAPIView):
    """Table 13, the documents issued: each series of the real documents of a financial year (?financial_year=, this
    year's by default), or of one month of it (?month=YYYY-MM): its first and last number, how many, how many
    cancelled, and its next serial."""

    serializer_class = SeriesRegisterSerializer
    permissions = {"GET": VIEW_SERIES}
    pagination_class = None

    @extend_schema(
        parameters=[
            OpenApiParameter("financial_year", str, description="2026-27: this year's by default"),
            OpenApiParameter("month", str, description="YYYY-MM: one month of it"),
        ]
    )
    def get(self, request, *args, **kwargs):
        month = month_param(request.query_params.get("month"))
        year = year_param(request.query_params.get("financial_year")) or financial_year(month or timezone.localdate())
        rows = []
        for model, kind in ((Invoice, None), (CreditNote, DocumentSeries.Type.CREDIT_NOTE)):
            found = scoped(model.objects.filter(financial_year=year), request.user, VIEW_SERIES)
            if month:
                found = found.filter(created__year=month.year, created__month=month.month)
            grouped = found.values("series").annotate(
                total=Count("pk"), cancelled=Count("pk", filter=Q(cancelled_at__isnull=False))
            )
            for group in grouped.order_by("series"):
                ends = found.filter(series=group["series"]).order_by("serial")
                series = DocumentSeries.objects.filter(prefix=group["series"], financial_year=year).first()
                series_type = series.document_type if series else (kind or DocumentSeries.Type.INVOICE)
                rows.append(
                    {
                        "series": group["series"],
                        "nature": tax.nature(series_type),
                        "document_type": series_type,
                        "financial_year": year,
                        "first": ends.values_list("number", flat=True).first(),
                        "last": ends.reverse().values_list("number", flat=True).first(),
                        "total": group["total"],
                        "cancelled": group["cancelled"],
                        "next_number": series.next_number if series else None,
                    }
                )
        body = {
            "financial_year": year,
            "month": f"{month:%Y-%m}" if month else None,
            "series_from": settings.SHOP_SERIES_FROM_FY,
            "prefixes": settings.SHOP_SERIES_PREFIXES,
            "rows": rows,
        }
        return Response(SeriesRegisterSerializer(body).data)


class ThresholdRowSerializer(serializers.ModelSerializer):
    label = serializers.CharField(source="get_line_display")
    count = serializers.SerializerMethodField(help_text="a number of documents, not rupees")

    class Meta:
        model = TaxThreshold
        fields = ["line", "label", "value", "limit", "crossed", "count", "detail", "date", "financial_year"]
        read_only_fields = fields

    def get_count(self, row) -> bool:
        return row.line in TaxThreshold.COUNTS


class ThresholdCardSerializer(serializers.Serializer):
    as_of = serializers.DateField(allow_null=True, help_text="the night of the latest look; null: none yet")
    financial_year = serializers.CharField()
    previous_year = serializers.CharField()
    previous_turnover = serializers.DecimalField(max_digits=14, decimal_places=2)
    qrmp = serializers.BooleanField(help_text="SHOP_GST_QRMP")
    hsn_digits = serializers.IntegerField(help_text="SHOP_HSN_DIGITS")
    basis = serializers.CharField(help_text="what the turnover counts")
    rows = ThresholdRowSerializer(many=True)


BASIS = (
    "Aggregate turnover as GST counts it: the storefront's invoices less their credit notes, taxable and exempt, "
    "without the tax. ERPNext's B2B sales join it at the cut-over."
)


class ThresholdsView(TaxView, generics.GenericAPIView):
    """The threshold card: the latest night's lines (₹2, 4, 5 and 10 crore of turnover this financial year; invoices
    above ₹1 lakh to another state; taxable goods above ₹50,000 in a parcel), the year before's turnover, the QRMP
    switch and the HSN digits documents print."""

    serializer_class = ThresholdCardSerializer
    permissions = {"GET": VIEW_THRESHOLDS}
    pagination_class = None

    def get(self, request, *args, **kwargs):
        card = tax.thresholds_card()
        body = {**card, "qrmp": site_setting("SHOP_GST_QRMP"), "hsn_digits": settings.SHOP_HSN_DIGITS, "basis": BASIS}
        return Response(ThresholdCardSerializer(body).data)


class TaxCalendarItemSerializer(serializers.Serializer):
    key = serializers.CharField()
    title = serializers.CharField()
    covers = serializers.CharField(help_text="the period or year it is for")
    due = serializers.DateField()
    applies = serializers.BooleanField()
    note = serializers.CharField()
    past = serializers.BooleanField()


class TaxCalendarSerializer(serializers.Serializer):
    month = serializers.CharField()
    qrmp = serializers.BooleanField()
    items = TaxCalendarItemSerializer(many=True)
    crossed = ThresholdRowSerializer(many=True, help_text="the lines the threshold monitor finds crossed")


class CalendarView(TaxView, generics.GenericAPIView):
    """What is due in a month (?month=YYYY-MM, this one by default): the returns, payments and cut-offs computed from
    the law's dates and the QRMP switch, and the threshold lines crossed this year."""

    serializer_class = TaxCalendarSerializer
    permissions = {"GET": VIEW_THRESHOLDS}
    pagination_class = None

    @extend_schema(parameters=[OpenApiParameter("month", str, description="YYYY-MM: this month by default")])
    def get(self, request, *args, **kwargs):
        month = month_param(request.query_params.get("month")) or timezone.localdate().replace(day=1)
        card = tax.thresholds_card()
        body = {
            "month": f"{month:%Y-%m}",
            "qrmp": site_setting("SHOP_GST_QRMP"),
            "items": tax.calendar(month.year, month.month),
            "crossed": [row for row in card["rows"] if row.crossed],
        }
        return Response(TaxCalendarSerializer(body).data)


# The GSTR-1 export


class Gstr1Serializer(serializers.Serializer):
    month = serializers.CharField(help_text="YYYY-MM: a month that has begun")
    months = serializers.ChoiceField(choices=[1, 3], default=1, help_text="3: the quarter ending with `month`")
    dry_run = serializers.BooleanField(default=False, help_text="count the documents, write nothing")

    def validate(self, data):
        return {**gstr1_period(data), "dry_run": data["dry_run"]}


def gstr1_period(params):
    """A GSTR-1 job's params ({month, months}) checked: a month that has begun; a quarter ends with June, September,
    December or March. Raises 400 with the field's words."""
    month, months = params.get("month"), params.get("months", 1)
    try:
        first = date.fromisoformat(f"{month}-01")
    except TypeError, ValueError:
        raise serializers.ValidationError({"params": {"month": ["A month: YYYY-MM."]}}) from None
    if first > timezone.localdate():
        raise serializers.ValidationError({"params": {"month": ["A month that has begun."]}})
    if str(months) not in ("1", "3"):
        raise serializers.ValidationError({"params": {"months": ["1 (a month) or 3 (a quarter)."]}})
    if int(months) == 3 and first.month not in tax.QUARTER_ENDS:
        raise serializers.ValidationError(
            {"params": {"months": ["A quarter ends with June, September, December or March."]}}
        )
    return {"month": f"{first:%Y-%m}", "months": int(months)}


class Gstr1View(TaxView, generics.GenericAPIView):
    """Run the GSTR-1 export for a month, or the quarter ending with it, as a background job (staff.run_gstr1): 202
    with the job; its file, the Offline Tool's CSV files zipped, through the job's result link. Above the starter's
    export_rows the job waits for an approver first (its change_request_id)."""

    serializer_class = JobSerializer
    permissions = {"POST": "staff.run_gstr1"}
    throttle_scope = "staff_export"

    @extend_schema(request=Gstr1Serializer, responses={202: JobSerializer})
    def post(self, request, *args, **kwargs):
        user = self.human()
        asked = Gstr1Serializer(data=request.data)
        asked.is_valid(raise_exception=True)
        data = asked.validated_data
        params = {"month": data["month"], "months": data["months"]}
        job = jobs.start(Job.Kind.GSTR1_EXPORT, params, user=user, dry_run=data["dry_run"], request=request)
        return Response(JobSerializer(job, context={"request": request}).data, status=status.HTTP_202_ACCEPTED)


router = SimpleRouter()
router.register("hsn", HsnViewSet, basename="hsn")
router.register("documents", DocumentViewSet, basename="document")
app_name = "tax"
urlpatterns = [  # under /api/v1/staff/tax/ (staff/urls.py), namespace "staff:tax"
    path("problems/", ProblemsView.as_view(), name="problems"),
    path("series/", SeriesView.as_view(), name="series"),
    path("thresholds/", ThresholdsView.as_view(), name="thresholds"),
    path("calendar/", CalendarView.as_view(), name="calendar"),
    path("gstr1/", Gstr1View.as_view(), name="gstr1"),
    *router.urls,
]
