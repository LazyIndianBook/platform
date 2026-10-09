from collections import defaultdict
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from insights.jobs import history, seasons_around, week_index
from insights.models import Forecast, ForecastRun

WEEKS = 4


class Command(BaseCommand):
    help = (
        "The monthly review in season (insights/README.md): for each title, each of the last four complete weeks' "
        "forecast (the last one made before the week began) beside the copies sold and the seasonal naive, with the "
        "WAPE of both. A method that loses to the naive is retired."
    )

    def handle(self, **options):
        today = timezone.localdate()
        forecasts = Forecast.objects.filter(  # a week is complete once 7 days from its start are over
            district=None,
            run__status=ForecastRun.Status.DONE,
            week_start__gte=today - timedelta(days=7 * WEEKS + 6),
            week_start__lte=today - timedelta(days=7),
        ).select_related("run", "product__subject")
        made = {}  # (product, week): the forecast of the last run made before the week began
        for forecast in forecasts.order_by("run__created"):
            if timezone.localdate(forecast.run.created) <= forecast.week_start:
                made[forecast.product, forecast.week_start] = forecast
        if not made:
            self.stdout.write("No forecast was made before any of the last four complete weeks.")
            return
        histories, titles = {}, defaultdict(list)
        for (product, start), forecast in sorted(made.items(), key=lambda pair: pair[0][1]):
            season = seasons_around(product.subject.board_id, product.subject.class_level_id, start)[0]
            if season is None:
                continue
            if season.pk not in histories:
                histories[season.pk] = history(season, {key[0].pk for key in made})
            sold = histories[season.pk][product.pk][0][week_index(season, start)]
            growth = forecast.run.params.get("titles", {}).get(product.slug, {}).get("growth") or 1.0
            titles[product].append((start, forecast.p50, sold, forecast.p50 / growth))
        self.stdout.write(f"{'title':40} {'week of':9} {'forecast':>9} {'sold':>6} {'naive':>7}")
        for product in sorted(titles, key=lambda product: product.title):
            for start, forecast, sold, naive in titles[product]:
                self.stdout.write(f"{product.title[:40]:40} {start:%d %b}    {forecast:9.1f} {sold:6.0f} {naive:7.1f}")
            if copies := sum(sold for _, _, sold, _ in titles[product]):
                method = sum(abs(sold - forecast) for _, forecast, sold, _ in titles[product]) / copies
                naive = sum(abs(sold - naive) for _, _, sold, naive in titles[product]) / copies
                self.stdout.write(f"{'':40} WAPE: forecast {method:.0%}, seasonal naive {naive:.0%}")
