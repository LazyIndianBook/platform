// The timeline and the spending summary on a customer's record. A timeline's rows link to the console's own pages only
// (a path from the API, never an address elsewhere); the kinds a role may not read are named, and are not offered; an
// address carries the kind and where the older rows begin. A child's spending is counts and nothing more: no money, no
// address, no tag, no forecast.
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { CustomerCommerce, TimelineRow } from "@/lib/api/staff";

import { CommerceSummary } from "./commerce";
import { safeHref, shownKinds, TimelineKinds, TimelineRows, timelineHref, withheldWords } from "./timeline";

const rows: TimelineRow[] = [
  {
    at: "2026-10-09T05:00:00Z",
    kind: "order",
    label: "Order EL-2026-000130: paid, ₹1,499",
    href: "/orders/EL-2026-000130/",
  },
  { at: "2026-10-08T05:00:00Z", kind: "sms", label: "SMS (order update): Sent, Delivered", href: null },
  {
    at: "2026-10-07T05:00:00Z",
    kind: "ticket",
    label: "Ticket SR-2026-000101: Order, Open",
    href: "https://elsewhere.example/x",
  },
];

describe("a timeline's rows", () => {
  it("link to the console's pages, and to nothing outside it", () => {
    expect(safeHref("/orders/EL-2026-000130/")).toBe("/orders/EL-2026-000130/");
    expect(safeHref("//elsewhere.example/x")).toBeNull();
    expect(safeHref("https://elsewhere.example/x")).toBeNull();
    expect(safeHref("javascript:alert(1)")).toBeNull();
    expect(safeHref(null)).toBeNull();
    render(<TimelineRows rows={rows} />);
    const table = screen.getByRole("region", { name: "The timeline" });
    expect(
      within(table)
        .getAllByRole("link")
        .map((link) => link.getAttribute("href")),
    ).toEqual(["/orders/EL-2026-000130/"]);
    expect(within(table).getByText("Ticket SR-2026-000101: Order, Open")).toBeVisible();
  });

  it("show the time, the kind in words and what happened", () => {
    render(<TimelineRows rows={rows} />);
    const first = screen.getAllByRole("row")[1];
    expect(within(first).getByText("Orders")).toBeVisible();
    expect(within(first).getByText("Order EL-2026-000130: paid, ₹1,499")).toBeVisible();
    expect(first.querySelector("time")).toHaveAttribute("datetime", "2026-10-09T05:00:00Z");
  });
});

describe("a timeline's address and kinds", () => {
  it("carries the kind and where the older rows begin, and nothing else", () => {
    expect(timelineHref(7102)).toBe("/users/7102/timeline/");
    expect(timelineHref(7102, { kind: "order" })).toBe("/users/7102/timeline/?kind=order");
    expect(timelineHref(7102, { kind: "order", before: "2026-10-01T10:00:00.000Z|order|9" })).toBe(
      "/users/7102/timeline/?kind=order&before=2026-10-01T10%3A00%3A00.000Z%7Corder%7C9",
    );
  });

  it("offers every kind but the ones the role may not read, and names those", () => {
    expect(shownKinds([])).toHaveLength(12);
    expect(shownKinds(["staff", "payment"])).not.toContain("staff");
    expect(withheldWords({ withheld: [] })).toBeNull();
    expect(withheldWords({ withheld: ["staff", "payment"] })).toBe(
      "Not shown to you, as your role does not read them: Payments, Staff actions.",
    );
    render(<TimelineKinds id={7102} current="order" withheld={["staff"]} />);
    const nav = screen.getByRole("navigation", { name: "Show" });
    expect(within(nav).getByRole("link", { name: "Orders" })).toHaveAttribute("aria-current", "page");
    expect(within(nav).getByRole("link", { name: "Everything" })).toHaveAttribute("href", "/users/7102/timeline/");
    expect(within(nav).queryByRole("link", { name: "Staff actions" })).toBeNull();
  });
});

const adult: CustomerCommerce = {
  child: false,
  orders: 4,
  kept: 3,
  cancelled: 1,
  returns: 1,
  rtos: 0,
  spent: "3048.00",
  refunded: "670.00",
  lifetime_value: "2378.00",
  average_order: "1016.00",
  first_order_at: "2026-09-01T05:00:00Z",
  last_order_at: "2026-10-09T05:00:00Z",
  addresses: [
    { city: "Guwahati", district: "Kamrup Metro", state: "AS", pin: "781005", phone: "••••••1873", is_default: true },
  ],
  tags: [{ name: "school", orders: 1 }],
};

describe("the spending summary", () => {
  it("gives an adult the counts, the money, the dates, the masked addresses and the tags", () => {
    render(<CommerceSummary commerce={adult} />);
    expect(screen.getByText("₹3,048")).toBeVisible();
    expect(screen.getByText("₹2,378")).toBeVisible();
    expect(screen.getByText("Spent less refunded")).toBeVisible();
    expect(screen.getByText("Guwahati, Kamrup Metro, AS, 781005")).toBeVisible();
    expect(screen.getByText("••••••1873")).toBeVisible();
    expect(screen.getByText("school: 1")).toBeVisible();
  });

  it("gives a child the counts alone, and says so", () => {
    render(
      <CommerceSummary
        commerce={{
          ...adult,
          child: true,
          spent: null,
          refunded: null,
          lifetime_value: null,
          average_order: null,
          first_order_at: null,
          last_order_at: null,
          addresses: null,
          tags: null,
        }}
      />,
    );
    expect(screen.getByText("A student under 18: the counts only.")).toBeVisible();
    expect(screen.queryByText("Spent")).toBeNull();
    expect(screen.queryByText("Saved addresses")).toBeNull();
    expect(screen.queryByText(/₹/)).toBeNull();
  });

  it("says when there is no order, and works out nothing of its own", () => {
    render(<CommerceSummary commerce={{ ...adult, orders: 0, kept: 0, cancelled: 0, returns: 0, spent: "0.00" }} />);
    expect(screen.getByText("No order yet.")).toBeVisible();
    expect(screen.queryByText(/forecast|score|likely/i)).toBeNull();
  });
});
