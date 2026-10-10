// THE HOME AND REPORTS PART OF THE STAFF API MOCK, FOR DEVELOPMENT AND TESTS ONLY (handler.ts calls it under
// STAFF_API_MOCK=1). It answers /api/v1/staff/home/ and /api/v1/staff/reports/ as examleaf-web's insights/staff_home.py and
// staff_api.py do, and the insights' own lists the reports draw (/api/v1/insights/print-runs/, forecasts/ and cohorts/),
// from facts made here: the sales of five titles over 400 days, grouped as the backend groups them; places with small
// ones the minimum hides; book codes by print run and district; the course's use with a day too small to show; cash on
// delivery's ageing; Razorpay's settlements; the newsvendor sum worked out with the backend's arithmetic. The rules are
// the backend's: Home's cards by role and permission (words copied from metrics.py), each report's own permission
// named when it is missing, the period at most 13 months and never ahead, a state's code checked, a minimum cell
// hiding its numbers, the export as a job with a file that ends with who made it. Dev-only cookies change a state:
// staff_mock_test_keys=1 (the site runs on test keys), staff_mock_card_error=<card key> (that card could not be worked
// out), staff_mock_settlements=off (the Finance module has not set them up), staff_mock_health=empty (the nightly count
// has not run), staff_mock_untested=1 (the forecast has not beaten the seasonal naive).
import type { MockJob, MockSchemas, World } from "./fixtures";
import { HOME_SPECS } from "./reports-specs";
import { REPORT_INDEX, REPORT_WORDS } from "./reports-words";

type S = MockSchemas;
type Body = Record<string, unknown>;
export type ReportsContext = {
  request: Request;
  url: URL;
  parts: string[];
  method: string;
  world: World;
  who: { id: number; email: string; name: string; role: string; breakGlass: boolean };
  body: Body;
  permissions: string[];
};
/** handler.ts's own helpers, lent to this part. */
export type ReportsKit = {
  json: (status: number, body: unknown) => Response;
  invalid: (fields: Record<string, unknown>) => Response;
  notFound: () => Response;
  refuse: (perm: string, detail?: string) => Response;
  record: (context: ReportsContext, action: string, extra?: Partial<S["AuditEvent"]>) => void;
  startJob: (context: ReportsContext, kind: S["Job"]["kind"], params: unknown, rows: string[]) => MockJob;
  visibleJob: (context: ReportsContext, job: MockJob) => S["Job"];
};

type Period = { start: string; end: string; days: number };

const DAY = 86_400_000;
const IST = 5.5 * 3_600_000;
const MIN_CELL = 10;
const MIN_CLASS = 5;
const MAX_MONTHS = 13;

/** A moment as a day in India ("2026-10-09"). */
const dayOf = (ms: number) => new Date(ms + IST).toISOString().slice(0, 10);
const daysAgo = (days: number) => dayOf(Date.now() - days * DAY);
const dayMs = (day: string) => Date.parse(`${day}T00:00:00Z`);
const shift = (day: string, days: number) => dayOf(dayMs(day) - IST + days * DAY);
const monday = (day: string) => shift(day, -((new Date(`${day}T00:00:00Z`).getUTCDay() + 6) % 7));
const firstOfMonth = (day: string) => `${day.slice(0, 7)}-01`;
const money = (value: number) => value.toFixed(2);
const signed = (value: number, places: number) => `${value >= 0 ? "+" : "-"}${Math.abs(value).toFixed(places)}`;

function cookie(request: Request, name: string): string | undefined {
  return (request.headers.get("Cookie") ?? "")
    .split(/;\s*/)
    .find((pair) => pair.startsWith(`${name}=`))
    ?.slice(name.length + 1);
}

const testKeys = (context: ReportsContext) => cookie(context.request, "staff_mock_test_keys") === "1";
const settlementsOn = (context: ReportsContext) => cookie(context.request, "staff_mock_settlements") !== "off";

// ---- Who may open what ----

/** The permissions each report asks of the person besides staff.view_insights (the backend names the missing one). */
const REPORT_NEEDS: Record<string, string[]> = {
  sales: ["shop.view_orderitem"],
  "sales-by-place": ["shop.view_orderitem"],
  codes: ["learn.view_bookcode"],
  "course-health": ["learn.view_progress"],
  cod: ["staff.view_cod"],
  settlements: [],
  "print-run": ["shop.view_product"],
  cohorts: [],
  forecasts: [],
};

/** The report filters each export takes (insights/reports.py's params); another is a 400. */
const FILTERS: Record<string, string[]> = {
  sales: ["from", "to", "by", "grain"],
  "sales-by-place": ["from", "to", "level", "state"],
  codes: ["batch"],
  "course-health": ["subject", "chapter", "grain"],
  cod: ["from", "to"],
  settlements: ["from", "to"],
  cohorts: [],
  forecasts: [],
};

/** Which permission a request needs (handler.ts checks it first): Home is any member of staff's; the rest are the
 *  insights' reader's, and each report names its data's permission itself. */
export function reportsPermission(context: ReportsContext): string | null {
  return context.parts[0] === "home" ? null : "staff.view_insights";
}

// ---- Periods ----

