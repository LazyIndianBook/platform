"""Pictures drawn with Pillow for the web platform: the Open Graph image of a link preview (1200x630 JPEG, not WebP or
AVIF: not every crawler reads them), in a bundled font when static/fonts/og.ttf exists, else Pillow's own; and the
product pictures' sizes (queue_picture_sizes)."""

import io
import logging

from django.contrib.staticfiles import finders
from django.db import transaction
from pictures.conf import app_settings as pictures_settings
from pictures.tasks import process_picture_with_celery
from PIL import Image, ImageDraw, ImageFont, ImageOps

logger = logging.getLogger(__name__)

NIGHT, LEAF, PAPER = "#07122B", "#4CC265", "#FFFFFF"
OG_SIZE = (1200, 630)
MARGIN = 60


def font(size):
    path = finders.find("fonts/og.ttf")
    return ImageFont.truetype(path, size) if path else ImageFont.load_default(size)


def wrap(draw, text, face, width, max_lines=5):
    """The words of `text` in lines no wider than `width` pixels (at most max_lines)."""
    lines = []
    for word in text.split():
        if lines and draw.textlength(f"{lines[-1]} {word}", font=face) <= width:
            lines[-1] = f"{lines[-1]} {word}"
        else:
            lines.append(word)
    return lines[:max_lines]


def og_image(covers, title):
    """`covers` (Pillow images, may be none) fanned out on the right of the night colour, `title` on the left."""
    canvas = Image.new("RGB", OG_SIZE, NIGHT)
    draw = ImageDraw.Draw(canvas)
    height = 480 if len(covers) == 1 else 420
    scaled = [ImageOps.contain(cover.convert("RGB"), (OG_SIZE[0], height)) for cover in covers]
    step = round(scaled[0].width * 0.35) if scaled else 0
    left = OG_SIZE[0] - MARGIN - (scaled[0].width + step * (len(scaled) - 1)) if scaled else OG_SIZE[0]
    for index, cover in enumerate(scaled):
        canvas.paste(cover, (left + index * step, (OG_SIZE[1] - cover.height) // 2))
    draw.text((MARGIN, MARGIN + 20), "ExamLeaf", font=font(40), fill=LEAF)
    face = font(56)
    lines = wrap(draw, title, face, left - 2 * MARGIN)
    draw.multiline_text((MARGIN, MARGIN + 100), "\n".join(lines), font=face, fill=PAPER, spacing=14)
    buffer = io.BytesIO()
    canvas.save(buffer, "JPEG", quality=85, optimize=True)
    return buffer.getvalue()


def queue_picture_sizes(**work):
    """settings.PICTURES["PROCESSOR"]: django-pictures' Celery processor, queued once the transaction is committed, but
    with a broker that is down the AVIF and WebP sizes are made here and now (as emails and SMS are sent here), not a
    server error for the member of staff whose upload has been saved already."""

    def queue():
        try:
            process_picture_with_celery.apply_async(kwargs=work, queue=pictures_settings.QUEUE_NAME)
        except process_picture_with_celery.OperationalError:
            logger.exception("broker unavailable, making the picture sizes here")
            process_picture_with_celery.run(**work)

    transaction.on_commit(queue, robust=True)
