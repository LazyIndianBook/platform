"""The first drafts of the legal pages, from pages/drafts/<slug>.md (first line "# Title"). Later edits are made in
the admin; this migration only creates pages that do not exist yet."""

from pathlib import Path

from django.db import migrations
from django.utils import timezone

DRAFTS = Path(__file__).resolve().parent.parent / "drafts"


def create_pages(apps, schema_editor):
    Page, HistoricalPage = apps.get_model("pages", "Page"), apps.get_model("pages", "HistoricalPage")
    for slug in ["privacy", "terms", "refunds", "shipping", "contact"]:
        title, body = (DRAFTS / f"{slug}.md").read_text().split("\n", 1)
        page, created = Page.objects.get_or_create(
            slug=slug, defaults={"title": title.removeprefix("# "), "body_md": body.strip(), "version": "2026-10-08"}
        )
        if created:  # the first version in the page's history too (signals do not run in migrations)
            HistoricalPage.objects.create(
                id=page.id,
                slug=slug,
                title=page.title,
                body_md=page.body_md,
                version=page.version,
                updated=page.updated,
                history_date=timezone.now(),
                history_type="+",
                history_change_reason="first draft",
            )


class Migration(migrations.Migration):
    dependencies = [("pages", "0001_page")]
    operations = [migrations.RunPython(create_pages, migrations.RunPython.noop)]
