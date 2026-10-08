from allauth.account.forms import SignupForm as AllauthSignupForm
from django import forms
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


def axes_username(request, credentials=None):
    """django-axes: allauth authenticates with email=..., the admin login with username=..."""
    creds = credentials or {}
    value = creds.get("email") or creds.get("username") or request.POST.get("login") or request.POST.get("username")
    return value.lower() if value else None


class SignupForm(AllauthSignupForm):
    """allauth's signup form plus the student details. Parent fields are required (and kept) only under 18; the consent
    box is required for everyone (the parent ticks it for a student under 18) and its time is recorded."""

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
        self.fields["consent"].help_text = format_html(
            '<a href="{}" target="_blank" rel="noopener">Read the privacy notice</a>', reverse("privacy")
        )

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
            return value.lower()
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

    def try_save(self, request):
        user, response = super().try_save(request)
        if user is None:  # the address has an account already: nothing is made, but the answer must not come quicker
            make_password(self.cleaned_data["password1"])  # than for a new address, whose password is hashed
        return user, response

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


class TeacherRequestForm(forms.ModelForm):
    class Meta:
        model = TeacherProfile
        fields = ["school_name", "district", "subject"]
        labels = {"school_name": "School or college", "subject": "Subject you teach"}
