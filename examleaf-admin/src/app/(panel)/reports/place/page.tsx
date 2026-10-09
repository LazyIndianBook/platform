// /reports/place/: sales by state, district or PIN code (GET reports/sales-by-place/). A state is the place of supply the
// order was taxed in; a place with fewer orders than the minimum is not shown ("fewer than 10") and is in no total. A
// state's row opens its districts; the PIN codes of a state are one choice away.
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Problem } from "@/components/data/problem";
import { ExportReport } from "@/components/modules/reports/export-report";
import { filtersOf, todayIn } from "@/components/modules/reports/filters";
import { ChoiceField, DayFields, ReportForm, ReportHead } from "@/components/modules/reports/parts";
import { PlaceTable, placeHref } from "@/components/modules/reports/place";
import { ReportPage } from "@/components/modules/reports/report-page";
import { opens } from "@/components/modules/reports/reports-tabs";
import { ApiError } from "@/lib/api/errors";
import { attempt, pathOf, requestTime, type SearchParams, staffPage } from "@/lib/api/page";
import { getPlaceReport } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.reports.place.title };

export default async function PlaceReportPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/reports/place/", params));
  if (!opens(manifest, "place")) notFound();
  const words = copy.reports.place;
  const asked = filtersOf(params, ["from", "to", "level", "state"]);
  const report = await attempt(getPlaceReport(asked, transport), path);
  const answered = report instanceof ApiError ? null : report;
  const state = answered?.state ?? asked.state ?? "";
  const keep: Record<string, string> = answered?.period ? { from: answered.period.start, to: answered.period.end } : {};
  return (
    <ReportPage title={words.title} lead={words.lead} manifest={manifest} current="place">
      <ReportForm action="/reports/place/" label={copy.reports.filtersLabel}>
        <DayFields
          id="place"
          from={asked.from ?? answered?.period?.start ?? ""}
          to={asked.to ?? answered?.period?.end ?? ""}
          today={todayIn(requestTime())}
        />
        <ChoiceField
          id="place-level"
          name="level"
          label={words.level}
          value={asked.level ?? answered?.level ?? "state"}
          options={Object.entries(words.levels).map(([value, label]) => ({ value, label }))}
        />
        {state ? <input type="hidden" name="state" value={state} /> : null}
      </ReportForm>
      {state ? (
        <p className="m-0 text-[15px]">
          {words.stateOnly(state)}{" "}
          <Link href={placeHref(keep, "state", "")} className="font-semibold">
            {words.allStates}
          </Link>
        </p>
      ) : null}
      {answered ? (
        <>
          <ReportHead report={answered} />
          <PlaceTable report={answered} keep={keep} />
          {has(manifest, P.exportReport) && answered.period ? (
            <ExportReport
              report="sales-by-place"
              filters={{
                from: answered.period.start,
                to: answered.period.end,
                level: answered.level,
                ...(state ? { state } : {}),
              }}
            />
          ) : null}
        </>
      ) : report instanceof ApiError ? (
        <Problem error={report} />
      ) : null}
    </ReportPage>
  );
}
