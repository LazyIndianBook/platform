// /reports/forecasts/: demand forecasts and print runs (GET insights/print-runs/ and forecasts/, the insights' own lists,
// drawn here and not rebuilt). Each title's nightly print-run advice with the level it needs; one title's weekly
// forecast as a range; and the newsvendor's sum for it worked out again with the net price, the print cost and the
// salvage typed (POST reports/print-run/, nothing stored). A forecast that has not beaten the seasonal naive in the
// backtest is labelled untested, with how it did.
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { StatusChip } from "@/components/data/status-chip";
import { ExportReport } from "@/components/modules/reports/export-report";
import { backtestLine, ForecastTable, PrintRunsTable } from "@/components/modules/reports/insights";
import { PrintRunPanel } from "@/components/modules/reports/print-run";
import { ReportPage } from "@/components/modules/reports/report-page";
import { opens } from "@/components/modules/reports/reports-tabs";
import { Problem } from "@/components/data/problem";
import { Section } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, type SearchParams, staffPage } from "@/lib/api/page";
import { listForecasts, listPrintRuns } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { formatDateTime } from "@/lib/format";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.reports.forecasts.title };

export default async function ForecastsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/reports/forecasts/", params));
  if (!opens(manifest, "forecasts")) notFound();
  const words = copy.reports.forecasts;
  const runs = await attempt(listPrintRuns({ page_size: 200 }, transport), path);
  const known = runs instanceof ApiError ? [] : runs.results;
  const asked = param(params, "product");
  const chosen = known.find((run) => run.product === asked) ?? known[0];
  const forecast = chosen
    ? await attempt(listForecasts({ product: chosen.product, page_size: 60 }, transport), path)
    : null;
  return (
    <ReportPage title={words.title} lead={words.lead} manifest={manifest} current="forecasts">
      <Section id="print-runs" title={words.runs} lead={words.runsLead}>
        {runs instanceof ApiError ? (
          <Problem error={runs} />
        ) : (
          <>
            <p className="m-0 flex flex-wrap items-center gap-x-4 gap-y-1 text-[15px] text-muted-foreground">
              <span>{runs.data_as_of ? copy.reports.asOf(formatDateTime(runs.data_as_of)) : words.notCounted}</span>
              {runs.shown ? null : <StatusChip tone="waiting">{words.untested}</StatusChip>}
            </p>
            <p className="m-0 max-w-[60ch] text-sm text-muted-foreground">
              {runs.method ? words.methodSentence(runs.method) : null} {backtestLine(runs)}
            </p>
            <PrintRunsTable page={runs} selected={chosen?.product ?? ""} />
          </>
        )}
      </Section>

      {chosen ? (
        <Section id="work-it-out" title={words.workTitle(chosen.title)} lead={words.workLead}>
          {has(manifest, P.productsView) ? (
            <PrintRunPanel
              key={chosen.product}
              product={chosen.product}
              title={chosen.title}
              inputs={{ net_price: chosen.net_price, unit_cost: chosen.unit_cost, salvage: chosen.salvage }}
            />
          ) : (
            <p className="m-0 text-[15px] text-muted-foreground">{words.noProductPermission}</p>
          )}
        </Section>
      ) : null}

      {chosen && forecast ? (
        <Section id="forecast" title={words.forecastTitle(chosen.title)} lead={words.forecastLead}>
          {forecast instanceof ApiError ? <Problem error={forecast} /> : <ForecastTable page={forecast} />}
        </Section>
      ) : null}

      {has(manifest, P.exportReport) ? <ExportReport report="forecasts" filters={{}} /> : null}
    </ReportPage>
  );
}
