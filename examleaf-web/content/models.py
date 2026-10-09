from datetime import timedelta

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.functional import cached_property
from model_utils.models import TimeStampedModel
from qr_code.qrcode.maker import make_qr_code_image
from qr_code.qrcode.utils import QRCodeOptions
from simple_history.models import HistoricalRecords
from taggit.managers import TaggableManager


class Board(models.Model):
    name = models.CharField(max_length=120)
    short_name = models.CharField(max_length=20, unique=True)
    state = models.CharField(max_length=60)

    def __str__(self):
        return self.short_name


class ClassLevel(models.Model):
    number = models.PositiveSmallIntegerField(unique=True)

    def __str__(self):
        return f"Class {self.number}"


class Subject(models.Model):
    name = models.CharField(max_length=60)
    code = models.CharField(max_length=10)  # PHY, CHE, MAT, BIO
    board = models.ForeignKey(Board, on_delete=models.PROTECT)
    class_level = models.ForeignKey(ClassLevel, on_delete=models.PROTECT)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["board", "class_level", "code"], name="unique_subject")]

    def __str__(self):
        return f"{self.name} ({self.board}, {self.class_level})"


class Book(models.Model):
    title = models.CharField(max_length=200)
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="books")
    edition = models.CharField(max_length=60, blank=True)
    slug = models.SlugField(unique=True)
    cover = models.CharField(max_length=200, blank=True, help_text="Static path, e.g. img/physics.png")
    history = HistoricalRecords()

    # Phase B: content
    class Format(models.TextChoices):
        PRINT = "print", "printed book"
        EBOOK = "ebook", "e-book"

    isbn = models.CharField(
        "ISBN-13",
        max_length=13,
        blank=True,
        help_text="One per format, checked when set (content/isbn.py): a new one for a substantial change of the text, "
        "never for an unchanged reprint.",
    )
    format = models.CharField(max_length=5, choices=Format.choices, default=Format.PRINT)
    published_on = models.DateField(
        null=True,
        blank=True,
        help_text="The day this edition was published: the legal deposit's clock (CONTENT_LEGAL_DEPOSIT_DAYS) starts.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["isbn"],
                condition=~Q(isbn=""),
                name="unique_book_isbn",
                violation_error_message="Another book has this ISBN: each format and edition has its own.",
            )
        ]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return f"/books/{self.slug}/"  # the website's page (examleaf-frontend)

    @property
    def deposit_due_on(self):
        """The last day to deliver the legal deposits (CONTENT_LEGAL_DEPOSIT_DAYS after publication), or None."""
        return self.published_on + timedelta(days=settings.CONTENT_LEGAL_DEPOSIT_DAYS) if self.published_on else None

    def clean(self):
        """The ISBN is checked when the book is made or its ISBN changes (a book saved before the check keeps its
        own until then), and kept as its 13 digits."""
        from .isbn import changed_isbn

        self.isbn = changed_isbn(self.isbn, Book.objects.filter(pk=self.pk).values_list("isbn", flat=True).first())

    @cached_property
    def sample(self):
        """The paper whose solutions are open to everyone (Paper.is_sample), or None."""
        return self.papers.filter(is_sample=True, is_published=True).first()


