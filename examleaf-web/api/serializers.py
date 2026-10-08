"""The public catalogue, the solutions, attempts and the profile. Validation mirrors the models and the site's forms."""

from django.templatetags.static import static
from drf_spectacular.utils import OpenApiExample, extend_schema_field, extend_schema_serializer
from phonenumber_field.serializerfields import PhoneNumberField
from rest_framework import serializers
from rest_framework.reverse import reverse

from accounts.models import User
from content.models import Board, Book, Paper, Question, Solution, Subject
from content.templatetags.markdown import render
from practice.models import NOTES_MAX_LENGTH, Attempt, check_can_save


class BoardSerializer(serializers.ModelSerializer):
    class Meta:
        model = Board
        fields = ["id", "name", "short_name", "state"]


class SubjectSerializer(serializers.ModelSerializer):
    board = serializers.SlugRelatedField(slug_field="short_name", read_only=True)
    class_level = serializers.IntegerField(source="class_level.number", read_only=True)

    class Meta:
        model = Subject
        fields = ["id", "name", "code", "board", "class_level"]


class PaperBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Paper
        # full_marks and time_text: a book's marks and time without a call per book (the website's home page)
        fields = ["code", "tier", "number", "title", "full_marks", "time_text", "is_published", "is_sample"]


class BookSerializer(serializers.ModelSerializer):
    subject = SubjectSerializer(read_only=True)
    cover = serializers.SerializerMethodField()
    papers = PaperBriefSerializer(many=True, read_only=True)

    class Meta:
        model = Book
        fields = ["id", "slug", "title", "edition", "cover", "subject", "papers"]

    @extend_schema_field(serializers.URLField(allow_null=True))
    def get_cover(self, book):
        return self.context["request"].build_absolute_uri(static(book.cover)) if book.cover else None


def solutions_url(request, paper):
    return reverse("api:paper-solutions", kwargs={"code": paper.code}, request=request)


class PaperSerializer(serializers.ModelSerializer):
    book = serializers.SlugRelatedField(slug_field="slug", read_only=True)
    subject = serializers.CharField(source="book.subject.code", read_only=True)
    header = serializers.JSONField(source="header_json", read_only=True, help_text="instruction lines and allotment")
    web_url = serializers.URLField(source="landing_url", read_only=True, help_text="the page the QR code opens")
    solutions_url = serializers.SerializerMethodField()

    class Meta:
        model = Paper
        fields = [
            "code",
            "tier",
            "number",
            "title",
            "book",
            "subject",
            "full_marks",
            "pass_marks",
            "time_text",
            "header",
            "is_published",
            "is_sample",
            "web_url",
            "solutions_url",
        ]

    @extend_schema_field(serializers.URLField())
    def get_solutions_url(self, paper):
        return solutions_url(self.context["request"], paper)


class SolutionSerializer(serializers.ModelSerializer):
    markdown = serializers.CharField(source="body_md")
    html = serializers.SerializerMethodField(help_text="rendered by the site; $…$ maths left for KaTeX")

    class Meta:
        model = Solution
        fields = ["markdown", "html"]

    def get_html(self, solution) -> str:
        return render(solution.body_md)


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "A question and its solution",
            response_only=True,
            value={
                "order": 12,
                "label": "2(c)",
                "number": "2(c)",
                "part_label": "",
                "group_label": "",
                "is_alternative": False,
                "text": "A cell of emf 6 V and internal resistance 1 Ω drives 11 Ω. Find the current.",
                "table": "",
                "options": [],
                "marks": "2",
                "solution": {
                    "markdown": "| Step | Marks |\n|---|---|\n| $I = \\dfrac{\\varepsilon}{R+r}$ | 1 |\n"
                    "| $I = 0.5$ A | 1 |\n\n**Final answer:** 0.5 A",
                    "html": '<div class="table-scroll"><table class="steps">…</table></div>\n'
                    '<p class="final"><strong>Final answer:</strong> 0.5 A</p>\n',
                },
            },
        )
    ]
)
class QuestionSerializer(serializers.ModelSerializer):
    """One question in paper order. Markdown with $…$ maths; is_alternative marks the OR of the previous one."""

    number = serializers.CharField(
        read_only=True, help_text="as printed (B9(a) is 9(a)); the site prints none for an OR alternative"
    )
    text = serializers.CharField(source="text_md")
    table = serializers.CharField(source="table_md")
    options = serializers.ListField(source="options_json", child=serializers.CharField())
    marks = serializers.CharField(source="marks_text")
    solution = SolutionSerializer(allow_null=True)

    class Meta:
        model = Question
        fields = [
            "order",
            "label",
            "number",
            "part_label",
            "group_label",
            "is_alternative",
            "text",
            "table",
            "options",
            "marks",
            "solution",
        ]


