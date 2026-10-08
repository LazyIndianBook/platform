import logging
import re

import httpx
from allauth.account import forms as allauth_forms
from allauth.account.adapter import get_adapter
from allauth.account.fields import PhoneField
from allauth.account.forms import SignupForm as AllauthSignupForm
from allauth.core import context as allauth_context
from allauth.core import ratelimit
from allauth.headless.account import inputs as headless_inputs
from allauth.mfa.webauthn.forms import AddWebAuthnForm
from allauth.socialaccount.forms import SignupForm as AllauthSocialSignupForm
from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils.html import format_html

from .models import TeacherProfile

logger = logging.getLogger(__name__)
TURNSTILE = "https://challenges.cloudflare.com/turnstile/v0/"


def turnstile_passed(token):
    """Cloudflare's verdict on the token its widget put in the form. Cloudflare out of reach within 5 seconds: the form
    goes through (logged); the other limits still apply, and students are not locked out."""
    if not token:
        return False
    try:
        data = {"secret": settings.TURNSTILE_SECRET_KEY, "response": token}
        if request := allauth_context.request:  # the client's address, for Cloudflare's own check (I1)
            data["remoteip"] = get_adapter(request).get_client_ip(request)
        answer = httpx.post(TURNSTILE + "siteverify", data=data, timeout=5).json()
    except httpx.HTTPError, ValueError:
        logger.warning("Turnstile could not be reached: the form was let through", exc_info=True)
        return True
    if not answer.get("success"):
        logger.warning("Turnstile refused a form: %s", answer.get("error-codes"))  # a wrong secret shows here
    return bool(answer.get("success"))


class TurnstileWidget(forms.Widget):
    def render(self, name, value, attrs=None, renderer=None):
        return format_html(
            '<div class="cf-turnstile" data-sitekey="{}"></div><script src="{}" async defer></script>',
            settings.TURNSTILE_SITE_KEY,
            TURNSTILE + "api.js",
        )

    def value_from_datadict(self, data, files, name):
        # the hidden field the widget adds; JSON clients (allauth.headless, the API) send "turnstile"
        return data.get("cf-turnstile-response") or data.get(name, "")


class TurnstileField(forms.Field):
    widget = TurnstileWidget

    def __init__(self, **kwargs):
        super().__init__(required=False, label="", **kwargs)

    def validate(self, value):
        if not turnstile_passed(value):
            raise ValidationError("Wait until the check above says it is done, then press the button again.")


class TurnstileMixin:
    """Cloudflare Turnstile on a website form while settings.TURNSTILE is on (both keys set): sign-up and code requests
    here; any other public form takes it as its first base class. The app's API forms do without (DRF throttles)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if settings.TURNSTILE:  # first, so that it is checked before the others (I1); templates place it themselves
            self.fields = {"turnstile": TurnstileField(), **self.fields}


def normalise_phone(value):
    """An Indian mobile number as people type it ("98640 12345", "098640-12345", "+91 98640 12345") in E.164
    (+919864012345); None if the text is not one."""
    match = re.fullmatch(r"(?:\+?91|0)?([6-9]\d{9})", re.sub(r"[\s\-()]", "", value or ""))
    return "+91" + match.group(1) if match else None


def parent_link_contact(value):
    """Where a parent's consent link can go (PARENTAL_CONSENT_MODE "verified"): an email address (lower case), or with
    SMS on an Indian mobile number (E.164); None for anything else."""
    value = (value or "").strip()
    if "@" not in value:
        return normalise_phone(value) if settings.SMS_ENABLED else None
    try:
        validate_email(value)
    except ValidationError:
        return None
    return value.lower()


class IndianPhoneField(PhoneField):
    """allauth's phone field (log-in, code request, phone change), for Indian mobile numbers as people type them."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("label", "Mobile number")
        super().__init__(*args, **kwargs)
        self.widget.attrs["placeholder"] = "Mobile number"

    def clean(self, value):
        if value and not (value := normalise_phone(value)):
            raise ValidationError("Enter a 10-digit Indian mobile number.", code="invalid_phone")
        return super().clean(value)


class ChangePhoneForm(allauth_forms.ChangePhoneForm):
    """My account's mobile number: "wait a minute" when a code went to the number a moment ago (allauth's limit raises
    an exception on this page, a server error)."""

    def clean_phone(self):
        phone = super().clean_phone()
        if not ratelimit.consume(allauth_context.request, action="verify_phone", key=phone, dry_run=True):
            raise ValidationError("A code went to this number a moment ago: wait a minute before asking again.")
        return phone


