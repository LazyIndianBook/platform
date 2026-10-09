"""The message templates' API, under /api/v1/staff/templates/ (staff/urls.py; API.md "Templates (staff)"), on the staff
app's rules (staff.api.StaffView): the registry of what the site sends by SMS, email and (Phase D) WhatsApp, as
registered with DLT and MSG91 (ops.models.MessageTemplate). Reading is ops.view_messagetemplate's (ADMIN, MARKETING,
AUDITOR, OWNER), adding ops.add_messagetemplate's, changing and test sends ops.change_messagetemplate's (ADMIN, OWNER).
A template is never deleted: deactivate it. A test send goes to the member of staff's own confirmed mobile number or
email address only, never to anyone else; WhatsApp sends nothing before Phase D. Each change is an audit event."""

import re

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django_filters import rest_framework as django_filters
from drf_spectacular.utils import extend_schema
from rest_framework import exceptions, mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.routers import SimpleRouter

from api.schema import AutoSchema
from staff import audit
from staff.api import StaffView
from staff.backends import scoped

from .models import MessageTemplate

VIEW = "ops.view_messagetemplate"
EVENT = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
DLT_ID = re.compile(r"^\d{12,25}$")  # DLT's template and principal entity ids: long numbers (19 digits on most)
HEADER = re.compile(r"^(?:[A-Z]{6}|\d{6})$")  # a DLT header: 6 letters (service, transactional), 6 digits (promotional)
MSG91_ID = re.compile(r"^[A-Za-z0-9_-]{6,60}$")
WHATSAPP_NAME = re.compile(r"^[a-z0-9_]{1,100}$")
VARIABLE_NAME = re.compile(r"^[a-z][a-z0-9_]{0,19}$")
PLACEHOLDER = "{#var#}"
CATEGORIES = {  # which categories each channel takes
    MessageTemplate.Channel.SMS: {"transactional", "service", "promotional"},
    MessageTemplate.Channel.EMAIL: {"transactional", "service", "promotional"},
    MessageTemplate.Channel.WHATSAPP: {"utility", "authentication", "promotional"},
}
SAMPLES = {  # a test send's value of a variable not given, by its type (DLT's typed variables)
    "numeric": "123456",
    "alphanumeric": "TEST01",
    "url": "https://examleaf.in/",
    "urlott": "https://examleaf.in/t/TEST/",
    "cbn": "1800000000",
    "email": "test@examleaf.in",
}


class StaffSchema(AutoSchema):
    def get_tags(self):
        return ["templates (staff)"]


class VariableSerializer(serializers.Serializer):
    name = serializers.RegexField(VARIABLE_NAME, help_text="as the provider names it: var1, otp …")
    type = serializers.ChoiceField(choices=MessageTemplate.VARIABLE_TYPES)
    max_length = serializers.IntegerField(min_value=1, max_value=30, help_text="DLT: at most 30 characters")
    about = serializers.CharField(max_length=100, allow_blank=True, required=False, default="")


