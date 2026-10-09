// THE FINANCE PART OF THE STAFF API MOCK, FOR DEVELOPMENT AND TESTS ONLY (handler.ts calls it under STAFF_API_MOCK=1).
// It answers /api/v1/staff/finance/ as examleaf-web's shop/staff_finance.py does, from its own fixtures (financeWorld):
// Finance today counted from them and from the approvals' fixtures; payments with the stuck ones, and Razorpay asked
// again (a late authorisation captured, a payment Razorpay never had); refunds and offline payments, with the change
// requests waiting; the staff orders' and the B2B invoices' links, made, sent again, cancelled, asked of Razorpay again
// and recorded as posted; the settlements (posted, matched with ERPNext failing, one that does not match, a test one),
// a line matched by hand, a day fetched as a job; an invoice's ERPNext copy. The rules are the backend's: each
// endpoint's permission (handler.ts checks it first), field errors in DRF's shape, 404 for what is not there.
import type { MockSchemas, World } from "./fixtures";
import type { Kit, SupportContext } from "./support-handler";

type S = MockSchemas;
type Body = Record<string, unknown>;
type Payment = S["FinancePaymentDetail"];
type Settlement = S["FinanceSettlementDetail"] & { _lines: S["FinanceSettlementLine"][] };
/** A staff order a link is for: what it costs, whether it still waits for its payment. */
type StaffOrder = { amount: string; pending: boolean; website?: boolean; cod?: boolean };

export type FinanceWorld = {
  payments: Payment[];
  refunds: S["FinanceRequestRow"][];
  invoiceLinks: S["FinanceLink"][];
  settlements: Settlement[];
  /** The orders the links' POST knows: staff orders (and a website and a COD one, which it refuses). */
  orders: Record<string, StaffOrder>;
  /** ERPNext's B2B invoices in the platform's copy: name → what is outstanding ("0.00": nothing). */
  invoices: Record<string, string>;
  /** Finance today's rows that count other modules' records (cash on delivery, the sync): as fixtures. */
  elsewhere: S["FinanceTodayRow"][];
  /** The ERPNext copies of documents (finance/documents/{number}/erp/), by number. */
  documents: S["FinanceDocumentErp"][];
};

const HOUR = 3_600_000;
const IST = 5.5 * HOUR;
const LINK_DAYS = 15;
const VIEW_PAYMENT = "shop.view_payment";
const VIEW_REFUND = "shop.view_refund";
const VIEW_SETTLEMENT = "shop.view_settlement";
const RECONCILE = "staff.reconcile_settlements";

const iso = (ms = Date.now()) => new Date(ms).toISOString();
/** A moment's day in India: "2026-10-09". */
const indiaDay = (moment: string) => new Date(Date.parse(moment) + IST).toISOString().slice(0, 10);
const text = (value: unknown) => (typeof value === "string" ? value.trim() : "");
const rupees = (value: number) => value.toFixed(2);
const sum = (values: (string | null)[]) => rupees(values.reduce((total, value) => total + Number(value ?? 0), 0));
const refusal = (message: string) => ({ non_field_errors: [message] });
const LIST_FIELDS = [
  ...["id", "order", "order_status", "method", "status", "amount", "razorpay_order_id", "razorpay_payment_id"],
  ...["razorpay_payment_link_id", "reference", "error", "livemode", "is_test", "stuck", "is_link", "fee", "tax"],
  ...["settlement", "created", "modified"],
] as const;

