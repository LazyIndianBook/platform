import logging
import re

import httpx
from allauth.account import forms as allauth_forms
from allauth.account.fields import PhoneField
from allauth.account.forms import SignupForm as AllauthSignupForm
from allauth.core import context as allauth_context
from allauth.core import ratelimit
from allauth.mfa.webauthn.forms import AddWebAuthnForm
from allauth.socialaccount.forms import SignupForm as AllauthSocialSignupForm
from django import forms
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from phonenumber_field.phonenumber import to_python as to_phone

from content.models import Board

from . import roles
from .models import ConsentRecord, TeacherProfile, User, age_on

PARENT_FIELDS = ("parent_name", "parent_contact")
logger = logging.getLogger(__name__)
TURNSTILE = "https://challenges.cloudflare.com/turnstile/v0/"


def turnstile_passed(token):
    """Cloudflare's verdict on the token its widget put in the form. Cloudflare out of reach within 5 seconds: the form
    goes through (logged); the other limits still apply, and students are not locked out."""
    if not token:
        return False
    try:
        data = {"secret": settings.TURNSTILE_SECRET_KEY, "response": token}
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
        return data.get("cf-turnstile-response", "")  # the hidden field the widget adds


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
        if settings.TURNSTILE:
            self.fields["turnstile"] = TurnstileField()


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


def axes_username(request, credentials=None):
    """django-axes: allauth authenticates with email=... or phone=... (as typed), the admin login with username=..."""
    creds = credentials or {}
    if phone := creds.get("phone"):
        return normalise_phone(phone) or phone
    value = creds.get("email") or creds.get("username") or request.POST.get("login") or request.POST.get("username")
    return value.lower() if value else None


class StudentDetailsMixin(forms.Form):
    """The student details of both sign-up forms (email and password; after Google). Parent fields are required (and
    kept) only under 18; the consent box is required for everyone (the parent ticks it for a student under 18) and its
    time is recorded."""

    full_name = forms.CharField(
        max_length=120, label="Full name", widget=forms.TextInput(attrs={"autocomplete": "name"})
    )
    class_level = forms.TypedChoiceField(choices=User.CLASS_CHOICES, coerce=int, initial=12, label="Class")
    board = forms.ModelChoiceField(queryset=Board.objects.all(), empty_label=None)
    district = forms.CharField(max_length=80, required=False, label="District (optional)")
    date_of_birth = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    parent_name = forms.CharField(
        max_length=120, required=False, label="Parent's or guardian's name (if you are under 18)"
    )
    parent_contact = forms.CharField(
        max_length=120, required=False, label="Parent's or guardian's phone number or email (if you are under 18)"
    )
    consent = forms.BooleanField(
        required=False,  # enforced in clean(): the message depends on the age
        label="I have read the privacy notice and I agree that ExamLeaf may keep these details so that I can use the "
        "free solutions. If I am under 18, my parent or guardian reads the notice and ticks this box.",
    )
    field_order = [
        "full_name",
        "email",
        "password1",
        "password2",
        "class_level",
        "board",
        "district",
        "date_of_birth",
        "parent_name",
        "parent_contact",
        "consent",
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.pop("phone", None)  # added later on My account: here it would mean two codes in a row
        self.fields["consent"].help_text = format_html(
            '<a href="{}" target="_blank" rel="noopener">Read the privacy notice</a>', reverse("privacy")
        )
        if settings.PARENTAL_CONSENT_MODE == "verified":  # M9: the parent confirms through a link
            contact = "email or mobile number" if settings.SMS_ENABLED else "email"
            label = f"Parent's or guardian's {contact} (if you are under 18): we send them a link to confirm"
            self.fields["parent_contact"].label = label

    def clean_date_of_birth(self):
        dob = self.cleaned_data["date_of_birth"]
        if not 8 <= age_on(dob) <= 100:
            raise ValidationError("Enter your real date of birth.")
        return dob

    def clean_parent_contact(self):
        value = self.cleaned_data["parent_contact"].strip()
        dob = self.cleaned_data.get("date_of_birth")  # date_of_birth comes first in field_order
        if not value or (dob and age_on(dob) >= 18):  # an adult's parent field is ignored, so not validated either
            return ""
        if "@" in value:
            validate_email(value)
            if value.lower() == (self.cleaned_data.get("email") or "").lower():
                raise ValidationError("Enter your parent's or guardian's email, not your own.")
            return value.lower()
        if settings.PARENTAL_CONSENT_MODE == "verified":  # the link goes by SMS: an Indian mobile number
            if phone := parent_link_contact(value):
                return phone
            contact = "email address or mobile number" if settings.SMS_ENABLED else "email address"
            raise ValidationError(f"Enter your parent's or guardian's {contact}: we send them a link to confirm.")
        phone = to_phone(value)  # PHONENUMBER_DEFAULT_REGION = "IN"
        if not (phone and phone.is_valid()):
            raise ValidationError("Enter a valid phone number or email address.")
        return phone.as_e164

    def clean(self):
        data = super().clean()
        dob = data.get("date_of_birth")
        minor = bool(dob) and age_on(dob) < 18
        if minor:
            for name in PARENT_FIELDS:
                if not data.get(name) and name not in self.errors:
                    self.add_error(name, "Required for a student under 18.")
        if not data.get("consent"):
            self.add_error(
                "consent",
                "A parent or guardian must tick this box for a student under 18."
                if minor
                else "Please tick this box to agree to the privacy notice.",
            )
        return data

    def custom_signup(self, request, user):
        data = self.cleaned_data
        for name in ("full_name", "class_level", "board", "district", "date_of_birth"):
            setattr(user, name, data[name])
        if user.is_minor:
            user.parent_name, user.parent_contact = data["parent_name"], data["parent_contact"]
        user.consent_at = timezone.now()
        user.save()
        user.groups.add(Group.objects.get_or_create(name=roles.STUDENT)[0])
        ConsentRecord.record(request, user, by_parent=user.is_minor)
        if user.consent_pending:  # PARENTAL_CONSENT_MODE "verified": the parent confirms through an emailed link
            from .views import send_parent_link  # (views import this module)

            send_parent_link(user)


class SignupForm(TurnstileMixin, StudentDetailsMixin, AllauthSignupForm):
    def try_save(self, request):
        user, response = super().try_save(request)
        if user is None:  # the address has an account already: nothing is made, but the answer must not come quicker
            make_password(self.cleaned_data.get("password1", ""))  # than for a new address, whose password is hashed
        return user, response


class SocialSignupForm(StudentDetailsMixin, AllauthSocialSignupForm):
    """After Google: the address comes from Google (confirmed there), the name as a suggestion."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial.setdefault("full_name", self.sociallogin.account.extra_data.get("name", ""))


class TeacherRequestForm(forms.ModelForm):
    class Meta:
        model = TeacherProfile
        fields = ["school_name", "district", "subject"]
        labels = {"school_name": "School or college", "subject": "Subject you teach"}
