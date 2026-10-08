import re

from django.db import models
from simple_history.models import HistoricalRecords

# Each slug is also the page's URL on the website (/privacy/, /terms/, …).
SLUGS = ["privacy", "terms", "refunds", "shipping", "contact"]
# The drafts hold [places to fill in] (address, GSTIN, phone, Grievance Officer, delivery times ...): a [word in square
# brackets] that is not the text of a Markdown link, [text](url).
PLACEHOLDER = re.compile(r"\[[^\]\n]+\](?!\()")


class Page(models.Model):
    """A legal or policy page (Razorpay and the app stores ask for these), written in Markdown and edited in the
    admin; every edit is kept (History button)."""

    slug = models.SlugField(unique=True, choices=[(s, s) for s in SLUGS])
    title = models.CharField(max_length=120)
    body_md = models.TextField("text (Markdown)")
    version = models.CharField(
        max_length=20,
        help_text="Change it (e.g. to today's date) when the meaning changes. Consent records keep the "
        "privacy policy's version, and the History button shows the text of every version.",
    )
    updated = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return f"/{self.slug}/"  # the website's page (examleaf-frontend)

    @property
    def placeholders(self):
        """The [placeholders] still in the text: none may be left when the shop opens."""
        return PLACEHOLDER.findall(self.body_md)