export function financeWorld(at: (hours: number) => string): FinanceWorld {
  const day = (hours: number) => indiaDay(at(hours));
  const hook = (event_id: string, name: string, hours: number) => ({ event_id, name, received_at: at(hours) });
  const step = (hours: number, kind: string, label: string, actor = "") => ({
    at: at(hours),
    kind,
    label,
    actor,
    details: {},
  });
  const payment = (row: Partial<Payment> & Pick<Payment, "id" | "order" | "order_id" | "amount" | "status">) =>
    ({
      order_status: "paid",
      method: "razorpay",
      razorpay_order_id: `order_mock${row.order_id}`,
      razorpay_payment_id: row.status === "created" ? null : `pay_mock${row.order_id}`,
      razorpay_payment_link_id: null,
      reference: "",
      error: "",
      livemode: true,
      is_test: false,
      stuck: false,
      is_link: false,
      fee: null,
      tax: null,
      settlement: null,
      created: at(-24),
      modified: at(-24),
      order_total: row.amount,
      order_placed_at: row.created ?? at(-24),
      payment_link_url: "",
      refunds: [],
      webhooks: [],
      last_webhook: null,
      timeline: [],
      ...row,
    }) as Payment;

  const posted = { id: 1, settlement_id: "setl_mockA0001", date: day(-24 * 5), utr: "UTIB0000417", state: "posted" };
  const short = { id: 2, settlement_id: "setl_mockB0002", date: day(-24 * 2), utr: "UTIB0000588", state: "mismatched" };
  const payments: Payment[] = [
    payment({
      id: 410,
      order: "EL-2026-000123",
      order_id: 41,
      order_status: "shipped",
      amount: "2460.00",
      status: "captured",
      fee: "49.20",
      tax: "8.86",
      settlement: posted as Payment["settlement"],
      created: at(-24 * 6),
      modified: at(-24 * 6),
      webhooks: [hook("evt_mock410a", "payment.captured", -24 * 6), hook("evt_mock410b", "order.paid", -24 * 6)],
      last_webhook: { id: "pay_mock41", entity: "payment", amount: 246000, currency: "INR", status: "captured" },
      timeline: [
        step(-24 * 6, "payment", "Payment Started", "the site"),
        step(-24 * 6 + 0.01, "webhook", "Razorpay's webhook payment.captured", "Razorpay"),
        step(-24 * 6 + 0.02, "payment", "Payment Received", "the site"),
        step(-24 * 5, "settlement", "Settled in setl_mockA0001 (UTR UTIB0000417)", "Razorpay"),
      ],
    }),
    payment({
      id: 480,
      order: "EL-2026-000134",
      order_id: 48,
      order_status: "delivered",
      amount: "1470.00",
      status: "captured",
      fee: "29.40",
      tax: "5.29",
      settlement: short as Payment["settlement"],
      created: at(-24 * 9),
      modified: at(-24 * 9),
      refunds: [
        {
          id: 72,
          amount: "450.00",
          status: "processed",
          method: "source",
          speed: "normal",
          razorpay_refund_id: "rfnd_mock72",
          arn: "74512345678901234567890",
          created: at(-24 * 3),
          processed_at: at(-24 * 2.5),
        },
      ],
      webhooks: [hook("evt_mock480a", "payment.captured", -24 * 9)],
    }),
    payment({
      id: 440,
      order: "EL-2026-000130",
      order_id: 44,
      amount: "1499.00",
      status: "captured",
      created: at(-24),
      modified: at(-24),
      webhooks: [hook("evt_mock440a", "payment.captured", -24)],
    }),
    // stuck: authorised, never captured (the late-authorised case): asking Razorpay captures it
    payment({
      id: 9101,
      order: "EL-2026-000138",
      order_id: 138,
      order_status: "pending",
      amount: "729.00",
      status: "authorized",
      stuck: true,
      created: at(-0.75),
      modified: at(-0.7),
      order_placed_at: at(-0.75),
      webhooks: [hook("evt_mock9101a", "payment.authorized", -0.7)],
      timeline: [
        step(-0.75, "payment", "Payment Started", "the site"),
        step(-0.7, "webhook", "Razorpay's webhook payment.authorized", "Razorpay"),
        step(-0.7, "payment", "Payment Authorised", "the site"),
      ],
    }),
    // stuck: the checkout opened two hours ago and Razorpay never had a payment
    payment({
      id: 9102,
      order: "EL-2026-000139",
      order_id: 139,
      order_status: "pending",
      amount: "449.00",
      status: "created",
      stuck: true,
      created: at(-2),
      modified: at(-2),
      timeline: [step(-2, "payment", "Payment Started", "the site")],
    }),
    payment({
      id: 9103,
      order: "EL-2026-000140",
      order_id: 140,
      order_status: "cancelled",
      amount: "899.00",
      status: "failed",
      error: "Payment failed: the bank declined it.",
      created: at(-30),
      modified: at(-30),
      webhooks: [hook("evt_mock9103a", "payment.failed", -30)],
    }),
    payment({
      id: 9104,
      order: "EL-2026-000141",
      order_id: 141,
      method: "offline",
      amount: "5400.00",
      status: "captured",
      razorpay_order_id: null,
      razorpay_payment_id: null,
      reference: "UTR4471029384",
      created: at(-48),
      modified: at(-48),
    }),
    // a test order's (Razorpay's test keys): left out unless asked for
    payment({
      id: 9105,
      order: "EL-2026-000142",
      order_id: 142,
      amount: "299.00",
      status: "captured",
      livemode: false,
      is_test: true,
      created: at(-3),
      modified: at(-3),
    }),
    // the staff orders' links: open, paid, and one past its 15 days (stuck: its order still unpaid)
    payment({
      id: 501,
      order: "EL-2026-000136",
      order_id: 50,
      order_status: "pending",
      amount: "10800.00",
      status: "created",
      is_link: true,
      razorpay_order_id: null,
      razorpay_payment_link_id: "plink_mock50",
      payment_link_url: "https://rzp.io/i/mock50",
      created: at(-5),
      modified: at(-5),
    }),
    payment({
      id: 9106,
      order: "EL-2026-000126",
      order_id: 126,
      amount: "3600.00",
      status: "captured",
      is_link: true,
      razorpay_order_id: null,
      razorpay_payment_link_id: "plink_mock126",
      payment_link_url: "https://rzp.io/i/mock126",
      created: at(-24 * 4),
      modified: at(-24 * 3),
      webhooks: [hook("evt_mock9106a", "payment_link.paid", -24 * 3)],
    }),
    payment({
      id: 9107,
      order: "EL-2026-000128",
      order_id: 128,
      order_status: "pending",
      amount: "2250.00",
      status: "created",
      stuck: true,
      is_link: true,
      razorpay_order_id: null,
      razorpay_payment_link_id: "plink_mock128",
      payment_link_url: "https://rzp.io/i/mock128",
      created: at(-24 * 20),
      modified: at(-24 * 20),
    }),
  ];

  const refund = (row: Partial<S["FinanceRequestRow"]> & Pick<S["FinanceRequestRow"], "id" | "order" | "amount">) =>
    ({
      kind: "refund",
      status: "pending",
      reference: "",
      method: "source",
      speed: "normal",
      reason: "",
      arn: "",
      utr: "",
      razorpay_refund_id: "",
      credit_note: null,
      payee_masked: "",
      payment_method: "razorpay",
      error: "",
      change_request: null,
      change_request_status: "",
      checker: "",
      rule: "",
      by: "Rahul Saikia",
      created: at(-24),
      done_at: null,
      livemode: true,
      ...row,
    }) as S["FinanceRequestRow"];
  const refunds = [
    refund({
      id: 72,
      order: "EL-2026-000134",
      amount: "450.00",
      status: "processed",
      reason: "One copy came back unopened.",
      arn: "74512345678901234567890",
      razorpay_refund_id: "rfnd_mock72",
      credit_note: "EL/CN/2026-27/00004",
      created: at(-24 * 3),
      done_at: at(-24 * 2.5),
    }),
    refund({
      id: 71,
      order: "EL-2026-000137",
      amount: "349.00",
      method: "bank",
      reason: "Pages 12 to 16 missing",
      payee_masked: "••••••4521 (SBIN)",
      payment_method: "cod",
      by: "Rina Sales",
      created: at(-24 * 2),
    }),
    refund({
      id: 31,
      order: "EL-2026-000098",
      amount: "638.00",
      speed: "optimum",
      reason: "Cancelled before it was packed.",
      razorpay_refund_id: "rfnd_mock31",
      change_request: 505,
      change_request_status: "executed",
      created: at(-52),
    }),
    refund({
      id: 73,
      order: "EL-2026-000090",
      amount: "1499.00",
      status: "failed",
      reason: "Delivered late; the customer asked for the money back.",
      error: "Razorpay refused: the payment is too old to refund online. Refund it by bank transfer.",
      created: at(-33),
    }),
  ];

  const link = (row: Partial<S["FinanceLink"]> & Pick<S["FinanceLink"], "id" | "invoice" | "amount" | "state">) =>
    ({
      kind: "invoice",
      order: null,
      url: `https://rzp.io/i/mockb2b${row.id}`,
      razorpay_link_id: `plink_mockb2b${row.id}`,
      razorpay_payment_id: null,
      sent_at: at(-48),
      last_sent_at: null,
      expires_at: at(-48 + 24 * LINK_DAYS),
      paid_at: null,
      created_by: "Anita Baruah",
      posted_at: null,
      erp_name: "",
      livemode: true,
      is_test: false,
      ...row,
    }) as S["FinanceLink"];
  const invoiceLinks = [
    link({ id: 1, invoice: "ACC-SINV-2026-00007", amount: "18500.00", state: "sent" }),
    link({
      id: 2,
      invoice: "ACC-SINV-2026-00004",
      amount: "42000.00",
      state: "paid",
      razorpay_payment_id: "pay_mockb2b2",
      paid_at: at(-20),
      sent_at: at(-24 * 6),
      expires_at: at(-24 * 6 + 24 * LINK_DAYS),
    }),
    link({
      id: 3,
      invoice: "ACC-SINV-2026-00002",
      amount: "9600.00",
      state: "paid",
      razorpay_payment_id: "pay_mockb2b3",
      paid_at: at(-24 * 8),
      posted_at: at(-24 * 7),
      erp_name: "ACC-PAY-2026-00009",
      sent_at: at(-24 * 10),
      expires_at: at(-24 * 10 + 24 * LINK_DAYS),
    }),
    link({ id: 4, invoice: "ACC-SINV-2026-00001", amount: "7200.00", state: "cancelled", sent_at: at(-24 * 12) }),
    link({
      id: 5,
      invoice: "ACC-SINV-2026-00003",
      amount: "12400.00",
      state: "expired",
      sent_at: at(-24 * 17),
      expires_at: at(-24 * 2),
    }),
  ];

  const line = (row: Partial<S["FinanceSettlementLine"]> & Pick<S["FinanceSettlementLine"], "id" | "entity_id">) =>
    ({
      type: "payment",
      amount: "0.00",
      fee: "0.00",
      tax: "0.00",
      credit: "0.00",
      debit: "0.00",
      settled_at: at(-24 * 2),
      order_receipt: "",
      order: null,
      payment: null,
      refund: null,
      link: null,
      matched: true,
      matched_at: at(-24 * 2),
      matched_by: "",
      note: "",
      ...row,
    }) as S["FinanceSettlementLine"];
  const settlement = (row: Omit<Settlement, "created" | "modified" | "counts">) => {
    const lines = row._lines;
    const count = (type: string) => lines.filter((each) => each.type === type).length;
    return {
      created: at(-24 * 2),
      modified: at(-24 * 2),
      counts: {
        lines: lines.length,
        unmatched: lines.filter((each) => !each.matched).length,
        payment: count("payment"),
        refund: count("refund"),
        adjustment: count("adjustment"),
      },
      ...row,
    } as Settlement;
  };
  const settlements = [
    settlement({
      ...posted,
      id: 1,
      state: "posted",
      gross: "2460.00",
      fees: "49.20",
      tax: "8.86",
      adjustments: "0.00",
      net: "2401.94",
      problem: "",
      livemode: true,
      is_test: false,
      matched_at: at(-24 * 4.9),
      posted_at: at(-24 * 4.9),
      erp: {
        outbox: 7001,
        state: "sent",
        attempts: 1,
        last_error: "",
        sent_at: at(-24 * 4.8),
        name: "ACC-JV-2026-00031",
      },
      _lines: [
        line({
          id: 11,
          entity_id: "pay_mock41",
          amount: "2460.00",
          fee: "49.20",
          tax: "8.86",
          credit: "2401.94",
          order_receipt: "EL-2026-000123",
          order: "EL-2026-000123",
          payment: { id: 410, order: "EL-2026-000123", amount: "2460.00" },
          settled_at: at(-24 * 5),
          matched_at: at(-24 * 4.9),
        }),
      ],
    }),
    // does not match: the late-authorised payment's line (its webhook lost) and an adjustment wait for FINANCE
    settlement({
      ...short,
      id: 2,
      state: "mismatched",
      gross: "1774.00",
      fees: "43.98",
      tax: "7.91",
      adjustments: "25.00",
      net: "1722.11",
      problem: "2 lines not ours yet",
      livemode: true,
      is_test: false,
      matched_at: null,
      posted_at: null,
      erp: null,
      _lines: [
        line({
          id: 21,
          entity_id: "pay_mock48",
          amount: "1470.00",
          fee: "29.40",
          tax: "5.29",
          credit: "1435.31",
          order_receipt: "EL-2026-000134",
          order: "EL-2026-000134",
          payment: { id: 480, order: "EL-2026-000134", amount: "1470.00" },
        }),
        line({
          id: 22,
          type: "refund",
          entity_id: "rfnd_mock72",
          amount: "450.00",
          debit: "450.00",
          order_receipt: "EL-2026-000134",
          order: "EL-2026-000134",
          refund: { id: 72, order: "EL-2026-000134", amount: "450.00" },
        }),
        line({
          id: 23,
          entity_id: "pay_mock138",
          amount: "729.00",
          fee: "14.58",
          tax: "2.62",
          credit: "711.80",
          order_receipt: "EL-2026-000138",
          matched: false,
          matched_at: null,
        }),
        line({
          id: 24,
          type: "adjustment",
          entity_id: "adj_mockB1",
          amount: "25.00",
          credit: "25.00",
          matched: false,
          matched_at: null,
        }),
      ],
    }),
    // matched yesterday; its Journal Entry failed to reach ERPNext and is tried again
    settlement({
      id: 4,
      settlement_id: "setl_mockD0004",
      date: day(-24),
      utr: "UTIB0000612",
      state: "matched",
      gross: "3600.00",
      fees: "72.00",
      tax: "12.96",
      adjustments: "0.00",
      net: "3515.04",
      problem: "",
      livemode: true,
      is_test: false,
      matched_at: at(-20),
      posted_at: null,
      erp: {
        outbox: 7002,
        state: "failed",
        attempts: 2,
        last_error: "ERPNext did not answer within 10 seconds.",
        sent_at: null,
        name: null,
      },
      _lines: [
        line({
          id: 41,
          entity_id: "pay_mock126",
          amount: "3600.00",
          fee: "72.00",
          tax: "12.96",
          credit: "3515.04",
          order_receipt: "EL-2026-000126",
          order: "EL-2026-000126",
          payment: { id: 9106, order: "EL-2026-000126", amount: "3600.00" },
          settled_at: at(-24),
          matched_at: at(-20),
        }),
      ],
    }),
    // Razorpay's test keys: left out unless asked for, never posted
    settlement({
      id: 3,
      settlement_id: "setl_mockT0003",
      date: day(-24),
      utr: "",
      state: "matched",
      gross: "299.00",
      fees: "5.98",
      tax: "1.08",
      adjustments: "0.00",
      net: "291.94",
      problem: "",
      livemode: false,
      is_test: true,
      matched_at: at(-22),
      posted_at: null,
      erp: null,
      _lines: [
        line({
          id: 31,
          entity_id: "pay_mock142",
          amount: "299.00",
          fee: "5.98",
          tax: "1.08",
          credit: "291.94",
          order_receipt: "EL-2026-000142",
          order: "EL-2026-000142",
          payment: { id: 9105, order: "EL-2026-000142", amount: "299.00" },
        }),
      ],
    }),
  ];

  return {
    payments,
    refunds,
    invoiceLinks,
    settlements,
    orders: {
      "EL-2026-000136": { amount: "10800.00", pending: true },
      "EL-2026-000128": { amount: "2250.00", pending: true },
      "EL-2026-000144": { amount: "3240.00", pending: true },
      "EL-2026-000126": { amount: "3600.00", pending: false },
      "EL-2026-000130": { amount: "1499.00", pending: false, website: true },
      "EL-2026-000133": { amount: "299.00", pending: true, cod: true },
    },
    invoices: { "ACC-SINV-2026-00008": "6400.00", "ACC-SINV-2026-00007": "18500.00", "ACC-SINV-2026-00005": "0.00" },
    elsewhere: [
      { key: "cod_receivable", count: 2, oldest: day(-24 * 3), amount: "878.00", configured: true },
      { key: "cod_overdue", count: 1, oldest: day(-24 * 9), amount: "579.00", configured: true },
      { key: "cod_mismatched", count: 0, oldest: null, amount: null, configured: true },
      { key: "sync_differences", count: 1, oldest: day(-24), amount: null, configured: true },
    ],
    documents: [
      {
        number: "EL/2026-27/00123",
        kind: "invoice",
        state: "mirrored",
        doctype: "Sales Invoice",
        name: "ACC-SINV-2026-00123",
        synced_at: at(-24 * 6 + 1),
        outbox: [
          {
            id: 6101,
            event: "invoice.issued",
            state: "sent",
            attempts: 1,
            last_error: "",
            created: at(-24 * 6),
            sent_at: at(-24 * 6 + 1),
          },
        ],
      },
      {
        number: "EL/CN/2026-27/00004",
        kind: "credit_note",
        state: "failed",
        doctype: null,
        name: null,
        synced_at: null,
        outbox: [
          {
            id: 6102,
            event: "credit_note.issued",
            state: "failed",
            attempts: 3,
            last_error: "ERPNext refused it: the return's invoice is not there yet.",
            created: at(-24 * 2.5),
            sent_at: null,
          },
        ],
      },
    ],
  };
}

