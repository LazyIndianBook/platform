"""The insights in the admin: every list and record opens with rows behind it, each run with its summary; only the
exam seasons and the print costs can be added."""

from decimal import Decimal

import pytest
from django.contrib import admin
from django.urls import reverse

from accounts.factories import UserFactory
from insights.jobs import codes, delivery, demand, fraud, learning, offers
from insights.models import ForecastRun, PrintCost
from shop.factories import ProductFactory

from .helpers import day_in, sell

pytestmark = pytest.mark.django_db


def test_every_insights_page_opens_with_rows_and_each_run_shows_its_summary(client, physics, seasons):
    before, last, this = seasons
    book = ProductFactory(subject=physics, price=Decimal(195))
    for season, copies in ((before, 10), (last, 20)):
        for index in (3, 10, 20):
            sell(book, day_in(season, index), copies)
    PrintCost.objects.create(product=book, unit_cost=60, salvage=5)
    today = day_in(this, 5)
    for job in (demand.backtest, demand.forecast_demand, demand.advise_print_run):
        job(today=today)
    for job in (learning.item_analysis, learning.cohorts, codes.code_activation, delivery.delivery_stats):
        job()
    offers.offer_effectiveness()
    fraud.fraud_rules()
    client.force_login(UserFactory(is_staff=True, is_superuser=True))
    for model in admin.site._registry:
        if model._meta.app_label != "insights":
            continue
        base = f"admin:insights_{model._meta.model_name}"
        assert client.get(reverse(f"{base}_changelist")).status_code == 200, model
        if row := model._default_manager.first():
            assert client.get(reverse(f"{base}_change", args=[row.pk])).status_code == 200, model
        can_add = model._meta.model_name in ("examseason", "printcost")
        assert client.get(reverse(f"{base}_add")).status_code == (200 if can_add else 403), model
    for kind, heading in (
        ("forecast", "P50 (copies to the exam)"),
        ("backtest", "beats the naive"),
        ("print_run", "reprint at"),
    ):
        run = ForecastRun.objects.get(kind=kind)
        page = client.get(reverse("admin:insights_forecastrun_change", args=[run.pk])).content.decode()
        assert heading in page and book.title in page, kind
