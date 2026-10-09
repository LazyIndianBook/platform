"""Insights: what the nightly jobs (insights/jobs/) work out from the shop's and the course's tables, for staff.

Every prediction keeps how it was made (ForecastRun: the method, its parameters, when the data was read, the code's
version) and how the method fared against the seasonal naive (Backtest). Learner data are kept as aggregates only,
groups under 5 showing their size alone: no row here points to an account, and nothing here may feed marketing,
prices or offers, or rank students (DPDP Act s. 9(3); insights/README.md). A `district` of None is every district
together; "unknown" is a PIN code missing from India Post's directory (or no order to take one from)."""

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from learn.models import Entitlement


class ExamSeason(models.Model):
    """A board's exam for a class in an academic year, entered by staff from the board's notice. Sample papers sell
    until the exam: a season is the 52 weeks before `exam_start` (week 1 is the week just before it), and the forecasts
    stop there."""

    board = models.ForeignKey("content.Board", on_delete=models.PROTECT, related_name="+")
    class_level = models.ForeignKey("content.ClassLevel", on_delete=models.PROTECT, related_name="+")
    academic_year = models.CharField(max_length=7, help_text="2026-27")
    exam_start = models.DateField(help_text="The first written paper (practicals before it do not count).")
    exam_end = models.DateField(help_text="The last paper.")
    notes = models.TextField(blank=True, help_text="Where the dates come from (the board's notice).")

    class Meta:
        ordering = ["-exam_start"]
        constraints = [
            models.UniqueConstraint(fields=["board", "class_level", "academic_year"], name="one_exam_season_a_year")
        ]

    def __str__(self):
        return f"{self.board} {self.class_level} {self.academic_year}"

    def clean(self):
        if self.exam_start and self.exam_end and self.exam_end < self.exam_start:
            raise ValidationError({"exam_end": "The last paper cannot come before the first."})


class PrintCost(models.Model):
    """What a title costs to print and what is on order: the inputs of the print-run advice that the shop does not keep
    (ERPNext will own them: the Item's valuation and the open purchase orders). A title without one gets no advice."""

    product = models.OneToOneField(
        "shop.Product",
        on_delete=models.CASCADE,
        related_name="print_cost",
        limit_choices_to={"kind__in": ["sample-papers", "solutions"]},  # the books with copies of their own
    )
    unit_cost = models.DecimalField("print cost per copy (₹)", max_digits=8, decimal_places=2)
    salvage = models.DecimalField(
        "salvage per copy (₹)",
        max_digits=8,
        decimal_places=2,
        default=0,
        help_text="What a copy left after the exams fetches (pulping, a later sale); 0 when the papers change yearly.",
    )
    on_order = models.PositiveIntegerField("copies on order", default=0, help_text="Ordered, not yet in stock.")
    lead_time_weeks = models.PositiveSmallIntegerField("reprint lead time (weeks)", default=3)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "print cost"

    def __str__(self):
        return f"Print cost of {self.product}"


class ForecastRun(models.Model):
    """One run of a predictive job: what made its rows (method, parameters, code version) and when its data was read."""

    class Kind(models.TextChoices):
        FORECAST = "forecast", "demand forecast"
        BACKTEST = "backtest", "backtest"
        PRINT_RUN = "print_run", "print-run advice"

    class Status(models.TextChoices):
        RUNNING = "running", "running"
        DONE = "done", "done"
        SKIPPED = "skipped", "nothing to work on"
        FAILED = "failed", "failed"

    created = models.DateTimeField(auto_now_add=True, db_index=True)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    method = models.CharField(max_length=200)
    params = models.JSONField(default=dict, blank=True)
    data_as_of = models.DateTimeField(help_text="When the job read the data.")
    code_version = models.CharField(max_length=60, blank=True, help_text="RELEASE, as Sentry gets it.")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RUNNING)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return f"{self.get_kind_display()} #{self.pk}"


