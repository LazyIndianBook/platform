// /audit/: the audit trail (GET audit/?q=&actor=&action=&target_type=&target_id=&from=&to=&cursor=), newest first,
// each event opening in a side sheet; Export for a range of days (components/modules/audit/audit-table.tsx).
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { AuditTable } from "@/components/modules/audit/audit-table";
import { PageHeader } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, type SearchParams, staffPage } from "@/lib/api/page";
import { listAudit, listSavedViews } from "@/lib/api/staff";
import { copy } from "@/lib/copy";

export const metadata: Metadata = { title: copy.audit.title };

const FILTERS = ["q", "actor", "action", "target_type", "target_id", "from", "to", "cursor"] as const;

export default async function AuditPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { transport, path } = await staffPage(pathOf("/audit/", params));
  const query = Object.fromEntries(FILTERS.map((name) => [name, param(params, name)]));
  const [page, views] = await Promise.all([
    attempt(listAudit(query, transport), path),
    attempt(listSavedViews("audit", transport), path),
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
        />
      )}
    </>
  );
}