class TemplateSerializer(serializers.ModelSerializer):
    language = serializers.ChoiceField(choices=MessageTemplate.Language.choices, default=MessageTemplate.Language.EN)
    variables = VariableSerializer(many=True, required=False)
    days_unused = serializers.SerializerMethodField(help_text="since its last use (or since it was added)")
    warnings = serializers.SerializerMethodField(help_text="what to see to, in plain words")

    class Meta:
        model = MessageTemplate
        fields = [
            *["id", "event", "channel", "language", "text", "subject", "variables", "dlt_template_id", "pe_id"],
            *["header", "header_suffix", "msg91_id", "whatsapp_name", "category", "approval_state", "last_used_at"],
            *["self_certified_on", "notes", "created", "modified", "days_unused", "warnings"],
        ]
        read_only_fields = ["id", "last_used_at", "created", "modified", "days_unused", "warnings"]

    def get_days_unused(self, template) -> int:
        since = template.last_used_at or template.created
        return max(0, (timezone.now() - since).days)

    def get_warnings(self, template) -> list[str]:
        return warnings_of(template)

    def validate_event(self, value):
        if not EVENT.match(value):
            raise serializers.ValidationError("Small letters, digits and _: otp, order_placed …")
        return value

    def validate_dlt_template_id(self, value):
        if value and not DLT_ID.match(value):
            raise serializers.ValidationError("DLT's template id: the long number DLT gave it (19 digits).")
        return value

    def validate_pe_id(self, value):
        if value and not DLT_ID.match(value):
            raise serializers.ValidationError("DLT's principal entity id: the long number of the registration.")
        return value

    def validate_header(self, value):
        value = value.strip().upper()
        if value and not HEADER.match(value):
            raise serializers.ValidationError("6 letters (EXMLEF), or 6 digits for a promotional header.")
        return value

    def validate_msg91_id(self, value):
        if value and not MSG91_ID.match(value):
            raise serializers.ValidationError("MSG91's template id: letters and digits, as MSG91 shows it.")
        return value

    def validate_whatsapp_name(self, value):
        if value and not WHATSAPP_NAME.match(value):
            raise serializers.ValidationError("Small letters, digits and _ only, as Meta registered it.")
        return value

    def validate(self, data):
        current = {name: getattr(self.instance, name) for name in self.Meta.fields if hasattr(self.instance, name)}
        merged = {**current, **data}
        problems = {}
        channel, event = merged.get("channel"), merged.get("event")
        if self.instance is not None and ({"event", "channel", "language"} & set(data)):
            if any(data.get(name, current.get(name)) != current.get(name) for name in ("event", "channel", "language")):
                problems["event"] = ["What a template is for stays: add another one instead."]
        if channel == MessageTemplate.Channel.SMS and event not in settings.SMS_KINDS:
            problems["event"] = [f"An SMS is sent for one of: {', '.join(settings.SMS_KINDS)}."]
        if merged.get("category") not in CATEGORIES.get(channel, set()):
            problems["category"] = [f"For {channel}: one of {', '.join(sorted(CATEGORIES.get(channel, set())))}."]
        variables = merged.get("variables") or []
        names = [variable["name"] for variable in variables]
        if len(set(names)) != len(names):
            problems["variables"] = ["Each variable once."]
        text = merged.get("text") or ""
        if channel == MessageTemplate.Channel.SMS and text and text.count(PLACEHOLDER) != len(variables):
            problems["text"] = [f"{text.count(PLACEHOLDER)} {PLACEHOLDER} in the text, {len(variables)} variables."]
        if channel == MessageTemplate.Channel.SMS and event == "otp" and names != ["otp"]:
            problems["variables"] = ["A one-time code's template has one variable: otp (MSG91's OTP API fills it)."]
        if merged.get("approval_state") == MessageTemplate.Approval.APPROVED:
            if channel == MessageTemplate.Channel.SMS and not merged.get("msg91_id"):
                problems["msg91_id"] = ["An approved SMS template needs MSG91's id: it is what is sent."]
            if channel == MessageTemplate.Channel.WHATSAPP and not merged.get("whatsapp_name"):
                problems["whatsapp_name"] = ["An approved WhatsApp template needs its name."]
        if channel == MessageTemplate.Channel.EMAIL and merged.get("approval_state") == "approved":
            if not merged.get("subject"):
                problems["subject"] = ["An email needs its subject."]
        if problems:
            raise serializers.ValidationError(problems)
        return data


def warnings_of(template):
    """What a template's row should see to: the DLT id, the 90-day idle rule, the yearly self-certification."""
    found = []
    if template.channel == MessageTemplate.Channel.SMS:
        if not template.dlt_template_id:
            found.append("No DLT template id: add the one DLT gave it.")
        if not template.header:
            found.append("No sender header.")
    if template.approval_state == MessageTemplate.Approval.APPROVED:
        since = template.last_used_at or template.created
        days = (timezone.now() - since).days
        if template.channel == MessageTemplate.Channel.SMS and days >= IDLE_WARN_DAYS:
            found.append(f"Unused for {days} days: DLT deactivates a template unused for 90 days.")
        certified = template.self_certified_on
        if certified is None or (timezone.localdate() - certified).days >= CERTIFY_WARN_DAYS:
            found.append("Its yearly self-certification is due.")
    return found


IDLE_WARN_DAYS = 75  # two weeks' notice before DLT's 90 days
CERTIFY_WARN_DAYS = 335  # a month's notice before the year is out


class TemplateFilter(django_filters.FilterSet):
    class Meta:
        model = MessageTemplate
        fields = ["channel", "language", "approval_state", "event", "category"]


class TestSendSerializer(serializers.Serializer):
    variables = serializers.DictField(
        child=serializers.CharField(max_length=30, allow_blank=True),
        required=False,
        default=dict,
        help_text="a value for each variable (30 characters at most); a sample of its type otherwise",
    )


