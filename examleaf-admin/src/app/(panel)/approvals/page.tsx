// /approvals/: change requests that need a second person (GET change-requests/?status=&awaiting=&mine=), pending by
// default; and asking for a refund (POST change-requests/, #ask), for whoever may.
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { ApprovalsTable, AskRefundForm } from "@/components/modules/approvals/approvals-table";
import { PageHeader, Section } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, type SearchParams, staffPage } from "@/lib/api/page";
import { listChangeRequests, listSavedViews } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.approvals.title };

export default async function ApprovalsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/approvals/", params));
  const status = param(params, "status") || "pending";
  const who = param(params, "who");
  const [page, views] = await Promise.all([
    attempt(
      listChangeRequests(
        {
          status: status === "all" ? undefined : status,
          awaiting: who === "awaiting" || undefined,
          mine: who === "mine" || undefined,
          cursor: param(params, "cursor"),
        },
        transport,
      ),
      path,
    ),
    has(manifest, P.savedViewsView) ? attempt(listSavedViews("approvals", transport), path) : null,
  ]);
  const asking = has(manifest, P.approvalsAsk) && has(manifest, P.refundOrder);
  return (
    <>
      <PageHeader
        title={copy.approvals.title}
        lead={copy.approvals.lead}
        actions={
          asking ? (
            <a href="#ask" className="inline-flex min-h-11 items-center font-semibold">
              {copy.approvals.ask}
            </a>
          ) : null
        }
      />
      <div className="flex flex-col gap-10">
        {page instanceof ApiError ? (
          <Problem error={page} />
        ) : (
          <ApprovalsTable
            rows={page.results}
            next={page.next}
            previous={page.previous}
            views={views instanceof ApiError ? null : views}
          />
        )}
        {asking ? (
          <Section id="ask" title={copy.approvals.ask} lead={copy.approvals.askLead}>
            <AskRefundForm />
          </Section>
        ) : null}
      </div>
    </>
  );
}
