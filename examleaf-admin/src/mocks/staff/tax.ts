// FIXTURES FOR DEVELOPMENT AND TESTS ONLY: the tax module's world (examleaf-web shop/staff_tax.py's shapes) and the
// rules the mock answers it by, as shop/tax.py keeps them: a rate's day decides a code's rate today, table 13 is
// counted from the documents, the calendar from the law's dates. Every state the console draws: a code with a change
// to come, one with no rate today, products that disagree; invoices of the three types, one cancelled, one missing
// what Rule 46 asks, one with a credit note, a test-series one; a threshold crossed. Sample numbers, not real ones.
import type { MockSchemas } from "./fixtures";

type S = MockSchemas;

export type TaxWorld = {
  codes: S["HsnCodeDetail"][];
  problems: S["TaxProblem"][];
  documents: S["TaxDocumentDetail"][];
  card: S["ThresholdCard"];
  qrmp: boolean;
};

export const SERIES_FROM = "2027-28"; // settings.SHOP_SERIES_FROM_FY
export const PREFIXES: Record<string, string> = {
  tax_invoice: "TI",
  bill_of_supply: "BS",
  invoice_cum_bill_of_supply: "IB",
  credit_note: "CN",
  debit_note: "DN",
  receipt_voucher: "RV",
  refund_voucher: "RF",
};
const NATURES: Record<string, string> = { credit_note: "Credit Note" };
const QUARTERS: Record<number, string> = {
  6: "April to June",
  9: "July to September",
  12: "October to December",
  3: "January to March",
};
const MONTHS = ["January", "February", "March", "April", "May", "June", "July"].concat([
  "August",
  "September",
  "October",
  "November",
  "December",
]);

/** India's day of a moment: "2026-10-09". */
export const dayOf = (moment: number) => new Date(moment + 5.5 * 3_600_000).toISOString().slice(0, 10);

/** The financial year of a day: "2026-10-09" → "2026-27". */
export function yearOf(day: string): string {
  const [year, month] = day.split("-").map(Number);
  const start = month >= 4 ? year : year - 1;
  return `${start}-${String((start + 1) % 100).padStart(2, "0")}`;
}

/** A code's rates in order, each with its end (`until`), and its brief rate today and next change, on `today`. */
export function refreshCode(code: S["HsnCodeDetail"], today: string) {
  code.rates.sort((a, b) => a.effective_from.localeCompare(b.effective_from));
  code.rates.forEach((rate, index) => {
    const next = code.rates[index + 1];
    const before = next
      ? new Date(Date.parse(`${next.effective_from}T00:00:00Z`) - 86_400_000).toISOString().slice(0, 10)
      : null;
    (rate as S["HsnRate"]).until = rate.effective_to ?? before;
  });
  const brief = (rate: S["HsnRate"]) => ({
    rate: rate.rate,
    taxability: rate.taxability,
    effective_from: rate.effective_from,
    notification: rate.notification,
  });
  const current = code.rates.filter((rate) => rate.effective_from <= today && (!rate.until || rate.until >= today));
  const later = code.rates.find((rate) => rate.effective_from > today);
  code.today = current.length ? brief(current[current.length - 1]) : null;
  code.next_change = later ? brief(later) : null;
  code.products = code.linked.length;
}