function periodOf(context: ReportsContext, days = 30): Period | Response {
  const asked = (name: string) => context.url.searchParams.get(name) ?? "";
  const valid = (value: string) => /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(value));
  for (const name of ["from", "to"])
    if (asked(name) && !valid(asked(name)))
      return Response.json(
        { [name]: ["A day: YYYY-MM-DD."] },
        { status: 400, headers: { "Cache-Control": "no-store" } },
      );
  const today = daysAgo(0);
  const end = asked("to") || today;
  const start = asked("from") || shift(end, -(days - 1));
  const bad = (field: string, text: string) =>
    Response.json({ [field]: [text] }, { status: 400, headers: { "Cache-Control": "no-store" } });
  if (end > today) return bad("to", "Not after today.");
  if (start > end) return bad("from", "Not after the last day.");
  const earliest = new Date(`${end}T00:00:00Z`);
  earliest.setUTCMonth(earliest.getUTCMonth() - MAX_MONTHS);
  if (start <= earliest.toISOString().slice(0, 10))
    return bad("from", `At most ${MAX_MONTHS} months before the last day.`);
  return { start, end, days: Math.round((dayMs(end) - dayMs(start)) / DAY) + 1 };
}

const isPeriod = (value: Period | Response): value is Period => !(value instanceof Response);

function envelope(context: ReportsContext, key: string, period: Period | null) {
  return {
    report: key,
    definition: REPORT_WORDS[key].definition,
    columns: REPORT_WORDS[key].columns,
    as_of: new Date().toISOString(),
    test_mode: testKeys(context),
    period,
  };
}

// ---- Home ----

const HOME_PERIODS: Record<string, { days: number; label: string; scale: number }> = {
  today: { days: 1, label: "Today", scale: 0.15 },
  week: { days: 7, label: "The last 7 days", scale: 1 },
  month: { days: 30, label: "The last 30 days", scale: 4.3 },
};
/** A week's figure of each card, and how the period before compared (a fraction up or down). */
const WEEK: Record<string, number> = {
  net_revenue: 184250,
  orders_placed: 212,
  codes_redeemed: 340,
  active_learners: 1260,
  orders_to_pack: 4,
  quotes_open: 3,
  refunds_to_approve: 2,
  bank_refunds_to_pay: 1,
  cod_overdue: 5,
  tickets_due: 6,
  tickets_breached: 1,
  reports_open: 7,
  items_flagged: 2,
  settlement_items_unmatched: 3,
};
/** The same week's figure the week before: the comparison is the difference, so the sentence reads the same each run. */
const BEFORE: Record<string, number> = {
  net_revenue: 151900,
  orders_placed: 221,
  codes_redeemed: 315,
  active_learners: 1260,
};
/** Cards that stand on orders, payments, refunds or parcels (test mode applies). */
const ON_ORDERS = new Set([
  "net_revenue",
  "orders_placed",
  "orders_to_pack",
  "refunds_to_approve",
  "bank_refunds_to_pay",
]);

function home(context: ReportsContext, kit: ReportsKit): Response {
  const asked = context.url.searchParams.get("period") ?? "";
  if (asked && !HOME_PERIODS[asked]) return kit.invalid({ period: ["One of today, week, month."] });
  const key = asked || "week";
  const { days, label, scale } = HOME_PERIODS[key];
  const end = daysAgo(0);
  const span = (length: number, back = 0) => ({
    start: shift(end, -(length - 1) - back),
    end: shift(end, -back),
    days: length,
  });
  const roles = context.who.breakGlass ? ["OWNER"] : [context.who.role];
  const failing = cookie(context.request, "staff_mock_card_error");
  const keys = testKeys(context);
  const cards: S["HomeCard"][] = HOME_SPECS.filter(
    (spec) =>
      spec.roles.some((role) => roles.includes(role)) &&
      spec.needs.every((permission) => context.permissions.includes(permission)) &&
      (spec.key !== "settlement_items_unmatched" || settlementsOn(context)),
  ).map((spec) => {
    const window = spec.days ?? days;
    const base = spec.group === "measure" ? WEEK[spec.key] * (spec.days ? 1 : scale) : WEEK[spec.key];
    const figure = spec.unit === "inr" ? money(base) : String(Math.round(base));
    const before = (BEFORE[spec.key] ?? base) * (spec.days ? 1 : spec.group === "measure" ? scale : 1);
    const difference = base - before;
    const card: S["HomeCard"] = {
      key: spec.key,
      label: spec.label,
      group: spec.group,
      unit: spec.unit,
      value: failing === spec.key ? null : figure,
      definition: spec.definition,
      as_of: new Date().toISOString(),
      period: spec.group === "measure" ? span(window) : null,
      href: spec.href.replace("{period}", `?from=${span(window).start}&to=${span(window).end}`),
      test_mode: keys && ON_ORDERS.has(spec.key),
      comparison:
        spec.compares && failing !== spec.key
          ? {
              previous: spec.unit === "inr" ? money(before) : String(Math.round(before)),
              difference: spec.unit === "inr" ? signed(difference, 2) : signed(Math.round(difference), 0),
              percent: before === 0 ? null : signed((difference / before) * 100, 1),
              period: span(window, window),
            }
          : null,
      error: failing === spec.key ? "This number could not be worked out just now." : "",
    };
    return card;
  });
  const answer: S["Home"] = {
    as_of: new Date().toISOString(),
    period: { ...span(days), key, label },
    test_mode: keys,
    test_orders_left_out: keys ? 0 : 3,
    cards,
  };
  return kit.json(200, answer);
}

// ---- Sales ----

