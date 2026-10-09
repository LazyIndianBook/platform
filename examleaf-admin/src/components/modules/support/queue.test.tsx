// The queue: each tab is the API's filters (the running tickets but in All), a tab's link keeps the list's filters
// (the status only in All) from the first page; a ticket's deadline counts down while it runs and says when it
// stopped and whether it was late; the status filter is All's, the test orders' filter a live site's.
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ManifestProvider } from "@/components/shell/manifest";
import { P } from "@/lib/modules";
import { manifestWith } from "@/test/fixtures";
import { ticketWith } from "@/test/support";

import { tabHref } from "./overview";
import { QueueClock, TicketQueue } from "./queue";
import { agentName, requesterLabel, tabFilters, tabOf } from "./shared";

const NOW = Date.parse("2026-10-20T06:30:00Z");

describe("the tabs", () => {
  it("are the API's filters, due soonest by default", () => {
    expect(tabOf("")).toBe("due");
    expect(tabOf("nonsense")).toBe("due");
    expect(tabFilters("due")).toEqual({ open: true });
    expect(tabFilters("mine")).toEqual({ mine: true, open: true });
    expect(tabFilters("unassigned")).toEqual({ unassigned: true, open: true });
    expect(tabFilters("overdue")).toEqual({ overdue: true });
    expect(tabFilters("waiting")).toEqual({ waiting: true });
    expect(tabFilters("all")).toEqual({});
  });

  it("keep the filters, the status in All only, and start from the first page", () => {
    const params = { q: "SR-2026-000101", category: "order", status: "spam", cursor: "cD0x", view: "4" };
    expect(tabHref("mine", params)).toBe("/support/?q=SR-2026-000101&category=order&tab=mine");
    expect(tabHref("all", params)).toBe("/support/?q=SR-2026-000101&category=order&status=spam&tab=all");
    expect(tabHref("due", {})).toBe("/support/");
  });
});

describe("the words", () => {
  it("name the requester and the staff as the API lets them", () => {
    expect(requesterLabel(ticketWith())).toBe("Bikash Deka");
    expect(requesterLabel(ticketWith({ requester: { name: "", email: "", phone: "••••••2345", user: null } }))).toBe(
      "••••••2345",
    );
    const agents = [{ id: 9003, name: "Rahul Saikia", handles: true }];
    expect(agentName(agents, null, 7)).toBe("No one");
    expect(agentName(agents, 7, 7)).toBe("You");
    expect(agentName(agents, 9003, 7)).toBe("Rahul Saikia");
    expect(agentName(null, 9005, 7)).toBe("Staff #9005");
  });
});

describe("QueueClock", () => {
  it("counts down a running deadline and says when it is late", () => {
    const late = ticketWith({ next_due_at: "2026-10-20T04:30:00Z", overdue: true });
    const { rerender } = render(<QueueClock ticket={late} now={NOW} />);
    expect(screen.getByText("overdue by 2 h 0 min")).toBeInTheDocument();
    rerender(<QueueClock ticket={ticketWith({ clock: "ack", next_due_at: "2026-10-20T09:00:00Z" })} now={NOW} />);
    expect(screen.getByText("2 h 30 min left")).toBeInTheDocument();
  });

  it("says when a stopped ticket stopped, and that it missed its deadline", () => {
    render(
      <QueueClock
        ticket={ticketWith({
          clock: null,
          status: "resolved",
          resolved_at: "2026-10-12T06:00:00Z",
          due_breached: true,
        })}
        now={NOW}
      />,
    );
    expect(screen.getByText(/Resolved 12 Oct 2026/)).toBeInTheDocument();
    expect(screen.getByText(/deadline missed/)).toBeInTheDocument();
  });
});

describe("TicketQueue", () => {
  const renderQueue = (tab: "due" | "all", flags: Record<string, unknown>) =>
    render(
      <ManifestProvider manifest={manifestWith([P.ticketsView], { flags })}>
        <TicketQueue
          rows={[ticketWith({ is_test: true })]}
          next={null}
          previous={null}
          views={null}
          tab={tab}
          agents={null}
          now={NOW}
        />
      </ManifestProvider>,
    );

  it("links each ticket by its number and marks a test order's", () => {
    renderQueue("due", { test_mode: true });
    const link = screen.getByRole("link", { name: /SR-2026-000101/ });
    expect(link).toHaveAttribute("href", "/support/tickets/SR-2026-000101/");
    expect(within(link).getByText("Test order")).toBeInTheDocument();
  });

  it("offers the status filter in All, and the test orders' filter on a live site only", () => {
    const { unmount } = renderQueue("due", { test_mode: true });
    expect(screen.queryByLabelText("Status")).toBeNull();
    expect(screen.queryByLabelText("Test orders")).toBeNull();
    unmount();
    renderQueue("all", {});
    expect(screen.getByLabelText("Status")).toBeInTheDocument();
    expect(screen.getByLabelText("Test orders")).toBeInTheDocument();
  });
});
