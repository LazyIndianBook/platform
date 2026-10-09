"use client";

// A background job's progress (a bulk action, an export): asked every second, then every three, until it is done or
// failed; the bar always has its words beside it ("12 of 48 done"), the rows that failed are listed with the API's
// reason, and an export's file is a link. Screen readers hear the start and the end (a polite region), not each tick.
// No answer, a server error or too many asks: said (a 429 with when), and asked again 10 s later or after the wait
// given, as the job runs on regardless; any other refusal ends the asking, and onDone hears null.
import { useEffect, useRef, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Progress } from "@/components/ui/progress";
import { ApiError, errorText } from "@/lib/api/errors";
import { FINAL_JOB_STATES, getJob, type Job } from "@/lib/api/staff";
import { copy } from "@/lib/copy";

const AGAIN_S = 10;

export function JobProgress({ jobId, onDone }: { jobId: string; onDone?: (job: Job | null) => void }) {
  const [job, setJob] = useState<Job | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const finished = useRef(onDone);
  useEffect(() => {
    finished.current = onDone;
  });

  useEffect(() => {
    const controller = new AbortController();
    let tries = 0;
    let timer: ReturnType<typeof setTimeout>;
    const ask = async () => {
      try {
        const answer = await getJob(jobId, controller.signal);
        setJob(answer);
        setProblem(null);
        if (FINAL_JOB_STATES.has(answer.state)) {
          finished.current?.(answer);
          return;
        }
      } catch (error) {
        if (controller.signal.aborted) return;
        const problem = error instanceof ApiError ? error : new ApiError(0, "unavailable", copy.errors.unavailable);
        setProblem(errorText(problem));
        if (problem.unavailable || problem.status === 429)
          timer = setTimeout(ask, Math.max(problem.retryAfter ?? 0, AGAIN_S) * 1000);
        else finished.current?.(null); // refused for good (the job is gone, or not this person's)
        return;
      }
      tries += 1;
      timer = setTimeout(ask, tries < 5 ? 1000 : 3000);
    };
    ask();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [jobId]);

  const done = job ? FINAL_JOB_STATES.has(job.state) : false;
  const failed = job?.state === "failed";
  return (
    <div className="flex flex-col gap-3">
      <p className="sr-only" aria-live="polite">
        {done && job
          ? failed
            ? copy.bulk.jobFailed
            : copy.bulk.finished(job.done - job.errors.length, job.errors.length)
          : copy.bulk.started}
      </p>
      {problem ? (
        <Alert variant="error" role="alert" title={copy.errors.problem}>
          <p>{problem}</p>
        </Alert>
      ) : job ? (
        <Progress
          value={job.done}
          max={Math.max(job.total, 1)}
          name={copy.bulk.progressName}
          label={
            done
              ? failed
                ? copy.bulk.jobFailed
                : copy.bulk.finished(job.done - job.errors.length, job.errors.length)
              : copy.bulk.progress(job.done, job.total)
          }
        />
      ) : (
        <p className="m-0 text-[15px] text-muted-foreground">{copy.bulk.queued}</p>
      )}
      {job?.errors.length ? (
        <div className="flex flex-col gap-1.5">
          <p className="m-0 text-[15px] font-semibold">{copy.bulk.failedTitle}</p>
          <ul className="m-0 flex list-none flex-col gap-1 p-0 text-[15px]">
            {job.errors.map((row) => (
              <li key={row.id} className="border-l-2 border-destructive pl-3">
                <span className="font-semibold">{row.label}</span>: {row.message}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {done && job?.result_url ? (
        <p className="m-0">
          <a href={job.result_url} className="font-semibold" download>
            {copy.table.exportReady}
          </a>
        </p>
      ) : null}
    </div>
  );
}
