// The shop's logic and islands (package 8B, then the Answer Script redesign): prices with MRP and saving, the
// checkout's stepper states, the cart's copies rule and its stepper (a step is sent at once, 0 asks first), the
// coupon applied and refused in the API's words, the checkout's first step (the server's rules before going on, the
// PIN code found and not found), Add to cart sending once however often it is pressed, an order's timeline and
// outcome, the done page claiming nothing before the server (no PAID while a payment is confirmed or not completed),
// a payment Razorpay refused (the order kept, cash on delivery offered), the cancel dialog giving the focus back, and
// Razorpay's window around the API's options (its answer to the server, failures in words, closing sends nothing).
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Price } from "@/components/ui/price";
import { Stepper } from "@/components/ui/stepper";
import { api, ApiError } from "@/lib/api/client";
import type { Order } from "@/lib/api/shop";

import { CancelOrder } from "./cancel-order";
import { CartView } from "./cart-view";
import { CheckoutForm, pinNote, validateAddress } from "./checkout-form";
import { OrderView } from "./order-view";
import { PayButton } from "./pay-button";
import { AddToCart } from "./product-actions";
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
/** The API's refusal as openapi-fetch hands it over: unwrap() turns it into an ApiError with the API's words. */
const refused = (body: unknown, status = 400) =>
  Promise.resolve({ error: body, response: new Response(null, { status }) });

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

