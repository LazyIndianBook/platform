// Logging a call or message: the docket is asked for a National Consumer Helpline complaint only, the body is what the
// API takes (received_at as India's time with its offset), and the new ticket opens once it is logged.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ManifestProvider } from "@/components/shell/manifest";
import { logTicket } from "@/lib/api/staff";
import { P } from "@/lib/modules";
import { manifestWith } from "@/test/fixtures";
import { navigation } from "@/test/navigation";

import { logBody, LogTicketForm } from "./log-form";

vi.mock("@/lib/api/staff", async (original) => ({
  ...(await original<typeof import("@/lib/api/staff")>()),
  logTicket: vi.fn(),
}));

const NOW = Date.parse("2026-10-09T06:30:00Z");

beforeEach(() => {
  vi.mocked(logTicket).mockReset();
  window.sessionStorage.clear();
});

describe("logBody", () => {
  it("is the API's body, the time received in India's time", () => {
    const form = new FormData();
    for (const [name, value] of Object.entries({
      source: "nch",
      nch_docket: " NCH/2026/1234567 ",
      name: "Hemanta",
      email: "",
      phone: "98640 12345",
      category: "",
      priority: "high",
      subject: "Forwarded by NCH",
      message: "The solutions do not open.",
      received_at: "2026-10-09T11:15",
      order: "",
    }))
      form.set(name, value);
    expect(logBody(form)).toEqual({
      source: "nch",
      nch_docket: "NCH/2026/1234567",
      name: "Hemanta",
      email: "",
      phone: "98640 12345",
      category: "",
      priority: "high",
      subject: "Forwarded by NCH",
      message: "The solutions do not open.",
      received_at: "2026-10-09T11:15:00+05:30",
      order: "",
    });
  });
});

describe("LogTicketForm", () => {
  it("asks for the docket for an NCH complaint only, and opens the new ticket", async () => {
    const push = vi.spyOn(navigation.router, "push");
    vi.mocked(logTicket).mockResolvedValue({ number: "SR-2026-000113" } as never);
    render(
      <ManifestProvider manifest={manifestWith([P.ticketsHandle])}>
        <LogTicketForm now={NOW} />
      </ManifestProvider>,
    );
    expect(screen.queryByLabelText("NCH docket")).toBeNull();
    expect(screen.getByLabelText("Received")).toHaveValue("2026-10-09T12:00");
    await userEvent.selectOptions(screen.getByLabelText("How it came"), "nch");
    await userEvent.type(screen.getByLabelText("NCH docket"), "NCH/2026/1234567");
    await userEvent.type(screen.getByLabelText(/^Mobile number/), "98640 12345");
    await userEvent.type(screen.getByLabelText("Subject"), "Forwarded by NCH");
    await userEvent.type(screen.getByLabelText("What they said or wrote"), "The solutions do not open.");
    await userEvent.click(screen.getByRole("button", { name: "Log it" }));
    expect(vi.mocked(logTicket).mock.calls[0][0]).toMatchObject({
      source: "nch",
      nch_docket: "NCH/2026/1234567",
      phone: "98640 12345",
    });
    expect(push).toHaveBeenCalledWith("/support/tickets/SR-2026-000113/");
    push.mockRestore();
  });
});
