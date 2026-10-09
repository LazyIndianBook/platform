// THE ORDERS MODULE'S MOCK, FOR DEVELOPMENT AND TESTS ONLY (STAFF_API_MOCK=1 under `next dev`): its fixtures (orders
// in every state the console draws: paid and to pack, held, cash on delivery placed with a high risk, sent, delivered
// with a return asked for, cancelled, a staff order waiting for its payment, a bank refund waiting for FINANCE, a test
// order; returns asked for, received, refunded and declined; quotations new and ordered; books to find) and the
// answers of shop/staff_orders.py's paths (/api/v1/staff/orders/…), with the backend's rules kept: each path's
// permission (handler.ts), the actions the state machine allows crossed with the person's permissions, the role's
// refund and discount limits (202 with a change request above them), the Idempotency-Key, 400 in the API's words.
// handler.ts routes the "orders" area here and gives this module its tools (OrdersKit).
import type { Schemas } from "@/lib/api/staff";

type Mutable<T> = { -readonly [K in keyof T]: T[K] };
type S = { [K in keyof Schemas]: Mutable<Schemas[K]> };
type Body = Record<string, unknown>;
type Order = S["OrderDetail"];
type Return = S["ReturnDetail"];
type Quote = S["QuoteDetail"];
type Payment = Mutable<S["OrderPayment"]>;
type Refund = Mutable<S["OrderRefund"]>;

export type OrdersWorld = {
  orders: Order[];
  returns: Return[];
  quotes: Quote[];
  products: S["ProductPick"][];
  /** The first answer to each Idempotency-Key: the same key answers it again. */
  keys: Record<string, { status: number; body: unknown }>;
};

/** What handler.ts lends this module: the request, the person, and the mock's own ways of answering. */
export type OrdersKit = {
  url: URL;
  method: string;
  parts: string[];
  body: Body;
  request: Request;
  orders: OrdersWorld;
  me: number;
  can: (permission: string) => boolean;
  limit: (name: string) => number | null;
  nextId: () => number;
  json: (status: number, body: unknown) => Response;
  notFound: () => Response;
  invalid: (fields: Record<string, unknown>) => Response;
  record: (action: string, extra?: Record<string, unknown>) => void;
  waiting: (row: Body) => Response;
  executed: (row: Body, result: unknown) => S["ChangeRequest"];
  paginate: <T>(rows: T[], size?: number) => Response;
  startJob: (kind: S["Job"]["kind"], params: unknown, rows: string[]) => S["Job"];
};

const PDF =
  "%PDF-1.4\n% the staff API mock's stand-in\n1 0 obj << /Type /Catalog >> endobj\ntrailer << /Root 1 0 R >>\n%%EOF\n";
const pdf = (name: string) =>
  new Response(PDF, {
    headers: {
      "Content-Type": "application/pdf",
      "Content-Disposition": `attachment; filename="ExamLeaf-${name}.pdf"`,
      "Cache-Control": "no-store",
    },
  });

const money = (paise: number) => (paise / 100).toFixed(2);
const toPaise = (value: unknown) => Math.round(Number(value) * 100);
const text = (value: unknown) => (typeof value === "string" ? value.trim() : "");
const ADDRESS = (name: string, city = "Guwahati", district = "Kamrup Metro", pin = "781001") => ({
  name,
  phone: "••••••2210",
  line1: "House 4, Zoo Road",
  line2: "",
  city,
  district,
  state: "AS",
  pin,
});

// ---- Fixtures ----

type LineSpec = [title: string, isbn: string, unit: number, quantity: number, discount?: number];

function lines(id: number, specs: LineSpec[]): S["OrderLine"][] {
  return specs.map(([title, isbn, unit, quantity, discount = 0], index) => {
    const total = unit * quantity;
    return {
      id: id * 10 + index,
      product: title.toLowerCase().replace(/[^a-z0-9]+/g, "-"),
      title,
      isbn,
      hsn_code: "4901",
      gst_rate: "0.00",
      mrp: money(unit * 100 + 5000),
      unit_price: money(unit * 100),
      quantity,
      line_total: money(total * 100),
      discount: money(discount * 100),
      invoiced: money((total - discount) * 100),
      refunded: 0,
      returnable: quantity,
      digital: false,
    };
  });
}

type OrderSpec = Partial<Order> & {
  id: number;
  number: string;
  status: Order["status"];
  specs: LineSpec[];
  customer: Order["customer"];
  hours: number;
};

function order(at: (hours: number) => string, spec: OrderSpec): Order {
  const { specs, hours, ...rest } = spec;
  const orderLines = lines(spec.id, specs);
  const subtotal = orderLines.reduce((sum, line) => sum + toPaise(line.line_total), 0);
  const discount = orderLines.reduce((sum, line) => sum + toPaise(line.discount), 0);
  const shipping = toPaise(rest.shipping_fee ?? "40.00");
  const total = subtotal - discount + shipping;
  const created = at(hours);
  const method = rest.payment_method ?? "razorpay";
  const paid = !["pending", "cancelled"].includes(spec.status) || (method === "cod" && rest.placed_at !== null);
  return {
    status_label: "",
    payment_method: method,
    items: orderLines.map((line) => `${line.title} × ${line.quantity}`),
    courier: null,
    parcel: null,
    tags: [],
    held: false,
    hold_reason: "",
    risk_bucket: "",
    is_test: false,
    is_cod: method === "cod",
    has_returns: false,
    staff_order: false,
    livemode: true,
    created,
    placed_at: created,
    subtotal: money(subtotal),
    discount: money(discount),
    shipping_fee: money(shipping),
    coupon_code: "",
    savings: discount ? [{ label: "Coupon EXAM10", amount: money(discount) }] : [],
    address: ADDRESS(spec.customer.name),
    lines: orderLines,
    payments:
      method === "razorpay" && paid
        ? [
            {
              id: spec.id * 10,
              method: "razorpay",
              amount: money(total),
              status: "captured",
              razorpay_order_id: `order_mock${spec.id}`,
              razorpay_payment_id: `pay_mock${spec.id}`,
              payment_link_url: "",
              reference: "",
              error: "",
              created,
              modified: created,
              refundable: money(total),
              older_than_6_months: false,
            },
          ]
        : [],
    refunds: [],
    documents: [],
    shipments: [],
    returns: [],
    hold: null,
    risk_reasons: [],
    is_digital: false,
    quote: null,
    created_by: null,
    actions: [],
    refund: {
      payment: null,
      payment_method: null,
      refundable: "0.00",
      shipping_left: money(shipping),
      methods: [],
      cancels: false,
      payment_age_days: null,
      warnings: [],
    },
    erp: [],
    timeline: [],
    modified: created,
    ...rest,
    total: money(total),
  } as Order;
}

