"""/api/v1/parent-consent/<token>/: the parent's link (accounts.views.parent_consent, M9) for a frontend of its own.
GET says who registered (only to whoever holds the link, as the website's page does); POST is "I agree" and records
the consent, verified by the link. An expired or replaced link answers 400 with status "expired" and, for a genuine
link that is only too old, the student's first name, so that the parent knows whom to ask."""

from datetime import timedelta

from django.core import signing
from django.utils import timezone
from django.utils.cache import add_never_cache_headers
from django.utils.http import base36_to_int
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import generics, permissions, serializers
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
    },
)


class ParentLinkView(generics.GenericAPIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []  # the parent has no account; the signed token is the permission
    throttle_scope = "dj_rest_auth"

    def answer(self, status, student=None, first_name=None, code=200):
        body = {
            "status": status,
            "student_name": student.full_name if student else None,
            "student_email": student.email if student else None,
            "contact": ("email" if "@" in student.parent_contact else "phone") if student else None,
            "first_name": first_name,
            "days": PARENT_LINK_DAYS,
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

    @extend_schema(request=None, responses={200: PARENT_LINK, 400: PARENT_LINK})
    def post(self, request, token, **kwargs):
        student, first_name = self.student(token)
        if student is None:
            return self.answer("expired", first_name=first_name or None, code=400)
        if student.consent_pending:
            method = ConsentRecord.Method.EMAIL_LINK if "@" in student.parent_contact else ConsentRecord.Method.SMS_LINK
            ConsentRecord.record(request, student, by_parent=True, method=method, verified_at=timezone.now())
        return self.answer("confirmed", student)
