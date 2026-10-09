"""The minimum cell size (plan 5.16; research lms 5.8, b2b 2.2 and 4.6): a cell of a table that counts fewer than k
people or orders is not shown, so that a table never points at a few of them. One helper, used by every report:
`apply()` takes a row, the count the cell stands on and the measures that hold numbers, and answers the row with those
measures empty and `hidden: true, under: k` when the count is under the minimum (`hidden: false, under: null`
otherwise). The console writes "fewer than k" for a hidden row; an export writes the same words.

Two minimums, both settings (settings.py, DEPLOYMENT.md): `INSIGHTS_MIN_CELL` (10) for the tables of districts, PIN
codes, states, schools, cohorts and searches, and `INSIGHTS_MIN_CELL_CLASS` (5) for a class's or a chapter's learners
(the course health). Neither may be set under 5 (insights/checks.py).

What it protects: a table never shows a small cell. It is not statistical disclosure control: a reader who subtracts
the cells of one table from the total of another can still work out a hidden one, which is why no report here answers
a total that includes the cells it hides."""

from django.conf import settings

PLACE = "place"  # districts, PIN codes, states, schools, cohorts, searches
CLASS = "class"  # a class's or a chapter's learners


def minimum(kind=PLACE):
    """The least count a cell of this kind of table may stand on."""
    return settings.INSIGHTS_MIN_CELL_CLASS if kind == CLASS else settings.INSIGHTS_MIN_CELL


def is_hidden(count, kind=PLACE):
    """Whether a cell standing on `count` is under the minimum: some, but fewer than k (a cell of nobody shows no one,
    so a day with no learner says 0; a count of None is hidden: nothing is known of it)."""
    return count is None or 0 < count < minimum(kind)


def apply(row, count, measures, kind=PLACE):
    """`row` with `hidden` and `under`; when `count` is under the minimum, every name in `measures` emptied (None)."""
    if not is_hidden(count, kind):
        return {**row, "hidden": False, "under": None}
    return {**row, **dict.fromkeys(measures), "hidden": True, "under": minimum(kind)}


def words(row):
    """What a hidden row says in a file or a sentence: "fewer than 10"."""
    return f"fewer than {row['under']}"