const STATUS_LABELS: Record<string, string> = {
  pending: "awaiting payment",
  paid: "paid",
  packed: "packed",
  shipped: "sent",
  delivered: "delivered",
  cancelled: "cancelled",
  refunded: "refunded",
};

export function ordersWorld(at: (hours: number) => string): OrdersWorld {
  const riya = { id: 7101, name: "Riya Das", email: "ri•••@example.com", phone: "••••••2210", is_minor: true };
  const bikash = { id: 7102, name: "Bikash Deka", email: "bi•••@example.com", phone: "••••••1873", is_minor: false };
  const kabir = { id: 7105, name: "Kabir Ahmed", email: "ka•••@example.com", phone: "••••••2118", is_minor: false };
  const guest = { id: null, name: "Anita Gogoi", email: "an•••@example.com", phone: "••••••4410", is_minor: false };
  const school = {
    id: null,
    name: "Cotton Collegiate",
    email: "of•••@example.com",
    phone: "••••••0101",
    is_minor: false,
  };

  const shipped = order(at, {
    id: 41,
    number: "EL-2026-000123",
    status: "shipped",
    customer: riya,
    hours: -24 * 6,
    specs: [
      ["Physics Sample Papers 2027", "978-93-0000-000-1", 900, 1],
      ["Chemistry Sample Papers 2027", "978-93-0000-000-2", 850, 1],
      ["Biology Sample Papers 2027", "978-93-0000-000-3", 710, 1],
    ],
    courier: { name: "India Post", tracking_number: "EA123456789IN" },
    parcel: "in_transit",
    tags: ["school"],
  });
  shipped.shipments = [
    {
      id: 301,
      order: "EL-2026-000123",
      courier: "India Post",
      tracking_number: "EA123456789IN",
      tracking_url: "",
      shipped_at: at(-24 * 4),
      delivered_at: null,
      detail: null,
      last_event: {
        source: "poll",
        carrier_label: "Item dispatched",
        status: "in_transit",
        occurred_at: at(-30),
        location: "Guwahati NSH",
      },
    },
  ] as Order["shipments"];
  shipped.documents = [
    {
      kind: "invoice",
      id: 901,
      number: "EL/2026-27/00123",
      created: at(-24 * 6),
      ready: true,
      url: "/api/v1/staff/orders/EL-2026-000123/invoice/",
      amount: shipped.total,
    },
  ];

  const toPack = order(at, {
    id: 44,
    number: "EL-2026-000130",
    status: "paid",
    customer: bikash,
    hours: -24,
    specs: [["Mathematics Sample Papers 2027", "978-93-0000-000-4", 729.5, 2]],
    shipping_fee: "40.00",
  });
  const held = order(at, {
    id: 45,
    number: "EL-2026-000131",
    status: "paid",
    customer: kabir,
    hours: -20,
    specs: [["Physics Sample Papers 2027", "978-93-0000-000-1", 379, 2]],
    held: true,
    hold_reason: "address to check",
    hold: { at: at(-19), by: "Admin E2E", reason: "address to check" },
  });
  const risky = order(at, {
    id: 46,
    number: "EL-2026-000132",
    status: "pending",
    status_label: "placed (pay on delivery)",
    payment_method: "cod",
    customer: guest,
    hours: -10,
    specs: [["Chemistry Sample Papers 2027", "978-93-0000-000-2", 579, 2]],
    risk_bucket: "high",
    risk_reasons: ["40% of COD parcels to this PIN code come back", "the customer's first cash-on-delivery order"],
    held: true,
    hold_reason: "payment check",
    hold: { at: at(-10), by: "the site", reason: "payment check" },
  });
  const cod = order(at, {
    id: 47,
    number: "EL-2026-000133",
    status: "pending",
    status_label: "placed (pay on delivery)",
    payment_method: "cod",
    customer: bikash,
    hours: -30,
    specs: [["Biology Sample Papers 2027", "978-93-0000-000-3", 299, 1]],
    risk_bucket: "low",
  });
  const delivered = order(at, {
    id: 48,
    number: "EL-2026-000134",
    status: "delivered",
    customer: bikash,
    hours: -24 * 9,
    specs: [
      ["Physics Sample Papers 2027", "978-93-0000-000-1", 450, 2, 90],
      ["Chemistry Sample Papers 2027", "978-93-0000-000-2", 400, 1, 40],
    ],
    has_returns: true,
    courier: { name: "Delhivery", tracking_number: "1490817263" },
    parcel: "delivered",
  });
  const cancelled = order(at, {
    id: 49,
    number: "EL-2026-000135",
    status: "cancelled",
    customer: kabir,
    hours: -24 * 3,
    specs: [["English Sample Papers 2027", "978-93-0000-000-5", 299, 1]],
  });
  cancelled.payments = [];
  const draft = order(at, {
    id: 50,
    number: "EL-2026-000136",
    status: "pending",
    customer: school,
    hours: -5,
    placed_at: null,
    specs: [["Physics Sample Papers 2027", "978-93-0000-000-1", 270, 40]],
    staff_order: true,
    created_by: "Rina Sales",
    quote: "QT-00011",
    tags: ["school"],
  });
  draft.payments = [
    {
      id: 501,
      method: "razorpay",
      amount: draft.total,
      status: "created",
      razorpay_order_id: null,
      razorpay_payment_id: null,
      payment_link_url: "https://rzp.io/i/mock50",
      reference: "",
      error: "",
      created: at(-5),
      modified: at(-5),
      refundable: "0.00",
      older_than_6_months: false,
    },
  ];
  const bank = order(at, {
    id: 51,
    number: "EL-2026-000137",
    status: "refunded",
    payment_method: "cod",
    customer: kabir,
    hours: -24 * 12,
    specs: [["Mathematics Sample Papers 2027", "978-93-0000-000-4", 349, 1]],
  });
  bank.refunds = [
    {
      id: 71,
      amount: "349.00",
      status: "pending",
      reason: "Pages 12 to 16 missing",
      method: "bank",
      speed: "normal",
      lines: [{ item: 510, quantity: 1, amount: "349.00" }],
      shipping_amount: "0.00",
      restock: false,
      payee_masked: "UPI ka•••@okicici",
      utr: "",
      arn: "",
      razorpay_refund_id: null,
      change_request: null,
      created: at(-20),
      processed_at: null,
      error: "",
      credit_note: null,
      payment_method: "cod",
    },
  ];
  const test = order(at, {
    id: 52,
    number: "T-2026-000004",
    status: "paid",
    customer: bikash,
    hours: -2,
    specs: [["Physics Sample Papers 2027", "978-93-0000-000-1", 1, 1]],
    is_test: true,
    livemode: false,
  });
  const orders = [test, draft, risky, held, toPack, cod, cancelled, shipped, delivered, bank];
  for (const each of orders) each.status_label ||= STATUS_LABELS[each.status];

  const backLines = (source: Order, quantity: number) => [
    { item: source.lines[0].id, title: source.lines[0].title, quantity },
  ];
  const ret = (row: Partial<Return> & { id: number; status: Return["status"]; source: Order }): Return => {
    const { source, ...rest } = row;
    return {
      number: `RR-${String(row.id).padStart(5, "0")}`,
      order: source.number ?? "",
      status_label: "",
      reason: "damaged",
      reason_label: "damaged in transit",
      lines: backLines(source, 1),
      by_customer: true,
      decision_note: "",
      return_courier: "",
      return_awb: "",
      photos: 0,
      received_at: null,
      inspected_at: null,
      refund: null,
      created: at(-30),
      modified: at(-30),
      note: "The cover was torn and pages 4 to 9 are creased.",
      next: [],
      ...rest,
    } as Return;
  };
  const returns = [
    ret({ id: 7, status: "requested", source: delivered, created: at(-6) }),
    ret({
      id: 6,
      status: "received",
      source: delivered,
      reason: "misprint",
      reason_label: "misprinted or pages missing",
      received_at: at(-3),
      photos: 1,
      by_customer: false,
      note: "Asked for by phone (ticket 4420).",
    }),
    ret({
      id: 5,
      status: "declined",
      source: delivered,
      decision_note: "Asked for 40 days after delivery.",
      reason: "late",
      reason_label: "delivered late",
    }),
  ];
  delivered.returns = returns.map(({ note, next, ...row }) => {
    void note;
    void next;
    return row;
  });

  const quote = (row: Partial<Quote> & { id: number; status: Quote["status"] }): Quote =>
    ({
      number: `QT-${String(row.id).padStart(5, "0")}`,
      school: "Cotton Collegiate Government HS School",
      contact_name: "Anita Das",
      email: "of•••@example.com",
      phone: "••••••0101",
      gstin: "",
      delivery_pin: "781001",
      copies: 40,
      discount_percent: "10.00",
      shipping_fee: "120.00",
      quoted_at: null,
      valid_until: null,
      has_quotation: false,
      order: null,
      created: at(-48),
      items: [{ product: "physics-sample-papers-2027", title: "Physics Sample Papers 2027", quantity: 40 }],
      note: "For the Class 12 batch; delivery before 1 December.",
      waiting: null,
      ...row,
    }) as Quote;
  const quotes = [
    quote({ id: 12, status: "new", school: "Don Bosco School, Guwahati", copies: 60 }),
    quote({
      id: 11,
      status: "ordered",
      order: "EL-2026-000136",
      has_quotation: true,
      quoted_at: at(-40),
      valid_until: at(24 * 20).slice(0, 10),
    }),
  ];

  const products: S["ProductPick"][] = [
    ["physics-sample-papers-2027", "Physics Sample Papers 2027", "978-93-0000-000-1", 299, 120],
    ["chemistry-sample-papers-2027", "Chemistry Sample Papers 2027", "978-93-0000-000-2", 299, 80],
    ["biology-sample-papers-2027", "Biology Sample Papers 2027", "978-93-0000-000-3", 299, 0],
    ["mathematics-sample-papers-2027", "Mathematics Sample Papers 2027", "978-93-0000-000-4", 349, 64],
  ].map(([slug, title, isbn, price, available]) => ({
    slug: String(slug),
    title: String(title),
    kind: "sample-papers",
    isbn: String(isbn),
    price: Number(price).toFixed(2),
    mrp: (Number(price) + 50).toFixed(2),
    available: Number(available),
  })) as S["ProductPick"][];

  return { orders, returns, quotes, products, keys: {} };
}

