// The shop's logic and islands (package 8B): prices with MRP and saving, the checkout's stepper states, the cart's
// copies rule and its stepper (a step is sent at once, 0 asks first), an order's timeline and outcome, and
// Razorpay's window around the API's options (its answer to the server, failures in words, closing sends nothing).
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Price } from "@/components/ui/price";
import { Stepper } from "@/components/ui/stepper";
import { api } from "@/lib/api/client";

import { CartView } from "./cart-view";
import {
  addressLines,
  cancelledMessage,
  checkoutSteps,
  copies,
  documentIsPayPage,
  loadRazorpay,
  openRazorpay,
  orderOutcome,
  orderTimeline,
  type PaymentStart,
  type RazorpayConstructor,
} from "./shop";

vi.mock("@/lib/api/client", async (original) => ({
  ...(await original<typeof import("@/lib/api/client")>()),
  api: { GET: vi.fn(), POST: vi.fn(), PATCH: vi.fn(), DELETE: vi.fn() },
}));

const answer = <T,>(data: T, status = 200) => Promise.resolve({ data, response: new Response(null, { status }) });

const cart = {
  items: [
    {
      product: "physics-sample-papers-2027",
      title: "Physics Sample Papers",
      price: "299.00",
      quantity: 1,
      total: "299.00",
    },
  ],
  count: 1,
  coupon: null,
  coupon_problem: null,
  subtotal: "299.00",
  savings: [],
  discount: "0.00",
  shipping: null,
  total: "299.00",
  problems: [],
} as never;
const info = {
  "physics-sample-papers-2027": { cover: null, subject: "PHY", kind: "sample-papers" as const, digital: false },
};

beforeEach(() => vi.clearAllMocks());

describe("Price", () => {
  it("shows the MRP struck through and the saving in words only when it differs", () => {
    const { container, rerender } = render(<Price price="499.00" mrp="548.00" />);
    expect(container).toHaveTextContent("₹499");
    expect(container.querySelector("s")).toHaveTextContent("MRP ₹548");
    expect(container).toHaveTextContent("Save ₹49 (9%)");
    rerender(<Price price="299.00" mrp="299.00" />);
    expect(container.querySelector("s")).toBeNull();
    expect(container).not.toHaveTextContent("Save");
  });
});

describe("the checkout's stepper", () => {
  it("marks the current step and links the done ones back to the checkout while the order can change", () => {
    const { unmount } = render(<Stepper label="Checkout" steps={checkoutSteps("/checkout/")} current={2} />);
    expect(screen.getByText("3. Payment").closest("[aria-current]")).toHaveAttribute("aria-current", "step");
    expect(screen.getByRole("link", { name: /1\. Address/ })).toHaveAttribute("href", "/checkout/");
    expect(screen.getByRole("link", { name: /2\. Delivery/ })).toHaveAttribute("href", "/checkout/");
    unmount();
    render(<Stepper label="Checkout" steps={checkoutSteps()} current={3} />); // done: nothing to go back to
    expect(screen.queryAllByRole("link")).toHaveLength(0);
    expect(screen.getByText("4. Done").closest("[aria-current]")).toHaveAttribute("aria-current", "step");
  });
});

describe("copies", () => {
  it("reads whole numbers from 0 to 20 and nothing else", () => {
    expect(copies("3")).toBe(3);
    expect(copies(" 2 ")).toBe(2);
    expect(copies("0")).toBe(0);
    expect(copies("25")).toBe(20);
    expect(copies(-1)).toBe(0);
    expect(copies("")).toBeNull();
    expect(copies("2.5")).toBeNull();
    expect(copies("two")).toBeNull();
  });
});

