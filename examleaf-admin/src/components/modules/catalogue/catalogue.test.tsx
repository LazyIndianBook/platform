// The Catalogue module's parts: what a change sends (only the fields that differ: money as numbers, moments to the
// minute, lists as sets), a bundle's lines read from their box, a discount in words; the price form's note of what the
// website would print before anything is saved, its 202 (the change request waiting for FINANCE) and an unchanged
// price said without a call; a coupon's change sending its changed fields with the reason; a school's codes started as
// a job with the API's params; the import refusing to start without a file and reading its job's result; the move
// dialog's targets; the home's cards.
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  type CatalogueCoupon,
  type CatalogueOptions,
  type CatalogueProduct,
  getPriorPrice,
  type Job,
  startCatalogueJob,
  updateCatalogueProduct,
  updateCoupon,
  uploadProductImport,
} from "@/lib/api/staff";
import { copy } from "@/lib/copy";

import { movesFor } from "./categories";
import { codesParams, MakeCodes } from "./codes";
import { exportFilters, ImportOutcome, ImportPanel, importResult } from "./import";
import { newProductBody } from "./new-product";
import { PriceForm, priceBody, priorPriceNote } from "./price-form";
import { bundleLinesOf, changedOnly, discountText, same, shown, slugsOf } from "./shared";
import { cardsOf } from "./summary";
import { CouponForm, couponBody, offerBody } from "./terms";

vi.mock("@/lib/api/staff", async (original) => ({
  ...(await original<typeof import("@/lib/api/staff")>()),
  getPriorPrice: vi.fn(),
  updateCatalogueProduct: vi.fn(),
  updateCoupon: vi.fn(),
  startCatalogueJob: vi.fn(),
  uploadProductImport: vi.fn(),
  getJob: vi.fn(() => new Promise(() => {})), // JobProgress asks; the test is done before an answer matters
}));

beforeEach(() => {
  vi.mocked(getPriorPrice).mockReset();
  vi.mocked(updateCatalogueProduct).mockReset();
  vi.mocked(updateCoupon).mockReset();
  vi.mocked(startCatalogueJob).mockReset();
  vi.mocked(uploadProductImport).mockReset();
  window.sessionStorage.clear();
});

const form = (fields: Record<string, string | string[]>) => {
  const data = new FormData();
  for (const [name, value] of Object.entries(fields))
    for (const each of Array.isArray(value) ? value : [value]) data.append(name, each);
  return data;
};

const OPTIONS: CatalogueOptions = {
  kinds: [{ value: "sample-papers", label: "Sample Papers" }],
  packaging: [{ value: "flyer", label: "a flyer" }],
  tax_treatments: [],
  subjects: [],
  books: [],
  product_types: [],
  categories: [
    { value: "class-12", label: "Class 12" },
    { value: "science", label: "Science" },
  ],
  collections: [],
  hsn_codes: null,
  states: [],
};

