// /content/errata/: the mistakes confirmed or fixed, per book and printing (GET content/errata/); those marked for the
// errata are what the website's GET /api/v1/errata/?book= gives. Each opens its report.
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Problem } from "@/components/data/problem";
import { ContentNav } from "@/components/modules/content/nav";
import { ErrataTable } from "@/components/modules/content/tables";
import { PageHeader } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, type SearchParams, staffPage } from "@/lib/api/page";
import { listBooks, listErrata } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.content.errata.title };

export default async function ErrataPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/content/errata/", params));
  if (!has(manifest, P.reportsView)) notFound();
  const [page, books] = await Promise.all([
    attempt(
      listErrata(
        {
          book: param(params, "book"),
          printing: param(params, "printing"),
          public: param(params, "public"),
          cursor: param(params, "cursor"),
        },
        transport,
      ),
      path,
    ),
    has(manifest, P.booksView) ? attempt(listBooks({ page_size: 200 }, transport), path) : null,
  ]);
  const bookOptions =
    books && !(books instanceof ApiError) ? books.results.map((book) => ({ value: String(book.id), label: book.title })) : [];
  return (
    <>
      <PageHeader title={copy.content.title} lead={copy.content.errata.lead} />
      <ContentNav manifest={manifest} current="errata" />
      {page instanceof ApiError ? (
        <Problem error={page} />
      ) : (
        <ErrataTable rows={page.results} next={page.next} previous={page.previous} books={bookOptions} />
      )}
    </>
  );
}