describe("the cart's copies stepper", () => {
  it("sends a step at once and shows the cart the API answers", async () => {
    vi.mocked(api.PATCH).mockReturnValue(
      answer({
        ...(cart as object),
        items: [{ ...(cart as { items: object[] }).items[0], quantity: 2, total: "598.00" }],
        count: 2,
        subtotal: "598.00",
        total: "598.00",
      }) as never,
    );
    render(<CartView initial={cart} info={info} />);
    await userEvent.click(screen.getByRole("button", { name: "One copy more of Physics Sample Papers" }));
    expect(api.PATCH).toHaveBeenCalledWith("/api/v1/cart/items/{product}/", {
      params: { path: { product: "physics-sample-papers-2027" } },
      body: { quantity: 2 },
    });
    expect(await screen.findByDisplayValue("2")).toBeInTheDocument();
    expect(screen.getAllByText("₹598.00").length).toBeGreaterThan(0);
  });

  it("asks before 0 removes a book, and keeps it on Keep it", async () => {
    render(<CartView initial={cart} info={info} />);
    const box = screen.getByLabelText("Copies of Physics Sample Papers");
    fireEvent.change(box, { target: { value: "0" } });
    fireEvent.blur(box);
    const dialog = await screen.findByRole("dialog", { name: "Remove this book?" });
    expect(api.PATCH).not.toHaveBeenCalled();
    await userEvent.click(within(dialog).getByRole("button", { name: "Keep it" }));
    expect(api.DELETE).not.toHaveBeenCalled();
  });

  it("refuses a number it cannot read without calling the API", () => {
    render(<CartView initial={cart} info={info} />);
    const box = screen.getByLabelText("Copies of Physics Sample Papers");
    fireEvent.change(box, { target: { value: "" } });
    fireEvent.blur(box);
    expect(screen.getByRole("alert")).toHaveTextContent("Enter a number of copies from 0 to 20.");
    expect(api.PATCH).not.toHaveBeenCalled();
  });
});

const ordered = { status: "ordered", at: "2026-10-08T10:42:00+05:30" };

describe("an order's timeline and outcome", () => {
  it("shows what happened, the latest current, then what is still to come", () => {
    const items = orderTimeline({
      timeline: [ordered],
      status: "pending",
      placed_at: null,
      payment_method: "razorpay",
    });
    expect(items.map((item) => [item.label, item.state])).toEqual([
      ["Ordered", "current"],
      ["Paid", "upcoming"],
      ["Packed", "upcoming"],
      ["Shipped", "upcoming"],
      ["Delivered", "upcoming"],
    ]);
    expect(items[0].time).toBe("8 Oct 2026, 10:42");
    const course = orderTimeline(
      {
        timeline: [ordered, { ...ordered, status: "paid" }],
        status: "paid",
        placed_at: ordered.at,
        payment_method: "razorpay",
      },
      true,
    );
    expect(course.map((item) => item.label)).toEqual(["Ordered", "Paid", "Delivered"]); // nothing is posted
    const over = orderTimeline({
      timeline: [ordered, { ...ordered, status: "cancelled" }],
      status: "cancelled",
      placed_at: null,
      payment_method: "razorpay",
    });
    expect(over.every((item) => item.state === "done")).toBe(true);
  });

  it("claims success only when the API says the order is paid or placed", () => {
    expect(orderOutcome({ status: "paid", placed_at: ordered.at, payment_method: "razorpay" })).toBe("paid");
    expect(orderOutcome({ status: "pending", placed_at: ordered.at, payment_method: "cod" })).toBe("placed");
    expect(orderOutcome({ status: "pending", placed_at: null, payment_method: "razorpay" })).toBe("confirming");
    expect(orderOutcome({ status: "cancelled", placed_at: null, payment_method: "razorpay" })).toBe("not-completed");
    expect(orderOutcome({ status: "refunded", placed_at: ordered.at, payment_method: "razorpay" })).toBe(
      "not-completed",
    );
  });

  it("words a cancellation and an address as Django does", () => {
    expect(cancelledMessage("EL-2026-000123", "638.00")).toBe(
      "Order EL-2026-000123 is cancelled. ₹638.00 will be refunded to the account, card or UPI ID you paid from within 5–7 working days.",
    );
    expect(cancelledMessage("EL-2026-000123")).toBe("Order EL-2026-000123 is cancelled.");
    expect(
      addressLines({
        name: "Rahul",
        phone: "+919864012345",
        line1: "1 Lane",
        line2: "",
        city: "Guwahati",
        district: "Kamrup Metro",
        state: "AS",
        pin: "781001",
      }),
    ).toEqual(["Rahul", "1 Lane", "Guwahati, Kamrup Metro district", "Assam 781001", "Mobile +91 98640 12345"]);
  });
});

