// /content/books/: the books (GET content/books/, within the person's subjects) and, for whoever may add one
// (content.add_book), a new edition or format with its ISBN checked by the API.
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Problem } from "@/components/data/problem";
import { BookForm } from "@/components/modules/content/book-form";
import { ContentNav } from "@/components/modules/content/nav";
import { BooksTable } from "@/components/modules/content/tables";
import { PageHeader, Section } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, type SearchParams, staffPage } from "@/lib/api/page";
import { listBooks, listSavedViews } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.content.books.title };

export default async function BooksPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/content/books/", params));
  if (!has(manifest, P.booksView)) notFound();
  const [page, views] = await Promise.all([
    attempt(
      listBooks(
        { subject: param(params, "subject"), format: param(params, "format"), cursor: param(params, "cursor") },
        transport,
      ),
      path,
    ),
    has(manifest, P.savedViewsView) ? attempt(listSavedViews("content-books", transport), path) : null,
  ]);
  return (
    <>
      <PageHeader eyebrow={copy.content.title} title={copy.content.books.title} lead={copy.content.books.lead} />
      <ContentNav manifest={manifest} current="books" />
      <div className="flex flex-col gap-10">
        {page instanceof ApiError ? (
          <Problem error={page} />
        ) : (
          <BooksTable
            rows={page.results}
            next={page.next}
            previous={page.previous}
            views={views instanceof ApiError ? null : views}
          />
        )}
        {has(manifest, P.booksAdd) && !(page instanceof ApiError) && page.results.length ? (
          <Section id="add-book" title={copy.content.books.add} lead={copy.content.books.addLead}>
            <BookForm
              subjects={[...new Map(page.results.map((book) => [book.subject, book.subject_code])).entries()].map(
                ([id, code]) => ({ id, code }),
              )}
            />
          </Section>
        ) : null}
      </div>
    </>
  );
}
