"""REST API v1 for the shop: the books on sale and the delivery rates (public); for a signed-in customer with a
confirmed email address the cart, the saved addresses and the orders, paid with Razorpay's mobile SDK or cash on
delivery; for a visitor a guest cart (the session, or X-Cart-Token) and a guest's checkout paid through the order's
link; and the guests' order lookup. Every step goes through shop.cart, shop.services and shop.payments, as on the
website. The Razorpay webhook stays the website's (/shop/webhooks/razorpay/): it completes an order whatever the client
did."""

import django_filters
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Avg, Count, Prefetch, Q
from django.utils.cache import add_never_cache_headers, patch_cache_control
from django_fsm import TransitionNotAllowed
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    PolymorphicProxySerializer,
    extend_schema,
    extend_schema_field,
    extend_schema_serializer,
)
from localflavor.in_.in_states import STATE_CHOICES
from phonenumber_field.serializerfields import PhoneNumberField
from rest_framework import exceptions, generics, mixins, negotiation, permissions, serializers, status, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.reverse import reverse

from shop import payments, services
from shop.cart import cart_by_token, get_cart, issue_token, merge_carts, set_quantity, totals
from shop.forms import QuoteRequestForm
from shop.models import (
    Address,
    Attribute,
    AttributeValue,
    BundleItem,
    Cart,
    CartItem,
    Category,
    Collection,
    CollectionItem,
    Coupon,
    CreditNote,
    Order,
    OrderItem,
    PinCode,
    Product,
    Review,
    ShippingRate,
    StockAlert,
    validate_indian_mobile,
)
from shop.views import QUOTE_SENT, lookup_allowed, over_limit, pdf_response

from .views import DetailSerializer, VerifiedEmail, cached, check_turnstile

CUSTOMER = [permissions.IsAuthenticated, VerifiedEmail]
NOT_PAYABLE = "This order is not waiting for an online payment."


class ShopOpen(permissions.BasePermission):
    """While SHOP_OPEN is off only staff change carts, check out and pay (shop.views.shop_open)."""

    message = "The shop opens soon."

    def has_permission(self, request, view):
        if settings.SHOP_OPEN or request.method in permissions.SAFE_METHODS or request.user.is_staff:
            return True
        raise exceptions.PermissionDenied(self.message)  # 403 for visitors too (DRF would answer them 401)


CART_TOKEN = "X-Cart-Token"


class GuestOrCustomer(permissions.BasePermission):
    """Signed in: a confirmed email address, as before. A visitor: their guest cart, held by the X-Cart-Token header
    or, in a browser, by the session cookie with the CSRF token (X-CSRFToken) on every change, as for a signed-in
    session (DRF checks CSRF only for signed-in sessions)."""

    message = VerifiedEmail.message

    def has_permission(self, request, view):
        if request.user.is_authenticated:
            return VerifiedEmail().has_permission(request, view)
        changes = request.method not in permissions.SAFE_METHODS and getattr(view, "action", None) != "start"
        if changes and CART_TOKEN not in request.headers:
            SessionAuthentication().enforce_csrf(request)  # 403 "CSRF Failed: ..."
        return True


def caller_cart(request, create=False):
    """The caller's cart: the account's (a guest cart sent along by X-Cart-Token joins it first: the log-in of a
    client without cookies), else the guest cart of X-Cart-Token (404 once expired), else the session's (a browser)."""
    token = request.headers.get(CART_TOKEN)
    if request.user.is_authenticated:
        if token and (guest := cart_by_token(token)):
            merge_carts(guest, request.user)
        return get_cart(request, create=create)
    if not token:
        return get_cart(request, create=create)
    if cart := cart_by_token(token):
        return cart
    raise exceptions.NotFound("This cart has expired: start a new one (POST cart/).")


def buyer(request):
    """(user, email) for prices and coupons: the signed-in user, or a visitor (None, "")."""
    user = request.user if request.user.is_authenticated else None
    return user, user.email if user else ""


class Private:
    """A visitor's cart and orders are as personal as an account's: never kept by a browser or a proxy."""

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        add_never_cache_headers(response)
        return response


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
    return request.build_absolute_uri(file.url) if file else None  # the public bucket, or /shop/media/


# Products


class BundleItemSerializer(serializers.ModelSerializer):
    product = serializers.SlugRelatedField(slug_field="slug", read_only=True)
    title = serializers.CharField(source="product.title", read_only=True)

    class Meta:
        model = BundleItem
        fields = ["product", "title", "quantity"]


class AttributeValueSerializer(serializers.ModelSerializer):
    code = serializers.CharField(source="attribute.code", read_only=True, help_text="the filter: ?attr_<code>=")
    name = serializers.CharField(source="attribute.name", read_only=True)

    class Meta:
        model = AttributeValue
        fields = ["code", "name", "value"]


