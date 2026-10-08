from django.conf import settings
from django.core.management.base import BaseCommand
from PIL import Image

from examleaf.images import app_icon, og_image

COVERS = ["physics", "chemistry", "mathematics", "biology"]  # static/img/<name>.png, 480 px wide
WIDTHS = [240, 320, 480]  # 240: the home page's fanned covers on a phone (104 px wide, so 208 px on a 2x screen)
FORMATS = {"avif": "AVIF", "webp": "WEBP"}


def build_covers(folder):
    """Each cover in AVIF and WebP, 240, 320 and 480 px wide, next to its PNG: img/physics-240.avif, …"""
    for name in COVERS:
        with Image.open(folder / f"{name}.png") as image:
            image = image.convert("RGB")
            for width in WIDTHS:
                resized = image.resize((width, round(image.height * width / image.width)), Image.Resampling.LANCZOS)
                for extension, file_type in FORMATS.items():
                    resized.save(folder / f"{name}-{width}.{extension}", file_type)


def build_og_default(folder):
    """The site's link-preview picture (og:image of every page without its own): the four covers, img/og-default.jpg."""
    covers = [Image.open(folder / f"{name}.png") for name in COVERS]
    (folder / "og-default.jpg").write_bytes(og_image(covers, "Sample papers with free solutions"))


def build_icons(folder):
    """The web app manifest's icons (examleaf.views.manifest): img/icon-192.png and img/icon-512.png."""
    for size in (192, 512):
        (folder / f"icon-{size}.png").write_bytes(app_icon(size))


class Command(BaseCommand):
    help = (
        "Write the static images made from the covers in static/img/: the AVIF and WebP sizes of the book covers "
        "({% static_cover %} on the home and book pages), the default Open Graph image and the app icons. Run it "
        "after changing a cover and commit the files."
    )

    def handle(self, **options):
        folder = settings.BASE_DIR / "static" / "img"
        build_covers(folder)
        build_og_default(folder)
        build_icons(folder)
        self.stdout.write(f"Written to {folder}.")
