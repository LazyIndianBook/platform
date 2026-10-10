// The reports as the API answers them: the tabs a manifest opens, Home's cards (a link each with its definition on
// hover and under "How this is counted", the totals beside the period before, the queues as they stand, test data said
// first), the tables with a bar beside the figure and "fewer than 10" in place of a group too small to show, a source
// not set up said so, and the two client parts: an export started as a job, and the print run worked out again from the
// typed inputs (checked before anything is sent).
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, toApiError } from "@/lib/api/errors";
import {
  type CodesReport,
  type CodReport,
  type HealthReport,
  type Home,
  type HomeCard,
  type InsightsPage,
  type Job,
  type PlaceReport,
  type PrintRun,
  type SalesReport,
  type SettlementsReport,
} from "@/lib/api/staff";
import { P } from "@/lib/modules";
import { manifestWith } from "@/test/fixtures";

import { CodTables } from "./cod";
import { CodesTables } from "./codes";
import { ExportReport } from "./export-report";
import { HealthTables } from "./health";
import { HomeNumbers, NumberCard } from "./home-cards";
import { backtestLine, CohortTable, ForecastTable, PrintRunsTable } from "./insights";
import { PlaceTable, placeHref } from "./place";
import { inputProblems, PrintRunPanel } from "./print-run";
import { opens, ReportsTabs, reportsTabs } from "./reports-tabs";
import { SalesTable } from "./sales";
import { SettlementsTable } from "./settlements";

const mocks = vi.hoisted(() => ({ exportReport: vi.fn(), getJob: vi.fn(), recomputePrintRun: vi.fn() }));
vi.mock("@/lib/api/staff", async (original) => ({
  ...(await original<typeof import("@/lib/api/staff")>()),
  exportReport: mocks.exportReport,
  getJob: mocks.getJob,
  recomputePrintRun: mocks.recomputePrintRun,
}));

const envelope = {
  definition: "What the report counts.",
  columns: [
    { key: "label", label: "Group", definition: "What the lines are grouped by." },
    { key: "net", label: "Net (₹)", definition: "What the lines sold for, after discounts." },
  ],
  as_of: "2026-10-09T12:00:00Z",
  test_mode: false,
  period: { start: "2026-09-10", end: "2026-10-09", days: 30 },
};

beforeEach(() => {
  mocks.exportReport.mockReset();
  mocks.getJob.mockReset();
  mocks.recomputePrintRun.mockReset();
});