const BOOKS = [
  {
    slug: "physics-sample-papers-2027",
    title: "Physics Sample Papers 2027",
    subject: "Physics",
    klass: "Class 12",
    board: "ASSEB",
    edition: "2027",
    price: 195,
  },
  {
    slug: "chemistry-sample-papers-2027",
    title: "Chemistry Sample Papers 2027",
    subject: "Chemistry",
    klass: "Class 12",
    board: "ASSEB",
    edition: "2027",
    price: 195,
  },
  {
    slug: "mathematics-sample-papers-2027",
    title: "Mathematics Sample Papers 2027",
    subject: "Mathematics",
    klass: "Class 12",
    board: "ASSEB",
    edition: "2027",
    price: 210,
  },
  {
    slug: "physics-sample-papers-class-10-2027",
    title: "Physics Sample Papers, Class 10, 2027",
    subject: "Physics",
    klass: "Class 10",
    board: "SEBA",
    edition: "2027",
    price: 150,
  },
  {
    slug: "physics-solutions-2026",
    title: "Physics Solutions 2026",
    subject: "Physics",
    klass: "Class 12",
    board: "ASSEB",
    edition: "2026",
    price: 120,
  },
];

type Fact = {
  day: string;
  book: (typeof BOOKS)[number];
  orders: number;
  units: number;
  gross: number;
  discount: number;
};

/** The lines sold on each of the last 400 days: a pattern, not a random draw, so a table reads the same each time. */
function facts(period: Period): Fact[] {
  const found: Fact[] = [];
  for (let back = 0; back < 400; back += 1) {
    const day = daysAgo(back);
    if (day < period.start || day > period.end) continue;
    BOOKS.forEach((book, index) => {
      const units = (back * 7 + index * 13 + 3) % 6;
      if (units === 0) return;
      const gross = units * book.price;
      found.push({
        day,
        book,
        orders: Math.ceil(units / 2),
        units,
        gross,
        discount: back % 5 === 0 ? Math.round(gross * 0.1) : 0,
      });
    });
  }
  return found;
}

const BY = ["product", "subject", "class", "board", "edition", "none"];
const GRAINS = ["none", "day", "week", "month"];

function group(book: (typeof BOOKS)[number], by: string): [string, string] {
  if (by === "product") return [book.slug, book.title];
  if (by === "subject") return [book.subject, book.subject];
  if (by === "class") return [book.klass, book.klass];
  if (by === "board") return [book.board, book.board];
  if (by === "edition") return [book.edition, `Edition ${book.edition}`];
  return ["all", "Everything together"];
}

function bucket(day: string, grain: string): string | null {
  if (grain === "day") return day;
  if (grain === "week") return monday(day);
  if (grain === "month") return firstOfMonth(day);
  return null;
}

function salesRows(context: ReportsContext, period: Period, by: string, grain: string) {
  const rows = new Map<string, S["ReportSalesRow"]>();
  const total = { orders: 0, units: 0, gross: 0, discount: 0 };
  for (const fact of facts(period)) {
    const [key, label] = group(fact.book, by);
    const start = bucket(fact.day, grain);
    const id = `${key}|${start ?? ""}`;
    const row = rows.get(id) ?? {
      key,
      label,
      period_start: start,
      orders: 0,
      units: 0,
      gross: "0.00",
      discount: "0.00",
      net: "0.00",
    };
    const gross = Number(row.gross) + fact.gross;
    const discount = Number(row.discount) + fact.discount;
    rows.set(id, {
      ...row,
      orders: row.orders + fact.orders,
      units: row.units + fact.units,
      gross: money(gross),
      discount: money(discount),
      net: money(gross - discount),
    });
    total.orders += fact.orders;
    total.units += fact.units;
    total.gross += fact.gross;
    total.discount += fact.discount;
  }
  void context;
  const table = [...rows.values()].sort(
    (a, b) =>
      (a.period_start ?? "").localeCompare(b.period_start ?? "") ||
      Number(b.net) - Number(a.net) ||
      a.label.localeCompare(b.label),
  );
  return {
    table,
    totals: {
      orders: total.orders,
      units: total.units,
      gross: money(total.gross),
      discount: money(total.discount),
      net: money(total.gross - total.discount),
    },
  };
}

function sales(context: ReportsContext, kit: ReportsKit): Response {
  const period = periodOf(context);
  if (!isPeriod(period)) return period;
  const by = context.url.searchParams.get("by") || "product";
  const grain = context.url.searchParams.get("grain") || "none";
  if (!BY.includes(by)) return kit.invalid({ by: [`"${by}" is not a valid choice.`] });
  if (!GRAINS.includes(grain)) return kit.invalid({ grain: [`"${grain}" is not a valid choice.`] });
  const { table, totals } = salesRows(context, period, by, grain);
  const answer: S["ReportSales"] = { ...envelope(context, "sales", period), by, grain, totals, rows: table };
  return kit.json(200, answer);
}

// ---- Sales by place ----

type Pins = [string, number][]; // PIN code, its orders in 30 days
const PLACES: { state: string; name: string; districts: [string, Pins][] }[] = [
  {
    state: "AS",
    name: "Assam",
    districts: [
      [
        "Kamrup Metro",
        [
          ["781001", 31],
          ["781005", 18],
          ["781006", 7],
        ],
      ],
      ["Jorhat", [["785001", 22]]],
      ["Dibrugarh", [["786001", 14]]],
      ["Dhemaji", [["787057", 4]]],
    ],
  },
  {
    state: "WB",
    name: "West Bengal",
    districts: [
      [
        "Kolkata",
        [
          ["700001", 19],
          ["700019", 12],
        ],
      ],
      ["Howrah", [["711101", 8]]],
    ],
  },
  { state: "MH", name: "Maharashtra", districts: [["Pune", [["411001", 11]]]] },
  { state: "SK", name: "Sikkim", districts: [["Gangtok", [["737101", 3]]]] },
];

