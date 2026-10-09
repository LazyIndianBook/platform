// The saved replies: a delete puts one in the bin with Undo for 5 seconds (Undo restores it), the bin restores the
// older ones, and the changes are drawn only for whoever may make them.
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ManifestProvider } from "@/components/shell/manifest";
import { deleteSavedReply, restoreSavedReply, type SavedReply } from "@/lib/api/staff";
import { P } from "@/lib/modules";
import { manifestWith } from "@/test/fixtures";

import { SavedReplies, UNDO_SECONDS } from "./replies";

vi.mock("@/lib/api/staff", async (original) => ({
  ...(await original<typeof import("@/lib/api/staff")>()),
  deleteSavedReply: vi.fn(),
  restoreSavedReply: vi.fn(),
}));

const reply = (row: Partial<SavedReply> = {}): SavedReply => ({
  id: 61,
  title: "Refund timeline",
  language: "en",
  body: "Dear {name|there}, the refund for {order} takes {refund_days|5 to 7} days.",
  variables: ["name", "order", "refund_days"],
  created_by: 7,
  created: "2026-08-01T06:00:00Z",
  modified: "2026-09-01T06:00:00Z",
  deleted_at: null,
  ...row,
});

const ALL = [P.repliesView, P.repliesAdd, P.repliesChange, P.repliesDelete];
const renderReplies = (permissions: string[], bin: SavedReply[] | null = []) =>
  render(
    <ManifestProvider manifest={manifestWith(permissions)}>
      <SavedReplies replies={[reply()]} bin={bin} />
    </ManifestProvider>,
  );

beforeEach(() => {
  vi.mocked(deleteSavedReply).mockReset();
  vi.mocked(restoreSavedReply).mockReset();
  window.sessionStorage.clear();
});
afterEach(() => {
  vi.useRealTimers();
});

describe("SavedReplies", () => {
  it("shows each reply's variables, and only reading for whoever may only read", () => {
    renderReplies([P.repliesView], null);
    expect(screen.getByText("{name} {order} {refund_days}")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Delete/ })).toBeNull();
    expect(screen.queryByText("Edit")).toBeNull();
    expect(screen.queryByRole("heading", { name: "Add a saved reply" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Deleted in the last 30 days" })).toBeNull();
  });

  it("puts a deleted reply in the bin with Undo, which restores it", async () => {
    vi.mocked(deleteSavedReply).mockResolvedValue(undefined as never);
    vi.mocked(restoreSavedReply).mockResolvedValue(reply() as never);
    renderReplies(ALL);
    await userEvent.click(screen.getByRole("button", { name: "Delete: Refund timeline" }));
    expect(deleteSavedReply).toHaveBeenCalledWith(61);
    expect(screen.getByRole("status")).toHaveTextContent("Refund timeline is in the bin.");
    await userEvent.click(screen.getByRole("button", { name: "Undo" }));
    expect(restoreSavedReply).toHaveBeenCalledWith(61);
    expect(screen.queryByRole("button", { name: "Undo" })).toBeNull();
  });

  it(`takes Undo away after ${UNDO_SECONDS} seconds`, async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.mocked(deleteSavedReply).mockResolvedValue(undefined as never);
    renderReplies(ALL);
    await userEvent.click(screen.getByRole("button", { name: "Delete: Refund timeline" }));
    expect(screen.getByRole("button", { name: "Undo" })).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(UNDO_SECONDS * 1000));
    expect(screen.queryByRole("button", { name: "Undo" })).toBeNull();
  });

  it("restores an older one from the bin", async () => {
    vi.mocked(restoreSavedReply).mockResolvedValue(reply({ id: 65 }) as never);
    renderReplies(ALL, [reply({ id: 65, title: "Old courier", deleted_at: "2026-10-06T06:00:00Z" })]);
    await userEvent.click(screen.getByRole("button", { name: "Restore: Old courier" }));
    expect(restoreSavedReply).toHaveBeenCalledWith(65);
  });
});