class AttemptSerializer(serializers.ModelSerializer):
    """A student's marks for a published paper, from 0 to its full marks (as the website's form); the paper is fixed."""

    paper = serializers.SlugRelatedField(slug_field="code", queryset=Paper.objects.filter(is_published=True))
    subject = serializers.CharField(source="paper.book.subject.code", read_only=True)
    tier = serializers.CharField(source="paper.tier", read_only=True)
    full_marks = serializers.IntegerField(source="paper.full_marks", read_only=True)
    percent = serializers.IntegerField(read_only=True)

    class Meta:
        model = Attempt
        fields = [
            "id",
            "paper",
            "subject",
            "tier",
            "date",
            "marks_obtained",
            "full_marks",
            "percent",
            "time_taken_minutes",
            "notes",
            "created",
            "modified",
        ]
        extra_kwargs = {"notes": {"max_length": NOTES_MAX_LENGTH}}

    def validate(self, attrs):
        paper = attrs.get("paper") or self.instance.paper
        if self.instance and paper != self.instance.paper:
            raise serializers.ValidationError({"paper": "An attempt stays with its paper."})
        marks = attrs.get("marks_obtained", getattr(self.instance, "marks_obtained", None))
        if not 0 <= marks <= paper.full_marks:
            raise serializers.ValidationError({"marks_obtained": f"Enter marks from 0 to {paper.full_marks}."})
        check_can_save(self.context["request"].user, paper, new=self.instance is None)  # 400 with the reason
        return attrs


class ProfileSerializer(serializers.ModelSerializer):
    """The signed-in user. The email address, date of birth and parent details change only on the website (the email
    after a confirmation code; the others decide the consent rules)."""

    phone = PhoneNumberField(required=False, allow_blank=True)
    board = serializers.PrimaryKeyRelatedField(queryset=Board.objects.all(), allow_null=True, required=False)
    roles = serializers.SerializerMethodField()
    deletion_due_at = serializers.DateTimeField(
        source="pending_deletion.due_at", read_only=True, allow_null=True, help_text="set while a deletion waits"
    )
    consent_pending = serializers.BooleanField(
        read_only=True, help_text="a parent has not confirmed yet (me/parent-consent/ sends the link again)"
    )

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "full_name",
            "phone",
            "class_level",
            "board",
            "district",
            "date_of_birth",
            "parent_name",
            "parent_contact",
            "consent_at",
            "consent_pending",
            "roles",
            "deletion_due_at",
            "login_phone",
            "login_phone_verified",
            "sms_updates",
        ]
        read_only_fields = [
            *["email", "date_of_birth", "parent_name", "parent_contact", "consent_at"],
            *["login_phone", "login_phone_verified"],  # changed through allauth.headless (account/phone), with a code
        ]
        extra_kwargs = {"sms_updates": {"help_text": "order updates by SMS; only with a confirmed mobile number"}}

    def get_roles(self, user) -> list[str]:
        return sorted(user.role_names)

    def validate_sms_updates(self, value):
        if value and not self.instance.login_phone_verified:
            raise serializers.ValidationError("Confirm a mobile number first: the updates go to it.")
        return value