class ProductSerializer(serializers.ModelSerializer):
    """A book on sale. `in_stock` says whether copies can be ordered (a bundle: of each of its books; a digital
    product: always); the number of copies is not given."""

    categories = serializers.SlugRelatedField(slug_field="slug", many=True, read_only=True)
    attributes = AttributeValueSerializer(source="attribute_values", many=True, read_only=True)
    related = serializers.SerializerMethodField()

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
            "categories",
            "attributes",
            "related",
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
        if product.is_digital:
            return True
        if product.kind != Product.Kind.BUNDLE:
            return product.stock > 0
        items = list(product.bundle_items.all())
        books = [item for item in items if not item.product.is_digital]  # a course has no copies
        return not books and bool(items) or min((item.product.stock // item.quantity for item in books), default=0) > 0

    def get_related(self, product) -> list[str]:
        return [other.slug for other in product.related.all() if other.is_active]

    def get_web_url(self, product) -> str:
        return self.context["request"].build_absolute_uri(product.get_absolute_url())


class ProductFilter(django_filters.FilterSet):
    category = django_filters.CharFilter(method="in_category", help_text="a category's slug (with its sub-categories)")
    collection = django_filters.CharFilter(
        field_name="collection_items__collection__slug", help_text="a collection's slug"
    )

    class Meta:
        model = Product
        fields = ["kind", "subject", "category", "collection"]

    def in_category(self, queryset, name, value):
        if (category := Category.objects.filter(slug=value).first()) is None:
            return queryset.none()
        return queryset.filter(categories__in=Category.objects.get_tree(category))


ATTRIBUTE_FILTERS = 5  # ?attr_<code>= parameters in one request, their attributes fetched in one query (L2)


def attribute_match(attributes, value):
    """Products whose attribute (one of `attributes`, those of one code) holds `value` (compared as the attribute
    stores it: "2027.0" finds 2027)."""
    match = Q(pk__in=[])
    for attribute in attributes:
        try:
            normal = attribute.normalise(value)
        except ValidationError:
            continue
        match |= Q(attribute_values__attribute=attribute, attribute_values__value__iexact=normal)
    return match


@extend_schema_serializer(
    examples=[OpenApiExample("A review", value={"rating": 5, "text": "Every answer step by step."}, request_only=True)]
)
class ProductReviewSerializer(serializers.ModelSerializer):
    """A buyer's review as the product page shows it: "Verified buyer", never a name (many buyers are minors)."""

    rating = serializers.IntegerField(min_value=1, max_value=5)

    class Meta:
        model = Review
        fields = ["rating", "text", "status", "created"]
        read_only_fields = ["status", "created"]


class ProductReviewsSerializer(serializers.Serializer):
    average = serializers.DecimalField(max_digits=2, decimal_places=1, allow_null=True, help_text="of the approved")
    count = serializers.IntegerField()
    can_review = serializers.BooleanField(help_text="the signed-in user may write one (a delivered order of it)")
    results = ProductReviewSerializer(many=True, help_text="the approved reviews, newest first")


NOT_A_BUYER = "Reviews are from buyers whose order of this book has been delivered, one each."


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    """The products on sale, with their prices, pictures, what a bundle holds, whether they are in stock, their
    categories and attributes. Filters: `?kind=`, `?subject=`, `?category=<slug>` (with its sub-categories),
    `?collection=<slug>`, and `?attr_<code>=<value>` for any attribute (e.g. `?attr_language=Assamese`,
    `?attr_year=2027`; several are combined with AND)."""

    permission_classes = [permissions.AllowAny]
    queryset = (
        Product.objects.filter(is_active=True)
        .select_related("subject", "book")
        .prefetch_related(
            "images",
            "categories",
            "related",
            Prefetch("bundle_items", queryset=BundleItem.objects.select_related("product")),
            Prefetch("attribute_values", queryset=AttributeValue.objects.select_related("attribute")),
        )
    )
    serializer_class = ProductSerializer
    lookup_field = "slug"
    filterset_class = ProductFilter
    search_fields = ["title"]
    ordering_fields = ["title", "price"]  # only these: any other name is ignored

    def get_queryset(self):
        products, params = super().get_queryset(), self.request.query_params.items()
        wanted = [(name.removeprefix("attr_"), value) for name, value in params if name.startswith("attr_")]
        if len(wanted) > ATTRIBUTE_FILTERS:
            raise exceptions.ValidationError({"detail": f"At most {ATTRIBUTE_FILTERS} attr_ filters."})
        by_code = {}
        for attribute in Attribute.objects.filter(code__in=[code for code, _ in wanted]):
            by_code.setdefault(attribute.code, []).append(attribute)
        for code, value in wanted:
            products = products.filter(attribute_match(by_code.get(code, []), value))
        return products.distinct()  # a product on two shelves of one branch is listed once

    @extend_schema(methods=["GET"], responses=ProductReviewsSerializer)
    @extend_schema(methods=["POST"], request=ProductReviewSerializer, responses={201: ProductReviewSerializer})
    @action(detail=True, methods=["get", "post"], filter_backends=[], pagination_class=None)
    def reviews(self, request, **kwargs):
        """GET: the approved reviews, their average, and whether the signed-in user may write one. POST (signed in,
        email confirmed): a review from a buyer whose order of the product was delivered, one each; it shows once staff
        have read it (`status` pending). At most 5 an hour per client address, the website's included."""
        product = self.get_object()
        if request.method == "GET":
            approved = product.reviews.filter(status=Review.Status.APPROVED)
            data = approved.aggregate(average=Avg("rating"), count=Count("pk"))
            data.update(can_review=Review.can_review(request.user, product), results=approved)
            return Response(ProductReviewsSerializer(data).data)
        if not VerifiedEmail().has_permission(request, self):
            self.permission_denied(request, message=VerifiedEmail.message)
        if over_limit(request, "review", 5, 3600):
            raise exceptions.Throttled(wait=3600)
        serializer = ProductReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not Review.can_review(request.user, product):
            raise exceptions.PermissionDenied(NOT_A_BUYER)
        try:
            with transaction.atomic():
                serializer.save(product=product, user=request.user)
        except IntegrityError as error:  # sent twice at once
            raise exceptions.PermissionDenied(NOT_A_BUYER) from error
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses=DetailSerializer)
    @action(
        detail=True,
        methods=["post"],
        url_path="stock-alert",
        filter_backends=[],
        permission_classes=[permissions.IsAuthenticated],
    )
    def stock_alert(self, request, **kwargs):
        """ "Email me when it is back", for a product out of stock: one email, to the signed-in user's own address (an
        address given by a visitor could be anyone's: L3). The answer is the same whatever the stock. At most 10 an
        hour per client address, the website's included."""
        product = self.get_object()
        if over_limit(request, "stock-alert", 10, 3600):
            raise exceptions.Throttled(wait=3600)
        email = request.user.email
        if product.available < 1:
            StockAlert.objects.get_or_create(email=email.lower(), product=product)
        return Response({"detail": f"We will email {email} once, when {product} is back in stock."})


class CategorySerializer(serializers.ModelSerializer):
    """A category of the shop's tree: `depth` 1 at the top, `parent` the slug of the one above (null at the top)."""

    description = serializers.CharField(read_only=True, help_text="Markdown")
    parent = serializers.SerializerMethodField()
    web_url = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ["slug", "name", "description", "depth", "parent", "web_url"]

    def get_parent(self, category) -> str | None:
        return self.context["slugs"].get(category.path[: -Category.steplen])

    def get_web_url(self, category) -> str:
        return self.context["request"].build_absolute_uri(category.get_absolute_url())


@cached
class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """The category tree, in tree order (each category followed by its sub-categories); products/?category=<slug>
    lists a category's products."""

    permission_classes = [permissions.AllowAny]
    queryset = Category.objects.order_by("path")
    serializer_class = CategorySerializer
    lookup_field = "slug"
    filter_backends = []

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "slugs": dict(Category.objects.values_list("path", "slug"))}