describe("Razorpay's window", () => {
  const options: PaymentStart = {
    key: "rzp_test_x",
    order_id: "order_x",
    amount: 63800,
    currency: "INR",
    name: "ExamLeaf",
    description: "Order EL-2026-000123",
    prefill: {},
    notes: {},
    theme: {},
    test_mode: true,
  };

  function fake() {
    const made: {
      settings?: Record<string, unknown>;
      failed?: (response: { error?: { description?: string } }) => void;
      opened: boolean;
    } = { opened: false };
    const Razorpay = vi.fn(function (this: unknown, settings: Record<string, unknown>) {
      made.settings = settings;
      return {
        open: () => (made.opened = true),
        on: (_: string, callback: typeof made.failed) => (made.failed = callback),
      };
    }) as unknown as RazorpayConstructor;
    return { Razorpay, made };
  }

  it("opens with the API's options and hands its answer to the server's check", () => {
    const { Razorpay, made } = fake();
    const on = { success: vi.fn(), failure: vi.fn(), dismiss: vi.fn() };
    openRazorpay(Razorpay, options, on);
    expect(made.opened).toBe(true);
    expect(made.settings).toMatchObject({ key: "rzp_test_x", order_id: "order_x", amount: 63800 });
    expect(made.settings).not.toHaveProperty("test_mode");
    const response = { razorpay_order_id: "order_x", razorpay_payment_id: "pay_x", razorpay_signature: "sig" };
    (made.settings!.handler as (r: typeof response) => void)(response);
    expect(on.success).toHaveBeenCalledWith(response);
  });

  it("says a failure in words, and closing the window sends nothing", () => {
    const { Razorpay, made } = fake();
    const on = { success: vi.fn(), failure: vi.fn(), dismiss: vi.fn() };
    openRazorpay(Razorpay, options, on);
    made.failed!({ error: { description: "Card declined" } });
    expect(on.failure).toHaveBeenCalledWith("The payment did not go through (Card declined). You can try again.");
    (made.settings!.modal as { ondismiss: () => void }).ondismiss();
    expect(on.dismiss).toHaveBeenCalled();
    expect(on.success).not.toHaveBeenCalled();
  });

  it("loads checkout.js only when asked, once, with the page's nonce (security review S3)", async () => {
    const script = () => document.querySelector<HTMLScriptElement>('script[src*="checkout.razorpay.com"]');
    expect(script()).toBeNull();
    const loading = loadRazorpay("n0nce");
    expect(script()?.nonce).toBe("n0nce");
    const { Razorpay } = fake();
    Object.assign(window, { Razorpay });
    script()!.dispatchEvent(new Event("load"));
    expect(await loading).toBe(Razorpay);
    expect(await loadRazorpay("n0nce")).toBe(Razorpay); // loaded: no second script
    expect(document.querySelectorAll('script[src*="checkout.razorpay.com"]')).toHaveLength(1);
    delete (window as { Razorpay?: unknown }).Razorpay;
    script()!.remove();
  });

  it("knows whether the document began on a pay page, whose CSP alone lets Razorpay in (S2)", () => {
    const entries = vi.spyOn(performance, "getEntriesByType");
    entries.mockReturnValue([{ name: "https://examleaf.in/checkout/EL-2026-000003/pay/" } as PerformanceEntry]);
    expect(documentIsPayPage()).toBe(true);
    entries.mockReturnValue([{ name: "https://examleaf.in/checkout/t/tok-1/pay/" } as PerformanceEntry]);
    expect(documentIsPayPage()).toBe(true);
    entries.mockReturnValue([{ name: "https://examleaf.in/cart/" } as PerformanceEntry]);
    expect(documentIsPayPage()).toBe(false); // reached by a client-side navigation: the page reloads once
    entries.mockRestore();
  });
});