/** What is due in a month (shop/tax.py `calendar`, the seller in Assam): "2026-10". */
export function calendarOf(month: string, qrmp: boolean, today: string): S["TaxCalendarItem"][] {
  const [year, number] = month.split("-").map(Number);
  const filedYear = number === 1 ? year - 1 : year;
  const filed = number === 1 ? 12 : number - 1;
  const period = `${MONTHS[filed - 1]} ${filedYear}`;
  const label = (start: number) => `${start}-${String((start + 1) % 100).padStart(2, "0")}`;
  const items: S["TaxCalendarItem"][] = [];
  const due = (day: number, key: string, title: string, covers: string, note: string, applies = true) => {
    const when = `${month}-${String(day).padStart(2, "0")}`;
    items.push({ key, title, covers, due: when, applies, note, past: when < today });
  };
  if (!qrmp) {
    due(11, "gstr1", "GSTR-1", period, "Every invoice and credit note of the month (the export).");
    due(20, "gstr3b", "GSTR-3B", period, "Its tax comes from GSTR-1 and cannot be edited.");
  } else if (QUARTERS[filed]) {
    const quarter = `${QUARTERS[filed]} ${filedYear}`;
    due(13, "gstr1", "GSTR-1 (quarterly, QRMP)", quarter, "The quarter's invoices and credit notes.");
    due(24, "gstr3b", "GSTR-3B (quarterly, QRMP)", quarter, "Its tax comes from GSTR-1.");
  } else {
    due(13, "iff", "IFF (optional, QRMP)", period, "Only invoices to registered buyers: the storefront has none.");
    due(25, "pmt06", "PMT-06 tax payment (QRMP)", period, "The month's tax, by the fixed sum or as worked out.");
  }
  if (number === 11)
    due(
      30,
      "credit_note_cutoff",
      "Last day for credit notes",
      `Invoices of FY ${label(year - 1)}`,
      "Credit notes after it are refused; declare November's in a return filed by today.",
    );
  if (number === 12)
    due(31, "gstr9", "GSTR-9 annual return", `FY ${label(year - 1)}`, "Required above ₹2 crore of turnover.", false);
  if (number === 10)
    due(
      qrmp ? 24 : 20,
      "rule42",
      "Rule 42 true-up",
      `FY ${label(year - 1)}`,
      "The year's reversal of common input tax credit, in the September return.",
    );
  const tds: Record<number, [number, string]> = {
    7: [31, "April to June"],
    10: [31, "July to September"],
    1: [31, "October to December"],
    5: [31, "January to March"],
  };
  if (tds[number])
    due(
      tds[number][0],
      "tds",
      "Quarterly TDS statement",
      `${tds[number][1]} ${number === 1 || number === 5 ? year - 1 : year}`,
      "Tax deducted from vendors' payments.",
    );
  return items.sort((a, b) => a.due.localeCompare(b.due) || a.key.localeCompare(b.key));
}

/** Table 13 of a year, or of a month of it, counted from the real series' documents. */
export function seriesOf(world: TaxWorld, year: string, month: string | null): S["SeriesRow"][] {
  const rows: S["SeriesRow"][] = [];
  for (const kind of ["invoice", "credit_note"] as const) {
    const found = world.documents.filter(
      (row) => row.kind === kind && !row.test && row.financial_year === year && (!month || row.date.startsWith(month)),
    );
    for (const series of [...new Set(found.map((row) => row.series))].sort()) {
      const mine = found.filter((row) => row.series === series).sort((a, b) => a.serial - b.serial);
      const all = world.documents.filter((row) => row.series === series && row.financial_year === year && !row.test);
      const type =
        kind === "credit_note"
          ? "credit_note"
          : (Object.entries(PREFIXES).find(([, prefix]) => prefix === series)?.[0] ?? "invoice");
      rows.push({
        series,
        nature: NATURES[type] ?? "Invoices for outward supply",
        document_type: type as S["SeriesRow"]["document_type"],
        financial_year: year,
        first: mine[0].number,
        last: mine[mine.length - 1].number,
        total: mine.length,
        cancelled: mine.filter((row) => row.cancelled_at).length,
        next_number: Math.max(...all.map((row) => row.serial)) + 1,
      });
    }
  }
  return rows;
}

/** A document as the list gives it: its detail's own fields only. */
export function documentRow(row: S["TaxDocumentDetail"]): S["TaxDocument"] {
  const { title, lines, charges, round_off, checks, credit_notes, ...listed } = row;
  void [title, lines, charges, round_off, checks, credit_notes];
  return listed;
}

