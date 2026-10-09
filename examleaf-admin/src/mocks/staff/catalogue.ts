// THE CATALOGUE MODULE'S MOCK, FOR DEVELOPMENT AND TESTS ONLY (STAFF_API_MOCK=1 under `next dev`): its fixtures
// (products complete, missing their weight, with GST that disagrees with the master, low and out of stock, a bundle, a
// course, one with a price waiting for approval; coupons live, scheduled, ended, switched off and single-use with
// codes used and not; offers with a countdown, scheduled and ended; rates for Assam, the North East and every other
// state; a shelf tree; collections; back-in-stock requests) and the answers of shop/staff_catalogue.py's paths
// (/api/v1/staff/catalogue/…) with the backend's rules kept: each part's permission (the first lacking is refused),
// the maker's discount limit (beyond it the change request waits: 202), the courier's data, the dark-pattern phrases
// and the countdown's real end, the copies a page read, the codes' and the import's jobs. handler.ts routes the
// "catalogue" area here and lends this module its tools (CatalogueKit).
import type { Schemas } from "@/lib/api/staff";

type Mutable<T> = { -readonly [K in keyof T]: T[K] };
type S = { [K in keyof Schemas]: Mutable<Schemas[K]> };
type Body = Record<string, unknown>;
type Product = S["CatalogueProduct"];
type Version = S["CatalogueVersion"];

export type CatalogueWorld = {
  products: Product[];
  history: Record<string, Version[]>;
  coupons: S["CatalogueCoupon"][];
  codes: Record<string, S["CatalogueCode"][]>;
  offers: S["CatalogueOffer"][];
  rates: S["CatalogueShippingRate"][];
  categories: S["CatalogueCategory"][];
  collections: S["CatalogueCollection"][];
  alerts: S["CatalogueAlertRow"][];
  /** Files uploaded for an import: token → its rows' slugs. */
  uploads: Record<string, string[]>;
  /** The first answer to each Idempotency-Key. */
  keys: Record<string, { status: number; body: unknown }>;
};

type JobOptions = {
  result?: Record<string, unknown>;
  dryRun?: boolean;
  /** Above the starter's limit: the job waits for an approver (job.run). */
  over?: { total: number; limit: number; what: string };
};

/** What handler.ts lends this module: the request, the person and the mock's ways of answering. */
export type CatalogueKit = {
  url: URL;
  method: string;
  parts: string[];
  body: Body;
  request: Request;
  world: CatalogueWorld;
  me: number;
  can: (permission: string) => boolean;
  limit: (name: string) => number | null;
  nextId: () => number;
  json: (status: number, body: unknown) => Response;
  notFound: () => Response;
  invalid: (fields: Record<string, unknown>) => Response;
  record: (action: string, extra?: Record<string, unknown>) => void;
  /** A change request that waits for its approver: the request itself (its 202 is the caller's to answer). */
  waiting: (row: Body) => S["ChangeRequest"];
  executed: (row: Body, result: unknown) => S["ChangeRequest"];
  paginate: <T>(rows: T[], size?: number) => Response;
  startJob: (kind: S["Job"]["kind"], params: unknown, rows: string[], options?: JobOptions) => S["Job"];
};

const text = (value: unknown) => (typeof value === "string" ? value.trim() : "");
const money = (value: number) => value.toFixed(2);
const GOODS = new Set(["sample-papers", "solutions"]);
const LOW = 5; // SHOP_LOW_STOCK
const PRIOR_FROM = "2027-01-01"; // SHOP_PRIOR_PRICE_FROM
const PRICE_FIELDS = new Set(["mrp", "price"]);
const TAX_FIELDS = new Set(["hsn", "tax_treatment", "tax_note", "tax_note_date"]);
const PAGE_FIELDS = new Set(
  ["title", "slug", "kind", "is_active", "subject", "book", "isbn", "pages", "description", "product_type"].concat([
    "attributes",
    "categories",
    "related",
    "weight_grams",
    "length_cm",
    "width_cm",
    "height_cm",
    "packaging",
    "seo_title",
    "seo_description",
  ]),
);
// SHOP_DARK_PATTERN_PHRASES' default (shop/copy_rules.py): the phrase and the pattern it reads as
const PHRASES: [string, string][] = [
  ["only fools", "confirm shaming"],
  ["you will regret", "confirm shaming"],
  ["do not miss", "false urgency"],
  ["last chance", "false urgency"],
  ["hurry", "false urgency"],
  ["limited time", "false urgency"],
];
const DATE = /\b(\d{1,2}\s+[a-z]+|[a-z]+\s+\d{1,2})\b|\d{4}-\d{2}-\d{2}/i;

/** The dark-pattern phrase a text holds, in the API's words; null when none. */
function darkPattern(value: string): string | null {
  const words = ` ${value.toLowerCase().replace(/[’']/g, "'").replace(/don't/g, "do not").replace(/'ll/g, " will")} `;
  for (const [phrase, pattern] of PHRASES) {
    if (!new RegExp(`\\b${phrase}\\b`).test(words)) continue;
    if (phrase === "limited time" && DATE.test(value)) continue;
    return `“${phrase}” reads as ${pattern}, a dark pattern the CCPA's 2023 guidelines name: say what is offered and the day it ends.`;
  }
  return null;
}

const discountOff = (mrp: number, price: number) => (mrp > 0 ? Math.round(((mrp - price) * 10000) / mrp) / 100 : 0);

// ---- Fixtures ----

function product(
  at: (hours: number) => string,
  spec: Partial<Product> & Pick<Product, "id" | "slug" | "title">,
): Product {
  const mrp = Number(spec.prices?.mrp ?? "349.00");
  const price = Number(spec.prices?.price ?? "299.00");
  return {
    kind: "sample-papers",
    is_active: true,
    subject: { id: 12, label: "Physics, ASSEB Class 12" },
    book: null,
    isbn: "",
    pages: 240,
    description: "Thirty papers with worked solutions, in the board's pattern.",
    product_type: { id: 1, name: "Printed book" },
    attributes: [
      { code: "language", name: "Language", kind: "choice", choices: ["English", "Assamese"], value: "English" },
    ],
    categories: [{ slug: "class-12", name: "Class 12" }],
    collections: [],
    related: [],
    old_slugs: [],
    web_url: `https://examleaf.in/shop/${spec.slug}/`,
    hsn: "4901",
    hsn_code: "4901",
    gst_rate: "0.00",
    tax_treatment: "split",
    tax_note: "",
    tax_note_date: null,
    tax: {
      today: {
        rate: "0.00",
        taxability: "exempt",
        effective_from: "2017-07-01",
        notification: "2/2017-Central Tax (Rate)",
      },
      next_change: null,
      problem: "",
    },
    weight_grams: 320,
    length_cm: null,
    width_cm: null,
    height_cm: null,
    packaging: "flyer",
    courier_problem: "",
    stock_info: {
      stock: 40,
      available: 40,
      state: "in_stock",
      low_stock: LOW,
      reserved: 2,
      awaiting_payment: 1,
      alerts: 0,
      last_alert: null,
    },
    cover: null,
    images: [],
    bundle_items: [],
    seo_title: "",
    seo_description: "",
    barcode: false,
    waiting: [],
    created: at(24 * 120),
    modified: at(24 * 3),
    ...spec,
    prices: {
      mrp: money(mrp),
      price: money(price),
      saving_percent: Math.floor(discountOff(mrp, price)),
      prior_price: null,
      prior_price_applies: false,
      prior_price_from: PRIOR_FROM,
      ...spec.prices,
    },
  } as Product;
}

const version = (
  id: number,
  at: string,
  by: [number | null, string],
  reason: string,
  changes: [string, unknown, unknown][],
  type: Version["type"] = "~",
): Version => ({
  id,
  at,
  by: by[0],
  by_name: by[1],
  reason,
  type,
  changes: changes.map(([field, before, after]) => ({ field, before, after })),
});

