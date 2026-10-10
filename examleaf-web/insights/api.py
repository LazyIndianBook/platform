"""The insights for staff, under /api/v1/insights/ (API.md "Insights (staff)"), on the staff app's rules
(staff.api.StaffAppView: `staff.view_insights` to read, `staff.acknowledge_signal` to acknowledge a fraud signal; the
admin host only; refusals and acknowledgements in the audit log): the rows of each job's newest run or day. Every
answer says how its numbers were made (research-b2b-predictive.md 4.1): `method`, `data_as_of`, `backtest` (the newest
backtest of every title together, four weeks ahead; null where nothing is predicted) and `shown` (false while a
prediction has not beaten the seasonal naive: the panel then hides it or says so); each row has its `n`."""

from django.db import transaction
from django.db.models import Max
from django.urls import path
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers
from rest_framework.response import Response

from staff import audit
from staff.api import StaffAppView

from . import cells
from .jobs import fraud, latest
from .jobs.demand import SHOWN_HORIZON
from .models import (
    Backtest,
    ChapterStat,
    CodeActivationStat,
    CohortStat,
    DeliveryStat,
    Forecast,
    ForecastRun,
    FraudSignal,
    ItemStat,
    OfferStat,
    PrintRunAdvice,
)


class TitledSerializer(serializers.ModelSerializer):
    product = serializers.SlugRelatedField(slug_field="slug", read_only=True)
    title = serializers.CharField(source="product.title", read_only=True)


class ForecastSerializer(TitledSerializer):
    n = serializers.IntegerField(source="n_history", read_only=True)

    class Meta:
        model = Forecast
        fields = ["product", "title", "district", "week_start", "p10", "p50", "p90", "n"]


class PrintRunAdviceSerializer(TitledSerializer):
    n = serializers.IntegerField(source="n_history", read_only=True)

    class Meta:
        model = PrintRunAdvice
        fields = [
            *["product", "title", "net_price", "unit_cost", "salvage", "critical_ratio", "target_quantity", "supply"],
            *["recommended_quantity", "reprint_trigger_units", "weeks_of_cover", "projected_leftover", "level"],
            *["alert", "n"],
        ]


class BacktestSerializer(serializers.ModelSerializer):
    product = serializers.SlugRelatedField(slug_field="slug", read_only=True)  # null: every title together
    n = serializers.IntegerField(source="n_weeks", read_only=True)

    class Meta:
        model = Backtest
        fields = ["product", "horizon_weeks", "wape", "mase_vs_seasonal_naive", "shown", "n"]


class ItemStatSerializer(serializers.ModelSerializer):
    chapter = serializers.IntegerField(source="item.chapter_id", read_only=True)
    kind = serializers.CharField(source="item.kind", read_only=True)
    text = serializers.CharField(source="item.text", read_only=True)

    class Meta:
        model = ItemStat
        fields = ["item", "chapter", "kind", "text", "n", "p", "discrimination", "flags"]


class ChapterStatSerializer(serializers.ModelSerializer):
    number = serializers.IntegerField(source="chapter.number", read_only=True)
    title = serializers.CharField(source="chapter.title", read_only=True)
    subject = serializers.IntegerField(source="chapter.subject_id", read_only=True)
    n = serializers.IntegerField(source="n_learners", read_only=True)

    class Meta:
        model = ChapterStat
        fields = ["chapter", "subject", "number", "title", "mean_accuracy", "trend", "n"]


class CohortStatSerializer(serializers.ModelSerializer):
    """A cohort's week. A week of fewer than INSIGHTS_MIN_CELL learners shows its size and no shares (`hidden`)."""

    hidden = serializers.SerializerMethodField(help_text="true: too few learners to show the shares (see `under`)")
    under = serializers.SerializerMethodField(help_text="the minimum cell a hidden row is under; null when shown")

    class Meta:
        model = CohortStat
        fields = ["cohort_month", "source", "week_index", "active_share", "churned_share", "n", "hidden", "under"]

    def get_hidden(self, stat) -> bool:
        return cells.is_hidden(stat.n)

    def get_under(self, stat) -> int | None:
        return cells.minimum() if cells.is_hidden(stat.n) else None

    def to_representation(self, stat):
        data = super().to_representation(stat)
        if data["hidden"]:
            data["active_share"] = data["churned_share"] = None
        return data


