// /content/papers/: every paper by its code (GET content/papers/, within the person's subjects), with its questions on
// the site and how many drafts wait in it; filters in the address (code or title, subject, tier, drafts, on the site).
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Problem } from "@/components/data/problem";
import { ContentNav } from "@/components/modules/content/nav";
import { PapersTable } from "@/components/modules/content/tables";
import { PageHeader } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, type SearchParams, staffPage } from "@/lib/api/page";
import { listPapers, listSavedViews } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.content.papers.title };

export default async function PapersPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/content/papers/", params));
  if (!has(manifest, P.papersView)) notFound();
  const filters = Object.fromEntries(
    ["q", "subject", "tier", "changed", "is_published", "cursor"].map((name) => [name, param(params, name)]),
  );
  const [page, views] = await Promise.all([
    attempt(listPapers(filters, transport), path),
    has(manifest, P.savedViewsView) ? attempt(listSavedViews("content-papers", transport), path) : null,
  ]);
  return (
    <>
      <PageHeader title={copy.content.title} lead={copy.content.papers.lead} />
      <ContentNav manifest={manifest} current="papers" />
      {page instanceof ApiError ? (
        <Problem error={page} />
      ) : (
        <PapersTable
          rows={page.results}
          next={page.next}
          previous={page.previous}
          views={views instanceof ApiError ? null : views}
        />
      )}
    </>
  );
}
