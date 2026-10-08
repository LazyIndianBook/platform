"""REST API v1 for the shop: the books on sale (public); for a signed-in customer with a confirmed email address the
cart, the saved addresses and the orders, paid with Razorpay's mobile SDK or cash on delivery; and the guests' order
lookup. Every step goes through shop.cart, shop.services and shop.payments, as on the website. The Razorpay webhook
stays the website's (/shop/webhooks/razorpay/): it completes an order whatever the client did."""

from django.conf import settings
from django.db.models import Prefetch
from django.urls import reverse as site_reverse
from django.utils.cache import add_never_cache_headers
from django_fsm import TransitionNotAllowed
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_field
from localflavor.in_.in_states import STATE_CHOICES
from phonenumber_field.serializerfields import PhoneNumberField
from rest_framework import exceptions, mixins, negotiation, permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.reverse import reverse

from shop import payments, services
from shop.cart import get_cart, set_quantity, totals
from shop.models import (
    Address,
    BundleItem,
    Cart,
    CartItem,
    Coupon,
    CreditNote,
    Order,
    OrderItem,
    Product,
    validate_indian_mobile,
)
from shop.views import lookup_allowed, over_limit, pdf_response

from .views import VerifiedEmail

CUSTOMER = [permissions.IsAuthenticated, VerifiedEmail]
NOT_PAYABLE = "This order is not waiting for an online payment."


class ShopOpen(permissions.BasePermission):
    """While SHOP_OPEN is off only staff change carts, check out and pay (shop.views.shop_open)."""

    message = "The shop opens soon."

    def has_permission(self, request, view):
        return settings.SHOP_OPEN or request.method in permissions.SAFE_METHODS or request.user.is_staff


NOT_CONFIRMED = (
    "We could not confirm this payment. If money was taken from your account, we confirm the order or refund it "
    "by ourselves within a few minutes."
)


def rupees(source=None, **kwargs):
    """Money: a decimal string in rupees, "299.00"."""
    return serializers.DecimalField(source=source, max_digits=10, decimal_places=2, read_only=True, **kwargs)


def refuse(message):
    """A shop rule the customer must satisfy: 400 {"non_field_errors": [message]}, DRF's format."""
    return serializers.ValidationError({"non_field_errors": [message]})