class CodeActivationSerializer(serializers.ModelSerializer):
    """A batch's redemptions, in all (`district` null) and by district. A district under INSIGHTS_MIN_CELL redemptions
    is `hidden`: no counts."""

    n = serializers.IntegerField(source="redeemed", read_only=True)
    hidden = serializers.SerializerMethodField(help_text="true: too few redemptions to show the counts (see `under`)")
    under = serializers.SerializerMethodField(help_text="the minimum cell a hidden row is under; null when shown")

    class Meta:
        model = CodeActivationStat
        fields = ["batch", "district", "printed", "redeemed", "redeemed_7d", "n", "hidden", "under"]

    def get_hidden(self, stat) -> bool:
        return stat.district is not None and cells.is_hidden(stat.redeemed)

    def get_under(self, stat) -> int | None:
        return cells.minimum() if self.get_hidden(stat) else None

    def to_representation(self, stat):
        data = super().to_representation(stat)
        if data["hidden"]:
            data["redeemed"] = data["redeemed_7d"] = data["n"] = None
        return data


class DeliveryStatSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryStat
        fields = ["courier", "district", "median_days", "p90_days", "n"]


class FraudSignalSerializer(serializers.ModelSerializer):
    label = serializers.CharField(source="get_kind_display", read_only=True)
    n = serializers.IntegerField(source="count", read_only=True)

    class Meta:
        model = FraudSignal
        fields = [
            *["id", "kind", "label", "subject", "window_start", "window_end", "details", "created", "acknowledged_at"],
            "n",
        ]


class OfferStatSerializer(serializers.ModelSerializer):
    coupon = serializers.SlugRelatedField(slug_field="code", read_only=True)
    offer = serializers.SlugRelatedField(slug_field="name", read_only=True)
    n = serializers.IntegerField(source="orders", read_only=True)

    class Meta:
        model = OfferStat
        fields = [
            *["coupon", "offer", "period_start", "period_end", "orders", "revenue", "discount_cost", "period_orders"],
            *["baseline_orders", "baseline_revenue", "interval_low", "interval_high", "note", "n"],
        ]


TIME = serializers.DateTimeField()  # the API's times: the Indian offset, as the serializers give them


def backtest_summary():
    """The newest backtest of every title together, SHOWN_HORIZON weeks ahead, or None."""
    record = latest(ForecastRun.Kind.BACKTEST)
    row = record and record.backtests.filter(product=None, horizon_weeks=SHOWN_HORIZON).first()
    if not row:
        return None
    fields = ["horizon_weeks", "wape", "mase_vs_seasonal_naive", "shown", "n_weeks"]
    return {**{name: getattr(row, name) for name in fields}, "data_as_of": TIME.to_representation(record.data_as_of)}


class InsightList(StaffAppView, generics.ListAPIView):
    """The rows of a job's newest run (`kind` and `rows`: a ForecastRun's) or newest day (a stat model's)."""

    permissions = {"GET": "staff.view_insights"}
    filter_backends = []  # the few filters are read in get_queryset (API.md)
    kind = rows = None  # a predictive job: its ForecastRun kind, and the run's related name for its rows
    method = ""  # a stat job: how its rows are made
    predicts = False

    def get_queryset(self):
        model = self.serializer_class.Meta.model
        if self.kind:
            self.record = latest(self.kind)
            self.as_of = self.record and self.record.data_as_of
            return getattr(self.record, self.rows).all() if self.record else model.objects.none()
        self.as_of = model.objects.aggregate(newest=Max("computed_at"))["newest"]
        return model.objects.filter(computed_at=self.as_of)

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        backtest = backtest_summary() if self.predicts else None
        about = {
            "method": self.record.method if self.kind and self.record else self.method,
            "data_as_of": self.as_of and TIME.to_representation(self.as_of),
            "backtest": backtest,
            "shown": bool(backtest and backtest["shown"]) if self.predicts else True,
        }
        response.data = {**about, **response.data}
        return response


class ForecastList(InsightList):
    """Weekly forecasts of each title: every district together, or `?district=all` (each district) or a district's
    name; `?product=<slug>` for one title."""

    serializer_class, kind, rows, predicts = ForecastSerializer, ForecastRun.Kind.FORECAST, "forecasts", True

    def get_queryset(self):
        rows = super().get_queryset().select_related("product")
        district = self.request.query_params.get("district")
        if not district:
            rows = rows.filter(district=None)
        elif district == "all":
            rows = rows.exclude(district=None)
        else:
            rows = rows.filter(district=district)
        if product := self.request.query_params.get("product"):
            rows = rows.filter(product__slug=product)
        return rows


class PrintRunList(InsightList):
    serializer_class, kind, rows, predicts = PrintRunAdviceSerializer, ForecastRun.Kind.PRINT_RUN, "advice", True

    def get_queryset(self):
        return super().get_queryset().select_related("product")


