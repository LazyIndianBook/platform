from django.conf import settings
from django.db import models
from django.utils import timezone
from model_utils import Choices
from model_utils.models import StatusModel, TimeStampedModel

NOTES_MAX_LENGTH = (
    2000  # characters of "what to revise", in the form and in the API (the text is read back on every page)
)


class Attempt(TimeStampedModel):
    """A student's own record of sitting a paper, marked against the solutions."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="attempts")
    paper = models.ForeignKey("content.Paper", on_delete=models.CASCADE, related_name="attempts")
    date = models.DateField(default=timezone.localdate)
    marks_obtained = models.DecimalField(max_digits=5, decimal_places=1)
    time_taken_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    notes = models.TextField("what to revise", blank=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.user} {self.paper} {self.marks_obtained}"

    @property
    def percent(self):
        return round(100 * float(self.marks_obtained) / self.paper.full_marks)


class AnswerSheetUpload(StatusModel, TimeStampedModel):
    """A photographed answer sheet for AI checking (planned). No grading logic yet."""

    STATUS = Choices("pending", "processing", "checked", "failed")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="answer_sheets")
    paper = models.ForeignKey("content.Paper", on_delete=models.CASCADE, related_name="answer_sheets")
    image = models.ImageField(upload_to="answer-sheets/%Y/%m/")
    result_json = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"{self.user} {self.paper} ({self.status})"
