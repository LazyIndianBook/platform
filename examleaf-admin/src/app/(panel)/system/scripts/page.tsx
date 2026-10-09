// /system/scripts/: the scripts the storefront's checkout and the console's sign-in load (GET system/scripts/, PCI
// DSS 6.4.3 and 11.6.1): each page's daily check (when, whether it could be read, what was new or gone), and the
// scripts seen with their SHA-256, first and last seen, those on the page now marked. A change opens an inbox item.
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { StatusChip } from "@/components/data/status-chip";
import { PageHeader, Section } from "@/components/shell/page-header";
import { Table, TableCell, TableHead } from "@/components/ui/table";
import { ApiError } from "@/lib/api/errors";
import { attempt, requestTime, staffPage } from "@/lib/api/page";
import { getScripts } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatAgo, formatDateTime } from "@/lib/format";

const words = copy.management;

export const metadata: Metadata = { title: words.system.pageTitles.scripts };

export default async function ScriptsPage() {
  const { transport, path } = await staffPage("/system/scripts/");
  const checks = await attempt(getScripts(transport), path);
  const now = requestTime();
  const back = { href: "/system/", label: copy.system.title };
  if (checks instanceof ApiError) {
    return (
      <>
        <PageHeader title={words.system.pageTitles.scripts} back={back} />
        <Problem error={checks} />
      </>
    );
  }
  return (
    <>
      <PageHeader title={words.system.pageTitles.scripts} lead={words.system.pageLeads.scripts} back={back} />
      <div className="flex flex-col gap-10">
        <Section id="runs" title={words.scripts.runs}>
          <ul className="m-0 flex list-none flex-col p-0">
            {checks.runs.map((run) => (
              <li
                key={run.page}
                className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-b border-border py-2.5 text-[15px]"
              >
                <span className="flex min-w-0 flex-col">
                  <span className="font-semibold">{labelOf(words.scripts.pages, run.page)}</span>
                  <span className="text-sm break-all text-muted-foreground">
                    {run.url} · {run.at ? words.scripts.checked(formatAgo(run.at, now)) : words.scripts.notChecked}
                  </span>
                  {run.error ? <span className="text-sm text-destructive">{run.error}</span> : null}
                  {run.ok && (run.added || run.removed) ? (
                    <span className="text-sm">{words.scripts.changed(run.added, run.removed)}</span>
                  ) : null}
                </span>
                {run.ok === null ? null : (
                  <StatusChip tone={!run.ok ? "bad" : run.added || run.removed ? "waiting" : "good"}>
                    {!run.ok
                      ? words.scripts.failed
                      : run.added || run.removed
                        ? words.scripts.changedChip
                        : words.scripts.unchanged}
                  </StatusChip>
                )}
              </li>
            ))}
          </ul>
        </Section>
        <Section id="inventory" title={words.scripts.inventory}>
          {checks.scripts.length ? (
            <Table caption={copy.table.region(words.scripts.inventory)}>
              <thead>
                <tr>
                  <TableHead>{words.scripts.columns.page}</TableHead>
                  <TableHead>{words.scripts.columns.script}</TableHead>
                  <TableHead>{words.scripts.columns.hash}</TableHead>
                  <TableHead>{words.scripts.columns.first}</TableHead>
                  <TableHead>{words.scripts.columns.last}</TableHead>
                </tr>
              </thead>
              <tbody>
                {checks.scripts.map((script) => (
                  <tr key={script.id}>
                    <TableCell>{labelOf(words.scripts.pages, script.page)}</TableCell>
                    <TableCell>
                      {script.src ? <code className="break-all">{script.src}</code> : words.scripts.inline}
                      {script.current ? (
                        <span className="block text-sm font-semibold">{words.scripts.current}</span>
                      ) : null}
                    </TableCell>
                    <TableCell>
                      <code title={script.sha256}>{script.sha256?.slice(0, 12)}…</code>
                    </TableCell>
                    <TableCell>{script.first_seen ? formatDateTime(script.first_seen) : "—"}</TableCell>
                    <TableCell>{script.last_seen ? formatDateTime(script.last_seen) : "—"}</TableCell>
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <p className="m-0 text-[15px] text-muted-foreground">{words.scripts.none}</p>
          )}
        </Section>
      </div>
    </>
  );
}
