// The Orders module's logic in the console: the refund's estimate from the invoiced values (two lines of three), the
// refund dialog's body and its 202 (a change request shown, nothing refunded), the 5-second undo (sent after the wait,
// not at all when undone, at once when the page is left), and the bulk bar's cancel (the count typed; more than 250
// refused before anyone asks).
import { act, render, renderHook, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ManifestProvider } from "@/components/shell/manifest";
import { ApiError } from "@/lib/api/errors";
import { askRefund, type OrderDetail, type OrderRow, startOrdersJob } from "@/lib/api/staff";
import { P } from "@/lib/modules";
import { manifestWith } from "@/test/fixtures";
import { navigation } from "@/test/navigation";

import { OrdersBulk } from "./orders-bulk";
import { estimate, RefundDialog } from "./refund-dialog";
import { useUndo } from "./undo";

vi.mock("@/lib/api/staff", async (original) => ({
  ...(await original<typeof import("@/lib/api/staff")>()),
  askRefund: vi.fn(),
  startOrdersJob: vi.fn(),
}));

const line = (id: number, title: string, invoiced: string, quantity = 1) => ({
  id,
  product: title.toLowerCase(),
  title,
  isbn: "",
  hsn_code: "4901",
  gst_rate: "0.00",
  mrp: "1000.00",
  unit_price: invoiced,
  quantity,
  line_total: invoiced,
  discount: "0.00",
  invoiced,
  refunded: 0,
  returnable: quantity,
  digital: false,
});

const ORDER = {
  id: 41,
  number: "EL-2026-000123",
  lines: [line(1, "Physics", "720.00"), line(2, "Chemistry", "810.00"), line(3, "Biology", "900.00")],
  refund: {
    payment: 410,
    payment_method: "razorpay",
    refundable: "2430.00",
    shipping_left: "0.00",
    methods: ["source", "bank"],
    cancels: false,
    payment_age_days: 200,
    warnings: ["The payment is older than 6 months: Razorpay may refuse a normal refund."],
  },
} as unknown as OrderDetail;

beforeEach(() => {
  navigation.router.refresh = vi.fn();
  navigation.router.push = vi.fn();
  vi.mocked(askRefund).mockReset();
  vi.mocked(startOrdersJob).mockReset();
});

afterEach(() => vi.useRealTimers());

describe("estimate", () => {
  it("adds each line's invoiced value per copy, and the shipping, in paise", () => {
    expect(estimate(ORDER.lines, { 2: 1, 3: 1 }, "")).toBe(171_000);
    expect(estimate([line(9, "Two", "999.99", 3)], { 9: 2 }, "40")).toBe(66_666 + 4_000);
    expect(estimate(ORDER.lines, {}, "abc")).toBe(0);
  });
});

describe("RefundDialog", () => {
  it("shows the warning before confirming, sends the chosen lines, and shows the change request of a 202", async () => {
    const user = userEvent.setup();
    const waiting = { id: 31, status: "pending", checker: "staff.approve_refund", payload_sha256: "a".repeat(64) };
    vi.mocked(askRefund).mockRejectedValue(
      new ApiError(202, "approval_required", "A second person needs to approve this", {}, waiting),
    );
    render(
      <ManifestProvider manifest={manifestWith([P.refundOrder])}>
        <RefundDialog order={ORDER} />
      </ManifestProvider>,
    );
    await user.click(screen.getByRole("button", { name: "Refund" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/older than 6 months/)).toBeInTheDocument();
    await user.clear(within(dialog).getByLabelText("Copies of Chemistry to refund"));
    await user.type(within(dialog).getByLabelText("Copies of Chemistry to refund"), "1");
    await user.clear(within(dialog).getByLabelText("Copies of Biology to refund"));
    await user.type(within(dialog).getByLabelText("Copies of Biology to refund"), "5"); // one copy: the most left
    expect(within(dialog).getByText(/About ₹1,710/)).toBeInTheDocument();
    await user.type(within(dialog).getByLabelText("Reason"), "Damaged in transit");
    await user.click(within(dialog).getByRole("button", { name: "Ask for the refund" }));
    expect(askRefund).toHaveBeenCalledWith("EL-2026-000123", {
      reason: "Damaged in transit",
      restock: false,
      speed: "normal",
      customer_agreed: false,
      method: "source",
      lines: [
        { item: 2, quantity: 1 },
        { item: 3, quantity: 1 },
      ],
    });
    expect(await within(dialog).findByText("A second person needs to approve this")).toBeInTheDocument();
    expect(within(dialog).getByRole("link", { name: /Open the change request/ })).toHaveAttribute(
      "href",
      "/approvals/31/",
    );
  });

  it("asks for the customer's account by bank, and their agreement for an online payment", async () => {
    const user = userEvent.setup();
    vi.mocked(askRefund).mockResolvedValue({} as never);
    render(
      <ManifestProvider manifest={manifestWith([P.refundOrder])}>
        <RefundDialog order={ORDER} />
      </ManifestProvider>,
    );
    await user.click(screen.getByRole("button", { name: "Refund" }));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("radio", { name: /By bank transfer or UPI/ }));
    await user.type(within(dialog).getByLabelText("UPI ID"), "rahul@okicici");
    await user.click(within(dialog).getByRole("checkbox", { name: /customer agreed/ }));
    await user.type(within(dialog).getByLabelText("Reason"), "Asked by phone");
    await user.click(within(dialog).getByRole("button", { name: "Ask for the refund" }));
    expect(askRefund).toHaveBeenCalledWith(
      "EL-2026-000123",
      expect.objectContaining({ method: "bank", payee: { upi: "rahul@okicici" }, customer_agreed: true }),
    );
  });
});

