// Before anything else, what the manifest says the session owes: a break-glass account's reason (POST session/reason/),
// then the policies due (POST policies/ack/ each), each a modal that Escape does not close.
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { acknowledgePolicy, giveSessionReason, type Manifest } from "@/lib/api/staff";
import { manifestWith } from "@/test/fixtures";
import { navigation } from "@/test/navigation";

import { ManifestProvider } from "./manifest";
import { SessionGate } from "./session-gate";

vi.mock("@/lib/api/staff", async (original) => ({
  ...(await original<typeof import("@/lib/api/staff")>()),
  giveSessionReason: vi.fn(),
  acknowledgePolicy: vi.fn(),
}));

const ends_at = "2026-10-09T12:00:00Z"; // the break-glass box's end

const gate = (extra: Partial<Manifest>) =>
  render(
    <ManifestProvider manifest={manifestWith([], extra)}>
      <SessionGate />
    </ManifestProvider>,
  );

let refresh = vi.fn<() => void>();
beforeEach(() => {
  refresh = vi.fn<() => void>();
  navigation.router.refresh = refresh;
  vi.mocked(giveSessionReason).mockReset();
  vi.mocked(acknowledgePolicy).mockReset();
});

describe("SessionGate", () => {
  it("draws nothing when nothing is owed", () => {
    const { container } = gate({
      break_glass: { reason_required: false, reason: "Lost phone.", ends_at },
      policies_due: [],
    });
    expect(container).toBeEmptyDOMElement();
  });

  it("asks a break-glass session for its reason first, and keeps asking through Escape", async () => {
    vi.mocked(giveSessionReason).mockResolvedValueOnce({} as never);
    gate({
      break_glass: { reason_required: true, reason: null, ends_at },
      policies_due: [{ policy: "acceptable_use", version: "2026-10" }],
    });
    const dialog = screen.getByRole("alertdialog", { name: "Why is a break-glass account needed?" });
    expect(screen.queryByText("Read and acknowledge")).toBeNull();
    fireEvent(dialog, new Event("cancel", { cancelable: true }));
    expect(dialog).toHaveAttribute("open");
    await userEvent.type(screen.getByLabelText("Reason"), "The owner's phone is lost and the shop is down.");
    await userEvent.click(screen.getByRole("button", { name: "Give the reason" }));
    expect(giveSessionReason).toHaveBeenCalledWith("The owner's phone is lost and the shop is down.");
    expect(refresh).toHaveBeenCalled();
  });

  it("then asks for each policy due to be acknowledged", async () => {
    vi.mocked(acknowledgePolicy).mockResolvedValue({} as never);
    const policies = [
      { policy: "acceptable_use", version: "2026-10" },
      { policy: "childrens_data", version: "3" },
    ];
    gate({ policies_due: policies });
    expect(screen.getByText("Acceptable use")).toBeInTheDocument(); // STAFF_POLICIES' key, as words
    expect(screen.getByText("(version 3)")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "I have read them and will follow them" }));
    expect(acknowledgePolicy).toHaveBeenCalledTimes(2);
    expect(acknowledgePolicy).toHaveBeenCalledWith(policies[1]);
    expect(refresh).toHaveBeenCalled();
  });
});
