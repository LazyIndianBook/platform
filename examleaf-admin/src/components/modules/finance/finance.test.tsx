// The Finance module's logic in the console: Finance today's words and links (none for what waits for nothing or is not
// set up), the tabs a manifest opens, where a refund's or an offline payment's row opens, the links' actions by state
// and permission, "Ask Razorpay again" and what it changed, a settlement line matched by hand (a number checked before
// anyone is asked, an adjustment accepted, nothing drawn for a matched line or a posted settlement), a day fetched as
// a job and its counts, a B2B link made and its address shown to copy.
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ManifestProvider } from "@/components/shell/manifest";
import {
  askPaymentLink,
  fetchSettlements,
  type FinanceLink,
  type FinanceSettlementLine,
  type FinanceToday,
  type Job,
  matchSettlementLine,
  reconcileFinancePayment,
} from "@/lib/api/staff";
import { P } from "@/lib/modules";
import { targetHref } from "@/lib/targets";
import { manifestWith } from "@/test/fixtures";
import { navigation } from "@/test/navigation";

import { financeTabs } from "./finance-tabs";
import { linkActions, NewLinkForm } from "./links";
import { ReconcileButton } from "./payments";
import { requestHref, requestName } from "./requests";
import { FetchForm, FetchResult, idOf, MatchLine } from "./settlements";
import { DocumentErpState, documentKey, TodayList, todayWords } from "./today";

vi.mock("@/lib/api/staff", async (original) => ({
  ...(await original<typeof import("@/lib/api/staff")>()),
  askPaymentLink: vi.fn(),
  fetchSettlements: vi.fn(),
  matchSettlementLine: vi.fn(),
  reconcileFinancePayment: vi.fn(),
}));

beforeEach(() => {
  navigation.router.refresh = vi.fn();
  vi.mocked(askPaymentLink).mockReset();
  vi.mocked(fetchSettlements).mockReset();
  vi.mocked(matchSettlementLine).mockReset();
  vi.mocked(reconcileFinancePayment).mockReset();
});

const row = (key: string, count: number | null, extra: Partial<FinanceToday["rows"][number]> = {}) =>
  ({ key, count, oldest: null, amount: null, configured: count !== null, ...extra }) as FinanceToday["rows"][number];

