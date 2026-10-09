// Home: what waits for the person today, all from the API (nothing invented): their open inbox by kind, the change
// requests waiting for a decision (and theirs waiting for someone else), the legal clocks nearest to due (data
// requests to acknowledge or answer, incidents to report), the system's failing checks, and their modules. Each part
// is drawn only when the manifest opens its module, and each fails on its own (a Problem in its card).
import type { Metadata } from "next";
import Link from "next/link";

import { Clock } from "@/components/data/clock";
import { Problem } from "@/components/data/problem";
import { PageHeader } from "@/components/shell/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError } from "@/lib/api/errors";
import { attempt, requestTime, staffPage } from "@/lib/api/page";
import {
  type DataRequest,
  FINAL_REQUEST_STATES,
  getSystem,
  type Incident,
  listChangeRequests,
  listDataRequests,
  listIncidents,
  listInbox,
} from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { has, moduleHref, P, visibleModules } from "@/lib/modules";
import { ERP_URL } from "@/lib/site";

export const metadata: Metadata = { title: copy.home.title };

type ClockRow = { key: string; label: string; href: string; start: string | null; due: string };

function clocksOf(requests: DataRequest[], incidents: Incident[]): ClockRow[] {
  const rows: ClockRow[] = [];
  for (const request of requests) {
    if (FINAL_REQUEST_STATES.has(request.state)) continue;
    const what = `${labelOf(copy.privacy.types, request.type)} · ${request.id}`;
    if (!request.acknowledged_at && request.ack_due_at)
      rows.push({
        key: `ack-${request.id}`,
        label: `${what}: ${copy.privacy.ackClock}`,
        href: `/privacy/requests/${request.id}/`,
        start: request.received_at,
        due: request.ack_due_at,
      });
    else if (request.due_at)
      rows.push({
        key: `due-${request.id}`,
        label: `${what}: ${copy.privacy.dueClock}`,
        href: `/privacy/requests/${request.id}/`,
        start: request.received_at,
        due: request.due_at,
      });
  }
  for (const incident of incidents) {
    if (incident.state === "closed") continue;
    const what = `${labelOf(copy.privacy.incidentTypes, incident.type)} · ${incident.id}`;
    if (!incident.certin_reported_at && incident.certin_due_at)
      rows.push({
        key: `certin-${incident.id}`,
        label: `${what}: ${copy.privacy.certinClock}`,
        href: `/privacy/incidents/${incident.id}/`,
        start: incident.detected_at,
        due: incident.certin_due_at,
      });
    if (!incident.board_reported_at && incident.board_due_at)
      rows.push({
        key: `board-${incident.id}`,
        label: `${what}: ${copy.privacy.boardClock}`,
        href: `/privacy/incidents/${incident.id}/`,
        start: incident.detected_at,
        due: incident.board_due_at,
      });
  }
  return rows.sort((a, b) => Date.parse(a.due) - Date.parse(b.due)).slice(0, 6);
}

