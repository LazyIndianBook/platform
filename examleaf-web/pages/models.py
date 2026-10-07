from django.db import models
from django.urls import reverse
from simple_history.models import HistoricalRecords

# Each slug is also the page's URL (/privacy/, /terms/, …) and its URL name; see examleaf/urls.py.
SLUGS = ["privacy", "terms", "refunds", "shipping", "contact"]


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
        return reverse(self.slug)
