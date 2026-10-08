"""The revision course (docs/examleaf-phase6-plan.md, work package D): per chapter the Board's marks and how often it
asked, a 10-15 minute revision made of short clips, flash cards and one-mark quiz items; who may watch (entitlements,
book codes); each student's progress, quiz answers, settings and app devices."""

import hashlib
import hmac
import re
import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django_fsm import FSMField, transition
from model_utils.models import TimeStampedModel
from taggit.managers import TaggableManager

VIDEO_TYPES = ["mp4", "mov", "m4v", "webm", "mkv"]


def source_path(clip, filename):
    return f"learn/sources/{uuid.uuid4().hex}{Path(filename).suffix.lower()}"  # not the editor's file name


def max_upload(file):
    if file.size > settings.LEARN_MAX_UPLOAD_MB * 1024 * 1024:
        raise ValidationError(f"At most {settings.LEARN_MAX_UPLOAD_MB} MB (LEARN_MAX_UPLOAD_MB).")


class Chapter(models.Model):
    subject = models.ForeignKey("content.Subject", on_delete=models.PROTECT, related_name="chapters")
    number = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=200)
    weight = models.DecimalField(
        "Board marks", max_digits=4, decimal_places=1, default=0, help_text="From format.json: import_chapter_insights."
    )
    frequency = models.PositiveSmallIntegerField(
        "previous-year questions", default=0, help_text="Questions the Board asked on it (production/<subject>/pyq/)."
    )
    must_do = models.TextField("must-do note", blank=True, help_text="Markdown.")

    class Meta:
        ordering = ["subject", "number"]
        constraints = [models.UniqueConstraint(fields=["subject", "number"], name="unique_learn_chapter")]

    def __str__(self):
        return self.tag_name

    @property
    def tag_name(self):  # the chapter tag of content.Question: "Ch 3: Current Electricity"
        return f"Ch {self.number}: {self.title}"


class Revision(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "draft"
        PUBLISHED = "published", "published"

    chapter = models.OneToOneField(Chapter, on_delete=models.CASCADE, related_name="revision")
    title = models.CharField(max_length=200)
    target_minutes = models.PositiveSmallIntegerField(
        default=12, validators=[MinValueValidator(1), MaxValueValidator(60)], help_text="10 to 15."
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT, db_index=True)
    order = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        ordering = ["order", "pk"]

    def __str__(self):
        return self.title


class Clip(TimeStampedModel):
    class Kind(models.TextChoices):
        CONCEPT = "concept", "concept"
        TRICK = "trick", "trick"
        SHORTCUT = "shortcut", "shortcut"
        FORMULA = "formula", "formula"
        PATTERN = "pattern", "question pattern"
        MISTAKE = "mistake", "common mistake"
        PYQ = "pyq", "previous-year question"

    class Processing(models.TextChoices):
        UPLOADED = "uploaded", "uploaded"
        PROCESSING = "processing", "processing"
        READY = "ready", "ready"
        FAILED = "failed", "failed"

    revision = models.ForeignKey(Revision, on_delete=models.CASCADE, related_name="clips")
    order = models.PositiveIntegerField(default=0, db_index=True)
    title = models.CharField(max_length=200)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.CONCEPT)
    source = models.FileField(
        "video",
        upload_to=source_path,
        blank=True,
        validators=[FileExtensionValidator(VIDEO_TYPES), max_upload],
        help_text="Vertical (9:16) is best; processed into HLS for phones after saving.",
    )
    processing = FSMField(default=Processing.UPLOADED, choices=Processing.choices, editable=False)
    processing_error = models.TextField(blank=True, editable=False, help_text="The end of ffmpeg's messages.")
    hls_path = models.CharField("HLS master playlist", max_length=300, blank=True, editable=False)
    poster = models.CharField(max_length=300, blank=True, editable=False)
    duration = models.PositiveIntegerField("seconds", default=0, editable=False)
    notes = models.TextField("transcript or notes", blank=True, help_text="Markdown.")
    is_free_preview = models.BooleanField(
        "free preview", default=False, help_text="The first clip of a revision is free anyway (LEARN_FREE_PREVIEW)."
    )
    questions = models.ManyToManyField("content.Question", blank=True, related_name="+")
    tags = TaggableManager(blank=True)

    class Meta:
        ordering = ["order", "pk"]

    def __str__(self):
        return self.title

    @transition(field=processing, source="*", target=Processing.PROCESSING)
    def start(self):
        self.processing_error = ""

    @transition(field=processing, source=Processing.PROCESSING, target=Processing.READY)
    def finish(self, hls_path, poster, duration):
        self.hls_path, self.poster, self.duration = hls_path, poster, duration

    @transition(field=processing, source="*", target=Processing.FAILED)
    def fail(self, error):
        self.processing_error = error[-2000:]


class FlashCard(models.Model):
    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name="flash_cards")
    order = models.PositiveIntegerField(default=0, db_index=True)
    front = models.TextField(help_text="Markdown.")
    back = models.TextField(help_text="Markdown.")
    tags = TaggableManager(blank=True)

    class Meta:
        ordering = ["order", "pk"]

    def __str__(self):
        return self.front[:60]


def normalise(text):
    """A fill-in-the-blank answer as compared: lower case, no punctuation or leading article, single spaces."""
    text = re.sub(r"[^\w\s]", " ", str(text).lower())
    return re.sub(r"^(a|an|the) ", "", " ".join(text.split()))