beforeEach(() => {
  vi.clearAllMocks();
  window.sessionStorage.clear(); // the checkout's draft of the tab
});

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
    const more = screen.getByRole("button", { name: "One copy more of Physics Sample Papers" });
    await userEvent.click(more);
    expect(api.PATCH).toHaveBeenCalledWith("/api/v1/cart/items/{product}/", {
      params: { path: { product: "physics-sample-papers-2027" } },
      body: { quantity: 2 },
    });
    expect(await screen.findByDisplayValue("2")).toBeInTheDocument();
    expect(screen.getAllByText("₹598.00").length).toBeGreaterThan(0);
    expect(more).toHaveFocus(); // the next Enter adds another (accessibility review F1)
  });

  it("gives focus to the list once a confirmed Remove has taken the line away", async () => {
    vi.mocked(api.DELETE).mockReturnValue(answer({ ...(cart as object), items: [], count: 0 }) as never);
    render(
      <main>
        <CartView initial={cart} info={info} />
      </main>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Remove Physics Sample Papers" }));
    const dialog = screen.getByRole("dialog", { name: "Remove this book?" });
    expect(within(dialog).getByRole("button", { name: "Keep it" })).toHaveFocus();
    await userEvent.click(within(dialog).getByRole("button", { name: "Remove" }));
    const empty = await screen.findByText("Your cart is empty");
    await waitFor(() => expect(empty).toHaveFocus()); // its heading, not the page's start
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

describe("the cart's coupon", () => {
  it("shows the discount the API answers", async () => {
    vi.mocked(api.POST).mockReturnValue(
      answer({
        ...(cart as object),
        coupon: "WELCOME10",
        savings: [{ label: "Coupon WELCOME10", amount: "29.90" }],
        discount: "29.90",
        total: "269.10",
      }) as never,
    );
    render(<CartView initial={cart} info={info} />);
    await userEvent.type(screen.getByLabelText("Coupon code"), "welcome10");
    await userEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(api.POST).toHaveBeenCalledWith("/api/v1/cart/coupon/", { body: { code: "welcome10" } });
    expect(await screen.findByText("Coupon WELCOME10")).toBeInTheDocument(); // the API's own label
    expect(screen.getByText("−₹29.90")).toBeInTheDocument();
    expect(screen.getByText("₹269.10")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove the coupon" })).toBeInTheDocument();
  });

  it("says the API's refusal on the field, and applies nothing", async () => {
    vi.mocked(api.POST).mockReturnValue(refused({ code: ["This code cannot be applied to this cart."] }) as never);
    render(<CartView initial={cart} info={info} />);
    await userEvent.type(screen.getByLabelText("Coupon code"), "nosuchcode");
    await userEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(await screen.findByText("This code cannot be applied to this cart.")).toBeInTheDocument();
    expect(screen.getByLabelText("Coupon code")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("Coupon code")).toHaveAccessibleDescription(
      "This code cannot be applied to this cart.",
    );
    expect(screen.queryByText(/^Coupon [A-Z0-9]+$/)).toBeNull(); // no saving row
    expect(screen.getAllByText("₹299.00", { selector: "dd" })).toHaveLength(2); // the books and the total, as they were
  });
});

describe("the checkout's address step", () => {
  const quote = (pin: string, states: string[], districts: string[]) => ({
    pin,
    states,
    districts,
    state: states.length === 1 ? states[0] : null,
    amount: "299.00",
    fee: states.length ? "40.00" : null,
    free_above: states.length ? "499.00" : null,
  });
  function answers(found: ReturnType<typeof quote>) {
    vi.mocked(api.GET).mockImplementation(((path: string, options: { params?: { query?: { pin?: string } } }) => {
      if (path === "/api/v1/shipping/quote/") return answer(options.params?.query?.pin ? found : quote("", ["AS"], []));
      return answer(cart);
    }) as never);
  }
  const form = () => (
    <CheckoutForm cart={cart} addresses={[]} email="" cod={{ offered: false, max: "1500.00" }} digital={false} guest />
  );

  it("fills the district and state from a PIN code the directory knows, and says so", async () => {
    answers(quote("781001", ["AS"], ["Kamrup Metro"]));
    render(form());
    await userEvent.selectOptions(screen.getByLabelText(/^State/), "BR");
    await userEvent.type(screen.getByLabelText(/^PIN code/), "781001");
    expect(await screen.findByText("Kamrup Metro, Assam: filled in below")).toBeInTheDocument();
    expect(screen.getByLabelText(/^District/)).toHaveValue("Kamrup Metro");
    expect(screen.getByLabelText(/^State/)).toHaveValue("AS");
    expect(api.GET).toHaveBeenCalledWith(
      "/api/v1/shipping/quote/",
      expect.objectContaining({ params: { query: { pin: "781001" } } }),
    );
  });

  it("says when the directory does not know the PIN code, and leaves the boxes to the buyer", async () => {
    answers(quote("781999", [], []));
    render(form());
    await userEvent.type(screen.getByLabelText(/^PIN code/), "781999");
    expect(
      await screen.findByText("We don't know PIN 781999. Type the district and state yourself."),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/^District/)).toHaveValue("");
  });

  it("checks the boxes with the server's rules before going on, and keeps what was typed in the tab", async () => {
    answers(quote("781001", ["AS"], ["Kamrup Metro"]));
    const { unmount } = render(form());
    await userEvent.click(screen.getByRole("button", { name: "Continue to delivery" }));
    const summary = screen.getByRole("alert");
    expect(within(summary).getByRole("link", { name: "PIN code: Enter the 6-digit PIN code." })).toHaveAttribute(
      "href",
      "#pin",
    );
    expect(screen.getByLabelText(/^PIN code/)).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Where should we deliver?"); // still step 1
    await userEvent.type(screen.getByLabelText(/^Full name/), "Rahul Das");
    unmount(); // a log-in round trip after a 401, or Back: the tab's draft brings it back
    render(form());
    expect(screen.getByLabelText(/^Full name/)).toHaveValue("Rahul Das");
  });

  it("offers cash on delivery at the Delivery step when the server does, with its terms and its own button", async () => {
    answers(quote("781001", ["AS"], ["Kamrup Metro"]));
    const address = {
      id: 7,
      name: "Rahul Das",
      phone: "+919864012345",
      line1: "1 Lane",
      line2: "",
      city: "Guwahati",
      district: "Kamrup Metro",
      state: "AS" as const,
      pin: "781001",
      is_default: true,
      created: ordered.at,
      modified: ordered.at,
    };
    render(
      <CheckoutForm
        cart={cart}
        addresses={[address]}
        email="rahul@example.com"
        cod={{ offered: true, max: "1500.00" }}
        digital={false}
      />,
    );
    expect(screen.getByRole("radio", { name: /Rahul Das/ })).toBeChecked(); // the address book's default
    expect(screen.queryByRole("radio", { name: /Cash on delivery/ })).toBeNull(); // not on the Address step
    await userEvent.click(screen.getByRole("button", { name: "Continue to delivery" }));
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Delivery to Assam");
    await userEvent.click(screen.getByRole("radio", { name: /Cash on delivery/ }));
    expect(screen.getByText(/For accounts with a confirmed email address, on orders up to ₹1,500/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Place the order: pay ₹[\d,.]+ on delivery$/ })).toBeInTheDocument();
  });

  it("waits for a parent's consent: the form is disabled and says why", () => {
    answers(quote("781001", ["AS"], ["Kamrup Metro"]));
    render(
      <CheckoutForm
        cart={cart}
        addresses={[]}
        email="minor@example.com"
        cod={{ offered: false, max: "1500.00" }}
        digital={false}
        consentPending
      />,
    );
    expect(screen.getByText("Waiting for your parent's or guardian's consent")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Send them the link again" })).toHaveAttribute("href", "/account/privacy/");
    expect(screen.getByLabelText(/^Full name/)).toBeDisabled();
    expect(screen.getByRole("button", { name: "Continue to delivery" })).toBeDisabled();
  });

  it("reads mobile numbers and PIN codes as the backend does", () => {
    const draft = {
      name: "Rahul",
      phone: "+91 98640-12345",
      line1: "1 Lane",
      line2: "",
      city: "Guwahati",
      district: "Kamrup Metro",
      state: "AS" as const,
      pin: "781 001",
    };
    expect(validateAddress(draft, { newAddress: true })).toEqual({});
    expect(validateAddress({ ...draft, phone: "12345" }, { newAddress: true }).phone).toEqual([
      "Enter a 10-digit Indian mobile number.",
    ]);
    expect(validateAddress(draft, { newAddress: false, email: "" }).email).toBeTruthy();
    expect(
      pinNote({ pin: "999992", states: ["AS", "ML"], districts: [], known: true }, { ...draft, pin: "999992" }),
    ).toEqual({
      text: "PIN code 999992 lies in Assam and Meghalaya: choose the state.",
      found: false,
    });
  });
});

describe("Add to cart", () => {
  it("sends once, however often it is pressed while the first is on its way", async () => {
    document.cookie = "csrftoken=test";
    vi.mocked(api.POST).mockReturnValue(new Promise(() => undefined) as never); // the server has not answered yet
    render(
      <AddToCart
        options={[
          {
            slug: "physics-sample-papers-2027",
            title: "Physics Sample Papers",
            label: "Physics Sample Papers",
            price: "299.00",
            mrp: "299.00",
            inStock: true,
            digital: false,
          },
        ]}
      />,
    );
    const add = screen.getByRole("button", { name: "Add to cart · ₹299" });
    await userEvent.click(add);
    await waitFor(() => expect(add).toHaveAttribute("aria-busy", "true"));
    await userEvent.click(add);
    await userEvent.click(screen.getByRole("button", { name: "Buy now" }));
    fireEvent.submit(add.closest("form")!); // Enter in the copies box
    expect(api.POST).toHaveBeenCalledTimes(1);
    expect(api.POST).toHaveBeenCalledWith("/api/v1/cart/items/", {
      body: { product: "physics-sample-papers-2027", quantity: 1 },
    });
  });
});

const order = {
  number: "EL-2026-000123",
  created: "2026-10-08T10:42:00+05:30",
  placed_at: null,
  status: "pending",
  status_label: "awaiting payment",
  payment_method: "razorpay",
  total: "339.00",
  items: [
    {
      product: "physics-sample-papers-2027",
      title: "Physics Sample Papers",
      hsn_code: "4901",
      gst_rate: "0.00",
      mrp: "299.00",
      unit_price: "299.00",
      quantity: 1,
      line_total: "299.00",
    },
  ],
  is_digital: false,
  has_shipping: true,
  email: "rahul@example.com",
  shipping_address: {
    name: "Rahul",
    phone: "+919864012345",
    line1: "1 Lane",
    city: "Guwahati",
    state: "AS",
    pin: "781001",
  },
  subtotal: "299.00",
  savings: [],
  discount: "0.00",
  shipping_fee: "40.00",
  coupon_code: "",
  timeline: [ordered],
  shipments: [],
  refunds: [],
  can_cancel: true,
  can_pay: true,
  invoice: null,
  credit_notes: [],
  web_url: "https://examleaf.in/orders/t/tok-1/",
} as unknown as Order;

describe("the done page", () => {
  const done = (state: Partial<Order>) =>
    render(
      <OrderView number="EL-2026-000123" order={{ ...order, ...state }} mode="thanks" digital={false} books={{}} />,
    );

  it("says the payment is being confirmed, with no PAID stamp and nothing to pay again", () => {
    const { container } = done({});
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("We're confirming your payment");
    expect(screen.getByRole("status")).toHaveTextContent("Checking EL-2026-000123. This page updates once.");
    expect(container).not.toHaveTextContent(/PAID/);
    expect(screen.queryByRole("link", { name: /^Pay/ })).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("says an order cancelled while paying was not completed, with no PAID stamp", () => {
    const { container } = done({ status: "cancelled", status_label: "cancelled" });
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("We could not complete this order");
    expect(container).not.toHaveTextContent(/PAID/);
  });

  it("stamps PAID only once the server says the order is paid", () => {
    const { container } = done({ status: "paid", status_label: "paid", placed_at: ordered.at });
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Thank you. Your order is placed.");
    expect(container).toHaveTextContent(/PAID/);
  });

  it("places a cash-on-delivery order without a PAID stamp", () => {
    const { container } = done({ payment_method: "cod", placed_at: ordered.at });
    expect(screen.getByText(/Pay ₹339.00 in cash when the parcel arrives/)).toBeInTheDocument();
    expect(container).not.toHaveTextContent(/PAID/);
  });
});

describe("a payment Razorpay refused", () => {
  it("keeps the order, offers to try again or cash on delivery, and claims nothing", async () => {
    const options: PaymentStart = {
      key: "rzp_test_x",
      order_id: "order_x",
      amount: 33900,
      currency: "INR",
      name: "ExamLeaf",
      description: "Order EL-2026-000123",
      prefill: {},
      notes: {},
      theme: {},
      test_mode: false,
    };
    vi.mocked(api.POST).mockReturnValue(answer(options) as never);
    Object.assign(window, {
      Razorpay: function (this: Record<string, unknown>) {
        let failed: (response: { error: { description: string } }) => void = () => undefined;
        this.on = (_: string, callback: typeof failed) => (failed = callback);
        this.open = () => failed({ error: { description: "Your bank declined it" } });
      },
    });
    const { container } = render(<PayButton number="EL-2026-000123" total="339.00" nonce="n0nce" codInstead />);
    const pay = await screen.findByRole("button", { name: "Pay ₹339.00" });
    await waitFor(() => expect(pay).not.toHaveAttribute("aria-busy"));
    await userEvent.click(pay);
    expect(
      await screen.findByText("The payment did not go through (Your bank declined it). You can try again."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Your order EL-2026-000123 is kept: you can pay it again for two days."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Pay cash on delivery instead" })).toHaveAttribute(
      "href",
      "/checkout/?pay=cod",
    );
    expect(api.POST).toHaveBeenCalledTimes(1); // the options only: nothing was sent to be confirmed
    expect(container).not.toHaveTextContent(/PAID/);
    delete (window as { Razorpay?: unknown }).Razorpay;
  });

  it("says what happens to the money when its confirmation gets no answer, and lets Pay go when the window fails", async () => {
    const options = { key: "rzp_test_x", order_id: "order_x", amount: 33900, currency: "INR", test_mode: false };
    vi.mocked(api.POST)
      .mockReturnValueOnce(answer(options) as never)
      // the confirmation's 30 s ran out (timedFetch): may have gone through
      .mockRejectedValueOnce(new ApiError(0, "unavailable", "ExamLeaf didn't answer in time.") as never);
    let open = (settings: { handler: (response: unknown) => void }) => settings.handler({ razorpay_payment_id: "p" });
    Object.assign(window, {
      Razorpay: function (this: Record<string, unknown>, settings: { handler: (response: unknown) => void }) {
        this.on = () => undefined;
        this.open = () => open(settings);
      },
    });
    const { container } = render(<PayButton number="EL-2026-000123" total="339.00" nonce="n0nce" />);
    const pay = await screen.findByRole("button", { name: "Pay ₹339.00" });
    await waitFor(() => expect(pay).not.toHaveAttribute("aria-busy"));
    await userEvent.click(pay);
    expect(await screen.findByText(/we confirm the order or refund it by ourselves/)).toBeInTheDocument();
    expect(container).not.toHaveTextContent(/PAID/);

    open = () => {
      throw new Error("Razorpay's window would not open");
    };
    await userEvent.click(pay);
    expect(await screen.findByText(/The payment window could not be loaded/)).toBeInTheDocument();
    expect(pay).not.toHaveAttribute("aria-busy"); // Pay is ready again, not busy for good
    delete (window as { Razorpay?: unknown }).Razorpay;
  });
});

describe("the cancel dialog", () => {
  it("opens on Keep the order and gives the focus back to the button that opened it", async () => {
    render(<CancelOrder number="EL-2026-000123" paid={false} digital={false} />);
    const trigger = screen.getAllByRole("button", { name: "Cancel order" })[0];
    await userEvent.click(trigger);
    const dialog = screen.getByRole("dialog", { name: "Cancel order EL-2026-000123?" });
    const keep = within(dialog).getByRole("button", { name: "Keep the order" });
    expect(keep).toHaveFocus();
    await userEvent.click(keep);
    expect(dialog).not.toHaveAttribute("open");
    expect(trigger).toHaveFocus();
    expect(api.POST).not.toHaveBeenCalled();
  });
});
