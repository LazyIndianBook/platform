// The lookup box: a code answered in one line; a redeemed code's learner a link (never prefetched); an unused one voided
// once VOID is typed, with a reason, and looked up again; nothing to void without the permission.
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ManifestProvider } from "@/components/shell/manifest";
import { type CourseCodeLookup, lookUpCode, voidCode } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { P } from "@/lib/modules";
import { manifestWith } from "@/test/fixtures";

import { CodeLookup } from "./codes";

vi.mock("@/lib/api/staff", async (original) => ({
  ...(await original<typeof import("@/lib/api/staff")>()),
  lookUpCode: vi.fn(),
  voidCode: vi.fn(),
}));

const words = copy.course.codes;

const answer = (row: Partial<CourseCodeLookup>): CourseCodeLookup => ({
  state: "unused",
  line: "Not redeemed yet: batch PHY-2027-1 (Physics).",
  batch: "PHY-2027-1",
  batch_state: "dispatched",
  subject: "Physics",
  redeemed_at: null,
  voided_at: null,
  redeemed_by: null,
  ...row,
});

const renderLookup = (permissions: string[]) =>
  render(
    <ManifestProvider manifest={manifestWith(permissions)}>
      <CodeLookup />
    </ManifestProvider>,
  );

beforeEach(() => {
  vi.mocked(lookUpCode).mockReset();
  vi.mocked(voidCode).mockReset();
});

describe("CodeLookup", () => {
  it("answers a redeemed code in one line, its learner a link", async () => {
    vi.mocked(lookUpCode).mockResolvedValueOnce(
      answer({
        state: "redeemed",
        line: "Redeemed on 20 Sep 2026 by account #7101: batch PHY-2027-1 (Physics).",
        redeemed_at: "2026-09-20T10:00:00Z",
        redeemed_by: { id: 7101, email: "ri•••@example.com", is_minor: true },
      }),
    );
    renderLookup([P.bookCodesView, P.accessView]);
    await userEvent.type(screen.getByLabelText(words.codeField), "4hnc 8dve 2jys");
    await userEvent.click(screen.getByRole("button", { name: words.lookupButton }));
    expect(lookUpCode).toHaveBeenCalledWith("4hnc 8dve 2jys");
    expect(screen.getByText(/Redeemed on 20 Sep 2026 by account #7101/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: words.openLearner })).toHaveAttribute("href", "/course/learners/7101/");
    expect(screen.queryByRole("button", { name: words.voidCode })).not.toBeInTheDocument();
  });

  it("voids an unused code once VOID is typed, then looks it up again", async () => {
    vi.mocked(lookUpCode)
      .mockResolvedValueOnce(answer({}))
      .mockResolvedValueOnce(answer({ state: "void", line: "Void since 10 Oct 2026: batch PHY-2027-1 (Physics)." }));
    vi.mocked(voidCode).mockResolvedValueOnce({ id: 1, batch: "PHY-2027-1", voided_at: "2026-10-10T10:00:00Z" });
    renderLookup([P.bookCodesView, P.codesVoid]);
    await userEvent.type(screen.getByLabelText(words.codeField), "7KQM-3XPA-9TRW");
    await userEvent.click(screen.getByRole("button", { name: words.lookupButton }));
    await userEvent.click(screen.getByRole("button", { name: words.voidCode }));
    const dialog = screen.getByRole("dialog");
    const confirm = within(dialog).getByRole("button", { name: words.voidCode });
    await userEvent.type(within(dialog).getByLabelText(copy.common.reason), "The parent sent a photo of a torn page.");
    expect(confirm).toBeDisabled();
    await userEvent.type(within(dialog).getByLabelText(copy.confirmTyped.instruction(words.voidCodeTyped)), "VOID");
    await userEvent.click(confirm);
    expect(voidCode).toHaveBeenCalledWith("7KQM-3XPA-9TRW", "The parent sent a photo of a torn page.");
    expect(lookUpCode).toHaveBeenCalledTimes(2);
    expect(await screen.findByText(/Void since 10 Oct 2026/)).toBeInTheDocument();
  });

  it("offers no void without the permission", async () => {
    vi.mocked(lookUpCode).mockResolvedValueOnce(answer({}));
    renderLookup([P.bookCodesView]);
    await userEvent.type(screen.getByLabelText(words.codeField), "7KQM-3XPA-9TRW");
    await userEvent.click(screen.getByRole("button", { name: words.lookupButton }));
    expect(screen.getByText(/Not redeemed yet/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: words.voidCode })).not.toBeInTheDocument();
  });
});