// ---- Permissions (shop/staff_orders.py's `permissions`) ----

export function ordersPermission(method: string, parts: string[]): string {
  const [, a, b, c] = parts; // ["orders", …]
  const get = method === "GET";
  if (a === "returns") {
    if (get) return "shop.view_returnrequest";
    return ["receive", "inspect", "photos"].includes(c ?? "") ? "staff.receive_return" : "staff.handle_return";
  }
  if (a === "refunds") return "staff.approve_refund";
  if (a === "quotes") return get ? "shop.view_quoterequest" : "shop.change_quoterequest";
  if (a === "products") return "shop.view_product";
  if (a === "preview") return "shop.add_order";
  if (a === "pick-list") return "staff.pack_order";
  if (!a) return get ? "shop.view_order" : "shop.add_order";
  if (a === "packing") return "shop.view_order";
  if (get) {
    if (b === "documents") return "staff.pack_order";
    if (b === "invoice") return "shop.view_invoice";
    if (b === "credit-notes") return "shop.view_creditnote";
    return "shop.view_order";
  }
  const verbs: Record<string, string> = {
    pack: "staff.pack_order",
    ship: "staff.pack_order",
    deliver: "staff.pack_order",
    refunds: "staff.refund_order",
    "offline-payment": "staff.record_offline_payment",
    returns: "staff.handle_return",
  };
  return verbs[b ?? ""] ?? "shop.change_order";
}

/** The permission of POST jobs/ for an orders kind (staff.jobs.permission), or null. */
export function ordersJobPermission(kind: unknown): string | null {
  const kinds: Record<string, string> = {
    orders_pack: "staff.pack_order",
    orders_print: "staff.pack_order",
    orders_cancel: "shop.change_order",
    orders_export: "shop.export_order",
  };
  return typeof kind === "string" ? (kinds[kind] ?? null) : null;
}

// ---- The answers ----

const PAID = new Set(["paid", "packed", "shipped", "delivered"]);

function refundable(order: Order): number {
  const payment = order.payments.find((each) => each.status === "captured");
  const paid = payment ? toPaise(payment.amount) : order.is_cod && PAID.has(order.status) ? toPaise(order.total) : 0;
  const given = order.refunds
    .filter((refund) => refund.status !== "failed")
    .reduce((sum, r) => sum + toPaise(r.amount), 0);
  return Math.max(0, paid - given);
}

function refundOptions(order: Order): Order["refund"] {
  const left = refundable(order);
  const online = order.payments.some((each) => each.method === "razorpay" && each.status === "captured");
  const given = order.refunds.reduce((sum, refund) => sum + toPaise(refund.shipping_amount), 0);
  return {
    payment: left ? (order.payments[0]?.id ?? order.id * 10) : null,
    payment_method: left ? (online ? "razorpay" : order.payment_method) : null,
    refundable: money(left),
    shipping_left: money(Math.max(0, toPaise(order.shipping_fee) - given)),
    methods: left ? (online ? ["source", "bank"] : ["bank"]) : [],
    cancels: left > 0 && order.status === "paid",
    payment_age_days: left ? 1 : null,
    warnings: [],
  };
}