/** A code as the master's list gives it: without its history and products. */
export function codeRow(row: S["HsnCodeDetail"]): S["HsnCode"] {
  const { rates, linked, ...listed } = row;
  void [rates, linked];
  return listed;
}

const longDate = (day: string) => {
  const [year, month, date] = day.split("-").map(Number);
  return `${date} ${MONTHS[month - 1]} ${year}`;
};
const DAY = /^\d{4}-\d{2}-\d{2}$/;
export const MONTH = /^\d{4}-(0[1-9]|1[0-2])$/;

/** A new rate's fields as shop/staff_tax.py's NewHsnRateSerializer checks them, after `latest`: its errors or null. */
export function rateProblems(input: Record<string, unknown>, latest?: S["HsnRate"]): Record<string, string[]> | null {
  const text = (name: string) => (typeof input[name] === "string" ? (input[name] as string).trim() : "");
  const rate = Number(text("rate"));
  const fields: Record<string, string[]> = {};
  if (!text("rate") || Number.isNaN(rate) || rate < 0 || rate >= 100) fields.rate = ["A valid number is required."];
  if (!["taxable", "nil", "exempt", "non_gst"].includes(text("taxability")))
    fields.taxability = [`"${text("taxability")}" is not a valid choice.`];
  if (!DAY.test(text("effective_from")))
    fields.effective_from = ["Date has wrong format. Use one of these formats instead: YYYY-MM-DD."];
  if (text("effective_to") && !DAY.test(text("effective_to")))
    fields.effective_to = ["Date has wrong format. Use one of these formats instead: YYYY-MM-DD."];
  if (!text("notification")) fields.notification = ["This field may not be blank."];
  if (Object.keys(fields).length) return fields;
  const from = text("effective_from");
  if (text("taxability") === "taxable" && rate <= 0) return { rate: ["A taxable supply has a rate above 0."] };
  if (text("taxability") !== "taxable" && rate !== 0)
    return { rate: ["Nil-rated, exempt and non-GST supplies are at 0."] };
  if (text("effective_to") && text("effective_to") < from) return { effective_to: ["It ends after it starts."] };
  if (latest && from <= latest.effective_from)
    return {
      effective_from: [
        `A new rate starts after the latest one (${longDate(latest.effective_from)}): the history is not rewritten.`,
      ],
    };
  if (latest?.effective_to && from <= latest.effective_to)
    return {
      effective_from: [
        `The rate from ${longDate(latest.effective_from)} runs until ${longDate(latest.effective_to)}: start after it.`,
      ],
    };
  return null;
}

/** A rate as the master stores it, from the fields rateProblems passed. */
export function newRate(input: Record<string, unknown>, id: number, by: number): S["HsnRate"] {
  const text = (name: string) => (typeof input[name] === "string" ? (input[name] as string).trim() : "");
  return {
    id,
    rate: Number(text("rate")).toFixed(2),
    taxability: text("taxability") as S["HsnRate"]["taxability"],
    effective_from: text("effective_from"),
    effective_to: text("effective_to") || null,
    until: null,
    notification: text("notification"),
    serial: text("serial"),
    note: text("note"),
    created: new Date().toISOString(),
    created_by: by,
  };
}

/** Whether a month ends a quarter (a QRMP GSTR-1). */
export const endsQuarter = (month: string) => Boolean(QUARTERS[Number(month.slice(5))]);

/** The month before the one of `now`, in India: "2026-09". */
export const monthBefore = (now: number) => monthsCovered(dayOf(now).slice(0, 7), 2)[1];

/** The months a GSTR-1 export covers: the month, or the quarter ending with it ("2026-07" … "2026-09"). */
export function monthsCovered(month: string, months: number): string[] {
  const [year, number] = month.split("-").map(Number);
  return Array.from({ length: months }, (_, back) => {
    const index = year * 12 + number - 1 - back;
    return `${Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, "0")}`;
  });
}