class CollectionSerializer(serializers.ModelSerializer):
    description = serializers.CharField(read_only=True, help_text="Markdown")
    products = serializers.SerializerMethodField()
    web_url = serializers.SerializerMethodField()

    class Meta:
        model = Collection
        fields = ["slug", "name", "description", "products", "web_url"]

    def get_products(self, collection) -> list[str]:
        return [item.product.slug for item in collection.items.all() if item.product.is_active]

    def get_web_url(self, collection) -> str:
        return self.context["request"].build_absolute_uri(collection.get_absolute_url())


@cached
class CollectionViewSet(viewsets.ReadOnlyModelViewSet):
    """Hand-picked lists of products ("Board 2027 essentials"); `products` are slugs, in the order staff gave them."""

    permission_classes = [permissions.AllowAny]
    queryset = Collection.objects.filter(is_active=True).prefetch_related(
        Prefetch("items", queryset=CollectionItem.objects.select_related("product"))
    )
    serializer_class = CollectionSerializer
    lookup_field = "slug"
    filter_backends = []


# Cart


class CartLineSerializer(serializers.Serializer):
    product = serializers.SlugField(source="product.slug")
    title = serializers.CharField(source="product.title")
    price = rupees("product.price.amount")
    quantity = serializers.IntegerField()
    total = rupees()


class SavingSerializer(serializers.Serializer):
    label = serializers.CharField(help_text='"Coupon WELCOME10", an offer\'s name, "Discount"')
    amount = rupees()


class CartSerializer(serializers.Serializer):
    """The cart at today's prices (shop.cart.totals, as the website): `savings` are the coupon's and the automatic
    offers' discounts, `discount` their sum."""

    items = CartLineSerializer(source="lines", many=True)
    count = serializers.IntegerField(help_text="copies")
    coupon = serializers.SerializerMethodField()
    coupon_problem = serializers.CharField(allow_null=True, help_text="why the coupon does not apply now")
    subtotal = rupees()
    savings = SavingSerializer(many=True)
    discount = rupees()
    shipping = rupees(allow_null=True, help_text="null without ?state=")
    total = rupees()
    problems = serializers.ListField(child=serializers.CharField(), help_text="what stops an order: stock, sale")

    def get_coupon(self, result) -> str | None:
        cart = self.context["cart"]
        return cart.coupon.code if cart and cart.coupon else None


@extend_schema_serializer(
    examples=[
        OpenApiExample("Two copies", value={"product": "physics-sample-papers", "quantity": 2}, request_only=True)
    ]
)
class CartItemSerializer(serializers.Serializer):
    product = serializers.SlugRelatedField(slug_field="slug", queryset=Product.objects.filter(is_active=True))
    quantity = serializers.IntegerField(min_value=1, max_value=CartItem.MAX_QUANTITY, default=1)


class QuantitySerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=0, max_value=CartItem.MAX_QUANTITY, help_text="0 removes the book")


class CouponSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=30)
    turnstile = serializers.CharField(
        required=False, allow_blank=True, write_only=True, help_text="a visitor's: Turnstile's token while it is on"
    )


class CartStartSerializer(CartSerializer):
    token = serializers.CharField(help_text="send it as X-Cart-Token; shown once, valid 30 days")


STATE = OpenApiParameter("state", str, description="two-letter state code (AS): adds the shipping for it")
PRODUCT = OpenApiParameter("product", str, OpenApiParameter.PATH, description="the product's slug")
HELD = OpenApiParameter(
    CART_TOKEN,
    str,
    OpenApiParameter.HEADER,
    description="a visitor's cart token (POST cart/), for clients without cookies",
)


@extend_schema(parameters=[HELD])
class CartViewSet(Private, viewsets.GenericViewSet):
    """The cart, the same as on the website: a signed-in customer's (confirmed email address), or a visitor's, held by
    the session cookie (a browser on the site's origin; CSRF token on changes) or by X-Cart-Token (POST cart/). Every
    answer is the whole cart; `?state=` adds the shipping."""

    permission_classes = [GuestOrCustomer, ShopOpen]
    serializer_class = CartSerializer
    pagination_class = None
    filter_backends = []

    def answer(self, cart, code=status.HTTP_200_OK, **extra):
        (user, email), state = buyer(self.request), self.request.query_params.get("state") or None
        if state and state not in dict(STATE_CHOICES):
            raise serializers.ValidationError({"state": ["Unknown state code."]})
        result = totals(cart, state=state, user=user, email=email)
        return Response({**CartSerializer(result, context={"cart": cart}).data, **extra}, status=code)

    @extend_schema(parameters=[STATE])
    def retrieve(self, request, **kwargs):
        return self.answer(caller_cart(request))

    @extend_schema(request=None, responses={201: CartStartSerializer})
    def start(self, request, **kwargs):
        """A new, empty guest cart for a client without cookies, and its `token` (shown once): send it as X-Cart-Token
        with every cart, shipping quote and checkout call, for 30 days. At log-in, sending it along once with the
        account's credentials adds its books to the account's cart. Signed in: 400 (the account has its cart)."""
        if request.user.is_authenticated:
            raise refuse("You are signed in: your account's cart needs no token.")
        cart = Cart.objects.create()
        return self.answer(cart, status.HTTP_201_CREATED, token=issue_token(cart))

    @extend_schema(request=CartItemSerializer, responses=CartSerializer, parameters=[STATE])
    def add(self, request, **kwargs):
        """Add copies of a book (to those already in the cart), at most 20 in all."""
        data = CartItemSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        product = data.validated_data["product"]
        if product.available < 1:
            raise serializers.ValidationError({"product": [f"{product} is out of stock."]})
        cart = caller_cart(request, create=True)
        set_quantity(cart, product, data.validated_data["quantity"], add=True)
        return self.answer(cart)

    def item(self, request, product):
        cart = caller_cart(request)
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
        small a cart); limited per user (API_THROTTLE_COUPON). A visitor, as on the website: Turnstile's token while
        the bot check is on, and 10 codes an hour per client address, the website's included."""
        data = CouponSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        user, email = buyer(request)
        if user is None:
            check_turnstile(data.validated_data)
            if over_limit(request, "coupon", 10, 3600):  # shared with the website's cart page
                raise exceptions.Throttled(wait=3600)
        cart = caller_cart(request, create=True)
        coupon = Coupon.objects.filter(code__iexact=data.validated_data["code"].strip()).first()
        if coupon is None or coupon.problem(totals(cart).subtotal, user=user, email=email):
            raise serializers.ValidationError({"code": [services.COUPON_REFUSED]})
        cart.coupon = coupon
        cart.save(update_fields=["coupon", "modified"])
        return self.answer(cart)

    @extend_schema(request=None, responses=CartSerializer, parameters=[STATE])
    def remove_coupon(self, request, **kwargs):
        cart = caller_cart(request)
        if cart and cart.coupon:
            cart.coupon = None
            cart.save(update_fields=["coupon", "modified"])
        return self.answer(cart)


# Shipping


class ShippingRateSerializer(serializers.ModelSerializer):
    states = serializers.ListField(
        child=serializers.CharField(), help_text="two-letter codes; [] for every state no other rate names"
    )
    fee = rupees("fee.amount")
    free_above = rupees("free_above.amount", allow_null=True, help_text="books worth this much or more ship free")

    class Meta:
        model = ShippingRate
        fields = ["name", "states", "fee", "free_above"]


class ShippingSerializer(serializers.Serializer):
    fee_from = rupees(allow_null=True, help_text='the lowest fee: "delivery from ₹40"')
    free_above = rupees(allow_null=True, help_text="the lowest value from which a rate ships free")
    rates = ShippingRateSerializer(many=True)