function actionsFor(order: Order, can: (permission: string) => boolean): Order["actions"] {
  const awaiting = order.status === "pending" && !order.placed_at && !order.is_cod;
  const placedCod = order.status === "pending" && order.is_cod && Boolean(order.placed_at);
  const moves: [string, string, boolean][] = [
    ["release", "shop.change_order", order.held],
    ["hold", "shop.change_order", !order.held && (order.status === "paid" || placedCod)],
    ["payment_link", "shop.change_order", awaiting && order.staff_order],
    ["offline_payment", "staff.record_offline_payment", awaiting],
    ["pack", "staff.pack_order", !order.held && (order.status === "paid" || placedCod)],
    ["ship", "staff.pack_order", order.status === "packed"],
    ["deliver", "staff.pack_order", order.status === "shipped"],
    ["refund", "staff.refund_order", refundable(order) > 0],
    ["return", "staff.handle_return", order.status === "delivered"],
    ["cancel", "shop.change_order", order.status === "pending" || order.status === "paid"],
    ["tags", "shop.change_order", true],
    ["notify", "shop.change_order", Boolean(order.placed_at) || order.status === "cancelled"],
    ["invoice", "shop.change_order", order.documents.length > 0 || PAID.has(order.status)],
  ];
  const allowed = moves.filter(([, permission, possible]) => possible && can(permission));
  const first = allowed.find(([name]) => ["release", "payment_link", "pack", "ship", "deliver"].includes(name))?.[0];
  return allowed.map(([name, permission]) => ({ name, permission, primary: name === first }));
}

const ROW_FIELDS = ["id", "number", "created", "placed_at", "status", "status_label", "payment_method", "total"].concat(
  ["items", "customer", "courier", "parcel", "tags", "held", "hold_reason", "risk_bucket", "is_test", "is_cod"],
  ["has_returns", "staff_order", "livemode"],
);
const rowOf = (order: Order) => Object.fromEntries(ROW_FIELDS.map((name) => [name, order[name as keyof Order]]));

function detailOf(order: Order, can: (permission: string) => boolean): Order {
  return {
    ...order,
    actions: actionsFor(order, can),
    refund: refundOptions(order),
    timeline: [
      { at: order.created, kind: "status", label: "Status: ordered", actor: "the customer", details: {} },
      ...(order.placed_at && order.status !== "pending"
        ? [{ at: order.placed_at, kind: "payment", label: "Payment received", actor: "", details: {} }]
        : []),
      ...order.timeline,
    ],
  };
}

function tabbed(order: Order, tab: string): boolean {
  switch (tab) {
    case "to_pack":
      return (
        !order.held && (order.status === "paid" || (order.status === "pending" && order.is_cod && !!order.placed_at))
      );
    case "shipped":
      return order.status === "shipped";
    case "returns":
      return order.has_returns || order.parcel === "returning" || order.parcel === "returned";
    case "cancelled":
      return order.status === "cancelled";
    case "drafts":
      return order.status === "pending" && !order.placed_at && order.staff_order;
    default:
      return true;
  }
}

/** The kind of search `q` is (shop/staff_orders.py classify): a person's searches are audited by their hash. */
function classify(value: string): "number" | "document" | "email" | "phone" | "name" | "none" {
  if (/^(el|t)-\d{4}-\d{6,}$/i.test(value)) return "number";
  if (/^(el|t|cn|tc)\/\d{4}-\d{2}\/\d{5}$/i.test(value)) return "document";
  if (value.includes("@")) return "email";
  if (/^[\d\s+-]+$/.test(value) && value.replace(/\D/g, "").length >= 4) return "phone";
  return value.length >= 3 ? "name" : "none";
}

function listOrders(kit: OrdersKit): Response {
  const query = (name: string) => kit.url.searchParams.get(name) ?? "";
  const q = query("q").trim();
  const kind = q ? classify(q) : "none";
  const rows = kit.orders.orders.filter((order) => {
    if (query("livemode") === "false" ? order.livemode : !order.livemode) return false;
    if (!tabbed(order, query("tab"))) return false;
    if (query("status") && order.status !== query("status")) return false;
    if (query("method") && order.payment_method !== query("method")) return false;
    if (query("risk") && order.risk_bucket !== query("risk")) return false;
    if (query("hold") && String(order.held) !== query("hold")) return false;
    if (query("tag") && !order.tags.includes(query("tag").toLowerCase())) return false;
    if (
      query("shipping") &&
      (query("shipping") === "none" ? order.parcel !== null : order.parcel !== query("shipping"))
    )
      return false;
    if (q) {
      const needle = q.toLowerCase();
      if (kind === "number") return (order.number ?? "").toLowerCase() === needle;
      if (kind === "name") return order.customer.name.toLowerCase().includes(needle);
      if (kind === "phone") return order.customer.phone.endsWith(needle.replace(/\D/g, "").slice(-4));
      if (kind === "email") return order.customer.email.slice(0, 2) === needle.slice(0, 2);
      return false;
    }
    return true;
  });
  if (["email", "phone", "name"].includes(kind))
    kit.record("customer.lookup", { details: { kind, query: "hash:mock", found: rows.length, list: "orders" } });
  return kit.paginate(rows.map(rowOf), 20);
}

const refuse400 = (kit: OrdersKit, message: string) => kit.invalid({ non_field_errors: [message] });

async function idempotent(kit: OrdersKit, make: () => Response): Promise<Response> {
  const key = kit.request.headers.get("Idempotency-Key") ?? "";
  const seen = key ? kit.orders.keys[key] : undefined;
  if (seen) return kit.json(seen.status === 201 ? 200 : seen.status, seen.body);
  const answer = make();
  if (key && (answer.status === 201 || answer.status === 202))
    kit.orders.keys[key] = { status: answer.status, body: await answer.clone().json() };
  return answer;
}

