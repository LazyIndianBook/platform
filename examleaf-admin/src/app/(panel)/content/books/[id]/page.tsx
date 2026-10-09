// /content/books/<id>/: one book (GET content/books/{id}/): its facts, its legal deposit (the libraries still without
// this edition, the day it is due), the form that changes it (content.change_book; the ISBN checked by the API), its
// history with restore, and its notes and audit trail beside.
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { Facts, RecordPage } from "@/components/data/record-page";
import { recordSide } from "@/components/data/record-side";
import { StatusChip } from "@/components/data/status-chip";
import { BookForm } from "@/components/modules/content/book-form";
import { History } from "@/components/modules/content/history";
import { Section } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, recordId, type SearchParams, staffPage } from "@/lib/api/page";
import { getBook, listHistory } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDate } from "@/lib/format";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.content.books.title };

const words = copy.content;

export default async function BookPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<SearchParams>;
}) {
  const { id } = await params;
  const search = await searchParams;
  const { manifest, transport, path } = await staffPage(`/content/books/${encodeURIComponent(id)}/`);
  const book = await attempt(getBook(recordId(id), transport), path, "404");
  const back = { href: "/content/books/", label: words.books.title };
  if (book instanceof ApiError)
    return (
      <RecordPage title={words.books.title} back={back}>
        <Problem error={book} />
      </RecordPage>
    );
  const versions = await attempt(listHistory("books", book.id, param(search, "versions"), transport), path);
  return (
    <RecordPage
      eyebrow={labelOf(words.subjects, book.subject_code)}
      title={book.title}
      back={back}
      status={<StatusChip tone="stopped">{labelOf(words.formats, book.format ?? "print")}</StatusChip>}
      side={recordSide({
        manifest,
        transport,
        path,
        audit: { target_type: "content.book", target_id: String(book.id) },
        note: { type: "content.book", id: String(book.id) },
      })}
    >
      <Facts
        items={[
          { label: words.books.fields.edition, value: book.edition || copy.common.none },
          { label: words.books.fields.isbn, value: <span className="font-mono">{book.isbn || copy.common.none}</span> },
          { label: words.books.fields.slug, value: <span className="font-mono">{book.slug}</span> },
          { label: words.books.fields.publishedOn, value: book.published_on ? formatDate(book.published_on) : copy.common.none },
          { label: words.books.columns.papers, value: book.papers },
        ]}
      />
      <Section id="deposit" title={words.books.deposits}>
        {!book.published_on ? (
          <p className="m-0 text-[15px] text-muted-foreground">{words.books.depositsUnpublished}</p>
        ) : book.missing_deposits.length ? (
          <div className="flex flex-col gap-1.5 text-[15px] [&>p]:m-0">
            {book.deposit_due_on ? <p>{words.books.depositsDue(formatDate(book.deposit_due_on))}</p> : null}
            <p>
              {words.books.depositsMissing}:{" "}
              {book.missing_deposits.map((library) => labelOf(words.deposits.libraries, library)).join(", ")}
            </p>
          </div>
        ) : (
          <p className="m-0 text-[15px]">{words.books.depositsDone}</p>
        )}
      </Section>
      {has(manifest, P.booksChange) ? (
        <Section id="edit" title={words.books.edit}>
          <BookForm book={book} />
        </Section>
      ) : null}
      <Section id="history" title={words.editor.history} lead={words.editor.historyLead}>
        {versions instanceof ApiError ? <Problem error={versions} /> : <History kind="books" id={book.id} page={versions} />}
      </Section>
    </RecordPage>
  );
}
