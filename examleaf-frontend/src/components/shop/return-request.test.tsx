// Sending books back from the order page: the form only for the owner while the API says they may ask, the copies,
// the reason and their words sent as the API takes them (books by their product), a refusal in the API's words, and
// each return's state in a line (the courier and number to send it with once the label is sent; a decline's reason).
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api/client";
import type { Order } from "@/lib/api/shop";

import { OrderView } from "./order-view";

vi.mock("@/lib/api/client", async (original) => ({
  ...(await original<typeof import("@/lib/api/client")>()),
  api: { GET: vi.fn(), POST: vi.fn(), PATCH: vi.fn(), DELETE: vi.fn() },
}));

const answer = <T,>(data: T, status = 200) => Promise.resolve({ data, response: new Response(null, { status }) });
const refused = (body: unknown, status = 400) =>
  Promise.resolve({ error: body, response: new Response(null, { status }) });

const delivered = {
  number: "EL-2026-000123",
  created: "2026-10-01T10:42:00+05:30",
  placed_at: "2026-10-01T10:45:00+05:30",
  status: "delivered",
  status_label: "delivered",
  payment_method: "razorpay",
  total: "638.00",
  items: [
    { product: "physics-sample-papers-2027", title: "Physics Sample Papers", quantity: 2, unit_price: "299.00" },
    { product: "chemistry-sample-papers-2027", title: "Chemistry Sample Papers", quantity: 1, unit_price: "299.00" },
  ],
  is_digital: false,
  has_shipping: true,
  shipping_address: { name: "Rahul", line1: "1 Lane", city: "Guwahati", state: "AS", pin: "781001" },
  subtotal: "897.00",
  savings: [],
  shipping_fee: "40.00",
  timeline: [{ status: "delivered", at: "2026-10-05T10:00:00+05:30" }],
  shipments: [],
  refunds: [],
  returns: [],
  can_cancel: false,
  can_pay: false,
  can_return: true,
  return_until: "2026-10-20T10:00:00+05:30",
  invoice: null,
  credit_notes: [],
} as unknown as Order;

const view = (order: Order, mode: "owner" | "link" = "owner") =>
  render(<OrderView number="EL-2026-000123" order={order} mode={mode} digital={false} books={{}} />);

beforeEach(() => vi.mocked(api.POST).mockReset());

describe("sending books back", () => {
  it("asks with the copies of each book, the reason and what happened", async () => {
    vi.mocked(api.POST).mockReturnValue(answer({ ...delivered, can_return: false }, 201) as never);
    view(delivered);
    await userEvent.click(screen.getByRole("button", { name: "Send books back" }));
    await userEvent.clear(screen.getByLabelText("Copies of Physics Sample Papers to send back"));
    await userEvent.type(screen.getByLabelText("Copies of Physics Sample Papers to send back"), "1");
    await userEvent.selectOptions(screen.getByLabelText("Why"), "misprint");
    await userEvent.type(screen.getByLabelText(/What happened/), "Pages 12 to 16 are blank.");
    await userEvent.click(screen.getByRole("button", { name: "Ask to send them back" }));
    expect(api.POST).toHaveBeenCalledWith("/api/v1/orders/{number}/returns/", {
      params: { path: { number: "EL-2026-000123" } },
      body: {
        lines: [{ product: "physics-sample-papers-2027", quantity: 1 }],
        reason: "misprint",
        note: "Pages 12 to 16 are blank.",
      },
    });
  });

  it("says why the API refused, and asks for a copy before sending anything", async () => {
    vi.mocked(api.POST).mockReturnValue(
      refused({ non_field_errors: ["Books are sent back within 15 days of delivery."] }) as never,
    );
    view(delivered);
    await userEvent.click(screen.getByRole("button", { name: "Send books back" }));
    await userEvent.click(screen.getByRole("button", { name: "Ask to send them back" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Choose at least one copy to send back.");
    expect(api.POST).not.toHaveBeenCalled();
    await userEvent.type(screen.getByLabelText("Copies of Chemistry Sample Papers to send back"), "1");
    await userEvent.click(screen.getByRole("button", { name: "Ask to send them back" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Books are sent back within 15 days of delivery.");
  });

  it("offers no form when the API says no, nor on an emailed link, and shows each return's state", () => {
    const returns = [
      {
        number: "RR-00012",
        status: "label_sent",
        status_label: "send the books back with the courier and number below",
        reason: "damaged",
        created: "2026-10-06T10:00:00+05:30",
        lines: [],
        decision_note: "",
        return_courier: "India Post",
        return_awb: "EA987654321IN",
      },
      {
        number: "RR-00011",
        status: "declined",
        status_label: "declined",
        reason: "late",
        created: "2026-10-04T10:00:00+05:30",
        lines: [],
        decision_note: "Asked 40 days after delivery",
        return_courier: "",
        return_awb: "",
      },
    ];
    view({ ...delivered, can_return: false, returns } as unknown as Order);
    expect(screen.queryByRole("button", { name: "Send books back" })).toBeNull();
    const list = screen.getByRole("list", { name: "Returns" });
    expect(
      within(list)
        .getByText(/RR-00012/)
        .closest("li"),
    ).toHaveTextContent(
      "Return RR-00012: send the books back with the courier and number below (India Post, number EA987654321IN).",
    );
    expect(
      within(list)
        .getByText(/RR-00011/)
        .closest("li"),
    ).toHaveTextContent("Return RR-00011: declined: Asked 40 days after delivery.");
    view(delivered, "link");
    expect(screen.queryByRole("button", { name: "Send books back" })).toBeNull();
  });
});
