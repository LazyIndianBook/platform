from datetime import date

from django.core.management.base import BaseCommand

from insights.jobs import codes, delivery, demand, fraud, learning, offers
from insights.models import ForecastRun

JOBS = {  # in the night's order (settings.CELERY_BEAT_SCHEDULE)
    "backtest": demand.backtest,
    "forecast_demand": demand.forecast_demand,
    "advise_print_run": demand.advise_print_run,
    "item_analysis": learning.item_analysis,
    "cohorts": learning.cohorts,
    "code_activation": codes.code_activation,
    "delivery_stats": delivery.delivery_stats,
    "offer_effectiveness": offers.offer_effectiveness,
    "fraud_rules": fraud.fraud_rules,
}


class Command(BaseCommand):
    help = (
        "Run an insights job now, as its nightly task does, or all of them in the night's order (insights/README.md). "
        "--date works out the numbers as on another day, to see what a forecast would have said then."
    )

    def add_arguments(self, parser):
        parser.add_argument("job", choices=[*JOBS, "all"])
        parser.add_argument("--date", type=date.fromisoformat, help="YYYY-MM-DD (default: today)")

    def handle(self, job, date, **options):
        for name in JOBS if job == "all" else [job]:
            result = JOBS[name](today=date)
            if isinstance(result, ForecastRun):
                said = f"run #{result.pk} {result.get_status_display()}. {result.notes}".strip()
            else:
                said = f"{result} {'signals new or grown' if name == 'fraud_rules' else 'rows'}"
            self.stdout.write(f"{name}: {said}")
