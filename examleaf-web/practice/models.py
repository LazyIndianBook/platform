from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from model_utils import Choices
from model_utils.models import StatusModel, TimeStampedModel

NOTES_MAX_LENGTH = (
    2000  # characters of "what to revise", in the form and in the API (the text is read back on every page)
)
ATTEMPTS_PER_DAY = 20  # new attempts of one paper by one student in a day (L12): plenty to use, too few to fill disks


def check_can_save(user, paper, new):
    """What the website's form and the API check before an attempt is saved: the parent's consent where it must be
    verified (M9), and at most ATTEMPTS_PER_DAY new attempts of a paper a day (L12)."""
    if user.consent_pending:
        raise ValidationError(
            "Your parent or guardian has not confirmed your account yet: marks can be saved once they have "
            "(see My account)."
        )
    if new and user.attempts.filter(paper=paper, created__date=timezone.localdate()).count() >= ATTEMPTS_PER_DAY:
        raise ValidationError(f"At most {ATTEMPTS_PER_DAY} attempts of one paper can be saved in a day: try tomorrow.")


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
        permissions = [("export_attempt", "Can export attempts")]  # the admin's CSV export (ADMIN role)

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