function askRefund(kit: OrdersKit, order: Order): Response {
  const body = kit.body;
  const reason = text(body.reason);
  if (!reason) return kit.invalid({ reason: ["This field may not be blank."] });
  const options = refundOptions(order);
  if (!options.methods.length) return refuse400(kit, `Nothing is left to refund on order ${order.number}.`);
  const method = text(body.method) || options.methods[0];
  if (!options.methods.includes(method))
    return refuse400(kit, "Cash on delivery and transfers are refunded by bank or UPI to the customer's account.");
  const payee = (body.payee ?? {}) as Body;
  if (method === "bank" && !text(payee.upi) && !text(payee.account))
    return kit.invalid({ payee: { upi: ["The customer's UPI ID, or a bank account."] } });
  if (method === "bank" && options.payment_method === "razorpay" && body.customer_agreed !== true)
    return kit.invalid({ customer_agreed: ["An online payment goes to a bank only with the customer's agreement."] });
  const asked = Array.isArray(body.lines) ? (body.lines as Body[]) : [];
  let amount = 0;
  const priced = [];
  for (const row of asked) {
    const line = order.lines.find((each) => each.id === Number(row.item));
    const quantity = Number(row.quantity);
    if (!line || !Number.isInteger(quantity) || quantity < 0)
      return refuse400(kit, "Each line: one of the order's items, once.");
    if (!quantity) continue;
    const left = line.quantity - line.refunded;
    if (quantity > left) return refuse400(kit, `${line.title}: ${left} of ${line.quantity} copies are left to refund.`);
    const value = Math.round((toPaise(line.invoiced) * quantity) / line.quantity);
    priced.push({ item: line.id, quantity, amount: money(value) });
    amount += value;
  }
  const shipping = body.shipping === undefined ? 0 : toPaise(body.shipping);
  if (shipping > toPaise(options.shipping_left))
    return kit.invalid({ shipping: [`At most ₹${options.shipping_left} of the shipping is left.`] });
  amount += shipping;
  if (!priced.length && !shipping) amount = toPaise(options.refundable);
  if (amount > toPaise(options.refundable))
    return refuse400(kit, `Only ₹${options.refundable} is left of the payment to refund.`);
  const payload = { order: order.number, amount: money(amount), cancel: options.cancels, method, lines: priced };
  const row = {
    action: "order.refund",
    label: "Refund an order",
    target_type: "shop.order",
    target_id: String(order.id),
    target_label: order.number,
    payload,
    amount: money(amount),
    reason,
    checker: "staff.approve_refund",
  };
  const limit = kit.limit("refund_inr");
  if (limit !== null && amount > limit * 100) {
    const answer = kit.waiting({
      ...row,
      rule: `A refund of ₹${(amount / 100).toLocaleString("en-IN", { minimumFractionDigits: 2 })} is above the limit of ₹${limit.toLocaleString("en-IN")}.`,
    });
    return answer;
  }
  const refundId = kit.nextId();
  const done = kit.executed(row, { refund: refundId, amount: money(amount), status: "pending" });
  order.refunds.unshift({
    id: refundId,
    amount: money(amount),
    status: method === "bank" ? "pending" : "processed",
    reason,
    method: method as "source" | "bank",
    speed: text(body.speed) === "optimum" ? "optimum" : "normal",
    lines: priced,
    shipping_amount: money(shipping),
    restock: body.restock === true,
    payee_masked: method === "bank" ? (text(payee.upi) ? `UPI ${text(payee.upi).slice(0, 2)}•••` : "Account ••••") : "",
    utr: "",
    arn: "",
    razorpay_refund_id: method === "source" ? `rfnd_mock${refundId}` : null,
    change_request: done.id,
    created: new Date().toISOString(),
    processed_at: method === "bank" ? null : new Date().toISOString(),
    error: "",
    credit_note: null,
    payment_method: order.payment_method,
  });
  for (const line of priced) {
    const found = order.lines.find((each) => each.id === line.item);
    if (found) found.refunded += line.quantity;
  }
  if (options.cancels) order.status = "cancelled";
  return kit.json(201, { ...done, warnings: [] });
}

