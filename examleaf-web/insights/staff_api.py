"""The reports, for the panel (API.md "Home and reports (staff)"), under `/api/v1/staff/reports/`: sales by product,
subject, class, board, edition and period; sales by state, district and PIN code; book codes by batch and district;
the course's use by subject and chapter; cash on delivery; Razorpay's settlements; and the print-run sum recomputed
with the inputs typed. (The cohorts, the forecasts and the nightly print-run advice are `insights/api.py`'s, under
`/api/v1/insights/`: the console draws them from there.) Every endpoint needs `staff.view_insights` and the
permission of
the data it reads (named through `needs`, so a refusal names the one missing); the rules each report keeps are in
reports.py, and the export of any of them is the job `report_export` (exports.py)."""

from django.urls import path
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, serializers
from rest_framework.response import Response

from api.schema import AutoSchema
from shop.models import live_mode
from staff.api import StaffView

from . import reports


class ReportsSchema(AutoSchema):
    def get_tags(self):
        return ["reports (staff)"]


def needs(*perms, report=None):
    """A permission map entry that asks for all of `perms` (the report's own, `staff.view_insights`, and the data's
    `view_`), or those a `report` requires now: the first the person lacks is the one a refusal names (and the audit
    log's `authz_fail` records). The API reference lists `.needs`."""

    def permission(view, request):
        wanted = report.required() if report else perms
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return wanted[0]
        return next((perm for perm in wanted if not user.has_perm(perm)), wanted[0])

    permission.needs = report.needs if report else perms
    return permission


# ---- What the reports answer ----


class ReportColumnSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    definition = serializers.CharField(help_text="how the column's numbers are counted")


class ReportPeriodSerializer(serializers.Serializer):
    start = serializers.DateField()
    end = serializers.DateField(help_text="the last day, included")
    days = serializers.IntegerField()


class ReportEnvelopeSerializer(serializers.Serializer):
    report = serializers.CharField()
    definition = serializers.CharField(help_text="what the report counts and how, in words")
    columns = ReportColumnSerializer(many=True)
    as_of = serializers.DateTimeField(help_text="when it was worked out")
    test_mode = serializers.BooleanField(help_text="the site runs on test keys: every number is of test-mode rows")
    period = ReportPeriodSerializer(allow_null=True)


class Cell(serializers.Serializer):
    hidden = serializers.BooleanField(help_text="too few to show: the numbers are null (see `under`)")
    under = serializers.IntegerField(allow_null=True, help_text="the minimum cell the row is under; null when shown")


def money(**kwargs):
    return serializers.DecimalField(max_digits=14, decimal_places=2, **kwargs)


def share(**kwargs):
    return serializers.DecimalField(max_digits=6, decimal_places=4, **kwargs)


class ReportSalesRowSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    period_start = serializers.DateField(allow_null=True)
    orders = serializers.IntegerField()
    units = serializers.IntegerField()
    gross = money()
    discount = money()
    net = money()


class ReportSalesTotalsSerializer(serializers.Serializer):
    orders = serializers.IntegerField()
    units = serializers.IntegerField()
    gross = money()
    discount = money()
    net = money()


class ReportSalesSerializer(ReportEnvelopeSerializer):
    by = serializers.CharField()
    grain = serializers.CharField()
    totals = ReportSalesTotalsSerializer(help_text="the whole period, whatever the grouping")
    rows = ReportSalesRowSerializer(many=True)


class ReportPlaceRowSerializer(Cell):
    level = serializers.CharField()
    state = serializers.CharField(allow_null=True, help_text="a state's code")
    state_name = serializers.CharField(allow_null=True)
    district = serializers.CharField(allow_null=True)
    pin = serializers.CharField(allow_null=True)
    label = serializers.CharField()
    orders = serializers.IntegerField(allow_null=True)
    units = serializers.IntegerField(allow_null=True)
    net = money(allow_null=True)


class ReportPlaceTotalsSerializer(serializers.Serializer):
    orders = serializers.IntegerField()
    units = serializers.IntegerField()
    net = money()


class ReportPlaceSerializer(ReportEnvelopeSerializer):
    level = serializers.CharField()
    state = serializers.CharField(allow_blank=True)
    minimum = serializers.IntegerField(help_text="a place with fewer orders is hidden")
    hidden_rows = serializers.IntegerField()
    totals_shown = ReportPlaceTotalsSerializer(help_text="the rows shown only: the places hidden are not in it")
    rows = ReportPlaceRowSerializer(many=True)


class ReportCodesRowSerializer(serializers.Serializer):
    batch = serializers.CharField()
    printed = serializers.IntegerField()
    sold = serializers.IntegerField(allow_null=True, help_text="null until the course module records a batch's book")
    activated = serializers.IntegerField()
    activated_7d = serializers.IntegerField()
    revoked = serializers.IntegerField(allow_null=True, help_text="null until the course module can void codes")
    activation_rate = share(allow_null=True)


