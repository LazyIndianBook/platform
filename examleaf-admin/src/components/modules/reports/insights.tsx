// The insights' own lists, drawn and not rebuilt (GET insights/cohorts/, print-runs/ and forecasts/, numbered pages): the
// cohorts' weekly retention (a week of fewer learners than the minimum says "fewer than 10"), the nightly print-run
// advice of each title with the level it needs, and one title's weekly forecast as a range (a season in ten sells
// less than the low figure, one in ten more than the high one). A prediction that has not beaten the seasonal naive in
// the backtest is labelled untested here, not hidden: the page says what was tested and how it did.
import Link from "next/link";

import { StatusChip, type Tone } from "@/components/data/status-chip";
import { EmptyState } from "@/components/ui/empty-state";
import { Table, TableCell, TableHead } from "@/components/ui/table";
import type { CohortStat, Forecast, InsightsAbout, InsightsPage, PrintRunAdvice } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";

import { count, decimal, maxOf, percent, periodLabel } from "./numbers";
import { Fewer, Measure } from "./parts";

/** How the last backtest did, in a sentence: the error of the forecast against the copies sold (WAPE), and whether it
 *  beat the seasonal naive (MASE below 1), which is what lets the panel trust it. */
export function backtestLine(about: Pick<InsightsAbout, "backtest">): string {
  const words = copy.reports.forecasts;
  const backtest = about.backtest;
  if (!backtest) return words.noBacktest;
  const error = percent(backtest.wape, 0);
  const mase = decimal(backtest.mase_vs_seasonal_naive, 2);
  return backtest.shown
    ? words.backtestShown(error, mase, backtest.horizon_weeks)
    : words.backtestUntested(error, mase);
}

export function CohortTable({ page }: { page: InsightsPage<CohortStat> }) {
  const words = copy.reports.cohorts;
  if (page.results.length === 0)
    return (
      <EmptyState art="results" title={words.emptyTitle}>
        <p>{words.emptyText}</p>
      </EmptyState>
    );
  return (
    <Table caption={words.table}>
      <thead>
        <tr>
          <TableHead>{words.cohort}</TableHead>
          <TableHead>{words.source}</TableHead>
          <TableHead numeric>{words.week}</TableHead>
          <TableHead numeric>{words.learners}</TableHead>
          <TableHead numeric>{words.active}</TableHead>
          <TableHead numeric>{words.quiet}</TableHead>
        </tr>
      </thead>
      <tbody>
        {page.results.map((row) => (
          <tr key={`${row.cohort_month}|${row.source}|${row.week_index}`}>
            <TableCell>{periodLabel("month", row.cohort_month)}</TableCell>
            <TableCell>{labelOf(words.sources, row.source)}</TableCell>
            <TableCell numeric>{count(row.week_index)}</TableCell>
            {row.hidden ? (
              <Fewer under={row.under} span={3} />
            ) : (
              <>
                <TableCell numeric>{count(row.n)}</TableCell>
                <TableCell numeric>
                  <Measure value={row.active_share} max={1}>
                    {percent(row.active_share, 0)}
                  </Measure>
                </TableCell>
                <TableCell numeric>{percent(row.churned_share, 0)}</TableCell>
              </>
            )}
          </tr>
        ))}
      </tbody>
    </Table>
  );
}

const LEVEL_TONE: Record<string, Tone> = { ok: "good", watch: "waiting", act: "bad" };

