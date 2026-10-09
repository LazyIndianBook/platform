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
    const { container } = gate({ break_glass: { reason_required: false }, policies_due: [] });
    expect(container).toBeEmptyDOMElement();
  });

  it("asks a break-glass session for its reason first, and keeps asking through Escape", async () => {
    vi.mocked(giveSessionReason).mockResolvedValueOnce(undefined);
    gate({
      break_glass: { reason_required: true },
      policies_due: [{ policy: "handbook", version: "2026-10", title: "The staff handbook" }],
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
    vi.mocked(acknowledgePolicy).mockResolvedValue(undefined);
    const policies = [
      { policy: "handbook", version: "2026-10", title: "The staff handbook", url: "https://examleaf.in/handbook/" },
      { policy: "privacy", version: "3", title: "Handling personal data" },
    ];
    gate({ policies_due: policies });
    expect(screen.getByRole("link", { name: /^Read The staff handbook/ })).toHaveAttribute(
      "href",
      "https://examleaf.in/handbook/",
    );
    await userEvent.click(screen.getByRole("button", { name: "I have read them and will follow them" }));
    expect(acknowledgePolicy).toHaveBeenCalledTimes(2);
    expect(acknowledgePolicy).toHaveBeenCalledWith(policies[1]);
    expect(refresh).toHaveBeenCalled();
  });
});
