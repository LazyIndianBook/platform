"""The commands and the nightly tasks: every job runs on an empty database; a failure is kept and raised; the review."""

from datetime import timedelta
from io import StringIO

import pytest
from celery import current_app
from django.core.management import call_command
from django.utils import timezone

from insights import tasks
from insights.jobs import demand
from insights.models import ExamSeason, ForecastRun
from shop.factories import ProductFactory

from .helpers import at_noon, day_in, sell

pytestmark = pytest.mark.django_db


def test_every_job_and_the_review_run_on_an_empty_database():
    out = StringIO()
    call_command("insights_run", "all", stdout=out)
    lines = out.getvalue().splitlines()
    assert [line.split(":")[0] for line in lines] == [
        *["backtest", "forecast_demand", "advise_print_run", "item_analysis", "cohorts", "code_activation"],
        *["delivery_stats", "offer_effectiveness", "fraud_rules"],
    ]
    assert lines[1].startswith("forecast_demand: run #") and "nothing to work on" in lines[1]
    assert lines[2].startswith("advise_print_run: run #")  # (its number: PostgreSQL's sequences outlive a test)
    assert lines[2].endswith(" nothing to work on. No demand forecast yet.")
    assert lines[-1] == "fraud_rules: 0 signals new or grown"
    out = StringIO()
    call_command("insights_review", stdout=out)
    assert out.getvalue() == "No forecast was made before any of the last four complete weeks.\n"


def test_the_jobs_are_scheduled_at_night_one_task_each(settings):
    entries = [entry for name, entry in settings.CELERY_BEAT_SCHEDULE.items() if name.startswith("insights-")]
    assert len({entry["task"] for entry in entries}) == len(entries) == 9
    assert all(entry["task"] in current_app.tasks for entry in entries)
    assert all(entry["schedule"].hour <= {1, 2, 3} for entry in entries)
    assert all(entry["task"] != "insights.tasks.fraud_rules" or entry["schedule"].hour == {3} for entry in entries)


def test_a_task_that_fails_is_tried_once_more_and_its_run_says_why(monkeypatch):
    assert ForecastRun.objects.get(pk=tasks.forecast_demand.delay().get()).status == ForecastRun.Status.SKIPPED
    calls = []

    def broken():
        calls.append(1)
        raise RuntimeError("the database went away")

    monkeypatch.setattr(demand, "printed_books", broken)
    with pytest.raises(RuntimeError):
        tasks.forecast_demand.apply(throw=False)  # (inline: Celery's retry, which a worker makes 10 minutes later)
    assert len(calls) == 2  # retried once, then raised for Sentry
    failed = ForecastRun.objects.filter(status=ForecastRun.Status.FAILED)
    assert [run.notes for run in failed] == ["RuntimeError: the database went away"] * 2
    assert not failed.first().forecasts.exists()


def test_the_review_sets_each_weeks_forecast_beside_what_sold_and_the_naive(physics):
    today = timezone.localdate()
    exam = today + timedelta(weeks=20)  # this week is the season's 33rd (index 32)
    this, last = (
        ExamSeason.objects.create(board=physics.board, class_level=physics.class_level, academic_year=year,
                                  exam_start=start, exam_end=start + timedelta(days=30))
        for year, start in (("2026-27", exam), ("2025-26", exam - timedelta(weeks=52)))
    )  # fmt: skip
    book = ProductFactory(subject=physics, title="Physics Sample Papers")
    for index in range(27, 32):
        sell(book, day_in(last, index), 10)
    made = today - timedelta(weeks=5)  # five weeks ago: before the last four complete weeks began
    run = demand.forecast_demand(today=made)
    ForecastRun.objects.filter(pk=run.pk).update(created=at_noon(made))
    for index, copies in ((28, 12), (29, 8), (30, 10), (31, 10)):
        sell(book, day_in(this, index), copies)
    out = StringIO()
    call_command("insights_review", stdout=out)
    lines = out.getvalue().splitlines()
    assert lines[0].split() == ["title", "week", "of", "forecast", "sold", "naive"]
    assert [line.split()[-3:] for line in lines[1:5]] == [["10.0", "12", "10.0"], ["10.0", "8", "10.0"]] + [
        ["10.0", "10", "10.0"]
    ] * 2
    assert lines[5].split()[-5:] == ["forecast", "10%,", "seasonal", "naive", "10%"]