class Paper(models.Model):
    class Tier(models.TextChoices):
        EASY = "E", "Easy"
        MEDIUM = "M", "Medium"
        HARD = "H", "Hard"

    book = models.ForeignKey(Book, on_delete=models.PROTECT, related_name="papers")
    code = models.CharField(max_length=20, unique=True)  # PHY-E01
    tier = models.CharField(max_length=1, choices=Tier.choices)
    number = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=200)
    full_marks = models.PositiveSmallIntegerField()
    pass_marks = models.PositiveSmallIntegerField()
    time_text = models.CharField(max_length=40)
    header_json = models.JSONField(default=dict, blank=True, help_text="instruction lines and allotment tables")
    is_published = models.BooleanField(default=True)
    is_sample = models.BooleanField(
        "open sample",
        default=False,
        help_text="Its solutions open without an account, even when the others need one: the paper the home, book and "
        "product pages offer as a sample. One per book.",
    )
    history = HistoricalRecords()

    class Meta:
        ordering = ["book", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["book"],
                condition=models.Q(is_sample=True),
                name="one_sample_per_book",
                violation_error_message="Another paper of this book is its open sample: untick that one first.",
            )
        ]

    def __str__(self):
        return self.code

    def get_absolute_url(self):
        return f"/s/{self.code}/"  # the website's solutions page (examleaf-frontend)

    @property
    def short_code(self):  # E-01, as printed in the book
        return f"{self.tier}-{self.number:02d}"

    def landing_url(self):  # what the QR code printed on the paper encodes
        return settings.SITE_URL + self.get_absolute_url()

    def qr_image(self, image_format="png", url=None):  # url: the landing address with a query (a print run's)
        return make_qr_code_image(
            url or self.landing_url(), QRCodeOptions(size=10, border=4, image_format=image_format)
        )


class Question(models.Model):
    paper = models.ForeignKey(Paper, on_delete=models.CASCADE, related_name="questions")
    order = models.PositiveSmallIntegerField()
    label = models.CharField(max_length=20)  # 1(a), 9, 9 OR, B9(a), Z3 OR — the solution file's "### label"
    group_label = models.CharField(max_length=300, blank=True)
    part_label = models.CharField(max_length=120, blank=True)
    text_md = models.TextField()
    options_json = models.JSONField(default=list, blank=True)
    marks_text = models.CharField(max_length=40, blank=True)
    is_alternative = models.BooleanField(default=False, help_text="the OR alternative of the previous question")
    table_md = models.TextField(blank=True)
    tags = TaggableManager(blank=True, help_text="chapter and textbook section")
    history = HistoricalRecords()

    # Phase B: content
    class State(models.TextChoices):
        DRAFT = "draft", "draft"
        IN_REVIEW = "in_review", "in review"
        PUBLISHED = "published", "published"

    # what an edit in the panel writes to the draft, never to the live text: the review publishes it (content.review)
    DRAFTED = ("text_md", "table_md", "options_json", "marks_text", "group_label", "part_label", "is_alternative")
    is_published = models.BooleanField(
        default=True, help_text="Off: no longer in the books repository (kept, hidden, with its history)."
    )
    state = models.CharField(max_length=10, choices=State.choices, default=State.PUBLISHED, db_index=True)
    draft = models.JSONField(default=dict, blank=True, help_text="The changed fields to review: {field: value}.")
    draft_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    published_at = models.DateTimeField(null=True, blank=True, help_text="Its last publish from the panel.")
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["paper", "order"]
        constraints = [models.UniqueConstraint(fields=["paper", "label"], name="unique_question_label")]

    def __str__(self):
        return f"{self.paper.code} {self.label}"

    @property
    def number(self):  # label as printed: B9(a) -> 9(a); alternatives show no number
        return self.label.lstrip("BZ")


class Solution(models.Model):
    question = models.OneToOneField(Question, on_delete=models.CASCADE, related_name="solution")
    body_md = models.TextField()
    history = HistoricalRecords()

    # Phase B: content
    DRAFTED = ("body_md",)
    state = models.CharField(
        max_length=10, choices=Question.State.choices, default=Question.State.PUBLISHED, db_index=True
    )
    draft = models.JSONField(default=dict, blank=True, help_text="The changed fields to review: {field: value}.")
    draft_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    published_at = models.DateTimeField(null=True, blank=True, help_text="Its last publish from the panel.")
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    def __str__(self):
        return f"Solution {self.question}"


# Phase B: content