class PaymentServiceUnavailable(exceptions.APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "The payment service could not be reached."


class AnyAccept(negotiation.DefaultContentNegotiation):
    """The PDF downloads answer whatever the client accepts; their errors are JSON."""

    def select_renderer(self, request, renderers, format_suffix=None):
        return renderers[0], renderers[0].media_type


def can_pay(order):
    return order.status == Order.Status.PENDING and not order.is_cod and order.placed_at is None


def media_url(request, file):
    return request.build_absolute_uri(site_reverse("shop:media", args=[file.name])) if file else None


# Products


class BundleItemSerializer(serializers.ModelSerializer):
    product = serializers.SlugRelatedField(slug_field="slug", read_only=True)
    title = serializers.CharField(source="product.title", read_only=True)

    class Meta:
        model = BundleItem
        fields = ["product", "title", "quantity"]


class ProductSerializer(serializers.ModelSerializer):
    """A book on sale. `in_stock` says whether copies can be ordered (a bundle: of each of its books); the number of
    copies is not given."""

    subject = serializers.CharField(source="subject.code", read_only=True, allow_null=True)
    book = serializers.SlugRelatedField(slug_field="slug", read_only=True, help_text="the papers inside: books/<slug>/")
    description = serializers.CharField(read_only=True, help_text="Markdown")
    cover = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    mrp = rupees("mrp.amount")
    price = rupees("price.amount")
    saving_percent = serializers.IntegerField(read_only=True)
    in_stock = serializers.SerializerMethodField()
    bundle_items = BundleItemSerializer(many=True, read_only=True)
    web_url = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "slug",
            "title",
            "kind",
            "subject",
            "book",
            "isbn",
            "pages",
            "description",
            "cover",
            "images",
            "mrp",
            "price",
            "saving_percent",
            "gst_rate",
            "hsn_code",
            "in_stock",
            "bundle_items",
            "web_url",
        ]

    @extend_schema_field(serializers.URLField(allow_null=True))
    def get_cover(self, product):
        return media_url(self.context["request"], product.cover)

    @extend_schema_field(
        serializers.ListField(child=serializers.DictField(child=serializers.CharField()), help_text="url and alt")
    )
    def get_images(self, product):
        return [{"url": media_url(self.context["request"], i.image), "alt": i.alt} for i in product.images.all()]

    def get_in_stock(self, product) -> bool:
        if product.kind != Product.Kind.BUNDLE:
            return product.stock > 0
        return min((item.product.stock // item.quantity for item in product.bundle_items.all()), default=0) > 0

    def get_web_url(self, product) -> str:
        return self.context["request"].build_absolute_uri(product.get_absolute_url())


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    """The books on sale, with their prices, pictures, what a bundle holds, and whether they are in stock."""

    permission_classes = [permissions.AllowAny]
    queryset = (
        Product.objects.filter(is_active=True)
        .select_related("subject", "book")
        .prefetch_related("images", Prefetch("bundle_items", queryset=BundleItem.objects.select_related("product")))
    )
    serializer_class = ProductSerializer
    lookup_field = "slug"
    filterset_fields = ["kind", "subject"]
    search_fields = ["title"]
    ordering_fields = ["title", "price"]  # only these: any other name is ignored


# Cart


class CartLineSerializer(serializers.Serializer):
    product = serializers.SlugField(source="product.slug")
    title = serializers.CharField(source="product.title")
    price = rupees("product.price.amount")
    quantity = serializers.IntegerField()
    total = rupees()


class CartSerializer(serializers.Serializer):
    """The cart at today's prices (shop.cart.totals, as the website)."""

    items = CartLineSerializer(source="lines", many=True)
    count = serializers.IntegerField(help_text="copies")
    coupon = serializers.SerializerMethodField()
    coupon_problem = serializers.CharField(allow_null=True, help_text="why the coupon does not apply now")
    subtotal = rupees()
    discount = rupees()
    shipping = rupees(allow_null=True, help_text="null without ?state=")
    total = rupees()
    problems = serializers.ListField(child=serializers.CharField(), help_text="what stops an order: stock, sale")

    def get_coupon(self, result) -> str | None:
        cart = self.context["cart"]
        return cart.coupon.code if cart and cart.coupon else None


class CartItemSerializer(serializers.Serializer):
    product = serializers.SlugRelatedField(slug_field="slug", queryset=Product.objects.filter(is_active=True))
    quantity = serializers.IntegerField(min_value=1, max_value=CartItem.MAX_QUANTITY, default=1)


class QuantitySerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=0, max_value=CartItem.MAX_QUANTITY, help_text="0 removes the book")


class CouponSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=30)


STATE = OpenApiParameter("state", str, description="two-letter state code (AS): adds the shipping for it")
PRODUCT = OpenApiParameter("product", str, OpenApiParameter.PATH, description="the product's slug")


