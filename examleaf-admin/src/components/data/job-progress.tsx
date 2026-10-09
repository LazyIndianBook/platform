"use client";

// A background job's progress (an export, a bulk action; GET jobs/{id}/): asked every second, then every three, while
// the tab is in view, until it is done, failed or cancelled; the bar always has its words beside it ("12 of 48 done"),
// the rows that failed are listed with the API's reason, a job waiting for an approval says which change request, and
// its starter may cancel it while it waits or runs (POST jobs/{id}/cancel/). Its file is fetched through a fresh link
// each time (the job read again: its result_url's token lasts 5 minutes). Screen readers hear the start and the end
// (a polite region), not each tick. No answer, a server error or too many asks: said (a 429 with when), and asked
// again 10 s later or after the wait given, as the job runs on regardless; any other refusal ends the asking, and
// onDone hears null.
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { useAction } from "@/components/forms/use-action";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { ApiError, errorText } from "@/lib/api/errors";
import { cancelJob, FINAL_JOB_STATES, getJob, type Job, jobFileHref } from "@/lib/api/staff";
import { copy } from "@/lib/copy";

const AGAIN_S = 10;

/** Its file: a fresh link from the job, opened on this origin (the browser downloads it). */
export function DownloadJobFile({ job }: { job: Pick<Job, "id"> }) {
  const { run, busy, error } = useAction();
  const [gone, setGone] = useState(false);
  return (
    <span className="inline-flex flex-wrap items-center gap-3">
      <Button
        variant="secondary"
        size="sm"
        busy={busy}
        onClick={() =>
          run(async () => {
            const href = await jobFileHref(job.id);
            if (href) window.location.assign(href);
            else setGone(true);
          })
        }
      >
        {copy.jobs.download}
      </Button>
      {gone ? <span className="text-sm text-muted-foreground">{copy.jobs.gone}</span> : null}
      {error ? <span className="text-sm font-semibold text-destructive">{errorText(error)}</span> : null}
    </span>
  );
}

/** What a job says about itself, in words. */
export function jobWords(job: Job): string {
  if (job.state === "failed") return copy.jobs.jobFailed;
  if (job.state === "cancelled") return copy.jobs.jobCancelled;
  if (job.state === "done") return copy.jobs.finished(job.done - job.errors.length, job.errors.length);
  if (job.state === "queued" && job.change_request_id) return copy.jobs.awaiting(String(job.change_request_id));
  if (job.state === "queued") return copy.jobs.queued;
  return copy.jobs.progress(job.done, job.total);
}

export function JobProgress({ job: first, onDone }: { job: Job; onDone?: (job: Job | null) => void }) {
  const [job, setJob] = useState<Job>(first);
  const [problem, setProblem] = useState<string | null>(null);
  const cancelling = useAction();
  const finished = useRef(onDone);
  useEffect(() => {
    finished.current = onDone;
  });

  const id = first.id;
  useEffect(() => {
    const controller = new AbortController();
    let tries = 0;
    let timer: ReturnType<typeof setTimeout>;
    const ask = async () => {
      if (!document.hidden) {
        try {
          const answer = await getJob(id, controller.signal);
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
      }
      tries += 1;
      timer = setTimeout(ask, tries < 5 ? 1000 : 3000);
    };
    if (FINAL_JOB_STATES.has(first.state)) return;
    timer = setTimeout(ask, 1000);
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [id, first.state]);

  const done = FINAL_JOB_STATES.has(job.state);
  return (
    <div className="flex flex-col gap-3">
      <p className="sr-only" aria-live="polite">
        {done ? jobWords(job) : copy.jobs.started}
      </p>
      {problem ? (
        <Alert variant="error" role="alert" title={copy.errors.problem}>
          <p>{problem}</p>
        </Alert>
      ) : (
        <Progress value={job.done} max={Math.max(job.total, 1)} name={copy.jobs.progressName} label={jobWords(job)} />
      )}
      {job.state === "queued" && job.change_request_id ? (
        <p className="m-0">
          <Link href={`/approvals/${job.change_request_id}/`} className="font-semibold">
            {copy.approval.open}
            <span className="sr-only">: {copy.approval.number(String(job.change_request_id))}</span>
          </Link>
        </p>
      ) : null}
      {job.errors.length ? (
        <div className="flex flex-col gap-1.5">
          <p className="m-0 text-[15px] font-semibold">{copy.jobs.failedTitle}</p>
          <ul className="m-0 flex list-none flex-col gap-1 p-0 text-[15px]">
            {job.errors.map((row, index) => (
              <li key={`${String(row.id)}-${index}`} className="border-l-2 border-destructive pl-3">
                <span className="font-semibold">{row.label}</span>: {row.message}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <div className="flex flex-wrap items-center gap-3">
        {job.state === "done" && job.result_url ? <DownloadJobFile job={job} /> : null}
        {!done && !job.cancel_requested ? (
          <Button
            variant="ghost"
            size="sm"
            busy={cancelling.busy}
            onClick={() => cancelling.run(async () => setJob(await cancelJob(job.id)))}
          >
            {copy.jobs.cancel}
          </Button>
        ) : null}
        {cancelling.error ? (
          <span className="text-sm font-semibold text-destructive">{errorText(cancelling.error)}</span>
        ) : null}
      </div>
    </div>
  );
}
