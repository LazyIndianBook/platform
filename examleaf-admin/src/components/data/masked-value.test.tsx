// Revealing a customer's contact: masked first, a reason asked for and sent with the reveal, the value for 60 seconds
// and then masked again by itself; the API's refusals said in the dialog; no Reveal at all without the permission.
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/errors";

import { MaskedValue } from "./masked-value";

afterEach(() => {
  vi.useRealTimers();
});

async function revealWith(reason: string) {
  fireEvent.click(screen.getByRole("button", { name: "Reveal email address" }));
  fireEvent.change(screen.getByLabelText("Reason"), { target: { value: reason } });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Reveal it" }));
  });
}

describe("MaskedValue", () => {
  it("shows the mask, asks why, reveals for 60 seconds, then masks again", async () => {
    vi.useFakeTimers();
    const reveal = vi.fn().mockResolvedValue("riya.das@example.com");
    render(<MaskedValue masked="r•••@example.com" what="email address" reveal={reveal} />);
    expect(screen.getByText("r•••@example.com")).toBeInTheDocument();
    await revealWith("Ticket 4412: the parent asked.");
    expect(reveal).toHaveBeenCalledWith("Ticket 4412: the parent asked.");
    expect(screen.getByText("riya.das@example.com")).toBeInTheDocument();
    expect(screen.getByText("Hidden again in 60 s")).toBeInTheDocument();
    // the same button now hides it, and the dialog gave the focus back to it
    expect(screen.getByRole("button", { name: "Hide now email address" })).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(30_000));
    expect(screen.getByText("Hidden again in 30 s")).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(31_000));
    expect(screen.queryByText("riya.das@example.com")).toBeNull();
    expect(screen.getByText("r•••@example.com")).toBeInTheDocument();
  });

  it("puts the API's field error beside the reason and keeps the dialog open", async () => {
    const reveal = vi
      .fn()
      .mockRejectedValue(new ApiError(400, "invalid", "Give a reason.", { reason: ["Give a reason."] }));
    render(<MaskedValue masked="r•••@example.com" what="email address" reveal={reveal} />);
    await revealWith("");
    expect(screen.getByRole("dialog", { name: "Reveal the email address?" })).toBeInTheDocument();
    expect(screen.getByLabelText("Reason")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("alert")).toHaveTextContent("Reason: Give a reason.");
    expect(screen.queryByText("riya.das@example.com")).toBeNull();
  });

  it("says when to try again after too many reveals", async () => {
    const reveal = vi.fn().mockRejectedValue(new ApiError(429, "throttled", "Request was throttled.", {}, null, 60));
    render(<MaskedValue masked="r•••@example.com" what="email address" reveal={reveal} />);
    await revealWith("Ticket 1");
    expect(screen.getByRole("alert")).toHaveTextContent(/Too many requests\. You can try again after \d\d:\d\d\./);
  });

  it("offers no Reveal when the manifest does not allow it, and says when there is nothing", () => {
    const { rerender } = render(<MaskedValue masked="r•••@example.com" what="email address" />);
    expect(screen.queryByRole("button")).toBeNull();
    rerender(<MaskedValue masked={null} what="mobile number" />);
    expect(screen.getByText("None on record")).toBeInTheDocument();
  });
});