async function orderMove(kit: OrdersKit, order: Order, move: string): Promise<Response> {
  const body = kit.body;
  const ok = () => kit.json(200, rowOf(order));
  const allowed = (name: string) => actionsFor(order, () => true).some((action) => action.name === name);
  const label = { target_type: "shop.order", target_id: String(order.id), target_label: order.number };
  switch (move) {
    case "pack":
      if (order.held)
        return refuse400(kit, `Order ${order.number} is on hold (${order.hold_reason}): release it first.`);
      if (!allowed("pack")) return refuse400(kit, "Not possible for this order in its present state.");
      order.status = "packed";
      order.status_label = STATUS_LABELS.packed;
      kit.record("order.packed", label);
      return ok();
    case "ship":
      if (!allowed("ship")) return refuse400(kit, "Not possible for this order in its present state.");
      if (!text(body.tracking_number)) return kit.invalid({ tracking_number: ["This field may not be blank."] });
      order.status = "shipped";
      order.status_label = STATUS_LABELS.shipped;
      order.courier = { name: text(body.courier) || "India Post", tracking_number: text(body.tracking_number) };
      kit.record("shipping.shipped_by_hand", label);
      return ok();
    case "deliver":
      if (!allowed("deliver")) return refuse400(kit, "Not possible for this order in its present state.");
      order.status = "delivered";
      order.status_label = STATUS_LABELS.delivered;
      kit.record("order.delivered", label);
      return ok();
    case "hold": {
      const reason = text(body.reason);
      if (!reason) return kit.invalid({ reason: ["This field may not be blank."] });
      if (order.held) return refuse400(kit, `Order ${order.number} is on hold already.`);
      order.held = true;
      order.hold_reason = reason;
      order.hold = { at: new Date().toISOString(), by: "You", reason };
      kit.record("order.held", { ...label, reason });
      return ok();
    }
    case "release":
      if (!order.held) return refuse400(kit, `Order ${order.number} is not on hold.`);
      order.held = false;
      order.hold_reason = "";
      order.hold = null;
      kit.record("order.released", label);
      return ok();
    case "tags": {
      const clean = (value: unknown) =>
        (Array.isArray(value) ? value : [])
          .map((tag) => String(tag).trim().toLowerCase().replace(/\s+/g, " "))
          .filter(Boolean);
      const tags = new Set(order.tags);
      for (const tag of clean(body.add)) tags.add(tag.slice(0, 40));
      for (const tag of clean(body.remove)) tags.delete(tag);
      if (tags.size > 10) return kit.invalid({ add: ["Ten tags at most."] });
      order.tags = [...tags].sort();
      kit.record("order.tagged", label);
      return ok();
    }
    case "notify": {
      const kind = text(body.kind);
      if (kind !== order.status && !(kind === "placed" && order.placed_at))
        return refuse400(
          kit,
          `Order ${order.number} is ${STATUS_LABELS[order.status]}: that message is no longer true.`,
        );
      kit.record("order.notified", { ...label, details: { kind } });
      return kit.json(200, { detail: `Sent again: the ${kind} email.` });
    }
    case "payment-link": {
      if (!allowed("payment_link"))
        return refuse400(kit, `Order ${order.number} is not waiting for an online payment.`);
      const payment = order.payments[0] as Payment | undefined;
      if (text(body.action) === "cancel") {
        if (payment) payment.payment_link_url = "";
        kit.record("order.payment_link_cancelled", label);
        return kit.json(200, { detail: "The payment link is cancelled.", url: "" });
      }
      const url = payment?.payment_link_url || `https://rzp.io/i/mock${order.id}${kit.nextId()}`;
      if (payment) payment.payment_link_url = url;
      kit.record("order.payment_link_sent", label);
      return kit.json(200, { detail: "Emailed to the customer.", url });
    }
    case "offline-payment": {
      if (!text(body.reference)) return kit.invalid({ reference: ["This field may not be blank."] });
      if (!text(body.reason)) return kit.invalid({ reason: ["This field may not be blank."] });
      const amount = toPaise(order.total);
      const limit = kit.limit("offline_inr");
      const row = {
        action: "order.offline_payment",
        label: "Record a payment received offline",
        ...label,
        payload: { order: order.number, reference: text(body.reference), amount: order.total },
        amount: order.total,
        reason: text(body.reason),
        checker: "staff.approve_payment",
      };
      if (limit !== null && amount > limit * 100)
        return kit.waiting({ ...row, rule: `₹${order.total} paid offline is above the limit of ₹${limit}.` });
      order.status = "paid";
      order.status_label = STATUS_LABELS.paid;
      return kit.json(201, kit.executed(row, { order: order.number, paid: true }));
    }
    case "cancel": {
      const reason = text(body.reason);
      if (!reason) return kit.invalid({ reason: ["This field may not be blank."] });
      if (!allowed("cancel"))
        return refuse400(
          kit,
          `Order ${order.number} is ${STATUS_LABELS[order.status]}: refund it, or ask for a return.`,
        );
      if (order.payments.some((payment) => payment.method === "razorpay" && payment.status === "captured"))
        return idempotent({ ...kit, body: { reason } }, () => askRefund({ ...kit, body: { reason } }, order));
      order.status = "cancelled";
      order.status_label = STATUS_LABELS.cancelled;
      kit.record("order.cancelled", { ...label, reason });
      return ok();
    }
    case "refunds":
      return idempotent(kit, () => askRefund(kit, order));
    case "returns": {
      if (order.status !== "delivered") return refuse400(kit, "Only a delivered order's books are sent back.");
      const asked = (Array.isArray(body.lines) ? (body.lines as Body[]) : []).filter((row) => Number(row.quantity) > 0);
      if (!asked.length) return kit.invalid({ lines: ["Choose the copies to send back."] });
      const id = kit.nextId();
      const back: Return = {
        id,
        number: `RR-${String(id).padStart(5, "0")}`,
        order: order.number ?? "",
        status: "requested",
        status_label: "",
        reason: (text(body.reason) || "other") as Return["reason"],
        reason_label: text(body.reason) || "other",
        lines: asked.map((row) => ({
          item: Number(row.item),
          title: order.lines.find((line) => line.id === Number(row.item))?.title ?? "",
          quantity: Number(row.quantity),
        })),
        by_customer: false,
        decision_note: "",
        return_courier: "",
        return_awb: "",
        photos: 0,
        received_at: null,
        inspected_at: null,
        refund: null,
        created: new Date().toISOString(),
        modified: new Date().toISOString(),
        note: text(body.note),
        next: ["approve", "decline"],
      };
      kit.orders.returns.unshift(back);
      order.has_returns = true;
      kit.record("order.return_requested", label);
      return kit.json(201, back);
    }
    case "invoice/regenerate":
      if (order.documents.some((document) => document.ready))
        return refuse400(kit, "Nothing is missing: its documents are made.");
      return kit.json(202, { detail: "Being made: the documents appear on the order within a minute." });
    case "invoice/resend":
      if (!order.documents.some((document) => document.kind === "invoice" && document.ready))
        return refuse400(kit, `Order ${order.number} has no invoice yet: make it first.`);
      kit.record("order.invoice_sent", label);
      return kit.json(200, { detail: "Sent to the customer's address." });
  }
  return kit.notFound();
}

const RETURN_NEXT: Record<string, string[]> = {
  requested: ["approve", "decline"],
  approved: ["label", "receive"],
  label_sent: ["receive"],
  received: ["inspect"],
  restocked: ["refund"],
  damaged: ["refund"],
};

function returnRoute(kit: OrdersKit, id: string | undefined, move: string | undefined): Response {
  if (!id) {
    const query = (name: string) => kit.url.searchParams.get(name) ?? "";
    const open = ["requested", "approved", "label_sent", "received"];
    const rows = kit.orders.returns.filter(
      (back) =>
        (!query("status") || back.status === query("status")) &&
        (!query("open") || open.includes(back.status) === (query("open") === "true")) &&
        (!query("reason") || back.reason === query("reason")) &&
        (!query("order") || back.order.toLowerCase() === query("order").toLowerCase()),
    );
    return kit.paginate(
      rows.map(({ note, next, ...row }) => (void note, void next, row)),
      20,
    );
  }
  const back = kit.orders.returns.find((row) => String(row.id) === id);
  if (!back) return kit.notFound();
  const view = () => ({ ...back, next: back.refund ? [] : (RETURN_NEXT[back.status] ?? []) });
  if (kit.method === "GET" && !move) return kit.json(200, view());
  if (kit.method === "GET" && move === "photos") return pdf("photo");
  const can = (step: string) => view().next.includes(step);
  const refusal = () => refuse400(kit, `Return ${back.number} is ${back.status.replace("_", " ")}: not possible now.`);
  const now = new Date().toISOString();
  switch (move) {
    case "approve":
      if (!can("approve")) return refusal();
      back.status = "approved";
      break;
    case "decline":
      if (!can("decline")) return refusal();
      if (!text(kit.body.note)) return kit.invalid({ note: ["This field may not be blank."] });
      back.status = "declined";
      back.decision_note = text(kit.body.note);
      break;
    case "label":
      if (!can("label")) return refusal();
      if (!text(kit.body.awb)) return kit.invalid({ awb: ["This field may not be blank."] });
      back.status = "label_sent";
      back.return_courier = text(kit.body.courier);
      back.return_awb = text(kit.body.awb);
      break;
    case "receive":
      if (!can("receive")) return refusal();
      back.status = "received";
      back.received_at = now;
      break;
    case "inspect":
      if (!can("inspect")) return refusal();
      back.status = text(kit.body.outcome) === "damaged" ? "damaged" : "restocked";
      back.inspected_at = now;
      break;
    case "photos":
      if (back.photos >= 5) return kit.invalid({ photo: ["Five photographs at most."] });
      back.photos += 1;
      break;
    default:
      return kit.notFound();
  }
  back.modified = now;
  kit.record(`order.return_${move}`, { target_type: "shop.order", target_label: back.order });
  return kit.json(200, view());
}

