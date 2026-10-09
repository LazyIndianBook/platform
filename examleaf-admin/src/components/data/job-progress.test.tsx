// A job's progress keeps asking through no answer, a server error and a 429 (the job runs on: said, a 429 with when,
// and asked again 10 s later or after the wait given), and stops for good on any other refusal, telling onDone.
import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/errors";
import { getJob, type Job } from "@/lib/api/staff";
import { copy } from "@/lib/copy";

import { JobProgress } from "./job-progress";

vi.mock("@/lib/api/staff", async (original) => ({
  ...(await original<typeof import("@/lib/api/staff")>()),
  getJob: vi.fn(),
}));

const DONE: Job = { id: "41", state: "done", done: 2, total: 2, errors: [], result_url: null };
const later = async (ms: number) => act(async () => void (await vi.advanceTimersByTimeAsync(ms)));

beforeEach(() => {
  vi.useFakeTimers();
  vi.mocked(getJob).mockReset();
});
afterEach(() => vi.useRealTimers());

describe("JobProgress", () => {
  it("asks again after no answer and after a 429's wait, then shows the job", async () => {
    vi.mocked(getJob)
      .mockRejectedValueOnce(new ApiError(503, "server", copy.errors.unavailable))
      .mockRejectedValueOnce(new ApiError(429, "throttled", "Request was throttled.", {}, null, 30))
      .mockResolvedValueOnce(DONE);
    const onDone = vi.fn();
    render(<JobProgress jobId="41" onDone={onDone} />);
    await later(0);
    expect(screen.getByRole("alert")).toHaveTextContent(copy.errors.unavailable);

    await later(10_000); // asked again: a 429 this time, with when
    expect(getJob).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("alert")).toHaveTextContent(/You can try again after/);

    await later(29_000);
    expect(getJob).toHaveBeenCalledTimes(2); // the wait it was given, not sooner
    await later(1_000);
    expect(getJob).toHaveBeenCalledTimes(3);
    expect(onDone).toHaveBeenCalledWith(DONE);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("stops for good on a refusal, and onDone hears null", async () => {
    vi.mocked(getJob).mockRejectedValueOnce(new ApiError(404, "not_found", "We could not find that."));
    const onDone = vi.fn();
    render(<JobProgress jobId="41" onDone={onDone} />);
    await later(0);
    expect(onDone).toHaveBeenCalledWith(null);
    await later(60_000);
    expect(getJob).toHaveBeenCalledTimes(1);
  });
});