export default async function HomePage() {
  const { manifest, transport, path } = await staffPage("/");
  const now = requestTime();
  const [inbox, approvals, requests, incidents, system] = await Promise.all([
    has(manifest, P.inboxView) ? attempt(listInbox({ state: "open", assignee: "me" }, transport), path) : null,
    has(manifest, P.approvalsView) ? attempt(listChangeRequests({ state: "pending" }, transport), path) : null,
    has(manifest, P.requestsView) ? attempt(listDataRequests({}, transport), path) : null,
    has(manifest, P.incidentsView) ? attempt(listIncidents({}, transport), path) : null,
    has(manifest, P.systemView) ? attempt(getSystem(transport), path) : null,
  ]);

  const byKind = new Map<string, number>();
  if (inbox && !(inbox instanceof ApiError))
    for (const item of inbox.results) byKind.set(item.kind, (byKind.get(item.kind) ?? 0) + 1);
  const clocks =
    (requests && !(requests instanceof ApiError)) || (incidents && !(incidents instanceof ApiError))
      ? clocksOf(
          requests && !(requests instanceof ApiError) ? requests.results : [],
          incidents && !(incidents instanceof ApiError) ? incidents.results : [],
        )
      : null;
  const modules = visibleModules(manifest, ERP_URL).filter((module) => module.key !== "home");

  return (
    <>
      <PageHeader title={copy.home.title} lead={copy.home.lead} />
      <div className="grid gap-5 min-[1100px]:grid-cols-2">
        {inbox ? (
          <Card>
            <CardHeader>
              <CardTitle>{copy.home.inbox}</CardTitle>
            </CardHeader>
            <CardContent>
              {inbox instanceof ApiError ? (
                <Problem error={inbox} />
              ) : inbox.results.length === 0 ? (
                <p className="text-[15px] text-muted-foreground">{copy.home.inboxEmpty}</p>
              ) : (
                <ul className="m-0 flex list-none flex-col p-0">
                  {[...byKind].map(([kind, count]) => (
                    <li
                      key={kind}
                      className="flex items-center justify-between border-b border-border py-2 text-[15px]"
                    >
                      <Link href={`/inbox/?kind=${encodeURIComponent(kind)}`}>{labelOf(copy.inbox.kinds, kind)}</Link>
                      <span className="font-mono font-semibold">{count}</span>
                    </li>
                  ))}
                  {inbox.next ? (
                    <li className="pt-2 text-sm text-muted-foreground">{copy.home.more(inbox.results.length)}</li>
                  ) : null}
                </ul>
              )}
              <p>
                <Link href="/inbox/" className="font-semibold">
                  {copy.home.openInbox}
                </Link>
              </p>
            </CardContent>
          </Card>
        ) : null}

        {approvals ? (
          <Card>
            <CardHeader>
              <CardTitle>{copy.home.approvals}</CardTitle>
            </CardHeader>
            <CardContent>
              {approvals instanceof ApiError ? (
                <Problem error={approvals} />
              ) : approvals.results.length === 0 ? (
                <p className="text-[15px] text-muted-foreground">{copy.home.approvalsEmpty}</p>
              ) : (
                <ul className="m-0 flex list-none flex-col gap-1 p-0 text-[15px]">
                  <li className="font-semibold">
                    {copy.home.approvalsForYou(
                      approvals.results.filter((request) => request.maker.id !== manifest.user.id).length,
                    )}
                  </li>
                  <li className="text-muted-foreground">
                    {copy.home.approvalsYours(
                      approvals.results.filter((request) => request.maker.id === manifest.user.id).length,
                    )}
                  </li>
                </ul>
              )}
              <p>
                <Link href="/approvals/" className="font-semibold">
                  {copy.home.openApprovals}
                </Link>
              </p>
            </CardContent>
          </Card>
        ) : null}

        {requests || incidents ? (
          <Card className="min-[1100px]:col-span-2">
            <CardHeader>
              <CardTitle>{copy.home.clocks}</CardTitle>
              <p className="m-0 text-[15px] text-muted-foreground">{copy.home.clocksLead}</p>
            </CardHeader>
            <CardContent>
              {requests instanceof ApiError ? <Problem error={requests} what={copy.privacy.requestsTitle} /> : null}
              {incidents instanceof ApiError ? <Problem error={incidents} what={copy.privacy.incidentsTitle} /> : null}
              {clocks && clocks.length === 0 ? (
                <p className="text-[15px] text-muted-foreground">{copy.home.clocksEmpty}</p>
              ) : null}
              {clocks && clocks.length ? (
                <ul className="m-0 flex list-none flex-col p-0">
                  {clocks.map((clock) => (
                    <li
                      key={clock.key}
                      className="flex flex-wrap items-center justify-between gap-x-6 gap-y-1 border-b border-border py-2"
                    >
                      <Link href={clock.href} className="text-[15px]">
                        {clock.label}
                      </Link>
                      <Clock label={clock.label} start={clock.start} due={clock.due} now={now} compact />
                    </li>
                  ))}
                </ul>
              ) : null}
            </CardContent>
          </Card>
        ) : null}

        {system ? (
          <Card>
            <CardHeader>
              <CardTitle>{copy.home.health}</CardTitle>
            </CardHeader>
            <CardContent>
              {system instanceof ApiError ? (
                <Problem error={system} />
              ) : system.health.every((check) => check.ok) ? (
                <p className="text-[15px]">{copy.home.healthOk}</p>
              ) : (
                <>
                  <p className="text-[15px] font-semibold text-destructive">
                    {copy.home.healthFailing(system.health.filter((check) => !check.ok).length)}
                  </p>
                  <ul className="m-0 flex list-none flex-col gap-1 p-0 text-[15px]">
                    {system.health
                      .filter((check) => !check.ok)
                      .map((check) => (
                        <li key={check.name}>
                          <span className="font-mono">{check.name}</span>
                          {check.detail ? <span className="text-muted-foreground">: {check.detail}</span> : null}
                        </li>
                      ))}
                  </ul>
                </>
              )}
              <p>
                <Link href="/system/" className="font-semibold">
                  {copy.home.openSystem}
                </Link>
              </p>
            </CardContent>
          </Card>
        ) : null}

        <Card>
          <CardHeader>
            <CardTitle>{copy.home.quickLinks}</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="m-0 grid list-none grid-cols-[repeat(auto-fill,minmax(10rem,1fr))] gap-x-4 p-0">
              {modules.map((module) => (
                <li key={module.key}>
                  <Link
                    href={moduleHref(module, ERP_URL)}
                    className="inline-flex min-h-11 items-center text-[15px]"
                    {...(module.erp ? { target: "_blank", rel: "noopener noreferrer" } : {})}
                  >
                    {copy.nav.modules[module.key]}
                    {module.erp ? <span className="sr-only"> ({copy.shell.erpOpens})</span> : null}
                  </Link>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
