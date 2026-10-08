from datetime import timedelta

from allauth.account.models import EmailAddress
from allauth.account.signals import email_confirmed, user_logged_in, user_signed_up
from axes.helpers import get_client_ip_address
from axes.models import AccessAttempt
from django.conf import settings
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.contrib.contenttypes.models import ContentType
from django.db import models, transaction
from django.dispatch import receiver
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.utils.functional import cached_property
from model_utils.models import TimeStampedModel
from phonenumber_field.modelfields import PhoneNumberField

from pages.models import Page

from . import roles

STAFF_SESSION = timedelta(hours=8)  # a member of staff's session lasts this long from the log-in (H2, L11)


@receiver(user_logged_in)  # allauth's log-in (the website and the admin; not the API, which has no session)
def shorter_staff_sessions(sender, request, user, **kwargs):
    if user.is_staff:
        request.session.set_expiry(STAFF_SESSION)


# PARENTAL_CONSENT_MODE "verified": the parent's link (accounts.views.send_parent_link) goes once the student has
# confirmed their own address, never from an anonymous sign-up (M3), whichever way the account was made (website, app,
# Google). After that only from My account, with its limits (accounts.views.resend_parent_link).
@receiver(email_confirmed)
def parent_link_once_confirmed(sender, request, email_address, **kwargs):
    if email_address.user_id and email_address.user.consent_pending:
        from .views import send_parent_link  # (views import this module)

        send_parent_link(email_address.user)


@receiver(user_signed_up)
def parent_link_after_google(sender, request, user, **kwargs):
    """After Google the address is confirmed at the sign-up: no email_confirmed follows."""
    from allauth.account.utils import has_verified_email

    if user.consent_pending and has_verified_email(user):
        from .views import send_parent_link

        send_parent_link(user)


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
    # Log-in by SMS code (allauth, accounts.adapter): the mobile number is stored only once its code was confirmed on
    # My account, as +91XXXXXXXXXX; one account per number. `phone` above stays a contact detail only.
    login_phone = models.CharField("mobile number for log-in", max_length=16, blank=True)
    login_phone_verified = models.BooleanField("mobile number confirmed", default=False)
    sms_updates = models.BooleanField("order updates by SMS", default=False)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = UserManager()
    USERNAME_FIELD = EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        permissions = [("export_user", "Can export users")]  # the admin's CSV export (ADMIN role)
        constraints = [
            models.UniqueConstraint(
                fields=["login_phone"], condition=models.Q(login_phone_verified=True), name="uniq_verified_login_phone"
            )
        ]

    def __str__(self):
        return self.email

    @property
    def is_minor(self):
        return self.date_of_birth is not None and age_on(self.date_of_birth) < 18

    # Roles are groups (accounts/roles.py). The names are read once per user object.
    @cached_property
    def role_names(self):
        return set(self.groups.values_list("name", flat=True))

    def has_role(self, role):
        return role in self.role_names

    is_student = property(lambda self: self.has_role(roles.STUDENT))
    is_teacher = property(lambda self: self.has_role(roles.TEACHER))  # a verified teacher (see TeacherProfile)
    is_editor = property(lambda self: self.has_role(roles.CONTENT_EDITOR))
    is_sales = property(lambda self: self.has_role(roles.SALES))
    is_support = property(lambda self: self.has_role(roles.SUPPORT))
    is_admin = property(lambda self: self.is_superuser or self.has_role(roles.ADMIN))

    @cached_property
    def consent_pending(self):
        """PARENTAL_CONSENT_MODE "verified": a student under 18 whose parent has not confirmed through the emailed link
        yet. Such an account can log in and read, not save marks or order (M9)."""
        return (
            settings.PARENTAL_CONSENT_MODE == "verified"
            and self.is_minor
            and not self.consents.filter(event=ConsentRecord.Event.GIVEN, verified_at__isnull=False).exists()
        )

    @property
    def pending_deletion(self):
        return self.deletion_requests.filter(status=DeletionRequest.Status.PENDING).first()


