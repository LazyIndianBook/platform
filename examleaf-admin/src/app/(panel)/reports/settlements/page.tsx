// /reports/settlements/: Razorpay's settlements (GET reports/settlements/): what was paid, the fees and the GST on them,
// the refunds and what reached the bank, with the UTR, over the last 90 days unless a period is asked for. Until the
// Finance module has them the page says it is not set up, and why.
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Problem } from "@/components/data/problem";
import { ExportReport } from "@/components/modules/reports/export-report";
import { filtersOf, todayIn } from "@/components/modules/reports/filters";
import { DayFields, ReportForm, ReportHead } from "@/components/modules/reports/parts";
import { ReportPage } from "@/components/modules/reports/report-page";
import { opens } from "@/components/modules/reports/reports-tabs";
import { SettlementsTable } from "@/components/modules/reports/settlements";
import { ApiError } from "@/lib/api/errors";
import { attempt, pathOf, requestTime, type SearchParams, staffPage } from "@/lib/api/page";
import { getSettlementsReport } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.reports.settlements.title };

export default async function SettlementsReportPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/reports/settlements/", params));
  if (!opens(manifest, "settlements")) notFound();
  const words = copy.reports.settlements;
  const asked = filtersOf(params, ["from", "to"]);
  const report = await attempt(getSettlementsReport(asked, transport), path);
  const answered = report instanceof ApiError ? null : report;
  return (
    <ReportPage title={words.title} lead={words.lead} manifest={manifest} current="settlements">
      {answered?.configured === false ? null : (
        <ReportForm action="/reports/settlements/" label={copy.reports.filtersLabel}>
          <DayFields
            id="settlements"
            from={asked.from ?? answered?.period?.start ?? ""}
            to={asked.to ?? answered?.period?.end ?? ""}
            today={todayIn(requestTime())}
          />
        </ReportForm>
      )}
      {answered ? (
        <>
          <ReportHead report={answered} />
          <SettlementsTable report={answered} />
          {has(manifest, P.exportReport) && answered.configured && answered.period ? (
            <ExportReport report="settlements" filters={{ from: answered.period.start, to: answered.period.end }} />
          ) : null}
        </>
      ) : report instanceof ApiError ? (
        <Problem error={report} />
      ) : null}
    </ReportPage>
  );
}
