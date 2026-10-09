// Home: what waits for the person today, all from the API (nothing invented). First the numbers of their roles (GET
// home/: the money, the orders, the queues, each a link to the list it counts, with its definition and when it was
// worked out), streamed on their own so that they show as soon as they are ready; then their inbox (its open and
// overdue counts, GET inbox/count/, and the first page by kind), the change requests waiting for them to decide and
// theirs waiting for someone else, the legal clocks nearest to due (data requests to acknowledge or answer, incidents
// to report), the system's failing checks, and their modules. Each part is drawn only when the manifest opens its
// module, and each fails on its own (a Problem in its card).
import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { Clock } from "@/components/data/clock";
import { Problem } from "@/components/data/problem";
import { HomeCards, HomeCardsSkeleton } from "@/components/modules/reports/home-cards";
import { PageHeader } from "@/components/shell/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, requestTime, type SearchParams, staffPage } from "@/lib/api/page";
import {
  type DataRequestRow,
  getSystem,
  type HomePeriod,
  type Incident,
  inboxCount,
  listChangeRequests,
  listDataRequests,
  listIncidents,
  listInbox,
  type Manifest,
  type Transport,
} from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { has, moduleHref, P, visibleModules } from "@/lib/modules";
import { ERP_URL } from "@/lib/site";

export const metadata: Metadata = { title: copy.home.title };

type ClockRow = { key: string; label: string; href: string; start: string | null; due: string };

function clocksOf(requests: DataRequestRow[], incidents: Incident[]): ClockRow[] {
  const rows: ClockRow[] = [];
  for (const request of requests) {
    if (request.status === "closed") continue;
    const what = `${labelOf(copy.privacy.kinds, request.kind)} · ${request.id}`;
    const href = `/privacy/requests/${request.id}/`;
    const start = request.received_at ?? null;
    if (!request.acknowledged_at)
      rows.push({
        key: `ack-${request.id}`,
        label: `${what}: ${copy.privacy.ackClock}`,
        href,
        start,
        due: request.ack_due_at,
      });
    else
      rows.push({
        key: `due-${request.id}`,
        label: `${what}: ${copy.privacy.dueClock}`,
        href,
        start,
        due: request.due_at,
      });
  }
  for (const incident of incidents) {
    if (incident.closed_at) continue;
    const what = `${labelOf(copy.privacy.incidentKinds, incident.kind)} · ${incident.id}`;
    const href = `/privacy/incidents/${incident.id}/`;
    const start = incident.detected_at ?? null;
    if (!incident.cert_in_reported_at)
      rows.push({
        key: `certin-${incident.id}`,
        label: `${what}: ${copy.privacy.certinClock}`,
        href,
        start,
        due: incident.cert_in_due,
      });
    if (!incident.board_report_at)
      rows.push({
        key: `board-${incident.id}`,
        label: `${what}: ${copy.privacy.boardClock}`,
        href,
        start,
        due: incident.board_due,
      });
  }
  return rows.sort((a, b) => Date.parse(a.due) - Date.parse(b.due)).slice(0, 6);
}

const PERIODS: HomePeriod[] = ["today", "week", "month"];

export default async function HomePage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/", params));
  const asked = param(params, "period");
  const period = (PERIODS as string[]).includes(asked) ? (asked as HomePeriod) : "";
  return (
    <>
      <PageHeader title={copy.home.title} lead={copy.home.lead} />
      <div className="flex flex-col gap-8">
        <Suspense fallback={<HomeCardsSkeleton />}>
          <HomeCards transport={transport} path={path} period={period} />
        </Suspense>
        <Suspense fallback={<Skeleton className="h-48 rounded-lg" />}>
          <HomeParts manifest={manifest} transport={transport} path={path} />
        </Suspense>
      </div>
    </>
  );
}

