import re

from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

# Each slug is also the page's URL on the website (/privacy/, /terms/, …).
SLUGS = ["privacy", "terms", "refunds", "shipping", "contact"]
# The drafts hold [places to fill in] (address, GSTIN, phone, Grievance Officer, delivery times ...): a [word in square
# brackets] that is not the text of a Markdown link, [text](url).
PLACEHOLDER = re.compile(r"\[[^\]\n]+\](?!\()")


class Page(models.Model):
    """A legal or policy page (Razorpay and the app stores ask for these), written in Markdown; every edit is kept
    (History button). The row is the version in force; a version published for a later day waits in `scheduled`
    until pages.versions.publish_due makes it so (the panel's policy versions: pages/versions.py)."""

    slug = models.SlugField(unique=True, choices=[(s, s) for s in SLUGS])
    title = models.CharField(max_length=120)
    body_md = models.TextField("text (Markdown)")
    version = models.CharField(
        max_length=20,
        help_text="Change it (e.g. to today's date) when the meaning changes. Consent records keep the "
        "privacy policy's version, and the History button shows the text of every version.",
    )
    updated = models.DateTimeField(auto_now=True)
    # Phase B: legal
    effective_from = models.DateField(
        default=timezone.localdate,
        blank=True,
        help_text="The day this version came into force (a new version: today, unless set).",
    )
    summary = models.CharField(max_length=200, blank=True, help_text="What this version changed, in a line.")
    scheduled = models.JSONField(
        null=True, blank=True, editable=False, help_text="A version published for a later day, until that day."
    )
    history = HistoricalRecords(excluded_fields=["scheduled"])

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        """A new version (its label changed) is in force from today unless its day was set with it; a correction
        within a version keeps the version's day."""
        before = Page.objects.filter(pk=self.pk).values("version", "effective_from").first() if self.pk else None
        new_version = before is not None and before["version"] != self.version
        if self.effective_from is None or (new_version and self.effective_from == before["effective_from"]):
            self.effective_from = before["effective_from"] if before and not new_version else timezone.localdate()
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return f"/{self.slug}/"  # the website's page (examleaf-frontend)

    @property
    def placeholders(self):
        """The [placeholders] still in the text: none may be left when the shop opens."""
        return PLACEHOLDER.findall(self.body_md)