class CartViewSet(viewsets.GenericViewSet):
    """The signed-in customer's cart, the same as on the website. Every answer is the whole cart; `?state=` adds the
    shipping. Carts of visitors without an account stay on the website."""

    permission_classes = [*CUSTOMER, ShopOpen]
    serializer_class = CartSerializer
    pagination_class = None
    filter_backends = []

    def answer(self, cart):
        user, state = self.request.user, self.request.query_params.get("state") or None
        if state and state not in dict(STATE_CHOICES):
            raise serializers.ValidationError({"state": ["Unknown state code."]})
        result = totals(cart, state=state, user=user, email=user.email)
        return Response(CartSerializer(result, context={"cart": cart}).data)

    @extend_schema(parameters=[STATE])
    def retrieve(self, request, **kwargs):
        return self.answer(get_cart(request))

    @extend_schema(request=CartItemSerializer, responses=CartSerializer, parameters=[STATE])
    def add(self, request, **kwargs):
        """Add copies of a book (to those already in the cart), at most 20 in all."""
        data = CartItemSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        product = data.validated_data["product"]
        if product.available < 1:
            raise serializers.ValidationError({"product": [f"{product} is out of stock."]})
        cart = get_cart(request, create=True)
        set_quantity(cart, product, data.validated_data["quantity"], add=True)
        return self.answer(cart)

    def item(self, request, product):
        cart = get_cart(request)
        item = cart.items.select_related("product").filter(product__slug=product).first() if cart else None
        if item is None:
            raise exceptions.NotFound("This book is not in the cart.")
        return cart, item

    @extend_schema(request=QuantitySerializer, responses=CartSerializer, parameters=[PRODUCT, STATE])
    def change(self, request, product, **kwargs):
        """Set the number of copies of a book in the cart (0 removes it)."""
        cart, item = self.item(request, product)
        data = QuantitySerializer(data=request.data)
        data.is_valid(raise_exception=True)
        set_quantity(cart, item.product, data.validated_data["quantity"])
        return self.answer(cart)

    @extend_schema(request=None, responses=CartSerializer, parameters=[PRODUCT, STATE])
    def remove(self, request, product, **kwargs):
        cart, item = self.item(request, product)
        item.delete()
        return self.answer(cart)

    @property
    def throttle_scope(self):  # coupon codes are not guessed: API_THROTTLE_COUPON
        return "coupon" if getattr(self, "action", None) == "apply_coupon" else None

    @extend_schema(request=CouponSerializer, responses=CartSerializer, parameters=[STATE])
    def apply_coupon(self, request, **kwargs):
        """Use a coupon code (any case). Refused with one message whatever the reason (unknown, expired, used up, too
        small a cart); limited per user (API_THROTTLE_COUPON)."""
        data = CouponSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        cart, user = get_cart(request, create=True), request.user
        coupon = Coupon.objects.filter(code__iexact=data.validated_data["code"].strip()).first()
        if coupon is None or coupon.problem(totals(cart).subtotal, user=user, email=user.email):
            raise serializers.ValidationError({"code": [services.COUPON_REFUSED]})
        cart.coupon = coupon
        cart.save(update_fields=["coupon", "modified"])
        return self.answer(cart)

    @extend_schema(request=None, responses=CartSerializer, parameters=[STATE])
    def remove_coupon(self, request, **kwargs):
        cart = get_cart(request)
        if cart and cart.coupon:
            cart.coupon = None
            cart.save(update_fields=["coupon", "modified"])
        return self.answer(cart)


# Addresses


class AddressSerializer(serializers.ModelSerializer):
    """A saved delivery address: a state code from the list, a 6-digit PIN code and a 10-digit Indian mobile number
    (the website's rules)."""

    phone = PhoneNumberField(region="IN", validators=[validate_indian_mobile])

    class Meta:
        model = Address
        fields = ["id", *Address.FIELDS, "is_default", "created", "modified"]


