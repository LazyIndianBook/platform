from django import template
from django.utils.safestring import mark_safe

from content.templatetags.markdown import render
from pages.models import PLACEHOLDER

register = template.Library()


@register.filter
def page_html(text):
    """A page's Markdown as HTML, with each [placeholder] still to be filled in marked (yellow), so that none goes
    unnoticed into a live policy."""
    html = PLACEHOLDER.sub(lambda m: f'<mark class="placeholder">{m.group()}</mark>', render(text or ""))
    return mark_safe(html)
