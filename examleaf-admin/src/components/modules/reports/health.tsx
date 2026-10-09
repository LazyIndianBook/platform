// Course health (GET reports/course-health/): how the course is used, counted overnight by subject and chapter and
// never by student: learners with any activity (each counted once in a period), clips, quiz answers and how many were
// right, flash cards turned over and not known, by day, week or month, and the codes redeemed by week; the chapters
// over the last 28 days. A cell standing on fewer learners than the minimum is not shown ("fewer than 5").
import Link from "next/link";

import { EmptyState } from "@/components/ui/empty-state";
import { Table, TableCell, TableHead } from "@/components/ui/table";
import type { HealthReport } from "@/lib/api/staff";
import { copy } from "@/lib/copy";

import { count, decimal, maxOf, percent, periodLabel } from "./numbers";
import { defined, Fewer, Measure } from "./parts";

const chapterHref = (grain: string, subject: number, chapter: number) =>
  `/reports/course-health/?${new URLSearchParams({ grain, subject: String(subject), chapter: String(chapter) })}`;

export function HealthTables({ report }: { report: HealthReport }) {
  const words = copy.reports.health;
  const hover = defined(report.columns);
  const days = report.grain === "day";
  if (report.computed_at === null)
    return (
      <EmptyState art="results" title={words.notYetTitle}>
        <p>{words.notYetText}</p>
      </EmptyState>
    );
  const learners = maxOf(report.series.map((point) => point.active_learners));
  return (
    <div className="flex flex-col gap-10">
      <section aria-labelledby="health-series" className="flex flex-col gap-3">
        <h2 id="health-series" className="m-0 font-head text-xl leading-tight tracking-normal">
          {words.series[report.grain as keyof typeof words.series] ?? words.series.week}
        </h2>
        <p className="m-0 max-w-[60ch] text-[15px] text-muted-foreground">
          {report.whole_course ? words.wholeCourse : words.narrowed}
        </p>
        {report.series.length === 0 ? (
          <p className="m-0 text-[15px] text-muted-foreground">{words.noPeriods}</p>
        ) : (
          <Table caption={words.seriesTable}>
            <thead>
              <tr>
                <TableHead>{words.period}</TableHead>
                <TableHead numeric>{words.active}</TableHead>
                <TableHead numeric>{words.clipsDone}</TableHead>
                <TableHead numeric>{words.answers}</TableHead>
                <TableHead numeric>{words.accuracy}</TableHead>
                <TableHead numeric>{words.cards}</TableHead>
                <TableHead numeric>{words.lapses}</TableHead>
                {days ? (
                  <>
                    <TableHead numeric>{words.smooth7}</TableHead>
                    <TableHead numeric>{words.smooth28}</TableHead>
                  </>
                ) : null}
              </tr>
            </thead>
            <tbody>
              {report.series.map((point) => (
                <tr key={point.period_start}>
                  <TableCell>{periodLabel(report.grain, point.period_start)}</TableCell>
                  {point.hidden ? (
                    <Fewer under={point.under} span={days ? 8 : 6} />
                  ) : (
                    <>
                      <TableCell numeric>
                        <Measure value={point.active_learners} max={learners}>
                          {count(point.active_learners)}
                        </Measure>
                      </TableCell>
                      <TableCell numeric>{count(point.clips_completed)}</TableCell>
                      <TableCell numeric>{count(point.quiz_answers)}</TableCell>
                      <TableCell numeric>{percent(point.quiz_accuracy, 1)}</TableCell>
                      <TableCell numeric>{count(point.card_reviews)}</TableCell>
                      <TableCell numeric>{count(point.card_lapses)}</TableCell>
                      {days ? (
                        <>
                          <TableCell numeric>{decimal(point.smoothed_7)}</TableCell>
                          <TableCell numeric>{decimal(point.smoothed_28)}</TableCell>
                        </>
                      ) : null}
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </Table>
        )}
        {days ? <p className="m-0 max-w-[60ch] text-sm text-muted-foreground">{words.smoothNote}</p> : null}
      </section>

      <section aria-labelledby="health-codes" className="flex flex-col gap-3">
        <h2 id="health-codes" className="m-0 font-head text-xl leading-tight tracking-normal">
          {words.codesByWeek}
        </h2>
        {report.codes_by_week.length === 0 ? (
          <p className="m-0 text-[15px] text-muted-foreground">{words.noCodes}</p>
        ) : (
          <Table caption={words.codesTable}>
            <thead>
              <tr>
                <TableHead>{words.week}</TableHead>
                <TableHead numeric>{words.redeemed}</TableHead>
              </tr>
            </thead>
            <tbody>
              {report.codes_by_week.map((week) => (
                <tr key={week.week_start}>
                  <TableCell>{periodLabel("week", week.week_start)}</TableCell>
                  {week.hidden ? (
                    <Fewer under={week.under} span={1} />
                  ) : (
                    <TableCell numeric>{count(week.redeemed)}</TableCell>
                  )}
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </section>

      <section aria-labelledby="health-chapters" className="flex flex-col gap-3">
        <h2 id="health-chapters" className="m-0 font-head text-xl leading-tight tracking-normal">
          {words.chapters}
        </h2>
        <p className="m-0 max-w-[60ch] text-[15px] text-muted-foreground">{words.chaptersLead(report.minimum)}</p>
        {report.rows.length === 0 ? (
          <p className="m-0 text-[15px] text-muted-foreground">{words.noChapters}</p>
        ) : (
          <Table caption={words.chaptersTable}>
            <thead>
              <tr>
                <TableHead title={hover.label}>{words.chapter}</TableHead>
                <TableHead numeric title={hover.active_7d}>
                  {words.active7}
                </TableHead>
                <TableHead numeric title={hover.active_28d}>
                  {words.active28}
                </TableHead>
                <TableHead numeric title={hover.clips_started}>
                  {words.clipsStarted}
                </TableHead>
                <TableHead numeric title={hover.clips_completed}>
                  {words.clipsDone}
                </TableHead>
                <TableHead numeric title={hover.completion_rate}>
                  {words.completion}
                </TableHead>
                <TableHead numeric title={hover.quiz_answers}>
                  {words.answers}
                </TableHead>
                <TableHead numeric title={hover.quiz_accuracy}>
                  {words.accuracy}
                </TableHead>
                <TableHead numeric title={hover.card_reviews}>
                  {words.cards}
                </TableHead>
                <TableHead numeric title={hover.card_lapses}>
                  {words.lapses}
                </TableHead>
              </tr>
            </thead>
            <tbody>
              {report.rows.map((row) => (
                <tr key={`${row.subject}-${row.chapter}`}>
                  <TableCell>
                    <Link href={chapterHref(report.grain, row.subject, row.chapter)}>{row.label}</Link>
                  </TableCell>
                  {row.hidden ? (
                    <Fewer under={row.under} span={9} />
                  ) : (
                    <>
                      <TableCell numeric>{count(row.active_7d)}</TableCell>
                      <TableCell numeric>{count(row.active_28d)}</TableCell>
                      <TableCell numeric>{count(row.clips_started)}</TableCell>
                      <TableCell numeric>{count(row.clips_completed)}</TableCell>
                      <TableCell numeric>{percent(row.completion_rate, 1)}</TableCell>
                      <TableCell numeric>{count(row.quiz_answers)}</TableCell>
                      <TableCell numeric>{percent(row.quiz_accuracy, 1)}</TableCell>
                      <TableCell numeric>{count(row.card_reviews)}</TableCell>
                      <TableCell numeric>{count(row.card_lapses)}</TableCell>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </section>
    </div>
  );
}
