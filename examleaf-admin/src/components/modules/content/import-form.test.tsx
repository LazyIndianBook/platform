// An import: the dry run first, its counts and the labels behind them, then Apply naming it (the subject and commit
// it ran with); the API's refusal beside its field; the test papers offered on a test site only.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ManifestProvider } from "@/components/shell/manifest";
import { ApiError } from "@/lib/api/errors";
import { type Job, startImport } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { P } from "@/lib/modules";
import { manifestWith } from "@/test/fixtures";
import { navigation } from "@/test/navigation";

import { ImportForm } from "./import-form";

vi.mock("@/lib/api/staff", async (original) => ({
  ...(await original<typeof import("@/lib/api/staff")>()),
  startImport: vi.fn(),
  getJob: vi.fn(),
}));

const words = copy.content.imports;

const job = (row: Partial<Job>): Job => ({
  id: 2801,
  kind: "content_import",
  state: "done",
  dry_run: true,
  params: { subject: "chemistry", commit: "", fixtures: false },
  done: 30,
  total: 30,
  errors: [],
  result: {
    subject: "chemistry",
    commit: "0e64cdf3a1b2c4d5e6f708192a3b4c5d6e7f8091",
    counts: { created: 0, updated: 2, unchanged: 1258, unmatched: 0, removed: 1 },
    rows: { updated: ["CHE-E01 1(a): solution", "CHE-M02 4: question"], removed: ["CHE-E05 4 OR: question"] },
  },
  result_url: null,
  change_request_id: null,
  cancel_requested: false,
  started_by: 7,
  created: "2026-10-09T10:00:00Z",
  started_at: "2026-10-09T10:00:00Z",
  finished_at: "2026-10-09T10:01:00Z",
  ...row,
});

function renderForm(testSite = true) {
  return render(
    <ManifestProvider manifest={manifestWith([P.papersView, P.contentImport], { flags: { test_mode: testSite } })}>
      <ImportForm />
    </ManifestProvider>,
  );
}

beforeEach(() => {
  vi.mocked(startImport).mockReset();
  navigation.router.refresh = vi.fn();
});

describe("ImportForm", () => {
  it("runs the dry run, shows what it found, then applies it by name", async () => {
    vi.mocked(startImport)
      .mockResolvedValueOnce(job({}) as never)
      .mockResolvedValueOnce(job({ id: 2802, dry_run: false }) as never);
    renderForm();
    await userEvent.selectOptions(screen.getByLabelText(words.subject), "chemistry");
    await userEvent.click(screen.getByRole("button", { name: words.dryRun }));
    expect(startImport).toHaveBeenCalledWith({ subject: "chemistry", commit: "" }, true);
    expect(screen.getByText(words.counts.updated).nextElementSibling).toHaveTextContent("2");
    expect(screen.getByText(words.counts.removed).nextElementSibling).toHaveTextContent("1");
    expect(screen.getByText("CHE-M02 4: question", { exact: true })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: words.apply }));
    expect(startImport).toHaveBeenLastCalledWith({ subject: "chemistry", commit: "", dry_run_job: 2801 }, false);
    expect(navigation.router.refresh).toHaveBeenCalled();
    expect(screen.getByRole("button", { name: words.apply })).toBeDisabled();
  });

  it("shows the API's refusal beside its field", async () => {
    vi.mocked(startImport).mockRejectedValueOnce(
      new ApiError(400, "invalid", "A commit's hash.", {
        "params.commit": ["A commit's hash: 7 to 40 of 0-9 and a-f; empty for the folder as it is."],
      }),
    );
    renderForm();
    await userEvent.type(screen.getByLabelText(new RegExp(`^${words.commit}`)), "not-a-commit");
    await userEvent.click(screen.getByRole("button", { name: words.dryRun }));
    expect(
      (await screen.findAllByText(/A commit's hash: 7 to 40 of 0-9 and a-f; empty for the folder as it is\./)).length,
    ).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: words.apply })).toBeNull();
  });

  it("offers the test papers on a test site only", () => {
    const { unmount } = renderForm(true);
    expect(screen.getByRole("checkbox", { name: words.fixtures })).toBeInTheDocument();
    unmount();
    renderForm(false);
    expect(screen.queryByRole("checkbox", { name: words.fixtures })).toBeNull();
  });
});
