from allauth.account.forms import SignupForm as AllauthSignupForm
from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils import timezone
from django.utils.safestring import mark_safe
from phonenumber_field.phonenumber import to_python as to_phone

from content.models import Board

from .models import User, age_on

PARENT_FIELDS = ("parent_name", "parent_contact")


def axes_username(request, credentials=None):
    """django-axes: allauth authenticates with email=..., the admin login with username=..."""
    creds = credentials or {}
    value = creds.get("email") or creds.get("username") or request.POST.get("login") or request.POST.get("username")
    return value.lower() if value else None


class SignupForm(AllauthSignupForm):
    """allauth's signup form plus the student details. Parent fields are required (and kept) only under 18."""

    full_name = forms.CharField(max_length=120, label="Full name")
    class_level = forms.TypedChoiceField(choices=User.CLASS_CHOICES, coerce=int, initial=12, label="Class")
    board = forms.ModelChoiceField(queryset=Board.objects.all(), empty_label=None)
    district = forms.CharField(max_length=80, required=False, label="District (optional)")
    date_of_birth = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    parent_name = forms.CharField(max_length=120, required=False, label="Parent's or guardian's name (if you are under 18)")
    parent_contact = forms.CharField(
        max_length=120, required=False, label="Parent's or guardian's phone number or email (if you are under 18)"
    )
    parent_consent = forms.BooleanField(
        required=False,
        label="For a student under 18 — to be ticked by the parent or guardian: I have read the privacy notice "
        "and I agree that ExamLeaf may keep these details so that my child can use the free solutions.",
        help_text=mark_safe('<a href="/privacy/" target="_blank">Read the privacy notice</a>'),
    )
    field_order = ["full_name", "email", "password1", "password2", "class_level", "board", "district",
                   "date_of_birth", "parent_name", "parent_contact", "parent_consent"]

    def clean_date_of_birth(self):
        dob = self.cleaned_data["date_of_birth"]
        if not 8 <= age_on(dob) <= 100:
            raise ValidationError("Enter your real date of birth.")
        return dob

    def clean_parent_contact(self):
        value = self.cleaned_data["parent_contact"].strip()
        if not value:
            return value
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
        if dob and age_on(dob) < 18:
            for name in PARENT_FIELDS:
                if not data.get(name) and name not in self.errors:
                    self.add_error(name, "Required for a student under 18.")
            if not data.get("parent_consent"):
                self.add_error("parent_consent", "A parent or guardian must give consent for a student under 18.")
        return data

    def custom_signup(self, request, user):
        data = self.cleaned_data
        for name in ("full_name", "class_level", "board", "district", "date_of_birth"):
            setattr(user, name, data[name])
        if user.is_minor:
            user.parent_name, user.parent_contact = data["parent_name"], data["parent_contact"]
        user.consent_at = timezone.now()
        user.save()
