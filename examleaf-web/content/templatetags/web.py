import json
from functools import cache

from django import template
from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.serializers.json import DjangoJSONEncoder
from django.forms.utils import flatatt
from django.templatetags.static import static
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe

from accounts.forms import RequestLoginCodeForm
from content.management.commands.build_covers import FORMATS, WIDTHS
from content.models import Paper
from shop.templatetags.shop import inr

register = template.Library()


@cache  # the static files change only with a deployment
def _has_sizes(stem):
    return all(finders.find(f"{stem}-{width}.{extension}") for width in WIDTHS for extension in FORMATS)


@register.simple_tag
def static_cover(path, alt="", sizes="(min-width: 900px) 25vw, 50vw", **attrs):
    """A book cover of static/img/ ("img/physics.png") as a <picture>: its AVIF and WebP sizes (manage.py
    build_covers) when they exist, the PNG for the browsers that read neither. Keyword arguments become attributes of
    the <img>: fetchpriority="high" on the first cover of the page, loading="lazy" on the others."""
    stem = path.rsplit(".", 1)[0]
    sources = ""
    if _has_sizes(stem):
        srcsets = (
            (extension, ", ".join(f"{static(f'{stem}-{width}.{extension}')} {width}w" for width in WIDTHS), sizes)
            for extension in FORMATS
        )
        sources = format_html_join("", '<source type="image/{}" srcset="{}" sizes="{}">', srcsets)
    img = format_html('<img src="{}" alt="{}" width="480" height="678"{}>', static(path), alt, flatatt(attrs))
    return format_html("<picture>{}{}</picture>", sources, img)


@register.filter
def inr_short(value):
    """A display price without zero paise (components.md, .price): ₹299, but ₹718.20. Totals keep `inr`."""
    text = inr(value)
    return text.removesuffix(".00")


@register.simple_tag
def login_code_form():
    """The log-in page's mobile number box: allauth's code request form (posted to its own page), with Turnstile when
    it is on."""
    return RequestLoginCodeForm()


@register.simple_tag
def record_summary(user, latest=5):
    """My account's "My record" card: the average for each tier (as My record counts it; None without a paper of the
    tier) and the latest attempts."""
    attempts = list(user.attempts.select_related("paper"))
    averages = []
    for tier, label in Paper.Tier.choices:
        rows = [a.percent for a in attempts if a.paper.tier == tier]
        averages.append((label, len(rows), round(sum(rows) / len(rows)) if rows else None))
    return {"averages": averages, "latest": attempts[:latest], "count": len(attempts)}


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