export function PrintRunsTable({ page, selected }: { page: InsightsPage<PrintRunAdvice>; selected: string }) {
  const words = copy.reports.forecasts;
  if (page.results.length === 0)
    return (
      <EmptyState art="sheet" title={words.noRunsTitle}>
        <p>{words.noRunsText}</p>
      </EmptyState>
    );
  return (
    <Table caption={words.runsTable}>
      <thead>
        <tr>
          <TableHead>{words.titleColumn}</TableHead>
          <TableHead numeric title={words.ratioHelp}>
            {words.ratio}
          </TableHead>
          <TableHead numeric title={words.targetHelp}>
            {words.target}
          </TableHead>
          <TableHead numeric title={words.supplyHelp}>
            {words.supply}
          </TableHead>
          <TableHead numeric title={words.printHelp}>
            {words.print}
          </TableHead>
          <TableHead numeric title={words.triggerHelp}>
            {words.trigger}
          </TableHead>
          <TableHead numeric title={words.coverHelp}>
            {words.cover}
          </TableHead>
          <TableHead numeric title={words.leftoverHelp}>
            {words.leftover}
          </TableHead>
          <TableHead>{words.level}</TableHead>
        </tr>
      </thead>
      <tbody>
        {page.results.map((row) => (
          <tr key={row.product}>
            <TableCell>
              <Link
                href={`/reports/forecasts/?product=${encodeURIComponent(row.product)}#work-it-out`}
                aria-current={row.product === selected ? "true" : undefined}
                className={row.product === selected ? "font-bold" : undefined}
              >
                {row.title}
              </Link>
            </TableCell>
            <TableCell numeric>{percent(row.critical_ratio, 0)}</TableCell>
            <TableCell numeric>{count(row.target_quantity)}</TableCell>
            <TableCell numeric>{count(row.supply)}</TableCell>
            <TableCell numeric>
              <strong>{count(row.recommended_quantity)}</strong>
            </TableCell>
            <TableCell numeric>{count(row.reprint_trigger_units)}</TableCell>
            <TableCell numeric>
              {row.weeks_of_cover === null || row.weeks_of_cover === undefined
                ? words.outlasts
                : decimal(row.weeks_of_cover)}
            </TableCell>
            <TableCell numeric>{count(row.projected_leftover)}</TableCell>
            <TableCell>
              <StatusChip tone={LEVEL_TONE[row.level ?? "ok"] ?? "stopped"}>
                {labelOf(words.levels, row.level ?? "ok")}
              </StatusChip>
            </TableCell>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}

export function ForecastTable({ page }: { page: InsightsPage<Forecast> }) {
  const words = copy.reports.forecasts;
  if (page.results.length === 0)
    return (
      <EmptyState art="results" title={words.noForecastTitle}>
        <p>{words.noForecastText}</p>
      </EmptyState>
    );
  const max = maxOf(page.results.map((row) => row.p90));
  const share = (value: number) => `${Math.min(100, (value / (max || 1)) * 100)}%`;
  return (
    <Table caption={words.forecastTable}>
      <thead>
        <tr>
          <TableHead>{words.week}</TableHead>
          <TableHead numeric title={words.lowHelp}>
            {words.low}
          </TableHead>
          <TableHead numeric title={words.midHelp}>
            {words.mid}
          </TableHead>
          <TableHead numeric title={words.highHelp}>
            {words.high}
          </TableHead>
          <TableHead>
            <span className="sr-only">{words.range}</span>
          </TableHead>
        </tr>
      </thead>
      <tbody>
        {page.results.map((row) => (
          <tr key={`${row.product}|${row.week_start}|${row.district ?? ""}`}>
            <TableCell>{periodLabel("week", row.week_start)}</TableCell>
            <TableCell numeric>{count(Math.round(row.p10))}</TableCell>
            <TableCell numeric>{count(Math.round(row.p50))}</TableCell>
            <TableCell numeric>{count(Math.round(row.p90))}</TableCell>
            <TableCell className="w-40 min-w-32">
              <span aria-hidden="true" className="relative mt-2 block h-1.5 w-full bg-rule-soft">
                <span
                  className="absolute inset-y-0 bg-primary/40"
                  style={{ left: share(row.p10), width: `${Math.max(1, ((row.p90 - row.p10) / (max || 1)) * 100)}%` }}
                />
                <span className="absolute -top-0.5 -bottom-0.5 w-0.5 bg-primary" style={{ left: share(row.p50) }} />
              </span>
            </TableCell>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}