function place(context: ReportsContext, kit: ReportsKit): Response {
  const period = periodOf(context);
  if (!isPeriod(period)) return period;
  const level = context.url.searchParams.get("level") || "state";
  const only = (context.url.searchParams.get("state") || "").toUpperCase();
  if (!["state", "district", "pin"].includes(level))
    return kit.invalid({ level: [`"${level}" is not a valid choice.`] });
  if (only && !PLACES.some((each) => each.state === only))
    return kit.invalid({ state: ["A state's code: AS for Assam."] });
  const scale = period.days / 30;
  const orders = (base: number) => Math.round(base * scale);
  type Cell = {
    label: string;
    state: string;
    stateName: string;
    district: string | null;
    pin: string | null;
    orders: number;
  };
  const cells: Cell[] = [];
  for (const each of PLACES) {
    if (only && each.state !== only) continue;
    if (level === "state") {
      const total = each.districts.flatMap(([, pins]) => pins).reduce((sum, [, base]) => sum + orders(base), 0);
      cells.push({
        label: each.name,
        state: each.state,
        stateName: each.name,
        district: null,
        pin: null,
        orders: total,
      });
    }
    for (const [district, pins] of each.districts) {
      if (level === "district")
        cells.push({
          label: district,
          state: each.state,
          stateName: each.name,
          district,
          pin: null,
          orders: pins.reduce((sum, [, base]) => sum + orders(base), 0),
        });
      if (level === "pin")
        for (const [pin, base] of pins)
          cells.push({ label: pin, state: each.state, stateName: each.name, district, pin, orders: orders(base) });
    }
  }
  const rows: S["ReportPlaceRow"][] = cells
    .map((cell) => {
      const hidden = cell.orders > 0 && cell.orders < MIN_CELL;
      return {
        hidden,
        under: hidden ? MIN_CELL : null,
        level,
        state: cell.state,
        state_name: cell.stateName,
        district: cell.district,
        pin: cell.pin,
        label: cell.label,
        orders: hidden ? null : cell.orders,
        units: hidden ? null : Math.round(cell.orders * 1.6),
        net: hidden ? null : money(cell.orders * 340),
      };
    })
    .sort(
      (a, b) =>
        Number(a.hidden) - Number(b.hidden) || (b.orders ?? 0) - (a.orders ?? 0) || a.label.localeCompare(b.label),
    );
  const shown = rows.filter((row) => !row.hidden);
  const answer: S["ReportPlace"] = {
    ...envelope(context, "sales-by-place", period),
    level,
    state: only,
    minimum: MIN_CELL,
    hidden_rows: rows.length - shown.length,
    totals_shown: {
      orders: shown.reduce((sum, row) => sum + (row.orders ?? 0), 0),
      units: shown.reduce((sum, row) => sum + (row.units ?? 0), 0),
      net: money(shown.reduce((sum, row) => sum + Number(row.net ?? 0), 0)),
    },
    rows,
  };
  return kit.json(200, answer);
}

// ---- Book codes ----

const BATCHES = [
  { batch: "PHY-2027-1", printed: 5000, sold: 4200, activated: 1850, recent: 140, void: 12 },
  { batch: "CHE-2027-1", printed: 3000, sold: null, activated: 640, recent: 55, void: null },
  { batch: "MAT-2027-1", printed: 2000, sold: 1900, activated: 90, recent: 31, void: 0 },
];
const DISTRICTS = [
  ["Kamrup Metro", 410, 38],
  ["Jorhat", 220, 17],
  ["Dibrugarh", 130, 9],
  ["Sivasagar", 9, 1],
  ["Dhemaji", 6, 0],
] as const;

function codes(context: ReportsContext, kit: ReportsKit): Response {
  const batch = context.url.searchParams.get("batch") ?? "";
  if (batch && !BATCHES.some((each) => each.batch === batch)) return kit.invalid({ batch: ["No such print run."] });
  const share = batch ? BATCHES.find((each) => each.batch === batch)!.activated / 2580 : 1;
  const districts: S["ReportCodesDistrict"][] = DISTRICTS.map(([district, redeemed, recent]) => {
    const total = Math.round(redeemed * share);
    const hidden = total > 0 && total < MIN_CELL;
    return {
      hidden,
      under: hidden ? MIN_CELL : null,
      district,
      redeemed: hidden ? null : total,
      redeemed_7d: hidden ? null : Math.round(recent * share),
    };
  });
  const answer: S["ReportCodes"] = {
    ...envelope(context, "codes", null),
    batch,
    minimum: MIN_CELL,
    districts_computed_at: new Date(Date.now() - 6 * 3_600_000).toISOString(),
    districts,
    rows: BATCHES.map((each) => ({
      batch: each.batch,
      printed: each.printed,
      sold: each.sold,
      activated: each.activated,
      activated_7d: each.recent,
      void: each.void,
      activation_rate: (each.activated / each.printed).toFixed(4),
    })),
  };
  return kit.json(200, answer);
}

// ---- Course health ----

const SUBJECTS = [
  { id: 1, name: "Physics", chapters: ["Electric charges and fields", "Current electricity", "Magnetism", "Optics"] },
  { id: 2, name: "Chemistry", chapters: ["Solutions", "Electrochemistry", "Chemical kinetics"] },
  { id: 3, name: "Mathematics", chapters: ["Relations and functions", "Matrices", "Integrals"] },
];