class TestSentSerializer(serializers.Serializer):
    sent = serializers.BooleanField()
    to = serializers.CharField(help_text="where it went: the last digits of your number, or your address masked")
    detail = serializers.CharField()


class TemplateViewSet(
    StaffView,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """The template registry (filters channel, language, approval_state, event, category), by event: add one, change
    one (PATCH: what it is for, its channel and language stay), send yourself a test. Never deleted: deactivated."""

    schema = StaffSchema()
    queryset = MessageTemplate.objects.all()
    serializer_class = TemplateSerializer
    filterset_class = TemplateFilter
    pagination_class = None  # a few dozen rows at most
    throttle_scopes = {"test": "staff_test_send"}
    permissions = {
        **dict.fromkeys(["list", "retrieve"], VIEW),
        "create": "ops.add_messagetemplate",
        **dict.fromkeys(["partial_update", "test"], "ops.change_messagetemplate"),
    }

    def get_queryset(self):
        return scoped(MessageTemplate.objects.order_by("event", "channel", "language"), self.request.user, VIEW)

    def perform_create(self, serializer):
        with transaction.atomic():
            template = serializer.save()
            details = {"event": template.event, "channel": template.channel, "language": template.language}
            audit.record("template.created", request=self.request, target=template, details=details)

    def partial_update(self, request, *args, **kwargs):
        template = self.get_object()
        serializer = self.get_serializer(template, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        before = {name: getattr(template, name) for name in serializer.validated_data}
        with transaction.atomic():
            template = serializer.save()
            changes = {
                name: [before[name], getattr(template, name)]
                for name in before
                if before[name] != getattr(template, name)
            }
            audit.record("template.changed", request=request, target=template, changes=changes)
        return Response(self.get_serializer(template).data)

    @extend_schema(request=TestSendSerializer, responses=TestSentSerializer)
    @action(detail=True, methods=["post"])
    def test(self, request, *args, **kwargs):
        """Send this template to yourself: an SMS to your own confirmed mobile number, an email to your own address."""
        user, template = self.human(), self.get_object()
        asked = TestSendSerializer(data=request.data)
        asked.is_valid(raise_exception=True)
        given = asked.validated_data["variables"]
        values = {v["name"]: given.get(v["name"]) or SAMPLES[v["type"]][: v["max_length"]] for v in template.variables}
        if template.channel == MessageTemplate.Channel.WHATSAPP:
            raise exceptions.ValidationError({"non_field_errors": ["WhatsApp comes in Phase D: nothing is sent yet."]})
        if template.channel == MessageTemplate.Channel.SMS:
            sent, to, detail = send_test_sms(template, user, values)
        else:
            sent, to, detail = send_test_email(template, user, values)
        with transaction.atomic():
            details = {"event": template.event, "channel": template.channel, "sent": sent}
            audit.record("template.test_sent", request=request, target=template, details=details)
        return Response(TestSentSerializer({"sent": sent, "to": to, "detail": detail}).data)


def send_test_sms(template, user, values):
    from .sms import queue_sms

    if not (user.login_phone and user.login_phone_verified):
        raise exceptions.ValidationError(
            {"non_field_errors": ["Confirm a mobile number on your own account first: a test goes there only."]}
        )
    if settings.SMS_BACKEND == "msg91" and not template.msg91_id:
        raise exceptions.ValidationError({"non_field_errors": ["It has no MSG91 id yet: nothing can be sent."]})
    sent = queue_sms(template.event, user.login_phone, values, user=user, template=template.msg91_id)
    detail = (
        "Sent: it should arrive within a minute." if sent else "Not sent: SMS are off here, or a limit was reached."
    )
    return sent, f"******{user.login_phone[-4:]}", detail


def send_test_email(template, user, values):
    from staff.privacy import mask_email

    from .tasks import queue_text_email

    text = template.text or f"A test of the template for {template.event}."
    for value in values.values():
        text = text.replace(PLACEHOLDER, value, 1)
    subject = f"[test] {template.subject or template.event}"
    queue_text_email(user.email, subject, f"{text}\n\n(A test from the console's template registry.)")
    return True, mask_email(user.email), "Sent to your own address."


router = SimpleRouter()
router.register("", TemplateViewSet, basename="template")
urlpatterns = router.urls  # under /api/v1/staff/templates/ (staff/urls.py)
