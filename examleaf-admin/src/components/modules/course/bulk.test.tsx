// A bulk action of the course: the dry run first (nothing changed; what can be done and what would be refused), then
// Apply with the same rows, payload and reason; the page read again once applied.
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { type Job, startCourseBulk } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { navigation } from "@/test/navigation";

import { BulkDialog, outcomeLine } from "./bulk";

vi.mock("@/lib/api/staff", async (original) => ({
  ...(await original<typeof import("@/lib/api/staff")>()),
  startCourseBulk: vi.fn(),
  getJob: vi.fn(),
}));

const words = copy.course.bulk;

const job = (row: Partial<Job>): Job => ({
  id: 3101,
  kind: "bulk_action",
  state: "done",
  dry_run: true,
  params: {},
  done: 2,
  total: 2,
  errors: [],
  result: {},
  result_url: null,
  change_request_id: null,
  cancel_requested: false,
  started_by: 7,
  created: "2026-10-09T10:00:00Z",
  started_at: "2026-10-09T10:00:00Z",
  finished_at: "2026-10-09T10:00:01Z",
  ...row,
});

beforeEach(() => {
  vi.mocked(startCourseBulk).mockReset();
  navigation.router.refresh = vi.fn();
});

describe("outcomeLine", () => {
  it("says each outcome in words, the empty ones left out", () => {
    expect(outcomeLine({ outcomes: { valid: 3, refused: 1 } })).toBe("3 can be done, 1 refused");
    expect(outcomeLine({ outcomes: { executed: 2, pending: 0 } })).toBe("2 done");
    expect(outcomeLine({})).toBe(words.none);
  });
});

describe("BulkDialog", () => {
  it("checks the rows first, then applies the same change", async () => {
    const applied = vi.fn();
    vi.mocked(startCourseBulk)
      .mockResolvedValueOnce(
        job({
          result: { outcomes: { valid: 1, refused: 1 } },
          errors: [{ id: 702, label: "702", message: "One of easy, medium, hard, or empty (not set)." }],
        }),
      )
      .mockResolvedValueOnce(job({ dry_run: false, result: { outcomes: { executed: 1 } } }));
    render(
      <BulkDialog
        action="item_metadata"
        targets={[701, 702]}
        triggerLabel="Change 2 items"
        title="Change the metadata of 2 items"
        lead="Only the fields you fill in change."
        build={() => ({ payload: { marks: 2 } })}
        onApplied={applied}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Change 2 items" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText(copy.common.reason), "Board marking scheme");
    await userEvent.click(within(dialog).getByRole("button", { name: words.dryRun }));
    expect(startCourseBulk).toHaveBeenCalledWith(
      "item_metadata",
      [701, 702],
      { marks: 2 },
      "Board marking scheme",
      true,
    );
    expect(within(dialog).getByText(words.checked("1 can be done, 1 refused"))).toBeInTheDocument();
    expect(within(dialog).getByText(/One of easy, medium, hard/)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: words.apply }));
    expect(startCourseBulk).toHaveBeenLastCalledWith(
      "item_metadata",
      [701, 702],
      { marks: 2 },
      "Board marking scheme",
      false,
    );
    expect(applied).toHaveBeenCalled();
    expect(navigation.router.refresh).toHaveBeenCalled();
  });

  it("offers no Apply when every row would be refused", async () => {
    vi.mocked(startCourseBulk).mockResolvedValueOnce(job({ result: { outcomes: { refused: 2 } } }));
    render(
      <BulkDialog
        action="entitlement.revoke"
        targets={[801, 802]}
        triggerLabel="Revoke 2"
        title="Revoke access of 2"
        lead="Access ends today."
        build={() => ({ payload: {} })}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Revoke 2" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText(copy.common.reason), "Refunded");
    await userEvent.click(within(dialog).getByRole("button", { name: words.dryRun }));
    expect(within(dialog).getByText(words.checked("2 refused"))).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: words.apply })).not.toBeInTheDocument();
  });
});
