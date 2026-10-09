from django.conf import settings
from django.core.checks import Error, register

FLOOR = 5  # the least minimum cell a report may be set to (insights/cells.py)


@register()
def minimum_cells(app_configs, **kwargs):
    """The reports hide a cell standing on fewer than INSIGHTS_MIN_CELL (or, for a chapter's or a class's learners,
    INSIGHTS_MIN_CELL_CLASS) people or orders: set lower than FLOOR they would show a table of a handful of people,
    which the DPDP Act's rule on children's data (insights/README.md) does not allow. Run by `manage.py check` and
    `migrate`, so a server with such a value does not start."""
    return [
        Error(
            f"{name} is {getattr(settings, name)}: a report's cell may not stand on fewer than {FLOOR}.",
            hint=f"Set it to {FLOOR} or more (DEPLOYMENT.md, Insights).",
            id="insights.E001",
        )
        for name in ("INSIGHTS_MIN_CELL", "INSIGHTS_MIN_CELL_CLASS")
        if getattr(settings, name) < FLOOR
    ]
