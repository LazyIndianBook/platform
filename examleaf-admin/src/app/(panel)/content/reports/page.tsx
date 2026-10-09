// /content/reports/: the triage queue (GET content/reports/), oldest first, the open ones unless the state filter says;
// filters by kind, subject, printing and verified teachers in the address. Spam never shows here.
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Problem } from "@/components/data/problem";
import { ContentNav } from "@/components/modules/content/nav";
import { ReportsTable } from "@/components/modules/content/tables";
import { PageHeader } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, type SearchParams, staffPage } from "@/lib/api/page";
import { listReports, listSavedViews } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.content.reports.title };

export default async function ReportsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/content/reports/", params));
  if (!has(manifest, P.reportsView)) notFound();
  const filters = Object.fromEntries(
    ["state", "category", "subject", "printing", "teacher", "cursor"].map((name) => [name, param(params, name)]),
  );
  const [page, views] = await Promise.all([
    attempt(listReports(filters, transport), path),
    has(manifest, P.savedViewsView) ? attempt(listSavedViews("content-reports", transport), path) : null,
  ]);
  return (
    <>
      <PageHeader eyebrow={copy.content.title} title={copy.content.reports.title} lead={copy.content.reports.lead} />
      <ContentNav manifest={manifest} current="reports" />
      {page instanceof ApiError ? (
        <Problem error={page} />
      ) : (
        <ReportsTable
          rows={page.results}
          next={page.next}
          previous={page.previous}
          views={views instanceof ApiError ? null : views}
        />
      )}
    </>
  );
}