/** Which permission a finance path needs, as shop/staff_finance.py's `permissions` names it. */
export function financePermission(context: SupportContext): string {
  const { method, parts } = context;
  const [, a, b, c] = parts;
  const get = method === "GET";
  if (a === "today") return context.permissions.includes(VIEW_PAYMENT) ? VIEW_PAYMENT : "staff.view_cod";
  if (a === "payments") return get ? VIEW_PAYMENT : "staff.replay_webhook";
  if (a === "offline-payments") return VIEW_PAYMENT;
  if (a === "payment-links") {
    if (b === "invoices") return c === "posted" ? RECONCILE : "staff.replay_webhook";
    return get ? VIEW_PAYMENT : "shop.change_order";
  }
  if (a === "refunds") return VIEW_REFUND;
  if (a === "settlements") {
    if (get) return c === "lines" ? "shop.view_settlementline" : VIEW_SETTLEMENT;
    return RECONCILE;
  }
  if (a === "documents") return "shop.view_invoice";
  return VIEW_PAYMENT;
}

const listRow = (payment: Payment) =>
  Object.fromEntries(LIST_FIELDS.map((name) => [name, payment[name]])) as S["FinancePayment"];

/** A live payment, unless the test ones were asked for (`livemode`: the rows of that mode). */
function inMode<T extends { livemode: boolean }>(rows: T[], url: URL): T[] {
  const asked = url.searchParams.get("livemode");
  if (asked === "true" || asked === "1") return rows.filter((row) => row.livemode);
  if (asked === "false" || asked === "0") return rows.filter((row) => !row.livemode);
  return rows.filter((row) => row.livemode);
}

