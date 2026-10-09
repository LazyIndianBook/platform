// Before anything else, what the manifest says the session owes: a break-glass account's reason (POST session/reason/),
// then the policies due (POST policies/ack/ each), each a modal that Escape does not close.
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { acknowledgePolicy, endOtherSessions, giveSessionReason, type Manifest } from "@/lib/api/staff";
import { manifestWith } from "@/test/fixtures";
import { navigation } from "@/test/navigation";

import { ManifestProvider } from "./manifest";
import { SessionGate } from "./session-gate";

vi.mock("@/lib/api/staff", async (original) => ({
  ...(await original<typeof import("@/lib/api/staff")>()),
  giveSessionReason: vi.fn(),
  acknowledgePolicy: vi.fn(),
  endOtherSessions: vi.fn(),
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
  vi.mocked(endOtherSessions).mockReset();
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

  it("sends a privileged role without a passkey to add one, and keeps asking until the manifest stops", async () => {
    gate({ steps: ["passkey_required"], policies_due: [{ policy: "acceptable_use", version: "2026-10" }] });
    const dialog = screen.getByRole("alertdialog", { name: "Add a passkey or a security key" });
    expect(screen.queryByText("Read and acknowledge")).toBeNull(); // the passkey first
    const link = screen.getByRole("link", { name: /Open the account page/ });
    expect(link).toHaveAttribute("href", expect.stringMatching(/\/account\/security\/$/));
    fireEvent(dialog, new Event("cancel", { cancelable: true }));
    expect(dialog).toHaveAttribute("open");
    await userEvent.click(screen.getByRole("button", { name: "I have added it" }));
    expect(refresh).toHaveBeenCalled(); // the manifest read again says whether it is done
  });

  it("offers once to end the other sessions after a second factor changed, and may be put off", async () => {
    vi.mocked(endOtherSessions).mockResolvedValueOnce({ sessions: 2, tokens: 1 });
    gate({ offer_end_sessions: true });
    expect(screen.getByRole("dialog", { name: "Your two-step sign-in changed" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "End the other sessions" }));
    expect(endOtherSessions).toHaveBeenCalledTimes(1);
    expect(refresh).toHaveBeenCalled();
    expect(screen.queryByRole("dialog", { name: "Your two-step sign-in changed" })).toBeNull();
  });
});