describe("Finance today", () => {
  it("says how many wait, how much and since when; links only what waits", () => {
    expect(todayWords(row("stuck_payments", 2, { amount: "1178.00", oldest: "2026-10-08" }))).toBe(
      "2 waiting · ₹1,178 · oldest from 8 Oct 2026",
    );
    expect(todayWords(row("b2b_to_post", 0))).toBe("Nothing waits");
    expect(todayWords(row("disputes", null))).toBe("Not set up");
    render(
      <TodayList
        today={{
          livemode: false,
          as_of: "2026-10-10T04:00:00Z",
          rows: [row("refunds_to_approve", 1, { amount: "2500.00" }), row("bank_refunds", 0), row("disputes", null)],
        }}
      />,
    );
    expect(screen.getByRole("link", { name: "Refunds to approve" })).toHaveAttribute(
      "href",
      "/finance/refunds/?state=waiting",
    );
    expect(screen.queryByRole("link", { name: "Bank refunds to transfer" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Disputes" })).not.toBeInTheDocument();
    expect(screen.getByText(/test keys/)).toBeInTheDocument();
  });

  it("shows a document's copy in ERPNext, its outbox rows in words", () => {
    expect(documentKey(" EL/2026-27/00123 ")).toBe("EL-2026-27-00123");
    render(
      <DocumentErpState
        document={{
          number: "EL/CN/2026-27/00004",
          kind: "credit_note",
          state: "failed",
          doctype: null,
          name: null,
          synced_at: null,
          outbox: [{ id: 1, event: "credit_note.issued", state: "failed", last_error: "ERPNext refused it." }],
        }}
      />,
    );
    expect(screen.getByRole("link", { name: "EL/CN/2026-27/00004" })).toHaveAttribute(
      "href",
      "/tax/documents/EL-CN-2026-27-00004/",
    );
    expect(screen.getByText("Failed: tried again")).toBeInTheDocument();
    expect(screen.getByText("credit_note.issued: failed, to be tried again")).toBeInTheDocument();
    expect(screen.getByText("ERPNext refused it.")).toBeInTheDocument();
  });
});

describe("the tabs and the rows", () => {
  it("opens the tabs the manifest allows", () => {
    expect(financeTabs(manifestWith([P.paymentsView])).map((tab) => tab.key)).toEqual([
      "today",
      "payments",
      "offline",
      "links",
    ]);
    expect(financeTabs(manifestWith([P.settlementsView])).map((tab) => tab.key)).toEqual(["settlements"]);
  });

  it("opens a payment, a settlement, a day's fetch and a B2B link from the inbox and the audit trail", () => {
    expect(targetHref("shop.payment", "9101")).toBe("/finance/payments/9101/");
    expect(targetHref("shop.settlement", "2")).toBe("/finance/settlements/2/");
    expect(targetHref("shop.settlement", "2026-10-09")).toBe(
      "/finance/settlements/?date_from=2026-10-09&date_to=2026-10-09",
    );
    expect(targetHref("shop.invoicepaymentlink", "2")).toBe("/finance/payment-links/?kind=invoice");
  });

  it("opens a waiting request's approval, and a refund's or a payment's order", () => {
    expect(requestHref({ kind: "request", id: 501, order: "EL-2026-000123" })).toBe("/approvals/501/");
    expect(requestHref({ kind: "refund", id: 71, order: "EL-2026-000137" })).toBe("/orders/EL-2026-000137/");
    expect(requestName({ kind: "request", id: 501 })).toBe("Change request #501");
    expect(requestName({ kind: "refund", id: 71 })).toBe("Refund #71");
  });
});

describe("payment links", () => {
  const link = (extra: Partial<FinanceLink>) =>
    ({ kind: "order", state: "sent", posted_at: null, ...extra }) as FinanceLink;
  const can =
    (...permissions: string[]) =>
    (permission: string) =>
      permissions.includes(permission);

  it("offers what the link's state allows, to whoever may do it", () => {
    expect(linkActions(link({}), can(P.ordersChange))).toEqual({
      send: true,
      cancel: true,
      ask: false,
      posted: false,
    });
    expect(linkActions(link({ state: "expired" }), can(P.ordersChange))).toEqual({
      send: false,
      cancel: false,
      ask: false,
      posted: false,
    });
    expect(linkActions(link({ kind: "invoice" }), can(P.ordersChange, P.reconcile)).ask).toBe(true);
    const paid = link({ kind: "invoice", state: "paid" });
    expect(linkActions(paid, can(P.reconcileSettlements)).posted).toBe(true);
    expect(linkActions({ ...paid, posted_at: "2026-10-09T10:00:00Z" }, can(P.reconcileSettlements)).posted).toBe(false);
    expect(linkActions(paid, can(P.ordersChange)).posted).toBe(false);
  });

  it("makes a B2B invoice's link and shows its address to send", async () => {
    const user = userEvent.setup();
    vi.mocked(askPaymentLink).mockResolvedValue({
      ...link({ kind: "invoice", invoice: "ACC-SINV-2026-00008", order: null }),
      url: "https://rzp.io/i/abc",
      detail: "Made: send its address to the customer.",
    } as never);
    render(<NewLinkForm />);
    await user.selectOptions(screen.getByLabelText("For"), "invoice");
    await user.type(screen.getByLabelText("Invoice's name in ERPNext"), "ACC-SINV-2026-00008");
    await user.click(screen.getByRole("button", { name: "Make the link" }));
    expect(askPaymentLink).toHaveBeenCalledWith({ invoice: "ACC-SINV-2026-00008", action: "send" });
    expect(await screen.findByText("Made: send its address to the customer.")).toBeInTheDocument();
    expect(screen.getByText("https://rzp.io/i/abc")).toBeInTheDocument();
  });
});

describe("Ask Razorpay again", () => {
  it("shows Razorpay's answer and what it changed", async () => {
    const user = userEvent.setup();
    vi.mocked(reconcileFinancePayment).mockResolvedValue({
      paid: true,
      detail: "Razorpay had the payment: the order is paid now.",
      changes: { order: ["pending", "paid"] },
      payment: {},
    } as never);
    render(<ReconcileButton payment={{ id: 9101 }} />);
    await user.click(screen.getByRole("button", { name: "Ask Razorpay again" }));
    expect(reconcileFinancePayment).toHaveBeenCalledWith(9101);
    expect(await screen.findByText("Razorpay had the payment: the order is paid now.")).toBeInTheDocument();
    expect(screen.getByText("order: pending to paid")).toBeInTheDocument();
    expect(navigation.router.refresh).toHaveBeenCalled();
  });
});

describe("settlement lines", () => {
  const line = (extra: Partial<FinanceSettlementLine>) =>
    ({
      id: 23,
      type: "payment",
      entity_id: "pay_mock138",
      amount: "729.00",
      matched: false,
      ...extra,
    }) as FinanceSettlementLine;
  const open = { id: 2, state: "mismatched" as const };

  it("checks the payment's number before asking, then sends it with the note", async () => {
    const user = userEvent.setup();
    vi.mocked(matchSettlementLine).mockResolvedValue({} as never);
    render(
      <ManifestProvider manifest={manifestWith([P.reconcileSettlements])}>
        <MatchLine settlement={open} line={line({})} />
      </ManifestProvider>,
    );
    await user.click(screen.getByRole("button", { name: "Match: pay_mock138" }));
    const dialog = screen.getByRole("dialog", { name: "Match line pay_mock138" });
    expect(within(dialog).getByText("The line is ₹729.")).toBeInTheDocument();
    await user.type(within(dialog).getByLabelText("Payment number"), "abc");
    await user.type(within(dialog).getByLabelText("Why"), "Its webhook was lost; Razorpay asked again.");
    await user.click(within(dialog).getByRole("button", { name: "Match" }));
    expect(matchSettlementLine).not.toHaveBeenCalled();
    expect((await within(dialog).findAllByText("A number, such as 123.")).length).toBeGreaterThan(0);
    await user.clear(within(dialog).getByLabelText("Payment number"));
    await user.type(within(dialog).getByLabelText("Payment number"), "#9101");
    await user.click(within(dialog).getByRole("button", { name: "Match" }));
    expect(matchSettlementLine).toHaveBeenCalledWith(2, {
      line: 23,
      payment: 9101,
      accept: false,
      note: "Its webhook was lost; Razorpay asked again.",
    });
  });

  it("accepts an adjustment as it is, and draws nothing for a matched line, a posted settlement or without the right", async () => {
    const user = userEvent.setup();
    vi.mocked(matchSettlementLine).mockResolvedValue({} as never);
    const { rerender } = render(
      <ManifestProvider manifest={manifestWith([P.reconcileSettlements])}>
        <MatchLine settlement={open} line={line({ id: 24, type: "adjustment", entity_id: "adj_1" })} />
      </ManifestProvider>,
    );
    await user.click(screen.getByRole("button", { name: "Accept: adj_1" }));
    const dialog = screen.getByRole("dialog");
    await user.type(within(dialog).getByLabelText("Why"), "Razorpay's fee reversal.");
    await user.click(within(dialog).getByRole("button", { name: "Accept" }));
    expect(matchSettlementLine).toHaveBeenCalledWith(2, { line: 24, accept: true, note: "Razorpay's fee reversal." });

    for (const [settlement, each, permissions] of [
      [open, line({ matched: true }), [P.reconcileSettlements]],
      [{ id: 1, state: "posted" as const }, line({}), [P.reconcileSettlements]],
      [open, line({}), [P.settlementsView]],
    ] as const) {
      rerender(
        <ManifestProvider manifest={manifestWith([...permissions])}>
          <MatchLine settlement={settlement} line={each} />
        </ManifestProvider>,
      );
      expect(screen.queryByRole("button", { name: /^(Match|Accept)/ })).not.toBeInTheDocument();
    }
  });

  it("reads a number as typed", () => {
    expect(idOf(" #123 ", "payment")).toBe(123);
    expect(() => idOf("0", "refund")).toThrow("A number, such as 123.");
    expect(() => idOf("12a", "refund")).toThrow();
  });
});

describe("a day fetched", () => {
  const job = (extra: Partial<Job>) =>
    ({
      id: 77,
      kind: "settlement_fetch",
      state: "done",
      dry_run: false,
      done: 1,
      total: 1,
      errors: [],
      result: {
        settlements: 2,
        new_settlements: 1,
        lines: 9,
        matched_lines: 8,
        orders_paid_now: 1,
        states: { matched: 1, mismatched: 1 },
      },
      ...extra,
    }) as Job;

  it("counts what the fetch found, and says when a dry run kept nothing", () => {
    const { rerender } = render(<FetchResult job={job({})} />);
    expect(screen.getByText("Lines matched").nextSibling).toHaveTextContent("8");
    expect(screen.getByText("Matched: 1 · Does not match: 1")).toBeInTheDocument();
    rerender(<FetchResult job={job({ dry_run: true })} />);
    expect(screen.getByText("A dry run: nothing was kept.")).toBeInTheDocument();
  });

  it("sends the day and the dry run, then shows the counts of a job already done", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchSettlements).mockResolvedValue(job({}));
    render(<FetchForm yesterday="2026-10-09" today="2026-10-10" />);
    expect(screen.getByLabelText("Day")).toHaveValue("2026-10-09");
    await user.click(screen.getByRole("checkbox", { name: "Dry run: keep nothing" }));
    await user.click(screen.getByRole("button", { name: "Fetch the day" }));
    expect(fetchSettlements).toHaveBeenCalledWith({ day: "2026-10-09", dry_run: true });
    expect(await screen.findByText("Orders marked paid")).toBeInTheDocument();
    expect(navigation.router.refresh).toHaveBeenCalled();
  });
});