class AddressViewSet(viewsets.ModelViewSet):
    """The signed-in customer's own addresses (another customer's: 404). One may be the default."""

    serializer_class = AddressSerializer
    permission_classes = CUSTOMER
    ordering_fields = ["created"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # schema generation has no user
            return Address.objects.none()
        return self.request.user.addresses.all()

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


# Orders


class OrderItemSerializer(serializers.ModelSerializer):
    product = serializers.SlugRelatedField(slug_field="slug", read_only=True)
    mrp = rupees("mrp.amount")
    unit_price = rupees("unit_price.amount")
    line_total = rupees("line_total.amount")

    class Meta:
        model = OrderItem
        fields = ["product", "title", "hsn_code", "gst_rate", "mrp", "unit_price", "quantity", "line_total"]


class OrderBriefSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(read_only=True, help_text="as the website shows it")
    total = rupees("total.amount")
    items = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ["number", "created", "placed_at", "status", "status_label", "payment_method", "total", "items"]

    @extend_schema_field(serializers.ListField(child=serializers.CharField(), help_text='"2 × Physics Sample Papers"'))
    def get_items(self, order):
        return [str(item) for item in order.items.all()]


class TimelineSerializer(serializers.Serializer):
    status = serializers.CharField()
    at = serializers.DateTimeField()


class ShipmentSerializer(serializers.Serializer):
    courier = serializers.CharField()
    tracking_number = serializers.CharField()
    tracking_url = serializers.URLField()
    shipped_at = serializers.DateTimeField()
    delivered_at = serializers.DateTimeField(allow_null=True)


class RefundSerializer(serializers.Serializer):
    amount = rupees("amount.amount")
    status = serializers.CharField()
    reason = serializers.CharField()
    created = serializers.DateTimeField()
    processed_at = serializers.DateTimeField(allow_null=True)


class DocumentSerializer(serializers.Serializer):
    number = serializers.CharField()
    created = serializers.DateTimeField()
    url = serializers.URLField(help_text="the PDF, for the order's owner")


class CreditNoteSerializer(DocumentSerializer):
    amount = rupees(help_text="credited (refunded)")


class OrderSerializer(OrderBriefSerializer):
    """An order as its owner sees it on the website: status and timeline, the books (prices as ordered), the address
    copied at checkout, shipments with tracking, refunds, and the invoice and credit notes once their PDFs exist."""

    subtotal = rupees("subtotal.amount")
    discount = rupees("discount.amount")
    shipping_fee = rupees("shipping_fee.amount")
    items = OrderItemSerializer(many=True, read_only=True)
    timeline = serializers.SerializerMethodField()
    shipments = ShipmentSerializer(many=True, read_only=True)
    refunds = RefundSerializer(many=True, read_only=True)
    can_cancel = serializers.BooleanField(read_only=True)
    can_pay = serializers.SerializerMethodField()
    invoice = serializers.SerializerMethodField()
    credit_notes = serializers.SerializerMethodField()
    web_url = serializers.SerializerMethodField()

    class Meta(OrderBriefSerializer.Meta):
        fields = [
            *OrderBriefSerializer.Meta.fields,
            *["email", "shipping_address", "subtotal", "discount", "shipping_fee", "coupon_code"],
            *["timeline", "shipments", "refunds", "can_cancel", "can_pay", "invoice", "credit_notes", "web_url"],
        ]

    @extend_schema_field(TimelineSerializer(many=True))
    def get_timeline(self, order):
        return TimelineSerializer([{"status": label, "at": at} for label, at in order.timeline()], many=True).data

    def get_can_pay(self, order) -> bool:
        return can_pay(order)

    def pdf_url(self, name, order, **kwargs):
        return reverse(name, kwargs={"number": order.number, **kwargs}, request=self.context["request"])

    @extend_schema_field(DocumentSerializer(allow_null=True))
    def get_invoice(self, order):
        invoice = getattr(order, "invoice", None)
        if invoice is None or not invoice.pdf:
            return None
        url = self.pdf_url("api:order-invoice", order)
        return DocumentSerializer({"number": invoice.number, "created": invoice.created, "url": url}).data

    @extend_schema_field(CreditNoteSerializer(many=True))
    def get_credit_notes(self, order):
        notes = CreditNote.objects.filter(invoice__order=order).exclude(pdf="").select_related("refund")
        return CreditNoteSerializer(
            [
                {
                    "number": note.number,
                    "created": note.created,
                    "amount": note.refund.amount.amount,
                    "url": self.pdf_url("api:order-credit-note", order, note=note.pk),
                }
                for note in notes
            ],
            many=True,
        ).data

    def get_web_url(self, order) -> str:
        return self.context["request"].build_absolute_uri(order.get_absolute_url())


class CheckoutSerializer(serializers.Serializer):
    address = serializers.IntegerField(help_text="the id of one of the customer's addresses (addresses/)")
    payment_method = serializers.ChoiceField(choices=Order.Method.choices)

    def validate_address(self, value):
        if address := self.context["request"].user.addresses.filter(pk=value).first():
            return address
        raise serializers.ValidationError("Not one of your addresses.")


class PaymentStartSerializer(serializers.Serializer):
    """The options of Razorpay's Checkout and mobile SDKs."""

    key = serializers.CharField(help_text="the Razorpay key id (rzp_test_… in test mode)")
    order_id = serializers.CharField(help_text="Razorpay's order")
    amount = serializers.IntegerField(help_text="paise")
    currency = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField()
    prefill = serializers.DictField(child=serializers.CharField(), help_text="name, email, contact")
    notes = serializers.DictField(child=serializers.CharField())
    theme = serializers.DictField(child=serializers.CharField())
    test_mode = serializers.BooleanField()


class PaymentConfirmSerializer(serializers.Serializer):
    """What the SDK's success callback returns."""

    razorpay_order_id = serializers.CharField()
    razorpay_payment_id = serializers.CharField()
    razorpay_signature = serializers.CharField()


class LookupSerializer(serializers.Serializer):
    number = serializers.CharField(max_length=20)
    email = serializers.EmailField(help_text="the address the order was placed with")


class LinkSentSerializer(serializers.Serializer):
    detail = serializers.CharField(help_text="always: " + services.LINK_SENT)


PDF = {(200, "application/pdf"): OpenApiTypes.BINARY}
NOTE = OpenApiParameter("note", int, OpenApiParameter.PATH, description="the credit note's id (credit_notes[].url)")


class OrderViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """The signed-in customer's own orders (another customer's: 404), checkout, payment and cancellation."""

    permission_classes = [*CUSTOMER, ShopOpen]
    throttle_scope = None  # the payment and lookup actions set theirs
    lookup_field = "number"
    filterset_fields = ["status"]
    ordering_fields = ["created"]
    ordering = ["-created"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # schema generation has no user
            return Order.objects.none()
        orders = self.request.user.orders.all()
        if self.action == "list":
            return orders.prefetch_related("items")
        items = Prefetch("items", queryset=OrderItem.objects.select_related("product"))
        return orders.select_related("invoice").prefetch_related(items, "shipments", "refunds")

    def get_serializer_class(self):
        return OrderBriefSerializer if self.action == "list" else OrderSerializer

    def answer(self, order, code=status.HTTP_200_OK):
        return Response(OrderSerializer(order, context=self.get_serializer_context()).data, status=code)

    @extend_schema(request=CheckoutSerializer, responses={201: OrderSerializer})
    def create(self, request, *args, **kwargs):
        """Checkout: an order from the cart at today's prices, to a saved address. Online: pending until paid
        (payment/). Cash on delivery: placed at once and the cart emptied."""
        if request.user.consent_pending:
            raise exceptions.PermissionDenied("A parent or guardian has not confirmed this account yet.")
        if over_limit(request, "checkout", 10, 600):  # shared with the website's checkout, per client address
            raise exceptions.Throttled(wait=600)
        data = CheckoutSerializer(data=request.data, context={"request": request})
        data.is_valid(raise_exception=True)
        user, cart = request.user, get_cart(request)
        try:
            order = services.create_order(
                cart,
                user=user,
                email=user.email,
                address=data.validated_data["address"].snapshot(),
                method=data.validated_data["payment_method"],
            )
            if order.is_cod:
                try:
                    order = services.place_cod(order)
                except services.ShopError as error:  # sold out, or the coupon's last use went, meanwhile
                    services.cancel_order(order, f"Not placed: {error}", email=False)
                    raise
                cart.delete()
        except services.ShopError as error:
            raise refuse(str(error)) from error
        return self.answer(order, status.HTTP_201_CREATED)

    @extend_schema(request=None, responses=OrderSerializer)
    @action(detail=True, methods=["post"], permission_classes=CUSTOMER)  # also while the shop is closed
    def cancel(self, request, **kwargs):
        """Cancel while pending or paid; an online payment is refunded in full (5–7 working days)."""
        order = self.get_object()
        try:
            if not order.can_cancel:
                raise TransitionNotAllowed
            order = services.cancel_order(order, "Cancelled by the customer.")
        except TransitionNotAllowed as error:
            raise refuse("This order can no longer be cancelled; see the Refund Policy.") from error
        return self.answer(order)

    @extend_schema(request=None, responses=PaymentStartSerializer)
    @action(detail=True, methods=["post"], throttle_scope="payment")
    def payment(self, request, **kwargs):
        """Start paying online: the options for Razorpay's mobile SDK, with the Razorpay order for this order (made
        on the first call; the same one afterwards). 503 while Razorpay cannot be reached: try again."""
        order = self.get_object()
        if not can_pay(order):
            raise refuse(NOT_PAYABLE)
        if problem := services.coupon_problem(order):  # a payment would only be refunded
            raise refuse(f"{problem} Cancel this order and check out again without the coupon.")
        try:
            options = payments.checkout_options(order)
        except payments.Unavailable as error:
            raise PaymentServiceUnavailable(str(error)) from error
        return Response({**options, "test_mode": payments.test_mode()})

    @extend_schema(request=PaymentConfirmSerializer, responses=OrderSerializer)
    @action(detail=True, methods=["post"], url_path="payment/confirm", throttle_scope="payment")
    def payment_confirm(self, request, **kwargs):
        """The SDK's success callback, checked (signature) and confirmed with Razorpay: the order is paid and the cart
        emptied. If Razorpay cannot be asked now the order stays pending a few minutes until its webhook arrives."""
        order = self.get_object()
        data = PaymentConfirmSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        payment = order.payments.filter(razorpay_order_id=data.validated_data["razorpay_order_id"]).first()
        if payment is None or not payments.confirm_return(payment, data.validated_data):
            raise refuse(NOT_CONFIRMED)
        order = self.get_object()
        if order.status != Order.Status.CANCELLED:  # cancelled: sold out or coupon used up while paying (refunded)
            Cart.objects.filter(user=request.user).delete()
        return self.answer(order)

    @extend_schema(responses=PDF)
    @action(detail=True, content_negotiation_class=AnyAccept)
    def invoice(self, request, **kwargs):
        """The invoice PDF (404 until it has been made, a few minutes after payment)."""
        response = pdf_response(getattr(self.get_object(), "invoice", None))
        add_never_cache_headers(response)
        return response

    @extend_schema(responses=PDF, parameters=[NOTE])
    @action(detail=True, url_path=r"credit-notes/(?P<note>\d+)", content_negotiation_class=AnyAccept)
    def credit_note(self, request, note, **kwargs):
        """A credit note PDF (for a refund of an invoiced order)."""
        response = pdf_response(CreditNote.objects.filter(invoice__order=self.get_object(), pk=note).first())
        add_never_cache_headers(response)
        return response

    @extend_schema(request=LookupSerializer, responses=LinkSentSerializer)
    @action(
        detail=False,
        methods=["post"],
        permission_classes=[permissions.AllowAny],
        authentication_classes=[],
        throttle_scope="order_lookup",
    )
    def lookup(self, request, **kwargs):
        """Guests (who ordered on the website without an account): the link to an order is emailed to the address it
        was placed with, never answered here; the answer is the same whether an order matched or not. Limited per
        client address, per email address and per order number."""
        data = LookupSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        number, email = data.validated_data["number"].strip().upper(), data.validated_data["email"]
        if not lookup_allowed(number, email):
            raise exceptions.Throttled(wait=3600)
        services.email_order_link(number, email)
        return Response({"detail": services.LINK_SENT})