/** The rest of Home, below the numbers: the inbox, the approvals, the clocks, the system's health, the modules. */
async function HomeParts({ manifest, transport, path }: { manifest: Manifest; transport: Transport; path: string }) {
  const now = requestTime();
  const approvals = has(manifest, P.approvalsView);
  const [count, inbox, awaiting, mine, requests, incidents, system] = await Promise.all([
    has(manifest, P.inboxView) ? attempt(inboxCount(transport), path) : null,
    has(manifest, P.inboxView) ? attempt(listInbox({}, transport), path) : null,
    approvals ? attempt(listChangeRequests({ awaiting: true }, transport), path) : null,
    approvals ? attempt(listChangeRequests({ mine: true, status: "pending" }, transport), path) : null,
    has(manifest, P.requestsView) ? attempt(listDataRequests({}, transport), path) : null,
    has(manifest, P.incidentsView) ? attempt(listIncidents({ open: true }, transport), path) : null,
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
  const failing = system && !(system instanceof ApiError) ? system.health.filter((check) => !check.ok) : [];
  const modules = visibleModules(manifest, ERP_URL).filter((module) => module.key !== "home");

  return (
    <>
      <div className="grid gap-5 min-[1100px]:grid-cols-2">
        {inbox ? (
          <Card>
            <CardHeader>
              <CardTitle>{copy.home.inbox}</CardTitle>
              {count && !(count instanceof ApiError) ? (
                <p className="m-0 text-[15px] text-muted-foreground">
                  {copy.home.inboxCount(count.open, count.overdue)}
                </p>
              ) : null}
            </CardHeader>
            <CardContent>
              {inbox instanceof ApiError ? (
                <Problem error={inbox} />
              ) : inbox.results.length === 0 ? (
                <p className="text-[15px] text-muted-foreground">{copy.home.inboxEmpty}</p>
              ) : (
                <ul className="m-0 flex list-none flex-col p-0">
                  {[...byKind].map(([kind, n]) => (
                    <li
                      key={kind}
                      className="flex items-center justify-between border-b border-border py-2 text-[15px]"
                    >
                      <Link href={`/inbox/?kind=${encodeURIComponent(kind)}`}>{labelOf(copy.inbox.kinds, kind)}</Link>
                      <span className="font-mono font-semibold">{n}</span>
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

        {awaiting && mine ? (
          <Card>
            <CardHeader>
              <CardTitle>{copy.home.approvals}</CardTitle>
            </CardHeader>
            <CardContent>
              {awaiting instanceof ApiError ? (
                <Problem error={awaiting} />
              ) : mine instanceof ApiError ? (
                <Problem error={mine} />
              ) : awaiting.results.length + mine.results.length === 0 ? (
                <p className="text-[15px] text-muted-foreground">{copy.home.approvalsEmpty}</p>
              ) : (
                <ul className="m-0 flex list-none flex-col gap-1 p-0 text-[15px]">
                  <li className="font-semibold">
                    <Link href="/approvals/?who=awaiting">{copy.home.approvalsForYou(awaiting.results.length)}</Link>
                  </li>
                  <li className="text-muted-foreground">
                    <Link href="/approvals/?who=mine">{copy.home.approvalsYours(mine.results.length)}</Link>
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
              ) : failing.length === 0 ? (
                <p className="text-[15px]">{copy.home.healthOk}</p>
              ) : (
                <>
                  <p className="text-[15px] font-semibold text-destructive">
                    {copy.home.healthFailing(failing.length)}
                  </p>
                  <ul className="m-0 flex list-none flex-col gap-1 p-0 text-[15px]">
                    {failing.map((check) => (
                      <li key={check.check}>
                        <span className="font-mono">{check.check}</span>
                        {check.error ? <span className="text-muted-foreground">: {check.error}</span> : null}
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
                    {module.erp ? (
                      <>
                        {" "}
                        <span className="sr-only">({copy.shell.erpOpens})</span>
                      </>
                    ) : null}
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
