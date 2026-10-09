// A ticket's forms: the status offers the API's moves and, for resolving or closing, only the fields its category asks
// for (and says what must come first); reopening is offered once it is resolved or closed; a correction sends only what
// changed, the masked contact details only when typed.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ManifestProvider } from "@/components/shell/manifest";
import { setTicketStatus } from "@/lib/api/staff";
import { P } from "@/lib/modules";
import { manifestWith } from "@/test/fixtures";
import { ticketWith } from "@/test/support";

import { changedDetails, StatusForm } from "./ticket";

vi.mock("@/lib/api/staff", async (original) => ({
  ...(await original<typeof import("@/lib/api/staff")>()),
  setTicketStatus: vi.fn(),
}));

const renderStatus = (ticket = ticketWith()) =>
  render(
    <ManifestProvider manifest={manifestWith([P.ticketsHandle])}>
      <StatusForm ticket={ticket} />
    </ManifestProvider>,
  );

beforeEach(() => {
  vi.mocked(setTicketStatus).mockReset();
  window.sessionStorage.clear();
});

describe("StatusForm", () => {
  it("offers the API's moves and asks, when closing, for what the category needs", async () => {
    vi.mocked(setTicketStatus).mockResolvedValue({} as never);
    renderStatus();
    const status = screen.getByLabelText("New status");
    expect([...status.querySelectorAll("option")].map((option) => option.textContent)).toEqual([
      "Choose",
      "Waiting on the customer",
      "Waiting on others",
      "Resolved",
      "Closed",
      "Spam",
    ]);
    expect(screen.queryByLabelText("What was done")).toBeNull();
    await userEvent.selectOptions(status, "resolved");
    await userEvent.type(screen.getByLabelText("What was done"), "Sent again by courier.");
    await userEvent.type(screen.getByLabelText("Order number"), "EL-2026-000130");
    expect(screen.queryByLabelText("Paper code")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Change the status" }));
    expect(setTicketStatus).toHaveBeenCalledWith("SR-2026-000101", {
      status: "resolved",
      resolution: "Sent again by courier.",
      order: "EL-2026-000130",
      record: "",
    });
  });

  it("asks for no order once one is linked, and says to sort an unsorted ticket first", async () => {
    renderStatus(ticketWith({ order: "EL-2026-000130", category: "", closing_fields: ["category", "resolution"] }));
    await userEvent.selectOptions(screen.getByLabelText("New status"), "closed");
    expect(screen.queryByLabelText("Order number")).toBeNull();
    expect(screen.getByText("Sort it first: choose its category under Sort and correct.")).toBeInTheDocument();
  });

  it("offers reopening once resolved, and nothing more once closed", () => {
    const { unmount } = renderStatus(ticketWith({ status: "resolved", transitions: ["closed"] }));
    expect(screen.getByRole("button", { name: "Reopen it" })).toBeInTheDocument();
    unmount();
    renderStatus(ticketWith({ status: "closed", transitions: [] }));
    expect(screen.queryByLabelText("New status")).toBeNull();
    expect(screen.getByText(/Closed: nothing follows/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reopen it" })).toBeInTheDocument();
  });
});

describe("changedDetails", () => {
  it("sends only what changed, and the contact details only when typed", () => {
    const ticket = ticketWith({ order: "EL-2026-000130" });
    const form = new FormData();
    for (const [name, value] of Object.entries({
      category: "payment",
      priority: "medium",
      language: "en",
      source: "form",
      nch_docket: "",
      subject: "Where is my order?",
      name: "Bikash Deka",
      order: "",
      record: "",
      email: "",
      phone: "98640 12345",
    }))
      form.set(name, value);
    expect(changedDetails(ticket, form)).toEqual({ category: "payment", order: "", phone: "98640 12345" });
  });
});
