// /reports/codes/: book codes by print run and by district (GET reports/codes/): printed, sold, activated and revoked,
// the share activated, and where the redemptions came from, a district under the minimum shown as "fewer than 10". One
// batch's districts with `?batch=`.
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Problem } from "@/components/data/problem";
import { CodesTables } from "@/components/modules/reports/codes";
import { ExportReport } from "@/components/modules/reports/export-report";
import { filtersOf } from "@/components/modules/reports/filters";
import { ChoiceField, ReportForm, ReportHead } from "@/components/modules/reports/parts";
import { ReportPage } from "@/components/modules/reports/report-page";
import { opens } from "@/components/modules/reports/reports-tabs";
import { ApiError } from "@/lib/api/errors";
import { attempt, pathOf, type SearchParams, staffPage } from "@/lib/api/page";
import { getCodesReport } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.reports.codes.title };

export default async function CodesReportPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/reports/codes/", params));
  if (!opens(manifest, "codes")) notFound();
  const words = copy.reports.codes;
  const asked = filtersOf(params, ["batch"]);
  const report = await attempt(getCodesReport(asked, transport), path);
  const answered = report instanceof ApiError ? null : report;
  return (
    <ReportPage title={words.title} lead={words.lead} manifest={manifest} current="codes">
      {answered && answered.rows.length ? (
        <ReportForm action="/reports/codes/" label={copy.reports.filtersLabel}>
          <ChoiceField
            id="codes-batch"
            name="batch"
            label={words.batchFilter}
            value={answered.batch}
            options={[
              { value: "", label: words.everyBatch },
              ...answered.rows.map((row) => ({ value: row.batch, label: row.batch })),
            ]}
            className="w-64"
          />
        </ReportForm>
      ) : null}
      {answered ? (
        <>
          <ReportHead report={answered} />
          <CodesTables report={answered} />
          {has(manifest, P.exportReport) ? (
            <ExportReport report="codes" filters={answered.batch ? { batch: answered.batch } : {}} />
          ) : null}
        </>
      ) : report instanceof ApiError ? (
        <Problem error={report} />
      ) : null}
    </ReportPage>
  );
}