export function catalogueWorld(at: (hours: number) => string, me: number): CatalogueWorld {
  const editor: [number, string] = [9004, "Anita Baruah"];
  const finance: [number, string] = [9002, "Rahul Saikia"];
  const physics = product(at, {
    id: 301,
    slug: "physics-sample-papers-2027",
    title: "Physics Sample Papers 2027",
    isbn: "9789390000013",
    barcode: true,
    prices: { mrp: "349.00", price: "299.00" } as Product["prices"],
    images: [{ id: 3101, src: PICTURE, width: 400, height: 600, alt: "A page of paper 4", position: 1 }],
    cover: { src: PICTURE, width: 400, height: 600 },
    collections: [{ slug: "board-2027-picks", name: "Board 2027 picks" }],
  });
  const chemistry = product(at, {
    id: 302,
    slug: "chemistry-sample-papers-2027",
    title: "Chemistry Sample Papers 2027",
    subject: { id: 13, label: "Chemistry, ASSEB Class 12" },
    weight_grams: 0,
    courier_problem: "No weight: weigh one copy, in grams.",
    stock_info: {
      stock: 3,
      available: 3,
      state: "low",
      low_stock: LOW,
      reserved: 1,
      awaiting_payment: 0,
      alerts: 0,
      last_alert: null,
    },
  });
  const biology = product(at, {
    id: 303,
    slug: "biology-solutions-2027",
    title: "Biology Solutions 2027",
    kind: "solutions",
    is_active: false,
    subject: { id: 14, label: "Biology, ASSEB Class 12" },
    hsn: null,
    hsn_code: "49011",
    tax: { today: null, next_change: null, problem: "Not on the HSN and SAC master: choose its code." },
    stock_info: {
      stock: 0,
      available: 0,
      state: "out",
      low_stock: LOW,
      reserved: 0,
      awaiting_payment: 0,
      alerts: 4,
      last_alert: at(5),
    },
  });
  const set = product(at, {
    id: 304,
    slug: "class-12-science-set",
    title: "Class 12 Science Set",
    kind: "bundle",
    prices: { mrp: "698.00", price: "599.00" } as Product["prices"],
    weight_grams: 0,
    bundle_items: [
      { product: physics.slug, title: physics.title, kind: "sample-papers", quantity: 1, stock: 40, weight_grams: 320 },
      {
        product: chemistry.slug,
        title: chemistry.title,
        kind: "sample-papers",
        quantity: 1,
        stock: 3,
        weight_grams: 0,
      },
    ],
    courier_problem: "No weight: weigh the bundle, or each of its books.",
    stock_info: {
      stock: 0,
      available: 3,
      state: "low",
      low_stock: LOW,
      reserved: 0,
      awaiting_payment: 0,
      alerts: 0,
      last_alert: null,
    },
  });
  const course = product(at, {
    id: 305,
    slug: "physics-revision-pass",
    title: "Physics Revision Pass",
    kind: "digital",
    prices: { mrp: "499.00", price: "499.00" } as Product["prices"],
    hsn: "999293",
    hsn_code: "999293",
    gst_rate: "18.00",
    tax: {
      today: {
        rate: "18.00",
        taxability: "taxable",
        effective_from: "2017-07-01",
        notification: "11/2017-Central Tax (Rate)",
      },
      next_change: null,
      problem: "",
    },
    weight_grams: 0,
    packaging: "",
    attributes: [],
    stock_info: {
      stock: 0,
      available: 1,
      state: "none",
      low_stock: LOW,
      reserved: 0,
      awaiting_payment: 0,
      alerts: 0,
      last_alert: null,
    },
  });
  const maths = product(at, {
    id: 306,
    slug: "maths-sample-papers-2027",
    title: "Mathematics Sample Papers 2027",
    subject: { id: 15, label: "Mathematics, ASSEB Class 12" },
    prices: { mrp: "399.00", price: "349.00" } as Product["prices"],
    waiting: [
      {
        id: 851,
        action: "product.price",
        status: "pending",
        rule: "45% off the MRP is above the maker's limit of 20%.",
        payload: { product: "maths-sample-papers-2027", price: "219.00", mrp_from: "399.00", price_from: "349.00" },
        created: at(6),
      },
    ],
  });
  const products = [physics, chemistry, biology, set, course, maths];
  const history: Record<string, Version[]> = {
    [`product:${physics.slug}`]: [
      version(4003, at(24 * 3), editor, "", [["title", "Physics Sample Papers", physics.title]]),
      version(4002, at(24 * 20), finance, "Change request #812", [["price", "279.00", "299.00"]]),
      version(4001, at(24 * 120), [null, ""], "When its history began", [], "+"),
    ],
  };
  for (const other of products.slice(1))
    history[`product:${other.slug}`] = [
      version(4100 + other.id, at(24 * 120), [null, ""], "When its history began", [], "+"),
    ];

  const coupon = (
    spec: Partial<S["CatalogueCoupon"]> & Pick<S["CatalogueCoupon"], "id" | "code">,
  ): S["CatalogueCoupon"] => ({
    kind: "percent",
    value: "10.00",
    min_order: "0.00",
    valid_from: at(24 * 30),
    valid_until: null,
    max_uses: null,
    max_uses_per_customer: 1,
    is_active: true,
    description: "",
    note: "",
    include_products: [],
    include_categories: [],
    exclude_products: [],
    exclude_categories: [],
    first_order_only: false,
    stackable: true,
    single_use: false,
    state: "live",
    uses: 0,
    codes: { made: 0, used: 0, batches: [] },
    waiting: [],
    created: at(24 * 30),
    modified: at(24 * 30),
    ...spec,
  });
  const coupons = [
    coupon({ id: 401, code: "WELCOME10", description: "10% off a first order.", first_order_only: true, uses: 12 }),
    coupon({
      id: 402,
      code: "BOARD50",
      kind: "fixed",
      value: "50.00",
      min_order: "499.00",
      valid_from: at(-24 * 10),
      valid_until: at(-24 * 40),
      state: "scheduled",
      include_categories: ["class-12"],
      stackable: false,
    }),
    coupon({ id: 403, code: "DIWALI2025", value: "15.00", valid_until: at(24 * 300), state: "ended", uses: 88 }),
    coupon({ id: 404, code: "OLDCODE", is_active: false, state: "inactive" }),
    coupon({
      id: 405,
      code: "CCHS2027",
      value: "12.00",
      single_use: true,
      note: "Cotton Collegiate HS, Class 12",
      max_uses_per_customer: null,
      uses: 1,
      codes: {
        made: 3,
        used: 1,
        batches: [{ job: 702, note: "Cotton Collegiate", made: 3, used: 1, created: at(48) }],
      },
    }),
  ];
  const codes = {
    CCHS2027: [
      {
        code: "CCHS-7KQ2MZRX",
        note: "Cotton Collegiate",
        job: 702,
        created: at(48),
        used: true,
        used_at: at(20),
        order: "EL-2026-000131",
      },
      {
        code: "CCHS-B4WNT8PD",
        note: "Cotton Collegiate",
        job: 702,
        created: at(48),
        used: false,
        used_at: null,
        order: null,
      },
      {
        code: "CCHS-H9XCV3KE",
        note: "Cotton Collegiate",
        job: 702,
        created: at(48),
        used: false,
        used_at: null,
        order: null,
      },
    ],
  };
  history["coupon:WELCOME10"] = [version(4201, at(24 * 30), [me, "You"], "Change request #640", [], "+")];

  const offer = (
    spec: Partial<S["CatalogueOffer"]> & Pick<S["CatalogueOffer"], "id" | "name">,
  ): S["CatalogueOffer"] => ({
    banner: "",
    kind: "percent",
    value: "10.00",
    scope: "cart",
    products: [],
    categories: [],
    collections: [],
    min_quantity: 0,
    min_value: "0.00",
    valid_from: at(24 * 5),
    valid_until: null,
    max_uses: null,
    max_uses_per_customer: null,
    combinable: true,
    is_active: true,
    show_countdown: false,
    state: "live",
    uses: 0,
    waiting: [],
    created: at(24 * 5),
    modified: at(24 * 5),
    ...spec,
  });
  const offers = [
    offer({
      id: 501,
      name: "Board 2027 offer",
      valid_until: at(-24 * 20),
      show_countdown: true,
      uses: 34,
      banner: "10% off every book until 30 October.",
    }),
    offer({
      id: 502,
      name: "Science set offer",
      scope: "categories",
      categories: ["science"],
      valid_from: at(-24 * 7),
      state: "scheduled",
      combinable: false,
    }),
    offer({ id: 503, name: "Summer offer", valid_until: at(24 * 90), state: "ended", uses: 51 }),
  ];
  history["offer:501"] = [version(4301, at(24 * 5), [me, "You"], "Change request #702", [], "+")];

  const rates: S["CatalogueShippingRate"][] = [
    { id: 61, name: "Assam", states: ["AS"], fee: "40.00", free_above: "499.00", is_active: true },
    {
      id: 62,
      name: "North East",
      states: ["AR", "ML", "MN", "MZ", "NL", "SK", "TR"],
      fee: "60.00",
      free_above: "799.00",
      is_active: true,
    },
    { id: 63, name: "Rest of India", states: [], fee: "80.00", free_above: "999.00", is_active: true },
    { id: 64, name: "Old flat rate", states: ["WB"], fee: "50.00", free_above: null, is_active: false },
  ];
  history["rate:61"] = [version(4401, at(24 * 40), finance, "The courier's new tariff", [["fee", "35.00", "40.00"]])];

  const categories: S["CatalogueCategory"][] = [
    { id: 71, slug: "books", name: "Books", description: "", depth: 1, parent: null, products: 0 },
    { id: 72, slug: "class-12", name: "Class 12", description: "", depth: 2, parent: "books", products: 5 },
    { id: 73, slug: "science", name: "Science", description: "", depth: 3, parent: "class-12", products: 3 },
    { id: 74, slug: "commerce", name: "Commerce", description: "", depth: 3, parent: "class-12", products: 0 },
    { id: 75, slug: "courses", name: "Courses", description: "", depth: 1, parent: null, products: 1 },
  ];
  const collections: S["CatalogueCollection"][] = [
    {
      id: 81,
      slug: "board-2027-picks",
      name: "Board 2027 picks",
      description: "",
      is_active: true,
      position: 1,
      products: [physics.slug, chemistry.slug],
      created: at(24 * 60),
      modified: at(24 * 6),
    },
    {
      id: 82,
      slug: "new-this-year",
      name: "New this year",
      description: "",
      is_active: false,
      position: 2,
      products: [],
      created: at(24 * 2),
      modified: at(24 * 2),
    },
  ];
  const alerts = [{ product: biology.slug, title: biology.title, requests: 4, last_asked: at(5), available: 0 }];
  return { products, history, coupons, codes, offers, rates, categories, collections, alerts, uploads: {}, keys: {} };
}