const staffName = (world: World, id: number) =>
  id === world.me.id ? world.me.name : (world.people.find((person) => person.id === id)?.full_name ?? "");

/** A row's fields a recorded payment or refund leaves empty (staff_finance.blank_row). */
const BLANK_ROW = {
  reference: "",
  method: "",
  speed: "",
  reason: "",
  arn: "",
  utr: "",
  razorpay_refund_id: "",
  credit_note: null,
  payee_masked: "",
  payment_method: "",
  error: "",
  change_request: null,
  change_request_status: "",
  checker: "",
  rule: "",
  by: "",
  done_at: null,
};

/** The change requests of an action on orders waiting for a second person, newest first. */
const waitingRequests = (world: World, action: string) =>
  world.changeRequests.filter(
    (row) => row.action === action && row.status === "pending" && row.target_type === "shop.order",
  );

function requestRow(world: World, row: S["ChangeRequest"]): S["FinanceRequestRow"] {
  const payload = (row.payload ?? {}) as Body;
  return {
    kind: "request",
    id: row.id,
    order: row.target_label ?? "",
    amount: row.amount ?? null,
    status: row.status ?? "pending",
    reference: text(payload.reference),
    method: text(payload.method),
    speed: text(payload.speed),
    reason: row.reason,
    arn: "",
    utr: "",
    razorpay_refund_id: "",
    credit_note: null,
    payee_masked: text(payload.payee_masked),
    payment_method: "",
    error: "",
    change_request: row.id,
    change_request_status: row.status ?? "pending",
    checker: row.checker,
    rule: row.rule ?? "",
    by: staffName(world, row.maker),
    created: row.created,
    done_at: null,
    livemode: true,
  };
}

