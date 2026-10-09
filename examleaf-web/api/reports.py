"""Readers' "Report a mistake" and the public errata (API.md "Catalogue and solutions"; content/README.md): POST
reports/ takes a report on a solution, a question, a quiz item or a clip (the page prefills the paper, the question,
the step and the printing), with Turnstile's token while the bot check is on, at most 5 an hour and 20 a day per client
address (the website's form included), a honeypot, and spam set apart by content.reports' rules; GET errata/?book= are
the mistakes staff publish for a book, per printing. A signed-in reader is the reporter (a verified teacher's report is
marked); anyone may report."""

from django.utils.cache import patch_cache_control
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema, extend_schema_serializer
from rest_framework import exceptions, generics, permissions, serializers, status
from rest_framework.response import Response

from content import reports
from content.models import ErrorReport, Question
from learn.models import Clip, QuizItem
from shop.views import over_limit

from .views import check_turnstile

THANKS = "Thank you: we will check it, and fix it if it is wrong."
LIMITS = [("report", 5, 3600), ("report-day", 20, 86400)]  # per client address: an hour's and a day's


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "A wrong step",
            request_only=True,
            value={
                "kind": "solution",
                "paper": "PHY-E01",
                "question": "2(c)",
                "step": 2,
                "printing": "PHY-2027-1",
                "category": "wrong_answer",
                "note": "The current should be 0.5 A, not 5 A.",
                "email": "",
                "turnstile": "0.Zx…",
            },
        )
    ]
)
class MistakeReportSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=reports.TARGETS, help_text="what the mistake is in")
    paper = serializers.CharField(max_length=20, required=False, allow_blank=True, help_text="its code: PHY-E01")
    question = serializers.CharField(max_length=20, required=False, allow_blank=True, help_text="its label: 2(c)")
    quiz_item = serializers.IntegerField(min_value=1, required=False, help_text="a quiz item's id")
    clip = serializers.IntegerField(min_value=1, required=False, help_text="a clip's id")
    step = serializers.IntegerField(min_value=1, max_value=50, required=False, allow_null=True,
                                    help_text="the marking step, 1 for the first")  # fmt: skip
    printing = serializers.RegexField(reports.PRINTING, max_length=40, required=False, allow_blank=True,
                                      help_text="the print run read: PHY-2027-1")  # fmt: skip
    category = serializers.ChoiceField(choices=reports.READER_CATEGORIES)
    note = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True, help_text="to hear of the fix (once); optional")
    website = serializers.CharField(
        required=False, allow_blank=True, write_only=True, help_text="the honeypot: a field people never see; send none"
    )
    turnstile = serializers.CharField(
        required=False, allow_blank=True, write_only=True, help_text="Turnstile's token while the bot check is on"
    )

    def validate(self, attrs):
        check_turnstile(attrs)
        kind = attrs["kind"]
        if kind in ("solution", "question"):
            question = (
                Question.objects.select_related("paper__book__subject", "solution")
                .filter(paper__code__iexact=attrs.get("paper", ""), paper__is_published=True, is_published=True)
                .filter(label=attrs.get("question", ""))
                .first()
            )
            if question is None:
                raise serializers.ValidationError({"question": ["No such question on that paper."]})
            if kind == "solution" and not hasattr(question, "solution"):
                raise serializers.ValidationError({"question": ["That question has no solution yet."]})
            attrs["where"] = dict(
                target=question.solution if kind == "solution" else question,
                subject=question.paper.book.subject,
                paper=question.paper,
                question=question,
            )
        elif kind == "quiz_item":
            item = QuizItem.objects.select_related("chapter__subject").filter(pk=attrs.get("quiz_item")).first()
            if item is None:
                raise serializers.ValidationError({"quiz_item": ["No such quiz item."]})
            attrs["where"] = dict(target=item, subject=item.chapter.subject)
        else:
            clip = Clip.objects.select_related("revision__chapter__subject").filter(pk=attrs.get("clip")).first()
            if clip is None:
                raise serializers.ValidationError({"clip": ["No such clip."]})
            attrs["where"] = dict(target=clip, subject=clip.revision.chapter.subject)
        return attrs


class MistakeReportSentSerializer(serializers.Serializer):
    reference = serializers.IntegerField(allow_null=True, help_text="its number, for a question about it")
    detail = serializers.CharField()


class ReportView(generics.GenericAPIView):
    """Report a mistake: anyone (signed in: the reporter's account is kept; a verified teacher's is marked), 5 an hour
    and 20 a day per client address, Turnstile while it is on; a filled-in `website` (the honeypot) is thanked and
    dropped; a note that reads as spam is kept apart, out of the queue, and goes after 30 days."""

    permission_classes = [permissions.AllowAny]
    serializer_class = MistakeReportSerializer

    @extend_schema(responses={201: MistakeReportSentSerializer})
    def post(self, request, *args, **kwargs):
        for scope, limit, seconds in LIMITS:  # counted before anything is read: probing costs the same
            if over_limit(request, scope, limit, seconds):
                raise exceptions.Throttled(wait=seconds)
        data = self.get_serializer(data=request.data)
        data.is_valid(raise_exception=True)
        sent = data.validated_data
        if sent.get("website"):
            return Response({"reference": None, "detail": THANKS}, status=status.HTTP_201_CREATED)
        user = request.user if request.user.is_authenticated else None
        report = reports.receive(
            **sent["where"],
            step=sent.get("step") if sent["kind"] == "solution" else None,
            printing=sent.get("printing", ""),
            category=sent["category"],
            note=sent.get("note", "").strip(),
            email=sent.get("email", ""),
            reporter=user,
            request=request,
        )
        return Response({"reference": report.pk, "detail": THANKS}, status=status.HTTP_201_CREATED)


class ErratumSerializer(serializers.ModelSerializer):
    paper = serializers.CharField(source="paper.code", read_only=True, allow_null=True)
    question = serializers.CharField(source="question.label", read_only=True, allow_null=True)
    reported_on = serializers.DateTimeField(source="created", read_only=True)

    class Meta:
        model = ErrorReport
        fields = ["paper", "question", "step", "category", "printing", "state", "fixed_in", "fixed_at", "reported_on"]
        read_only_fields = fields


class ErrataView(generics.ListAPIView):
    """A book's errata: the mistakes staff confirmed or fixed and published, in paper and question order, with the
    printing each was read in and the printing that carries its fix. Public, kept 5 minutes by shared caches."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    serializer_class = ErratumSerializer
    filter_backends = []

    @extend_schema(parameters=[OpenApiParameter("book", str, required=True, description="its slug: physics-2027")])
    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        patch_cache_control(response, public=True, max_age=300)
        return response

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ErrorReport.objects.none()
        book = self.request.query_params.get("book", "").strip()
        if not book:
            raise serializers.ValidationError({"book": ["A book's slug: ?book=physics-2027."]})
        return reports.errata(ErrorReport.objects.filter(public=True, paper__book__slug=book))