/** A small picture the mock serves for every upload (an SVG page, 2:3). */
const PICTURE =
  "data:image/svg+xml;utf8," +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="600" viewBox="0 0 400 600"><rect width="400" height="600" fill="#0b2a5b"/><text x="200" y="300" fill="#ffffff" font-size="40" text-anchor="middle">ExamLeaf</text></svg>',
  );

export const CATALOGUE_OPTIONS = (hsn: boolean): S["CatalogueOptions"] => ({
  kinds: [
    { value: "sample-papers", label: "Sample Papers" },
    { value: "solutions", label: "Solutions" },
    { value: "bundle", label: "Bundle" },
    { value: "digital", label: "Digital (in the app)" },
  ],
  packaging: [
    { value: "flyer", label: "a flyer (the courier's bag, of the standard size)" },
    { value: "box", label: "a box (its length, width and height)" },
  ],
  tax_treatments: [
    { value: "split", label: "split: each component a line of its own, the price shared by their MRPs" },
    { value: "composite", label: "composite: one line at the principal supply's rate" },
    { value: "mixed", label: "mixed: one line at the highest rate" },
  ],
  subjects: [
    { value: "12", label: "Physics, ASSEB Class 12" },
    { value: "13", label: "Chemistry, ASSEB Class 12" },
    { value: "14", label: "Biology, ASSEB Class 12" },
    { value: "15", label: "Mathematics, ASSEB Class 12" },
  ],
  books: [{ value: "physics-2027", label: "Physics 2027" }],
  product_types: [{ value: "1", label: "Printed book" }],
  categories: [
    { value: "books", label: "Books" },
    { value: "class-12", label: "  Class 12" },
    { value: "science", label: "    Science" },
    { value: "commerce", label: "    Commerce" },
    { value: "courses", label: "Courses" },
  ],
  collections: [
    { value: "board-2027-picks", label: "Board 2027 picks" },
    { value: "new-this-year", label: "New this year" },
  ],
  hsn_codes: hsn
    ? [
        { value: "4820", label: "4820 Exercise books, graph books, laboratory notebooks and notebooks" },
        { value: "4901", label: "4901 Printed books, brochures, leaflets and similar printed matter" },
        { value: "999293", label: "999293 Commercial training and coaching services" },
      ]
    : null,
  states: [
    { value: "AR", label: "Arunachal Pradesh" },
    { value: "AS", label: "Assam" },
    { value: "ML", label: "Meghalaya" },
    { value: "MN", label: "Manipur" },
    { value: "MZ", label: "Mizoram" },
    { value: "NL", label: "Nagaland" },
    { value: "SK", label: "Sikkim" },
    { value: "TR", label: "Tripura" },
    { value: "WB", label: "West Bengal" },
  ],
});

// ---- Permissions (each path's, as shop/staff_catalogue.py names them) ----

/** Which permission a catalogue path needs; for a product's change the first part the person lacks, as the API. */
export function cataloguePermission(
  method: string,
  parts: string[],
  body: Body,
  can: (perm: string) => boolean,
): string {
  const [, area, key, sub, child] = parts;
  const get = method === "GET";
  switch (area) {
    case "products": {
      if (get) return "shop.view_product";
      if (!key) return "shop.add_product";
      if (sub === "stock") return "staff.set_stock";
      if (sub === "bundle") return "shop.change_product";
      if (sub === "pictures")
        return child
          ? method === "DELETE"
            ? "shop.delete_productimage"
            : "shop.change_productimage"
          : "shop.add_productimage";
      const keys = Object.keys(body);
      const needed = [
        ...(keys.some((name) => !PRICE_FIELDS.has(name) && !TAX_FIELDS.has(name) && name !== "reason") || !keys.length
          ? ["shop.change_product"]
          : []),
        ...(keys.some((name) => PRICE_FIELDS.has(name)) ? ["staff.change_price"] : []),
        ...(keys.some((name) => TAX_FIELDS.has(name)) ? ["staff.change_product_tax"] : []),
      ];
      return needed.find((perm) => !can(perm)) ?? needed[0] ?? "shop.change_product";
    }
    case "stock":
      return "shop.view_product";
    case "stock-alerts":
      return "shop.view_stockalert";
    case "coupons":
      if (sub === "codes") return "shop.view_couponcode";
      return get ? "shop.view_coupon" : key ? "shop.change_coupon" : "shop.add_coupon";
    case "offers":
      return get ? "shop.view_offer" : key ? "shop.change_offer" : "shop.add_offer";
    case "shipping-rates":
      return get ? "shop.view_shippingrate" : key ? "shop.change_shippingrate" : "shop.add_shippingrate";
    case "categories":
      return get ? "shop.view_category" : key ? "shop.change_category" : "shop.add_category";
    case "collections":
      return get ? "shop.view_collection" : key ? "shop.change_collection" : "shop.add_collection";
    case "import":
      return "shop.import_product";
    default:
      return "shop.view_product"; // summary/, options/
  }
}

/** The permission a catalogue job needs (staff.jobs.permission), or null for another kind. */
export function catalogueJobPermission(kind: unknown): string | null {
  return (
    {
      coupon_codes: "shop.add_couponcode",
      product_import: "shop.import_product",
      product_export: "shop.export_product",
    }[String(kind)] ?? null
  );
}

// ---- The answers ----

const find = (kit: CatalogueKit, key: string | undefined) =>
  kit.world.products.find((row) => row.slug === key || String(row.id) === key);

const rowOf = (row: Product): S["CatalogueProductRow"] => ({
  id: row.id,
  slug: row.slug,
  title: row.title,
  kind: row.kind,
  is_active: row.is_active,
  mrp: row.prices.mrp,
  price: row.prices.price,
  saving_percent: row.prices.saving_percent,
  stock: row.stock_info.stock,
  available: row.stock_info.available,
  stock_state: row.stock_info.state as S["CatalogueProductRow"]["stock_state"],
  hsn_code: row.hsn_code,
  gst_rate: row.gst_rate,
  tax_problem: row.tax.problem,
  courier_problem: row.courier_problem,
  cover: row.cover,
  categories: row.categories.map((shelf) => shelf.slug),
  modified: row.modified,
});

function courierProblem(row: Product): string {
  if (row.kind === "digital") return "";
  if (row.kind === "bundle") {
    const books = row.bundle_items.filter((item) => item.kind !== "digital");
    if (!books.length) return "";
    if (!row.weight_grams && books.some((item) => !item.weight_grams))
      return "No weight: weigh the bundle, or each of its books.";
  } else if (!row.weight_grams) return "No weight: weigh one copy, in grams.";
  const sized = row.length_cm && row.width_cm && row.height_cm;
  if (row.packaging === "box" && !sized) return "A box needs its length, width and height.";
  if (!row.packaging && !sized) return "Neither a packaging kind nor dimensions: a flyer, or the box's size.";
  return "";
}

function stockState(row: Product) {
  const info = row.stock_info;
  if (row.kind === "digital") return Object.assign(info, { state: "none", available: 1 });
  if (row.kind === "bundle")
    info.available = Math.min(...row.bundle_items.map((item) => Math.floor(item.stock / item.quantity)), 999);
  else info.available = info.stock;
  info.state = info.available <= 0 ? "out" : info.available < LOW ? "low" : "in_stock";
  return info;
}

function versionOf(
  kit: CatalogueKit,
  key: string,
  reason: string,
  changes: [string, unknown, unknown][],
  type: Version["type"] = "~",
) {
  (kit.world.history[key] ??= []).unshift(
    version(kit.nextId(), new Date().toISOString(), [kit.me, "You"], reason, changes, type),
  );
}

/** The answer an Idempotency-Key already had, else what `answer` gives (kept for the key). */
function once(kit: CatalogueKit, answer: () => { status: number; body: unknown }): Response {
  const key = kit.request.headers.get("Idempotency-Key") ?? "";
  const kept = key ? kit.world.keys[key] : undefined;
  if (kept) return kit.json(kept.status, kept.body);
  const made = answer();
  if (key && made.status < 400) kit.world.keys[key] = made;
  return kit.json(made.status, made.body);
}