function health(context: ReportsContext, kit: ReportsKit): Response {
  const grain = context.url.searchParams.get("grain") || "week";
  if (!["day", "week", "month"].includes(grain)) return kit.invalid({ grain: [`"${grain}" is not a valid choice.`] });
  const subject = Number(context.url.searchParams.get("subject")) || null;
  const chapter = Number(context.url.searchParams.get("chapter")) || null;
  if (subject && !SUBJECTS.some((each) => each.id === subject)) return kit.invalid({ subject: ["No such subject."] });
  const empty = cookie(context.request, "staff_mock_health") === "empty";
  const length = grain === "day" ? 14 : grain === "week" ? 12 : 6;
  const factor = subject ? 0.35 : 1;
  const series: S["ReportHealthPoint"][] = empty
    ? []
    : Array.from({ length }, (_, index) => {
        const back = length - 1 - index;
        const start =
          grain === "day"
            ? daysAgo(back + 1)
            : grain === "week"
              ? monday(daysAgo(7 * back + 7))
              : firstOfMonth(daysAgo(30 * back + 30));
        const learners = Math.round(
          (900 + 220 * Math.sin(index / 2) + index * 12) *
            factor *
            (grain === "day" ? 0.45 : grain === "week" ? 1 : 2.4),
        );
        const hidden = index === 2;
        return {
          hidden,
          under: hidden ? MIN_CLASS : null,
          period_start: start,
          active_learners: hidden ? null : learners,
          clips_completed: hidden ? null : Math.round(learners * 1.7),
          quiz_answers: hidden ? null : Math.round(learners * 6.2),
          quiz_accuracy: hidden ? null : (0.62 + (index % 4) * 0.03).toFixed(4),
          card_reviews: hidden ? null : Math.round(learners * 4.1),
          card_lapses: hidden ? null : Math.round(learners * 0.9),
          smoothed_7: grain === "day" && !hidden ? (learners * 0.98).toFixed(1) : null,
          smoothed_28: grain === "day" && !hidden ? (learners * 0.94).toFixed(1) : null,
        };
      });
  const chapters = SUBJECTS.flatMap((each) =>
    each.chapters.map((title, index) => ({
      subject: each.id,
      name: each.name,
      chapter: each.id * 100 + index + 1,
      number: index + 1,
      title,
    })),
  ).filter((each) => (!subject || each.subject === subject) && (!chapter || each.chapter === chapter));
  const rows: S["ReportHealthChapter"][] = empty
    ? []
    : chapters.map((each, index) => {
        const hidden = index === 5;
        const learners = 180 - index * 11;
        return {
          hidden,
          under: hidden ? MIN_CLASS : null,
          subject: each.subject,
          chapter: each.chapter,
          number: each.number,
          title: each.title,
          label: `${each.name} ${each.number}: ${each.title}`,
          active_7d: hidden ? null : learners,
          active_28d: hidden ? null : Math.round(learners * 2.3),
          clips_started: hidden ? null : Math.round(learners * 3.1),
          clips_completed: hidden ? null : Math.round(learners * 2.2),
          completion_rate: hidden ? null : "0.7100",
          quiz_answers: hidden ? null : learners * 9,
          quiz_accuracy: hidden ? null : (0.58 + (index % 5) * 0.04).toFixed(4),
          card_reviews: hidden ? null : learners * 6,
          card_lapses: hidden ? null : learners,
        };
      });
  const answer: S["ReportHealth"] = {
    ...envelope(context, "course-health", null),
    grain,
    computed_at: empty ? null : new Date(Date.now() - 6 * 3_600_000).toISOString(),
    minimum: MIN_CLASS,
    subject,
    chapter,
    subjects: SUBJECTS.map((each) => ({ id: each.id, name: each.name })),
    whole_course: !subject,
    series,
    codes_by_week: empty
      ? []
      : Array.from({ length: 6 }, (_, index) => {
          const hidden = index === 1;
          return {
            hidden,
            under: hidden ? MIN_CLASS : null,
            week_start: monday(daysAgo(7 * (5 - index) + 7)),
            redeemed: hidden ? null : 40 + index * 9,
          };
        }),
    rows,
  };
  return kit.json(200, answer);
}

// ---- Cash on delivery ----

function cod(context: ReportsContext, kit: ReportsKit): Response {
  const period = periodOf(context);
  if (!isPeriod(period)) return period;
  const answer: S["ReportCod"] = {
    ...envelope(context, "cod", period),
    as_of_day: daysAgo(0),
    remitted: { count: 14, expected: "11200.00", received: "11150.00", difference: "-50.00" },
    by_courier: [
      { courier: "India Post", count: 9, expected: "5900.00", overdue: 3 },
      { courier: "Delhivery", count: 4, expected: "2300.00", overdue: 1 },
    ],
    rows: [
      { key: "not_due", label: "Not yet due", count: 6, expected: "3150.00", oldest_expected_on: shift(daysAgo(0), 2) },
      {
        key: "late_1_7",
        label: "1 to 7 days late",
        count: 4,
        expected: "2400.00",
        oldest_expected_on: shift(daysAgo(0), -6),
      },
      {
        key: "late_8_30",
        label: "8 to 30 days late",
        count: 2,
        expected: "1700.00",
        oldest_expected_on: shift(daysAgo(0), -19),
      },
      {
        key: "late_31",
        label: "More than 30 days late",
        count: 1,
        expected: "950.00",
        oldest_expected_on: shift(daysAgo(0), -44),
      },
    ],
  };
  return kit.json(200, answer);
}

// ---- Settlements ----

