from django.conf import settings
from django.db import models
from django.utils.functional import cached_property
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

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return f"/books/{self.slug}/"  # the website's page (examleaf-frontend)

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

    def qr_image(self, image_format="png"):
        return make_qr_code_image(self.landing_url(), QRCodeOptions(size=10, border=4, image_format=image_format))


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

    def __str__(self):
        return f"Solution {self.question}"
