"""/api/v1/parent-consent/<token>/: the parent's link (M9; accounts.views.send_parent_link), for the website's page
/c/<token>/. GET says who registered (only to whoever holds the link); POST is "I agree" and records
the consent, verified by the link. An expired or replaced link answers 400 with status "expired" and, for a genuine
link that is only too old, the student's first name, so that the parent knows whom to ask. While the student, under
18, waits for their account's deletion, the same link carries it (`deletion`), and POST {"confirm": "deletion"} is the
parent's confirmation of the erasure (accounts.views.send_parent_deletion_link; staff.privacy.erasure_holds)."""

from datetime import timedelta

from django.core import signing
from django.db import transaction
from django.utils import timezone
from django.utils.cache import add_never_cache_headers
from django.utils.http import base36_to_int
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import exceptions, generics, permissions, serializers
from rest_framework.response import Response

from accounts.models import ConsentRecord, User
from accounts.views import PARENT_LINK_DAYS, parent_signer

PARENT_LINK = inline_serializer(
    "ParentLink",
    {
        "status": serializers.ChoiceField(choices=["pending", "confirmed", "expired"]),
        "student_name": serializers.CharField(allow_null=True, help_text="the full name; null on an expired link"),
        "student_email": serializers.EmailField(allow_null=True),
        "contact": serializers.ChoiceField(choices=["email", "phone"], allow_null=True, help_text="how the link came"),
        "first_name": serializers.CharField(allow_null=True, help_text="an expired genuine link: whom to ask"),
        "days": serializers.IntegerField(help_text="how long a link works"),
        "deletion": inline_serializer(
            "ParentLinkDeletion",
            {
                "requested_at": serializers.DateTimeField(),
                "due_at": serializers.DateTimeField(help_text="erased then, once the parent has confirmed"),
                "confirmed": serializers.BooleanField(help_text="the parent or guardian confirmed it"),
            },
            allow_null=True,
            required=False,
            help_text="the student (under 18) asked to delete their account: null otherwise",
        ),
    },
)
CONFIRM = inline_serializer(
    "ParentLinkConfirm",
    {
        "confirm": serializers.ChoiceField(
            choices=["consent", "deletion"], required=False, help_text='consent ("I agree", the default) or deletion'
        )
    },
)


def waiting_deletion(student):
    """A student under 18's deletion request that waits (their own "Delete my account"), or None."""
    deletion = student.pending_deletion
    return deletion if deletion is not None and student.is_minor else None


class ParentLinkView(generics.GenericAPIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []  # the parent has no account; the signed token is the permission
    throttle_scope = "dj_rest_auth"

    def answer(self, status, student=None, first_name=None, code=200):
        deletion = waiting_deletion(student) if student else None
        body = {
            "status": status,
            "student_name": student.full_name if student else None,
            "student_email": student.email if student else None,
            "contact": ("email" if "@" in student.parent_contact else "phone") if student else None,
            "first_name": first_name,
            "days": PARENT_LINK_DAYS,
            "deletion": {
                "requested_at": deletion.requested_at,
                "due_at": deletion.due_at,
                "confirmed": deletion.parent_confirmed_at is not None,
            }
            if deletion
            else None,
        }
        response = Response(body, status=code)
        add_never_cache_headers(response)  # names a student: never kept by a cache
        return response

    def student(self, token):
        """(student, None) for a valid link, (None, first name or "") for an expired or replaced one."""
        student = None
        try:
            student = User.objects.get(pk=base36_to_int(token.partition(".")[0]), is_active=True)
            parent_signer(student.parent_contact).unsign(token, max_age=timedelta(days=PARENT_LINK_DAYS))
        except (ValueError, signing.BadSignature, User.DoesNotExist) as error:
            expired = isinstance(error, signing.SignatureExpired) and student is not None
            return None, " ".join(student.full_name.split()[:1]) if expired else ""
        return student, None

    @extend_schema(responses={200: PARENT_LINK, 400: PARENT_LINK})
    def get(self, request, token, **kwargs):
        student, first_name = self.student(token)
        if student is None:
            return self.answer("expired", first_name=first_name or None, code=400)
        return self.answer("pending" if student.consent_pending else "confirmed", student)

    @extend_schema(request=CONFIRM, responses={200: PARENT_LINK, 400: PARENT_LINK})
    def post(self, request, token, **kwargs):
        student, first_name = self.student(token)
        if student is None:
            return self.answer("expired", first_name=first_name or None, code=400)
        method = ConsentRecord.Method.EMAIL_LINK if "@" in student.parent_contact else ConsentRecord.Method.SMS_LINK
        if self.confirming_deletion(request):
            self.confirm_deletion(request, student, method)
            return self.answer("pending" if student.consent_pending else "confirmed", student)
        if student.consent_pending:
            ConsentRecord.record(request, student, by_parent=True, method=method, verified_at=timezone.now())
        return self.answer("confirmed", student)

    @staticmethod
    def confirming_deletion(request):
        """Whether the POST's JSON body says {"confirm": "deletion"}; a body of any other kind (or none: "I agree"
        from a form) is the consent, as before."""
        try:
            return isinstance(request.data, dict) and request.data.get("confirm") == "deletion"
        except exceptions.UnsupportedMediaType, exceptions.ParseError:
            return False

    def confirm_deletion(self, request, student, method):
        """The parent's confirmation of their child's erasure (once): on the deletion request, as their withdrawal
        of the consent in the ledger, and in the audit log; the nightly purge erases it once due."""
        from staff import audit

        with transaction.atomic():
            deletion = waiting_deletion(student)
            if deletion is None or deletion.parent_confirmed_at:
                return
            deletion.parent_confirmed_at = timezone.now()
            deletion.save(update_fields=["parent_confirmed_at"])
            ConsentRecord.record(
                request,
                student,
                event=ConsentRecord.Event.WITHDRAWN,
                by_parent=True,
                method=method,
                verified_at=deletion.parent_confirmed_at,
            )
            audit.record(
                "account.deletion_parent_confirmed",
                request=request,
                actor_type=audit.ActorType.ANONYMOUS,
                target=("accounts.user", student.pk, f"Account #{student.pk}"),
                details={"deletion_request": deletion.pk, "through": "the parent's link"},
            )
