from django.conf import settings
from django.core.management.base import BaseCommand
from PIL import Image

from examleaf.images import og_image

COVERS = ["physics", "chemistry", "mathematics", "biology"]  # static/img/<name>.png, 480 px wide
WIDTHS = [320, 480]  # the website's <picture> sizes (examleaf-frontend, src/components/ui/cover.tsx)
FORMATS = {"avif": "AVIF", "webp": "WEBP"}


def build_covers(folder):
    """Each cover in AVIF and WebP, 320 and 480 px wide, next to its PNG: img/physics-320.avif, …"""
    for name in COVERS:
        with Image.open(folder / f"{name}.png") as image:
            image = image.convert("RGB")
            for width in WIDTHS:
                resized = image.resize((width, round(image.height * width / image.width)), Image.Resampling.LANCZOS)
                for extension, file_type in FORMATS.items():
                    resized.save(folder / f"{name}-{width}.{extension}", file_type)


def build_og_default(folder):
    """The website's link-preview picture (og:image of every page without its own): the four covers,
    img/og-default.jpg."""
    covers = [Image.open(folder / f"{name}.png") for name in COVERS]
    (folder / "og-default.jpg").write_bytes(og_image(covers, "Sample papers with free solutions"))


class Command(BaseCommand):
    help = (
        "Write the static images made from the covers in static/img/, which the website (examleaf-frontend) "
        "shows: the AVIF and WebP sizes of the book covers and the default Open Graph image. Run it after changing "
        "a cover and commit the files."
    )

    def handle(self, **options):
        folder = settings.BASE_DIR / "static" / "img"
        build_covers(folder)
        build_og_default(folder)
        self.stdout.write(f"Written to {folder}.")
