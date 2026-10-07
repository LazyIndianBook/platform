"""The Refund and Shipping pages rewritten for the shop as built (pages/drafts/refunds.md and shipping.md). A page
is replaced only while it is still the first draft: text edited in the admin is left alone."""

from pathlib import Path

from django.db import migrations
from django.utils import timezone

DRAFTS = Path(__file__).resolve().parent.parent / "drafts"
VERSION = "2026-10-08.2"


def update_pages(apps, schema_editor):
    Page, HistoricalPage = apps.get_model("pages", "Page"), apps.get_model("pages", "HistoricalPage")
    for page in Page.objects.filter(slug__in=["refunds", "shipping"]):
        if HistoricalPage.objects.filter(id=page.id).count() != 1:
            continue  # edited since the first draft
        title, body = (DRAFTS / f"{page.slug}.md").read_text().split("\n", 1)
        page.title, page.body_md, page.version = title.removeprefix("# "), body.strip(), VERSION
        page.save()
        HistoricalPage.objects.create(
            id=page.id,
            slug=page.slug,
            title=page.title,
            body_md=page.body_md,
            version=page.version,
            updated=page.updated,
            history_date=timezone.now(),
            history_type="~",
            history_change_reason="the shop's rules",
        )


class Migration(migrations.Migration):
    dependencies = [("pages", "0002_legal_pages")]
    operations = [migrations.RunPython(update_pages, migrations.RunPython.noop)]