/** A price change through product.price: within the maker's limit at once, beyond it waiting. */
function priceChange(kit: CatalogueKit, row: Product, mrp: number, price: number, reason: string) {
  const off = discountOff(mrp, price);
  const limit = kit.limit("discount_percent");
  const payload = {
    product: row.slug,
    mrp: money(mrp),
    price: money(price),
    mrp_from: row.prices.mrp,
    price_from: row.prices.price,
  };
  const change = {
    action: "product.price",
    label: "Change a price",
    target_type: "shop.product",
    target_id: String(row.id),
    target_label: row.title,
    payload,
    amount: money(price),
    reason,
    checker: "staff.approve_discount",
  };
  if (limit !== null && off > limit) {
    const waiting = kit.waiting({ ...change, rule: `${off}% off the MRP is above the maker's limit of ${limit}%.` });
    row.waiting.unshift({
      id: waiting.id,
      action: "product.price",
      status: "pending",
      rule: waiting.rule ?? "",
      payload,
      created: waiting.created,
    });
    return waiting;
  }
  const before = { ...row.prices };
  row.prices.mrp = money(mrp);
  row.prices.price = money(price);
  row.prices.saving_percent = Math.floor(off);
  const done = kit.executed(
    { ...change, rule: "Within the maker's limits: no approval needed." },
    { price: money(price) },
  );
  versionOf(kit, `product:${row.slug}`, `Change request #${done.id}`, [
    ...(before.mrp !== row.prices.mrp ? [["mrp", before.mrp, row.prices.mrp] as [string, unknown, unknown]] : []),
    ...(before.price !== row.prices.price
      ? [["price", before.price, row.prices.price] as [string, unknown, unknown]]
      : []),
  ]);
  return done;
}

const PRICE = /^\d{1,6}(\.\d{1,2})?$/;

function productRoute(kit: CatalogueKit): Response {
  const { method, parts, body, url } = kit;
  const [, , key, sub, child] = parts;
  const query = (name: string) => url.searchParams.get(name) ?? "";
  if (!key && method === "GET") {
    const q = query("q").toLowerCase();
    const rows = kit.world.products.filter(
      (row) =>
        (!q || row.title.toLowerCase().includes(q) || row.slug.includes(q) || row.isbn.includes(q)) &&
        (!query("kind") || row.kind === query("kind")) &&
        (!query("published") || String(row.is_active) === query("published")) &&
        (!query("stock") || (GOODS.has(row.kind) && row.stock_info.state === query("stock"))) &&
        (!query("tax_problem") || Boolean(row.tax.problem) === (query("tax_problem") === "true")) &&
        (!query("incomplete") || Boolean(row.courier_problem) === (query("incomplete") === "true")),
    );
    return kit.paginate(rows.map(rowOf), 50);
  }
  if (!key && method === "POST") return createProduct(kit);
  const row = find(kit, key);
  if (!row) return kit.notFound();
  if (method === "GET" && !sub) return kit.json(200, row);
  if (method === "GET" && sub === "history") return kit.paginate(kit.world.history[`product:${row.slug}`] ?? [], 20);
  if (method === "GET" && sub === "prior-price") {
    const price = query("price");
    if (!PRICE.test(price) || Number(price) <= 0) return kit.invalid({ price: ["A price in rupees, above 0."] });
    const since = Date.now() - 30 * 86_400_000;
    const recent = (kit.world.history[`product:${row.slug}`] ?? [])
      .filter((entry) => Date.parse(entry.at) >= since)
      .flatMap((entry) =>
        entry.changes.filter((change) => change.field === "price").map((change) => Number(change.before)),
      );
    const lowest = Math.min(Number(row.prices.price), ...recent);
    return kit.json(200, {
      price: money(Number(price)),
      lowest_in_30_days: money(lowest),
      prior_price: Number(price) < lowest ? money(lowest) : null,
      window_from: new Date(since).toISOString(),
      applies: new Date().toISOString().slice(0, 10) >= PRIOR_FROM,
      applies_from: PRIOR_FROM,
    });
  }
  if (method === "GET" && sub === "barcode.svg") {
    if (!row.barcode) return kit.json(404, { detail: "No valid ISBN-13: no barcode.", code: "not_found" });
    return new Response(
      `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 113 76" width="37.29mm"><title>EAN-13 barcode ${row.isbn}</title><rect width="113" height="76" fill="#fff"/>${Array.from({ length: 30 }, (_, index) => `<rect x="${11 + index * 3}" y="0" width="${index % 3 ? 1 : 2}" height="60"/>`).join("")}<text x="56" y="73" font-size="9" text-anchor="middle">${row.isbn}</text></svg>`,
      { headers: { "Content-Type": "image/svg+xml", "Cache-Control": "no-store" } },
    );
  }
  if (method === "PATCH" && !sub) return changeProduct(kit, row);
  if (method === "PUT" && sub === "bundle") {
    if (row.kind !== "bundle") return kit.invalid({ non_field_errors: ["Only a bundle holds books."] });
    const lines = Array.isArray(body.lines) ? (body.lines as Body[]) : [];
    if (!lines.length || lines.length > 50)
      return kit.invalid({ lines: ["1 to 50 lines: a product's slug and its copies."] });
    const items: Product["bundle_items"] = [];
    for (const line of lines) {
      const book = find(kit, text(line.product));
      const quantity = Number(line.quantity ?? 1);
      if (!book) return kit.invalid({ lines: [`Not found: ${text(line.product)}.`] });
      if (book.kind === "bundle") return kit.invalid({ lines: ["A bundle holds books and courses, not bundles."] });
      if (!Number.isInteger(quantity) || quantity < 1 || quantity > 99)
        return kit.invalid({ lines: [`${book.slug}: 1 to 99 copies.`] });
      if (items.some((item) => item.product === book.slug))
        return kit.invalid({ lines: [`${book.slug} twice: once, with its copies.`] });
      items.push({
        product: book.slug,
        title: book.title,
        kind: book.kind,
        quantity,
        stock: book.stock_info.stock,
        weight_grams: book.weight_grams,
      });
    }
    row.bundle_items = items;
    row.courier_problem = courierProblem(row);
    stockState(row);
    kit.record("catalogue.bundle_changed", {
      target_type: "shop.product",
      target_id: String(row.id),
      target_label: row.title,
    });
    return kit.json(200, row);
  }
  if (method === "POST" && sub === "stock") {
    if (!GOODS.has(row.kind))
      return kit.invalid({ non_field_errors: ["A bundle's copies are its books', and a course has none."] });
    const stock = Number(body.stock);
    if (!Number.isInteger(stock) || stock < 0 || stock > 1_000_000)
      return kit.invalid({ stock: ["A whole number of copies, 0 or more."] });
    if (!text(body.reason)) return kit.invalid({ reason: ["Say why: the audit trail keeps it."] });
    if (body.expected !== undefined && Number(body.expected) !== row.stock_info.stock)
      return kit.invalid({
        expected: [`Orders changed the copies meanwhile: ${row.stock_info.stock} now. Read them again, then set them.`],
      });
    row.stock_info.stock = stock;
    stockState(row);
    kit.record("catalogue.stock_set", {
      target_type: "shop.product",
      target_id: String(row.id),
      target_label: row.title,
      reason: text(body.reason),
    });
    return kit.json(200, row);
  }
  if (sub === "pictures") {
    if (method === "POST" && !child) {
      const file = body.image;
      if (!(file instanceof File) || !file.size) return kit.invalid({ image: ["No file was submitted."] });
      if (file.size > 2 * 1024 * 1024) return kit.invalid({ image: ["At most 2 MB: every phone loads it."] });
      if (!/\.(jpe?g|png|webp)$/i.test(file.name)) return kit.invalid({ image: ["A JPEG, PNG or WebP picture."] });
      const picture = {
        id: kit.nextId(),
        src: PICTURE,
        width: 400,
        height: 600,
        alt: text(body.alt),
        position: Number(body.position ?? 0) || 0,
      };
      if (body.as_cover === "true") row.cover = { src: PICTURE, width: 400, height: 600 };
      else row.images.push(picture);
      kit.record("catalogue.picture_added", {
        target_type: "shop.product",
        target_id: String(row.id),
        target_label: row.title,
      });
      return kit.json(201, row);
    }
    const picture = row.images.find((image) => String(image.id) === child);
    if (!picture) return kit.notFound();
    if (method === "PATCH") {
      if ("alt" in body) picture.alt = text(body.alt);
      if ("position" in body) picture.position = Number(body.position) || 0;
      return kit.json(200, row);
    }
    if (method === "DELETE") {
      row.images = row.images.filter((image) => image !== picture);
      kit.record("catalogue.picture_removed", {
        target_type: "shop.product",
        target_id: String(row.id),
        target_label: row.title,
      });
      return kit.json(200, row);
    }
  }
  return kit.notFound();
}

