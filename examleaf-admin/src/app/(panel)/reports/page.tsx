// /reports/: the reports the person may open (GET reports/), each with what it counts in a line, a mark where its
// source is not set up yet (Razorpay's settlements wait for the Finance module) and, for one the person's role does not
// reach, the permission it needs; and how every number on these pages is counted. The reports are tables and plain bars,
// each saying how its numbers are defined and when they were worked out.
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Problem } from "@/components/data/problem";
import { StatusChip } from "@/components/data/status-chip";
import { opens, ReportsTabs } from "@/components/modules/reports/reports-tabs";
import { PageHeader, Section } from "@/components/shell/page-header";
import { Alert } from "@/components/ui/alert";
import { ApiError } from "@/lib/api/errors";
import { attempt, staffPage } from "@/lib/api/page";
import { getReportIndex, type ReportIndexItem } from "@/lib/api/staff";
import { copy } from "@/lib/copy";

export const metadata: Metadata = { title: copy.reports.title };

function ReportList({ reports }: { reports: ReportIndexItem[] }) {
  const words = copy.reports.index;
  return (
    <ul className="m-0 flex list-none flex-col p-0">
      {reports.map((report) => (
        <li key={report.key} className="flex flex-col gap-1 border-b border-border py-4">
          <p className="m-0 flex flex-wrap items-center gap-2 text-[17px] font-semibold">
            {report.available ? <Link href={report.page}>{report.label}</Link> : report.label}
            {report.configured ? null : <StatusChip tone="stopped">{words.notSetUp}</StatusChip>}
            {report.available ? null : <StatusChip tone="stopped">{words.noAccess}</StatusChip>}
          </p>
          <p className="m-0 text-[15px] text-muted-foreground">{report.summary}</p>
          {report.available ? null : (
            <p className="m-0 text-sm text-muted-foreground">
              {words.needs}: <span className="font-mono">{report.needs.join(", ")}</span>
            </p>
          )}
        </li>
      ))}
    </ul>
  );
}

export default async function ReportsPage() {
  const { manifest, transport, path } = await staffPage("/reports/");
  if (!opens(manifest, "index")) notFound();
  const index = await attempt(getReportIndex(transport), path);
  return (
    <>
      <PageHeader title={copy.reports.title} lead={copy.reports.lead} />
      <ReportsTabs manifest={manifest} current="index" />
      <div className="flex max-w-[60rem] flex-col gap-10">
        {index instanceof ApiError ? (
          <Problem error={index} />
        ) : (
          <>
            {index.test_mode ? (
              <Alert variant="warning" title={copy.reports.testTitle}>
                <p>{copy.reports.testText}</p>
              </Alert>
            ) : null}
            <ReportList reports={index.reports} />
          </>
        )}
        <Section id="how" title={copy.reports.index.howTitle} lead={copy.reports.index.howLead}>
          <ul className="m-0 flex list-disc flex-col gap-2 pl-5 text-[15px]">
            {copy.reports.index.how.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </Section>
      </div>
    </>
  );
}