class Forecast(models.Model):
    """A title's copies in one week of the season: the median (p50) and the 10-90 % range."""

    run = models.ForeignKey(ForecastRun, on_delete=models.CASCADE, related_name="forecasts")
    product = models.ForeignKey("shop.Product", on_delete=models.CASCADE, related_name="+")
    district = models.CharField(max_length=80, null=True, blank=True)  # noqa: DJ001  None: every district
    week_start = models.DateField()
    p10 = models.FloatField()
    p50 = models.FloatField()
    p90 = models.FloatField()
    n_history = models.PositiveIntegerField(help_text="Copies sold in the history it stands on.")

    class Meta:
        ordering = ["-run", "product", "week_start", "district"]

    def __str__(self):
        return f"{self.product} from {self.week_start}"


class Backtest(models.Model):
    """How the method would have done last season (rolling origin), against the seasonal naive (last season's week)."""

    run = models.ForeignKey(ForecastRun, on_delete=models.CASCADE, related_name="backtests")
    product = models.ForeignKey(  # None: every title together
        "shop.Product", on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    horizon_weeks = models.PositiveSmallIntegerField()
    wape = models.FloatField("WAPE", null=True, help_text="Sum of absolute errors ÷ sum of copies sold.")
    mase_vs_seasonal_naive = models.FloatField(
        "MASE", null=True, help_text="Mean absolute error ÷ the seasonal naive's on the same weeks: below 1 beats it."
    )
    n_weeks = models.PositiveSmallIntegerField()
    shown = models.BooleanField(default=False, help_text="It beats the seasonal naive, so the panel may show it.")

    class Meta:
        ordering = ["-run", "product", "horizon_weeks"]

    def __str__(self):
        return f"Backtest of {self.product or 'every title'}, {self.horizon_weeks} weeks ahead"


class PrintRunAdvice(models.Model):
    """The newsvendor's answer for a title: how many copies to print now, when to reprint, what may be left over."""

    class Level(models.TextChoices):
        OK = "ok", "nothing to do"
        WATCH = "watch", "watch"
        ACT = "act", "act now"

    run = models.ForeignKey(ForecastRun, on_delete=models.CASCADE, related_name="advice")
    product = models.ForeignKey("shop.Product", on_delete=models.CASCADE, related_name="+")
    net_price = models.DecimalField("net price (₹)", max_digits=8, decimal_places=2)
    unit_cost = models.DecimalField("print cost (₹)", max_digits=8, decimal_places=2)
    salvage = models.DecimalField("salvage (₹)", max_digits=8, decimal_places=2)
    critical_ratio = models.FloatField(help_text="(net price − cost) ÷ (net price − salvage): the quantile to print.")
    target_quantity = models.PositiveIntegerField(help_text="The season's demand from now at the critical ratio.")
    supply = models.PositiveIntegerField(help_text="Copies in stock and on order.")
    recommended_quantity = models.PositiveIntegerField(help_text="Copies to print now: the target less the supply.")
    reprint_trigger_units = models.PositiveIntegerField(
        help_text="Reprint once the supply is at or below this: the P90 of the demand over the reprint lead time."
    )
    weeks_of_cover = models.FloatField(null=True, help_text="Empty: the supply outlasts the season.")
    projected_leftover = models.PositiveIntegerField(help_text="Copies left at the exam if nothing more is printed.")
    n_history = models.PositiveIntegerField(help_text="Copies sold in the history the forecast stands on.")
    level = models.CharField(max_length=5, choices=Level.choices, default=Level.OK)
    alert = models.CharField(max_length=200, blank=True)
    computed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name_plural = "print-run advice"
        ordering = ["-run", "product"]

    def __str__(self):
        return f"Print run of {self.product}"


class ItemStat(models.Model):
    """A quiz item's classical item analysis, from each learner's first attempt: computed once 30 learners answered."""

    item = models.ForeignKey("learn.QuizItem", on_delete=models.CASCADE, related_name="+")
    n = models.PositiveIntegerField(help_text="Learners who answered it (first attempts).")
    p = models.FloatField(null=True, help_text="Share who got it right.")
    discrimination = models.FloatField(
        null=True, help_text="Corrected item-total point-biserial against the chapter's other items."
    )
    flags = models.JSONField(default=list, blank=True)
    computed_at = models.DateTimeField(default=timezone.now)
    run_date = models.DateField(default=timezone.localdate)

    class Meta:
        ordering = ["-run_date", "item"]
        constraints = [models.UniqueConstraint(fields=["item", "run_date"], name="one_item_stat_a_day")]

    def __str__(self):
        return f"Item analysis of quiz item #{self.item_id}"


class ChapterStat(models.Model):
    """A chapter's quiz accuracy (first attempts, the mean of its learners' shares) and its trend over four weeks."""

    chapter = models.ForeignKey("learn.Chapter", on_delete=models.CASCADE, related_name="+")
    n_learners = models.PositiveIntegerField()
    mean_accuracy = models.FloatField(null=True, help_text="Empty below 5 learners.")
    trend = models.FloatField(null=True, help_text="The last 4 weeks' accuracy less the 4 weeks before.")
    computed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-computed_at", "chapter"]

    def __str__(self):
        return f"Accuracy in {self.chapter}"


class CohortStat(models.Model):
    """The share of a cohort (the month its learners' course opened, and how: book code, purchase, grant) active in
    each week after it opened, and the share gone quiet (no activity for 14 days, the exam still ahead)."""

    cohort_month = models.DateField(help_text="The first day of the month the course opened.")
    source = models.CharField(max_length=10, choices=Entitlement.Source.choices)
    week_index = models.PositiveSmallIntegerField(help_text="Weeks since the course opened (0: the first).")
    n = models.PositiveIntegerField(help_text="Learners counted that week (their exam still ahead).")
    active_share = models.FloatField(null=True, help_text="Empty below 5 learners.")
    churned_share = models.FloatField(null=True, help_text="No activity for 14 days; empty below 5 or in week 0.")
    computed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-computed_at", "cohort_month", "source", "week_index"]

    def __str__(self):
        return f"Cohort {self.cohort_month:%Y-%m} ({self.source}), week {self.week_index}"


class CodeActivationStat(models.Model):
    """Book codes of a print run (batch) redeemed, in all and by district (the redeemer's order's PIN code)."""

    batch = models.CharField(max_length=40)
    district = models.CharField(max_length=80, null=True, blank=True)  # noqa: DJ001  None: the whole batch
    printed = models.PositiveIntegerField(null=True, help_text="On the batch's row only.")
    redeemed = models.PositiveIntegerField()
    redeemed_7d = models.PositiveIntegerField("redeemed in the last 7 days")
    computed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-computed_at", "batch", "district"]

    def __str__(self):
        return f"Codes of {self.batch} in {self.district or 'every district'}"


class DeliveryStat(models.Model):
    """Days from shipped to delivered for a courier to a district, over the last year: the median and the P90."""

    courier = models.CharField(max_length=80)
    district = models.CharField(max_length=80, null=True, blank=True)  # noqa: DJ001  None: every district
    n = models.PositiveIntegerField()
    median_days = models.FloatField()
    p90_days = models.FloatField()
    computed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-computed_at", "courier", "district"]

    def __str__(self):
        return f"{self.courier} to {self.district or 'every district'}"


class FraudSignal(models.Model):
    """Something the fraud rules found, for staff to look at. The subject is a keyed hash where it would be personal
    (an account, an address, a phone number), never the value; the details hold counts and batches only."""

    class Kind(models.TextChoices):
        FAILED_CODES_ACCOUNT = "codes_failed_account", "failed book codes from one account in an hour"
        FAILED_CODES_ADDRESS = "codes_failed_ip", "failed book codes from one IP address in an hour"
        FAILED_CODES_SPIKE = "codes_failed_spike", "failed book codes: an hour far above the usual"
        CODES_PER_ACCOUNT = "codes_per_account", "one account redeeming many codes"
        ACCOUNTS_PER_CODE = "accounts_per_code", "one code tried by several accounts"
        SHARED_PHONE = "shared_phone", "accounts sharing a phone number on COD or coupon orders"
        SHARED_ADDRESS = "shared_address", "accounts sharing an address on COD or coupon orders"
        # Phase B: course
        FAILED_CODES_DEVICE = "codes_failed_device", "failed book codes from one device in an hour"
        UNDISPATCHED = "codes_undispatched", "codes redeemed from a batch not yet dispatched (a leak)"

    kind = models.CharField(max_length=25, choices=Kind.choices)
    subject = models.CharField(max_length=64, help_text="A keyed hash, or “all”.")
    count = models.PositiveIntegerField()
    window_start = models.DateTimeField()
    window_end = models.DateTimeField()
    details = models.JSONField(default=dict, blank=True)
    created = models.DateTimeField(auto_now_add=True, db_index=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    # the staff member's user id, not a key: no insights row links to an account (insights/tests/test_privacy.py)
    acknowledged_by = models.PositiveBigIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return f"{self.get_kind_display()} #{self.pk}"


class RedemptionAttempt(models.Model):
    """A book code tried in the app (api/learn.py RedeemView), for the fraud rules: keyed hashes of the account, the IP
    address, the device (the app's installation ID, when it sends one) and the code, the code's batch and the outcome.
    Deleted after 180 days."""

    class Outcome(models.TextChoices):
        REDEEMED = "redeemed", "redeemed"
        UNKNOWN = "unknown", "no such code"
        USED = "used", "used by another account"
        VOID = "void", "a void code"  # Phase B: course

    user_hash = models.CharField(max_length=64, db_index=True)
    ip_hash = models.CharField(max_length=64, db_index=True)
    code_hash = models.CharField(max_length=64, db_index=True)
    batch = models.CharField(max_length=40, blank=True, help_text="Empty: no such code.")
    outcome = models.CharField(max_length=10, choices=Outcome.choices)
    created = models.DateTimeField(default=timezone.now, db_index=True)
    # Phase B: course
    device_hash = models.CharField(max_length=64, blank=True, db_index=True, help_text="Empty: the app sent none.")

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return f"Book code tried #{self.pk}"


class OfferStat(models.Model):
    """What a coupon or an offer did while it ran, beside the same weeks last season, with a 95 % interval for the
    ratio of orders; it says when the numbers are too few to conclude anything, and never names a winner."""

    coupon = models.ForeignKey("shop.Coupon", on_delete=models.CASCADE, null=True, blank=True, related_name="+")
    offer = models.ForeignKey("shop.Offer", on_delete=models.CASCADE, null=True, blank=True, related_name="+")
    period_start = models.DateField()
    period_end = models.DateField()
    orders = models.PositiveIntegerField(help_text="Orders that used it.")
    revenue = models.DecimalField("their revenue (₹)", max_digits=12, decimal_places=2)
    discount_cost = models.DecimalField("discount given (₹)", max_digits=12, decimal_places=2)
    period_orders = models.PositiveIntegerField(help_text="Every order while it ran.")
    baseline_orders = models.PositiveIntegerField(help_text="Every order in the same weeks last season.")
    baseline_revenue = models.DecimalField(max_digits=12, decimal_places=2)
    interval_low = models.FloatField(null=True, help_text="95 % interval of orders while it ran ÷ the baseline's.")
    interval_high = models.FloatField(null=True)
    note = models.CharField(max_length=200)
    computed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-computed_at", "period_start"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(coupon__isnull=False, offer__isnull=True)
                | models.Q(coupon__isnull=True, offer__isnull=False),
                name="offer_stat_of_a_coupon_or_an_offer",
            )
        ]

    def __str__(self):
        return f"Effect of {self.coupon or self.offer}"


class AccountScore(models.Model):
    """A school's or distributor's lead score from the rules (insights.jobs.risk.score_account), never a student's.
    No rows yet: the schools and distributors will live in ERPNext, whose sync is to fill them."""

    class Kind(models.TextChoices):
        SCHOOL = "school", "school"
        DISTRIBUTOR = "distributor", "distributor"

    class Bucket(models.TextChoices):
        HIGH = "high", "High"
        MEDIUM = "medium", "Medium"
        LOW = "low", "Low"

    kind = models.CharField(max_length=11, choices=Kind.choices)
    external_ref = models.CharField(max_length=140, help_text="The account's name in ERPNext.")
    score = models.IntegerField()
    bucket = models.CharField(max_length=6, choices=Bucket.choices)
    reasons = models.JSONField(default=list, blank=True)
    computed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-computed_at", "-score"]

    def __str__(self):
        return f"{self.get_kind_display()} {self.external_ref}"
