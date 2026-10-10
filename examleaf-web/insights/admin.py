"""Insights in the admin: what the nightly jobs worked out, read-only, with a summary of each run, and the action that
acknowledges a fraud signal. Staff enter two things here: the exam seasons and the print costs."""

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db.models import Count, Sum
from django.utils import timezone
from django.utils.html import format_html, format_html_join

from accounts.admin import ReadOnlyAdmin

from .models import (
    AccountScore,
    Backtest,
    ChapterStat,
    CodeActivationStat,
    CohortStat,
    CourseHealthStat,
    DeliveryStat,
    ExamSeason,
    Forecast,
    ForecastRun,
    FraudSignal,
    ItemStat,
    OfferStat,
    PrintCost,
    PrintRunAdvice,
    RedemptionAttempt,
)


@admin.register(ExamSeason)
class ExamSeasonAdmin(admin.ModelAdmin):
    list_display = ["__str__", "exam_start", "exam_end"]
    list_filter = ["board", "class_level"]


@admin.register(PrintCost)
class PrintCostAdmin(admin.ModelAdmin):
    list_display = ["product", "unit_cost", "salvage", "on_order", "lead_time_weeks", "modified"]
    list_select_related = ["product"]


def table(header, rows):
    """A small HTML table of the run's numbers."""
    head = format_html_join("", "<th>{}</th>", ((name,) for name in header))
    lines = [format_html_join("", "<td>{}</td>", ((cell,) for cell in row)) for row in rows]
    body = format_html_join("", "<tr>{}</tr>", ((line,) for line in lines))
    return format_html("<table><thead><tr>{}</tr></thead><tbody>{}</tbody></table>", head, body)


def figure(value, places=1):
    return "—" if value is None else f"{value:.{places}f}"


@admin.register(ForecastRun)
class ForecastRunAdmin(ReadOnlyAdmin):
    list_display = ["__str__", "created", "status", "data_as_of", "rows", "notes"]
    list_filter = ["kind", "status", "created"]
    readonly_fields = ["summary"]

    def get_queryset(self, request):
        counts = {f"{name}_count": Count(name, distinct=True) for name in ("forecasts", "backtests", "advice")}
        return super().get_queryset(request).annotate(**counts)

    @admin.display(description="rows")
    def rows(self, run):
        return run.forecasts_count + run.backtests_count + run.advice_count

    @admin.display(description="summary")
    def summary(self, run):
        """Per title: a forecast's season from now (P10, P50, P90), a backtest's errors, a print run's advice."""
        if run.kind == ForecastRun.Kind.FORECAST:
            titles = run.forecasts.filter(district=None).values("product__title").order_by("product__title")
            sums = titles.annotate(weeks=Count("pk"), p10=Sum("p10"), p50=Sum("p50"), p90=Sum("p90"))
            rows = [[t["product__title"], t["weeks"], *(figure(t[p], 0) for p in ("p10", "p50", "p90"))] for t in sums]
            return table(["title", "weeks", "P10", "P50 (copies to the exam)", "P90"], rows)
        if run.kind == ForecastRun.Kind.BACKTEST:
            rows = []
            for test in run.backtests.select_related("product"):
                errors = figure(test.wape, 2), figure(test.mase_vs_seasonal_naive, 2)
                beats = "yes" if test.shown else "no"
                rows.append([test.product or "every title", test.horizon_weeks, *errors, beats, test.n_weeks])
            return table(["title", "weeks ahead", "WAPE", "MASE", "beats the naive", "weeks tested"], rows)
        rows = []
        for advice in run.advice.select_related("product"):
            numbers = [advice.recommended_quantity, advice.reprint_trigger_units, figure(advice.weeks_of_cover)]
            rows.append([advice.product, advice.get_level_display(), *numbers, advice.projected_leftover, advice.alert])
        return table(["title", "level", "print now", "reprint at", "weeks of cover", "leftover", "alert"], rows)


@admin.register(Forecast)
class ForecastAdmin(ReadOnlyAdmin):
    list_display = ["product", "district", "week_start", "p10", "p50", "p90", "n_history", "run"]
    list_filter = [("district", admin.EmptyFieldListFilter), "product", "week_start"]
    list_select_related = ["product", "run"]
    show_full_result_count = False


@admin.register(Backtest)
class BacktestAdmin(ReadOnlyAdmin):
    list_display = ["__str__", "wape", "mase_vs_seasonal_naive", "shown", "n_weeks", "run"]
    list_filter = ["horizon_weeks", "shown"]
    list_select_related = ["product", "run"]


@admin.register(PrintRunAdvice)
class PrintRunAdviceAdmin(ReadOnlyAdmin):
    list_display = [
        *["product", "level", "recommended_quantity", "target_quantity", "supply", "reprint_trigger_units"],
        *["weeks_of_cover", "projected_leftover", "alert", "computed_at"],
    ]
    list_filter = ["level", "computed_at"]
    list_select_related = ["product"]


@admin.register(ItemStat)
class ItemStatAdmin(ReadOnlyAdmin):
    list_display = ["item", "n", "p", "discrimination", "flags", "run_date"]
    list_filter = ["run_date", "item__chapter__subject", "item__kind"]
    list_select_related = ["item"]


@admin.register(ChapterStat)
class ChapterStatAdmin(ReadOnlyAdmin):
    list_display = ["chapter", "n_learners", "mean_accuracy", "trend", "computed_at"]
    list_filter = ["computed_at", "chapter__subject"]
    list_select_related = ["chapter"]


@admin.register(CohortStat)
class CohortStatAdmin(ReadOnlyAdmin):
    list_display = ["cohort_month", "source", "week_index", "n", "active_share", "churned_share", "computed_at"]
    list_filter = ["computed_at", "source", "cohort_month"]


@admin.register(CourseHealthStat)
class CourseHealthStatAdmin(ReadOnlyAdmin):
    list_display = ["grain", "period_start", "subject", "chapter", "active_learners", "clips_completed", "quiz_answers"]
    list_filter = ["grain", "subject"]
    list_select_related = ["subject", "chapter"]


@admin.register(CodeActivationStat)
class CodeActivationStatAdmin(ReadOnlyAdmin):
    list_display = ["batch", "district", "printed", "redeemed", "redeemed_7d", "computed_at"]
    list_filter = ["computed_at", "batch"]


@admin.register(DeliveryStat)
class DeliveryStatAdmin(ReadOnlyAdmin):
    list_display = ["courier", "district", "n", "median_days", "p90_days", "computed_at"]
    list_filter = ["computed_at", "courier"]


@admin.register(OfferStat)
class OfferStatAdmin(ReadOnlyAdmin):
    list_display = [
        *["__str__", "period_start", "period_end", "orders", "discount_cost", "period_orders", "baseline_orders"],
        *["interval_low", "interval_high", "note"],
    ]
    list_filter = ["computed_at"]
    list_select_related = ["coupon", "offer"]


@admin.register(AccountScore)
class AccountScoreAdmin(ReadOnlyAdmin):
    list_display = ["__str__", "score", "bucket", "reasons", "computed_at"]
    list_filter = ["kind", "bucket", "computed_at"]


@admin.register(RedemptionAttempt)
class RedemptionAttemptAdmin(ReadOnlyAdmin):
    """Book codes tried in the app, kept 180 days for the fraud rules: hashes, never the account or the code."""

    list_display = ["created", "outcome", "batch", "account", "address"]
    list_filter = ["outcome", "batch", "created"]

    @admin.display(description="account (hash)")
    def account(self, attempt):
        return attempt.user_hash[:12]

    @admin.display(description="IP address (hash)")
    def address(self, attempt):
        return attempt.ip_hash[:12]


@admin.register(FraudSignal)
class FraudSignalAdmin(ReadOnlyAdmin):
    list_display = ["__str__", "count", "window_start", "window_end", "short_subject", "acknowledged_at"]
    list_filter = ["kind", ("acknowledged_at", admin.EmptyFieldListFilter), "created"]
    exclude = ["acknowledged_by"]
    readonly_fields = ["acknowledged_by_whom"]
    actions = ["acknowledge"]

    @admin.display(description="subject")
    def short_subject(self, signal):
        return signal.subject[:12]

    @admin.display(description="acknowledged by")
    def acknowledged_by_whom(self, signal):
        users = get_user_model().objects.filter(pk=signal.acknowledged_by)
        return users.values_list("email", flat=True).first() or "—"

    @admin.action(description="Acknowledge: looked at and handled", permissions=["acknowledge"])
    def acknowledge(self, request, queryset):
        from .jobs.fraud import acknowledged

        signals, now = list(queryset.filter(acknowledged_at=None)), timezone.now()
        for signal in signals:
            signal.acknowledged_at, signal.acknowledged_by = now, request.user.pk
            signal.save(update_fields=["acknowledged_at", "acknowledged_by"])
            acknowledged(signal)  # its inbox item done
            self.log_change(request, signal, "Acknowledged.")
        self.message_user(request, f"{len(signals)} signals acknowledged.")

    def has_acknowledge_permission(self, request):
        return request.user.has_perm("staff.acknowledge_signal")  # as the API's (staff.catalogue)