class ReportCodesDistrictSerializer(Cell):
    district = serializers.CharField()
    redeemed = serializers.IntegerField(allow_null=True)
    redeemed_7d = serializers.IntegerField(allow_null=True)


class ReportCodesSerializer(ReportEnvelopeSerializer):
    batch = serializers.CharField(allow_blank=True)
    minimum = serializers.IntegerField()
    districts_computed_at = serializers.DateTimeField(allow_null=True)
    districts = ReportCodesDistrictSerializer(many=True)
    rows = ReportCodesRowSerializer(many=True)


class ReportHealthPointSerializer(Cell):
    period_start = serializers.DateField()
    active_learners = serializers.IntegerField(allow_null=True)
    clips_completed = serializers.IntegerField(allow_null=True)
    quiz_answers = serializers.IntegerField(allow_null=True)
    quiz_accuracy = share(allow_null=True)
    card_reviews = serializers.IntegerField(allow_null=True)
    card_lapses = serializers.IntegerField(allow_null=True)
    smoothed_7 = serializers.DecimalField(
        max_digits=8, decimal_places=1, allow_null=True, help_text="daily series only"
    )
    smoothed_28 = serializers.DecimalField(
        max_digits=8, decimal_places=1, allow_null=True, help_text="daily series only"
    )


class ReportHealthChapterSerializer(Cell):
    subject = serializers.IntegerField()
    chapter = serializers.IntegerField()
    number = serializers.IntegerField()
    title = serializers.CharField()
    label = serializers.CharField()
    active_7d = serializers.IntegerField(allow_null=True)
    active_28d = serializers.IntegerField(allow_null=True)
    clips_started = serializers.IntegerField(allow_null=True)
    clips_completed = serializers.IntegerField(allow_null=True)
    completion_rate = share(allow_null=True)
    quiz_answers = serializers.IntegerField(allow_null=True)
    quiz_accuracy = share(allow_null=True)
    card_reviews = serializers.IntegerField(allow_null=True)
    card_lapses = serializers.IntegerField(allow_null=True)


class ReportHealthWeekSerializer(Cell):
    week_start = serializers.DateField()
    redeemed = serializers.IntegerField(allow_null=True)


class ReportHealthSubjectSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


class ReportHealthSerializer(ReportEnvelopeSerializer):
    grain = serializers.CharField()
    computed_at = serializers.DateTimeField(allow_null=True, help_text="null: the nightly job has not run yet")
    minimum = serializers.IntegerField(help_text="a cell of fewer learners is hidden")
    subject = serializers.IntegerField(allow_null=True)
    chapter = serializers.IntegerField(allow_null=True)
    subjects = ReportHealthSubjectSerializer(many=True, help_text="the subjects the person looks after")
    whole_course = serializers.BooleanField(help_text="the series is of the whole course")
    series = ReportHealthPointSerializer(many=True, help_text="active learners and the rest, one point per period")
    codes_by_week = ReportHealthWeekSerializer(many=True)
    rows = ReportHealthChapterSerializer(many=True, help_text="the chapters over the last 28 days")


class ReportCodRowSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    count = serializers.IntegerField()
    expected = money()
    oldest_expected_on = serializers.DateField(allow_null=True)


class ReportCodCourierSerializer(serializers.Serializer):
    courier = serializers.CharField()
    count = serializers.IntegerField()
    expected = money()
    overdue = serializers.IntegerField()


class ReportCodRemittedSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    expected = money()
    received = money()
    difference = money(help_text="received less expected")


class ReportCodSerializer(ReportEnvelopeSerializer):
    as_of_day = serializers.DateField()
    remitted = ReportCodRemittedSerializer(help_text="remitted in the period")
    by_courier = ReportCodCourierSerializer(many=True)
    rows = ReportCodRowSerializer(many=True, help_text="what is outstanding, by how late")


class ReportSettlementRowSerializer(serializers.Serializer):
    reference = serializers.CharField()
    date = serializers.DateField(allow_null=True)
    gross = money(allow_null=True)
    fees = money(allow_null=True)
    tax = money(allow_null=True)
    refunds = money(allow_null=True)
    net = money(allow_null=True)
    utr = serializers.CharField(allow_blank=True)
    state = serializers.CharField(allow_blank=True)


class ReportSettlementsSerializer(ReportEnvelopeSerializer):
    configured = serializers.BooleanField(help_text="false: the Finance module has not set up the settlements")
    note = serializers.CharField(allow_blank=True)
    rows = ReportSettlementRowSerializer(many=True)


class ReportIndexItemSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    summary = serializers.CharField()
    page = serializers.CharField(help_text="the console's page")
    api = serializers.CharField(help_text="where the numbers are")
    needs = serializers.ListField(child=serializers.CharField(), help_text="the permissions that open it")
    available = serializers.BooleanField(help_text="the person holds them all")
    configured = serializers.BooleanField(help_text="false: its source is not set up yet")


class ReportIndexSerializer(serializers.Serializer):
    test_mode = serializers.BooleanField()
    reports = ReportIndexItemSerializer(many=True)


class ReportPrintRunRequestSerializer(serializers.Serializer):
    product = serializers.SlugField(help_text="the title's slug")
    net_price = serializers.DecimalField(
        max_digits=8, decimal_places=2, min_value=0, help_text="what a copy sells for after discounts"
    )
    unit_cost = serializers.DecimalField(max_digits=8, decimal_places=2, min_value=0, help_text="print cost per copy")
    salvage = serializers.DecimalField(
        max_digits=8, decimal_places=2, min_value=0, default=0, help_text="what a copy left after the exams fetches"
    )

    def validate(self, data):
        if data["salvage"] > data["unit_cost"]:
            raise serializers.ValidationError(
                {"salvage": ["A left-over copy cannot fetch more than it cost to print."]}
            )
        return data


class ReportDemandRangeSerializer(serializers.Serializer):
    p10 = serializers.IntegerField(help_text="copies from now to the exam: a season in ten sells less")
    p50 = serializers.IntegerField()
    p90 = serializers.IntegerField(help_text="a season in ten sells more")
    weeks = serializers.IntegerField()


class ReportBacktestSerializer(serializers.Serializer):
    horizon_weeks = serializers.IntegerField()
    wape = serializers.FloatField(allow_null=True)
    mase_vs_seasonal_naive = serializers.FloatField(allow_null=True)
    shown = serializers.BooleanField()
    n_weeks = serializers.IntegerField()
    data_as_of = serializers.DateTimeField()


class ReportPrintRunSerializer(serializers.Serializer):
    product = serializers.CharField()
    title = serializers.CharField()
    net_price = money()
    unit_cost = money()
    salvage = money()
    critical_ratio = serializers.FloatField(
        help_text="(net price - cost) / (net price - salvage): the quantile to print"
    )
    percentile = serializers.IntegerField(help_text="the critical ratio in percent: print the Pn of the demand")
    target_quantity = serializers.IntegerField(allow_null=True, help_text="the season's demand at that percentile")
    supply = serializers.IntegerField(help_text="copies in stock and on order")
    recommended_quantity = serializers.IntegerField(allow_null=True, help_text="copies to print now; null: no forecast")
    range = ReportDemandRangeSerializer(allow_null=True)
    method = serializers.CharField(allow_blank=True)
    data_as_of = serializers.DateTimeField(allow_null=True)
    backtest = ReportBacktestSerializer(allow_null=True, help_text="the last backtest of every title, 4 weeks ahead")
    shown = serializers.BooleanField(help_text="false: the forecast has not beaten the seasonal naive in a backtest")
    note = serializers.CharField(allow_blank=True)


# ---- The views ----


class ReportView(StaffView, generics.GenericAPIView):
    """A report: its filters in the query, its answer from reports.py through its serializer."""

    schema = ReportsSchema()
    pagination_class = None
    filter_backends = []
    throttle_scope = "staff_reports"
    report = None  # the reports.Report

    def get(self, request, *args, **kwargs):
        return Response(self.get_serializer(self.report.run(request.user, request.query_params)).data)


PERIOD_PARAMS = [
    OpenApiParameter("from", str, description="the first day, YYYY-MM-DD (30 days before the last by default)"),
    OpenApiParameter("to", str, description="the last day, YYYY-MM-DD (today); at most 13 months from the first"),
]


