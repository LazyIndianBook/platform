"""The Customers module's staff API, under /api/v1/staff/users/ (API.md "Customers (staff)"; staff/README.md
"Customers"; plan 5.4), on the staff API's rules (staff.api.StaffView): the admin host only, a member of staff with a
second factor (or an API key for the reads), each action's catalogued permission, a re-authentication for the high
ones, every refusal an `authz_fail`, cursor pages, `Cache-Control: no-store`. It takes the customers' routes over from
staff.api.UserViewSet (which it extends and does not edit: the account actions, the reveal, the impersonation are
that class's, unchanged) and adds:

- the list's tabs (`?kind=students|parents|guests`), the badges on every row, and the access log (a search for a person
  is a `customer.lookup` event holding the query's keyed hash and how many people it found);
- users/{id}/timeline/ and users/{id}/commerce/ (each opening a `sensitive_read`, a child's marked as one);
- users/consent-pending/ (the children waiting for a parent) and users/{id}/consent/verify/ (a parent's consent
  recorded by hand, with its evidence);
- the account actions named by bulk jobs (staff.customers: user.suspend … user.resend_consent), started through jobs/.
"""

from django.utils import timezone
from django_filters import rest_framework as django_filters
from drf_spectacular.utils import OpenApiParameter, PolymorphicProxySerializer, extend_schema
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.routers import SimpleRouter

from api.schema import AutoSchema

from . import audit, customers
from .api import Cursor, CustomerFilter, UserViewSet
from .backends import scoped
from .customers import KIND_NAMES, METHODS, classify
from .privacy import mask_email, mask_phone
from .serializers import CustomerSerializer, age_band, locked_usernames


class StaffSchema(AutoSchema):
    def get_tags(self):
        return ["customers (staff)"]


METHOD_CHOICES = [(method.value, method.label) for method in METHODS]  # the methods a parent's consent is verified by


class Oldest(Cursor):
    """The children waiting for a parent: the first registered first (their waiting is the longest)."""

    ordering = ("created", "pk")


# ---- Serializers (explicit fields; contacts masked) ----


class CustomerTimelineRowSerializer(serializers.Serializer):
    at = serializers.DateTimeField()
    kind = serializers.CharField(help_text=", ".join(KIND_NAMES))
    label = serializers.CharField(help_text="in words: numbers and codes, never an address or a number")
    href = serializers.CharField(allow_null=True, help_text="the console's page for it (/orders/EL-…/), or null")


class CustomerTimelineSerializer(serializers.Serializer):
    child = serializers.BooleanField(help_text="a student under 18: the course shows in counts, never a trail")
    rows = CustomerTimelineRowSerializer(many=True, help_text="newest first, at most 200")
    next_before = serializers.CharField(allow_null=True, help_text="`?before=` for the older rows; null: that is all")
    withheld = serializers.ListField(
        child=serializers.CharField(), help_text="the parts the reader's permissions leave out (their kinds)"
    )


class CustomerCommerceAddressSerializer(serializers.Serializer):
    city = serializers.CharField()
    district = serializers.CharField()
    state = serializers.CharField()
    pin = serializers.CharField()
    phone = serializers.CharField(help_text="masked")
    is_default = serializers.BooleanField()


class CustomerCommerceTagSerializer(serializers.Serializer):
    name = serializers.CharField()
    orders = serializers.IntegerField(help_text="how many of their orders carry it")


class CustomerCommerceSerializer(serializers.Serializer):
    child = serializers.BooleanField(help_text="a student under 18: the counts only, the rest is null")
    orders = serializers.IntegerField(help_text="their live orders, any state")
    kept = serializers.IntegerField(help_text="placed (paid online, or placed to pay on delivery) and not cancelled")
    cancelled = serializers.IntegerField()
    returns = serializers.IntegerField(help_text="returns asked for")
    rtos = serializers.IntegerField(help_text="parcels that came back undelivered (the shipping outcome)")
    spent = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True, help_text="rupees, kept orders")
    refunded = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True, help_text="rupees, processed")
    lifetime_value = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        allow_null=True,
        help_text="spent less refunded, so far (a record, no forecast)",
    )
    average_order = serializers.DecimalField(
        max_digits=12, decimal_places=2, allow_null=True, help_text="spent over the kept orders; null without one"
    )
    first_order_at = serializers.DateTimeField(allow_null=True)
    last_order_at = serializers.DateTimeField(allow_null=True)
    addresses = CustomerCommerceAddressSerializer(many=True, allow_null=True, help_text="saved, masked")
    tags = CustomerCommerceTagSerializer(many=True, allow_null=True, help_text="staff's words on their orders")


