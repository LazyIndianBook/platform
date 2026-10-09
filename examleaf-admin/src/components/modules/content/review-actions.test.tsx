// A reviewer's decision: a publish with five seconds to undo it (the undo rolls the publish back), the page drawn again
// when the time is over; asking for changes; and whoever edited or submitted the draft decides nothing.
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ManifestProvider } from "@/components/shell/manifest";
import { type ContentReviewDetail, decideReview, draftAction } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { P } from "@/lib/modules";
import { manifestWith } from "@/test/fixtures";
import { navigation } from "@/test/navigation";

import { ReviewActions } from "./review-actions";

vi.mock("@/lib/api/staff", async (original) => ({
  ...(await original<typeof import("@/lib/api/staff")>()),
  decideReview: vi.fn(),
  draftAction: vi.fn(),
}));

const words = copy.content.reviews;

const review = (row: Partial<ContentReviewDetail> = {}): ContentReviewDetail => ({
  id: 2501,
  label: "PHY-E01 2(c), solution",
  kind: "solution",
  target_id: 2402,
  subject: "PHY",
  paper: 2201,
  stage: "check",
  state: "in_progress",
  assignee: null,
  submitted_by: 9004,
  edited_by: 9004,
  approved_by: null,
  approved_at: null,
  published_by: null,
  published_at: null,
  rolled_back_by: null,
  rolled_back_at: null,
  created: "2026-10-08T10:00:00Z",
  fields_changed: ["body_md"],
  yours: false,
  draft: { body_md: "$I = 0.50$ A" },
  previous: {},
  comments: [],
  changes: [],
  question: 2302,
  ...row,
});

function renderActions(row = review(), permissions = [P.reviewsView, P.papersPublish]) {
  return render(
    <ManifestProvider manifest={manifestWith(permissions)}>
      <ReviewActions review={row} />
    </ManifestProvider>,
  );
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.mocked(decideReview).mockReset();
  vi.mocked(draftAction).mockReset();
  navigation.router.refresh = vi.fn();
});

afterEach(() => {
  vi.useRealTimers();
});

/** The API's (mocked) answers taken in: the promises a click started, settled. */
async function answered() {
  for (let round = 0; round < 3; round++) await act(async () => {});
}

describe("ReviewActions", () => {
  it("publishes with five seconds to undo, and the undo rolls the publish back", async () => {
    vi.mocked(decideReview).mockResolvedValueOnce(review({ state: "approved" }) as never);
    vi.mocked(draftAction).mockResolvedValueOnce({} as never);
    renderActions();
    fireEvent.click(screen.getByRole("button", { name: words.publish }));
    await answered();
    expect(decideReview).toHaveBeenCalledWith(2501, "publish", "");
    expect(screen.getByText(words.undoLead(5))).toBeVisible();
    act(() => vi.advanceTimersByTime(2000));
    expect(screen.getByText(words.undoLead(3))).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: words.undo }));
    await answered();
    expect(draftAction).toHaveBeenCalledWith("solutions", 2402, "rollback");
    expect(screen.queryByText(words.undoLead(3))).toBeNull();
    expect(navigation.router.refresh).toHaveBeenCalled();
  });

  it("when the five seconds are over, the undo goes and the page is drawn again", async () => {
    vi.mocked(decideReview).mockResolvedValueOnce(review({ state: "approved" }) as never);
    renderActions();
    fireEvent.click(screen.getByRole("button", { name: words.publish }));
    await answered();
    expect(screen.getByRole("button", { name: words.undo })).toBeVisible();
    expect(navigation.router.refresh).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(5000));
    expect(screen.queryByRole("button", { name: words.undo })).toBeNull();
    expect(navigation.router.refresh).toHaveBeenCalled();
    expect(draftAction).not.toHaveBeenCalled();
  });

  it("asks for changes with the comment", async () => {
    vi.mocked(decideReview).mockResolvedValueOnce(review({ state: "needs_changes" }) as never);
    renderActions();
    fireEvent.change(screen.getByRole("textbox", { name: words.comment }), {
      target: { value: "Say which electrolyte." },
    });
    fireEvent.click(screen.getByRole("button", { name: words.needsChanges }));
    await answered();
    expect(decideReview).toHaveBeenCalledWith(2501, "needs-changes", "Say which electrolyte.");
    expect(navigation.router.refresh).toHaveBeenCalled();
  });

  it("offers no decision on one's own edit, nor to someone who may not publish", () => {
    const { unmount } = renderActions(review({ yours: true }));
    expect(screen.getByText(words.yours)).toBeVisible();
    expect(screen.queryByRole("button", { name: words.publish })).toBeNull();
    unmount();
    renderActions(review(), [P.reviewsView]);
    expect(screen.getByText(words.notYours)).toBeVisible();
    expect(screen.queryByRole("button", { name: words.publish })).toBeNull();
  });

  it("offers nothing on a review already published", () => {
    renderActions(review({ state: "approved", published_at: "2026-10-08T12:00:00Z" }));
    expect(screen.queryByRole("button")).toBeNull();
  });
});
