// /reports/sales/: sales by title, subject, class, board or edition, by day, week or month (GET reports/sales/): units,
// gross, discount and net of the lines of the orders placed in the period, test orders left out. The period, the grouping
// and the breakdown are in the address; the report can be taken away as a file.
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Problem } from "@/components/data/problem";
import { ExportReport } from "@/components/modules/reports/export-report";
import { filtersOf, todayIn } from "@/components/modules/reports/filters";
import { ChoiceField, DayFields, ReportForm, ReportHead } from "@/components/modules/reports/parts";
import { ReportPage } from "@/components/modules/reports/report-page";
import { opens } from "@/components/modules/reports/reports-tabs";
import { SalesTable } from "@/components/modules/reports/sales";
import { ApiError } from "@/lib/api/errors";
import { attempt, pathOf, requestTime, type SearchParams, staffPage } from "@/lib/api/page";
import { getSalesReport } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.reports.sales.title };

const options = (words: Record<string, string>) => Object.entries(words).map(([value, label]) => ({ value, label }));

export default async function SalesReportPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/reports/sales/", params));
  if (!opens(manifest, "sales")) notFound();
  const words = copy.reports.sales;
  const asked = filtersOf(params, ["from", "to", "by", "grain"]);
  const report = await attempt(getSalesReport(asked, transport), path);
  const answered = report instanceof ApiError ? null : report;
  return (
    <ReportPage title={words.title} lead={words.lead} manifest={manifest} current="sales">
      <ReportForm action="/reports/sales/" label={copy.reports.filtersLabel}>
        <DayFields
          id="sales"
          from={asked.from ?? answered?.period?.start ?? ""}
          to={asked.to ?? answered?.period?.end ?? ""}
          today={todayIn(requestTime())}
        />
        <ChoiceField
          id="sales-by"
          name="by"
          label={words.groupBy}
          value={asked.by ?? answered?.by ?? "product"}
          options={options(words.by)}
        />
        <ChoiceField
          id="sales-grain"
          name="grain"
          label={words.breakDown}
          value={asked.grain ?? answered?.grain ?? "none"}
          options={options(words.grains)}
        />
      </ReportForm>
      {answered ? (
        <>
          <ReportHead report={answered} />
          <SalesTable report={answered} />
          {has(manifest, P.exportReport) && answered.period ? (
            <ExportReport
              report="sales"
              filters={{ from: answered.period.start, to: answered.period.end, by: answered.by, grain: answered.grain }}
            />
          ) : null}
        </>
      ) : report instanceof ApiError ? (
        <Problem error={report} />
      ) : null}
    </ReportPage>
  );
}
