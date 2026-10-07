"""{{ text|markdown }} — Markdown to HTML with markdown-it-py (tables on, raw HTML off).

$…$ and $$…$$ maths is set aside before parsing and put back verbatim (HTML-escaped, quotes included, because it can
land inside a link's href or title) for KaTeX in the browser, so Markdown never touches underscores, backslashes or
pipes inside formulas.
"""
import re
from functools import lru_cache
from html import escape

from django import template
from django.utils.safestring import mark_safe
from markdown_it import MarkdownIt

register = template.Library()
MATH = re.compile(r"\$\$.+?\$\$|\$[^$\n]+\$", re.S)
COMMENT = re.compile(r"<!--.*?-->", re.S)
SLOT = re.compile("\ue000(\\d+)\ue001")  # private-use characters: cannot occur in the content, so no text can fake a slot
NO_SLOT_CHARS = {0xE000: None, 0xE001: None}
MARKERS = [  # solution lines that get their own style
    ("<p><strong>Final answer:</strong>", '<p class="final"><strong>Final answer:</strong>'),
    ("<p><em>Also accepted:</em>", '<p class="also"><em>Also accepted:</em>'),
    ("<blockquote>\n<p><em>Diagram expected:</em>", '<blockquote class="diagram">\n<p><em>Diagram expected:</em>'),
]


def table_open(self, tokens, idx, options, env):
    """Wrap tables so they scroll sideways on a phone; a marking table (last column "Marks") gets class steps."""
    head = []
    for token in tokens[idx + 1:]:
        if token.type == "thead_close":
            break
        if token.type == "inline":
            head.append(token.content.strip("* ").lower())
    css = ' class="steps"' if head and head[-1] == "marks" else ""
    return f'<div class="table-scroll"><table{css}>\n'


md = MarkdownIt("commonmark", {"html": False}).enable("table")
md.add_render_rule("table_open", table_open)
md.add_render_rule("table_close", lambda self, tokens, idx, options, env: "</table></div>\n")


@lru_cache(maxsize=20000)  # ponytail: per-process cache of rendered text; the source text is the key
def render(text, inline=False):
    maths = []

    def stash(m):
        maths.append(m.group())
        return f"\ue000{len(maths) - 1}\ue001"

    source = MATH.sub(stash, COMMENT.sub("", text).translate(NO_SLOT_CHARS))
    html = md.renderInline(source) if inline else md.render(source)
    html = SLOT.sub(lambda m: escape(maths[int(m.group(1))]), html)
    for old, new in MARKERS:
        html = html.replace(old, new)
    return html


@register.filter
def markdown(text):
    return mark_safe(render(text or ""))


@register.filter
def markdown_inline(text):  # one line: no paragraphs or lists ("1. Answer any eight ..." stays a heading)
    return mark_safe(render(text or "", inline=True))


if __name__ == "__main__":  # quick self-check: python content/templatetags/markdown.py
    out = render("| Step | Marks |\n|---|---|\n| $\\mu = \\dfrac{|v_d|}{E}$, $a_1 * b_2$ | 1 |\n\n**Final answer:** $x<y$")
    assert '<table class="steps">' in out and "$\\mu = \\dfrac{|v_d|}{E}$" in out and "$a_1 * b_2$" in out, out
    assert render("1. Answer `1×8=8`", inline=True) == "1. Answer <code>1×8=8</code>"
    assert '<p class="final">' in out and "$x&lt;y$" in out and "<!--" not in render("<!-- note -->ok"), out
    print("ok")