function linkState(payment: Payment, now = Date.now()): S["FinanceLink"]["state"] {
  if (payment.status === "captured" || payment.status === "refunded") return "paid";
  if (payment.status === "failed") return "cancelled";
  return Date.parse(payment.created) + LINK_DAYS * 24 * HOUR <= now ? "expired" : "sent";
}

function orderLinkRow(payment: Payment): S["FinanceLink"] {
  const state = linkState(payment);
  return {
    kind: "order",
    id: payment.id,
    order: payment.order,
    invoice: null,
    amount: payment.amount,
    state,
    url: payment.payment_link_url,
    razorpay_link_id: payment.razorpay_payment_link_id ?? "",
    razorpay_payment_id: payment.razorpay_payment_id,
    sent_at: payment.created,
    last_sent_at: (payment as Payment & { _sent?: string })._sent ?? null,
    expires_at: iso(Date.parse(payment.created) + LINK_DAYS * 24 * HOUR),
    paid_at: state === "paid" ? payment.modified : null,
    created_by: "Rina Sales",
    posted_at: null,
    erp_name: "",
    livemode: payment.livemode,
    is_test: payment.is_test,
  };
}

/** A B2B link's state now: an open one past its end is expired. */
const invoiceLinkRow = (row: S["FinanceLink"]): S["FinanceLink"] =>
  row.state === "sent" && Date.parse(row.expires_at) <= Date.now() ? { ...row, state: "expired" } : row;

function todayRows(context: SupportContext): S["FinanceTodayRow"][] {
  const { world } = context;
  const finance = world.finance;
  const can = (permission: string) => context.permissions.includes(permission);
  const rows: S["FinanceTodayRow"][] = [];
  const add = (
    key: S["FinanceTodayRow"]["key"],
    permission: string,
    found: { day: string; amount: string | null }[],
  ) => {
    if (!can(permission)) return;
    const days = found.map((row) => row.day).sort();
    const amounts = found.map((row) => row.amount).filter((amount) => amount !== null);
    rows.push({
      key,
      count: found.length,
      oldest: days[0] ?? null,
      amount: amounts.length ? sum(amounts) : null,
      configured: true,
    });
  };
  const asRequests = (action: string) =>
    waitingRequests(world, action).map((row) => ({ day: indiaDay(row.created), amount: row.amount ?? null }));
  add("refunds_to_approve", VIEW_REFUND, asRequests("order.refund"));
  add(
    "bank_refunds",
    VIEW_REFUND,
    finance.refunds
      .filter((row) => row.livemode && row.method === "bank" && row.status === "pending")
      .map((row) => ({ day: indiaDay(row.created), amount: row.amount })),
  );
  add("offline_to_approve", VIEW_PAYMENT, asRequests("order.offline_payment"));
  add(
    "stuck_payments",
    VIEW_PAYMENT,
    finance.payments
      .filter((row) => row.livemode && row.stuck)
      .map((row) => ({ day: indiaDay(row.created), amount: row.amount })),
  );
  add(
    "b2b_to_post",
    VIEW_PAYMENT,
    finance.invoiceLinks
      .filter((row) => row.livemode && row.state === "paid" && !row.posted_at)
      .map((row) => ({ day: indiaDay(row.paid_at ?? row.sent_at), amount: row.amount })),
  );
  const open = finance.settlements.filter((row) => row.livemode && ["fetched", "mismatched"].includes(row.state));
  add(
    "settlement_lines",
    VIEW_SETTLEMENT,
    open.flatMap((row) =>
      row._lines.filter((each) => !each.matched).map((each) => ({ day: row.date, amount: each.amount })),
    ),
  );
  add(
    "settlements_mismatched",
    VIEW_SETTLEMENT,
    finance.settlements
      .filter((row) => row.livemode && row.state === "mismatched")
      .map((row) => ({ day: row.date, amount: row.net })),
  );
  for (const row of finance.elsewhere.filter((each) => each.key.startsWith("cod_")))
    if (can("staff.view_cod")) rows.push(row);
  if (can("shop.view_creditnote")) {
    const refused = world.inbox.filter((item) => item.kind === "credit_note_missing" && !item.done_at);
    const days = refused.map((item) => indiaDay(item.created ?? iso())).sort();
    rows.push({
      key: "credit_notes_refused",
      count: refused.length,
      oldest: days[0] ?? null,
      amount: null,
      configured: true,
    });
  }
  for (const row of finance.elsewhere.filter((each) => each.key === "sync_differences"))
    if (can("erp.view_sync")) rows.push(row);
  if (can(VIEW_PAYMENT)) rows.push({ key: "disputes", count: null, oldest: null, amount: null, configured: false });
  return rows;
}

/** Razorpay asked again about a payment's order, as payments.reconcile does it: the answer and what it changed. */
function reconcile(context: SupportContext, kit: Kit, payment: Payment): Response {
  if (payment.method !== "razorpay")
    return kit.invalid(refusal(`Payment #${payment.id} was not made online: Razorpay knows nothing of it.`));
  if (!payment.livemode)
    return kit.invalid(
      refusal(`Payment #${payment.id} was made with test keys: the keys in force cannot ask about it.`),
    );
  const changes: Record<string, [string, string]> = {};
  let paid = false;
  const when = iso();
  if (payment.status === "authorized" || payment.status === "captured") {
    paid = true;
    if (payment.status === "authorized") {
      changes[`payment ${payment.id}`] = ["authorized", "captured"];
      payment.status = "captured";
      payment.razorpay_payment_id ??= `pay_mock${payment.order_id}`;
      payment.timeline.push({
        at: when,
        kind: "payment",
        label: "Payment Received",
        actor: context.who.name,
        details: {},
      });
    }
    if (payment.order_status === "pending") {
      changes.order = ["pending", "paid"];
      payment.order_status = "paid";
    }
    payment.stuck = false;
    payment.modified = when;
  }
  const words = !paid
    ? "Razorpay has no captured payment for this order: nothing changed."
    : !Object.keys(changes).length
      ? "Razorpay's answer is what the site knew already: nothing changed."
      : `Razorpay had the payment: ${[
          ...(changes.order ? [`the order is ${changes.order[1]} now`] : []),
          ...(changes[`payment ${payment.id}`] ? [`payment ${payment.id} recorded as captured`] : []),
        ].join("; ")}.`;
  kit.record(context, "payment.reconciled", {
    target_type: "shop.payment",
    target_id: String(payment.id),
    target_label: `Payment #${payment.id}`,
    details: { paid, changes },
  });
  payment.timeline.push({ at: when, kind: "audit", label: "payment.reconciled", actor: context.who.name, details: {} });
  return kit.json(200, { paid, detail: words, changes, payment });
}

