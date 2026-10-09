// The actions on a requester's orders: a refund of an order not shipped is in full; of a shipped one, the copies chosen
// (each from zero) or an amount, and an empty form sends nothing (never a refund in full by accident); a refund above
// the limit says which change request waits; each action is drawn only for whoever may do it.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ManifestProvider } from "@/components/shell/manifest";
import { ApiError } from "@/lib/api/errors";
import { refundFromTicket, type SidebarOrder } from "@/lib/api/staff";
import { P } from "@/lib/modules";
import { manifestWith } from "@/test/fixtures";
import { ticketWith } from "@/test/support";

import { refundBody, TicketActions } from "./actions";
import { hasActions } from "./shared";

vi.mock("@/lib/api/staff", async (original) => ({
  ...(await original<typeof import("@/lib/api/staff")>()),
  refundFromTicket: vi.fn(),
}));

const order = (row: Partial<SidebarOrder> = {}): SidebarOrder => ({
  number: "EL-2026-000123",
  status: "shipped",
  status_label: "Shipped",
  total: "2500.00",
  payment_method: "razorpay",
  created: "2026-09-01T06:00:00Z",
  placed_at: "2026-09-01T06:00:00Z",
  is_test: false,
  refund_mode: "partial",
  refund_warning: "",
  linked: true,
  payments: [
    {
      method: "razorpay",
      paid_with: "upi",
      status: "captured",
      amount: "2500.00",
      razorpay_order_id: "order_X",
      razorpay_payment_id: "pay_X",
      created: "2026-09-01T06:00:00Z",
    },
  ],
  refunds: [],
  shipments: [],
  invoice: "INV/2026-27/000412",
  credit_notes: [],
  items: [
    { id: 9101, title: "Physics solutions", quantity: 2, unit_price: "750.00", discount: null },
    { id: 9102, title: "Chemistry solutions", quantity: 1, unit_price: "1000.00", discount: null },
  ],
  ...row,
});

const form = (values: Record<string, string>) => {
  const data = new FormData();
  for (const [name, value] of Object.entries(values)) data.set(name, value);
  return data;
};

beforeEach(() => {
  vi.mocked(refundFromTicket).mockReset();
});

describe("refundBody", () => {
  it("refunds an order not shipped in full, whatever the form says", () => {
    expect(refundBody(order({ refund_mode: "cancel" }), form({ amount: "10" }), "Lost.")).toEqual({
      order: "EL-2026-000123",
      reason: "Lost.",
    });
  });

  it("sends the copies chosen (from zero), else the amount, else nothing", () => {
    expect(refundBody(order(), form({ "line-9101": "1", "line-9102": "0" }), "Torn.")).toEqual({
      order: "EL-2026-000123",
      lines: [{ item: 9101, quantity: 1 }],
      reason: "Torn.",
    });
    expect(refundBody(order(), form({ "line-9101": "0", amount: "300" }), "Late.")).toEqual({
      order: "EL-2026-000123",
      amount: "300",
      reason: "Late.",
    });
    expect(refundBody(order(), form({ "line-9101": "0", "line-9102": "0", amount: "" }), "Late.")).toBeNull();
  });
});

describe("TicketActions", () => {
  const renderActions = (permissions: string[]) =>
    render(
      <ManifestProvider manifest={manifestWith(permissions)}>
        <TicketActions ticket={ticketWith({ sidebar: { ...ticketWith().sidebar, orders: [order()] } })} />
      </ManifestProvider>,
    );

  it("sends nothing from an empty refund form, and says why", async () => {
    renderActions([P.refundOrder]);
    await userEvent.type(screen.getByLabelText("Reason"), "The parcel came damaged.");
    await userEvent.click(screen.getByRole("button", { name: "Refund" }));
    expect(refundFromTicket).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("Choose the copies to refund, or write the amount");
  });

  it("starts each copy at zero, and says which change request waits above the limit", async () => {
    vi.mocked(refundFromTicket).mockRejectedValue(
      new ApiError(
        202,
        "approval_required",
        "This needs a second person's approval.",
        {},
        {
          id: 512,
          status: "pending",
          checker: "staff.approve_refund",
          payload_sha256: "x",
        },
      ),
    );
    renderActions([P.refundOrder]);
    const physics = screen.getByLabelText(/Physics solutions/);
    expect(physics).toHaveValue(0);
    await userEvent.clear(physics);
    await userEvent.type(physics, "2");
    await userEvent.type(screen.getByLabelText("Reason"), "Both copies torn.");
    await userEvent.click(screen.getByRole("button", { name: "Refund" }));
    expect(refundFromTicket).toHaveBeenCalledWith("SR-2026-000101", {
      order: "EL-2026-000123",
      lines: [{ item: 9101, quantity: 2 }],
      reason: "Both copies torn.",
    });
    expect(screen.getByText("A second person needs to approve this")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^Open the change request/ })).toHaveAttribute("href", "/approvals/512/");
  });

  it("draws only what the manifest allows", () => {
    renderActions([P.ticketsHandle]);
    expect(screen.queryByRole("button", { name: "Refund" })).toBeNull();
    expect(screen.getByRole("button", { name: "Send the invoice again" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel the order" })).toBeNull(); // shipped: nothing to cancel
  });

  it("has an Actions section only when one of them is the person's", () => {
    const ticket = ticketWith({ sidebar: { ...ticketWith().sidebar, orders: [] } });
    expect(hasActions(ticket, () => false)).toBe(false);
    expect(hasActions(ticket, (perm) => perm === P.bookCodesView)).toBe(true);
    const grievance = ticketWith({ category: "grievance" });
    expect(hasActions(grievance, (perm) => perm === P.requestsHandle)).toBe(true);
    expect(hasActions({ ...grievance, data_request: 802 }, (perm) => perm === P.requestsHandle)).toBe(false);
  });
});