function physicalProblems(kind: string, values: Partial<Product>): Record<string, string[]> {
  if (kind === "digital") return {};
  const sizes = [values.length_cm, values.width_cm, values.height_cm];
  if (
    sizes.some((size) => size !== null && size !== undefined) &&
    sizes.some((size) => size === null || size === undefined)
  )
    return { length_cm: ["Give the length, width and height, or none of them."] };
  if (GOODS.has(kind) && !values.weight_grams) return { weight_grams: ["Above 0: weigh one copy, in grams."] };
  if (values.packaging === "box" && !sizes.every(Boolean))
    return { packaging: ["A box needs its length, width and height."] };
  if (!values.packaging && !sizes.every(Boolean))
    return { packaging: ["A packaging kind (a flyer) or the dimensions."] };
  return {};
}

function createProduct(kit: CatalogueKit): Response {
  const { body } = kit;
  const title = text(body.title);
  const slug = text(body.slug);
  const kind = text(body.kind);
  const mrp = text(body.mrp);
  const problems: Record<string, string[]> = {};
  if (!title) problems.title = ["This field is required."];
  if (!/^[-a-z0-9]+$/.test(slug)) problems.slug = ["Small letters, figures and hyphens."];
  else if (kit.world.products.some((row) => row.slug === slug)) problems.slug = ["Another product has this address."];
  if (!["sample-papers", "solutions", "bundle", "digital"].includes(kind)) problems.kind = ["Not a kind of product."];
  if (!PRICE.test(mrp) || Number(mrp) <= 0) problems.mrp = ["A price in rupees, above 0."];
  const price = text(body.price) || mrp;
  if (!PRICE.test(price) || Number(price) > Number(mrp)) problems.price = ["At most the MRP."];
  const physical = {
    weight_grams: Number(body.weight_grams ?? 0) || 0,
    packaging: (text(body.packaging) as Product["packaging"]) ?? "",
    length_cm: (body.length_cm as number | null) ?? null,
    width_cm: (body.width_cm as number | null) ?? null,
    height_cm: (body.height_cm as number | null) ?? null,
  };
  Object.assign(problems, physicalProblems(kind, physical));
  if (kind === "digital" && text(body.hsn) !== "999293")
    problems.hsn = ["A course is a service: choose its SAC code (999293)."];
  if (Object.keys(problems).length) return kit.invalid(problems);
  return once(kit, () => {
    const made = product((hours) => new Date(Date.now() - hours * 3_600_000).toISOString(), {
      id: kit.nextId(),
      slug,
      title,
      kind: kind as Product["kind"],
      is_active: body.is_active === true,
      subject: null,
      product_type: null,
      attributes: [],
      categories: [],
      description: "",
      pages: null,
      hsn: text(body.hsn) || "4901",
      hsn_code: text(body.hsn) || "4901",
      prices: { mrp: money(Number(mrp)), price: money(Number(mrp)) } as Product["prices"],
      ...physical,
      stock_info: {
        stock: 0,
        available: 0,
        state: "out",
        low_stock: LOW,
        reserved: 0,
        awaiting_payment: 0,
        alerts: 0,
        last_alert: null,
      },
      created: new Date().toISOString(),
      modified: new Date().toISOString(),
    });
    made.courier_problem = courierProblem(made);
    stockState(made);
    kit.world.products.unshift(made);
    versionOf(kit, `product:${slug}`, "", [], "+");
    kit.record("catalogue.product_created", {
      target_type: "shop.product",
      target_id: String(made.id),
      target_label: made.title,
    });
    const change =
      Number(price) < Number(mrp)
        ? priceChange(kit, made, Number(mrp), Number(price), text(body.reason) || "A new product's price")
        : null;
    return { status: 201, body: { product: made, price_change: change } };
  });
}

function changeProduct(kit: CatalogueKit, row: Product): Response {
  const { body } = kit;
  const unknown = Object.keys(body).filter(
    (name) => !PAGE_FIELDS.has(name) && !PRICE_FIELDS.has(name) && !TAX_FIELDS.has(name) && name !== "reason",
  );
  if (unknown.length)
    return kit.invalid(
      Object.fromEntries(
        unknown.map((name) => [
          name,
          [name === "stock" ? "Stock is set through stock/, with a reason." : "Not a field of a product."],
        ]),
      ),
    );
  const priceAsked = [...PRICE_FIELDS].some((name) => name in body);
  const mrp = "mrp" in body ? text(body.mrp) : row.prices.mrp;
  const price = "price" in body ? text(body.price) : row.prices.price;
  if (priceAsked) {
    if (!PRICE.test(mrp) || Number(mrp) <= 0) return kit.invalid({ mrp: ["A price in rupees, above 0."] });
    if (!PRICE.test(price) || Number(price) > Number(mrp)) return kit.invalid({ price: ["At most the MRP."] });
    if (!text(body.reason)) return kit.invalid({ reason: ["Say why the price changes: its approval reads it."] });
  }
  if (
    "slug" in body &&
    text(body.slug) !== row.slug &&
    kit.world.products.some((other) => other.slug === text(body.slug))
  )
    return kit.invalid({ slug: ["Another product has this address."] });
  const next = {
    ...row,
    ...Object.fromEntries(Object.entries(body).filter(([name]) => PAGE_FIELDS.has(name) || TAX_FIELDS.has(name))),
  };
  const physical = physicalProblems(String(next.kind), next as Partial<Product>);
  const touched = ["weight_grams", "length_cm", "width_cm", "height_cm", "packaging", "kind"].some(
    (name) => name in body,
  );
  if (touched && Object.keys(physical).length) return kit.invalid(physical);
  const changes: [string, unknown, unknown][] = [];
  for (const [name, value] of Object.entries(body)) {
    if (!PAGE_FIELDS.has(name) && !TAX_FIELDS.has(name)) continue;
    const before = (row as Record<string, unknown>)[name];
    if (name === "subject") {
      const id = value === null ? null : Number(value);
      row.subject = id === null ? null : { id, label: `Subject ${id}` };
      changes.push([name, before && (before as { id: number }).id, id]);
    } else if (name === "categories") {
      const slugs = Array.isArray(value) ? value.map(String) : [];
      row.categories = slugs.map((slug) => ({
        slug,
        name: kit.world.categories.find((shelf) => shelf.slug === slug)?.name ?? slug,
      }));
      changes.push([name, (before as { slug: string }[]).map((shelf) => shelf.slug), slugs]);
    } else if (name === "attributes") {
      for (const attribute of row.attributes) attribute.value = text((value as Body)[attribute.code]) || null;
    } else if (["book", "product_type"].includes(name)) {
      changes.push([name, before, value]);
    } else {
      (row as Record<string, unknown>)[name] = value;
      changes.push([name, before, value]);
    }
  }
  if ("slug" in body && text(body.slug) !== changes.find(([name]) => name === "slug")?.[1]) {
    const old = changes.find(([name]) => name === "slug")?.[1];
    if (old) {
      row.old_slugs.push(String(old));
      kit.world.history[`product:${row.slug}`] = kit.world.history[`product:${String(old)}`] ?? [];
    }
  }
  row.courier_problem = courierProblem(row);
  if ("hsn" in body) row.tax.problem = row.hsn ? "" : "Not on the HSN and SAC master: choose its code.";
  if (changes.length) {
    row.modified = new Date().toISOString();
    versionOf(kit, `product:${row.slug}`, text(body.reason), changes);
    kit.record("catalogue.product_changed", {
      target_type: "shop.product",
      target_id: String(row.id),
      target_label: row.title,
    });
  }
  if (!priceAsked || (Number(mrp) === Number(row.prices.mrp) && Number(price) === Number(row.prices.price)))
    return kit.json(200, row);
  return once(kit, () => {
    const change = priceChange(kit, row, Number(mrp), Number(price), text(body.reason));
    return change.status === "pending"
      ? { status: 202, body: { price_change: change, slug: row.slug } }
      : { status: 200, body: row };
  });
}

// coupons and offers: their terms through their approvals

const COUPON_FIELDS = ["code", "kind", "value", "min_order", "valid_from", "valid_until", "max_uses"].concat([
  "max_uses_per_customer",
  "is_active",
  "description",
  "note",
  "include_products",
  "include_categories",
  "exclude_products",
  "exclude_categories",
  "first_order_only",
  "stackable",
  "single_use",
]);
const OFFER_FIELDS = ["name", "banner", "kind", "value", "scope", "products", "categories", "collections"].concat([
  "min_quantity",
  "min_value",
  "valid_from",
  "valid_until",
  "max_uses",
  "max_uses_per_customer",
  "combinable",
  "is_active",
  "show_countdown",
]);

