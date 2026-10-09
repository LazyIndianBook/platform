"""The signed-in person's own privacy endpoints (API.md "Profile and data rights"): their nominee, who acts for them
after their death or incapacity (DPDP s.14, r.14(4)); and a marketing consent withdrawn as easily as it was given
(s.6(4)), which asks each processor holding marketing data to stop (an inbox task: staff.privacy.cease_tasks).
Throttled as the account's other data rights; refused while a member of staff is logged in as the customer."""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils.cache import patch_cache_control
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import exceptions, generics, permissions, serializers, status
from rest_framework.response import Response

from accounts.forms import normalise_phone
from accounts.models import ConsentRecord, Nominee
from pages.models import Page
from pages.versions import versions


class PageVersionSerializer(serializers.Serializer):
    number = serializers.IntegerField(help_text='"Version 2"')
    version = serializers.CharField(help_text="the label consent records keep (consents/notice_version)")
    effective_from = serializers.DateField(help_text="in force from that day")
    summary = serializers.CharField(allow_blank=True, help_text="what it changed, in a line")
    in_force = serializers.BooleanField()
    upcoming = serializers.BooleanField(help_text="published for a later day: not in force yet")


class PageVersionsView(generics.GenericAPIView):
    """A legal page's versions, newest first (the one waiting for its day first of all): its number, the day it is
    in force from and what it changed. Public, cacheable for 15 minutes."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    serializer_class = PageVersionSerializer
    queryset = Page.objects.all()
    lookup_field = "slug"
    pagination_class = None

    @extend_schema(responses=PageVersionSerializer(many=True))
    def get(self, request, *args, **kwargs):
        page = self.get_object()
        response = Response(PageVersionSerializer([vars(row) for row in reversed(versions(page))], many=True).data)
        patch_cache_control(response, public=True, max_age=900)
        return response


class NomineeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Nominee
        fields = ["name", "contact", "relation", "verified_at", "created", "updated"]
        read_only_fields = ["verified_at", "created", "updated"]

    def validate_name(self, name):
        return " ".join(name.split())

    def validate_contact(self, contact):
        contact = contact.strip()
        if "@" in contact:
            try:
                validate_email(contact)
            except DjangoValidationError as error:
                raise serializers.ValidationError("Enter an email address or an Indian mobile number.") from error
            contact = contact.lower()
        elif not (contact := normalise_phone(contact) or ""):
            raise serializers.ValidationError("Enter an email address or an Indian mobile number.")
        user = self.context["request"].user
        if contact in {user.email.lower(), str(user.phone), user.login_phone}:
            raise serializers.ValidationError("The nominee's own address or number, not yours.")
        return contact


class NomineeView(generics.GenericAPIView):
    """My nominee: GET it (404 while none), PUT it (made or changed; a nomination proved at a claim is not changed
    here), DELETE it (withdrawn)."""

    serializer_class = NomineeSerializer
    throttle_scope = "dj_rest_auth"

    def nominee(self):
        return Nominee.objects.filter(user=self.request.user).first()

    def get(self, request, *args, **kwargs):
        if (nominee := self.nominee()) is None:
            raise exceptions.NotFound("No nominee recorded.")
        return Response(self.get_serializer(nominee).data)

    @extend_schema(responses={200: NomineeSerializer, 201: NomineeSerializer})
    def put(self, request, *args, **kwargs):
        with transaction.atomic():
            nominee = Nominee.objects.select_for_update().filter(user=request.user).first()
            if nominee is not None and nominee.verified_at:
                raise serializers.ValidationError(
                    {"non_field_errors": ["This nomination was proved for a claim: write to us to change it."]}
                )
            data = self.get_serializer(nominee, data=request.data)
            data.is_valid(raise_exception=True)
            saved = data.save(user=request.user)
        return Response(
            self.get_serializer(saved).data, status=status.HTTP_200_OK if nominee else status.HTTP_201_CREATED
        )

    @extend_schema(responses={204: None})
    def delete(self, request, *args, **kwargs):
        if not Nominee.objects.filter(user=request.user, verified_at=None).delete()[0]:
            raise exceptions.NotFound("No nominee recorded.")
        return Response(status=status.HTTP_204_NO_CONTENT)


class WithdrawSerializer(serializers.Serializer):
    purpose = serializers.ChoiceField(choices=[ConsentRecord.Purpose.MARKETING.value], help_text="marketing")
    channel = serializers.ChoiceField(
        choices=ConsentRecord.Channel.choices, required=False, allow_blank=True, help_text="one channel; empty: all"
    )


WITHDRAWN = inline_serializer(
    "ConsentWithdrawn",
    {
        "purpose": serializers.CharField(),
        "channel": serializers.CharField(allow_blank=True),
        "withdrawn_at": serializers.DateTimeField(),
        "detail": serializers.CharField(),
    },
)


class ConsentWithdrawView(generics.GenericAPIView):
    """Withdraw a marketing consent (one channel, or every one): recorded in the consent ledger (once: a second
    withdrawal answers the first), and each processor that holds marketing data is told to stop (an inbox task)."""

    serializer_class = WithdrawSerializer
    throttle_scope = "dj_rest_auth"

    @extend_schema(responses={200: WITHDRAWN, 201: WITHDRAWN})
    def post(self, request, *args, **kwargs):
        from staff.privacy import cease_tasks

        data = self.get_serializer(data=request.data)
        data.is_valid(raise_exception=True)
        purpose, channel = data.validated_data["purpose"], data.validated_data.get("channel", "")
        with transaction.atomic():
            ledger = ConsentRecord.objects.filter(user=request.user, purpose=purpose, channel=channel)
            latest = ledger.order_by("-created", "-pk").first()
            created = latest is None or latest.event != ConsentRecord.Event.WITHDRAWN
            if created:
                latest = ConsentRecord.record(
                    request, request.user, event=ConsentRecord.Event.WITHDRAWN, purpose=purpose, channel=channel
                )
                transaction.on_commit(lambda: cease_tasks(latest), robust=True)
        where = f"on {latest.get_channel_display()}" if channel else "on any channel"
        return Response(
            {
                "purpose": purpose,
                "channel": channel,
                "withdrawn_at": latest.created,
                "detail": f"We will send you no more marketing messages {where}.",
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )
