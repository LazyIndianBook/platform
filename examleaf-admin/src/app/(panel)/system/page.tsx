// /system/: the platform's state (GET system/): the health checks, the Celery queues and failed tasks, recent
// webhooks, email and SMS, the last backup, and maintenance mode with its switch. The console shows these; it never
// replaces Sentry, the uptime monitor or the logs.
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { Facts } from "@/components/data/record-page";
import { StatusChip } from "@/components/data/status-chip";
import { MaintenanceForm } from "@/components/modules/system/maintenance";
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
                  key={check.name}
                  className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-b border-border py-2 text-[15px]"
                >
                  <span className="flex flex-col">
                    <span className="font-semibold">{humanize(check.name)}</span>
                    {check.detail ? <span className="text-sm text-muted-foreground">{check.detail}</span> : null}
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
            <Table caption={copy.system.queues}>
              <thead>
                <tr>
                  <TableHead>{copy.system.queue}</TableHead>
                  <TableHead numeric>{copy.system.waiting}</TableHead>
                </tr>
              </thead>
              <tbody>
                {Object.entries(system.celery.queues).map(([name, size]) => (
                  <tr key={name}>
                    <TableCell>
                      <code>{name}</code>
                    </TableCell>
                    <TableCell numeric>{formatNumber(size)}</TableCell>
                  </tr>
                ))}
              </tbody>
            </Table>
            <p className={system.celery.failed ? "font-semibold text-destructive" : "text-muted-foreground"}>
              {copy.system.failedTasks(system.celery.failed)}
            </p>
          </CardContent>
        </Card>

        <Card className="min-[1100px]:col-span-2">
          <CardHeader>
            <CardTitle>{copy.system.webhooks}</CardTitle>
          </CardHeader>
          <CardContent>
            {system.webhooks.length ? (
              <Table caption={copy.system.webhooks}>
                <thead>
                  <tr>
                    <TableHead>{copy.system.webhookColumns.provider}</TableHead>
                    <TableHead>{copy.system.webhookColumns.event}</TableHead>
                    <TableHead>{copy.system.webhookColumns.at}</TableHead>
                    <TableHead>{copy.system.webhookColumns.status}</TableHead>
                  </tr>
                </thead>
                <tbody>
                  {system.webhooks.map((hook, index) => (
                    <tr key={`${hook.provider}-${hook.at}-${index}`}>
                      <TableCell>{humanize(hook.provider)}</TableCell>
                      <TableCell>
                        <code className="text-[13px]">{hook.event}</code>
                      </TableCell>
                      <TableCell>{formatDateTime(hook.at)}</TableCell>
                      <TableCell>
                        <StatusChip tone={hook.ok ? "good" : "bad"}>
                          {hook.status ?? (hook.ok ? copy.system.healthy : copy.system.failing)}
                        </StatusChip>
                      </TableCell>
                    </tr>
                  ))}
                </tbody>
              </Table>
            ) : (
              <p className="text-[15px] text-muted-foreground">{copy.system.noWebhooks}</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{copy.system.email}</CardTitle>
          </CardHeader>
          <CardContent>
            <Facts
              items={[
                { label: copy.system.sent, value: formatNumber(system.email.sent) },
                { label: copy.system.bounced, value: formatNumber(system.email.bounced) },
                { label: copy.system.suppressed, value: formatNumber(system.email.suppressed) },
              ]}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{copy.system.sms}</CardTitle>
          </CardHeader>
          <CardContent>
            <Facts
              items={Object.entries(system.sms).map(([key, value]) => ({
                label: humanize(key),
                value: typeof value === "number" ? formatNumber(value) : value,
              }))}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{copy.system.backups}</CardTitle>
          </CardHeader>
          <CardContent>
            {system.backups.last_run ? (
              <Facts
                items={[
                  {
                    label: copy.system.lastBackup,
                    value: `${formatDateTime(system.backups.last_run)} (${formatAgo(system.backups.last_run, now)})`,
                  },
                  { label: copy.system.backupSize, value: formatBytes(system.backups.size) },
                ]}
              />
            ) : (
              <p className="font-semibold text-destructive">{copy.system.noBackup}</p>
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
          <MaintenanceForm on={system.maintenance.on} banner={system.maintenance.banner} />
        ) : null}
      </Section>
    </>
  );
}