describe("what a change sends", () => {
  it("reads money as numbers, moments to the minute, lists as sets and nothing as nothing", () => {
    expect(same("10.00", "10")).toBe(true);
    expect(same("2026-10-10T08:35:12.345Z", "2026-10-10T14:05:00+05:30")).toBe(true); // the box keeps minutes
    expect(same("2026-10-10T08:35:00Z", "2026-10-10T14:06:00+05:30")).toBe(false);
    expect(same(["b", "a"], ["a", "b"])).toBe(true);
    expect(same(null, "") && same(undefined, null)).toBe(true);
    expect(same({ language: "English" }, { language: "English" })).toBe(true);
    expect(same({ language: "English" }, { language: "" })).toBe(false);
    expect(
      changedOnly({ value: "10.00", stackable: true, note: "" }, { value: "15", stackable: true, note: "" }),
    ).toEqual({
      value: "15",
    });
  });

  it("reads slugs, a bundle's lines and versions' values as typed and shown", () => {
    expect(slugsOf("physics-2027\nChemistry-2027, physics-2027 ")).toEqual(["physics-2027", "chemistry-2027"]);
    expect(bundleLinesOf("physics-2027, 2\nchemistry-2027\n\nbiology-2027 3")).toEqual({
      lines: [
        { product: "physics-2027", quantity: 2 },
        { product: "chemistry-2027", quantity: 1 },
        { product: "biology-2027", quantity: 3 },
      ],
      problem: null,
    });
    expect(bundleLinesOf("physics-2027, two").problem).toBe(copy.catalogue.bundleLineProblem(1));
    expect(shown(null)).toBe("—");
    expect(shown(["a", "b"])).toBe("a, b");
    expect(shown(true)).toBe(copy.common.yes);
    expect(discountText("percent", "12.50")).toBe("12.5% off");
    expect(discountText("fixed", "50.00")).toBe("₹50 off");
  });

  it("builds a coupon's, an offer's and a new product's body from their forms", () => {
    const coupon = couponBody(
      form({
        code: "board50",
        kind: "fixed",
        value: "50",
        valid_from: "2026-10-10T09:00",
        include_products: "physics-2027\nchemistry-2027",
        include_categories: ["class-12"],
        stackable: "on",
        is_active: "on",
      }),
      true,
    );
    expect(coupon).toMatchObject({
      code: "BOARD50",
      kind: "fixed",
      min_order: "0",
      valid_from: "2026-10-10T09:00:00+05:30",
      valid_until: null,
      max_uses: null,
      include_products: ["physics-2027", "chemistry-2027"],
      include_categories: ["class-12"],
      exclude_categories: [],
      first_order_only: false,
      stackable: true,
    });
    const offer = offerBody(form({ name: "Board offer", scope: "categories", categories: ["science"], value: "10" }));
    expect(offer).toMatchObject({
      scope: "categories",
      categories: ["science"],
      show_countdown: false,
      min_quantity: 0,
    });
    const course = newProductBody(form({ title: "Pass", slug: "pass", kind: "digital", mrp: "499", hsn: "999293" }));
    expect(course).toEqual({
      title: "Pass",
      slug: "pass",
      kind: "digital",
      mrp: "499",
      is_active: false,
      hsn: "999293",
    });
    const book = newProductBody(
      form({
        title: "P",
        slug: "p",
        kind: "sample-papers",
        mrp: "349",
        weight_grams: "320",
        packaging: "flyer",
        length_cm: "",
      }),
    );
    expect(book).toMatchObject({ weight_grams: 320, packaging: "flyer" });
    expect("length_cm" in book).toBe(false);
    expect(exportFilters(form({ kind: "bundle", published: "", q: " " }))).toEqual({ kind: "bundle" });
  });
});

const PRODUCT = {
  slug: "physics-sample-papers-2027",
  prices: {
    mrp: "349.00",
    price: "299.00",
    saving_percent: 14,
    prior_price: null,
    prior_price_applies: true,
    prior_price_from: "2027-01-01",
  },
} as Pick<CatalogueProduct, "slug" | "prices">;

