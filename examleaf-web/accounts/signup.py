"""The student details of every sign-up (ACCOUNT_SIGNUP_FORM_CLASS): allauth builds its sign-up forms on this class, the
website's, the one after Google, and allauth.headless's for the app and the browser, so the rules hold whichever way an
account is made. allauth imports this module while it defines its forms: it must not import them (nor accounts.forms)
at the top."""

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
from .models import ConsentRecord, User, age_on

PARENT_FIELDS = ("parent_name", "parent_contact")


def boards():
    """The board choices by id: plain values, which allauth.headless's OpenAPI file can list (a ModelChoiceField's
    cannot be written as JSON)."""
    return [(board.pk, str(board)) for board in Board.objects.all()]


class StudentDetailsForm(forms.Form):
    """Parent fields are required (and kept) only under 18; the consent box is required for everyone (the parent ticks
    it for a student under 18) and its time is recorded. No phone at sign-up: it is added later on My account (here it
    would mean two codes in a row). Turnstile while it is on, except after Google (Google has checked the person)."""

    full_name = forms.CharField(
        max_length=120,
        label="Full name",
        widget=forms.TextInput(attrs={"autocomplete": "name"}),
        error_messages={"required": "Enter your full name."},
    )
    class_level = forms.TypedChoiceField(
        choices=User.CLASS_CHOICES,
        coerce=int,
        initial=12,
        label="Class",
        error_messages={"required": "Choose your class."},
    )
    board = forms.TypedChoiceField(
        choices=boards, coerce=int, label="Board", error_messages={"required": "Choose your board."}
    )
    district = forms.CharField(max_length=80, required=False, label="District (optional)")
    date_of_birth = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        error_messages={"required": "Enter your date of birth.", "invalid": "Enter your date of birth."},
    )
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
        if hasattr(self, "_signup_fields"):  # allauth's sign-up forms add the phone field after this __init__
            self._signup_fields = {name: spec for name, spec in self._signup_fields.items() if name != "phone"}
        super().__init__(*args, **kwargs)
        self.fields["consent"].help_text = format_html(
            '<a href="{}" target="_blank" rel="noopener">Read the privacy notice</a>', reverse("privacy")
        )
        if settings.PARENTAL_CONSENT_MODE == "verified":  # M9: the parent confirms through a link
            contact = "email or mobile number" if settings.SMS_ENABLED else "email"
            label = f"Parent's or guardian's {contact} (if you are under 18): we send them a link to confirm"
            self.fields["parent_contact"].label = label
        if settings.TURNSTILE and not hasattr(self, "sociallogin"):
            from .forms import TurnstileField

            self.fields["turnstile"] = TurnstileField()

    def clean_date_of_birth(self):
        dob = self.cleaned_data["date_of_birth"]
        if not 8 <= age_on(dob) <= 100:
            raise ValidationError("Enter your real date of birth.")
        return dob

    def clean_parent_contact(self):
        from .forms import parent_link_contact

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
        if getattr(self, "account_already_exists", False):  # nothing is made for an address with an account, but the
            make_password(data.get("password1") or data.get("password") or "")  # answer must not come quicker either
        return data

    def signup(self, request, user):
        """allauth calls it once the user is saved: the details, the consent record and the STUDENT role."""
        data = self.cleaned_data
        for name in ("full_name", "class_level", "district", "date_of_birth"):
            setattr(user, name, data[name])
        user.board_id = data["board"]
        if user.is_minor:
            user.parent_name, user.parent_contact = data["parent_name"], data["parent_contact"]
        user.consent_at = timezone.now()
        user.save()
        user.groups.add(Group.objects.get_or_create(name=roles.STUDENT)[0])
        ConsentRecord.record(request, user, by_parent=user.is_minor)
        # PARENTAL_CONSENT_MODE "verified": the parent's link goes once the student's own address is confirmed, not
        # now (M3: an anonymous sign-up must not make ExamLeaf write to any address or number); accounts.models.
