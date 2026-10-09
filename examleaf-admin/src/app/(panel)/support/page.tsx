// /support/: the queue (GET support/tickets/), the next legal deadline first with each ticket's clock counting down;
// tabs for due soonest (the running tickets), mine, unassigned, overdue, waiting and all; filters and the tab in the
// address; the module's numbers over 30 days (GET support/summary/) above it. Logging a call, the saved replies and
// the grievance register are a link away, each for whoever the manifest lets use it.
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Problem } from "@/components/data/problem";
import { QueueTabs, SupportNumbers } from "@/components/modules/support/overview";
import { TicketQueue } from "@/components/modules/support/queue";
import { tabFilters, tabOf } from "@/components/modules/support/shared";
import { PageHeader } from "@/components/shell/page-header";
import { buttonVariants } from "@/components/ui/button";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, requestTime, type SearchParams, staffPage } from "@/lib/api/page";
import { getSupportSummary, listAgents, listSavedViews, listTickets } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, hasAny, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.support.title };

export default async function SupportPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/support/", params));
  if (!hasAny(manifest, [P.ticketsView, P.repliesView, P.grievancesExport])) notFound();
  const tab = tabOf(param(params, "tab"));
  const reading = has(manifest, P.ticketsView);
  const [page, summary, agents, views] = await Promise.all([
    reading
      ? attempt(
          listTickets(
            {
              ...tabFilters(tab),
              q: param(params, "q"),
              category: param(params, "category"),
              priority: param(params, "priority"),
              source: param(params, "source"),
              status: tab === "all" ? param(params, "status") : "",
              test: param(params, "test"),
              cursor: param(params, "cursor"),
            },
            transport,
          ),
          path,
        )
      : null,
    reading ? attempt(getSupportSummary(30, transport), path) : null,
    reading ? attempt(listAgents(transport), path) : null,
    reading && has(manifest, P.savedViewsView) ? attempt(listSavedViews("support", transport), path) : null,
  ]);
  const links = [
    { href: "/support/new/", label: copy.support.logCall, when: has(manifest, P.ticketsHandle), primary: true },
    { href: "/support/replies/", label: copy.support.replies, when: has(manifest, P.repliesView) },
    { href: "/support/export/", label: copy.support.register, when: has(manifest, P.grievancesExport) },
  ].filter((link) => link.when);
  return (
    <>
      <PageHeader
        title={copy.support.title}
        lead={copy.support.lead}
        actions={links.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            className={buttonVariants({ variant: link.primary ? "primary" : "secondary", size: "sm" })}
          >
            {link.label}
          </Link>
        ))}
      />
      {reading ? (
        <div className="flex flex-col gap-8">
          {summary instanceof ApiError ? (
            <Problem error={summary} what={copy.support.numbers} />
          ) : summary ? (
            <SupportNumbers summary={summary} />
          ) : null}
          <div className="flex flex-col gap-4">
            <QueueTabs current={tab} params={params} />
            {page instanceof ApiError ? (
              <Problem error={page} />
            ) : page ? (
              <TicketQueue
                rows={page.results}
                next={page.next}
                previous={page.previous}
                views={views instanceof ApiError ? null : views}
                tab={tab}
                agents={agents instanceof ApiError ? null : agents}
                now={requestTime()}
              />
            ) : null}
          </div>
        </div>
      ) : null}
    </>
  );
}