class ReportSalesView(ReportView):
    serializer_class = ReportSalesSerializer
    report = reports.REPORTS["sales"]
    permissions = {"GET": needs(report=report)}

    @extend_schema(
        parameters=[
            *PERIOD_PARAMS,
            OpenApiParameter("by", str, enum=["product", "subject", "class", "board", "edition", "none"]),
            OpenApiParameter("grain", str, enum=["none", "day", "week", "month"], description="a row per period too"),
        ],
        responses=ReportSalesSerializer,
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class ReportPlaceView(ReportView):
    serializer_class = ReportPlaceSerializer
    report = reports.REPORTS["sales-by-place"]
    permissions = {"GET": needs(report=report)}

    @extend_schema(
        parameters=[
            *PERIOD_PARAMS,
            OpenApiParameter("level", str, enum=["state", "district", "pin"]),
            OpenApiParameter("state", str, description="a state's code (AS): the districts and PIN codes of it"),
        ],
        responses=ReportPlaceSerializer,
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class ReportCodesView(ReportView):
    serializer_class = ReportCodesSerializer
    report = reports.REPORTS["codes"]
    permissions = {"GET": needs(report=report)}

    @extend_schema(
        parameters=[OpenApiParameter("batch", str, description="one batch's districts")],
        responses=ReportCodesSerializer,
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class ReportHealthView(ReportView):
    serializer_class = ReportHealthSerializer
    report = reports.REPORTS["course-health"]
    permissions = {"GET": needs(report=report)}

    @extend_schema(
        parameters=[
            OpenApiParameter("subject", int, description="a subject's id (the whole course by default)"),
            OpenApiParameter("chapter", int, description="a chapter's id"),
            OpenApiParameter("grain", str, enum=["day", "week", "month"], description="the series' periods (week)"),
        ],
        responses=ReportHealthSerializer,
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class ReportCodView(ReportView):
    serializer_class = ReportCodSerializer
    report = reports.REPORTS["cod"]
    permissions = {"GET": needs(report=report)}

    @extend_schema(parameters=PERIOD_PARAMS, responses=ReportCodSerializer)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class ReportSettlementsView(ReportView):
    serializer_class = ReportSettlementsSerializer
    report = reports.REPORTS["settlements"]
    permissions = {"GET": needs(report=report)}

    @extend_schema(parameters=PERIOD_PARAMS, responses=ReportSettlementsSerializer)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class ReportPrintRunView(StaffView, generics.GenericAPIView):
    """The newsvendor's sum for a title with the inputs typed: nothing is stored and nothing is changed."""

    schema = ReportsSchema()
    pagination_class = None
    filter_backends = []
    throttle_scope = "staff_reports"
    permissions = {"POST": needs(reports.INSIGHTS, "shop.view_product")}
    serializer_class = ReportPrintRunRequestSerializer

    @extend_schema(request=ReportPrintRunRequestSerializer, responses=ReportPrintRunSerializer)
    def post(self, request, *args, **kwargs):
        asked = ReportPrintRunRequestSerializer(data=request.data)
        asked.is_valid(raise_exception=True)
        return Response(ReportPrintRunSerializer(reports.print_run(request.user, asked.validated_data)).data)


# the insights' own pages, which the console draws and the reports' index lists
INSIGHT_PAGES = [
    {
        "key": "cohorts",
        "label": "Cohorts",
        "page": "/reports/cohorts/",
        "api": "/api/v1/insights/cohorts/",
        "summary": "How many learners stay active week by week, by the month their course opened.",
    },
    {
        "key": "forecasts",
        "label": "Forecasts and print runs",
        "page": "/reports/forecasts/",
        "api": "/api/v1/insights/forecasts/",
        "summary": "Weekly demand per title with its range, and the copies to print.",
    },
]


class ReportIndexView(StaffView, generics.GenericAPIView):
    """The reports the person may open, each with the permissions it needs, and whether its source is set up."""

    schema = ReportsSchema()
    pagination_class = None
    filter_backends = []
    permissions = {"GET": reports.INSIGHTS}
    serializer_class = ReportIndexSerializer

    @extend_schema(responses=ReportIndexSerializer)
    def get(self, request, *args, **kwargs):
        def listed(key, label, summary, page, api, needed, configured=True):
            held = all(request.user.has_perm(perm) for perm in needed)
            return {
                "key": key,
                "label": label,
                "summary": summary,
                "page": page,
                "api": api,
                "needs": list(needed),
                "available": held,
                "configured": configured,
            }

        found = [
            listed(
                each.key,
                each.label,
                each.summary,
                each.page,
                f"/api/v1/staff/reports/{each.key}/",
                each.required(),
                configured=each.configured(),
            )
            for each in reports.REPORTS.values()
        ]
        found += [
            listed(each["key"], each["label"], each["summary"], each["page"], each["api"], (reports.INSIGHTS,))
            for each in INSIGHT_PAGES
        ]
        return Response(ReportIndexSerializer({"test_mode": not live_mode(), "reports": found}).data)


urlpatterns = [  # under /api/v1/staff/reports/ (staff/urls.py)
    path("", ReportIndexView.as_view(), name="reports"),
    path("sales/", ReportSalesView.as_view(), name="report-sales"),
    path("sales-by-place/", ReportPlaceView.as_view(), name="report-sales-by-place"),
    path("codes/", ReportCodesView.as_view(), name="report-codes"),
    path("course-health/", ReportHealthView.as_view(), name="report-course-health"),
    path("cod/", ReportCodView.as_view(), name="report-cod"),
    path("settlements/", ReportSettlementsView.as_view(), name="report-settlements"),
    path("print-run/", ReportPrintRunView.as_view(), name="report-print-run"),
]