export function createTaxWorld(now: number): TaxWorld {
  const today = dayOf(now);
  const daysAgo = (days: number) => dayOf(now - days * 86_400_000);
  const at = (hours: number) => new Date(now + hours * 3_600_000).toISOString();

  let rateId = 700;
  const rate = (
    rate: string,
    taxability: S["HsnRate"]["taxability"],
    effective_from: string,
    notification: string,
    serial = "",
    note = "",
  ): S["HsnRate"] => ({
    id: ++rateId,
    rate,
    taxability,
    effective_from,
    effective_to: null,
    until: null,
    notification,
    serial,
    note,
    created: at(-24 * 30),
    created_by: null,
  });
  const product = (id: number, title: string, kind: S["HsnProduct"]["kind"], gst: string, problem = "") => ({
    id,
    slug: title.toLowerCase().replace(/[^a-z0-9]+/g, "-"),
    title,
    kind,
    gst_rate: gst,
    is_active: true,
    problem,
  });
  const code = (
    hsn: string,
    kind: S["HsnCodeDetail"]["kind"],
    description: string,
    uqc: string,
    rates: S["HsnRate"][],
    linked: S["HsnProduct"][] = [],
  ): S["HsnCodeDetail"] => ({
    code: hsn,
    kind,
    description,
    uqc,
    today: null,
    next_change: null,
    products: 0,
    created: at(-24 * 30),
    rates,
    linked,
  });
  const changed = "2025-09-22";
  const began = "2017-07-01";
  const nextMonth = `${daysAgo(-40).slice(0, 7)}-01`;
  const disagrees = `GST 5.00% here, 0.00% in the master from 22 September 2025 (10/2025-Central Tax (Rate)).`;
  const codes = [
    code(
      "4901",
      "hsn",
      "Printed books, including Braille books",
      "NOS",
      [rate("0", "exempt", changed, "10/2025-Central Tax (Rate)", "132", "The sample papers and solutions.")],
      [
        product(301, "Class 10 Mathematics sample papers", "sample-papers", "0.00"),
        product(302, "Class 12 Physics sample papers", "sample-papers", "0.00"),
        product(303, "Class 10 Science solutions", "solutions", "5.00", disagrees),
      ],
    ),
    code("4820", "hsn", "Exercise books, graph books, laboratory notebooks and notebooks", "NOS", [
      rate("12", "taxable", began, "1/2017-Central Tax (Rate), as amended"),
      rate("0", "exempt", changed, "10/2025-Central Tax (Rate)", "130"),
    ]),
    code("4802", "hsn", "Uncoated paper for printing and writing, other than for exercise books", "KGS", [
      rate("12", "taxable", began, "1/2017-Central Tax (Rate), as amended"),
      rate("18", "taxable", changed, "9/2025-Central Tax (Rate)", "", "A purchase; the serial number to confirm."),
      rate("12", "taxable", nextMonth, "Sample notification for the mock", "", "A change to come (mock data)."),
    ]),
    code("4911", "hsn", "Other printed matter: posters and charts (mock data)", "NOS", [
      rate("18", "taxable", nextMonth, "Sample notification for the mock", "", "No rate until it starts."),
    ]),
    code(
      "998431",
      "sac",
      "E-books: electronic versions of printed books, supplied online",
      "NA",
      [rate("5", "taxable", changed, "11/2017-Central Tax (Rate), as amended by 13/2018-Central Tax (Rate)")],
      [product(304, "Class 10 Mathematics e-book", "digital", "5.00")],
    ),
    code(
      "999293",
      "sac",
      "Commercial training and coaching services: the revision course",
      "NA",
      [rate("18", "taxable", changed, "11/2017-Central Tax (Rate), as amended")],
      [product(305, "Class 10 revision course", "digital", "18.00")],
    ),
  ];
  for (const each of codes) refreshCode(each, today);
  const problems: S["TaxProblem"][] = [
    {
      id: 303,
      slug: "class-10-science-solutions",
      title: "Class 10 Science solutions",
      kind: "solutions",
      hsn_code: "4901",
      gst_rate: "5.00",
      is_active: true,
      tax_treatment: "split",
      problem: disagrees,
    },
    {
      id: 306,
      slug: "class-9-english-workbook",
      title: "Class 9 English workbook",
      kind: "sample-papers",
      hsn_code: "",
      gst_rate: "0.00",
      is_active: true,
      tax_treatment: "split",
      problem: "Not on the HSN and SAC master: choose its code.",
    },
  ];

  // the documents, numbered in date order within each series and year
  const serials: Record<string, number> = {};
  let documentId = 800;
  const document = (
    days: number,
    kind: S["TaxDocumentDetail"]["kind"],
    type: S["TaxDocumentDetail"]["document_type"],
    order: string,
    state: [string, string],
    lines: S["TaxLine"][],
    extra: Partial<S["TaxDocumentDetail"]> = {},
  ): S["TaxDocumentDetail"] => {
    const date = daysAgo(days);
    const year = yearOf(date);
    const test = Boolean(extra.test);
    const typed = Number(year.slice(0, 4)) >= Number(SERIES_FROM.slice(0, 4));
    const series = test
      ? kind === "credit_note"
        ? "TC"
        : "T"
      : kind === "credit_note"
        ? "CN"
        : typed
          ? PREFIXES[type || "tax_invoice"]
          : "EL";
    const start = { EL: 38, CN: 6 }[series] ?? 1;
    const serial = (serials[`${series}/${year}`] = (serials[`${series}/${year}`] ?? start - 1) + 1);
    const number = `${series}/${year}/${String(serial).padStart(5, "0")}`;
    const sum = (field: "amount" | "taxable" | "tax") =>
      [...lines, ...(extra.charges ?? [])].reduce((total, line) => total + Number(line[field]), 0);
    const exempt = [...lines, ...(extra.charges ?? [])]
      .filter((line) => Number(line.rate) === 0)
      .reduce((total, line) => total + Number(line.taxable), 0);
    return {
      key: number.replaceAll("/", "-"),
      kind,
      id: ++documentId,
      number,
      series,
      financial_year: year,
      serial,
      document_type: type,
      test,
      date,
      order,
      against: null,
      place_of_supply: state[0],
      place_label: state[1],
      total: sum("amount").toFixed(2),
      taxable_value: (sum("taxable") - exempt).toFixed(2),
      exempt_value: exempt.toFixed(2),
      tax_amount: sum("tax").toFixed(2),
      cancelled_at: null,
      cancel_reason: "",
      cancelled_by: null,
      has_pdf: true,
      title: kind === "credit_note" ? "Credit note" : type === "tax_invoice" ? "Tax invoice" : "Bill of supply",
      lines,
      charges: [],
      round_off: "0.00",
      checks: [],
      credit_notes: [],
      ...extra,
    };
  };
  const line = (
    title: string,
    hsn: string,
    quantity: number,
    rate: string,
    amount: string,
    taxable: string,
    tax: string,
    bundle = "",
  ): S["TaxLine"] => ({ title, bundle, hsn_code: hsn, quantity, rate, amount, taxable, tax });
  const assam: [string, string] = ["AS", "Assam (18)"];
  const exempt = document(
    40,
    "invoice",
    "bill_of_supply",
    "EL-2026-000101",
    assam,
    [line("Class 10 Mathematics sample papers", "4901", 1, "0.00", "349.00", "349.00", "0.00")],
    {
      charges: [{ label: "Shipping", rate: "0.00", amount: "50.00", taxable: "50.00", tax: "0.00" }],
    },
  );
  const mixed = document(
    20,
    "invoice",
    "invoice_cum_bill_of_supply",
    "EL-2026-000117",
    ["KA", "Karnataka (29)"],
    [
      line("Class 10 Mathematics sample papers", "4901", 1, "0.00", "449.00", "449.00", "0.00", "Class 10 starter set"),
      line("Class 10 Mathematics e-book", "9984", 1, "5.00", "199.00", "189.52", "9.48", "Class 10 starter set"),
    ],
  );
  const note = document(
    10,
    "credit_note",
    "invoice_cum_bill_of_supply",
    "EL-2026-000117",
    ["KA", "Karnataka (29)"],
    [line("Class 10 Mathematics e-book", "9984", 1, "5.00", "199.00", "189.52", "9.48")],
    { against: mixed.number },
  );
  mixed.credit_notes = [note.number];
  const cancelled = document(
    7,
    "invoice",
    "bill_of_supply",
    "EL-2026-000126",
    assam,
    [line("Class 12 Physics sample papers", "4901", 2, "0.00", "780.00", "780.00", "0.00")],
    {
      cancelled_at: at(-24 * 6),
      cancel_reason: "Made twice for one order; the order keeps its first invoice.",
      cancelled_by: 9002,
    },
  );
  const course = document(5, "invoice", "tax_invoice", "EL-2026-000133", assam, [
    line("Class 10 revision course", "9992", 1, "18.00", "999.00", "846.61", "152.39"),
  ]);
  const school = document(
    1,
    "invoice",
    "bill_of_supply",
    "EL-2026-000140",
    ["ML", "Meghalaya (17)"],
    [line("Class 12 Physics sample papers", "4901", 160, "0.00", "62400.00", "62400.00", "0.00")],
    { checks: ["The buyer's name and address: required from ₹50,000 (Rule 46(i))."], has_pdf: false },
  );
  const test = document(
    3,
    "invoice",
    "tax_invoice",
    "EL-2026-000131",
    assam,
    [line("Class 10 revision course", "9992", 1, "18.00", "999.00", "846.61", "152.39")],
    { test: true },
  );
  const documents = [school, test, course, cancelled, note, mixed, exempt]; // newest first, as the API lists them

  const year = yearOf(today);
  const previous = `${Number(year.slice(0, 4)) - 1}-${year.slice(2, 4)}`;
  const threshold = (
    line: S["ThresholdRow"]["line"],
    label: string,
    value: string,
    limit: string,
    crossed = false,
    count = false,
  ): S["ThresholdRow"] => ({
    line,
    label,
    value,
    limit,
    crossed,
    count,
    detail: {},
    date: daysAgo(1),
    financial_year: year,
  });
  const card: S["ThresholdCard"] = {
    as_of: daysAgo(1),
    financial_year: year,
    previous_year: previous,
    previous_turnover: "18450000.00",
    qrmp: true,
    hsn_digits: 4,
    basis:
      "Aggregate turnover as GST counts it: the storefront's invoices less their credit notes, taxable and exempt, without the tax. ERPNext's B2B sales join it at the cut-over.",
    rows: [
      threshold("gstr9", "₹2 crore: the annual return (GSTR-9) is due", "21450000.00", "20000000.00", true),
      threshold("warning", "₹4 crore: e-invoicing and monthly returns come at ₹5 crore", "21450000.00", "40000000.00"),
      threshold("e_invoice", "₹5 crore: e-invoicing, QRMP ends, 6-digit HSN codes", "21450000.00", "50000000.00"),
      threshold(
        "irp_30_days",
        "₹10 crore: e-invoices reported to the IRP within 30 days",
        "21450000.00",
        "100000000.00",
      ),
      threshold("b2c_large", "invoices above ₹1 lakh to another state (GSTR-1 table 5)", "0", "100000.00", false, true),
      threshold("eway_bill", "taxable goods above ₹50,000 in one parcel: an e-way bill", "0", "50000.00", false, true),
    ],
  };
  return { codes, problems, documents, card, qrmp: true };
}