function settlements(context: ReportsContext, kit: ReportsKit): Response {
  const period = periodOf(context, 90);
  if (!isPeriod(period)) return period;
  const configured = settlementsOn(context);
  if (configured && !context.permissions.includes("shop.view_settlement")) return kit.refuse("shop.view_settlement");
  const states = ["posted", "posted", "matched", "mismatched", "fetched"];
  const answer: S["ReportSettlements"] = {
    ...envelope(context, "settlements", period),
    configured,
    note: configured ? "" : "Razorpay's settlements are not set up yet: the Finance module fetches them.",
    rows: configured
      ? states
          .map((state, index) => ({
            reference: `setl_Nx${4100 + index}Qa`,
            date: shift(daysAgo(0), -(index * 2 + 1)),
            gross: money(48200 - index * 6150),
            fees: money(947.5 - index * 120),
            tax: money(170.55 - index * 21.6),
            refunds: money(index === 3 ? 1200 : 0),
            net: money(47081.95 - index * 6008.4 - (index === 3 ? 1200 : 0)),
            utr: `HDFCR5202610${String(1700 + index)}`,
            state,
          }))
          .filter((row) => row.date >= period.start && row.date <= period.end)
      : [],
  };
  return kit.json(200, answer);
}

// ---- The index ----

function index(context: ReportsContext, kit: ReportsKit): Response {
  const answer: S["ReportIndex"] = {
    test_mode: testKeys(context),
    reports: REPORT_INDEX.map((each) => {
      const needs = each.needs.includes("staff.view_insights") ? each.needs : ["staff.view_insights", ...each.needs];
      return {
        key: each.key,
        label: each.label,
        summary: each.summary,
        page: each.page,
        api:
          each.key === "cohorts" || each.key === "forecasts"
            ? `/api/v1/insights/${each.key}/`
            : `/api/v1/staff/reports/${each.key === "course-health" ? "course-health" : each.key}/`,
        needs,
        available: needs.every((permission) => context.permissions.includes(permission)),
        configured: each.key !== "settlements" || settlementsOn(context),
      };
    }),
  };
  return kit.json(200, answer);
}

// ---- The insights' own lists ----

const WEEKS = 18;
const RUNS = [
  {
    product: "physics-sample-papers-2027",
    title: "Physics Sample Papers 2027",
    net: 195,
    cost: 60,
    salvage: 5,
    target: 1240,
    supply: 540,
    trigger: 380,
    cover: 9.5,
    leftover: 85,
    level: "act",
    p50: 56,
  },
  {
    product: "chemistry-sample-papers-2027",
    title: "Chemistry Sample Papers 2027",
    net: 195,
    cost: 62,
    salvage: 5,
    target: 620,
    supply: 700,
    trigger: 210,
    cover: null,
    leftover: 120,
    level: "ok",
    p50: 30,
  },
  {
    product: "mathematics-sample-papers-2027",
    title: "Mathematics Sample Papers 2027",
    net: 210,
    cost: 70,
    salvage: 6,
    target: 910,
    supply: 640,
    trigger: 300,
    cover: 11.2,
    leftover: 40,
    level: "watch",
    p50: 41,
  },
] as const;

function ratio(net: number, cost: number, salvage: number): number {
  const under = net - cost;
  const over = cost - salvage;
  if (under <= 0) return 0;
  if (over <= 0) return 1;
  return under / (under + over);
}

const Z90 = 1.2815515655;
/** The standard normal's inverse CDF (Abramowitz and Stegun 26.2.23: good to 5e-4, plenty for a mock). */
function normalInverse(p: number): number {
  const q = Math.min(Math.max(p, 0.001), 0.999);
  const t = Math.sqrt(-2 * Math.log(q < 0.5 ? q : 1 - q));
  const x =
    t - (2.515517 + 0.802853 * t + 0.010328 * t * t) / (1 + 1.432788 * t + 0.189269 * t * t + 0.001308 * t * t * t);
  return q < 0.5 ? -x : x;
}

/** insights.stats.quantile_between: a log-normal through P10, P50 and P90, each side with its own spread. */
function quantileBetween(p10: number, p50: number, p90: number, q: number): number {
  if (p50 <= 0) return 0;
  const z = normalInverse(q);
  const edge = z >= 0 ? p90 : p10;
  return edge <= 0 ? 0 : p50 * (edge / p50) ** (Math.abs(z) / Z90);
}

const backtest = (context: ReportsContext) => ({
  horizon_weeks: 4,
  wape: 0.31,
  mase_vs_seasonal_naive: cookie(context.request, "staff_mock_untested") === "1" ? 1.14 : 0.82,
  shown: cookie(context.request, "staff_mock_untested") !== "1",
  n_weeks: 48,
  data_as_of: new Date(Date.now() - 20 * 3_600_000).toISOString(),
});

/** A forecast week for a title: this week's Monday on, rising towards the exam. */
const weekly = (run: (typeof RUNS)[number], week: number) => {
  const p50 = Math.round(run.p50 * (0.7 + 0.5 * Math.sin((week / WEEKS) * Math.PI)) + week);
  return {
    week_start: monday(shift(daysAgo(0), 7 * week)),
    p10: Math.round(p50 * 0.62),
    p50,
    p90: Math.round(p50 * 1.48),
  };
};

function numbered<T>(context: ReportsContext, kit: ReportsKit, rows: T[], extra: Record<string, unknown>): Response {
  const size = Math.min(200, Number(context.url.searchParams.get("page_size")) || 50);
  const page = Number(context.url.searchParams.get("page")) || 1;
  const pages = Math.max(1, Math.ceil(rows.length / size));
  if (page < 1 || page > pages)
    return Response.json({ detail: "Invalid page." }, { status: 404, headers: { "Cache-Control": "no-store" } });
  const link = (to: number) => {
    const next = new URL(context.url.href);
    next.searchParams.set("page", String(to));
    return next.href;
  };
  return kit.json(200, {
    ...extra,
    count: rows.length,
    next: page < pages ? link(page + 1) : null,
    previous: page > 1 ? link(page - 1) : null,
    results: rows.slice((page - 1) * size, page * size),
  });
}