class TeacherProfile(TimeStampedModel):
    """A request for teacher access. Staff check it (e.g. by calling the school) and verify it in the admin, which
    puts the user in the TEACHER group."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="teacher_profile")
    school_name = models.CharField(max_length=200)
    district = models.CharField(max_length=80)
    subject = models.CharField("subject taught", max_length=80)
    verified = models.BooleanField(default=False)
    verification_note = models.TextField(
        blank=True, help_text="How it was checked, for staff (not shown to the teacher)."
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    def __str__(self):
        return f"Teacher access #{self.pk}"  # no personal data: this text is kept in the admin's change log


class ConsentRecord(models.Model):
    """One consent event (DPDP Act): what was agreed to or withdrawn, under which version of the privacy policy, when,
    and a keyed hash of the internet address (enough to compare with an address later, not to read it back)."""

    class Event(models.TextChoices):
        GIVEN = "given", "given"
        WITHDRAWN = "withdrawn", "withdrawn"

    class Method(models.TextChoices):
        DECLARED = "declared", "ticked on the form"
        EMAIL_LINK = "email_link", "confirmed through the link emailed to the parent"
        SMS_LINK = "sms_link", "confirmed through the link texted to the parent"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="consents")
    event = models.CharField(max_length=10, choices=Event.choices, default=Event.GIVEN)
    purpose = models.CharField(max_length=120, default="account and free solutions (privacy policy)")
    notice_version = models.CharField("privacy policy version", max_length=20)
    by_parent = models.BooleanField("by a parent or guardian", default=False)
    method = models.CharField("how", max_length=10, choices=Method.choices, default=Method.DECLARED)
    verified_at = models.DateTimeField("verified at", null=True, blank=True, help_text="When the parent confirmed.")
    ip_hash = models.CharField("address hash", max_length=64, blank=True)
    created = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created"]
        permissions = [("export_consentrecord", "Can export consent records")]

    def __str__(self):
        return f"Consent {self.event} #{self.pk}"

    @classmethod
    def record(cls, request, user, event=Event.GIVEN, by_parent=False, method=Method.DECLARED, verified_at=None):
        ip = get_client_ip_address(request) or ""  # the client address as axes sees it (PROXY_COUNT aware)
        return cls.objects.create(
            user=user,
            event=event,
            by_parent=by_parent,
            method=method,
            verified_at=verified_at,
            notice_version=Page.objects.filter(slug="privacy").values_list("version", flat=True).first() or "",
            ip_hash=salted_hmac("accounts.ConsentRecord.ip", ip, algorithm="sha256").hexdigest() if ip else "",
        )


class DeletionRequest(models.Model):
    """A student's "Delete my account": after GRACE the purge task (accounts.tasks) erases the personal data, unless
    the student logged in and cancelled it."""

    GRACE = timedelta(days=7)

    class Status(models.TextChoices):
        PENDING = "pending", "waiting"
        CANCELLED = "cancelled", "cancelled"
        DONE = "done", "deleted"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="deletion_requests")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    requested_at = models.DateTimeField(default=timezone.now)
    due_at = models.DateTimeField()
    closed_at = models.DateTimeField("cancelled or done at", null=True, blank=True)

    class Meta:
        ordering = ["-requested_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user"], condition=models.Q(status="pending"), name="one_pending_deletion_per_user"
            )
        ]

    def __str__(self):
        return f"Deletion request #{self.pk}"

    def save(self, *args, **kwargs):
        if not self.due_at:
            self.due_at = self.requested_at + self.GRACE
        super().save(*args, **kwargs)

    def complete(self):
        """Erase the personal data. The user row stays, anonymised and unable to log in, so that the saved marks remain
        as statistics on the papers (without notes); consent records stay as proof, without the address hash.
        Returns the old email address, for the goodbye email."""
        user, email = self.user, self.user.email
        with transaction.atomic():
            from practice.models import AnswerSheetUpload, Attempt  # (practice does not import accounts)
            from shop.models import StockAlert  # (shop imports this module)

            StockAlert.objects.filter(email__iexact=email).delete()  # "email me when it is back": kept by address only
            sheets = list(user.answer_sheets.all())
            for model, pks in [  # admin history rows name these objects (the user's email is in their text)
                (User, [user.pk]),
                (TeacherProfile, TeacherProfile.objects.filter(user=user).values_list("pk", flat=True)),
                (Attempt, user.attempts.values_list("pk", flat=True)),
                (AnswerSheetUpload, [sheet.pk for sheet in sheets]),
            ]:
                LogEntry.objects.filter(
                    content_type=ContentType.objects.get_for_model(model), object_id__in=[str(pk) for pk in pks]
                ).update(object_repr=f"deleted account #{user.pk}")
            TeacherProfile.objects.filter(user=user).delete()
            EmailAddress.objects.filter(user=user).delete()
            user.authenticator_set.all().delete()  # passkeys, authenticator apps
            user.socialaccount_set.all().delete()  # Google sign-in and the profile Google sent
            # failed log-ins by address or by mobile number (axes), and the SMS log (number hash, last digits; L10)
            AccessAttempt.objects.filter(username__in=[email, user.login_phone or email]).delete()
            user.sms_messages.all().delete()
            user.attempts.update(notes="")
            user.answer_sheets.all().delete()
            user.consents.update(ip_hash="")
            user.groups.clear()
            user.user_permissions.clear()
            user.email, user.full_name = f"deleted-{user.pk}@deleted.invalid", "Deleted account"
            user.phone = user.district = user.parent_name = user.parent_contact = user.login_phone = ""
            user.login_phone_verified = user.sms_updates = False
            user.date_of_birth = None
            user.is_active = user.is_staff = user.is_superuser = False
            user.set_unusable_password()  # also ends every session: they are tied to the password hash
            user.save()
            self.status, self.closed_at = self.Status.DONE, timezone.now()
            self.save()
            transaction.on_commit(lambda: [sheet.image.delete(save=False) for sheet in sheets])  # photo files
        return email
