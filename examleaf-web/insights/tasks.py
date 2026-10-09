"""The insights jobs as Celery tasks, one each, at night from 01:00 (settings.CELERY_BEAT_SCHEDULE). A failure is
tried again once, ten minutes later, and then raised, so that Sentry reports it; a forecast run's row says "failed"
with the error (RUNBOOK.md, "An insights job failed")."""

from celery import shared_task

from examleaf.celery import LONG_TASK, single_run

from .jobs import codes, delivery, demand, fraud, learning, offers

ONCE_MORE = {"autoretry_for": (Exception,), "max_retries": 1, "default_retry_delay": 600, **LONG_TASK}


@shared_task(**ONCE_MORE)
def backtest():
    return demand.backtest().pk


@shared_task(**ONCE_MORE)
def forecast_demand():
    return demand.forecast_demand().pk


@shared_task(**ONCE_MORE)
def advise_print_run():
    return demand.advise_print_run().pk


@shared_task(**ONCE_MORE)
def item_analysis():
    return learning.item_analysis()


@shared_task(**ONCE_MORE)
def cohorts():
    return learning.cohorts()


@shared_task(**ONCE_MORE)
def code_activation():
    return codes.code_activation()


@shared_task(**ONCE_MORE)
def delivery_stats():
    return delivery.delivery_stats()


@shared_task(**ONCE_MORE)
def offer_effectiveness():
    return offers.offer_effectiveness()


@shared_task(**ONCE_MORE)
@single_run(LONG_TASK["time_limit"])
def fraud_rules():
    """The fraud rules, then the night's email (fraud signals and print runs to act on)."""
    return fraud.fraud_rules()
