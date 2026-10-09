// /tax/documents/: the storefront's invoices, or its credit notes, newest first (GET tax/documents/?kind=&series=
// &document_type=&month=&cancelled=&test=&search=&cursor=), each opening its own page; the test series only when
// asked for (it is not a tax document).
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { DocumentsTable } from "@/components/modules/tax/documents";
import { recentMonths } from "@/components/modules/tax/periods";
import { TaxTabs } from "@/components/modules/tax/tax-tabs";
import { PageHeader } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, requestTime, type SearchParams, staffPage } from "@/lib/api/page";
import { listSavedViews, listTaxDocuments } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.tax.documentsTitle };

const FILTERS = ["kind", "series", "document_type", "month", "cancelled", "test", "search", "cursor"] as const;

export default async function DocumentsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/tax/documents/", params));
  const filters = Object.fromEntries(FILTERS.map((name) => [name, param(params, name)]));
  const [page, views] = await Promise.all([
    attempt(listTaxDocuments(filters, transport), path),
    has(manifest, P.savedViewsView) ? attempt(listSavedViews("tax-documents", transport), path) : null,
  ]);
  return (
    <>
      <PageHeader title={copy.tax.documentsTitle} lead={copy.tax.documentsLead} />
      <TaxTabs manifest={manifest} current="documents" />
      {page instanceof ApiError ? (
        <Problem error={page} />
      ) : (
        <DocumentsTable
          rows={page.results}
          next={page.next}
          previous={page.previous}
          views={views instanceof ApiError ? null : views}
          months={recentMonths(requestTime())}
        />
      )}
    </>
  );
}