class CustomerGuestSerializer(serializers.Serializer):
    """A buyer without an account: the orders placed with one email address, shown by their newest."""

    id = serializers.IntegerField(help_text="their newest order's id")
    name = serializers.SerializerMethodField(help_text="as on the delivery address")
    email = serializers.SerializerMethodField(help_text="masked")
    phone = serializers.SerializerMethodField(help_text="masked")
    orders = serializers.SerializerMethodField(help_text="how many orders carry this address")
    last_order = serializers.CharField(source="number", help_text="the newest order's number")
    last_order_at = serializers.SerializerMethodField()

    def get_name(self, order) -> str:
        return str((order.shipping_address or {}).get("name", ""))

    def get_email(self, order) -> str:
        return mask_email(order.email)

    def get_phone(self, order) -> str:
        return mask_phone((order.shipping_address or {}).get("phone", ""))

    def get_orders(self, order) -> int:
        return self.context.get("guest_counts", {}).get(order.email.lower(), 1)

    def get_last_order_at(self, order) -> str | None:
        moment = order.placed_at or order.created
        return serializers.DateTimeField().to_representation(moment) if moment else None


class CustomerConsentPendingSerializer(serializers.ModelSerializer):
    """A student under 18 whose parent has not confirmed: the parent's contact masked, the link's life."""

    board = serializers.SlugRelatedField(slug_field="short_name", read_only=True)
    age_band = serializers.SerializerMethodField()
    email_verified = serializers.SerializerMethodField(help_text="the link goes only once the student's own is")
    parent_contact = serializers.SerializerMethodField(help_text="masked")
    parent_channel = serializers.SerializerMethodField(help_text="email or sms: where a link goes")
    blocking = serializers.SerializerMethodField(help_text="the account reads only until the parent confirms")
    links_sent = serializers.IntegerField(source="links", read_only=True)
    last_link_at = serializers.DateTimeField(source="last_link", read_only=True, allow_null=True)
    link_expires_at = serializers.SerializerMethodField(help_text="the last link works for 7 days; null: none sent")
    link_expired = serializers.SerializerMethodField()
    links_today = serializers.IntegerField(read_only=True, help_text="sent today for this account")
    daily_limit = serializers.SerializerMethodField(help_text="links a day to one parent's address or number")

    class Meta:
        model = CustomerSerializer.Meta.model
        fields = ["id", "full_name", "class_level", "board", "created", "age_band", "email_verified", "parent_contact"]
        fields += ["parent_channel", "blocking", "links_sent", "last_link_at", "link_expires_at", "link_expired"]
        fields += ["links_today", "daily_limit"]

    def get_age_band(self, user) -> str:
        return age_band(user)

    def get_email_verified(self, user) -> bool:
        return any(address.verified for address in user.emailaddress_set.all())

    def get_parent_contact(self, user) -> str:
        contact = user.parent_contact
        return mask_email(contact) if "@" in contact else mask_phone(contact)

    def get_parent_channel(self, user) -> str:
        return "email" if "@" in user.parent_contact else "sms"

    def get_blocking(self, user) -> bool:
        return customers.blocking()

    def get_link_expires_at(self, user) -> str | None:
        expires = customers.link_expires_at(user.last_link)
        return serializers.DateTimeField().to_representation(expires) if expires else None

    def get_link_expired(self, user) -> bool:
        expires = customers.link_expires_at(user.last_link)
        return bool(expires and expires <= timezone.now())

    def get_daily_limit(self, user) -> int:
        return customers.DAILY_LINKS