describe("a product's prices", () => {
  it("says what the website would print, in each case", () => {
    const answer = { price: "249.00", lowest_in_30_days: "279.00", window_from: "", applies_from: "2027-01-01" };
    expect(priorPriceNote({ ...answer, prior_price: "279.00", applies: true })).toBe(copy.catalogue.priorShown("₹279"));
    expect(priorPriceNote({ ...answer, prior_price: null, applies: true })).toBe(copy.catalogue.priorNone("₹279"));
    expect(priorPriceNote({ ...answer, prior_price: "279.00", applies: false })).toBe(
      copy.catalogue.priorLater("1 Jan 2027", "₹279"),
    );
    expect(priceBody(PRODUCT, form({ mrp: "349", price: "249", reason: "Board offer" }))).toEqual({
      price: "249",
      reason: "Board offer",
    });
  });

  it("previews the prior price, then a change beyond the limit answers with the change request waiting", async () => {
    const user = userEvent.setup();
    vi.mocked(getPriorPrice).mockResolvedValue({
      price: "199.00",
      lowest_in_30_days: "279.00",
      prior_price: "279.00",
      window_from: "2026-09-10T00:00:00+05:30",
      applies: true,
      applies_from: "2027-01-01",
    });
    vi.mocked(updateCatalogueProduct).mockResolvedValueOnce({
      price_change: { id: 851, status: "pending", checker: "staff.approve_discount" },
      slug: PRODUCT.slug,
    } as never);
    render(<PriceForm product={PRODUCT} />);
    await user.clear(screen.getByLabelText(copy.catalogue.fields.price));
    await user.type(screen.getByLabelText(copy.catalogue.fields.price), "199");
    expect(await screen.findByText(copy.catalogue.priorShown("₹279"))).toBeInTheDocument();
    expect(getPriorPrice).toHaveBeenLastCalledWith(PRODUCT.slug, "199", expect.any(AbortSignal));
    await user.type(screen.getByLabelText(copy.common.reason), "The board-exam offer");
    const bar = screen.getByRole("region", { name: copy.common.unsaved });
    await user.click(within(bar).getByRole("button", { name: copy.catalogue.savePrices }));
    expect(updateCatalogueProduct).toHaveBeenCalledWith(PRODUCT.slug, { price: "199", reason: "The board-exam offer" });
    expect(await screen.findByText(copy.approval.title)).toBeInTheDocument();
    expect(screen.getByText("staff.approve_discount")).toBeInTheDocument();
  });

  it("says the prices are unchanged without sending anything", async () => {
    const user = userEvent.setup();
    render(<PriceForm product={PRODUCT} />);
    await user.type(screen.getByLabelText(copy.common.reason), "No change");
    const bar = screen.getByRole("region", { name: copy.common.unsaved });
    await user.click(within(bar).getByRole("button", { name: copy.catalogue.savePrices }));
    expect(await screen.findByText(copy.catalogue.pricesUnchanged)).toBeInTheDocument();
    expect(updateCatalogueProduct).not.toHaveBeenCalled();
  });
});

const COUPON = {
  id: 401,
  code: "WELCOME10",
  kind: "percent",
  value: "10.00",
  min_order: "0.00",
  valid_from: "2026-09-10T08:35:12.345Z",
  valid_until: null,
  max_uses: null,
  max_uses_per_customer: 1,
  is_active: true,
  description: "10% off a first order.",
  note: "",
  include_products: [],
  include_categories: [],
  exclude_products: [],
  exclude_categories: [],
  first_order_only: true,
  stackable: true,
  single_use: false,
  state: "live",
  uses: 12,
  codes: { made: 0, used: 0, batches: [] },
  waiting: [],
  created: "2026-09-10T08:35:12.345Z",
  modified: "2026-09-10T08:35:12.345Z",
} as CatalogueCoupon;

describe("a coupon's change", () => {
  it("sends only what changed, with the reason", async () => {
    const user = userEvent.setup();
    vi.mocked(updateCoupon).mockResolvedValueOnce({ id: 900, status: "executed" } as never);
    render(<CouponForm coupon={COUPON} options={OPTIONS} />);
    await user.clear(screen.getByLabelText(copy.catalogue.fields.value));
    await user.type(screen.getByLabelText(copy.catalogue.fields.value), "15");
    await user.type(screen.getByLabelText(copy.common.reason), "The board season");
    const bar = screen.getByRole("region", { name: copy.common.unsaved });
    await user.click(within(bar).getByRole("button", { name: copy.catalogue.saveCoupon }));
    expect(updateCoupon).toHaveBeenCalledWith("WELCOME10", { value: "15", reason: "The board season" });
  });
});