describe("the tabs", () => {
  const keys = (permissions: string[]) => reportsTabs(manifestWith(permissions)).map((tab) => tab.key);

  it("open for the insights' permission and the data each report reads, as the API asks for both", () => {
    expect(keys([])).toEqual([]);
    expect(keys([P.insightsView])).toEqual(["index", "settlements", "cohorts", "forecasts"]);
    expect(keys([P.insightsView, P.orderItemsView, P.codView])).toEqual([
      "index",
      "sales",
      "place",
      "cod",
      "settlements",
      "cohorts",
      "forecasts",
    ]);
    expect(keys([P.insightsView, P.bookCodesView, P.progressView])).toContain("codes");
    expect(keys([P.insightsView, P.bookCodesView, P.progressView])).toContain("health");
    expect(keys([P.orderItemsView])).toEqual([]); // the data alone opens no report
  });

  it("say which page is open, and a page the manifest does not open is not one", () => {
    const manifest = manifestWith([P.insightsView, P.orderItemsView]);
    render(<ReportsTabs manifest={manifest} current="sales" />);
    expect(screen.getByRole("link", { name: "Sales" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Sales by place" })).not.toHaveAttribute("aria-current");
    expect(screen.queryByRole("link", { name: "Cash on delivery" })).toBeNull();
    expect(opens(manifest, "sales")).toBe(true);
    expect(opens(manifest, "cod")).toBe(false);
  });
});

const card = (extra: Partial<HomeCard>): HomeCard => ({
  key: "net_revenue",
  label: "Net revenue",
  group: "measure",
  unit: "inr",
  value: "184250.00",
  definition: "Money received less money returned in the period.",
  as_of: "2026-10-09T08:30:00Z",
  period: { start: "2026-10-03", end: "2026-10-09", days: 7 },
  href: "/reports/sales/?from=2026-10-03&to=2026-10-09",
  test_mode: false,
  comparison: {
    previous: "151900.00",
    difference: "+32350.00",
    percent: "+21.3",
    period: { start: "2026-09-26", end: "2026-10-02", days: 7 },
  },
  error: "",
  ...extra,
});

describe("Home's cards", () => {
  it("are a link to what they count, with the definition on hover and under 'How this is counted'", () => {
    render(
      <ul>
        <NumberCard card={card({})} />
      </ul>,
    );
    const link = screen.getByRole("link", { name: /Net revenue/ });
    expect(link).toHaveAttribute("href", "/reports/sales/?from=2026-10-03&to=2026-10-09");
    expect(link).toHaveAttribute("title", "Money received less money returned in the period.");
    expect(link).toHaveTextContent("₹1,84,250");
    expect(screen.getByText("Up ₹32,350 (21.3%) on the 7 days before (₹1,51,900)")).toBeInTheDocument();
    expect(screen.getByText("The last 7 days")).toBeInTheDocument();
    const disclosure = screen.getByText("How this is counted", { exact: false }).closest("details")!;
    expect(within(disclosure).getByText("Money received less money returned in the period.")).toBeInTheDocument();
    expect(within(disclosure).getByText(/^Worked out at \d\d:\d\d\.$/)).toBeInTheDocument();
  });

  it("show a queue as it stands now, a card that could not be worked out, and test keys", () => {
    render(
      <ul>
        <NumberCard
          card={card({
            key: "orders_to_pack",
            label: "Orders to pack",
            group: "queue",
            unit: "count",
            value: "4",
            period: null,
            comparison: null,
            href: "/orders/?tab=to_pack",
            test_mode: true,
          })}
        />
        <NumberCard
          card={card({
            key: "orders_placed",
            label: "Orders",
            unit: "count",
            value: null,
            comparison: null,
            error: "This number could not be worked out just now.",
          })}
        />
      </ul>,
    );
    expect(screen.getByRole("link", { name: /Orders to pack/ })).toHaveTextContent("4");
    expect(screen.getByText("As it stands now")).toBeInTheDocument();
    expect(screen.getByText("Test keys")).toBeInTheDocument();
    expect(screen.getByText("This number could not be worked out just now.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^Orders–/ })).toHaveTextContent("–"); // a dash, never a made-up zero
  });

  const home = (extra: Partial<Home>): Home => ({
    as_of: "2026-10-09T08:30:00Z",
    period: { start: "2026-10-03", end: "2026-10-09", days: 7, key: "week", label: "The last 7 days" },
    test_mode: false,
    test_orders_left_out: 0,
    cards: [
      card({}),
      card({
        key: "orders_to_pack",
        label: "Orders to pack",
        group: "queue",
        unit: "count",
        value: "4",
        period: null,
        comparison: null,
      }),
    ],
    ...extra,
  });

  it("put the totals first and what waits after, with the period to choose and when the data is from", () => {
    render(<HomeNumbers home={home({ test_orders_left_out: 3 })} />);
    const headings = screen.getAllByRole("heading").map((heading) => heading.textContent);
    expect(headings).toEqual(["The numbers", "Totals", "Waiting for someone"]);
    expect(screen.getByText(/^Data as of /)).toBeInTheDocument();
    expect(screen.getByText("3 test orders are left out of these numbers.")).toBeInTheDocument();
    const periods = within(screen.getByRole("navigation", { name: "Period of the totals" }));
    expect(periods.getByRole("link", { name: "7 days" })).toHaveAttribute("aria-current", "true");
    expect(periods.getByRole("link", { name: "Today" })).toHaveAttribute("href", "/?period=today");
    expect(periods.getByRole("link", { name: "30 days" })).toHaveAttribute("href", "/?period=month");
    expect(periods.getByRole("link", { name: "7 days" })).toHaveAttribute("href", "/");
  });

  it("say test data first on a site running on test keys, and have no period to choose for queues alone", () => {
    const { rerender } = render(<HomeNumbers home={home({ test_mode: true })} />);
    expect(
      screen.getByText("The site runs on Razorpay's test keys, so every number here is of test orders."),
    ).toBeInTheDocument();
    rerender(<HomeNumbers home={home({ cards: [card({ group: "queue", comparison: null, period: null })] })} />);
    expect(screen.queryByRole("navigation", { name: "Period of the totals" })).toBeNull();
    rerender(<HomeNumbers home={home({ cards: [] })} />);
    expect(screen.queryByRole("heading")).toBeNull(); // nothing for a role with no card
  });

  it("say one test order, not 'orders are'", () => {
    render(<HomeNumbers home={home({ test_orders_left_out: 1 })} />);
    expect(screen.getByText("1 test order is left out of these numbers.")).toBeInTheDocument();
  });
});

describe("sales", () => {
  const report = (extra: Partial<SalesReport>): SalesReport => ({
    ...envelope,
    report: "sales",
    by: "subject",
    grain: "none",
    totals: { orders: 5, units: 8, gross: "1560.00", discount: "60.00", net: "1500.00" },
    rows: [
      {
        key: "Physics",
        label: "Physics",
        period_start: null,
        orders: 3,
        units: 5,
        gross: "975.00",
        discount: "60.00",
        net: "915.00",
      },
      {
        key: "Chemistry",
        label: "Chemistry",
        period_start: null,
        orders: 2,
        units: 3,
        gross: "585.00",
        discount: "0.00",
        net: "585.00",
      },
    ],
    ...extra,
  });

  it("is a row per group with its net's bar, and the whole period's totals under it", () => {
    render(<SalesTable report={report({})} />);
    const table = screen.getByRole("region", { name: "Sales, a table" });
    expect(within(table).getByRole("columnheader", { name: "Subject" })).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "Net" })).toHaveAttribute(
      "title",
      "What the lines sold for, after discounts.",
    );
    const physics = within(table).getByRole("row", { name: /Physics/ });
    expect(physics).toHaveTextContent("₹915.00");
    expect(within(table).getByRole("row", { name: /Whole period/ })).toHaveTextContent("₹1,500.00");
    expect(table.querySelectorAll("[aria-hidden='true'] > span").length).toBe(2); // one bar for each net
  });

  it("has a column for the period when asked to break down, and says plainly when nothing was sold", () => {
    const { rerender } = render(
      <SalesTable
        report={report({
          grain: "week",
          rows: [
            {
              key: "Physics",
              label: "Physics",
              period_start: "2026-10-05",
              orders: 3,
              units: 5,
              gross: "975.00",
              discount: "0.00",
              net: "975.00",
            },
          ],
        })}
      />,
    );
    expect(screen.getByText("Week of 5 Oct 2026")).toBeInTheDocument();
    rerender(<SalesTable report={report({ rows: [] })} />);
    expect(screen.getByRole("heading", { name: "No sales in this period" })).toBeInTheDocument();
  });
});

describe("sales by place", () => {
  const report = (extra: Partial<PlaceReport>): PlaceReport => ({
    ...envelope,
    report: "sales-by-place",
    level: "state",
    state: "",
    minimum: 10,
    hidden_rows: 1,
    totals_shown: { orders: 80, units: 128, net: "27200.00" },
    rows: [
      {
        hidden: false,
        under: null,
        level: "state",
        state: "AS",
        state_name: "Assam",
        district: null,
        pin: null,
        label: "Assam",
        orders: 80,
        units: 128,
        net: "27200.00",
      },
      {
        hidden: true,
        under: 10,
        level: "state",
        state: "SK",
        state_name: "Sikkim",
        district: null,
        pin: null,
        label: "Sikkim",
        orders: null,
        units: null,
        net: null,
      },
    ],
    ...extra,
  });

  it("says 'fewer than 10' for a small place, links a state to its districts, and says the totals leave it out", () => {
    render(<PlaceTable report={report({})} keep={{ from: "2026-09-10", to: "2026-10-09" }} />);
    const sikkim = screen.getByRole("row", { name: /Sikkim/ });
    expect(within(sikkim).getByText("fewer than 10")).toBeInTheDocument();
    expect(within(sikkim).queryByRole("link")).toBeNull(); // nothing to open: its districts are smaller still
    expect(screen.getByRole("link", { name: /Assam/ })).toHaveAttribute(
      "href",
      "/reports/place/?from=2026-09-10&to=2026-10-09&level=district&state=AS",
    );
    expect(
      screen.getByText("1 place has fewer than 10 orders, so it is not shown and in no total below."),
    ).toBeInTheDocument();
    expect(screen.getByRole("row", { name: /Places shown/ })).toHaveTextContent("80");
  });

  it("builds an address at a level, with or without a state", () => {
    expect(placeHref({ from: "2026-09-10" }, "pin", "AS")).toBe("/reports/place/?from=2026-09-10&level=pin&state=AS");
    expect(placeHref({}, "state", "")).toBe("/reports/place/?level=state");
  });

  it("says plainly when nothing was sold", () => {
    render(<PlaceTable report={report({ rows: [], hidden_rows: 0 })} keep={{}} />);
    expect(screen.getByRole("heading", { name: "No sales in this period" })).toBeInTheDocument();
  });
});

describe("book codes", () => {
  const report = (extra: Partial<CodesReport>): CodesReport => ({
    ...envelope,
    report: "codes",
    period: null,
    batch: "",
    minimum: 10,
    districts_computed_at: "2026-10-09T02:00:00Z",
    districts: [
      { hidden: false, under: null, district: "Kamrup Metro", redeemed: 410, redeemed_7d: 38 },
      { hidden: true, under: 10, district: "Dhemaji", redeemed: null, redeemed_7d: null },
    ],
    rows: [
      {
        batch: "PHY-2027-1",
        printed: 5000,
        sold: 4200,
        activated: 1850,
        activated_7d: 140,
        void: 12,
        activation_rate: "0.3700",
      },
      {
        batch: "CHE-2027-1",
        printed: 3000,
        sold: null,
        activated: 640,
        activated_7d: 55,
        void: null,
        activation_rate: "0.2133",
      },
    ],
    ...extra,
  });

  it("shows the rate as a percent, and what the course has not recorded as 'not recorded yet', never zero", () => {
    render(<CodesTables report={report({})} />);
    const chemistry = screen.getByRole("row", { name: /CHE-2027-1/ });
    expect(within(chemistry).getAllByText("Not recorded yet")).toHaveLength(2); // sold and void, for a screen reader
    expect(chemistry).toHaveTextContent("21.3%");
    expect(screen.getByRole("row", { name: /PHY-2027-1/ })).toHaveTextContent("4,200");
  });

  it("hides a district under the minimum", () => {
    render(<CodesTables report={report({})} />);
    expect(within(screen.getByRole("row", { name: /Dhemaji/ })).getByText("fewer than 10")).toBeInTheDocument();
    expect(screen.getByRole("row", { name: /Kamrup Metro/ })).toHaveTextContent("410");
  });

  it("says plainly when no code exists, and when the districts were not counted yet", () => {
    const { rerender } = render(<CodesTables report={report({ rows: [] })} />);
    expect(screen.getByRole("heading", { name: "No book codes yet" })).toBeInTheDocument();
    rerender(<CodesTables report={report({ districts_computed_at: null, districts: [] })} />);
    expect(screen.getByText("The overnight count of districts has not run yet.")).toBeInTheDocument();
  });
});

describe("course health", () => {
  const point = (extra: object) => ({
    hidden: false,
    under: null,
    period_start: "2026-10-05",
    active_learners: 900,
    clips_completed: 1530,
    quiz_answers: 5580,
    quiz_accuracy: "0.6200",
    card_reviews: 3690,
    card_lapses: 810,
    smoothed_7: null,
    smoothed_28: null,
    ...extra,
  });
  const report = (extra: Partial<HealthReport>): HealthReport => ({
    ...envelope,
    report: "course-health",
    period: null,
    grain: "week",
    computed_at: "2026-10-09T02:15:00Z",
    minimum: 5,
    subject: null,
    chapter: null,
    subjects: [{ id: 1, name: "Physics" }],
    whole_course: true,
    series: [
      point({}),
      point({
        period_start: "2026-09-28",
        hidden: true,
        under: 5,
        active_learners: null,
        clips_completed: null,
        quiz_answers: null,
        quiz_accuracy: null,
        card_reviews: null,
        card_lapses: null,
      }),
    ],
    codes_by_week: [{ hidden: false, under: null, week_start: "2026-10-05", redeemed: 49 }],
    rows: [
      {
        hidden: false,
        under: null,
        subject: 1,
        chapter: 101,
        number: 1,
        title: "Electric charges",
        label: "Physics 1: Electric charges",
        active_7d: 180,
        active_28d: 414,
        clips_started: 558,
        clips_completed: 396,
        completion_rate: "0.7100",
        quiz_answers: 1620,
        quiz_accuracy: "0.5800",
        card_reviews: 1080,
        card_lapses: 180,
      },
    ],
    ...extra,
  });

  it("draws a week as learners with a bar and says 'fewer than 5' for a week too small to show", () => {
    render(<HealthTables report={report({})} />);
    const series = screen.getByRole("region", { name: "The course's use by period, a table" });
    expect(within(series).getByRole("row", { name: /Week of 5 Oct 2026/ })).toHaveTextContent("900");
    expect(
      within(within(series).getByRole("row", { name: /Week of 28 Sep 2026/ })).getByText("fewer than 5"),
    ).toBeInTheDocument();
    expect(screen.getByText(/A learner is counted once in a period/)).toBeInTheDocument();
    const chapters = screen.getByRole("region", { name: "The chapters over the last 28 days, a table" });
    expect(within(chapters).getByRole("link", { name: "Physics 1: Electric charges" })).toHaveAttribute(
      "href",
      "/reports/course-health/?grain=week&subject=1&chapter=101",
    );
    expect(within(chapters).getByRole("row", { name: /Electric charges/ })).toHaveTextContent("71.0%");
  });

  it("has the 7- and 28-day averages for days only", () => {
    const { rerender } = render(
      <HealthTables
        report={report({ grain: "day", series: [point({ smoothed_7: "880.0", smoothed_28: "851.5" })] })}
      />,
    );
    expect(screen.getByRole("columnheader", { name: "7-day average" })).toBeInTheDocument();
    expect(screen.getByText("851.5")).toBeInTheDocument();
    rerender(<HealthTables report={report({})} />);
    expect(screen.queryByRole("columnheader", { name: "7-day average" })).toBeNull();
  });

  it("says plainly that the overnight count has not run", () => {
    render(<HealthTables report={report({ computed_at: null, series: [], rows: [], codes_by_week: [] })} />);
    expect(screen.getByRole("heading", { name: "Nothing counted yet" })).toBeInTheDocument();
    expect(screen.queryByRole("region")).toBeNull();
  });
});

describe("cash on delivery", () => {
  const report = (remitted: CodReport["remitted"]): CodReport => ({
    ...envelope,
    report: "cod",
    as_of_day: "2026-10-09",
    remitted,
    by_courier: [{ courier: "India Post", count: 9, expected: "5900.00", overdue: 3 }],
    rows: [
      { key: "late_1_7", label: "1 to 7 days late", count: 4, expected: "2400.00", oldest_expected_on: "2026-10-03" },
    ],
  });

  it("says when the couriers remitted less than expected, in rupees", () => {
    render(
      <CodTables report={report({ count: 14, expected: "11200.00", received: "11150.00", difference: "-50.00" })} />,
    );
    expect(screen.getByText("The couriers remitted ₹50.00 less than expected in this period.")).toBeInTheDocument();
    expect(screen.getByText("-₹50.00")).toBeInTheDocument();
    expect(screen.getByRole("row", { name: /1 to 7 days late/ })).toHaveTextContent("₹2,400.00");
    expect(screen.getByRole("row", { name: /India Post/ })).toHaveTextContent("3");
  });

  it("says nothing of a shortfall when the cash matched", () => {
    render(<CodTables report={report({ count: 2, expected: "600.00", received: "600.00", difference: "0.00" })} />);
    expect(screen.queryByText(/less than expected/)).toBeNull();
  });
});

describe("settlements", () => {
  const report = (extra: Partial<SettlementsReport>): SettlementsReport => ({
    ...envelope,
    report: "settlements",
    configured: true,
    note: "",
    rows: [
      {
        reference: "setl_Nx4100Qa",
        date: "2026-10-08",
        gross: "48200.00",
        fees: "947.50",
        tax: "170.55",
        refunds: null,
        net: "47081.95",
        utr: "HDFCR52026101700",
        state: "posted",
      },
    ],
    ...extra,
  });

  it("is one row for each, a figure the module does not keep a dash and not a zero", () => {
    render(<SettlementsTable report={report({})} />);
    const row = screen.getByRole("row", { name: /setl_Nx4100Qa/ });
    expect(row).toHaveTextContent("₹47,081.95");
    expect(row).toHaveTextContent("HDFCR52026101700");
    expect(within(row).getAllByText("–").length).toBeGreaterThan(0);
  });

  it("says it is not set up, with the API's note, while the Finance module has no settlements", () => {
    render(
      <SettlementsTable
        report={report({
          configured: false,
          rows: [],
          note: "Razorpay's settlements are not set up yet: the Finance module fetches them.",
        })}
      />,
    );
    expect(screen.getByRole("heading", { name: "Razorpay's settlements are not set up" })).toBeInTheDocument();
    expect(
      screen.getByText("Razorpay's settlements are not set up yet: the Finance module fetches them."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("says plainly when the period holds none", () => {
    render(<SettlementsTable report={report({ rows: [] })} />);
    expect(screen.getByRole("heading", { name: "No settlement in this period" })).toBeInTheDocument();
  });
});

describe("the insights' lists", () => {
  const about = { method: "seasonal naive", data_as_of: "2026-10-09T02:00:00Z", backtest: null, shown: true };
  const page = <T,>(results: T[], extra: object = {}): InsightsPage<T> => ({
    count: results.length,
    next: null,
    previous: null,
    results,
    ...about,
    ...extra,
  });

  it("write a cohort week's shares, and 'fewer than 10' for a week too small to show", () => {
    render(
      <CohortTable
        page={page([
          {
            cohort_month: "2026-09-01",
            source: "book_code",
            week_index: 1,
            active_share: 0.72,
            churned_share: 0.05,
            n: 140,
            hidden: false,
            under: null,
          },
          {
            cohort_month: "2026-09-01",
            source: "purchase",
            week_index: 4,
            active_share: null,
            churned_share: null,
            n: 4,
            hidden: true,
            under: 10,
          },
        ])}
      />,
    );
    const shown = screen.getByRole("row", { name: /A book code/ });
    expect(shown).toHaveTextContent("September 2026");
    expect(shown).toHaveTextContent("72%");
    expect(within(screen.getByRole("row", { name: /A purchase/ })).getByText("fewer than 10")).toBeInTheDocument();
  });

  it("describe a backtest in words: tested and trusted, tested and not, or not tested yet", () => {
    const tested = {
      horizon_weeks: 4,
      wape: 0.31,
      mase_vs_seasonal_naive: 0.82,
      shown: true,
      n_weeks: 48,
      data_as_of: "2026-10-08T06:00:00Z",
    };
    expect(backtestLine({ backtest: tested })).toBe(
      "Tested against past seasons, 4 weeks ahead: it was off by 31% of the copies sold and beat the plain guess of last season's same week (MASE 0.82).",
    );
    expect(backtestLine({ backtest: { ...tested, shown: false, mase_vs_seasonal_naive: 1.14 } })).toContain(
      "labelled untested",
    );
    expect(backtestLine({ backtest: null })).toContain("two seasons of sales");
  });

  it("list the print runs with the level each needs, the chosen title marked", () => {
    const run = (title: string, level: "ok" | "watch" | "act", recommended: number) => ({
      product: title.toLowerCase(),
      title,
      net_price: "195.00",
      unit_cost: "60.00",
      salvage: "5.00",
      critical_ratio: 0.7105,
      target_quantity: 1240,
      supply: 540,
      recommended_quantity: recommended,
      reprint_trigger_units: 380,
      weeks_of_cover: null,
      projected_leftover: 85,
      level,
      alert: "",
      n: 1210,
    });
    render(<PrintRunsTable page={page([run("Physics", "act", 700), run("Chemistry", "ok", 0)])} selected="physics" />);
    expect(screen.getByRole("link", { name: "Physics" })).toHaveAttribute("aria-current", "true");
    expect(screen.getByRole("link", { name: "Physics" })).toHaveAttribute(
      "href",
      "/reports/forecasts/?product=physics#work-it-out",
    );
    expect(within(screen.getByRole("row", { name: /Physics/ })).getByText("Act now")).toBeInTheDocument();
    expect(within(screen.getByRole("row", { name: /Chemistry/ })).getByText("Nothing to do")).toBeInTheDocument();
    expect(within(screen.getByRole("row", { name: /Chemistry/ })).getByText("Past the season")).toBeInTheDocument(); // no weeks of cover
  });

  it("draw a title's weeks as a range with its middle marked", () => {
    render(
      <ForecastTable
        page={page([
          {
            product: "physics",
            title: "Physics",
            district: null,
            week_start: "2026-10-05",
            p10: 31.4,
            p50: 50.2,
            p90: 74.9,
            n: 1210,
          },
        ])}
      />,
    );
    const row = screen.getByRole("row", { name: /Week of 5 Oct 2026/ });
    expect(row).toHaveTextContent("31");
    expect(row).toHaveTextContent("50");
    expect(row).toHaveTextContent("75");
  });
});

const job = (extra: Partial<Job>): Job => ({
  id: 702,
  kind: "report_export",
  state: "queued",
  dry_run: false,
  params: { report: "sales", filters: {} },
  done: 0,
  total: 6,
  errors: [],
  result: {},
  result_url: null,
  change_request_id: null,
  cancel_requested: false,
  started_by: 7,
  created: "2026-10-09T10:00:00Z",
  started_at: null,
  finished_at: null,
  ...extra,
});

describe("ExportReport", () => {
  it("starts the job with the filters the page was read with, and shows its progress", async () => {
    mocks.exportReport.mockResolvedValue(
      job({ state: "done", done: 6, result_url: "http://x/api/v1/staff/jobs/702/result/?token=t" }),
    );
    render(
      <ExportReport report="sales" filters={{ from: "2026-09-10", to: "2026-10-09", by: "subject", grain: "none" }} />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Export as a file" }));
    expect(mocks.exportReport).toHaveBeenCalledWith("sales", {
      from: "2026-09-10",
      to: "2026-10-09",
      by: "subject",
      grain: "none",
    });
    expect(await screen.findByRole("button", { name: "Download the file" })).toBeInTheDocument();
  });

  it("links the change request when the job waits for an approver above the person's limit", async () => {
    mocks.exportReport.mockResolvedValue(job({ change_request_id: 508 }));
    mocks.getJob.mockResolvedValue(job({ change_request_id: 508 }));
    render(<ExportReport report="cod" filters={{}} />);
    await userEvent.click(screen.getByRole("button", { name: "Export as a file" }));
    expect(await screen.findByRole("link", { name: /^Open the change request/ })).toHaveAttribute(
      "href",
      "/approvals/508/",
    );
  });

  it("says why the API refused, and starts no job", async () => {
    mocks.exportReport.mockRejectedValue(
      toApiError(403, { detail: "You need the permission staff.view_cod.", code: "permission_denied" }),
    );
    render(<ExportReport report="cod" filters={{}} />);
    await userEvent.click(screen.getByRole("button", { name: "Export as a file" }));
    expect(await screen.findByText("You need the permission staff.view_cod.")).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).toBeNull();
  });
});

describe("the print run", () => {
  const result = (extra: Partial<PrintRun>): PrintRun => ({
    product: "physics-sample-papers-2027",
    title: "Physics Sample Papers 2027",
    net_price: "195.00",
    unit_cost: "60.00",
    salvage: "5.00",
    critical_ratio: 0.7105,
    percentile: 71,
    target_quantity: 1240,
    supply: 540,
    recommended_quantity: 700,
    range: { p10: 820, p50: 1010, p90: 1380, weeks: 18 },
    method: "seasonal naive by week of season × damped growth",
    data_as_of: "2026-10-08T06:00:00Z",
    backtest: {
      horizon_weeks: 4,
      wape: 0.31,
      mase_vs_seasonal_naive: 0.82,
      shown: true,
      n_weeks: 48,
      data_as_of: "2026-10-08T06:00:00Z",
    },
    shown: true,
    note: "",
    ...extra,
  });
  const inputs = { net_price: "195.00", unit_cost: "60.00", salvage: "5.00" };

  it("is worked out once on opening with the nightly inputs, with its range, method and last backtest", async () => {
    mocks.recomputePrintRun.mockResolvedValue(result({}));
    render(<PrintRunPanel product="physics-sample-papers-2027" title="Physics Sample Papers 2027" inputs={inputs} />);
    await waitFor(() => expect(mocks.recomputePrintRun).toHaveBeenCalledTimes(1));
    expect(mocks.recomputePrintRun).toHaveBeenCalledWith({ product: "physics-sample-papers-2027", ...inputs });
    const answer = await screen.findByRole("status", { name: "The print run worked out" });
    expect(
      within(answer).getByText("Critical ratio 0.7105: print for the 71st percentile of the season's demand."),
    ).toBeInTheDocument();
    expect(within(answer).getByText("700")).toBeInTheDocument();
    expect(within(answer).getByText("820 · 1,010 · 1,380")).toBeInTheDocument();
    expect(within(answer).getByText(/off by 31% of the copies sold/)).toBeInTheDocument();
    expect(within(answer).queryByText("Untested")).toBeNull();
  });

  it("is worked out again with what was typed, and nothing is sent for an input that is not rupees", async () => {
    mocks.recomputePrintRun.mockResolvedValue(result({}));
    render(<PrintRunPanel product="physics-sample-papers-2027" title="Physics Sample Papers 2027" inputs={inputs} />);
    await waitFor(() => expect(mocks.recomputePrintRun).toHaveBeenCalledTimes(1));
    const cost = screen.getByLabelText(/^Print cost/);
    await userEvent.clear(cost);
    await userEvent.type(cost, "60,5x");
    await userEvent.click(screen.getByRole("button", { name: "Work it out" }));
    expect(await screen.findByText("Rupees with up to two decimals, such as 195 or 60.50.")).toBeInTheDocument();
    expect(mocks.recomputePrintRun).toHaveBeenCalledTimes(1); // the bad input went nowhere
    await userEvent.clear(cost);
    await userEvent.type(cost, "80.50");
    mocks.recomputePrintRun.mockResolvedValue(
      result({ critical_ratio: 0.6053, percentile: 61, recommended_quantity: 410 }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Work it out" }));
    await waitFor(() => expect(mocks.recomputePrintRun).toHaveBeenCalledTimes(2));
    expect(mocks.recomputePrintRun).toHaveBeenLastCalledWith({
      product: "physics-sample-papers-2027",
      ...inputs,
      unit_cost: "80.50",
    });
    expect(
      await screen.findByText("Critical ratio 0.6053: print for the 61st percentile of the season's demand."),
    ).toBeInTheDocument();
  });

  it("labels a forecast that has not beaten the seasonal naive, and says there is no size without a forecast", async () => {
    mocks.recomputePrintRun.mockResolvedValue(result({ shown: false }));
    const { unmount } = render(<PrintRunPanel product="p" title="P" inputs={inputs} />);
    expect(await screen.findByText("Untested")).toBeInTheDocument();
    unmount();
    mocks.recomputePrintRun.mockResolvedValue(
      result({
        target_quantity: null,
        recommended_quantity: null,
        range: null,
        shown: false,
        backtest: null,
        note: "There is no demand forecast for this title yet, so no size can be recommended.",
      }),
    );
    render(<PrintRunPanel product="p" title="P" inputs={inputs} />);
    expect(
      await screen.findByText("There is no demand forecast for this title yet, so no size can be recommended."),
    ).toBeInTheDocument();
    expect(screen.queryByText("copies to print now")).toBeNull();
  });

  it("shows the API's word for a field it refused", async () => {
    mocks.recomputePrintRun.mockRejectedValue(
      new ApiError(400, "invalid", "Check what you entered.", { salvage: ["A valid number is required."] }),
    );
    render(<PrintRunPanel product="p" title="P" inputs={inputs} />);
    expect((await screen.findAllByText("A valid number is required.")).length).toBeGreaterThan(0);
  });

  it("checks rupees: up to two decimals, each field there", () => {
    expect(inputProblems({ net_price: "195", unit_cost: "60.5", salvage: "0" })).toEqual({});
    expect(Object.keys(inputProblems({ net_price: "", unit_cost: "60.555", salvage: "-1" }))).toEqual([
      "net_price",
      "unit_cost",
      "salvage",
    ]);
  });
});