class CustomerConsentVerifySerializer(serializers.Serializer):
    method = serializers.ChoiceField(
        choices=METHOD_CHOICES,
        help_text="staff_manual: staff checked it by hand; adult_account: the parent's own verified ExamLeaf account; "
        "digilocker: a DigiLocker token",
    )
    evidence_ref = serializers.CharField(
        max_length=200,
        help_text="where the evidence is: a ticket's number, a letter's date. Never the document, never a contact",
    )
    reason = serializers.CharField(max_length=500, help_text="why: kept in the audit trail")

    def validate_evidence_ref(self, value):
        value = " ".join(value.split())
        if not value:
            raise serializers.ValidationError("Say where the evidence is.")
        if problem := customers.evidence_problem(value):
            raise serializers.ValidationError(problem)
        return value

    def validate_reason(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Say why.")
        return value


class CustomerConsentRecordSerializer(serializers.Serializer):
    """The consent just recorded: the ledger's row."""

    id = serializers.IntegerField()
    event = serializers.CharField()
    method = serializers.CharField()
    by_parent = serializers.BooleanField()
    verified_at = serializers.DateTimeField()
    verified_by = serializers.IntegerField(
        source="verified_by_id", allow_null=True, help_text="the member of staff who recorded it"
    )
    evidence_ref = serializers.CharField()
    notice_version = serializers.CharField()
    created = serializers.DateTimeField()


# ---- Filters ----


class CustomerListFilter(CustomerFilter):
    """staff.api.CustomerFilter's, with the tabs. `q` takes an email address (exactly), a mobile number or its last
    digits (4 or more), or three letters of a name; what it takes for a person is a lookup (the access log)."""

    q = django_filters.CharFilter(
        method="search",
        help_text="an email address (exactly), a mobile number in any Indian format or its last digits (4 or more), "
        "or 3 letters or more of a name: a lookup of a person, written to the access log",
    )
    kind = django_filters.ChoiceFilter(
        choices=customers.KINDS,
        method="filter_kind",
        help_text="the tab: students (a class level, or under 18), parents (adult accounts a student named as their "
        "parent's contact), guests (buyers without an account: another shape of row, by their orders)",
    )

    class Meta(CustomerFilter.Meta):
        pass

    def search(self, queryset, name, value):
        return customers.search(queryset, *classify(value))

    def filter_kind(self, queryset, name, value):
        if value == "students":
            return customers.students(queryset)
        if value == "parents":
            return customers.parents(queryset)
        return queryset  # guests: another list (the view)


# ---- The viewset ----


class CustomerViewSet(UserViewSet):
    """Customers (staff are in people/): the list with its tabs and badges, a record, its timeline and commerce, the
    children waiting for a parent and a parent's consent by hand; and everything staff.api.UserViewSet has, as it was
    (the reveal with a reason, the account actions, the impersonation)."""

    schema = StaffSchema()
    filterset_class = CustomerListFilter
    permissions = {
        **UserViewSet.permissions,
        "timeline": "accounts.view_user",
        "commerce": "shop.view_order",  # the figures are the orders' (the account is in reach: get_queryset)
        "consent_pending": "accounts.view_user",
        "verify_consent": "staff.verify_consent",
    }

    def guests_tab(self):
        return self.action == "list" and self.request.query_params.get("kind") == "guests"

    def get_queryset(self):
        if self.guests_tab():
            return customers.guest_orders(self.request.user)
        return super().get_queryset().select_related("teacher_profile").prefetch_related("authenticator_set")

    def filter_queryset(self, queryset):
        if self.guests_tab():  # orders, not accounts: the filters of accounts do not apply
            query = self.request.query_params.get("q", "")
            kind, value = classify(query) if query.strip() else ("", "")
            return customers.guests(queryset, kind, value)
        return super().filter_queryset(queryset)

    def get_serializer_class(self):
        return CustomerGuestSerializer if self.guests_tab() else super().get_serializer_class()

    def get_serializer_context(self):
        return {**super().get_serializer_context(), **getattr(self, "page_context", {})}

    @extend_schema(
        responses=PolymorphicProxySerializer(
            component_name="CustomerRow",
            serializers=[CustomerSerializer, CustomerGuestSerializer],
            resource_type_field_name=None,
            many=True,
        )
    )
    def list(self, request, *args, **kwargs):
        """The list: accounts (every row with its badges), or with `kind=guests` the buyers without an account."""
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if self.guests_tab():
            self.page_context = {"guest_counts": customers.guest_counts(self.get_queryset(), page)}
        else:
            self.page_context = {"locked": locked_usernames(page)}  # the page's lock-outs in one query
        response = self.get_paginated_response(self.get_serializer(page, many=True).data)
        self.log_lookup(request, queryset)
        return response

    def log_lookup(self, request, queryset):
        """A search for a person (an email address, a number, a name) is one `customer.lookup` event: the query's keyed
        hash and how many it found (to 1,000), never the query. Browsing the tabs is not a lookup."""
        kind, value = classify(request.query_params.get("q", ""))
        if kind == "none":
            return
        found = queryset.order_by().values("pk")[: customers.GUEST_PREVIEW_LIMIT + 1].count()
        more = {"more": True} if found > customers.GUEST_PREVIEW_LIMIT else {}
        source = "guests" if self.guests_tab() else "users"
        audit.lookup(request, value, min(found, customers.GUEST_PREVIEW_LIMIT), kind=kind, source=source, **more)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "before", str, description="the older rows: the `next_before` of the last answer (or a time)"
            ),
            OpenApiParameter("kind", str, description=f"only these kinds, comma-separated: {', '.join(KIND_NAMES)}"),
        ],
        responses=CustomerTimelineSerializer,
    )
    @action(detail=True, methods=["get"], filter_backends=[], pagination_class=None)
    def timeline(self, request, *args, **kwargs):
        """One person's story, newest first, in one list: orders, payments and refunds, book codes redeemed, course
        access, a course-use summary (a child's: counts and the last active week; an adult's adds clips completed by
        week), tickets, SMS and emails sent, consent events, staff notes, and for whoever reads the audit log the staff
        actions on the account. Opening it is a `sensitive_read` (a child's marked `child`); the newest 200 rows, no
        query per row; `withheld` names the parts the reader may not see."""
        user = self.get_object()
        kinds = {kind for kind in request.query_params.get("kind", "").split(",") if kind}
        if unknown := kinds - set(KIND_NAMES):
            raise serializers.ValidationError({"kind": [f"Not a kind: {', '.join(sorted(unknown))}."]})
        audit.record(
            "sensitive_read", request=request, target=user, details={"what": "timeline", "child": user.is_minor}
        )
        data = customers.timeline(
            request.user, user, kinds=kinds, before=request.query_params.get("before"), request=request
        )
        return Response(CustomerTimelineSerializer(data).data)

    @extend_schema(responses=CustomerCommerceSerializer)
    @action(detail=True, methods=["get"], filter_backends=[], pagination_class=None)
    def commerce(self, request, *args, **kwargs):
        """What they bought: orders, lifetime value so far, the average order, refunds, parcels that came back,
        saved addresses (masked) and the tags of their orders. A student under 18: the counts only. A
        `sensitive_read`."""
        user = self.get_object()
        audit.record(
            "sensitive_read", request=request, target=user, details={"what": "commerce", "child": user.is_minor}
        )
        return Response(CustomerCommerceSerializer(customers.commerce(request.user, user)).data)

    @extend_schema(responses=CustomerConsentPendingSerializer(many=True))
    @action(
        detail=False,
        methods=["get"],
        url_path="consent-pending",
        filter_backends=[],
        pagination_class=Oldest,
    )
    def consent_pending(self, request, *args, **kwargs):
        """The students under 18 waiting for a parent, the first registered first: the parent's contact (masked), how
        many links went, the last one's time and expiry, and how many today. The link is sent again with
        `resend-verification/`, or the consent recorded by hand with `consent/verify/`."""
        accounts = scoped(customers.waiting_children(), request.user, "accounts.view_user")
        rows = customers.with_links(accounts).select_related("board").prefetch_related("emailaddress_set")
        page = self.paginate_queryset(rows)
        serializer = CustomerConsentPendingSerializer(page, many=True, context=self.get_serializer_context())
        return self.get_paginated_response(serializer.data)

    @extend_schema(request=CustomerConsentVerifySerializer, responses={201: CustomerConsentRecordSerializer})
    @action(detail=True, methods=["post"], url_path="consent/verify", filter_backends=[], pagination_class=None)
    def verify_consent(self, request, *args, **kwargs):
        """A parent's consent recorded by hand (a student under 18 whose parent has not confirmed): a verified consent
        with its method, where the evidence is and who recorded it; the account's flag clears at once and the parent is
        told by email. 400 for an adult, an erased account, one asking to be deleted, or one whose consent a parent
        confirmed already."""
        user, staff = self.get_object(), self.human()
        data = CustomerConsentVerifySerializer(data=request.data)
        data.is_valid(raise_exception=True)
        record = customers.verify_consent(staff, user.pk, request=request, **data.validated_data)
        return Response(CustomerConsentRecordSerializer(record).data, status=status.HTTP_201_CREATED)


# staff/urls.py mounts this as users/: the list, a record and its actions, as the staff API's own router had them
router = SimpleRouter()
router.register("", CustomerViewSet, basename="user")
urlpatterns = router.urls