/** Match a line by hand (settlements.manual_match): a payment, a refund, or an adjustment accepted, with a note. */
function match(context: SupportContext, kit: Kit, settlement: Settlement): Response {
  const { body, world } = context;
  const finance = world.finance;
  const note = text(body.note).replace(/\s+/g, " ");
  const numberOf = (value: unknown) => (value === null || value === undefined || value === "" ? null : Number(value));
  const lineId = numberOf(body.line);
  const paymentId = numberOf(body.payment);
  const refundId = numberOf(body.refund);
  const fields: Record<string, string[]> = {};
  if (lineId === null || !Number.isInteger(lineId)) fields.line = ["A valid integer is required."];
  if (paymentId !== null && !Number.isInteger(paymentId)) fields.payment = ["A valid integer is required."];
  if (refundId !== null && !Number.isInteger(refundId)) fields.refund = ["A valid integer is required."];
  if (!note) fields.note = ["This field may not be blank."];
  if (note.length > 300) fields.note = ["Ensure this field has no more than 300 characters."];
  if (Object.keys(fields).length) return kit.invalid(fields);
  const payment = paymentId === null ? undefined : finance.payments.find((row) => row.id === paymentId);
  if (paymentId !== null && !payment) return kit.invalid({ payment: ["No such payment (or not one you may see)."] });
  const refund = refundId === null ? undefined : finance.refunds.find((row) => row.id === refundId);
  if (refundId !== null && !refund) return kit.invalid({ refund: ["No such refund (or not one you may see)."] });
  if ([payment, refund, body.accept === true].filter(Boolean).length !== 1)
    return kit.invalid(refusal("Choose one: a payment, a refund, or accept it."));
  const line = settlement._lines.find((row) => row.id === lineId);
  if (!line) return kit.invalid({ line: ["No such line in this settlement."] });
  if (settlement.state === "posted")
    return kit.invalid(
      refusal(`Settlement ${settlement.settlement_id} was posted to ERPNext: correct its entry there.`),
    );
  if (line.matched) return kit.invalid(refusal(`Line ${line.entity_id} is matched already.`));
  if (payment) {
    if (payment.livemode !== settlement.livemode)
      return kit.invalid(refusal(`Payment #${payment.id} is of the other mode's keys.`));
    if (line.type === "payment") {
      if (payment.amount !== line.amount)
        return kit.invalid(refusal(`Payment #${payment.id} is ₹${payment.amount}, the line ₹${line.amount}.`));
      const elsewhere = finance.settlements.some((row) =>
        row._lines.some((each) => each.type === "payment" && each.payment?.id === payment.id),
      );
      if (elsewhere) return kit.invalid(refusal(`Payment #${payment.id} is another settlement line's already.`));
    }
    line.payment = { id: payment.id, order: payment.order, amount: payment.amount };
    line.order = payment.order;
  } else if (refund) {
    if (refund.livemode !== settlement.livemode)
      return kit.invalid(refusal(`Refund #${refund.id} is of the other mode's keys.`));
    line.refund = { id: refund.id, order: refund.order, amount: refund.amount };
    line.order = refund.order;
  } else if (line.type !== "adjustment") {
    return kit.invalid(refusal("Only an adjustment is accepted as it is: match a payment or a refund to this line."));
  }
  const when = iso();
  Object.assign(line, { matched: true, matched_at: when, matched_by: context.who.name, note: note.slice(0, 300) });
  const label = { target_type: "shop.settlement", target_id: String(settlement.id) };
  kit.record(context, "payment.settlement_line_matched", {
    ...label,
    target_label: `Settlement ${settlement.settlement_id}`,
    permission: RECONCILE,
    reason: note.slice(0, 500),
    details: { line: line.id, entity: line.entity_id, payment: payment?.id ?? null, refund: refund?.id ?? null },
  });
  if (payment && payment.settlement === null) {
    const { id, settlement_id, date, utr, state } = settlement;
    payment.settlement = { id, settlement_id, date, utr, state };
  }
  // evaluated again: matched once nothing is left (then its Journal Entry waits in ERPNext's outbox)
  const unmatched = settlement._lines.filter((row) => !row.matched).length;
  settlement.counts = { ...settlement.counts, unmatched };
  if (unmatched) {
    settlement.problem = `${unmatched} line${unmatched === 1 ? "" : "s"} not ours yet`;
  } else {
    Object.assign(settlement, { state: "matched", problem: "", matched_at: when, modified: when });
    settlement.erp = {
      outbox: kit.nextId(world),
      state: "pending",
      attempts: 0,
      last_error: "",
      sent_at: null,
      name: null,
    };
    kit.record(context, "payment.settlement_matched", {
      ...label,
      target_label: `Settlement ${settlement.settlement_id}`,
      details: { settlement: settlement.settlement_id, net: settlement.net },
    });
  }
  return kit.json(200, line);
}

/** A day of settlements fetched as a job (settlement_fetch): the mock's Razorpay has nothing new, so it counts. */
export function startSettlementFetch(context: SupportContext, kit: Kit, asked: Body): Response {
  const day = text(asked.day);
  const today = indiaDay(iso());
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day) || Number.isNaN(Date.parse(day)))
    return kit.invalid({ day: ["Date has wrong format. Use one of these formats instead: YYYY-MM-DD."] });
  if (day > today) return kit.invalid({ day: ["Not a day to come: Razorpay has not settled it."] });
  if (day < "2020-01-01") return kit.invalid({ day: ["A day from 2020 on."] });
  const found = context.world.finance.settlements.filter((row) => row.date === day && row.livemode);
  const states: Record<string, number> = {};
  for (const row of found) states[row.state] = (states[row.state] ?? 0) + 1;
  const job = kit.startJob(
    context,
    "settlement_fetch",
    { day },
    found.map((row) => row.settlement_id),
  );
  job.dry_run = asked.dry_run === true;
  job._result = {
    day,
    mode: "live",
    dry_run: job.dry_run,
    settlements: found.length,
    new_settlements: 0,
    lines: found.reduce((total, row) => total + row._lines.length, 0),
    new_lines: 0,
    matched_lines: 0,
    orders_paid_now: 0,
    states,
  };
  return kit.json(202, kit.visibleJob(context, job));
}

