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
from staff.config import site_setting

from . import roles

STAFF_SESSION = timedelta(hours=8)  # a member of staff's session lasts this long from the log-in (H2, L11)


def staff_session_limit(user):
    """How long a staff session lasts from its log-in, however busy: 8 hours; a break-glass account's (a superuser's)
    STAFF_BREAK_GLASS_HOURS, 2 (research 1.6: the elevated session is time-boxed)."""
    if user.is_superuser:
        return min(STAFF_SESSION, timedelta(hours=settings.STAFF_BREAK_GLASS_HOURS))
    return STAFF_SESSION


@receiver(user_logged_in)  # allauth's log-in (the website and the admin; not the API, which has no session)
def shorter_staff_sessions(sender, request, user, **kwargs):
    if user.is_staff or user.is_superuser:
        request.session.set_expiry(staff_session_limit(user))


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
    is_owner = property(lambda self: self.is_superuser or self.has_role(roles.OWNER))  # the panel's last resort

    @cached_property
    def consent_pending(self):
        """PARENTAL_CONSENT_MODE "verified": a student under 18 whose parent has not confirmed through the emailed link
        yet. Such an account can log in and read, not save marks or order (M9)."""
        return (
            site_setting("PARENTAL_CONSENT_MODE") == "verified"  # the environment's, or the panel's
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
    and a keyed hash of the internet address (enough to compare with an address later, not to read it back). The
    ledger is append-only in practice: rows are added, never changed (no endpoint changes or deletes one, the admin
    reads them), but for the erasure dropping the address hash."""

    class Event(models.TextChoices):
        GIVEN = "given", "given"
        WITHDRAWN = "withdrawn", "withdrawn"

    class Method(models.TextChoices):
        DECLARED = "declared", "ticked on the form"
        EMAIL_LINK = "email_link", "confirmed through the link emailed to the parent"
        SMS_LINK = "sms_link", "confirmed through the link texted to the parent"
        # DPDP Rules r.10: the parent an identifiable adult (an account of theirs, a DigiLocker token, staff by hand)
        ADULT_ACCOUNT = "adult_account", "confirmed by the parent's own verified adult account"
        DIGILOCKER = "digilocker", "confirmed with a DigiLocker token"
        STAFF_MANUAL = "staff_manual", "recorded by staff, with evidence"

    class Purpose(
        models.TextChoices
    ):  # the values `purpose` takes (free text in the table: older rows kept as they are)
        ACCOUNT = "account and free solutions (privacy policy)", "the account and the free solutions"
        MARKETING = "marketing", "marketing messages"

    class Channel(models.TextChoices):
        EMAIL = "email", "email"
        SMS = "sms", "SMS"
        WHATSAPP = "whatsapp", "WhatsApp"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="consents")
    event = models.CharField(max_length=10, choices=Event.choices, default=Event.GIVEN)
    purpose = models.CharField(max_length=120, default=Purpose.ACCOUNT.value)
    notice_version = models.CharField("privacy policy version", max_length=20)
    by_parent = models.BooleanField("by a parent or guardian", default=False)
    method = models.CharField("how", max_length=20, choices=Method.choices, default=Method.DECLARED)
    verified_at = models.DateTimeField("verified at", null=True, blank=True, help_text="When the parent confirmed.")
    ip_hash = models.CharField("address hash", max_length=64, blank=True)
    created = models.DateTimeField(default=timezone.now, db_index=True)
    # Phase B: legal
    channel = models.CharField(
        max_length=10, choices=Channel.choices, blank=True, help_text="A marketing consent's channel; empty: every one."
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="The member of staff who recorded it by hand.",
    )
    evidence_ref = models.CharField(
        "evidence reference",
        max_length=200,
        blank=True,
        help_text="Where the evidence is (a ticket's number, a letter's date): never the document itself.",
    )

    class Meta:
        ordering = ["-created"]
        permissions = [("export_consentrecord", "Can export consent records")]

    def __str__(self):
        return f"Consent {self.event} #{self.pk}"

    @classmethod
    def record(
        cls,
        request,
        user,
        event=Event.GIVEN,
        by_parent=False,
        method=Method.DECLARED,
        verified_at=None,
        purpose=Purpose.ACCOUNT,
        channel="",
        verified_by=None,
        evidence_ref="",
    ):
        # the client address as axes sees it (PROXY_COUNT aware); none when staff record it (verified_by)
        ip = (get_client_ip_address(request) or "") if request is not None and verified_by is None else ""
        return cls.objects.create(
            user=user,
            event=event,
            by_parent=by_parent,
            method=method,
            verified_at=verified_at,
            purpose=purpose,
            channel=channel,
            verified_by=verified_by,
            evidence_ref=evidence_ref,
            notice_version=Page.objects.filter(slug="privacy").values_list("version", flat=True).first() or "",
            ip_hash=salted_hmac("accounts.ConsentRecord.ip", ip, algorithm="sha256").hexdigest() if ip else "",
        )


class DeletionRequest(models.Model):
    """A student's "Delete my account": after GRACE the purge task (accounts.tasks) erases the personal data, unless
    the student logged in and cancelled it, or something holds it (staff.privacy.erasure_holds: a legal hold on the
    account, a student under 18 whose parent has not confirmed). Kept once done: the erasure ledger (`subject_hash`),
    which `manage.py reapply_erasures` erases again after a restore from a backup (never an erased account back)."""

    GRACE = timedelta(days=7)
    REGISTRATION_KEPT = timedelta(days=180)  # the IT Rules' r.3(1)(h), when SUPPORT_INTERMEDIARY_RULES is on
    # what a person gave to register, kept that long when the intermediary rule applies (forget_registration)
    REGISTRATION_FIELDS = ["email", "full_name", "phone", "login_phone", "district", "date_of_birth", "parent_name"]
    REGISTRATION_FIELDS += ["parent_contact"]

    class Status(models.TextChoices):
        PENDING = "pending", "waiting"
        CANCELLED = "cancelled", "cancelled"
        DONE = "done", "deleted"

    class Held(Exception):
        """The erasure waits: the reasons, in words (a legal hold on the account, a parent's confirmation)."""

        def __init__(self, reasons):
            self.reasons = list(reasons)
            super().__init__(" ".join(self.reasons))

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="deletion_requests")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    requested_at = models.DateTimeField(default=timezone.now)
    due_at = models.DateTimeField()
    closed_at = models.DateTimeField("cancelled or done at", null=True, blank=True)
    # Phase B: legal
    parent_confirmed_at = models.DateTimeField(
        null=True, blank=True, help_text="A student under 18: when the parent or guardian confirmed the erasure."
    )
    parent_confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="The member of staff who recorded the confirmation by hand; empty: the parent's own link.",
    )
    parent_evidence_ref = models.CharField(
        max_length=200, blank=True, help_text="How staff had it (a ticket's number, a letter's date), not the document."
    )
    subject_hash = models.CharField(
        max_length=64, blank=True, db_index=True, help_text="The ledger: a keyed hash of the email address erased."
    )
    registration_until = models.DateTimeField(
        null=True, blank=True, help_text="The intermediary rule: the registration details stay until then."
    )
    ledger_copied_at = models.DateTimeField(
        null=True, blank=True, help_text="When the ledger's line was copied to the backups' bucket."
    )

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

    def complete(self, reapply=False, registration_until=None, data_request=None):
        """Erase the personal data (research 4.5), unless something holds it: DeletionRequest.Held with the reasons
        (staff.privacy.erasure_holds). `reapply` (reapply_erasures, after a restore) skips that check, made when it was
        first done. The user row stays, anonymised and unable to log in, so that the saved marks remain as statistics
        on the papers (without notes); consent records stay as proof, without the address hash; the SMS log's rows stay
        their year as processing logs (examleaf.retention), without the account or the number's last digits; orders,
        invoices and credit notes stay as the books of account, with the address copied into them. With the
        intermediary rule (staff.privacy.intermediary_rules) the registration details stay REGISTRATION_KEPT more
        (`registration_until`), then forget_registration() erases them. The ledger keeps a keyed hash of the address
        (`subject_hash`), copied to the backups' bucket; the processors that keep personal data get a task each in the
        inbox (staff.privacy.processor_tasks). Returns the old email address, for the goodbye email; None when another
        run erased it meanwhile."""
        from staff import audit, privacy  # (the staff app imports this module)

        user, email = self.user, self.user.email
        if not reapply and (reasons := privacy.erasure_holds(user, deletion=self)):
            raise self.Held(reasons)
        now = timezone.now()
        if reapply:
            keep_until = registration_until if registration_until and registration_until > now else None
        else:
            keep_until = now + self.REGISTRATION_KEPT if privacy.intermediary_rules() else None
        with transaction.atomic():
            from practice.models import AnswerSheetUpload, Attempt  # (practice does not import accounts)
            from shop.models import StockAlert  # (shop imports this module)

            locked = type(self).objects.select_for_update().get(pk=self.pk)
            if locked.status == self.Status.DONE and not reapply:
                return None  # another run (the nightly purge, an approved erasure) was first
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
            user.usersession_set.all().delete()  # signed-in devices: addresses and browsers
            # failed log-ins by address or by mobile number (axes)
            AccessAttempt.objects.filter(username__in=[email, user.login_phone or email]).delete()
            # the SMS log: a processing log kept its year (examleaf.retention), without the account or the last digits
            user.sms_messages.update(user=None, phone_last4="")
            user.attempts.update(notes="")
            user.answer_sheets.all().delete()
            user.consents.update(ip_hash="")
            Nominee.objects.filter(user=user).delete()
            user.groups.clear()
            user.user_permissions.clear()
            if keep_until is None:
                forget_registration(user)
            user.login_phone_verified = user.sms_updates = False
            user.is_active = user.is_staff = user.is_superuser = False
            user.set_unusable_password()  # also ends every session: they are tied to the password hash
            user.save()
            self.status, self.closed_at = self.Status.DONE, now
            self.subject_hash = self.subject_hash or privacy.ledger_hash(email)
            self.registration_until, self.ledger_copied_at = keep_until, None
            self.save()
            audit.record(
                "account.erased",
                target=("accounts.user", user.pk, f"Account #{user.pk}"),
                details={
                    "deletion_request": self.pk,
                    "reapplied": reapply,
                    "registration_kept": keep_until is not None,
                },
            )
            transaction.on_commit(lambda: [sheet.image.delete(save=False) for sheet in sheets])  # photo files
            transaction.on_commit(lambda: privacy.after_erasure(self, data_request), robust=True)
        return email

    def forget_registration(self):
        """The intermediary rule's REGISTRATION_KEPT over: the registration details kept go too (the nightly
        accounts.tasks.purge_due_deletions)."""
        from staff import audit

        with transaction.atomic():
            forget_registration(self.user)
            self.user.save()
            self.registration_until = None
            self.save(update_fields=["registration_until"])
            audit.record(
                "account.registration_erased", target=("accounts.user", self.user_id, f"Account #{self.user_id}")
            )