function insights(context: ReportsContext, kit: ReportsKit): Response {
  const [, list] = context.parts;
  if (context.method !== "GET") return kit.notFound();
  const test = backtest(context);
  const about = (method: string, predicts: boolean) => ({
    method,
    data_as_of: new Date(Date.now() - 20 * 3_600_000).toISOString(),
    backtest: predicts ? test : null,
    shown: predicts ? test.shown : true,
  });
  if (list === "print-runs")
    return numbered(
      context,
      kit,
      RUNS.map((run) => ({
        product: run.product,
        title: run.title,
        net_price: money(run.net),
        unit_cost: money(run.cost),
        salvage: money(run.salvage),
        critical_ratio: ratio(run.net, run.cost, run.salvage),
        target_quantity: run.target,
        supply: run.supply,
        recommended_quantity: Math.max(0, run.target - run.supply),
        reprint_trigger_units: run.trigger,
        weeks_of_cover: run.cover,
        projected_leftover: run.leftover,
        level: run.level,
        alert: run.level === "act" ? "Reprint now: the copies in hand run out before the exam." : "",
        n: 1210,
      })),
      about("seasonal naive by week of season × damped growth, then the newsvendor's quantile", true),
    );
  if (list === "forecasts") {
    const product = context.url.searchParams.get("product") ?? "";
    const chosen = RUNS.filter((run) => !product || run.product === product);
    return numbered(
      context,
      kit,
      chosen.flatMap((run) =>
        Array.from({ length: WEEKS }, (_, week) => ({
          product: run.product,
          title: run.title,
          district: null,
          ...weekly(run, week),
          n: 1210,
        })),
      ),
      about("seasonal naive by week of season × damped growth", true),
    );
  }
  if (list === "cohorts") {
    const rows = [0, 1, 2].flatMap((back) =>
      ["book_code", "purchase"].flatMap((source) =>
        Array.from({ length: Math.max(1, 6 - back * 2) }, (_, week) => {
          const n = Math.max(0, Math.round((source === "book_code" ? 140 : 40) * (1 - back * 0.25) - week * 4));
          const hidden = n < MIN_CELL;
          return {
            cohort_month: `${shift(daysAgo(0), -30 * back).slice(0, 7)}-01`,
            source,
            week_index: week,
            active_share: hidden ? null : 0.72 - week * 0.07,
            churned_share: hidden || week === 0 ? null : 0.05 + week * 0.04,
            n,
            hidden,
            under: hidden ? MIN_CELL : null,
          };
        }),
      ),
    );
    return numbered(
      context,
      kit,
      rows,
      about(
        "share active each week since the course opened, and gone quiet 14 days, while the exam is ahead (n ≥ 10)",
        false,
      ),
    );
  }
  return kit.notFound();
}

// ---- The print run, worked out again ----

const MONEY = /^\d{1,8}(\.\d{1,2})?$/;

function printRun(context: ReportsContext, kit: ReportsKit): Response {
  const body = context.body;
  const field = (name: string, fallback?: string) =>
    typeof body[name] === "string" || typeof body[name] === "number" ? String(body[name]).trim() : fallback;
  const errors: Record<string, string[]> = {};
  for (const name of ["product", "net_price", "unit_cost"])
    if (!field(name)) errors[name] = ["This field is required."];
  for (const name of ["net_price", "unit_cost", "salvage"]) {
    const value = field(name, name === "salvage" ? "0.00" : undefined);
    if (value && !MONEY.test(value)) errors[name] = ["A valid number is required."];
  }
  if (Object.keys(errors).length) return kit.invalid(errors);
  const run = RUNS.find((each) => each.product === field("product"));
  if (!run) return kit.invalid({ product: ["No such title."] });
  const net = Number(field("net_price"));
  const cost = Number(field("unit_cost"));
  const salvage = Number(field("salvage", "0.00"));
  const critical = ratio(net, cost, salvage);
  const weeks = Array.from({ length: WEEKS }, (_, week) => weekly(run, week));
  const [p10, p50, p90] = (["p10", "p50", "p90"] as const).map((name) =>
    weeks.reduce((sum, week) => sum + week[name], 0),
  );
  const target = critical > 0 ? Math.ceil(quantileBetween(p10, p50, p90, critical)) : 0;
  const untested = cookie(context.request, "staff_mock_untested") === "1";
  const test = backtest(context);
  const answer: S["ReportPrintRun"] = {
    product: run.product,
    title: run.title,
    net_price: money(net),
    unit_cost: money(cost),
    salvage: money(salvage),
    critical_ratio: Math.round(critical * 10_000) / 10_000,
    percentile: Math.round(critical * 100),
    target_quantity: target,
    supply: run.supply,
    recommended_quantity: Math.max(0, target - run.supply),
    range: { p10, p50, p90, weeks: WEEKS },
    method: "seasonal naive by week of season × damped growth",
    data_as_of: new Date(Date.now() - 20 * 3_600_000).toISOString(),
    backtest: test,
    shown: !untested,
    note: critical === 0 ? "At this net price a copy sells at a loss: print none." : "",
  };
  return kit.json(200, answer);
}

// ---- The route ----