function quoteRoute(kit: OrdersKit, id: string | undefined, move: string | undefined): Response {
  if (!id) {
    const status = kit.url.searchParams.get("status") ?? "";
    return kit.paginate(
      kit.orders.quotes
        .filter((quote) => !status || quote.status === status)
        .map(({ items, note, waiting, ...row }) => (void items, void note, void waiting, row)),
      20,
    );
  }
  const quote = kit.orders.quotes.find((row) => String(row.id) === id);
  if (!quote) return kit.notFound();
  if (kit.method === "GET" && !move) return kit.json(200, quote);
  if (kit.method === "GET" && move === "quotation")
    return quote.has_quotation
      ? pdf(`quotation-${quote.number}`)
      : kit.json(404, { detail: "No quotation PDF yet.", code: "not_found" });
  if (move !== "convert") return kit.notFound();
  if (quote.order) return refuse400(kit, `Quotation ${quote.number} became order ${quote.order} already.`);
  const address = (kit.body.address ?? {}) as Body;
  const missing = ["name", "phone", "line1", "city", "district", "state", "pin"].filter((name) => !text(address[name]));
  if (missing.length)
    return kit.invalid({ address: Object.fromEntries(missing.map((name) => [name, ["This field is required."]])) });
  const number = `EL-2026-${String(kit.nextId()).padStart(6, "0")}`;
  const row = {
    action: "order.staff_discount",
    label: "Make a staff order",
    target_type: "shop.order",
    target_id: "",
    target_label: `Staff order: ${quote.copies} copies`,
    payload: { quote: quote.id, lines: quote.items },
    amount: quote.discount_percent,
    reason: text(kit.body.reason) || "A school's quotation accepted.",
    checker: "staff.approve_discount",
  };
  const limit = kit.limit("discount_percent");
  if (limit !== null && Number(quote.discount_percent) > limit) {
    const answer = kit.waiting({ ...row, rule: `${quote.discount_percent}% off is beyond the limit of ${limit}%.` });
    return answer;
  }
  quote.order = number;
  quote.status = "ordered";
  return kit.json(201, kit.executed(row, { order: number, total: "0.00", link: kit.body.send_link === true }));
}

function preview(kit: OrdersKit): Response {
  const asked = Array.isArray(kit.body.lines) ? (kit.body.lines as Body[]) : [];
  if (!asked.length) return kit.invalid({ lines: ["This list may not be empty."] });
  const priced = asked.map((row) => {
    const product = kit.orders.products.find((each) => each.slug === text(row.product));
    return { product, quantity: Math.max(1, Number(row.quantity) || 1) };
  });
  const unknown = priced.filter((row) => !row.product).map((_, index) => text(asked[index].product));
  if (unknown.length) return kit.invalid({ lines: [`Not on sale: ${unknown.join(", ")}.`] });
  const lines = priced.map(({ product, quantity }) => ({
    product: product!.slug,
    title: product!.title,
    unit_price: product!.price,
    quantity,
    line_total: money(toPaise(product!.price) * quantity),
    available: product!.available,
  }));
  const subtotal = lines.reduce((sum, line) => sum + toPaise(line.line_total), 0);
  const discount = Math.min(subtotal, toPaise(kit.body.discount ?? 0) || 0);
  const shipping =
    kit.body.shipping === null || kit.body.shipping === undefined || kit.body.shipping === ""
      ? 4000
      : toPaise(kit.body.shipping);
  const total = subtotal - discount + shipping;
  const percent = subtotal ? Math.round((discount * 10000) / subtotal) / 100 : 100;
  const limit = kit.limit("discount_percent");
  const approval =
    total === 0
      ? "A ₹0 order gives the books away: a second person approves it."
      : limit !== null && percent > limit
        ? `${percent.toFixed(2)}% off is beyond the limit of ${limit}%.`
        : null;
  const problems = lines
    .filter((line) => line.available < line.quantity)
    .map((line) =>
      line.available
        ? `Only ${line.available} copies of ${line.title} left.`
        : `${line.title} is out of stock. Please remove it.`,
    );
  return kit.json(200, {
    lines,
    subtotal: money(subtotal),
    offers: "0.00",
    discount: money(discount),
    percent: percent.toFixed(2),
    shipping: money(shipping),
    total: money(total),
    limit: limit === null ? null : limit.toFixed(2),
    approval,
    problems,
  });
}

export async function staffOrderAnswer(kit: OrdersKit): Promise<Response> {
  const body = kit.body;
  const fields: Record<string, unknown> = {};
  if (!text(body.email).includes("@")) fields.email = ["Enter a valid email address."];
  if (!text(body.reason)) fields.reason = ["This field may not be blank."];
  const address = (body.address ?? {}) as Body;
  const missing = ["name", "phone", "line1", "city", "district", "state", "pin"].filter((name) => !text(address[name]));
  if (missing.length) fields.address = Object.fromEntries(missing.map((name) => [name, ["This field is required."]]));
  if (Object.keys(fields).length) return kit.invalid(fields);
  const answer = preview({ ...kit, body: { ...body, state: address.state } });
  if (answer.status !== 200) return answer;
  const priced = (await answer.json()) as {
    total: string;
    percent: string;
    approval: string | null;
    problems: string[];
    lines: Body[];
  };
  if (priced.problems.length) return kit.invalid({ lines: priced.problems });
  const copies = priced.lines.reduce((sum, line) => sum + Number(line.quantity), 0);
  const row = {
    action: "order.staff_discount",
    label: "Make a staff order",
    target_type: "shop.order",
    target_id: "",
    target_label: `Staff order: ${copies} copies, ₹${priced.total}`,
    payload: {
      lines: body.lines,
      discount: text(body.discount) || "0",
      total: priced.total,
      percent: priced.percent,
      customer: "(encrypted)",
    },
    amount: text(body.discount) || "0",
    reason: text(body.reason),
    checker: "staff.approve_discount",
  };
  if (priced.approval) return kit.waiting({ ...row, rule: priced.approval });
  const id = kit.nextId();
  const number = `EL-2026-${String(id).padStart(6, "0")}`;
  const created = order(() => new Date().toISOString(), {
    id,
    number,
    status: "pending",
    customer: {
      id: null,
      name: text(address.name),
      email: `${text(body.email).slice(0, 2)}•••@${text(body.email).split("@")[1] ?? ""}`,
      phone: "••••••" + text(address.phone).slice(-4),
      is_minor: false,
    },
    hours: 0,
    placed_at: null,
    specs: priced.lines.map(
      (line) => [String(line.title), "", Number(line.unit_price), Number(line.quantity)] as LineSpec,
    ),
    staff_order: true,
    created_by: "You",
  });
  created.status_label = STATUS_LABELS.pending;
  kit.orders.orders.unshift(created);
  kit.record("order.staff_discount.executed", {
    target_type: "shop.order",
    target_id: String(id),
    target_label: number,
  });
  return kit.json(201, kit.executed(row, { order: number, total: created.total, link: body.send_link === true }));
}