class BacktestList(InsightList):
    serializer_class, kind, rows, predicts = BacktestSerializer, ForecastRun.Kind.BACKTEST, "backtests", True

    def get_queryset(self):
        return super().get_queryset().select_related("product")


class ItemStatList(InsightList):
    """Today's item analysis (`?chapter=<id>` for one chapter's items)."""

    serializer_class = ItemStatSerializer
    method = "classical item analysis of first attempts: p, corrected item-total point-biserial, TIMSS's flags (n ≥ 30)"

    def get_queryset(self):
        rows = ItemStat.objects.filter(run_date=ItemStat.objects.aggregate(day=Max("run_date"))["day"])
        self.as_of = rows.aggregate(newest=Max("computed_at"))["newest"]
        if chapter := self.request.query_params.get("chapter"):
            rows = rows.filter(item__chapter=chapter) if chapter.isdigit() else rows.none()
        return rows.select_related("item")


class ChapterStatList(InsightList):
    serializer_class = ChapterStatSerializer
    method = "mean of learners' shares right on first attempts; trend: the last 4 weeks less the 4 before (n ≥ 5)"

    def get_queryset(self):
        return super().get_queryset().select_related("chapter")


class CohortList(InsightList):
    serializer_class = CohortStatSerializer
    method = "share active each week since the course opened, and gone quiet 14 days, while the exam is ahead (n ≥ 10)"


class CodeActivationList(InsightList):
    serializer_class = CodeActivationSerializer
    method = "book codes redeemed per batch, and per district of the redeemer's order (under 5: other districts)"


class DeliveryList(InsightList):
    serializer_class = DeliveryStatSerializer
    method = "days from shipped to delivered over the last year, per courier and district: median and P90"


class FraudSignalList(InsightList):
    """The fraud rules' signals, newest first (`?open=1`: those not acknowledged yet)."""

    serializer_class = FraudSignalSerializer
    method = (
        "rules: failed book codes per account, address, device and hour; codes redeemed before their batch was "
        "dispatched; codes per account; accounts per code; shared contacts"
    )

    def get_queryset(self):
        rows = FraudSignal.objects.all()
        self.as_of = rows.aggregate(newest=Max("created"))["newest"]
        return rows.filter(acknowledged_at=None) if self.request.query_params.get("open") else rows


class FraudSignalAcknowledgeView(StaffAppView, generics.GenericAPIView):
    """Looked at and handled: the signal leaves `?open=1`. Once (again: the same answer); the audit log keeps who."""

    permissions = {"POST": "staff.acknowledge_signal"}
    queryset = FraudSignal.objects.all()
    serializer_class = FraudSignalSerializer

    @extend_schema(request=None, responses=FraudSignalSerializer)
    def post(self, request, *args, **kwargs):
        signal, user = self.get_object(), self.human()
        with transaction.atomic():
            done = FraudSignal.objects.filter(pk=signal.pk, acknowledged_at=None).update(
                acknowledged_at=timezone.now(), acknowledged_by=user.pk
            )
            if done:
                audit.record(
                    "insights.signal_acknowledged", request=request, target=signal, details={"kind": signal.kind}
                )
            fraud.acknowledged(signal)  # its inbox item done
        signal.refresh_from_db()
        return Response(self.get_serializer(signal).data)


class OfferList(InsightList):
    serializer_class = OfferStatSerializer
    method = "orders while it ran ÷ the same weeks last season, 95 % interval (normal approximation); no winners"

    def get_queryset(self):
        return super().get_queryset().select_related("coupon", "offer")


urlpatterns = [  # under /api/v1/insights/ (api/urls.py)
    path("forecasts/", ForecastList.as_view(), name="insights-forecasts"),
    path("print-runs/", PrintRunList.as_view(), name="insights-print-runs"),
    path("backtests/", BacktestList.as_view(), name="insights-backtests"),
    path("item-stats/", ItemStatList.as_view(), name="insights-item-stats"),
    path("chapter-stats/", ChapterStatList.as_view(), name="insights-chapter-stats"),
    path("cohorts/", CohortList.as_view(), name="insights-cohorts"),
    path("code-activation/", CodeActivationList.as_view(), name="insights-code-activation"),
    path("delivery/", DeliveryList.as_view(), name="insights-delivery"),
    path("fraud-signals/", FraudSignalList.as_view(), name="insights-fraud-signals"),
    path(
        "fraud-signals/<int:pk>/acknowledge/",
        FraudSignalAcknowledgeView.as_view(),
        name="insights-fraud-signal-acknowledge",
    ),
    path("offers/", OfferList.as_view(), name="insights-offers"),
]
