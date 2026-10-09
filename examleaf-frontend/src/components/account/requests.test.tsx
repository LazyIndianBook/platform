// My requests' form: what it is about, the subject, the message and the order (offered only when the account has
// orders) go to POST me/tickets/; the new request's number is said once it is made; the API's refusals stand beside
// their boxes or in the summary.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api/client";

import { RequestForm, TOPICS } from "./requests";

vi.mock("@/lib/api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/client")>()),
  api: { GET: vi.fn(), POST: vi.fn(), PATCH: vi.fn(), DELETE: vi.fn() },
}));

const answer = (status: number, body: unknown) =>
  (status < 300
    ? { data: body, response: new Response(null, { status }) }
    : { error: body, response: new Response(null, { status }) }) as never;

beforeEach(() => {
  vi.clearAllMocks();
});

describe("RequestForm", () => {
  it("sends the request and says its number", async () => {
    vi.mocked(api.POST).mockResolvedValue(answer(201, { number: "SR-2026-000114" }));
    render(<RequestForm orders={["EL-2026-000130", "EL-2026-000098"]} />);
    await userEvent.selectOptions(screen.getByLabelText(/What it is about/), "payment");
    await userEvent.selectOptions(screen.getByLabelText(/Order number/), "EL-2026-000130");
    await userEvent.type(screen.getByLabelText(/Subject/), "Refund not received");
    await userEvent.type(screen.getByLabelText(/Your message/), "I cancelled it a week ago.");
    await userEvent.click(screen.getByRole("button", { name: "Send the request" }));
    expect(api.POST).toHaveBeenCalledWith("/api/v1/me/tickets/", {
      body: {
        category: "payment",
        subject: "Refund not received",
        message: "I cancelled it a week ago.",
        order: "EL-2026-000130",
      },
    });
    expect(screen.getByText("We have your request SR-2026-000114.")).toBeInTheDocument();
    expect(screen.getByLabelText(/Subject/)).toHaveValue("");
  });

  it("offers no order without orders, and every topic the API takes", () => {
    render(<RequestForm orders={[]} />);
    expect(screen.queryByLabelText(/Order number/)).toBeNull();
    const topics = [...(screen.getByLabelText(/What it is about/) as HTMLSelectElement).options].map((o) => o.value);
    expect(topics).toEqual(TOPICS.map(([value]) => value));
  });

  it("puts the API's refusal beside its box", async () => {
    vi.mocked(api.POST).mockResolvedValue(answer(400, { subject: ["This field may not be blank."] }));
    render(<RequestForm orders={[]} />);
    await userEvent.click(screen.getByRole("button", { name: "Send the request" }));
    expect(screen.getByLabelText(/Subject/)).toHaveAttribute("aria-invalid", "true");
    expect(screen.queryByText(/We have your request/)).toBeNull();
  });

  it("says why when the email address is not confirmed yet", async () => {
    vi.mocked(api.POST).mockResolvedValue(
      answer(403, { detail: "Confirm your email address first.", code: "permission_denied" }),
    );
    render(<RequestForm orders={[]} />);
    await userEvent.type(screen.getByLabelText(/Subject/), "A question");
    await userEvent.type(screen.getByLabelText(/Your message/), "Hello.");
    await userEvent.click(screen.getByRole("button", { name: "Send the request" }));
    expect(screen.getByText("Confirm your email address first.")).toBeInTheDocument();
  });
});
