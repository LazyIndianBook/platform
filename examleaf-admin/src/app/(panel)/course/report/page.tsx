// /course/report/: the codes report (GET course/codes/report/): per print run, the codes printed, the copies of its
// book sold online, the codes activated, revoked and voided, the activation rate and where they were redeemed by
// district, a district under 10 shown as "fewer than 10" (never its number); the totals; how each number is made.
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Problem } from "@/components/data/problem";
import { CourseNav } from "@/components/modules/course/nav";
import { percent } from "@/components/modules/course/shared";
import { PageHeader, Section } from "@/components/shell/page-header";
import { EmptyState } from "@/components/ui/empty-state";
import { Table, TableCell, TableHead } from "@/components/ui/table";
import { ApiError } from "@/lib/api/errors";
import { attempt, staffPage } from "@/lib/api/page";
import { type CourseReport, getCodesReport } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDateTime, formatNumber } from "@/lib/format";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.course.report.title };

const words = copy.course.report;

function Districts({ cells }: { cells: CourseReport["rows"][number]["districts"] }) {
  if (!cells.length) return <>{copy.common.none}</>;
  return (
    <ul className="m-0 flex list-none flex-col gap-0.5 p-0 text-sm">
      {cells.map((cell) => (
        <li key={cell.district}>
          {cell.district}: {cell.hidden || cell.activated === null ? words.hidden : formatNumber(cell.activated)}
        </li>
      ))}
    </ul>
  );
}

export default async function ReportPage() {
  const { manifest, transport, path } = await staffPage("/course/report/");
  if (!has(manifest, P.batchesView)) notFound();
  const report = await attempt(getCodesReport(transport), path);
  return (
    <>
      <PageHeader eyebrow={copy.course.title} title={words.title} lead={words.lead} />
      <CourseNav manifest={manifest} current="report" />
      {report instanceof ApiError ? (
        <Problem error={report} />
      ) : !report.rows.length ? (
        <EmptyState title={words.emptyTitle}>
          <p>{words.emptyText}</p>
        </EmptyState>
      ) : (
        <div className="flex flex-col gap-8">
          <p className="m-0 text-sm text-muted-foreground">{words.computed(formatDateTime(report.computed_at))}</p>
          <Table caption={words.title} className="min-w-[56rem]">
            <thead>
              <tr>
                <TableHead>{words.columns.run}</TableHead>
                <TableHead numeric>{words.columns.printed}</TableHead>
                <TableHead numeric>{words.columns.sold}</TableHead>
                <TableHead numeric>{words.columns.activated}</TableHead>
                <TableHead numeric>{words.columns.revoked}</TableHead>
                <TableHead numeric>{words.columns.void}</TableHead>
                <TableHead numeric>{words.columns.rate}</TableHead>
                <TableHead>{words.columns.districts}</TableHead>
              </tr>
            </thead>
            <tbody>
              {report.rows.map((row) => (
                <tr key={row.batch.id}>
                  <TableCell>
                    <Link href={`/course/codes/${encodeURIComponent(row.batch.key)}/`} className="font-mono">
                      {row.batch.label}
                    </Link>
                  </TableCell>
                  <TableCell numeric>{formatNumber(row.printed)}</TableCell>
                  <TableCell numeric>{row.sold === null ? words.noBook : formatNumber(row.sold)}</TableCell>
                  <TableCell numeric>{formatNumber(row.activated)}</TableCell>
                  <TableCell numeric>{formatNumber(row.revoked)}</TableCell>
                  <TableCell numeric>{formatNumber(row.void)}</TableCell>
                  <TableCell numeric>{percent(row.activation_rate)}</TableCell>
                  <TableCell>
                    <Districts cells={row.districts} />
                  </TableCell>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <TableHead>{words.totals}</TableHead>
                <TableCell numeric>{formatNumber(report.totals.printed)}</TableCell>
                <TableCell numeric>{formatNumber(report.totals.sold)}</TableCell>
                <TableCell numeric>{formatNumber(report.totals.activated)}</TableCell>
                <TableCell numeric>{formatNumber(report.totals.revoked)}</TableCell>
                <TableCell numeric>{formatNumber(report.totals.void)}</TableCell>
                <TableCell numeric>{percent(report.totals.activation_rate)}</TableCell>
                <TableCell />
              </tr>
            </tfoot>
          </Table>
          <Section id="definitions" title={words.definitions}>
            <dl className="m-0 grid gap-x-8 gap-y-2 text-[15px] min-[640px]:grid-cols-[minmax(10rem,auto)_minmax(0,1fr)]">
              {Object.entries(report.definitions as Record<string, string>).map(([name, text]) => (
                <div key={name} className="contents">
                  <dt className="font-semibold">{labelOf(words.columns as Record<string, string>, name)}</dt>
                  <dd className="m-0 text-muted-foreground">{text}</dd>
                </div>
              ))}
            </dl>
          </Section>
        </div>
      )}
    </>
  );
}
