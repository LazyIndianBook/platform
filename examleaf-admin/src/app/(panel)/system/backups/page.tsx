// /system/backups/: the backups (GET system/backups/): the newest object of each source in the backups bucket (its
// time, size, SHA-256, encrypted or not, older than BACKUP_STALE_HOURS), how long they are kept, when a restore last
// proved them, in words, and the restore drills, with the form to record one (staff.manage_system).
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { StatusChip } from "@/components/data/status-chip";
import { DrillForm } from "@/components/modules/system/system-forms";
import { PageHeader, Section } from "@/components/shell/page-header";
import { Alert } from "@/components/ui/alert";
import { Table, TableCell, TableHead } from "@/components/ui/table";
import { ApiError } from "@/lib/api/errors";
import { attempt, requestTime, staffPage } from "@/lib/api/page";
import { getBackups } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { staffLabel } from "@/lib/display";
import { formatAgo, formatBytes, formatDate } from "@/lib/format";

const words = copy.management;

export const metadata: Metadata = { title: words.system.pageTitles.backups };

export default async function BackupsPage() {
  const { manifest, transport, path } = await staffPage("/system/backups/");
  const backups = await attempt(getBackups(transport), path);
  const now = requestTime();
  const back = { href: "/system/", label: copy.system.title };
  if (backups instanceof ApiError) {
    return (
      <>
        <PageHeader title={words.system.pageTitles.backups} back={back} />
        <Problem error={backups} />
      </>
    );
  }
  const latest = backups.sources.find((source) => source.latest)?.latest?.name ?? "";
  return (
    <>
      <PageHeader title={words.system.pageTitles.backups} lead={words.system.pageLeads.backups} back={back} />
      <div className="flex flex-col gap-10">
        {!backups.configured ? (
          <Alert variant="warning" title={words.backups.notSet} />
        ) : (
          <>
            {backups.unreadable ? <Alert variant="error" title={words.backups.unreadable} /> : null}
            {backups.stale && !backups.unreadable ? (
              <Alert variant="error" title={words.backups.stale(backups.stale_hours)} />
            ) : null}
            <Section id="sources" title={words.backups.sources} lead={words.backups.retention(backups.retention_days)}>
              <Table caption={copy.table.region(words.backups.sources)}>
                <thead>
                  <tr>
                    <TableHead>{words.backups.columns.source}</TableHead>
                    <TableHead>{words.backups.columns.latest}</TableHead>
                    <TableHead>{words.backups.columns.when}</TableHead>
                    <TableHead numeric>{words.backups.columns.size}</TableHead>
                    <TableHead>{words.backups.columns.checksum}</TableHead>
                  </tr>
                </thead>
                <tbody>
                  {backups.sources.map((source) => (
                    <tr key={source.key}>
                      <TableCell>{source.label}</TableCell>
                      <TableCell>
                        {source.latest ? (
                          <>
                            <code className="break-all">{source.latest.name}</code>
                            {source.latest.encrypted ? (
                              <span className="block text-sm text-muted-foreground">{words.backups.encrypted}</span>
                            ) : null}
                          </>
                        ) : source.error ? (
                          <span className="text-destructive">{source.error}</span>
                        ) : (
                          <span className="text-muted-foreground">{words.backups.noneYet}</span>
                        )}
                      </TableCell>
                      <TableCell>
                        {source.latest ? formatAgo(source.latest.at, now) : "—"}
                        {source.stale ? (
                          <span className="block">
                            <StatusChip tone="bad">{words.backups.stale(backups.stale_hours)}</StatusChip>
                          </span>
                        ) : null}
                      </TableCell>
                      <TableCell numeric>{source.latest ? formatBytes(source.latest.size) : "—"}</TableCell>
                      <TableCell>
                        {source.latest?.sha256 ? (
                          <code title={source.latest.sha256}>{source.latest.sha256.slice(0, 12)}…</code>
                        ) : (
                          "—"
                        )}
                      </TableCell>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </Section>
          </>
        )}
        <Section id="drills" title={words.backups.drills}>
          <p className="m-0 text-[15px] font-semibold">
            {backups.last_proven
              ? words.backups.proven(
                  formatDate(backups.last_proven.on),
                  labelOf(words.backups.engines, backups.last_proven.engine),
                )
              : words.backups.neverProven}
          </p>
          {backups.drills.length ? (
            <Table caption={copy.table.region(words.backups.drills)}>
              <thead>
                <tr>
                  <TableHead>{words.backups.drillColumns.date}</TableHead>
                  <TableHead>{words.backups.drillColumns.engine}</TableHead>
                  <TableHead>{words.backups.drillColumns.result}</TableHead>
                  <TableHead numeric>{words.backups.drillColumns.minutes}</TableHead>
                  <TableHead>{words.backups.drillColumns.by}</TableHead>
                </tr>
              </thead>
              <tbody>
                {backups.drills.map((drill) => (
                  <tr key={drill.id}>
                    <TableCell>{formatDate(drill.performed_on)}</TableCell>
                    <TableCell>
                      {labelOf(words.backups.engines, drill.engine)}
                      <code className="block text-sm break-all">{drill.backup}</code>
                      {drill.notes ? <span className="block text-sm text-muted-foreground">{drill.notes}</span> : null}
                    </TableCell>
                    <TableCell>
                      <StatusChip
                        tone={drill.result === "passed" ? "good" : drill.result === "failed" ? "bad" : "waiting"}
                      >
                        {labelOf(words.backups.results, drill.result)}
                      </StatusChip>
                    </TableCell>
                    <TableCell numeric>{drill.duration_minutes}</TableCell>
                    <TableCell>{staffLabel(drill.recorded_by, manifest.user.id)}</TableCell>
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <p className="m-0 text-[15px] text-muted-foreground">{words.backups.noDrills}</p>
          )}
          <DrillForm latest={latest} />
        </Section>
      </div>
    </>
  );
}
