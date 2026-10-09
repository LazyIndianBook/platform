// /system/dependencies/: CI's last audit of the packages (GET system/dependencies/: pip-audit's and npm audit's
// findings, loaded by the deploy): when it was made, the open advisories by severity with a critical one's 7-day
// target, and the versions that matter (Django, Python, Next.js, ERPNext).
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { Facts } from "@/components/data/record-page";
import { StatusChip, type Tone } from "@/components/data/status-chip";
import { PageHeader, Section } from "@/components/shell/page-header";
import { Alert } from "@/components/ui/alert";
import { Table, TableCell, TableHead } from "@/components/ui/table";
import { ApiError } from "@/lib/api/errors";
import { attempt, staffPage } from "@/lib/api/page";
import { getDependencies } from "@/lib/api/staff";
import { copy, humanize, labelOf } from "@/lib/copy";
import { formatDate, formatDateTime, formatNumber } from "@/lib/format";

const words = copy.management;
const TONE: Record<string, Tone> = {
  critical: "bad",
  high: "waiting",
  moderate: "moving",
  low: "stopped",
  unknown: "stopped",
};

export const metadata: Metadata = { title: words.system.pageTitles.dependencies };

export default async function DependenciesPage() {
  const { transport, path } = await staffPage("/system/dependencies/");
  const report = await attempt(getDependencies(transport), path);
  const back = { href: "/system/", label: copy.system.title };
  if (report instanceof ApiError) {
    return (
      <>
        <PageHeader title={words.system.pageTitles.dependencies} back={back} />
        <Problem error={report} />
      </>
    );
  }
  const counts = Object.entries(report.counts);
  return (
    <>
      <PageHeader title={words.system.pageTitles.dependencies} lead={words.system.pageLeads.dependencies} back={back} />
      <div className="flex flex-col gap-10">
        {!report.available ? <Alert variant="warning" title={words.dependencies.none} /> : null}
        {report.available && report.stale ? <Alert variant="warning" title={words.dependencies.stale} /> : null}
        {report.error ? <Alert variant="error" title={report.error} /> : null}
        {report.available && report.generated_at ? (
          <p className="m-0 text-[15px]">
            {words.dependencies.generated(formatDateTime(report.generated_at), report.age_days ?? 0)}
            {report.commit ? ` · ${words.dependencies.commit(report.commit)}` : ""}
          </p>
        ) : null}
        <Section id="counts" title={words.dependencies.counts}>
          <ul className="m-0 flex list-none flex-wrap gap-2 p-0">
            {counts.map(([severity, n]) => (
              <li key={severity}>
                <StatusChip tone={n ? (TONE[severity] ?? "stopped") : "stopped"}>
                  {labelOf(words.dependencies.severities, severity)}: {formatNumber(n)}
                </StatusChip>
              </li>
            ))}
          </ul>
          {report.advisories.length ? (
            <Table caption={copy.table.region(words.dependencies.counts)}>
              <thead>
                <tr>
                  <TableHead>{words.dependencies.columns.package}</TableHead>
                  <TableHead>{words.dependencies.columns.severity}</TableHead>
                  <TableHead>{words.dependencies.columns.advisory}</TableHead>
                  <TableHead>{words.dependencies.columns.fixed}</TableHead>
                  <TableHead>{words.dependencies.columns.due}</TableHead>
                </tr>
              </thead>
              <tbody>
                {report.advisories.map((row) => (
                  <tr key={`${row.ecosystem}-${row.project}-${row.package}-${row.id}`}>
                    <TableCell>
                      <code>{row.package}</code> {row.version}
                      <span className="block text-sm text-muted-foreground">
                        {row.ecosystem} · {row.project}
                      </span>
                    </TableCell>
                    <TableCell>
                      <StatusChip tone={TONE[row.severity] ?? "stopped"}>
                        {labelOf(words.dependencies.severities, row.severity)}
                      </StatusChip>
                    </TableCell>
                    <TableCell>
                      {row.url ? (
                        <a href={row.url} target="_blank" rel="noopener noreferrer">
                          {row.id} <span className="sr-only">{copy.common.opensElsewhere}</span>
                        </a>
                      ) : (
                        row.id
                      )}
                      {row.title ? <span className="block text-sm text-muted-foreground">{row.title}</span> : null}
                    </TableCell>
                    <TableCell>{row.fixed_in || "—"}</TableCell>
                    <TableCell>
                      {row.due ? formatDate(row.due) : "—"}
                      {row.overdue ? (
                        <span className="block text-sm font-semibold text-destructive">
                          {words.dependencies.overdue}
                        </span>
                      ) : null}
                    </TableCell>
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <p className="m-0 text-[15px] text-muted-foreground">{words.dependencies.noAdvisories}</p>
          )}
        </Section>
        <Section id="versions" title={words.dependencies.versions}>
          <Facts
            items={Object.entries(report.versions).map(([name, version]) => ({
              label: humanize(name),
              value: version,
            }))}
          />
        </Section>
      </div>
    </>
  );
}
