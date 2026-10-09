// A revision's review: a button for each move its `transitions` allow (none: said so), submitting in one press, a
// publish now or at a time read as India's, sending back with what to change.
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { type CourseRevision, moveRevision } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { navigation } from "@/test/navigation";

import { publishMoment, RevisionActions } from "./revision-actions";

vi.mock("@/lib/api/staff", async (original) => ({
  ...(await original<typeof import("@/lib/api/staff")>()),
  moveRevision: vi.fn(),
}));

const words = copy.course.revision;

const revision = (row: Partial<CourseRevision> = {}): CourseRevision => ({
  id: 402,
  chapter: { id: 302, number: 2, title: "Current electricity", subject: 1, subject_code: "PHY" },
  title: "Current electricity, the whole chapter",
  target_minutes: 12,
  status: "review",
  status_label: "in review",
  submitted_by: { id: 9004, name: "Meera Bora" },
  submitted_at: "2026-10-09T10:00:00Z",
  reviewer: null,
  publish_at: null,
  minutes: 6,
  clips: [],
  cards: 2,
  items: 4,
  transitions: [],
  created: "2026-09-01T10:00:00Z",
  modified: "2026-10-09T10:00:00Z",
  ...row,
});

const buttons = () => screen.queryAllByRole("button").map((button) => button.textContent);

beforeEach(() => {
  vi.mocked(moveRevision).mockReset();
  vi.mocked(moveRevision).mockResolvedValue({} as never);
  navigation.router.refresh = vi.fn();
});

describe("publishMoment", () => {
  it("is null for now, else the time typed in India", () => {
    expect(publishMoment("now", "2026-10-20T09:30")).toBeNull();
    expect(publishMoment("later", "")).toBeNull();
    expect(publishMoment("later", "2026-10-20T09:30")).toBe("2026-10-20T09:30:00+05:30");
  });
});

describe("RevisionActions", () => {
  it("says there is nothing to do when no move is the reader's", () => {
    render(<RevisionActions revision={revision()} />);
    expect(screen.getByText(words.noMoves)).toBeInTheDocument();
    expect(buttons()).toEqual([]);
  });

  it("draws the moves the API allows, in order", () => {
    render(
      <RevisionActions revision={revision({ transitions: ["approve", "needs_changes", "publish", "unpublish"] })} />,
    );
    expect(buttons()).toEqual([
      words.moves.approve,
      words.moves.publish,
      words.moves.needs_changes,
      words.moves.unpublish,
    ]);
  });

  it("submits a draft in one press", async () => {
    render(<RevisionActions revision={revision({ status: "draft", transitions: ["submit"] })} />);
    await userEvent.click(screen.getByRole("button", { name: words.moves.submit }));
    expect(moveRevision).toHaveBeenCalledWith(402, "submit", {});
    expect(navigation.router.refresh).toHaveBeenCalled();
  });

  it("publishes at a time to come, read as India's", async () => {
    render(<RevisionActions revision={revision({ status: "approved", transitions: ["publish"] })} />);
    await userEvent.click(screen.getByRole("button", { name: words.moves.publish }));
    const dialog = screen.getByRole("dialog");
    await userEvent.click(within(dialog).getByRole("radio", { name: words.later }));
    const at = within(dialog).getByLabelText(words.at);
    await userEvent.clear(at);
    await userEvent.type(at, "2026-10-20T09:30");
    await userEvent.click(within(dialog).getByRole("button", { name: words.moves.publish }));
    expect(moveRevision).toHaveBeenCalledWith(402, "publish", { publishAt: "2026-10-20T09:30:00+05:30" });
  });

  it("publishes now", async () => {
    render(<RevisionActions revision={revision({ transitions: ["publish"] })} />);
    await userEvent.click(screen.getByRole("button", { name: words.moves.publish }));
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: words.moves.publish }));
    expect(moveRevision).toHaveBeenCalledWith(402, "publish", { publishAt: undefined });
  });

  it("sends it back with what to change", async () => {
    render(<RevisionActions revision={revision({ transitions: ["needs_changes"] })} />);
    await userEvent.click(screen.getByRole("button", { name: words.moves.needs_changes }));
    const dialog = screen.getByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText(words.changesComment), "The second clip has no sound.");
    await userEvent.click(within(dialog).getByRole("button", { name: words.moves.needs_changes }));
    expect(moveRevision).toHaveBeenCalledWith(402, "needs_changes", { comment: "The second clip has no sound." });
  });
});
