// /reports/cod/: cash on delivery (GET reports/cod/): what the couriers collected and have not remitted, by how late it
// is, what was remitted in the period against what was expected, and the same by courier. Test orders' parcels are left
// out.
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Problem } from "@/components/data/problem";
import { CodTables } from "@/components/modules/reports/cod";
import { ExportReport } from "@/components/modules/reports/export-report";
import { filtersOf, todayIn } from "@/components/modules/reports/filters";
import { DayFields, ReportForm, ReportHead } from "@/components/modules/reports/parts";
import { ReportPage } from "@/components/modules/reports/report-page";
import { opens } from "@/components/modules/reports/reports-tabs";
import { ApiError } from "@/lib/api/errors";
import { attempt, pathOf, requestTime, type SearchParams, staffPage } from "@/lib/api/page";
import { getCodReport } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.reports.cod.title };

export default async function CodReportPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/reports/cod/", params));
  if (!opens(manifest, "cod")) notFound();
  const words = copy.reports.cod;
  const asked = filtersOf(params, ["from", "to"]);
  const report = await attempt(getCodReport(asked, transport), path);
  const answered = report instanceof ApiError ? null : report;
  return (
    <ReportPage title={words.title} lead={words.lead} manifest={manifest} current="cod">
      <ReportForm action="/reports/cod/" label={copy.reports.filtersLabel}>
        <DayFields
          id="cod"
          from={asked.from ?? answered?.period?.start ?? ""}
          to={asked.to ?? answered?.period?.end ?? ""}
          today={todayIn(requestTime())}
        />
      </ReportForm>
      {answered ? (
        <>
          <ReportHead report={answered} />
          <CodTables report={answered} />
          {has(manifest, P.exportReport) && answered.period ? (
            <ExportReport report="cod" filters={{ from: answered.period.start, to: answered.period.end }} />
          ) : null}
        </>
      ) : report instanceof ApiError ? (
        <Problem error={report} />
      ) : null}
    </ReportPage>
  );
}