describe("useUndo", () => {
  it("sends after 5 seconds, not at all when undone, and at once when the page is left", () => {
    vi.useFakeTimers();
    const send = vi.fn();
    const { result, unmount } = renderHook(() => useUndo());
    act(() => result.current.start("Marking 1 order packed in 5 s.", send));
    expect(result.current.pending).toEqual({ left: 5, message: "Marking 1 order packed in 5 s." });
    act(() => vi.advanceTimersByTime(4000));
    expect(send).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(1000));
    expect(send).toHaveBeenCalledTimes(1);
    expect(result.current.pending).toBeNull();

    act(() => result.current.start("Again", send));
    act(() => result.current.undo());
    act(() => vi.advanceTimersByTime(6000));
    expect(send).toHaveBeenCalledTimes(1);

    act(() => result.current.start("Leaving", send));
    unmount();
    expect(send).toHaveBeenCalledTimes(2);
  });
});

describe("OrdersBulk", () => {
  const rows = (count: number) =>
    Array.from({ length: count }, (_, index) => ({
      id: index + 1,
      number: `EL-2026-${String(index + 1).padStart(6, "0")}`,
    })) as OrderRow[];

  it("cancels only once the count is typed, as a job", async () => {
    const user = userEvent.setup();
    const onJob = vi.fn();
    vi.mocked(startOrdersJob).mockResolvedValue({ id: 9 } as never);
    render(
      <ManifestProvider manifest={manifestWith([P.ordersChange, P.packOrder, P.jobsView])}>
        <OrdersBulk rows={rows(3)} clear={vi.fn()} onPack={vi.fn()} onJob={onJob} />
      </ManifestProvider>,
    );
    expect(screen.getByText("3 orders selected")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Cancel orders" }));
    const dialog = screen.getByRole("dialog");
    await user.type(within(dialog).getByLabelText("Reason"), "Out of print");
    const confirm = within(dialog).getByRole("button", { name: "Cancel them" });
    expect(confirm).toBeDisabled();
    await user.type(within(dialog).getByLabelText("To confirm, type 3 below."), "3");
    await user.click(confirm);
    expect(startOrdersJob).toHaveBeenCalledWith("orders_cancel", {
      targets: ["EL-2026-000001", "EL-2026-000002", "EL-2026-000003"],
      reason: "Out of print",
    });
    expect(onJob).toHaveBeenCalledWith({ id: 9 }, "Cancel orders");
  });

  it("refuses more than 250 before anyone is asked, and draws nothing the person may not do", () => {
    render(
      <ManifestProvider manifest={manifestWith([P.ordersChange])}>
        <OrdersBulk rows={rows(251)} clear={vi.fn()} onPack={vi.fn()} onJob={vi.fn()} />
      </ManifestProvider>,
    );
    expect(screen.getByRole("button", { name: "Cancel orders" })).toBeDisabled();
    expect(screen.getAllByText(/At most 250 orders are cancelled at once/).length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: "Mark packed" })).not.toBeInTheDocument();
  });
});
