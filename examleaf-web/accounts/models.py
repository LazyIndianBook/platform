from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone
from model_utils.models import TimeStampedModel
from phonenumber_field.modelfields import PhoneNumberField


def age_on(dob, today=None):
    today = today or timezone.localdate()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


class UserManager(BaseUserManager):
    use_in_migrations = True

    def get_by_natural_key(self, email):
        return self.get(email__iexact=email)

    def create_user(self, email, password=None, **extra):
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra):
        return self.create_user(email, password, is_staff=True, is_superuser=True, **extra)


class User(AbstractBaseUser, PermissionsMixin, TimeStampedModel):
    CLASS_CHOICES = [(10, "Class 10"), (12, "Class 12")]

    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=120)
    phone = PhoneNumberField(blank=True)
    class_level = models.PositiveSmallIntegerField(choices=CLASS_CHOICES, null=True, blank=True)
    board = models.ForeignKey("content.Board", on_delete=models.PROTECT, null=True, blank=True)
    district = models.CharField(max_length=80, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    parent_name = models.CharField("parent or guardian", max_length=120, blank=True)
    parent_contact = models.CharField(
        "parent's phone or email", max_length=120, blank=True, help_text="Required when the student is under 18."
    )
    consent_at = models.DateTimeField(
        null=True, blank=True, help_text="When the privacy notice was accepted (by the parent if under 18)."
    )
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = UserManager()
    USERNAME_FIELD = EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    def __str__(self):
        return self.email

    @property
    def is_minor(self):
        return self.date_of_birth is not None and age_on(self.date_of_birth) < 18