class ShippingView(generics.GenericAPIView):
    """The delivery rates, as the website's checkout and Shipping Policy use them: a flat fee per group of states (a
    rate without states: every state no other rate names), free from a value of books when the rate says so. No
    weights. Cacheable for 5 minutes."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    serializer_class = ShippingSerializer

    def get(self, request, *args, **kwargs):
        rates = ShippingRate.objects.filter(is_active=True)
        response = Response(ShippingSerializer({**ShippingRate.summary(), "rates": rates}).data)
        patch_cache_control(response, public=True, max_age=300)
        return response


class ShippingQuoteQuery(serializers.Serializer):
    pin = serializers.RegexField(r"^\d{6}$", required=False, help_text="6 digits: its state, from the PIN directory")
    state = serializers.ChoiceField(choices=STATE_CHOICES, required=False, help_text="two-letter code, as typed")
    amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=0, required=False, help_text="books' value; default: the cart's"
    )

    def validate(self, attrs):
        pin, state = attrs.get("pin"), attrs.get("state")
        if not pin and not state:
            raise serializers.ValidationError({"pin": ["Give a PIN code (?pin=) or a state (?state=)."]})
        if pin and state and (problem := PinCode.state_problem(pin, state)):
            raise serializers.ValidationError({"state": [problem]})
        return attrs


class ShippingQuoteSerializer(serializers.Serializer):
    pin = serializers.CharField(allow_null=True)
    states = serializers.ListField(child=serializers.CharField(), help_text="the PIN's (a few lie in two); [] unknown")
    districts = serializers.ListField(child=serializers.CharField(), help_text="the PIN's, to fill in the address")
    state = serializers.CharField(allow_null=True, help_text="the fee's: ?state=, or the PIN's only one; null: ask")
    amount = rupees(help_text="the books' value the fee is for: ?amount=, or the cart's after discounts")
    fee = rupees(allow_null=True, help_text="null until the state is known")
    free_above = rupees(allow_null=True, help_text="the state's rate ships free from this value")


class ShippingQuoteView(Private, generics.GenericAPIView):
    """The checkout's delivery step: the fee to a PIN code (its state from the India Post directory, once loaded) or a
    state, for `amount` or for the caller's cart (the account's, or a visitor's by the session or X-Cart-Token; courses
    alone ship free), with the PIN code's states and districts to fill in the address. Rates are flat per state:
    there is no weight."""

    permission_classes = [permissions.AllowAny]
    serializer_class = ShippingQuoteSerializer

    @extend_schema(parameters=[ShippingQuoteQuery, HELD])
    def get(self, request, *args, **kwargs):
        query = ShippingQuoteQuery(data=request.query_params)
        query.is_valid(raise_exception=True)
        pin, state, amount = (query.validated_data.get(name) for name in ("pin", "state", "amount"))
        entry, fee = PinCode.objects.filter(pin=pin).first() if pin else None, None
        states = entry.states if entry else []
        state = state or (states[0] if len(states) == 1 else None)
        if amount is None:
            user, email = buyer(request)
            result = totals(caller_cart(request), state=state, user=user, email=email)
            amount, fee = result.subtotal - result.discount, result.shipping if result.lines else None
        if state and fee is None:
            fee = ShippingRate.fee_for(state, amount)
        rate = ShippingRate.rate_for(state) if state else None
        quote = {"pin": pin, "states": states, "districts": entry.districts if entry else [], "state": state}
        free = rate.free_above.amount if rate and rate.free_above is not None else None
        return Response(ShippingQuoteSerializer({**quote, "amount": amount, "fee": fee, "free_above": free}).data)


# Addresses


class AddressSerializer(serializers.ModelSerializer):
    """A saved delivery address: a state code from the list, a 6-digit PIN code and a 10-digit Indian mobile number
    (the website's rules)."""

    phone = PhoneNumberField(region="IN", validators=[validate_indian_mobile])

    class Meta:
        model = Address
        fields = ["id", *Address.FIELDS, "is_default", "created", "modified"]

    def validate(self, data):
        pin, state = (
            data.get("pin", getattr(self.instance, "pin", "")),
            data.get("state", getattr(self.instance, "state", "")),
        )
        if problem := PinCode.state_problem(pin, state):  # the PIN directory, when loaded (as on the website)
            raise serializers.ValidationError({"state": [problem]})
        return data


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
    savings = serializers.SerializerMethodField()
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
            *["email", "shipping_address", "subtotal", "savings", "discount", "shipping_fee", "coupon_code"],
            *["timeline", "shipments", "refunds", "can_cancel", "can_pay", "invoice", "credit_notes", "web_url"],
        ]

    @extend_schema_field(SavingSerializer(many=True))
    def get_savings(self, order):
        lines = [{"label": label, "amount": amount.amount} for label, amount in order.savings]
        return SavingSerializer(lines, many=True).data

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


@extend_schema_serializer(
    examples=[OpenApiExample("Pay online", value={"address": 12, "payment_method": "razorpay"}, request_only=True)]
)
class CheckoutSerializer(serializers.Serializer):
    address = serializers.IntegerField(help_text="the id of one of the customer's addresses (addresses/)")
    payment_method = serializers.ChoiceField(choices=services.CUSTOMER_METHOD_CHOICES)

    def validate_address(self, value):
        if address := self.context["request"].user.addresses.filter(pk=value).first():
            return address
        raise serializers.ValidationError("Not one of your addresses.")