/** The orders area: every path of shop/staff_orders.py (the permission was checked by handler.ts). */
export async function ordersRoute(kit: OrdersKit): Promise<Response> {
  const [, a, b, c] = kit.parts;
  const { method } = kit;
  if (!a) {
    if (method === "GET") return listOrders(kit);
    if (method === "POST") return staffOrderAnswer(kit);
    return kit.notFound();
  }
  if (a === "preview" && method === "POST") return preview(kit);
  if (a === "products" && method === "GET") {
    const q = (kit.url.searchParams.get("q") ?? "").trim().toLowerCase();
    if (q.length < 2) return kit.json(200, []);
    return kit.json(
      200,
      kit.orders.products.filter((product) => product.title.toLowerCase().includes(q) || product.isbn.includes(q)),
    );
  }
  if (a === "packing" && method === "GET") {
    const rows = kit.orders.orders
      .filter((order) => order.livemode && tabbed(order, "to_pack"))
      .sort((x, y) => Date.parse(x.placed_at ?? x.created) - Date.parse(y.placed_at ?? y.created))
      .map((order) => ({
        number: order.number,
        placed_at: order.placed_at ?? order.created,
        payment_method: order.payment_method,
        is_cod: order.is_cod,
        total: order.total,
        risk_bucket: order.risk_bucket,
        tags: order.tags,
        destination: `${order.address.city}, ${order.address.district}, ${order.address.pin}`,
        weight_g: order.lines.reduce((sum, line) => sum + 250 * line.quantity, 150),
        pick: order.lines.map((line) => ({ title: line.title, isbn: line.isbn, quantity: line.quantity })),
      }));
    return kit.paginate(rows, 50);
  }
  if (a === "pick-list" && method === "POST") {
    const asked = Array.isArray(kit.body.orders) ? kit.body.orders.map(String) : [];
    const missing = asked.filter((number) => !kit.orders.orders.some((order) => order.number === number));
    if (!asked.length) return kit.invalid({ orders: ["This list may not be empty."] });
    if (missing.length)
      return kit.invalid({ orders: [`No such order (or not one you may see): ${missing.join(", ")}.`] });
    kit.record("order.pick_list_printed", { details: { orders: asked.length } });
    return pdf("pick-list");
  }
  if (a === "returns") return returnRoute(kit, b, c);
  if (a === "quotes") return quoteRoute(kit, b, c);
  if (a === "refunds") {
    const refund = kit.orders.orders
      .flatMap((order) => order.refunds.map((row) => ({ order, row: row as Refund })))
      .find((each) => String(each.row.id) === b);
    if (!refund) return kit.notFound();
    if (c === "payee") {
      if (!text(kit.body.reason)) return kit.invalid({ reason: ["Say why: it is kept in the audit log."] });
      if (refund.row.method !== "bank")
        return refuse400(kit, `Refund #${refund.row.id} goes back the way it was paid: there is no account to show.`);
      kit.record("sensitive_read", {
        target_type: "shop.order",
        target_label: refund.order.number,
        reason: text(kit.body.reason),
        details: { what: "refund payee" },
      });
      return kit.json(200, { upi: "kabir.ahmed@okicici" });
    }
    if (c === "mark-paid") {
      if (!text(kit.body.utr)) return kit.invalid({ utr: ["This field may not be blank."] });
      if (refund.row.status !== "pending" || refund.row.method !== "bank")
        return refuse400(kit, `Refund #${refund.row.id} is marked paid already.`);
      refund.row.status = "processed";
      refund.row.utr = text(kit.body.utr);
      refund.row.processed_at = new Date().toISOString();
      refund.row.credit_note = `CN/2026-27/${String(refund.row.id).padStart(5, "0")}`;
      kit.record("refund.paid", { target_type: "shop.order", target_label: refund.order.number });
      return kit.json(200, refund.row);
    }
    return kit.notFound();
  }

  const found = kit.orders.orders.find((order) => order.number === decodeURIComponent(a) || String(order.id) === a);
  if (!found) return kit.notFound();
  if (method === "GET") {
    if (!b) {
      if (found.customer.is_minor)
        kit.record("sensitive_read", {
          target_type: "shop.order",
          target_id: String(found.id),
          target_label: found.number,
          details: { what: "order", child: true },
        });
      return kit.json(200, detailOf(found, kit.can));
    }
    if (b === "documents" || b === "invoice" || b === "credit-notes") return pdf(`${found.number}-${c ?? b}`);
    return kit.notFound();
  }
  if (method !== "POST") return kit.notFound();
  return orderMove(kit, found, b === "invoice" ? `invoice/${c}` : (b ?? ""));
}

/** POST jobs/ for an orders kind: its params checked as shop/order_jobs.py checks them, then a job (handler.ts runs
 *  it a third at a time on each look, as its other jobs). */
export function ordersJob(kit: OrdersKit, kind: string, params: Body): Response {
  const targets = Array.isArray(params.targets) ? params.targets.map(String) : [];
  if (kind === "orders_export") {
    if (params.filters && typeof params.filters === "object" && "q" in (params.filters as Body))
      return kit.invalid({ params: { filters: { q: ["Not a filter of the export (a search is the list's)."] } } });
    const rows = kit.orders.orders.filter((order) => order.livemode).map((order) => order.number ?? "");
    const job = kit.startJob("orders_export", { filters: params.filters ?? {} }, rows);
    return kit.json(202, job);
  }
  if (!targets.length) return kit.invalid({ params: { targets: ["The orders' numbers, as a list."] } });
  if (kind === "orders_cancel" && targets.length > 250)
    return kit.invalid({
      params: { targets: [`At most 250 orders are cancelled at once: you chose ${targets.length}.`] },
    });
  if (kind === "orders_cancel" && !text(params.reason))
    return kit.invalid({ params: { reason: ["Say why: the customers are told."] } });
  if (kind === "orders_print" && !["packing_slip", "label", "invoices"].includes(text(params.document)))
    return kit.invalid({ params: { document: ["One of packing_slip, label, invoices."] } });
  const job = kit.startJob(kind as S["Job"]["kind"], params, targets);
  if (kind === "orders_pack") {
    for (const number of targets) {
      const found = kit.orders.orders.find((order) => order.number === number);
      if (found && !found.held && tabbed(found, "to_pack")) {
        found.status = "packed";
        found.status_label = STATUS_LABELS.packed;
      }
    }
  }
  return kit.json(202, job);
}