function termsProblems(fields: string[], body: Body, isNew: boolean, words: string[]): Record<string, string[]> {
  const problems: Record<string, string[]> = {};
  for (const name of Object.keys(body))
    if (name !== "reason" && !fields.includes(name)) problems[name] = ["Not a field of these terms."];
  if (!text(body.reason)) problems.reason = ["Say why: its approval reads it."];
  if (isNew && !PRICE.test(text(body.value))) problems.value = ["A number: per cent or rupees off."];
  if ("value" in body && body.kind !== "fixed" && Number(body.value) > 100) problems.value = ["At most 100% off."];
  for (const name of words) {
    const found = darkPattern(text(body[name]));
    if (found) problems[name] = [found];
  }
  if (
    body.valid_until &&
    body.valid_from &&
    Date.parse(String(body.valid_until)) <= Date.parse(String(body.valid_from))
  )
    problems.valid_until = ["After its start."];
  return problems;
}

/** How far a coupon's or an offer's discount goes, as a percentage of what it is taken from. */
const depth = (kind: unknown, value: unknown) => (kind === "fixed" ? 0 : Number(value) || 0);

function termsRoute(kit: CatalogueKit, what: "coupon" | "offer"): Response {
  const { method, parts, body, url } = kit;
  const [, , key, sub] = parts;
  const query = (name: string) => url.searchParams.get(name) ?? "";
  const rows = (what === "coupon" ? kit.world.coupons : kit.world.offers) as (
    S["CatalogueCoupon"] | S["CatalogueOffer"]
  )[];
  const fields = what === "coupon" ? COUPON_FIELDS : OFFER_FIELDS;
  const words = what === "coupon" ? ["description"] : ["name", "banner"];
  const label = (row: Body) => (what === "coupon" ? String(row.code) : String(row.name));
  if (!key && method === "GET") {
    const q = query("q").toLowerCase();
    return kit.paginate(
      rows.filter(
        (row) =>
          (!q ||
            label(row as Body)
              .toLowerCase()
              .includes(q)) &&
          (!query("state") || row.state === query("state")) &&
          (!query("kind") || row.kind === query("kind")) &&
          (!query("single_use") || String((row as S["CatalogueCoupon"]).single_use) === query("single_use")) &&
          (!query("scope") || (row as S["CatalogueOffer"]).scope === query("scope")) &&
          (!query("combinable") || String((row as S["CatalogueOffer"]).combinable) === query("combinable")),
      ),
      50,
    );
  }
  const limit = kit.limit("discount_percent");
  if (!key && method === "POST") {
    const problems = termsProblems(fields, body, true, words);
    if (what === "coupon") {
      const code = text(body.code).toUpperCase();
      if (!/^[A-Z0-9-]{3,30}$/.test(code)) problems.code = ["3 to 30 capitals, figures and hyphens."];
      else if (kit.world.coupons.some((row) => row.code === code)) problems.code = ["Another coupon has this code."];
    } else if (!text(body.name)) problems.name = ["This field is required."];
    if (what === "offer" && body.show_countdown === true && !body.valid_until)
      problems.show_countdown = ["A countdown needs a real end: give the day it ends."];
    if (Object.keys(problems).length) return kit.invalid(problems);
    const payload = Object.fromEntries(Object.entries(body).filter(([name]) => name !== "reason"));
    const change = {
      action: `${what}.create`,
      label: what === "coupon" ? "Make a coupon" : "Make an offer",
      target_type: `shop.${what}`,
      target_id: what === "coupon" ? text(body.code).toUpperCase() : "",
      target_label: what === "coupon" ? text(body.code).toUpperCase() : `New offer: ${text(body.name)}`,
      payload,
      amount: null,
      reason: text(body.reason),
      checker: "staff.approve_discount",
    };
    const off = depth(body.kind, body.value);
    return once(kit, () => {
      if (limit !== null && off > limit) {
        const waiting = kit.waiting({ ...change, rule: `${off}% off is above the maker's limit of ${limit}%.` });
        return { status: 202, body: waiting };
      }
      const id = kit.nextId();
      const created = new Date().toISOString();
      if (what === "coupon") {
        const code = text(body.code).toUpperCase();
        kit.world.coupons.unshift({
          ...(kit.world.coupons[0] ?? {}),
          ...(payload as object),
          id,
          code,
          state: "live",
          uses: 0,
          codes: { made: 0, used: 0, batches: [] },
          waiting: [],
          created,
          modified: created,
        } as S["CatalogueCoupon"]);
        versionOf(kit, `coupon:${code}`, change.reason, [], "+");
        return {
          status: 201,
          body: kit.executed({ ...change, rule: "Within the maker's limits: no approval needed." }, { coupon: code }),
        };
      }
      kit.world.offers.unshift({
        ...(kit.world.offers[0] ?? {}),
        ...(payload as object),
        id,
        state: "live",
        uses: 0,
        waiting: [],
        created,
        modified: created,
      } as S["CatalogueOffer"]);
      versionOf(kit, `offer:${id}`, change.reason, [], "+");
      return {
        status: 201,
        body: kit.executed(
          { ...change, rule: "Within the maker's limits: no approval needed." },
          { offer: id, name: text(body.name) },
        ),
      };
    });
  }
  const row = rows.find(
    (each) =>
      (what === "coupon" ? (each as S["CatalogueCoupon"]).code === String(key).toUpperCase() : false) ||
      String(each.id) === key,
  );
  if (!row) return kit.notFound();
  const historyKey = what === "coupon" ? `coupon:${(row as S["CatalogueCoupon"]).code}` : `offer:${row.id}`;
  if (method === "GET" && !sub) return kit.json(200, row);
  if (method === "GET" && sub === "history") return kit.paginate(kit.world.history[historyKey] ?? [], 20);
  if (method === "GET" && sub === "codes" && what === "coupon") {
    const code = (row as S["CatalogueCoupon"]).code;
    const used = query("used");
    return kit.paginate(
      (kit.world.codes[code] ?? []).filter((each) => !used || String(each.used) === used),
      50,
    );
  }
  if (method === "PATCH" && !sub) {
    if ("code" in body) return kit.invalid({ code: ["A coupon's code never changes: customers hold it."] });
    const problems = termsProblems(fields, body, false, words);
    const next = { ...row, ...body } as S["CatalogueOffer"];
    if (what === "offer" && next.show_countdown && !next.valid_until)
      problems.show_countdown = ["A countdown needs a real end: give the day it ends."];
    if (what === "offer" && (row as S["CatalogueOffer"]).show_countdown && row.valid_until && "valid_until" in body) {
      const later = !body.valid_until || Date.parse(String(body.valid_until)) > Date.parse(row.valid_until);
      if (later) problems.valid_until = ["Its countdown has been shown: its end may come sooner, never later."];
    }
    if (Object.keys(problems).length) return kit.invalid(problems);
    const changes = Object.fromEntries(
      Object.entries(body)
        .filter(([name]) => name !== "reason")
        .map(([name, value]) => [name, [(row as Record<string, unknown>)[name] ?? null, value]]),
    );
    const change = {
      action: `${what}.change`,
      label: what === "coupon" ? "Change a coupon" : "Change an offer",
      target_type: `shop.${what}`,
      target_id: String(row.id),
      target_label: label(row as Body),
      payload: { id: row.id, changes },
      amount: null,
      reason: text(body.reason),
      checker: "staff.approve_discount",
    };
    const deeper =
      depth(next.kind, next.value) > depth(row.kind, row.value) || (body.is_active === true && !row.is_active);
    const off = depth(next.kind, next.value);
    return once(kit, () => {
      if (deeper && limit !== null && off > limit) {
        const waiting = kit.waiting({ ...change, rule: `${off}% off is above the maker's limit of ${limit}%.` });
        row.waiting.unshift({
          id: waiting.id,
          action: change.action,
          status: "pending",
          rule: waiting.rule ?? "",
          payload: change.payload,
          created: waiting.created,
        });
        return { status: 202, body: waiting };
      }
      Object.assign(row, Object.fromEntries(Object.entries(body).filter(([name]) => name !== "reason")));
      row.modified = new Date().toISOString();
      const done = kit.executed(
        { ...change, rule: "Within the maker's limits: no approval needed." },
        { [what]: row.id },
      );
      versionOf(
        kit,
        historyKey,
        `Change request #${done.id}`,
        Object.entries(changes).map(([name, [before, after]]) => [name, before, after]),
      );
      return { status: 200, body: done };
    });
  }
  return kit.notFound();
}