export function reportsRoute(context: ReportsContext, kit: ReportsKit): Response {
  const [area, a] = context.parts;
  const { method } = context;
  if (area === "home") return method === "GET" ? home(context, kit) : kit.notFound();
  if (area === "insights") return insights(context, kit);
  if (!a) return method === "GET" ? index(context, kit) : kit.notFound();
  const needs = REPORT_NEEDS[a];
  if (!needs || (a === "print-run") !== (method === "POST")) return kit.notFound();
  const missing = needs.find((permission) => !context.permissions.includes(permission));
  if (missing) return kit.refuse(missing);
  if (a === "print-run") return printRun(context, kit);
  if (a === "sales") return sales(context, kit);
  if (a === "sales-by-place") return place(context, kit);
  if (a === "codes") return codes(context, kit);
  if (a === "course-health") return health(context, kit);
  if (a === "cod") return cod(context, kit);
  if (a === "settlements") return settlements(context, kit);
  return kit.notFound();
}

// ---- Exports ----

/** The rows a report would put in a file, to count and to write. */
function exported(context: ReportsContext, kit: ReportsKit, report: string, filters: Record<string, string>) {
  const here: ReportsContext = {
    ...context,
    method: "GET",
    url: new URL(`${context.url.origin}/api/v1/staff/reports/${report}/?${new URLSearchParams(filters)}`),
  };
  const call: Record<string, () => Response> = {
    sales: () => sales(here, kit),
    "sales-by-place": () => place(here, kit),
    codes: () => codes(here, kit),
    "course-health": () => health(here, kit),
    cod: () => cod(here, kit),
    settlements: () => settlements(here, kit),
    cohorts: () => insights({ ...here, parts: ["insights", "cohorts"] }, kit),
    forecasts: () => insights({ ...here, parts: ["insights", "forecasts"] }, kit),
  };
  return call[report]?.();
}

/** POST jobs/ {kind: "report_export", params: {report, filters}}: the report and its filters checked before anything
 *  is queued (a 400 names the filter), the report's own permissions required of the starter. */
export async function startReportExport(context: ReportsContext, kit: ReportsKit): Promise<Response> {
  const params = (context.body.params ?? {}) as Body;
  const report = typeof params.report === "string" ? params.report : "";
  if (!(report in FILTERS)) return kit.invalid({ params: { report: ["No such report."] } });
  const filters = (params.filters && typeof params.filters === "object" ? params.filters : {}) as Record<
    string,
    unknown
  >;
  const unknown = Object.keys(filters).filter((name) => !FILTERS[report].includes(name));
  if (unknown.length) return kit.invalid({ params: { filters: [`The report does not take ${unknown.join(", ")}.`] } });
  const missing = ["staff.view_insights", ...REPORT_NEEDS[report]].find(
    (permission) => !context.permissions.includes(permission),
  );
  if (missing) return kit.refuse(missing);
  const answered = exported(
    context,
    kit,
    report,
    Object.fromEntries(Object.entries(filters).map(([name, value]) => [name, String(value)])),
  );
  if (!answered || !answered.ok) return answered ?? kit.notFound();
  const body = (await answered.json()) as { rows?: unknown[]; results?: unknown[] };
  const rows = (body.rows ?? body.results ?? []).map((_, row) => String(row));
  const job = kit.startJob(context, "report_export", { report, filters }, rows);
  job._result = { rows: rows.length, report };
  kit.record(context, "report.exported", {
    target_type: "staff.job",
    target_id: String(job.id),
    target_label: `Report ${report}`,
    details: { report, filters, rows: rows.length },
  } as Partial<S["AuditEvent"]>);
  return kit.json(202, kit.visibleJob(context, job));
}

const SAFE = /^[=+\-@\t\r]/;
/** A cell as insights/exports.py writes it: text a spreadsheet would run as a formula is made text, a number passes. */
const cell = (value: unknown): string => {
  const text = value === null || value === undefined ? "" : String(value);
  const escaped = typeof value === "string" && SAFE.test(text) ? `'${text}` : text;
  return /[",\n]/.test(escaped) ? `"${escaped.replace(/"/g, '""')}"` : escaped;
};

/** A done export's file, as the backend writes it: the report's columns as the header, the rows as the page showed them
 *  (a hidden cell as "fewer than 10"), an empty line, and who made it, when, and with which filters. */
export async function reportFile(context: ReportsContext, kit: ReportsKit, job: MockJob): Promise<Response> {
  const params = (job.params ?? {}) as { report?: string; filters?: Record<string, string> };
  const report = params.report ?? "sales";
  const filters = params.filters ?? {};
  const answered = exported(context, kit, report, filters);
  const body = answered?.ok
    ? ((await answered.json()) as {
        rows?: Record<string, unknown>[];
        results?: Record<string, unknown>[];
        period?: Period | null;
      })
    : {};
  const columns = REPORT_WORDS[report]?.columns ?? [];
  const lines = [columns.map((column) => cell(column.label)).join(",")];
  for (const row of body.rows ?? body.results ?? [])
    lines.push(
      columns
        .map((column) =>
          row.hidden === true && row[column.key] === null ? `fewer than ${row.under}` : cell(row[column.key]),
        )
        .join(","),
    );
  const made = new Date(Date.now() + IST).toISOString();
  const named = Object.entries(filters)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([name, value]) => `${name}=${value}`)
    .join(", ");
  lines.push(
    "",
    [
      "Report",
      REPORT_INDEX.find((each) => each.key === report)?.label ?? report,
      `made ${made.slice(0, 10)} ${made.slice(11, 16)} by staff member #${context.who.id}`,
      `filters: ${named || "none"}`,
    ]
      .map(cell)
      .join(","),
  );
  const span = body.period ? `${body.period.start}-to-${body.period.end}-` : "";
  return new Response(`${lines.join("\n")}\n`, {
    headers: {
      "Content-Type": "text/csv",
      "Content-Disposition": `attachment; filename="report-${report}-${span}made-${dayOf(Date.now()).replaceAll("-", "")}.csv"`,
      "Cache-Control": "no-store",
    },
  });
}