/** The links' POST: an order's link sent (made once, then again) or cancelled; a B2B invoice's made or cancelled. */
function askLink(context: SupportContext, kit: Kit): Response {
  const { body, world } = context;
  const finance = world.finance;
  const action = text(body.action);
  if (!["send", "cancel"].includes(action))
    return kit.invalid({ action: [action ? `"${action}" is not a valid choice.` : "This field is required."] });
  const order = text(body.order).toUpperCase();
  const invoice = text(body.invoice);
  if (Boolean(order) === Boolean(invoice)) return kit.invalid(refusal("Name one: an order, or a B2B invoice."));
  const answer = (row: S["FinanceLink"], detail: string, status = 200) => kit.json(status, { ...row, detail });
  if (invoice) {
    const open = finance.invoiceLinks.find((row) => row.invoice === invoice && invoiceLinkRow(row).state === "sent");
    if (action === "cancel") {
      if (!open) return kit.invalid(refusal(`No open link for invoice ${invoice}.`));
      open.state = "cancelled";
      kit.record(context, "payment.link_cancelled", {
        target_type: "shop.invoicepaymentlink",
        target_id: String(open.id),
        target_label: `Payment link ${open.id}`,
        details: { invoice },
      });
      return answer(open, "The payment link is cancelled.");
    }
    if (open) return answer(open, "This invoice's link is open already.");
    const outstanding = finance.invoices[invoice];
    if (outstanding === undefined)
      return kit.invalid(
        refusal(`No B2B invoice ${invoice} in the platform's copy of ERPNext (ERP_PULL_B2B keeps them).`),
      );
    if (Number(outstanding) <= 0) return kit.invalid(refusal(`Invoice ${invoice} has nothing outstanding.`));
    const id = kit.nextId(world);
    const made: S["FinanceLink"] = {
      kind: "invoice",
      id,
      order: null,
      invoice,
      amount: outstanding,
      state: "sent",
      url: `https://rzp.io/i/mockb2b${id}`,
      razorpay_link_id: `plink_mockb2b${id}`,
      razorpay_payment_id: null,
      sent_at: iso(),
      last_sent_at: null,
      expires_at: iso(Date.now() + LINK_DAYS * 24 * HOUR),
      paid_at: null,
      created_by: context.who.name,
      posted_at: null,
      erp_name: "",
      livemode: true,
      is_test: false,
    };
    finance.invoiceLinks.unshift(made);
    kit.record(context, "payment.link_made", {
      target_type: "shop.invoicepaymentlink",
      target_id: String(id),
      target_label: `Payment link ${id}`,
      details: { invoice, amount: outstanding },
    });
    return answer(made, "Made: send its address to the customer.", 201);
  }
  const known = finance.orders[order];
  if (!known) return kit.json(404, { detail: "No such order (or not one you may see).", code: "not_found" });
  if (known.website)
    return kit.invalid(refusal(`Order ${order} was placed on the website: its payment page is its link.`));
  if (!known.pending || known.cod) return kit.invalid(refusal(`Order ${order} is not waiting for an online payment.`));
  const open = finance.payments.find((row) => row.order === order && row.is_link && linkState(row) === "sent");
  const target = { target_type: "shop.order", target_id: order, target_label: order };
  if (action === "cancel") {
    if (!open) return kit.invalid(refusal(`Order ${order} has no payment link waiting to be paid.`));
    open.status = "failed";
    open.modified = iso();
    kit.record(context, "order.payment_link_cancelled", { ...target, details: { payment: open.id } });
    return answer(orderLinkRow(open), "The payment link is cancelled.");
  }
  let link = open;
  if (!link) {
    const id = kit.nextId(world);
    const now = iso();
    link = {
      id,
      order,
      order_id: Number(order.slice(-6)),
      order_status: "pending",
      order_total: known.amount,
      order_placed_at: now,
      method: "razorpay",
      amount: known.amount,
      status: "created",
      razorpay_order_id: null,
      razorpay_payment_id: null,
      razorpay_payment_link_id: `plink_mock${id}`,
      payment_link_url: `https://rzp.io/i/mock${id}`,
      reference: "",
      error: "",
      livemode: true,
      is_test: false,
      stuck: false,
      is_link: true,
      fee: null,
      tax: null,
      settlement: null,
      refunds: [],
      webhooks: [],
      last_webhook: null,
      timeline: [],
      created: now,
      modified: now,
    };
    finance.payments.unshift(link);
  }
  (link as Payment & { _sent?: string })._sent = iso();
  kit.record(context, "order.payment_link_sent", { ...target, details: { payment: link.id } });
  return answer(orderLinkRow(link), "Emailed to the customer.");
}

