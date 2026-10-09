// /approvals/: change requests that need a second person (GET change-requests/?state=), pending by default.
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { ApprovalsTable } from "@/components/modules/approvals/approvals-table";
import { PageHeader } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, type SearchParams, staffPage } from "@/lib/api/page";
import { listChangeRequests, listSavedViews } from "@/lib/api/staff";
import { copy } from "@/lib/copy";

export const metadata: Metadata = { title: copy.approvals.title };

export default async function ApprovalsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { transport, path } = await staffPage(pathOf("/approvals/", params));
  const state = param(params, "state") || "pending";
  const [page, views] = await Promise.all([
    attempt(
      listChangeRequests({ state: state === "all" ? undefined : state, cursor: param(params, "cursor") }, transport),
      path,
    ),
    attempt(listSavedViews("approvals", transport), path),
  ]);
  return (
    <>
      <PageHeader title={copy.approvals.title} lead={copy.approvals.lead} />
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
    </>
  );
}