describe("a school's codes", () => {
  it("starts the job with the API's params, its prefix in capitals, and follows it", async () => {
    const user = userEvent.setup();
    expect(codesParams("CCHS2027", form({ count: "300", prefix: "cchs", note: "Cotton Collegiate" }))).toEqual({
      coupon: "CCHS2027",
      count: 300,
      prefix: "CCHS",
      note: "Cotton Collegiate",
    });
    const job = { id: 77, kind: "coupon_codes", state: "running", done: 0, total: 300, errors: [] } as unknown as Job;
    vi.mocked(startCatalogueJob).mockResolvedValueOnce(job);
    render(<MakeCodes coupon="CCHS2027" />);
    await user.type(screen.getByLabelText(copy.catalogue.fields.count), "300");
    await user.type(screen.getByLabelText(copy.catalogue.fields.prefix), "cchs");
    await user.type(screen.getByLabelText(copy.catalogue.fields.school), "Cotton Collegiate");
    await user.click(screen.getByRole("button", { name: copy.catalogue.makeCodes }));
    expect(startCatalogueJob).toHaveBeenCalledWith("coupon_codes", {
      coupon: "CCHS2027",
      count: 300,
      prefix: "CCHS",
      note: "Cotton Collegiate",
    });
    expect(await screen.findByText(copy.jobs.progress(0, 300))).toBeInTheDocument();
  });
});

describe("the import", () => {
  it("asks for a file before anything is sent", async () => {
    const user = userEvent.setup();
    render(<ImportPanel />);
    await user.click(screen.getByRole("button", { name: copy.catalogue.runDryRun }));
    expect((await screen.findAllByText(copy.catalogue.chooseFile)).length).toBeGreaterThan(0);
    expect(uploadProductImport).not.toHaveBeenCalled();
  });

  it("reads a job's counts and rows, whatever else it holds", () => {
    expect(importResult({ result: null }).counts.created).toBe(0);
    const job = {
      dry_run: true,
      result: {
        counts: { created: 1, updated: 2, unchanged: 3, errors: 1, prices_waiting: 1 },
        rows: [{ line: 2, slug: "physics-2027", outcome: "updated", fields: ["price", "title"], price: "waits" }],
      },
    };
    render(<ImportOutcome job={job} />);
    expect(screen.getByText(copy.catalogue.importCounts.prices_waiting).nextSibling).toHaveTextContent("1");
    expect(screen.getByRole("cell", { name: "physics-2027" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: copy.catalogue.priceWays.waits })).toBeInTheDocument();
  });
});

describe("the shelves and the home", () => {
  it("never offers a shelf, or one under it, as where it moves", () => {
    const tree = [
      { id: 1, slug: "books", name: "Books", depth: 1, parent: null, products: 0 },
      { id: 2, slug: "class-12", name: "Class 12", depth: 2, parent: "books", products: 0 },
      { id: 3, slug: "science", name: "Science", depth: 3, parent: "class-12", products: 0 },
      { id: 4, slug: "courses", name: "Courses", depth: 1, parent: null, products: 0 },
    ];
    expect(movesFor(tree, "class-12").map((shelf) => shelf.slug)).toEqual(["books", "courses"]);
    expect(movesFor(tree, "courses").map((shelf) => shelf.slug)).toEqual(["books", "class-12", "science"]);
  });

  it("draws the back-in-stock card only for whoever may read the requests", () => {
    const summary = {
      products: 5,
      incomplete: 2,
      tax_problems: 1,
      low_stock: 1,
      out_of_stock: 1,
      low_stock_line: 5,
      stock_alerts: null,
      approvals: 1,
      prior_price_applies: false,
      prior_price_from: "2027-01-01",
    };
    expect(cardsOf(summary).map((card) => card.key)).toEqual(["incomplete", "tax", "out", "low", "approvals"]);
    expect(cardsOf({ ...summary, stock_alerts: 4 }).map((card) => card.key)).toContain("alerts");
    expect(cardsOf(summary)[0].href).toBe("/catalogue/products/?incomplete=true");
  });
});
