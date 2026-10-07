from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from content.models import Paper


class Command(BaseCommand):
    help = "Write every paper's QR code (its /s/<code>/ address under SITE_URL) as <CODE>.png and <CODE>.svg."

    def add_arguments(self, parser):
        parser.add_argument("--out", required=True, help="output folder")

    def handle(self, out, **options):
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)
        papers = Paper.objects.all()
        for paper in papers:
            for image_format in ("png", "svg"):
                (out / f"{paper.code}.{image_format}").write_bytes(paper.qr_image(image_format))
        self.stdout.write(f"{len(papers)} QR codes (PNG and SVG) written to {out}; they encode {settings.SITE_URL}/s/<code>/")