class QuizItem(models.Model):
    class Kind(models.TextChoices):
        MCQ = "mcq", "multiple choice"
        TRUE_FALSE = "true_false", "true or false"
        FILL_BLANK = "fill_blank", "fill in the blank"

    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name="quiz_items")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    text = models.TextField("question", help_text="Markdown.")
    options = models.JSONField(default=list, blank=True, help_text='Multiple choice: the options, ["(i) …", …].')
    answer = models.CharField(
        max_length=200,
        help_text="Multiple choice: the right option's number (1 for the first); true or false: true or false; "
        "fill in the blank: the accepted answers, separated by |.",
    )
    explanation = models.TextField(blank=True, help_text="Markdown.")
    source = models.OneToOneField(
        "content.Question", on_delete=models.SET_NULL, null=True, blank=True, related_name="+", editable=False
    )
    tags = TaggableManager(blank=True)

    class Meta:
        ordering = ["chapter", "pk"]

    def __str__(self):
        return self.text[:60]

    def clean(self):
        if self.kind == self.Kind.MCQ and not (self.answer.isdigit() and 1 <= int(self.answer) <= len(self.options)):
            raise ValidationError({"answer": "The number of one of the options."})
        if self.kind == self.Kind.TRUE_FALSE and self.answer not in ("true", "false"):
            raise ValidationError({"answer": "true or false."})

    def is_right(self, given):
        """Checked on the server: the option's number, true/false, or the word(s) of the blank."""
        if self.kind == self.Kind.FILL_BLANK:
            return normalise(given) in {normalise(answer) for answer in self.answer.split("|")}
        return str(given).strip().lower() == self.answer


CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"  # no 0/O or 1/I: read off a printed page
CODE_LENGTH = 12


def clean_code(code):
    """A book code as typed (any case, spaces, dashes) to its 12 characters."""
    return re.sub(r"[\s-]", "", str(code)).upper()


def code_digest(code):
    """What the database keeps of a book code: an HMAC keyed with LEARN_CODE_SECRET (never the code itself)."""
    key = (settings.LEARN_CODE_SECRET or "examleaf-book-codes").encode()
    return hmac.new(key, clean_code(code).encode(), hashlib.sha256).hexdigest()


class BookCode(models.Model):
    """A code printed in a book (manage.py make_book_codes), redeemed once in the app for an entitlement."""

    digest = models.CharField(max_length=64, unique=True, editable=False)
    subject = models.ForeignKey(
        "content.Subject", on_delete=models.PROTECT, null=True, blank=True, related_name="+", help_text="Empty: all."
    )
    batch = models.CharField(max_length=40, help_text="The print run, e.g. PHY-2027-1.")
    created = models.DateTimeField(default=timezone.now, editable=False)
    redeemed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+", editable=False
    )
    redeemed_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ["-created", "-pk"]

    def __str__(self):
        return f"Book code #{self.pk} ({self.batch})"


class Entitlement(TimeStampedModel):
    """What a student may watch: one subject or all of them (empty), until a day or for good."""

    class Source(models.TextChoices):
        BOOK_CODE = "book_code", "book code"
        PURCHASE = "purchase", "purchase"
        GRANT = "grant", "staff grant"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="entitlements")
    subject = models.ForeignKey(
        "content.Subject", on_delete=models.PROTECT, null=True, blank=True, related_name="+", help_text="Empty: all."
    )
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.GRANT, editable=False)
    reference = models.CharField(max_length=40, blank=True, editable=False, help_text="The order or the book code.")
    valid_until = models.DateField(null=True, blank=True, help_text="The last day; empty: no end.")
    note = models.CharField(max_length=200, blank=True, help_text="Why it was granted (staff).")

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return f"Entitlement #{self.pk}"  # no personal data: kept in the admin's change log


class Learner(models.Model):
    """A student's course settings (the app's settings screen)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, primary_key=True, related_name="learner"
    )
    exam_date = models.DateField(null=True, blank=True)
    minutes_per_day = models.PositiveSmallIntegerField(
        default=30, validators=[MinValueValidator(10), MaxValueValidator(300)]
    )
    reminders = models.BooleanField("daily reminder in the app", default=False)

    def __str__(self):
        return f"Course settings #{self.pk}"


class Progress(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="clip_progress")
    clip = models.ForeignKey(Clip, on_delete=models.CASCADE, related_name="+")
    seconds_watched = models.PositiveIntegerField(default=0)
    completed = models.BooleanField(default=False)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "clip"], name="one_progress_per_clip")]

    def __str__(self):
        return f"Progress #{self.pk}"


class QuizAttempt(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="quiz_attempts")
    item = models.ForeignKey(QuizItem, on_delete=models.CASCADE, related_name="+")
    correct = models.BooleanField()
    created = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["created", "pk"]

    def __str__(self):
        return f"Quiz attempt #{self.pk}"


class CardReview(models.Model):
    """A flash card turned over: did the student know the back?"""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="card_reviews")
    card = models.ForeignKey(FlashCard, on_delete=models.CASCADE, related_name="+")
    known = models.BooleanField()
    created = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["created", "pk"]

    def __str__(self):
        return f"Card review #{self.pk}"


class Device(models.Model):
    """The app on a phone, for the daily reminder (Firebase Cloud Messaging); deleted with the account."""

    class Platform(models.TextChoices):
        ANDROID = "android", "Android"
        IOS = "ios", "iOS"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="devices")
    token = models.CharField("Firebase installation ID", max_length=512, unique=True, help_text="FCM sends to it.")
    platform = models.CharField(max_length=10, choices=Platform.choices, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Device #{self.pk}"
