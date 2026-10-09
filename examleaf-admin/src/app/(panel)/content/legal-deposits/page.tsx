// /content/legal-deposits/: the published books still without their edition at some of the four libraries, with the
// day it is due (GET content/legal-deposits/missing/), the form that records one library's copy
// (content.add_legaldeposit), and the deposits made (GET content/legal-deposits/).
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Problem } from "@/components/data/problem";
import { StatusChip } from "@/components/data/status-chip";
import { DepositForm } from "@/components/modules/content/deposit-form";
import { ContentNav } from "@/components/modules/content/nav";
import { DepositsTable } from "@/components/modules/content/tables";
import { PageHeader, Section } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, type SearchParams, staffPage } from "@/lib/api/page";
import { listBooks, listDeposits, listMissingDeposits } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDate } from "@/lib/format";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.content.deposits.title };

const words = copy.content.deposits;

/** Today in India, as a date input wants it. */
const today = () =>
  new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata", year: "numeric", month: "2-digit", day: "2-digit" }).format(
    new Date(),
  );

export default async function DepositsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/content/legal-deposits/", params));
  if (!has(manifest, P.depositsView)) notFound();
  const [missing, deposits, books] = await Promise.all([
    attempt(listMissingDeposits(transport), path),
    attempt(listDeposits({ cursor: param(params, "cursor") }, transport), path),
    has(manifest, P.depositsAdd) && has(manifest, P.booksView) ? attempt(listBooks({ page_size: 200 }, transport), path) : null,
  ]);
  return (
    <>
      <PageHeader eyebrow={copy.content.title} title={words.title} lead={words.lead} />
      <ContentNav manifest={manifest} current="deposits" />
      <div className="flex flex-col gap-10">
        <Section id="missing" title={words.missingTitle}>
          {missing instanceof ApiError ? (
            <Problem error={missing} />
          ) : missing.length ? (
            <ul className="m-0 flex list-none flex-col gap-3 p-0">
              {missing.map((book) => (
                <li key={book.book} className="flex flex-col gap-1 rounded-lg border border-border bg-card px-4 py-3">
                  <span className="flex flex-wrap items-center gap-2">
                    <Link href={`/content/books/${book.book}/`} className="font-semibold">
                      {book.title}
                    </Link>
                    <span className="text-sm text-muted-foreground">
                      {book.edition} · {words.due(formatDate(book.due_on))}
                    </span>
                    {book.overdue ? <StatusChip tone="bad">{words.overdue}</StatusChip> : null}
                  </span>
                  <span className="text-[15px]">
                    {book.missing.map((library) => labelOf(words.libraries, library)).join(", ")}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="m-0 text-[15px] text-muted-foreground">{words.missingNone}</p>
          )}
        </Section>
        {books && !(books instanceof ApiError) && books.results.length ? (
          <Section id="record" title={words.record} lead={words.recordLead}>
            <DepositForm books={books.results.map((book) => ({ id: book.id, title: book.title }))} today={today()} />
          </Section>
        ) : null}
        <Section id="made" title={words.made}>
          {deposits instanceof ApiError ? (
            <Problem error={deposits} />
          ) : (
            <DepositsTable rows={deposits.results} next={deposits.next} previous={deposits.previous} />
          )}
        </Section>
      </div>
    </>
  );
}
