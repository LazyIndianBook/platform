// The outline: a drop lands before or after the row it fell on (nothing when it would not move), "Move to…" sends
// the same move from the keyboard, a card's delete waits five seconds for Undo, a clip's asks for its title typed,
// and the buttons follow the manifest.
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ManifestProvider } from "@/components/shell/manifest";
import { type CourseOutline, deleteRow, moveRow } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { P } from "@/lib/modules";
import { manifestWith } from "@/test/fixtures";
import { navigation } from "@/test/navigation";

import { dropMove, Outline } from "./outline";

vi.mock("@/lib/api/staff", async (original) => ({
  ...(await original<typeof import("@/lib/api/staff")>()),
  moveRow: vi.fn(),
  deleteRow: vi.fn(),
}));

const words = copy.course;

const outline: CourseOutline = {
  subject: { id: 1, code: "PHY", name: "Physics" },
  completion_rule: "A clip counts as watched once 90% of it has played.",
  free_preview: true,
  chapters: [
    {
      id: 301,
      number: 1,
      title: "Electric charges",
      weight: "8.0",
      frequency: 14,
      must_do: "",
      revision: {
        id: 401,
        title: "Charges in 12 minutes",
        status: "review",
        target_minutes: 12,
        minutes: 9,
        publish_at: null,
        clips: [
          {
            id: 501,
            order: 1,
            title: "Coulomb's law",
            kind: "concept",
            duration: 185,
            processing: "ready",
            reason: "",
            is_free_preview: false,
            free: true,
          },
          {
            id: 502,
            order: 2,
            title: "Field lines",
            kind: "trick",
            duration: 0,
            processing: "failed",
            reason: "The video could not be read.",
            is_free_preview: false,
            free: false,
          },
          {
            id: 503,
            order: 3,
            title: "Gauss's law",
            kind: "shortcut",
            duration: 236,
            processing: "ready",
            reason: "",
            is_free_preview: false,
            free: false,
          },
        ],
      },
      cards: [
        { id: 601, order: 1, front: "Unit of charge?" },
        { id: 602, order: 2, front: "Coulomb's law?" },
      ],
      items: [{ id: 701, order: 1, kind: "mcq", text: "Two charges of 2 µC", difficulty: "easy", flagged: 9301 }],
    },
  ],
};

const renderOutline = (permissions: string[]) =>
  render(
    <ManifestProvider manifest={manifestWith(permissions)}>
      <Outline outline={outline} />
    </ManifestProvider>,
  );

beforeEach(() => {
  vi.mocked(moveRow).mockReset();
  vi.mocked(deleteRow).mockReset();
  navigation.router.refresh = vi.fn();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("dropMove", () => {
  const ids = [1, 2, 3];
  it.each([
    [1, 1, true, null],
    [1, 2, false, null],
    [2, 1, true, null],
    [4, 1, true, null],
    [1, 2, true, { to: "after", target: 2 }],
    [3, 1, false, { to: "before", target: 1 }],
    [1, 3, true, { to: "after", target: 3 }],
  ] as const)("dragging %s onto %s (after: %s) gives %j", (dragged, over, after, expected) => {
    expect(dropMove(ids, dragged, over, after)).toEqual(expected);
  });
});

describe("Outline", () => {
  it("draws the chapter's revision, its clips with their state, cards and items", () => {
    renderOutline([P.chaptersView]);
    expect(screen.getByText(words.outline.chapter(1, "Electric charges"))).toBeInTheDocument();
    expect(screen.getByText(words.outline.counts(3, 2, 1))).toBeInTheDocument();
    expect(screen.getByText("The video could not be read.")).toBeInTheDocument();
    expect(screen.getByText(words.outline.free)).toBeInTheDocument();
    expect(screen.getByText(words.outline.flagged)).toBeInTheDocument();
    // no permission to change: no move, no delete
    expect(screen.queryByRole("button", { name: /Move to/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Delete/ })).not.toBeInTheDocument();
  });

  it("moves a clip after another from the keyboard, as a drag would", async () => {
    vi.mocked(moveRow).mockResolvedValue({} as never);
    renderOutline([P.chaptersView, P.clipsChange]);
    await userEvent.click(screen.getByRole("button", { name: `${words.move.button}: Coulomb's law` }));
    const dialog = screen.getByRole("dialog");
    await userEvent.click(within(dialog).getByRole("radio", { name: words.move.places.after }));
    await userEvent.selectOptions(within(dialog).getByLabelText(words.move.target), "Gauss's law");
    await userEvent.click(within(dialog).getByRole("button", { name: words.move.submit }));
    expect(moveRow).toHaveBeenCalledWith("clips", 501, "after", 503);
    expect(navigation.router.refresh).toHaveBeenCalled();
  });

  it("moves a card first, with no sibling to name", async () => {
    vi.mocked(moveRow).mockResolvedValue({} as never);
    renderOutline([P.chaptersView, P.cardsChange]);
    await userEvent.click(screen.getByRole("button", { name: `${words.move.button}: Coulomb's law?` }));
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: words.move.submit }));
    expect(moveRow).toHaveBeenCalledWith("cards", 602, "first", null);
  });

  it("deletes a card after five seconds, unless undone", async () => {
    vi.useFakeTimers();
    vi.mocked(deleteRow).mockResolvedValue({} as never);
    renderOutline([P.chaptersView, P.cardsDelete]);
    fireEvent.click(screen.getByRole("button", { name: `${words.outline.deleteRow}: Unit of charge?` }));
    expect(screen.getByRole("status")).toHaveTextContent(words.outline.deletedNotice("Unit of charge?"));
    fireEvent.click(screen.getByRole("button", { name: words.outline.undo }));
    await vi.advanceTimersByTimeAsync(6000);
    expect(deleteRow).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: `${words.outline.deleteRow}: Coulomb's law?` }));
    await vi.advanceTimersByTimeAsync(5000);
    expect(deleteRow).toHaveBeenCalledWith("cards", 602);
  });

  it("deletes a clip only once its title is typed", async () => {
    vi.mocked(deleteRow).mockResolvedValue({} as never);
    renderOutline([P.chaptersView, P.clipsDelete]);
    await userEvent.click(screen.getByRole("button", { name: `${words.outline.deleteRow}: Gauss's law` }));
    const dialog = screen.getByRole("dialog");
    const confirm = within(dialog).getByRole("button", { name: words.clip.deleteButton });
    expect(confirm).toBeDisabled();
    await userEvent.type(within(dialog).getByRole("textbox"), "Gauss's law");
    await userEvent.click(confirm);
    expect(deleteRow).toHaveBeenCalledWith("clips", 503);
  });
});
