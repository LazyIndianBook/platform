// A background job as the API answers it: waiting for an approval (its change request linked), running, done with its
// file fetched through a fresh link (the job read again: result_url's token lasts 5 minutes), cancelled, and its
// starter's Cancel.
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/errors";
import { cancelJob, getJob, type Job, jobFileHref } from "@/lib/api/staff";
import { copy } from "@/lib/copy";

import { JobProgress } from "./job-progress";

vi.mock("@/lib/api/staff", async (original) => ({
  ...(await original<typeof import("@/lib/api/staff")>()),
  getJob: vi.fn(),
  cancelJob: vi.fn(),
  jobFileHref: vi.fn(),
}));

const job = (row: Partial<Job>): Job => ({
  id: 702,
  kind: "audit_export",
  state: "queued",
  dry_run: false,
  params: { filters: {} },
  done: 0,
  total: 120,
  errors: [],
  result: {},
  result_url: null,
  change_request_id: null,
  cancel_requested: false,
  started_by: 7,
  created: "2026-10-09T10:00:00Z",
  started_at: null,
  finished_at: null,
  ...row,
});

beforeEach(() => {
  vi.mocked(getJob).mockReset();
  vi.mocked(cancelJob).mockReset();
});

describe("JobProgress", () => {
  it("says which approval a queued job waits for, and cancels it", async () => {
    vi.mocked(getJob).mockResolvedValue(job({ change_request_id: 508 }));
    vi.mocked(cancelJob).mockResolvedValueOnce(job({ state: "cancelled", cancel_requested: true }));
    render(<JobProgress job={job({ change_request_id: 508 })} />);
    expect(screen.getByRole("progressbar")).toHaveAttribute(
      "aria-valuetext",
      "Waiting for a second person to approve it: change request 508.",
    );
    expect(screen.getByRole("link", { name: /^Open the change request/ })).toHaveAttribute("href", "/approvals/508/");
    await userEvent.click(screen.getByRole("button", { name: "Cancel the job" }));
    expect(cancelJob).toHaveBeenCalledWith(702);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuetext", "Cancelled: it stopped where it was.");
    expect(screen.queryByRole("button", { name: "Cancel the job" })).toBeNull();
  });

  it("downloads a done job's file through a fresh link on this origin", async () => {
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign });
    vi.mocked(jobFileHref).mockResolvedValueOnce("/api/v1/staff/jobs/702/result/?token=fresh");
    render(<JobProgress job={job({ state: "done", done: 120, result_url: "https://admin.examleaf.in/old" })} />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuetext", "All done");
    await userEvent.click(screen.getByRole("button", { name: "Download the file" }));
    await waitFor(() => expect(assign).toHaveBeenCalledWith("/api/v1/staff/jobs/702/result/?token=fresh"));
    expect(jobFileHref).toHaveBeenCalledWith(702);
    vi.unstubAllGlobals();
  });

  it("lists the rows that failed, and never offers to cancel what has finished", () => {
    render(
      <JobProgress
        job={job({
          kind: "bulk_action",
          state: "done",
          done: 2,
          total: 2,
          errors: [{ id: "EL-NOPE", label: "EL-NOPE", message: "No such order." }],
        })}
      />,
    );
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuetext", "Done: 1, 1 row failed");
    expect(screen.getByText("EL-NOPE")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel the job" })).toBeNull();
  });
});

// the job runs on whatever its progress hears: no answer, a server error and a 429 are said and asked again (10 s
// later, or after the wait given); any other refusal stops the asking and tells onDone
describe("JobProgress when the API does not answer", () => {
  const later = async (ms: number) => act(async () => void (await vi.advanceTimersByTimeAsync(ms)));
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("asks again after no answer and after a 429's wait, then shows the job", async () => {
    const done = job({ state: "done", done: 120 });
    vi.mocked(getJob)
      .mockRejectedValueOnce(new ApiError(503, "server", copy.errors.unavailable))
      .mockRejectedValueOnce(new ApiError(429, "throttled", "Request was throttled.", {}, null, 30))
      .mockResolvedValueOnce(done);
    const onDone = vi.fn();
    render(<JobProgress job={job({ state: "running", done: 3 })} onDone={onDone} />);
    await later(1_000);
    expect(screen.getByRole("alert")).toHaveTextContent(copy.errors.unavailable);

    await later(10_000); // asked again: a 429 this time, with when
    expect(getJob).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("alert")).toHaveTextContent(/You can try again after/);
    await later(29_000);
    expect(getJob).toHaveBeenCalledTimes(2); // the wait it was given, not sooner
    await later(1_000);
    expect(getJob).toHaveBeenCalledTimes(3);
    expect(onDone).toHaveBeenCalledWith(done);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("stops for good on a refusal, and onDone hears null", async () => {
    vi.mocked(getJob).mockRejectedValueOnce(new ApiError(404, "not_found", "We could not find that."));
    const onDone = vi.fn();
    render(<JobProgress job={job({ state: "running" })} onDone={onDone} />);
    await later(1_000);
    expect(onDone).toHaveBeenCalledWith(null);
    await later(60_000);
    expect(getJob).toHaveBeenCalledTimes(1);
  });
});