class ShippingAddressSerializer(AddressSerializer):
    """A guest's delivery address, typed at checkout: the rules of saved addresses (and of the website's form)."""

    class Meta(AddressSerializer.Meta):
        fields = Address.FIELDS


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "A guest",
            request_only=True,
            value={
                "email": "rahul@example.com",
                "shipping_address": {
                    "name": "Rahul Das",
                    "phone": "98640 12345",
                    "line1": "House 12, Zoo Road",
                    "line2": "",
                    "city": "Guwahati",
                    "district": "Kamrup Metro",
                    "state": "AS",
                    "pin": "781024",
                },
                "payment_method": "razorpay",
                "turnstile": "0.Zx…",
            },
        )
    ]
)
class GuestCheckoutSerializer(serializers.Serializer):
    """A visitor's checkout (no account): the email address for the order's emails, the delivery address, online
    payment (cash on delivery is for signed-in accounts with a confirmed email address) and the bot check."""

    email = serializers.EmailField(help_text="the order's emails (confirmation, tracking, invoice) go there")
    shipping_address = ShippingAddressSerializer()
    payment_method = serializers.ChoiceField(choices=services.CUSTOMER_METHOD_CHOICES, help_text="razorpay")
    turnstile = serializers.CharField(
        required=False, allow_blank=True, write_only=True, help_text="Turnstile's token while the bot check is on"
    )

    def validate(self, attrs):
        check_turnstile(attrs)
        return attrs


class OrderLinkSerializer(OrderSerializer):
    """The order by the link in its emails, as the website's page shows it: its PDFs by the link (no account needed);
    `can_pay` for a guest's order awaiting payment (orders/t/<token>/payment/); an account's order is paid by its
    owner, signed in."""

    LINK_PDF = {"api:order-invoice": "api:order-link-invoice", "api:order-credit-note": "api:order-link-credit-note"}

    def pdf_url(self, name, order, **kwargs):
        return reverse(self.LINK_PDF[name], kwargs={"token": order.token, **kwargs}, request=self.context["request"])

    def get_can_pay(self, order) -> bool:
        return order.user_id is None and can_pay(order)

    def get_web_url(self, order) -> str:
        return self.context["request"].build_absolute_uri(order.get_link_url())


class GuestOrderSerializer(OrderLinkSerializer):
    """A guest's new order, as its link shows it, with the link's secret: the only time the API gives it."""

    token = serializers.CharField(read_only=True, help_text="for orders/t/<token>/ and its payment; also in the emails")

    class Meta(OrderLinkSerializer.Meta):
        fields = [*OrderLinkSerializer.Meta.fields, "token"]


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


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "The SDK's success callback",
            value={"razorpay_order_id": "order_N5…", "razorpay_payment_id": "pay_N5…", "razorpay_signature": "9c1f…"},
            request_only=True,
        )
    ]
)
class PaymentConfirmSerializer(serializers.Serializer):
    """What the SDK's success callback returns."""

    razorpay_order_id = serializers.CharField()
    razorpay_payment_id = serializers.CharField()
    razorpay_signature = serializers.CharField()


@extend_schema_serializer(
    examples=[
        OpenApiExample("A guest", value={"number": "EL-2026-000123", "email": "guest@example.com"}, request_only=True)
    ]
)
class LookupSerializer(serializers.Serializer):
    number = serializers.CharField(max_length=20)
    email = serializers.EmailField(help_text="the address the order was placed with")


class LinkSentSerializer(serializers.Serializer):
    detail = serializers.CharField(help_text="always: " + services.LINK_SENT)


PDF = {(200, "application/pdf"): OpenApiTypes.BINARY}
NOTE = OpenApiParameter("note", int, OpenApiParameter.PATH, description="the credit note's id (credit_notes[].url)")


def cancel_by_customer(order):
    """Cancel while pending or paid (can_cancel); an online payment is refunded in full. Later: 400."""
    try:
        if not order.can_cancel:
            raise TransitionNotAllowed
        return services.cancel_order(order, "Cancelled by the customer.")
    except TransitionNotAllowed as error:  # also when changed meanwhile (packed by staff)
        raise refuse("This order can no longer be cancelled; see the Refund Policy.") from error


def start_payment(order):
    """The options of Razorpay's SDKs for an order awaiting online payment, with its Razorpay order (made on the first
    call; the same one afterwards). 503 while Razorpay cannot be reached."""
    if not can_pay(order):
        raise refuse(NOT_PAYABLE)
    if problem := services.coupon_problem(order):  # a payment would only be refunded
        raise refuse(f"{problem} Cancel this order and check out again without the coupon.")
    try:
        options = payments.checkout_options(order)
    except payments.Unavailable as error:
        raise PaymentServiceUnavailable(str(error)) from error
    return Response({**options, "test_mode": payments.test_mode()})


def confirm_payment(request, order):
    """The SDK's success callback for `order`, checked (signature) and confirmed with Razorpay; 400 otherwise."""
    data = PaymentConfirmSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    payment = order.payments.filter(razorpay_order_id=data.validated_data["razorpay_order_id"]).first()
    if payment is None or not payments.confirm_return(payment, data.validated_data):
        raise refuse(NOT_CONFIRMED)


