from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from content.models import Paper


class Command(BaseCommand):
    help = "Write every paper's QR code (its /s/<code>/ address under SITE_URL) as <CODE>.png and <CODE>.svg."

    def add_arguments(self, parser):
        parser.add_argument("--out", required=True, help="output folder")
        parser.add_argument("--force", action="store_true", help="write the codes even if SITE_URL is not a public https address")

    def handle(self, out, force, **options):
        site = urlparse(settings.SITE_URL)
        if not force and (site.scheme != "https" or site.hostname in ("localhost", "127.0.0.1")):
            raise CommandError(f"SITE_URL is {settings.SITE_URL}: codes printed with it would not work. Set the real https "
                               "address (or pass --force for a test run).")
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)
        papers = Paper.objects.all()
        for paper in papers:
            for image_format in ("png", "svg"):
                (out / f"{paper.code}.{image_format}").write_bytes(paper.qr_image(image_format))
        self.stdout.write(f"{len(papers)} QR codes (PNG and SVG) written to {out}; they encode {settings.SITE_URL}/s/<code>/")
