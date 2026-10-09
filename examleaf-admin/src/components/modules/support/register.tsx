"use client";

// The grievance register as a background job (POST jobs/ {kind: "grievance_export", params: {from, until}}): the days
// received, both optional; the job's progress, and its file once done (a fresh link each time). Above the person's
// export limit the job waits for an approver: its change request is linked. The person's earlier exports are listed
// with their state and file.
import { useState } from "react";

import { DownloadJobFile, JobProgress, jobWords } from "@/components/data/job-progress";
import { ActionForm, formText } from "@/components/forms/action-form";
import { fieldError } from "@/components/forms/use-action";
import { Field, FormGrid } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { exportGrievances, type Job } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { formatDateTime } from "@/lib/format";

export function GrievanceRegister({ jobs }: { jobs: Job[] }) {
  const [started, setStarted] = useState<Job | null>(null);
  return (
    <div className="flex flex-col gap-8">
      <ActionForm
        id="grievance-register"
        submitLabel={copy.support.registerButton}
        success={copy.support.registerStarted}
        labels={{ "params.from": copy.support.registerFrom, "params.until": copy.support.registerUntil }}
        onSubmit={(form) =>
          exportGrievances({
            ...(formText(form, "from") ? { from: formText(form, "from") } : {}),
            ...(formText(form, "until") ? { until: formText(form, "until") } : {}),
          })
        }
        onDone={(job) => setStarted(job as Job)}
      >
        {(error) => (
          <>
            <p className="m-0 text-sm text-muted-foreground">{copy.support.registerHelp}</p>
            <FormGrid>
              <Field
                id="grievance-register-params.from"
                label={copy.support.registerFrom}
                optional
                error={fieldError(error, "params.from")}
              >
                <Input name="from" type="date" className="w-auto" />
              </Field>
              <Field
                id="grievance-register-params.until"
                label={copy.support.registerUntil}
                optional
                error={fieldError(error, "params.until")}
              >
                <Input name="until" type="date" className="w-auto" />
              </Field>
            </FormGrid>
          </>
        )}
      </ActionForm>
      {started ? <JobProgress key={started.id} job={started} /> : null}
      <section aria-labelledby="register-jobs" className="flex flex-col gap-3">
        <h2 id="register-jobs" className="m-0 font-head text-xl">
          {copy.support.registerJobs}
        </h2>
        {jobs.length ? (
          <ul className="m-0 flex list-none flex-col p-0">
            {jobs.map((job) => (
              <li
                key={job.id}
                className="flex flex-wrap items-center justify-between gap-3 border-b border-border py-2"
              >
                <span className="flex flex-col gap-0.5 text-[15px]">
                  <span>{formatDateTime(job.created)}</span>
                  <span className="text-sm text-muted-foreground">{jobWords(job)}</span>
                </span>
                {job.state === "done" && job.result_url ? <DownloadJobFile job={job} /> : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="m-0 text-[15px] text-muted-foreground">{copy.support.noRegisterJobs}</p>
        )}
      </section>
    </div>
  );
}
