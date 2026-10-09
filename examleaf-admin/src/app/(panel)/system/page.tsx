// /system/: the platform's state (GET system/): the health checks, Celery's queues and failed tasks, Razorpay's
// webhooks, email suppressions and the SMS log, the last backup, the audit chain's last check, maintenance mode with
// its switch (through the site's settings), and a stuck payment's check with Razorpay. The console shows these; it
// never replaces Sentry, the uptime monitor or the logs.
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { Facts } from "@/components/data/record-page";
import { StatusChip } from "@/components/data/status-chip";
import { MaintenanceForm, ReconcileForm } from "@/components/modules/system/maintenance";
import { PageHeader, Section } from "@/components/shell/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableCell, TableHead } from "@/components/ui/table";
import { ApiError } from "@/lib/api/errors";
import { attempt, requestTime, staffPage } from "@/lib/api/page";
import { getSystem } from "@/lib/api/staff";
import { copy, humanize } from "@/lib/copy";
import { formatAgo, formatBytes, formatDateTime, formatNumber } from "@/lib/format";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.system.title };

/** A map of counts ({name: n}) as facts. */
const counts = (map: Record<string, number> | undefined) =>
  Object.entries(map ?? {}).map(([name, n]) => ({ label: humanize(name), value: formatNumber(n) }));

export default async function SystemPage() {
  const { manifest, transport, path } = await staffPage("/system/");
  const system = await attempt(getSystem(transport), path);
  const now = requestTime();
  if (system instanceof ApiError) {
    return (
      <>
        <PageHeader title={copy.system.title} lead={copy.system.lead} />
        <Problem error={system} />
      </>
    );
  }
  const queues = system.celery.queues;
  const verification = system.audit.last_verification;
  const backups = system.backups;
  return (
    <>
      <PageHeader title={copy.system.title} lead={copy.system.lead} />
      <div className="grid gap-5 min-[1100px]:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>{copy.system.health}</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="m-0 flex list-none flex-col p-0">
              {system.health.map((check) => (
                <li
                  key={check.check}
                  className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-b border-border py-2 text-[15px]"
                >
                  <span className="flex flex-col">
                    <span className="font-semibold">{humanize(check.check.replace(/Check$/, ""))}</span>
                    {check.error ? <span className="text-sm text-muted-foreground">{check.error}</span> : null}
                  </span>
                  <StatusChip tone={check.ok ? "good" : "bad"}>
                    {check.ok ? copy.system.healthy : copy.system.failing}
                  </StatusChip>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{copy.system.queues}</CardTitle>
          </CardHeader>
          <CardContent>
            {queues === null ? (
              <p className="text-[15px] text-muted-foreground">{copy.system.eager}</p>
            ) : "error" in queues ? (
              <p className="font-semibold text-destructive">{copy.system.brokerDown(String(queues.error))}</p>
            ) : (
              <Table caption={copy.system.queues}>
                <thead>
                  <tr>
                    <TableHead>{copy.system.queue}</TableHead>
                    <TableHead numeric>{copy.system.waiting}</TableHead>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(queues).map(([name, size]) => (
                    <tr key={name}>
                      <TableCell>
                        <code>{name}</code>
                      </TableCell>
                      <TableCell numeric>{formatNumber(Number(size))}</TableCell>
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}
            <p className={system.celery.failed_7_days ? "font-semibold text-destructive" : "text-muted-foreground"}>
              {copy.system.failedTasks(system.celery.failed_7_days)}
            </p>
            {system.celery.failed.length ? (
              <ul className="m-0 flex list-none flex-col gap-1 p-0 text-sm">
                {system.celery.failed.map((task) => (
                  <li key={task.task_id}>
                    <code>{task.task_name ?? task.task_id}</code> · {formatDateTime(task.date_done)}
                  </li>
                ))}
              </ul>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{copy.system.webhooks}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="m-0 text-sm font-semibold">{copy.system.webhooksDay}</p>
            {Object.keys(system.webhooks.last_day).length ? (
              <Facts items={counts(system.webhooks.last_day)} />
            ) : (
              <p className="text-[15px] text-muted-foreground">{copy.system.noWebhooks}</p>
            )}
            <p className={system.webhooks.refused_7_days ? "font-semibold text-destructive" : "text-muted-foreground"}>
              {copy.system.webhooksRefused(system.webhooks.refused_7_days)}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{copy.system.email}</CardTitle>
          </CardHeader>
          <CardContent>
            <Facts
              items={[
                { label: copy.system.suppressed, value: formatNumber(system.email.suppressed) },
                ...counts(system.email.suppressed_7_days).map((row) => ({
                  ...row,
                  label: `${copy.system.suppressedWeek}: ${row.label}`,
                })),
              ]}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{copy.system.sms}</CardTitle>
          </CardHeader>
          <CardContent>
            {Object.keys(system.sms.last_day).length ? (
              <Facts items={counts(system.sms.last_day)} />
            ) : (
              <p className="text-[15px] text-muted-foreground">{copy.system.noSms}</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{copy.system.backups}</CardTitle>
          </CardHeader>
          <CardContent>
            {!backups.configured ? (
              <p className="text-[15px] text-muted-foreground">{copy.system.backupsOff}</p>
            ) : backups.error ? (
              <p className="font-semibold text-destructive">{copy.system.backupError(backups.error)}</p>
            ) : backups.latest && backups.at ? (
              <Facts
                items={[
                  {
                    label: copy.system.lastBackup,
                    value: `${backups.latest} (${formatAgo(backups.at, now)})`,
                  },
                  { label: copy.system.backupSize, value: formatBytes(backups.size) },
                ]}
              />
            ) : (
              <p className="font-semibold text-destructive">{copy.system.noBackup}</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{copy.system.audit}</CardTitle>
          </CardHeader>
          <CardContent>
            {verification ? (
              <p
                className={verification.action === "audit.verified" ? "text-[15px]" : "font-semibold text-destructive"}
              >
                {verification.action === "audit.verified"
                  ? copy.system.auditVerified(formatDateTime(verification.ts))
                  : copy.system.auditBroken(formatDateTime(verification.ts))}
              </p>
            ) : (
              <p className="text-[15px] text-muted-foreground">{copy.system.auditNever}</p>
            )}
          </CardContent>
        </Card>
      </div>

      <Section id="maintenance" title={copy.system.maintenance} className="mt-10 flex flex-col gap-3">
        <p className="m-0 flex flex-wrap items-center gap-3 text-[15px]">
          <StatusChip tone={system.maintenance.on ? "bad" : "good"}>
            {system.maintenance.on ? copy.common.on : copy.common.off}
          </StatusChip>
          {system.maintenance.on ? copy.system.maintenanceOn : copy.system.maintenanceOff}
        </p>
        {system.maintenance.on && system.maintenance.banner ? (
          <p className="m-0 text-[15px] text-muted-foreground">“{system.maintenance.banner}”</p>
        ) : null}
        {has(manifest, P.maintenance) ? (
          <MaintenanceForm on={system.maintenance.on} banner={system.maintenance.banner ?? ""} />
        ) : null}
      </Section>

      {has(manifest, P.reconcile) ? (
        <Section id="reconcile" title={copy.system.reconcile} lead={copy.system.reconcileLead} className="mt-10">
          <ReconcileForm />
        </Section>
      ) : null}
    </>
  );
}
