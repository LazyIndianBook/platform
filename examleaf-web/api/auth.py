"""Accounts through the API. Log-in, log-out, token refresh, passwords and user details are dj-rest-auth's views (with
the serializers below); sign-up and the email code run on the website's SignupForm and allauth's own flows, so the
rules, the consent record and the emails are the website's.

allauth confirms an email address with a code it keeps in the session. The app has no session, so sign-up (and a log-in
whose address is not confirmed yet) gives it that session's key as `verification_token`, and verify-email takes it back
with the code and answers with the tokens. dj-rest-auth's own sign-up and verify views are link-based (and need
allauth.socialaccount), so they are not used.
"""

from importlib import import_module

from allauth.account.adapter import get_adapter
from allauth.account.forms import ConfirmEmailVerificationCodeForm
from allauth.account.internal.flows.email_verification import send_verification_email_for_user
from allauth.account.internal.flows.email_verification_by_code import EmailVerificationProcess
from allauth.account.internal.flows.signup import complete_signup
from allauth.account.utils import has_verified_email, user_pk_to_url_str
from allauth.core import ratelimit
from dj_rest_auth import serializers as rest_auth
from dj_rest_auth.utils import jwt_encode
from django.conf import settings
from django.contrib.auth.signals import user_logged_in
from django.core.cache import cache
from django.urls import reverse
from drf_spectacular.utils import OpenApiExample, extend_schema, extend_schema_serializer
from rest_framework import exceptions, serializers, status
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from accounts.forms import SignupForm
from accounts.models import User
from content.models import Board

from .serializers import ProfileSerializer

SessionStore = import_module(settings.SESSION_ENGINE).SessionStore
TOKENS = {"access": "eyJhbGciOiJIUzI1NiIs…", "refresh": "eyJhbGciOiJIUzI1NiIs…"}


def email_code(request, send):
    """Run `send` (an allauth flow that emails a code and keeps it in the session) in a new session, never in a site
    session a browser may have sent; save it and hand over its key. No cookie is set: the app holds the key."""
    request.session = SessionStore()
    send()
    request.session.save()
    request.session.modified = False
    return {"detail": "Verification e-mail sent.", "verification_token": request.session.session_key}


def logged_in(request, user):
    """Django's log-in signal: last_login, axes forgets the failures. Its receivers (the shop's cart) get a session that
    is never saved: the app has none, and a site session a browser may send stays as it was."""
    request.session = SessionStore()
    user_logged_in.send(sender=user.__class__, request=request, user=user)
    request.session.modified = False


class VerificationSentSerializer(serializers.Serializer):
    detail = serializers.CharField()
    verification_token = serializers.CharField(help_text="send it back to verify-email with the emailed code")


class EmailNotVerified(exceptions.APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "E-mail is not verified."
    default_code = "email_not_verified"


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "A student under 18",
            request_only=True,
            value={
                "full_name": "Rahul Das",
                "email": "rahul@example.com",
                "password1": "Brahmaputra-2027",
                "password2": "Brahmaputra-2027",
                "class_level": 12,
                "board": 1,
                "district": "Kamrup",
                "date_of_birth": "2010-05-14",
                "parent_name": "Anita Das",
                "parent_contact": "98640 12345",
                "consent": True,
            },
        )
    ]
)
class RegisterSerializer(serializers.Serializer):  # validated by the website's form, accounts.forms.SignupForm
    """The website's sign-up form, field for field, with its rules: under 18, a parent's name and phone or email, and
    the parent ticks the consent; everyone agrees to the privacy notice; the email and password rules of the site."""

    full_name = serializers.CharField(max_length=120)
    email = serializers.EmailField()
    password1 = serializers.CharField(write_only=True, style={"input_type": "password"})
    password2 = serializers.CharField(write_only=True, style={"input_type": "password"})
    class_level = serializers.ChoiceField(choices=User.CLASS_CHOICES)
    board = serializers.PrimaryKeyRelatedField(queryset=Board.objects.all(), help_text="board id (boards/)")
    district = serializers.CharField(max_length=80, required=False, allow_blank=True)
    date_of_birth = serializers.DateField()
    parent_name = serializers.CharField(max_length=120, required=False, allow_blank=True, help_text="under 18")
    parent_contact = serializers.CharField(
        max_length=120, required=False, allow_blank=True, help_text="parent's phone or email; under 18"
    )
    consent = serializers.BooleanField(help_text="agrees to the privacy notice (the parent, under 18)")

    def validate(self, attrs):
        self.form = SignupForm(data=self.initial_data)
        if not self.form.is_valid():
            raise serializers.ValidationError(
                {api_settings.NON_FIELD_ERRORS_KEY if k == "__all__" else k: v for k, v in self.form.errors.items()}
            )
        return attrs

    def save(self, request):
        # An address that already has an account gets allauth's "you already have an account" email, and the same
        # answer as a new one (no way to find out who is registered).
        user, _ = self.form.try_save(request)
        if user:
            complete_signup(request, user=user)  # the STUDENT role and consent record came with the form's save
        return user