class AddPasskeyForm(AddWebAuthnForm):
    """allauth's "add a security key" form with Passwordless ticked: a passkey to log in with ("Use a passkey").
    Unticked, the key becomes a second step after the password."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["passwordless"].initial = True


class RequestLoginCodeForm(TurnstileMixin, allauth_forms.RequestLoginCodeForm):
    """ "Log in with a code": the email address or the mobile number (allauth's form took both boxes left empty, and the
    page failed with a server error)."""

    def clean(self):
        data = super().clean()
        if not self.errors and not (data.get("email") or data.get("phone")):
            raise ValidationError("Enter your email address or your mobile number.")
        return data

    # allauth spends the address's or the number's code requests (3 an hour) in these: not for a request that did not
    # pass Turnstile, or anyone could use up a student's codes without solving it (I1).
    def clean_email(self):
        return self.cleaned_data["email"] if "turnstile" in self._errors else super().clean_email()

    def clean_phone(self):
        return self.cleaned_data["phone"] if "turnstile" in self._errors else super().clean_phone()


def axes_username(request, credentials=None):
    """django-axes: allauth authenticates with email=... or phone=... (as typed), the admin login with username=..."""
    creds = credentials or {}
    if phone := creds.get("phone"):
        return normalise_phone(phone) or phone
    value = creds.get("email") or creds.get("username") or request.POST.get("login") or request.POST.get("username")
    return value.lower() if value else None


class SignupForm(AllauthSignupForm):
    """The website's sign-up: allauth's form on accounts.signup.StudentDetailsForm (the student details, the consent,
    Turnstile), as every sign-up is (ACCOUNT_SIGNUP_FORM_CLASS). allauth's own boxes say what they need."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        missing = {"email": "Enter your email address.", "password1": "Choose a password."}
        for name, message in {**missing, "password2": "Type the password again."}.items():
            if name in self.fields:
                self.fields[name].error_messages["required"] = message
        if "email" in self.fields:
            self.fields["email"].error_messages["invalid"] = "Enter an email address, such as name@example.com."


class SocialSignupForm(AllauthSocialSignupForm):
    """After Google: the address comes from Google (confirmed there), the name as a suggestion."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial.setdefault("full_name", self.sociallogin.account.extra_data.get("name", ""))


class TeacherRequestForm(forms.ModelForm):
    class Meta:
        model = TeacherProfile
        fields = ["school_name", "district", "subject"]
        labels = {"school_name": "School or college", "subject": "Subject you teach"}


# allauth.headless takes allauth's own forms, not ACCOUNT_FORMS: examleaf/urls.py routes these two of its endpoints
# (/_allauth/<client>/v1/auth/code/request and account/phone) to inputs on the website's forms.
class RequestLoginCodeInput(RequestLoginCodeForm, headless_inputs.RequestLoginCodeInput):
    """Turnstile while it is on; an email address or a mobile number."""


class ChangePhoneInput(ChangePhoneForm, headless_inputs.ChangePhoneInput):
    """ "Wait a minute" rather than allauth's limit failing with a server error."""


NO_TRIES_LEFT = "Too many tries for this code: ask for a new one."


def spend_try(request, code):
    """One try of this code (in this session), counted in the cache under allauth's lock (ACCOUNT_RATE_LIMITS
    "code_try": 3 per code, 60 an hour per client address). allauth counts tries in the session, which requests sent
    together each read before any of them saves it: with gunicorn's threads that would be many tries, not three (I7).
    False: none left."""
    return ratelimit.consume(request, action="code_try", key=f"{request.session.session_key}:{code}")


class CodeTriesMixin:
    """allauth's code forms (log-in code, email and phone confirmation; ACCOUNT_FORMS) with spend_try first."""

    def clean_code(self):
        if self.expected_code and not spend_try(allauth_context.request, self.expected_code):
            raise ValidationError(NO_TRIES_LEFT, code="too_many_tries")
        return super().clean_code()


class ConfirmLoginCodeForm(CodeTriesMixin, allauth_forms.ConfirmLoginCodeForm):
    pass


class ConfirmEmailVerificationCodeForm(CodeTriesMixin, allauth_forms.ConfirmEmailVerificationCodeForm):
    pass


class VerifyPhoneForm(CodeTriesMixin, allauth_forms.VerifyPhoneForm):
    pass
