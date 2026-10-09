// /system/sync/: the ERPNext sync at a glance (GET system/sync/): the outbox by flow and state with each flow's
// switch, the newest dead letters (replayed or given up on ERPNext's connection page), ERPNext's calls back over 7
// days, the last week's nightly reconciliations; and a document found among the links (GET system/sync/links/?q=).
import type { Metadata } from "next";
import Link from "next/link";

import { Problem } from "@/components/data/problem";
import { StatusChip } from "@/components/data/status-chip";
import { LinkSearch } from "@/components/modules/system/system-forms";
import { PageHeader, Section } from "@/components/shell/page-header";
import { Alert } from "@/components/ui/alert";
import { Table, TableCell, TableHead } from "@/components/ui/table";
import { ApiError } from "@/lib/api/errors";
import { attempt, staffPage } from "@/lib/api/page";
import { getSync } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDate, formatDateTime, formatNumber } from "@/lib/format";

const words = copy.management;
const STATES = ["pending", "sending", "sent", "failed", "dead", "discarded"];

export const metadata: Metadata = { title: words.system.pageTitles.sync };

export default async function SyncPage() {
  const { transport, path } = await staffPage("/system/sync/");
  const sync = await attempt(getSync(transport), path);
  const back = { href: "/system/", label: copy.system.title };
  if (sync instanceof ApiError) {
    return (
      <>
        <PageHeader title={words.system.pageTitles.sync} back={back} />
        <Problem error={sync} />
      </>
    );
  }
  const status = (sync.status ?? {}) as { enabled?: boolean };
  const inbound = Object.entries(sync.inbound.states);
  return (
    <>
      <PageHeader title={words.system.pageTitles.sync} lead={words.system.pageLeads.sync} back={back} />
      <div className="flex flex-col gap-10">
        {!status.enabled ? <Alert variant="info" title={words.sync.off} /> : null}
        <Section id="flows" title={words.sync.flows}>
          <Table caption={copy.table.region(words.sync.flows)}>
            <thead>
              <tr>
                <TableHead>{words.sync.flow}</TableHead>
                {STATES.map((state) => (
                  <TableHead key={state} numeric>
                    {labelOf(words.sync.states, state)}
                  </TableHead>
                ))}
              </tr>
            </thead>
            <tbody>
              {sync.flows.map((flow) => (
                <tr key={flow.flow}>
                  <TableCell>
                    <span className="flex flex-wrap items-center gap-2">
                      <code>{flow.flow}</code>
                      <StatusChip tone={flow.switch ? "good" : "stopped"}>
                        {flow.switch ? words.sync.switchOn : words.sync.switchOff}
                      </StatusChip>
                    </span>
                  </TableCell>
                  {STATES.map((state) => (
                    <TableCell key={state} numeric>
                      {formatNumber(flow.states[state] ?? 0)}
                    </TableCell>
                  ))}
                </tr>
              ))}
            </tbody>
          </Table>
        </Section>
        <Section id="dead" title={words.sync.dead(sync.dead_count)} lead={words.sync.deadLead}>
          {sync.dead_letters.length ? (
            <ul className="m-0 flex list-none flex-col gap-2 p-0 text-[15px]">
              {sync.dead_letters.map((row) => (
                <li key={row.id} className="border-b border-border pb-2">
                  <code>{row.examleaf_ref}</code> · {row.event} · {formatDateTime(row.created)}
                  <span className="block text-sm text-destructive">{row.last_error}</span>
                </li>
              ))}
            </ul>
          ) : null}
          <p className="m-0">
            <Link href="/settings/connections/erpnext/#dead-letters" className="font-semibold">
              {words.sync.deadLink}
            </Link>
          </p>
        </Section>
        <Section id="inbound" title={words.sync.inbound}>
          <p className="m-0 text-[15px]">
            {inbound.length
              ? inbound.map(([state, n]) => `${labelOf(words.events.states, state)} ${formatNumber(n)}`).join(", ")
              : words.sync.noInbound}
            {sync.inbound.last_received_at
              ? ` · ${words.webhooks.lastEvent(formatDateTime(sync.inbound.last_received_at))}`
              : ""}
          </p>
        </Section>
        <Section id="runs" title={words.sync.runs}>
          {sync.reconciliations.length ? (
            <Table caption={copy.table.region(words.sync.runs)}>
              <thead>
                <tr>
                  <TableHead>{words.sync.runColumns.date}</TableHead>
                  <TableHead>{words.sync.runColumns.state}</TableHead>
                  <TableHead numeric>{words.sync.runColumns.differences}</TableHead>
                  <TableHead numeric>{words.sync.runColumns.open}</TableHead>
                </tr>
              </thead>
              <tbody>
                {sync.reconciliations.map((run) => (
                  <tr key={run.id}>
                    <TableCell>{formatDate(run.date)}</TableCell>
                    <TableCell>
                      {run.state}
                      {run.error ? <span className="block text-sm text-destructive">{run.error}</span> : null}
                    </TableCell>
                    <TableCell numeric>{formatNumber(run.differences_count)}</TableCell>
                    <TableCell numeric>{formatNumber(run.open_differences)}</TableCell>
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <p className="m-0 text-[15px] text-muted-foreground">{words.sync.noRuns}</p>
          )}
        </Section>
        <Section id="links" title={words.sync.links}>
          <LinkSearch />
        </Section>
      </div>
    </>
  );
}