function ratesRoute(kit: CatalogueKit): Response {
  const { method, parts, body } = kit;
  const [, , key, sub] = parts;
  if (!key && method === "GET") return kit.paginate(kit.world.rates, 50);
  const rate = key ? kit.world.rates.find((row) => String(row.id) === key) : undefined;
  if (key && !rate) return kit.notFound();
  if (rate && method === "GET" && !sub) return kit.json(200, rate);
  if (rate && method === "GET" && sub === "history")
    return kit.paginate(kit.world.history[`rate:${rate.id}`] ?? [], 20);
  if (method !== "POST" && method !== "PATCH") return kit.notFound();
  const next = { ...(rate ?? { name: "", states: [], fee: "", free_above: null, is_active: true }), ...body } as Body;
  const states = Array.isArray(next.states) ? (next.states as string[]) : [];
  const problems: Record<string, string[]> = {};
  if (!text(next.name)) problems.name = ["This field is required."];
  if (!PRICE.test(String(next.fee))) problems.fee = ["A fee in rupees, 0 or more."];
  if (next.free_above !== null && next.free_above !== undefined && !PRICE.test(String(next.free_above)))
    problems.free_above = ["A value in rupees, or nothing."];
  if (next.is_active !== false) {
    const others = kit.world.rates.filter((row) => row !== rate && row.is_active);
    const both = states.filter((state) => others.some((row) => (row.states as string[]).includes(state)));
    if (both.length) problems.states = [`In another active rate already: ${both.join(", ")}.`];
    if (!states.length && others.some((row) => !(row.states as string[]).length))
      problems.states = ["Another active rate covers every other state already."];
  }
  if (Object.keys(problems).length) return kit.invalid(problems);
  const changes = rate
    ? Object.entries(body)
        .filter(([name]) => name !== "reason")
        .map(([name, value]): [string, unknown, unknown] => [name, (rate as Body)[name], value])
    : [];
  const saved = rate ?? ({ id: kit.nextId() } as S["CatalogueShippingRate"]);
  Object.assign(saved, Object.fromEntries(Object.entries(next).filter(([name]) => name !== "reason")));
  if (!rate) kit.world.rates.push(saved);
  versionOf(kit, `rate:${saved.id}`, text(body.reason), changes, rate ? "~" : "+");
  kit.record(rate ? "catalogue.rate_changed" : "catalogue.rate_created", {
    target_type: "shop.shippingrate",
    target_id: String(saved.id),
    target_label: saved.name,
    reason: text(body.reason),
  });
  return kit.json(rate ? 200 : 201, saved);
}

function shelvesRoute(kit: CatalogueKit): Response {
  const { method, parts, body } = kit;
  const [, , key, sub] = parts;
  const tree = kit.world.categories;
  if (!key && method === "GET") return kit.json(200, tree);
  if (!key && method === "POST") {
    const slug = text(body.slug);
    if (!text(body.name)) return kit.invalid({ name: ["This field is required."] });
    if (!/^[-a-z0-9]+$/.test(slug)) return kit.invalid({ slug: ["Small letters, figures and hyphens."] });
    if (tree.some((shelf) => shelf.slug === slug)) return kit.invalid({ slug: ["Another shelf has this address."] });
    const parent = body.parent ? tree.find((shelf) => shelf.slug === body.parent) : null;
    if (body.parent && !parent) return kit.invalid({ parent: ["No such shelf."] });
    const shelf = {
      id: kit.nextId(),
      slug,
      name: text(body.name),
      description: text(body.description),
      depth: parent ? parent.depth + 1 : 1,
      parent: parent?.slug ?? null,
      products: 0,
    };
    const at = parent ? subtreeEnd(tree, tree.indexOf(parent)) : tree.length;
    tree.splice(at, 0, shelf);
    kit.record("catalogue.category_created", {
      target_type: "shop.category",
      target_id: String(shelf.id),
      target_label: shelf.name,
    });
    return kit.json(201, shelf);
  }
  const shelf = tree.find((each) => each.slug === key);
  if (!shelf) return kit.notFound();
  if (method === "GET" && !sub) return kit.json(200, shelf);
  if (method === "PATCH" && !sub) {
    const slug = "slug" in body ? text(body.slug) : shelf.slug;
    if (slug !== shelf.slug && tree.some((each) => each.slug === slug))
      return kit.invalid({ slug: ["Another shelf has this address."] });
    for (const child of tree) if (child.parent === shelf.slug) child.parent = slug;
    Object.assign(shelf, {
      name: text(body.name) || shelf.name,
      slug,
      description: "description" in body ? text(body.description) : shelf.description,
    });
    kit.record("catalogue.category_changed", {
      target_type: "shop.category",
      target_id: String(shelf.id),
      target_label: shelf.name,
    });
    return kit.json(200, shelf);
  }
  if (method === "POST" && sub === "move") {
    const position = text(body.position);
    if (!["first-child", "last-child", "left", "right"].includes(position))
      return kit.invalid({ position: ["One of first-child, last-child, left, right."] });
    const start = tree.indexOf(shelf);
    const moving = tree.slice(start, subtreeEnd(tree, start));
    const target = body.target ? tree.find((each) => each.slug === body.target) : null;
    if (body.target && !target) return kit.invalid({ target: ["No such shelf."] });
    if (target && moving.includes(target)) return kit.invalid({ target: ["A shelf never moves under itself."] });
    tree.splice(start, moving.length);
    const shift = (depth: number) => depth - shelf.depth;
    let at: number;
    let depth: number;
    let parent: string | null;
    if (!target) {
      at = position === "first-child" || position === "left" ? 0 : tree.length;
      depth = 1;
      parent = null;
    } else if (position === "first-child" || position === "last-child") {
      at = position === "first-child" ? tree.indexOf(target) + 1 : subtreeEnd(tree, tree.indexOf(target));
      depth = target.depth + 1;
      parent = target.slug;
    } else {
      at = position === "left" ? tree.indexOf(target) : subtreeEnd(tree, tree.indexOf(target));
      depth = target.depth;
      parent = target.parent;
    }
    const moved = moving.map((each) => ({ ...each, depth: depth + shift(each.depth) }));
    moved[0].parent = parent;
    tree.splice(at, 0, ...moved);
    for (const [index, each] of moved.entries()) Object.assign(moving[index], each);
    kit.world.categories = tree.map((each) => moved.find((one) => one.id === each.id) ?? each);
    kit.record("catalogue.category_moved", {
      target_type: "shop.category",
      target_id: String(shelf.id),
      target_label: shelf.name,
    });
    return kit.json(200, kit.world.categories);
  }
  return kit.notFound();
}

/** Where a shelf's subtree ends (the index after its last shelf). */
function subtreeEnd(tree: S["CatalogueCategory"][], index: number): number {
  let end = index + 1;
  while (end < tree.length && tree[end].depth > tree[index].depth) end += 1;
  return end;
}

function collectionsRoute(kit: CatalogueKit): Response {
  const { method, parts, body } = kit;
  const [, , key] = parts;
  const rows = kit.world.collections;
  if (!key && method === "GET")
    return kit.paginate(
      [...rows].sort((a, b) => (a.position ?? 0) - (b.position ?? 0)),
      50,
    );
  const found = key ? rows.find((row) => row.slug === key) : undefined;
  if (key && !found) return kit.notFound();
  if (found && method === "GET") return kit.json(200, found);
  if (method !== "POST" && method !== "PATCH") return kit.notFound();
  const slug = "slug" in body ? text(body.slug) : (found?.slug ?? "");
  if (!found && !text(body.name)) return kit.invalid({ name: ["This field is required."] });
  if (!/^[-a-z0-9]+$/.test(slug)) return kit.invalid({ slug: ["Small letters, figures and hyphens."] });
  if (rows.some((row) => row !== found && row.slug === slug))
    return kit.invalid({ slug: ["Another collection has this address."] });
  const products = Array.isArray(body.products) ? body.products.map(String) : (found?.products ?? []);
  const missing = products.filter((each) => !kit.world.products.some((row) => row.slug === each));
  if (missing.length) return kit.invalid({ products: [`Not found: ${missing.join(", ")}.`] });
  const now = new Date().toISOString();
  const saved =
    found ??
    ({
      id: kit.nextId(),
      slug,
      name: "",
      description: "",
      is_active: true,
      position: 0,
      products: [],
      created: now,
      modified: now,
    } as S["CatalogueCollection"]);
  Object.assign(saved, {
    slug,
    name: text(body.name) || saved.name,
    description: "description" in body ? text(body.description) : saved.description,
    is_active: "is_active" in body ? body.is_active === true : saved.is_active,
    position: "position" in body ? Number(body.position) || 0 : saved.position,
    products,
    modified: now,
  });
  if (!found) rows.push(saved);
  kit.record(found ? "catalogue.collection_changed" : "catalogue.collection_created", {
    target_type: "shop.collection",
    target_id: String(saved.id),
    target_label: saved.name,
  });
  return kit.json(found ? 200 : 201, saved);
}

function summaryOf(kit: CatalogueKit): S["CatalogueSummary"] {
  const onSale = kit.world.products.filter((row) => row.is_active);
  const books = kit.world.products.filter((row) => GOODS.has(row.kind));
  return {
    products: onSale.length,
    incomplete: kit.world.products.filter((row) => row.courier_problem).length,
    tax_problems: kit.world.products.filter((row) => row.tax.problem).length,
    low_stock: books.filter((row) => row.stock_info.state === "low").length,
    out_of_stock: books.filter((row) => row.stock_info.state === "out").length,
    low_stock_line: LOW,
    stock_alerts: kit.can("shop.view_stockalert") ? kit.world.alerts.reduce((sum, row) => sum + row.requests, 0) : null,
    approvals: [...kit.world.products, ...kit.world.coupons, ...kit.world.offers].reduce(
      (sum, row) => sum + row.waiting.length,
      0,
    ),
    prior_price_applies: new Date().toISOString().slice(0, 10) >= PRIOR_FROM,
    prior_price_from: PRIOR_FROM,
  };
}