class RegisterView(GenericAPIView):
    """Sign up. Emails a code; send it with the verification_token to verify-email, which logs the student in."""

    permission_classes = [AllowAny]
    serializer_class = RegisterSerializer
    throttle_scope = "dj_rest_auth"

    @extend_schema(responses={201: VerificationSentSerializer})
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = email_code(request._request, lambda: serializer.save(request._request))
        return Response(data, status=status.HTTP_201_CREATED)


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "The emailed code",
            request_only=True,
            value={"verification_token": "q3k9w0d8m2…", "code": "ABCD-EFGH"},
        )
    ]
)
class VerifyEmailSerializer(serializers.Serializer):
    verification_token = serializers.CharField()
    code = serializers.CharField()


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "Signed in",
            response_only=True,
            value={
                **TOKENS,
                "user": {
                    "id": 7,
                    "email": "rahul@example.com",
                    "full_name": "Rahul Das",
                    "phone": "",
                    "class_level": 12,
                    "board": 1,
                    "district": "Kamrup",
                    "date_of_birth": "2010-05-14",
                    "parent_name": "Anita Das",
                    "parent_contact": "+919864012345",
                    "consent_at": "2026-10-08T10:15:00+05:30",
                    "roles": ["STUDENT"],
                    "deletion_due_at": None,
                },
            },
        )
    ]
)
class JWTSerializer(rest_auth.JWTSerializer):
    user = ProfileSerializer(read_only=True)


class VerifyEmailView(GenericAPIView):
    """Confirm the email address with the emailed code; answers with the tokens, as a log-in. Three wrong codes or
    15 minutes end the token: log in again for a new code."""

    permission_classes = [AllowAny]
    serializer_class = VerifyEmailSerializer
    throttle_scope = "dj_rest_auth"

    @extend_schema(responses={200: JWTSerializer})
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        django_request = request._request
        django_request.session = session = SessionStore(serializer.validated_data["verification_token"])
        process = EmailVerificationProcess.resume(django_request)
        if not process:
            raise serializers.ValidationError({"verification_token": ["Expired. Log in again for a new code."]})
        form = ConfirmEmailVerificationCodeForm(
            data=serializer.validated_data, code=process.code, user=process.user, email=process.email
        )
        if not (form.is_valid() and process.user):  # no user: the stand-in for an address with an account already
            process.record_invalid_attempt()
            session.save()
            session.modified = False  # no cookie
            raise serializers.ValidationError(form.errors or {"code": [get_adapter().error_messages["incorrect_code"]]})
        user = process.user
        process.finish()
        session.delete()  # the token is spent
        logged_in(django_request, user)
        access, refresh = jwt_encode(user)
        data = {"user": user, "access": access, "refresh": refresh}
        return Response(JWTSerializer(data, context=self.get_serializer_context()).data)


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "Log in", request_only=True, value={"email": "rahul@example.com", "password": "Brahmaputra-2027"}
        ),
    ]
)
class LoginSerializer(rest_auth.LoginSerializer):
    """Email and password. An address not confirmed yet gets a new code: the 400 answer then carries a
    verification_token for verify-email."""

    username = None

    def authenticate(self, **credentials):
        """Through allauth, as the website's log-in: its limit of failed log-ins per account (5 in 5 minutes, from any
        address) applies to the app too (M7). Over it, the answer is the website's "Too many failed login attempts"."""
        return get_adapter().authenticate(self.context["request"]._request, **credentials)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request, user = self.context["request"]._request, attrs["user"]
        if not has_verified_email(user, user.email):  # dj-rest-auth checks this only with its registration app
            data = email_code(request, lambda: send_verification_email_for_user(request, user))
            raise EmailNotVerified(data | {"detail": EmailNotVerified.default_detail})
        logged_in(request, user)
        return attrs


def reset_url(request, user, temp_key):
    """The emailed link opens the website's own "new password" page; an app can read uid and token from it."""
    path = reverse("account_reset_password_from_key", kwargs={"uidb36": user_pk_to_url_str(user), "key": temp_key})
    return settings.SITE_URL + path


class PasswordResetSerializer(rest_auth.PasswordResetSerializer):
    def validate_email(self, value):
        """allauth's limit of reset emails per address (5 a minute, website and app together; L5): 429 above it."""
        if not ratelimit.consume(self.context["request"]._request, action="reset_password", key=value.lower()):
            raise exceptions.Throttled()
        return super().validate_email(value)

    def get_email_options(self):
        return {"url_generator": reset_url}


class PasswordResetConfirmSerializer(rest_auth.PasswordResetConfirmSerializer):
    def save(self):
        super().save()
        get_adapter().send_notification_mail("account/email/password_reset", self.user)  # as the website does


WRONG_PASSWORDS = 5  # in an hour, per user, in the API's password checks (L6)


def check_password(request, password):
    """The password checks of the app's signed-in requests (password change, data export, deletion). A stolen token
    must not become a way to guess the password: after WRONG_PASSWORDS wrong ones in an hour every refresh token of
    the user is blacklisted (the app has to log in again) and the checks answer 429 until the hour is over (L6)."""
    user, key = request.user, f"api:wrong-passwords:{request.user.pk}"
    if (cache.get(key) or 0) >= WRONG_PASSWORDS:
        raise exceptions.Throttled(detail="Too many wrong passwords. Try again in an hour.")
    if user.check_password(password):
        return
    cache.add(key, 0, 3600)
    try:
        wrong = cache.incr(key) or 0  # None: the cache (Redis) is down, nothing counted
    except ValueError:  # expired in between
        wrong = 0
    if wrong >= WRONG_PASSWORDS:
        tokens = OutstandingToken.objects.filter(user=user, blacklistedtoken__isnull=True)
        BlacklistedToken.objects.bulk_create([BlacklistedToken(token=t) for t in tokens], ignore_conflicts=True)
        raise exceptions.Throttled(detail="Too many wrong passwords. Try again in an hour.")
    raise serializers.ValidationError("Incorrect password.")


class PasswordChangeSerializer(rest_auth.PasswordChangeSerializer):
    def validate_old_password(self, value):
        check_password(self.context["request"], value)
        return value

    def save(self):
        super().save()
        get_adapter().send_notification_mail("account/email/password_changed", self.user)