CHECKOUT = PolymorphicProxySerializer(
    component_name="CheckoutAny",
    serializers=[CheckoutSerializer, GuestCheckoutSerializer],
    resource_type_field_name=None,
)
CHECKED_OUT = PolymorphicProxySerializer(
    component_name="CheckedOut", serializers=[OrderSerializer, GuestOrderSerializer], resource_type_field_name=None
)


class OrderViewSet(Private, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """The signed-in customer's own orders (another customer's: 404), checkout (a visitor's too), payment and
    cancellation."""

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

    def get_permissions(self):
        if self.action == "create":  # a visitor checks out their guest cart
            return [GuestOrCustomer(), ShopOpen()]
        return super().get_permissions()

    def answer(self, order, code=status.HTTP_200_OK):
        return Response(OrderSerializer(order, context=self.get_serializer_context()).data, status=code)

    @extend_schema(request=CHECKOUT, responses={201: CHECKED_OUT}, parameters=[HELD])
    def create(self, request, *args, **kwargs):
        """Checkout: an order from the cart at today's prices. Signed in: to a saved address (`address`); online,
        pending until paid (payment/), or cash on delivery, placed at once and the cart emptied. A visitor (guest
        cart): with `email` and `shipping_address`, online only, and Turnstile's token while the bot check is on; the
        answer is the order as its link shows it, with the link's `token` (shown here only): pay through
        orders/t/<token>/payment/."""
        user, email = buyer(request)
        if user and user.consent_pending:
            raise exceptions.PermissionDenied("A parent or guardian has not confirmed this account yet.")
        if over_limit(request, "checkout", 10, 600):  # shared with the website's checkout, per client address
            raise exceptions.Throttled(wait=600)
        if user:
            data = CheckoutSerializer(data=request.data, context={"request": request})
            data.is_valid(raise_exception=True)
            address = data.validated_data["address"].snapshot()
        else:
            data = GuestCheckoutSerializer(data=request.data)
            data.is_valid(raise_exception=True)
            email, address = data.validated_data["email"], data.validated_data["shipping_address"]
            address = Address(**address).snapshot()
        cart = caller_cart(request)
        try:
            order = services.create_order(
                cart, user=user, email=email, address=address, method=data.validated_data["payment_method"]
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
        if user is None:
            guest = GuestOrderSerializer(order, context=self.get_serializer_context())
            return Response(guest.data, status=status.HTTP_201_CREATED)
        return self.answer(order, status.HTTP_201_CREATED)

    @extend_schema(request=None, responses=OrderSerializer)
    @action(detail=True, methods=["post"], permission_classes=CUSTOMER)  # also while the shop is closed
    def cancel(self, request, **kwargs):
        """Cancel while pending or paid; an online payment is refunded in full (5–7 working days)."""
        return self.answer(cancel_by_customer(self.get_object()))

    @extend_schema(request=None, responses=PaymentStartSerializer)
    @action(detail=True, methods=["post"], throttle_scope="payment")
    def payment(self, request, **kwargs):
        """Start paying online: the options for Razorpay's mobile SDK, with the Razorpay order for this order (made
        on the first call; the same one afterwards). 503 while Razorpay cannot be reached: try again."""
        return start_payment(self.get_object())

    @extend_schema(request=PaymentConfirmSerializer, responses=OrderSerializer)
    @action(detail=True, methods=["post"], url_path="payment/confirm", throttle_scope="payment")
    def payment_confirm(self, request, **kwargs):
        """The SDK's success callback, checked (signature) and confirmed with Razorpay: the order is paid and the cart
        emptied. If Razorpay cannot be asked now the order stays pending a few minutes until its webhook arrives."""
        confirm_payment(request, self.get_object())
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


class OrderLinkView(generics.RetrieveAPIView):
    """An order by the secret of the link in its emails (`https://<domain>/orders/t/<token>/`), without signing in, as
    the website's page: status, books, address, tracking, refunds and the PDFs; read-only. Any order's link works,
    a guest's or an account's. Never kept by a browser or a proxy."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    serializer_class = OrderLinkSerializer
    lookup_field = "token"
    queryset = Order.objects.select_related("invoice").prefetch_related(
        Prefetch("items", queryset=OrderItem.objects.select_related("product")), "shipments", "refunds"
    )

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        add_never_cache_headers(response)
        return response


class OrderLinkViewSet(Private, viewsets.GenericViewSet):
    """What the order's link (`token`: the emails', or a guest's checkout's) does without signing in, as the website's
    page: pay a guest's order (the steps of an account's payment/ and payment/confirm/; an account's order is paid by
    its owner, signed in: 404), cancel any order while pending or paid, and download its PDFs."""

    authentication_classes = []
    serializer_class = OrderLinkSerializer
    lookup_field = "token"
    queryset = OrderLinkView.queryset
    content_negotiation_class = AnyAccept  # the PDFs answer whatever the client accepts

    def paying(self):
        return getattr(self, "action", None) in ("payment", "payment_confirm")

    def get_queryset(self):
        return super().get_queryset().filter(user__isnull=True) if self.paying() else super().get_queryset()

    def get_permissions(self):
        return [permissions.AllowAny(), *([ShopOpen()] if self.paying() else [])]  # cancelling: also while closed

    @property
    def throttle_scope(self):
        return "payment" if self.paying() else None

    @extend_schema(request=None, responses=PaymentStartSerializer)
    def payment(self, request, **kwargs):
        """Start paying online: the options of Razorpay's Checkout (checkout.js) or mobile SDK. 400 when `can_pay` is
        false; 503 while Razorpay cannot be reached: try again."""
        return start_payment(self.get_object())

    @extend_schema(request=PaymentConfirmSerializer, responses=OrderLinkSerializer, parameters=[HELD])
    def payment_confirm(self, request, **kwargs):
        """Checkout's success callback, checked (signature) and confirmed with Razorpay: the order, paid, and the
        visitor's guest cart (session or X-Cart-Token) emptied; or still pending a few minutes until Razorpay's webhook
        completes it (read orders/t/<token>/ again)."""
        confirm_payment(request, self.get_object())
        order = self.get_object()
        if order.status != Order.Status.CANCELLED:  # cancelled: sold out or coupon used up while paying (refunded)
            token = request.headers.get(CART_TOKEN)
            if cart := cart_by_token(token) if token else get_cart(request):
                cart.delete()
        return Response(self.get_serializer(order).data)

    @extend_schema(request=None, responses=OrderLinkSerializer)
    def cancel(self, request, **kwargs):
        """Cancel while pending or paid (`can_cancel`), as the link's page does; an online payment is refunded in full
        (5–7 working days). Later: 400, see the Refund Policy."""
        cancel_by_customer(self.get_object())
        return Response(self.get_serializer(self.get_object()).data)

    @extend_schema(responses=PDF)
    def invoice(self, request, **kwargs):
        """The invoice PDF (404 until it has been made, a few minutes after payment)."""
        return pdf_response(getattr(self.get_object(), "invoice", None))

    @extend_schema(responses=PDF, parameters=[NOTE])
    def credit_note(self, request, note, **kwargs):
        """A credit note PDF (for a refund of an invoiced order)."""
        return pdf_response(CreditNote.objects.filter(invoice__order=self.get_object(), pk=note).first())


class QuoteItemSerializer(serializers.Serializer):
    product = serializers.SlugField(help_text="a product's slug (products/)")
    quantity = serializers.IntegerField(min_value=1, max_value=10000)


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "A school",
            request_only=True,
            value={
                "school": "Cotton Collegiate H.S. School",
                "contact_name": "Anita Das",
                "email": "office@example.com",
                "phone": "98640 12345",
                "gstin": "",
                "delivery_pin": "781001",
                "note": "Before 15 November, please.",
                "items": [{"product": "physics-sample-papers", "quantity": 120}],
                "turnstile": "0.Zx…",
            },
        )
    ]
)
class QuoteSerializer(serializers.Serializer):
    """The website's school-order form (/shop/school-orders/), which validates it: the same rules and the bot check."""

    school = serializers.CharField(max_length=200)
    contact_name = serializers.CharField(max_length=120)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=30, help_text="a 10-digit Indian mobile number, as typed")
    gstin = serializers.CharField(max_length=20, required=False, allow_blank=True)
    delivery_pin = serializers.CharField(max_length=7)
    note = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    items = QuoteItemSerializer(many=True, allow_empty=False)
    turnstile = serializers.CharField(
        required=False, allow_blank=True, write_only=True, help_text="Turnstile's token while the bot check is on"
    )

    def validate(self, attrs):
        slugs = [item["product"] for item in attrs["items"]]
        products = {product.slug: product for product in Product.objects.filter(is_active=True, slug__in=slugs)}
        if missing := [slug for slug in slugs if slug not in products]:
            raise serializers.ValidationError({"items": [f"Not on sale: {', '.join(missing)}."]})
        copies = {f"copies_{products[item['product']].pk}": item["quantity"] for item in attrs["items"]}
        self.form = QuoteRequestForm(data={**attrs, **copies})
        if not self.form.is_valid():
            errors = {"non_field_errors" if name == "__all__" else name: e for name, e in self.form.errors.items()}
            raise serializers.ValidationError(errors)
        return attrs


class QuoteSentSerializer(serializers.Serializer):
    number = serializers.CharField(help_text="QT-2026-00012")
    detail = serializers.CharField()


class QuoteView(generics.GenericAPIView):
    """School and bulk orders, the website's form: the buyer's details and the copies of each book; staff are emailed
    and send a quotation. Turnstile's token (`turnstile`) while the bot check is on (config/). At most 5 an hour per
    client address, the website's included."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    serializer_class = QuoteSerializer

    @extend_schema(responses={201: QuoteSentSerializer})
    def post(self, request, *args, **kwargs):
        if over_limit(request, "quote", 5, 3600):
            raise exceptions.Throttled(wait=3600)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        quote = serializer.form.save()
        services.email_staff(f"Quotation asked for: {quote.school}", "shop/email/quote_request.txt", {"quote": quote})
        return Response({"number": quote.number, "detail": QUOTE_SENT}, status=status.HTTP_201_CREATED)
