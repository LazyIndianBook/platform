"""Copy that pressures the buyer (plan 5.5; the CCPA's Guidelines for Prevention and Regulation of Dark Patterns, 2023,
whose 13 patterns staff.models.DARK_PATTERNS lists): the phrases of SHOP_DARK_PATTERN_PHRASES are refused in an offer's
name and banner and a coupon's description, whatever their case, apostrophes or spacing, each with the pattern it reads
as. "Limited time" passes only where an end is real: beside a date in the same text, or on an offer that ends on a
date (`dated`). The words a customer reads are checked where they are saved (the panel's API, its import, the
approvals that make or change a coupon or an offer), never only in the console."""

import re

from django.conf import settings
from django.core.exceptions import ValidationError

from staff.models import DARK_PATTERNS

PATTERNS = dict(DARK_PATTERNS)
WITH_A_DATE = {"limited time"}  # true beside a real end
MONTHS = "jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec"
DATE = re.compile(
    rf"\b(\d{{1,2}}(st|nd|rd|th)?\s+({MONTHS})[a-z]*|({MONTHS})[a-z]*\s+\d{{1,2}}(st|nd|rd|th)?\b|\d{{4}}-\d{{2}}-\d{{2}}"
    rf"|\d{{1,2}}[/.-]\d{{1,2}}([/.-]\d{{2,4}})?)",
    re.IGNORECASE,
)
CONTRACTIONS = {"don't": "do not", "won't": "will not", "you'll": "you will", "can't": "cannot"}


def normal(text):
    """Lower case, straight apostrophes, single spaces and contractions spelt out: "Don’t  miss" → "do not miss"."""
    text = " ".join(str(text or "").lower().replace("’", "'").replace("‘", "'").split())
    for short, long in CONTRACTIONS.items():
        text = re.sub(rf"(?<![\w']){re.escape(short)}(?![\w'])", long, text)
    return text


def found(text, dated=False):
    """[(phrase, pattern)] of SHOP_DARK_PATTERN_PHRASES in `text`, in the setting's order."""
    words = normal(text)
    hits = []
    for phrase, pattern in settings.SHOP_DARK_PATTERN_PHRASES.items():
        wanted = normal(phrase)
        if not re.search(rf"(?<![\w']){re.escape(wanted)}(?![\w'])", words):
            continue
        if wanted in WITH_A_DATE and (dated or DATE.search(str(text or ""))):
            continue
        hits.append((phrase, pattern))
    return hits


def message(phrase, pattern):
    advice = "say what is offered and the day it ends" if pattern == "false_urgency" else "say plainly what is offered"
    return (
        f"“{phrase}” reads as {PATTERNS.get(pattern, pattern).lower()}, a dark pattern the CCPA's 2023 guidelines "
        f"name: {advice}."
    )


def check(text, dated=False):
    """Raises ValidationError with one message per phrase found, naming its pattern; `dated`: the words belong to
    something that ends on a real date (an offer with an end), so "limited time" is true of it."""
    if hits := found(text, dated):
        raise ValidationError([message(phrase, pattern) for phrase, pattern in hits], code="dark_pattern")