export function financeRoute(context: SupportContext, kit: Kit): Response {
  const { method, parts, url, world, body } = context;
  const finance = world.finance;
  const [, a, b, c, d] = parts;
  const query = (name: string) => url.searchParams.get(name) ?? "";

  if (a === "today" && method === "GET" && !b)
    return kit.json(200, { livemode: true, as_of: iso(), rows: todayRows(context) });

  if (a === "payments") {
    if (method === "GET" && !b) {
      const q = query("q").replace(/\s+/g, " ").slice(0, 60);
      const from = query("created_from");
      const to = query("created_to");
      const stuck = query("stuck");
      const rows = inMode(finance.payments, url)
        .filter((row) => !query("status") || row.status === query("status"))
        .filter((row) => !query("method") || row.method === query("method"))
        .filter((row) => !stuck || row.stuck === (stuck === "true" || stuck === "1"))
        .filter((row) => !from || indiaDay(row.created) >= from)
        .filter((row) => !to || indiaDay(row.created) <= to)
        .filter(
          (row) =>
            !q ||
            [row.order, row.razorpay_payment_id, row.razorpay_order_id, row.razorpay_payment_link_id, row.reference]
              .filter(Boolean)
              .some((value) => String(value).toUpperCase() === q.toUpperCase()),
        )
        .sort((x, y) => Date.parse(y.created) - Date.parse(x.created) || y.id - x.id)
        .map(listRow);
      return kit.paginate(context, rows);
    }
    const payment = finance.payments.find((row) => String(row.id) === b);
    if (!payment) return kit.notFound();
    if (method === "GET" && !c) return kit.json(200, payment);
    if (method === "POST" && c === "reconcile") return reconcile(context, kit, payment);
    return kit.notFound();
  }

  if ((a === "offline-payments" || a === "refunds") && method === "GET" && !b) {
    const state = query("state");
    const q = query("q").toUpperCase();
    const action = a === "refunds" ? "order.refund" : "order.offline_payment";
    if (state === "waiting") {
      const rows = waitingRequests(world, action)
        .filter((row) => !q || (row.target_label ?? "").toUpperCase() === q)
        .map((row) => requestRow(world, row));
      return kit.paginate(context, rows);
    }
    if (a === "offline-payments") {
      const rows = inMode(finance.payments, url)
        .filter((row) => row.method === "offline" && (!q || row.order === q))
        .map((row): S["FinanceRequestRow"] => ({
          ...BLANK_ROW,
          kind: "payment",
          id: row.id,
          order: row.order,
          amount: row.amount,
          status: row.status,
          reference: row.reference,
          created: row.created,
          done_at: row.created,
          livemode: row.livemode,
        }));
      return kit.paginate(context, rows);
    }
    const rows = inMode(finance.refunds, url)
      .filter((row) => !state || row.status === state)
      .filter((row) => !query("method") || row.method === query("method"))
      .filter((row) => !q || row.order === q)
      .sort((x, y) => Date.parse(y.created) - Date.parse(x.created));
    return kit.paginate(context, rows);
  }

  if (a === "payment-links") {
    if (b === "invoices" && method === "POST") {
      const found = finance.invoiceLinks.find((row) => String(row.id) === c);
      if (!found) return kit.notFound();
      const label = { target_type: "shop.invoicepaymentlink", target_id: String(found.id) };
      if (d === "reconcile") {
        const paid = found.state === "paid";
        kit.record(context, "payment.link_reconciled", {
          ...label,
          target_label: `Payment link ${found.id}`,
          details: { invoice: found.invoice, paid },
        });
        const detail = paid ? "Paid: post its entry in ERPNext." : "Razorpay has no payment for this link yet.";
        return kit.json(200, { ...invoiceLinkRow(found), detail });
      }
      if (d === "posted") {
        const name = text(body.erp_name).replace(/\s+/g, " ");
        if (!name) return kit.invalid({ erp_name: ["This field may not be blank."] });
        if (name.length > 140) return kit.invalid({ erp_name: ["Ensure this field has no more than 140 characters."] });
        if (found.state !== "paid")
          return kit.invalid(refusal(`The link for ${found.invoice} is not paid: nothing to post.`));
        if (found.posted_at) return kit.invalid(refusal(`Posted already, as ${found.erp_name}.`));
        Object.assign(found, { posted_at: iso(), erp_name: name });
        world.inbox
          .filter((item) => item.kind === "b2b_payment" && item.target_id === String(found.id) && !item.done_at)
          .forEach((item) => Object.assign(item, { done_at: iso(), done_by: context.who.id }));
        kit.record(context, "payment.link_posted", {
          ...label,
          target_label: `Payment link ${found.id}`,
          details: { invoice: found.invoice, erp_name: name },
        });
        return kit.json(200, { ...found, detail: "Recorded as posted." });
      }
      return kit.notFound();
    }
    if (b) return kit.notFound();
    if (method === "POST") return askLink(context, kit);
    if (method !== "GET") return kit.notFound();
    const q = query("q").replace(/\s+/g, " ");
    const state = query("state");
    const rows =
      query("kind") === "invoice"
        ? inMode(finance.invoiceLinks, url)
            .map(invoiceLinkRow)
            .filter((row) => !q || (row.invoice ?? "").toUpperCase() === q.toUpperCase())
        : inMode(
            finance.payments.filter((row) => row.is_link),
            url,
          )
            .map(orderLinkRow)
            .filter((row) => !q || row.order === q.toUpperCase());
    return kit.paginate(
      context,
      rows.filter((row) => !state || row.state === state).sort((x, y) => Date.parse(y.sent_at) - Date.parse(x.sent_at)),
    );
  }

  if (a === "settlements") {
    if (b === "fetch" && method === "POST") return startSettlementFetch(context, kit, body);
    if (method === "GET" && !b) {
      const q = query("q").replace(/\s+/g, " ");
      const rows = inMode(finance.settlements, url)
        .filter((row) => !query("state") || row.state === query("state"))
        .filter((row) => !query("date_from") || row.date >= query("date_from"))
        .filter((row) => !query("date_to") || row.date <= query("date_to"))
        .filter((row) => !q || row.settlement_id === q || row.utr.toUpperCase() === q.toUpperCase())
        .sort((x, y) => y.date.localeCompare(x.date) || y.id - x.id)
        .map(({ _lines, counts, erp, ...row }) => {
          void _lines;
          void counts;
          void erp;
          return row;
        });
      return kit.paginate(context, rows);
    }
    const settlement = finance.settlements.find((row) => String(row.id) === b);
    if (!settlement) return kit.notFound();
    if (method === "GET" && !c) {
      const { _lines, ...shown } = settlement;
      void _lines;
      return kit.json(200, shown);
    }
    if (method === "GET" && c === "lines") {
      const matched = query("matched");
      const rows = settlement._lines
        .filter((row) => !matched || row.matched === (matched === "true" || matched === "1"))
        .filter((row) => !query("type") || row.type === query("type"));
      return kit.paginate(context, rows, Number(query("page_size")) || 50);
    }
    if (method === "POST" && c === "match") return match(context, kit, settlement);
    return kit.notFound();
  }

  if (a === "documents" && method === "GET" && c === "erp") {
    const number = decodeURIComponent(b ?? "").toUpperCase();
    const found = finance.documents.find((row) => row.number.replaceAll("/", "-") === number.replaceAll("/", "-"));
    return found ? kit.json(200, found) : kit.notFound();
  }
  return kit.notFound();
}