class ReviewTask(TimeStampedModel):
    """A second person's check of a draft before it goes live (plan 5.10: author → checker → publish): what was
    submitted (`draft`, the changed fields), by whom, its stage and state, the comments, and once published the live
    values it replaced (`previous`), which a rollback puts back. The target is any drafted record (a question, a
    solution; the course's may follow), by content type and id. One open task per target: an edit of the draft after it
    was submitted cancels it (content.review)."""

    class Stage(models.TextChoices):
        CHECK = "check", "a second person checks it"
        PUBLISH = "publish", "approved: to publish"

    class State(models.TextChoices):
        IN_PROGRESS = "in_progress", "in progress"
        APPROVED = "approved", "approved"
        NEEDS_CHANGES = "needs_changes", "needs changes"
        CANCELLED = "cancelled", "cancelled"

    target_type = models.ForeignKey(ContentType, on_delete=models.PROTECT, related_name="+")
    target_id = models.PositiveBigIntegerField()
    target = GenericForeignKey("target_type", "target_id")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    paper = models.ForeignKey(Paper, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    label = models.CharField(max_length=200, help_text='What it is, by code: "PHY-E01 2(c), solution".')
    stage = models.CharField(max_length=10, choices=Stage.choices, default=Stage.CHECK)
    state = models.CharField(max_length=15, choices=State.choices, default=State.IN_PROGRESS, db_index=True)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    draft = models.JSONField(default=dict, help_text="The changed fields as submitted: {field: value}.")
    previous = models.JSONField(default=dict, blank=True, help_text="The live values its publish replaced.")
    comments = models.JSONField(default=list, blank=True, help_text="[{author, text, at, field}]")
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    edited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="The draft's last editor when it was submitted: never its checker.",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    published_at = models.DateTimeField(null=True, blank=True)
    rolled_back_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    rolled_back_at = models.DateTimeField(null=True, blank=True)

    OPEN = Q(state=State.IN_PROGRESS) | Q(state=State.APPROVED, published_at=None)

    class Meta:
        default_permissions = ("view",)  # submitted with content.change_*, decided with staff.publish_paper
        ordering = ["-created", "-pk"]
        indexes = [models.Index(fields=["target_type", "target_id"], name="content_review_target")]
        constraints = [
            models.UniqueConstraint(
                fields=["target_type", "target_id"],
                condition=Q(state="in_progress") | Q(state="approved", published_at=None),
                name="one_open_review",
            )
        ]

    def __str__(self):
        return f"Review #{self.pk}"

    @property
    def is_open(self):
        return self.state == self.State.IN_PROGRESS or (self.state == self.State.APPROVED and not self.published_at)


class ErrorReport(TimeStampedModel):
    """A mistake reported by a reader (the public "Report a mistake", POST /api/v1/reports/) or flagged by the quiz's
    item analysis (content.tasks.flag_items): on what (a solution, a question, a quiz item or a clip, by content type
    and id: the course reads it too), where (the paper, the question, the marking step, the printing it was read in),
    what kind, and its triage: reported → confirmed or rejected → fixed online → fixed in printing N. Spam (by the
    rules of content.reports) stays out of the queue and goes after 30 days. The reporter's email, if left, serves only
    to tell them of the fix, and is cleared then (or once the report is rejected)."""

    class Category(models.TextChoices):
        WRONG_ANSWER = "wrong_answer", "a wrong answer or step"
        TYPO = "typo", "a typing or spelling mistake"
        MARKS = "marks", "the marks or the marking scheme"
        UNCLEAR = "unclear", "hard to follow"
        DISPLAY = "display", "maths or a picture does not show"
        OTHER = "other", "something else"
        ITEM_ANALYSIS = "item_analysis", "flagged by the item analysis"

    class State(models.TextChoices):
        REPORTED = "reported", "reported"
        CONFIRMED = "confirmed", "confirmed"
        REJECTED = "rejected", "rejected"
        FIXED_ONLINE = "fixed_online", "fixed online"
        FIXED_IN_PRINTING = "fixed_in_printing", "fixed in printing"

    OPEN = [State.REPORTED, State.CONFIRMED]
    FIXED = [State.FIXED_ONLINE, State.FIXED_IN_PRINTING]

    target_type = models.ForeignKey(ContentType, on_delete=models.PROTECT, related_name="+")
    target_id = models.PositiveBigIntegerField()
    target = GenericForeignKey("target_type", "target_id")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    paper = models.ForeignKey(Paper, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    question = models.ForeignKey(Question, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    step = models.PositiveSmallIntegerField(null=True, blank=True, help_text="The marking step, 1 for the first.")
    printing = models.CharField(max_length=40, blank=True, help_text="The print run it was read in: PHY-2027-1.")
    category = models.CharField(max_length=15, choices=Category.choices)
    note = models.TextField(blank=True)
    email = models.EmailField(blank=True, help_text="Left to hear of the fix; cleared once told (or rejected).")
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    teacher_verified = models.BooleanField(default=False, help_text="Reported by a verified teacher.")
    state = models.CharField(max_length=20, choices=State.choices, default=State.REPORTED, db_index=True)
    fixed_in = models.CharField(max_length=40, blank=True, help_text="The printing that carries the fix.")
    fixed_at = models.DateTimeField(null=True, blank=True, help_text="When it was fixed online.")
    resolved_at = models.DateTimeField(null=True, blank=True, help_text="When it was confirmed or rejected.")
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    staff_note = models.TextField(blank=True)
    reporter_told_at = models.DateTimeField(null=True, blank=True)
    public = models.BooleanField(default=False, help_text="On the errata of its book and printing.")
    spam = models.BooleanField(default=False, db_index=True)
    spam_reason = models.CharField(max_length=60, blank=True)

    class Meta:
        default_permissions = ("view",)  # triaged with staff.triage_report
        ordering = ["created", "pk"]  # the queue: oldest first
        indexes = [
            models.Index(fields=["state", "created"], name="content_report_queue"),
            models.Index(fields=["target_type", "target_id"], name="content_report_target"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["target_type", "target_id"],
                condition=Q(category="item_analysis", state__in=["reported", "confirmed"]),
                name="one_open_item_flag",
            )
        ]

    def __str__(self):
        return f"Report #{self.pk}"


class LegalDeposit(models.Model):
    """One copy of a book's edition delivered to one of the four public libraries the Delivery of Books and
    Newspapers (Public Libraries) Act 1954 names, within CONTENT_LEGAL_DEPOSIT_DAYS of publication (30, to be verified
    against the Act's text): when it went, the proof of dispatch (and its scan, in the private storage), the ERPNext
    delivery note once the stock movement is made there."""

    class Library(models.TextChoices):
        NATIONAL_LIBRARY = "national_library", "National Library, Kolkata"
        CONNEMARA = "connemara", "Connemara Public Library, Chennai"
        ASIATIC_SOCIETY = "asiatic_society", "Central Library (Asiatic Society), Mumbai"
        DELHI_PUBLIC_LIBRARY = "delhi_public_library", "Delhi Public Library, Delhi"

    book = models.ForeignKey(Book, on_delete=models.PROTECT, related_name="legal_deposits")
    edition = models.CharField(max_length=60, help_text="The book's edition when it was sent.")
    library = models.CharField(max_length=25, choices=Library.choices)
    sent_on = models.DateField()
    proof = models.CharField(max_length=300, help_text="How it went and its reference: Speed Post EA123456789IN.")
    proof_file = models.FileField(upload_to="content/legal-deposits/", blank=True, help_text="A scan or photo.")
    erp_delivery_note = models.CharField(max_length=60, blank=True, help_text="ERPNext's delivery note, once made.")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created = models.DateTimeField(default=timezone.now)

    class Meta:
        default_permissions = ("view", "add")
        ordering = ["-sent_on", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["book", "edition", "library"],
                name="one_deposit_per_library",
                violation_error_message="This library has this edition already.",
            )
        ]

    def __str__(self):
        return f"Legal deposit #{self.pk}"

    @classmethod
    def missing(cls, books):
        """{book id: [the libraries without its current edition]} for the books given, in one query."""
        books = list(books)
        sent = set(cls.objects.filter(book__in=books).values_list("book_id", "edition", "library"))
        return {
            book.pk: [library for library in cls.Library.values if (book.pk, book.edition, library) not in sent]
            for book in books
        }