function importRoute(kit: CatalogueKit): Promise<Response> | Response {
  const file = kit.body.file;
  if (!(file instanceof File) || !file.size) return kit.invalid({ file: ["Choose a CSV file."] });
  if (file.size > 2 * 1024 * 1024) return kit.invalid({ file: ["At most 2 MB: split the file."] });
  return file.text().then((content) => {
    const [header = "", ...lines] = content
      .replace(/^﻿/, "")
      .split(/\r?\n/)
      .filter((line) => line.trim());
    const names = header.split(",").map((name) => name.trim());
    if (!names.includes("slug"))
      return kit.invalid({ file: ["The first row names the columns, `slug` among them (the admin's export does)."] });
    const slugs = lines.map((line) => line.split(",")[names.indexOf("slug")]?.trim() ?? "");
    const token = Array.from({ length: 32 }, (_, index) => "0123456789abcdef"[(index * 7 + slugs.length) % 16]).join(
      "",
    );
    kit.world.uploads[token] = slugs;
    kit.record("catalogue.import_uploaded", { details: { rows: slugs.length } });
    return kit.json(202, importJob(kit, token, slugs, true, null));
  });
}

function importJob(
  kit: CatalogueKit,
  token: string,
  slugs: string[],
  dryRun: boolean,
  dryRunJob: number | null,
): S["Job"] {
  const known = new Set(kit.world.products.map((row) => row.slug));
  const counts = { created: 0, updated: 0, unchanged: 0, errors: 0, prices_waiting: 0 };
  const rows: Body[] = [];
  slugs.forEach((slug, index) => {
    if (!slug) {
      counts.errors += 1;
      return;
    }
    const outcome = known.has(slug) ? (index % 2 ? "unchanged" : "updated") : "created";
    counts[outcome as "created" | "updated" | "unchanged"] += 1;
    if (outcome !== "unchanged") rows.push({ line: index + 2, slug, outcome, fields: ["title"], price: null });
  });
  const params = dryRun
    ? { file: token, sha256: "0".repeat(64) }
    : { file: token, sha256: "0".repeat(64), dry_run_job: dryRunJob };
  return kit.startJob("product_import", params, slugs, { result: { counts, rows }, dryRun });
}

export async function catalogueRoute(kit: CatalogueKit): Promise<Response> {
  const area = kit.parts[1];
  if (area === "summary" && kit.method === "GET") return kit.json(200, summaryOf(kit));
  if (area === "options" && kit.method === "GET") return kit.json(200, CATALOGUE_OPTIONS(kit.can("shop.view_hsncode")));
  if (area === "products") return productRoute(kit);
  if (area === "stock" && kit.method === "GET") {
    const query = (name: string) => kit.url.searchParams.get(name) ?? "";
    const q = query("q").toLowerCase();
    const rows = kit.world.products
      .filter((row) => GOODS.has(row.kind))
      .filter(
        (row) =>
          (!q || row.title.toLowerCase().includes(q) || row.slug.includes(q)) &&
          (!query("state") || row.stock_info.state === query("state")) &&
          (!query("published") || String(row.is_active) === query("published")),
      )
      .sort((a, b) => a.stock_info.stock - b.stock_info.stock)
      .map((row) => ({
        id: row.id,
        slug: row.slug,
        title: row.title,
        kind: row.kind,
        is_active: row.is_active,
        stock: row.stock_info.stock,
        reserved: row.stock_info.reserved,
        awaiting_payment: row.stock_info.awaiting_payment,
        state: row.stock_info.state,
        alerts: row.stock_info.alerts,
      }));
    return kit.paginate(rows, 50);
  }
  if (area === "stock-alerts" && kit.method === "GET") return kit.paginate(kit.world.alerts, 50);
  if (area === "coupons") return termsRoute(kit, "coupon");
  if (area === "offers") return termsRoute(kit, "offer");
  if (area === "shipping-rates") return ratesRoute(kit);
  if (area === "categories") return shelvesRoute(kit);
  if (area === "collections") return collectionsRoute(kit);
  if (area === "import" && kit.method === "POST") return importRoute(kit);
  return kit.notFound();
}

/** POST jobs/ of a catalogue kind: its params checked as the API's, then the job (202). */
export function catalogueJob(kit: CatalogueKit, kind: string, params: Body): Response {
  if (kind === "coupon_codes") {
    const problems: Record<string, string[]> = {};
    const coupon = kit.world.coupons.find((row) => row.code === text(params.coupon).toUpperCase());
    if (!coupon) problems.coupon = ["No such coupon."];
    else if (!coupon.single_use)
      problems.coupon = ["Make it single-use first: its own code must not also work at the cart."];
    else if (coupon.state === "ended") problems.coupon = ["It has ended: codes of it would not work."];
    const count = params.count;
    if (typeof count !== "number" || !Number.isInteger(count) || count < 1 || count > 5000)
      problems.count = ["1 to 5,000 codes."];
    const prefix = text(params.prefix).toUpperCase();
    if (!/^[A-Z0-9]{2,10}$/.test(prefix)) problems.prefix = ["2 to 10 capitals and figures (the school's short name)."];
    const note = text(params.note);
    if (!note || note.length > 200) problems.note = ["The school's name (200 characters at most)."];
    if (Object.keys(problems).length) return kit.invalid({ params: problems });
    const total = count as number;
    const limit = kit.limit("bulk_rows");
    const over = limit !== null && total > limit ? { total, limit, what: "single-use codes" } : undefined;
    const letters = "ABCDEFGHJKMNPQRSTUVWXYZ23456789";
    const made = Array.from(
      { length: total },
      (_, index) =>
        `${prefix}-${Array.from({ length: 8 }, (__, at) => letters[(index * 13 + at * 7 + total) % letters.length]).join("")}`,
    );
    const job = kit.startJob("coupon_codes", { coupon: coupon!.code, count: total, prefix, note }, made, {
      result: { codes: total, coupon: coupon!.code },
      over,
    });
    if (!over) {
      const created = new Date().toISOString();
      (kit.world.codes[coupon!.code] ??= []).unshift(
        ...made.map((code) => ({ code, note, job: job.id, created, used: false, used_at: null, order: null })),
      );
      coupon!.codes.made += total;
      coupon!.codes.batches.unshift({ job: job.id, note, made: total, used: 0, created });
    }
    return kit.json(202, job);
  }
  if (kind === "product_import") {
    const token = text(params.file);
    if (!kit.world.uploads[token])
      return kit.invalid({ params: { file: ["Upload the file first (catalogue/import/)."] } });
    const dryRunJob = Number(params.dry_run_job);
    if (!Number.isInteger(dryRunJob) || dryRunJob <= 0)
      return kit.invalid({ params: { dry_run_job: ["The dry run's job, to apply it."] } });
    const job = importJob(kit, token, kit.world.uploads[token], false, dryRunJob);
    delete kit.world.uploads[token];
    return kit.json(202, job);
  }
  const filters = params.filters && typeof params.filters === "object" ? (params.filters as Body) : {};
  const known = ["q", "kind", "published", "stock", "tax_problem", "incomplete", "category", "collection"];
  const unknown = Object.keys(filters).filter((name) => !known.includes(name));
  if (unknown.length)
    return kit.invalid({ params: { filters: Object.fromEntries(unknown.map((name) => [name, ["Not a filter."]])) } });
  const rows = kit.world.products.map((row) => row.slug);
  const limit = kit.limit("export_rows");
  const over = limit !== null && rows.length > limit ? { total: rows.length, limit, what: "rows" } : undefined;
  return kit.json(202, kit.startJob("product_export", { filters }, rows, { result: { rows: rows.length }, over }));
}

/** A finished catalogue job's file: the school's codes, or the products as the admin's export. */
export function catalogueJobFile(kind: string, id: number, rows: string[]): Response | null {
  if (kind === "coupon_codes")
    return new Response(
      [
        "code,school,offer,minimum order,valid from,valid until,use",
        ...rows.map((code) => `${code},,,,,,one order`),
      ].join("\n") + "\n",
      {
        headers: {
          "Content-Type": "text/csv",
          "Content-Disposition": `attachment; filename="codes-${id}.csv"`,
          "Cache-Control": "no-store",
        },
      },
    );
  if (kind === "product_export")
    return new Response(["slug,title,kind", ...rows.map((slug) => `${slug},,`)].join("\n") + "\n", {
      headers: {
        "Content-Type": "text/csv",
        "Content-Disposition": `attachment; filename="products-${id}.csv"`,
        "Cache-Control": "no-store",
      },
    });
  return null;
}
