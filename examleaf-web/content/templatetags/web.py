import json
from functools import cache

from django import template
from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.serializers.json import DjangoJSONEncoder
from django.templatetags.static import static
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe

from content.management.commands.build_covers import FORMATS, WIDTHS

register = template.Library()


@cache  # the static files change only with a deployment
def _has_sizes(stem):
    return all(finders.find(f"{stem}-{width}.{extension}") for width in WIDTHS for extension in FORMATS)


@register.simple_tag
def static_cover(path, alt="", sizes="(min-width: 900px) 25vw, 50vw"):
    """A book cover of static/img/ ("img/physics.png") as a <picture>: its AVIF and WebP sizes (manage.py
    build_covers) when they exist, the PNG for the browsers that read neither."""
    stem = path.rsplit(".", 1)[0]
    sources = ""
    if _has_sizes(stem):
        srcsets = (
            (extension, ", ".join(f"{static(f'{stem}-{width}.{extension}')} {width}w" for width in WIDTHS), sizes)
            for extension in FORMATS
        )
        sources = format_html_join("", '<source type="image/{}" srcset="{}" sizes="{}">', srcsets)
    img = format_html('<img src="{}" alt="{}" width="480" height="678">', static(path), alt)
    return format_html("<picture>{}{}</picture>", sources, img)


@register.simple_tag
def jsonld(data):
    """`data` as a JSON-LD block for search engines (a data block: the CSP's script-src does not apply). Its JSON is not
    HTML-escaped, so <, > and & are written as JSON escapes: a title holding "</script>" cannot end the block."""
    text = json.dumps(data, ensure_ascii=False, cls=DjangoJSONEncoder)
    text = text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return mark_safe(f'<script type="application/ld+json">{text}</script>')


@register.filter
def absolute(url):
    """A URL of this site with SITE_URL in front (link previews and JSON-LD need whole URLs); whole URLs unchanged."""
    return url if url.startswith(("https://", "http://")) else settings.SITE_URL + url
