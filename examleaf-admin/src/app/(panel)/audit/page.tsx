// /audit/: the audit trail (GET audit/?actor=&action_prefix=&target_type=&target_id=&outcome=&change_request=
// &break_glass=&since=&until=&cursor=), newest first, each event opening in a side sheet; Export with the same filters
// (components/modules/audit/audit-table.tsx). Each read is itself an event (audit.read). The dates are India's days.
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { AuditTable } from "@/components/modules/audit/audit-table";
import { PageHeader } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, dayBound, param, pathOf, type SearchParams, staffPage } from "@/lib/api/page";
import { listAudit, listSavedViews } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.audit.title };

const FILTERS = ["actor", "action_prefix", "target_type", "target_id", "outcome", "change_request", "break_glass"];

export default async function AuditPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/audit/", params));
  const filters: Record<string, string> = {};
  for (const name of FILTERS) if (param(params, name)) filters[name] = param(params, name);
  const since = dayBound(param(params, "since"));
  const until = dayBound(param(params, "until"), true);
  if (since) filters.since = since;
  if (until) filters.until = until;
  const [page, views] = await Promise.all([
    attempt(listAudit({ ...filters, cursor: param(params, "cursor") }, transport), path),
    has(manifest, P.savedViewsView) ? attempt(listSavedViews("audit", transport), path) : null,
  ]);
  return (
    <>
      <PageHeader title={copy.audit.title} lead={copy.audit.lead} />
      {page instanceof ApiError ? (
        <Problem error={page} />
      ) : (
        <AuditTable
          rows={page.results}
          next={page.next}
          previous={page.previous}
          views={views instanceof ApiError ? null : views}
          filters={filters}
        />
      )}
    </>
  );
}
