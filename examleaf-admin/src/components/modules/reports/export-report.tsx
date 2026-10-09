"use client";

// A report as a file (POST jobs/ {kind: "report_export", params: {report, filters}}): the filters the page was read
// with, a CSV made in the background, its progress, and the file once it is done (a fresh link each time). Above the
// person's export limit the job waits for an approver, whose change request JobProgress links. A hidden cell is
// "fewer than 10" in the file as on the page; the file ends with who made it.
import { useState } from "react";

import { JobProgress } from "@/components/data/job-progress";
import { ErrorSummary } from "@/components/forms/error-summary";
import { useAction } from "@/components/forms/use-action";
import { Button } from "@/components/ui/button";
import { toast } from "@/components/ui/toaster";
import { exportReport, type Job } from "@/lib/api/staff";
import { copy } from "@/lib/copy";

export function ExportReport({ report, filters }: { report: string; filters: Record<string, string> }) {
  const [job, setJob] = useState<Job | null>(null);
  const { run, busy, error } = useAction();
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <Button
          variant="secondary"
          size="sm"
          busy={busy}
          onClick={() =>
            run(async () => {
              setJob(await exportReport(report, filters));
              toast.success(copy.reports.exportStarted);
            })
          }
        >
          {copy.reports.export}
        </Button>
        <span className="max-w-[60ch] text-sm text-muted-foreground">{copy.reports.exportHelp}</span>
      </div>
      <ErrorSummary error={error} />
      {job ? <JobProgress key={job.id} job={job} /> : null}
    </div>
  );
}
