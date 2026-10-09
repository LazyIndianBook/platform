// /tax/gstr1/: the month's (or the quarter's) GSTR-1 files for the accountant (POST tax/gstr1/: a background job,
// staff.run_gstr1), and the person's own GSTR-1 exports (GET jobs/?kind=gstr1_export&mine=true), newest first, each
// with its progress, cancel and its file (JobProgress). A new one shows here once started (the page is rendered
// again); one above the person's export limit waits for an approver first.
import type { Metadata } from "next";

import { JobProgress } from "@/components/data/job-progress";
import { Problem } from "@/components/data/problem";
import { StatusChip } from "@/components/data/status-chip";
import { Gstr1Form } from "@/components/modules/tax/gstr1";
import { periodLabel, recentMonths } from "@/components/modules/tax/periods";
import { TaxTabs } from "@/components/modules/tax/tax-tabs";
import { PageHeader, Section } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, requestTime, staffPage } from "@/lib/api/page";
import { type Job, listJobs } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDateTime } from "@/lib/format";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.tax.gstr1Title };

/** The job's period in words, from its params ({month, months}). */
function period(job: Job): string {
  const params = (job.params ?? {}) as { month?: unknown; months?: unknown };
  return typeof params.month === "string" ? periodLabel(params.month, Number(params.months ?? 1)) : copy.common.unknown;
}

export default async function Gstr1Page() {
  const { manifest, transport, path } = await staffPage("/tax/gstr1/");
  const jobs = has(manifest, P.jobsView)
    ? await attempt(listJobs({ kind: "gstr1_export", mine: true }, transport), path)
    : null;
  return (
    <>
      <PageHeader title={copy.tax.gstr1Title} lead={copy.tax.gstr1Lead} />
      <TaxTabs manifest={manifest} current="gstr1" />
      <div className="flex max-w-[52rem] flex-col gap-10">
        <Section id="run" title={copy.tax.gstr1Run} lead={copy.tax.gstr1Files}>
          <Gstr1Form months={recentMonths(requestTime())} />
        </Section>
        {jobs ? (
          <Section id="exports" title={copy.tax.gstr1Recent}>
            {jobs instanceof ApiError ? (
              <Problem error={jobs} />
            ) : jobs.results.length ? (
              <ul className="m-0 flex list-none flex-col gap-6 p-0">
                {jobs.results.map((job) => (
                  <li key={job.id} className="flex flex-col gap-2 border-b border-border pb-5">
                    <p className="m-0 flex flex-wrap items-center gap-x-3 gap-y-1 text-[15px]">
                      <strong>{period(job)}</strong>
                      <StatusChip tone={job.state === "failed" ? "bad" : job.state === "done" ? "done" : "moving"}>
                        {labelOf(copy.jobs.states, job.state)}
                      </StatusChip>
                      {job.dry_run ? <StatusChip tone="stopped">{copy.tax.dryRun}</StatusChip> : null}
                      <span className="text-sm text-muted-foreground">{formatDateTime(job.created)}</span>
                    </p>
                    <JobProgress job={job} />
                  </li>
                ))}
              </ul>
            ) : (
              <p className="m-0 text-[15px] text-muted-foreground">{copy.tax.gstr1None}</p>
            )}
          </Section>
        ) : null}
      </div>
    </>
  );
}