def forget_registration(user):
    """The details a person gave to register (DeletionRequest.REGISTRATION_FIELDS) anonymised on the user row; the
    class and board stay, with the saved marks, as statistics."""
    user.email, user.full_name = f"deleted-{user.pk}@deleted.invalid", "Deleted account"
    user.phone = user.district = user.parent_name = user.parent_contact = user.login_phone = ""
    user.date_of_birth = None


# Phase B: legal


class LegalHoldQuerySet(models.QuerySet):
    def active(self, today=None):
        """The holds in force: not released, and without an end or with one not yet past (India's date)."""
        today = today or timezone.localdate()
        return self.filter(released_at=None).filter(models.Q(until=None) | models.Q(until__gte=today))


class LegalHold(models.Model):
    """A legal hold (research 4.5; DPDP s.17(1)(a): processing to establish or defend a legal claim): a person, or one
    record (an order, an invoice …), kept as it is while a dispute, a chargeback, a claim or an investigation is open,
    until `until` or until released. A hold on a person stops their erasure (the dry run says so, and
    DeletionRequest.complete waits); a hold on a record keeps it from the retention clean-up (examleaf.retention) and
    is listed in the erasure's dry run. Made and released through the staff API (staff.manage_holds)."""

    class Reason(models.TextChoices):
        DISPUTE = "dispute", "a dispute"
        CHARGEBACK = "chargeback", "a chargeback"
        CLAIM = "claim", "a legal claim"
        INVESTIGATION = "investigation", "an investigation"
        OTHER = "other", "another reason (in the note)"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="legal_holds"
    )
    target_type = models.ForeignKey(ContentType, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    target_id = models.CharField(max_length=64, blank=True)
    reason = models.CharField(max_length=15, choices=Reason.choices)
    note = models.TextField(blank=True, help_text="The case: its reference and what it is about, briefly.")
    until = models.DateField(null=True, blank=True, help_text="The last day it holds; empty: until released.")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created = models.DateTimeField(default=timezone.now)
    released_at = models.DateTimeField(null=True, blank=True)
    released_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    release_reason = models.CharField(max_length=300, blank=True)

    objects = LegalHoldQuerySet.as_manager()

    class Meta:
        default_permissions = ("view",)  # made and released through staff.manage_holds
        ordering = ["-created", "-pk"]
        indexes = [models.Index(fields=["target_type", "target_id"], name="accounts_hold_target")]
        constraints = [
            models.CheckConstraint(  # a person or a record, never both, never neither
                condition=(models.Q(user__isnull=False) & models.Q(target_type__isnull=True))
                | (models.Q(user__isnull=True) & models.Q(target_type__isnull=False) & ~models.Q(target_id="")),
                name="legal_hold_one_target",
            )
        ]

    def __str__(self):
        return f"Legal hold #{self.pk}"

    @property
    def is_active(self):
        return self.released_at is None and (self.until is None or self.until >= timezone.localdate())


class Nominee(models.Model):
    """The person a data principal nominates to exercise their rights after their death or incapacity (DPDP s.14,
    r.14(4)): given on My account (api/v1/me/nominee/), read by staff only behind the contact's mask; verified when a
    claim is made (the claim's flow: Phase C). Erased with the account."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="nominee")
    name = models.CharField(max_length=120)
    contact = models.CharField(max_length=120, help_text="An email address or an Indian mobile number.")
    relation = models.CharField(max_length=60, help_text="Mother, brother, friend …")
    verified_at = models.DateTimeField(null=True, blank=True, help_text="When a claim proved the nomination.")
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created = models.DateTimeField(default=timezone.now)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        default_permissions = ("view",)  # each person their own (api/v1/me/nominee/); staff read it, masked

    def __str__(self):
        return f"Nominee #{self.pk}"
