// /content/: the content module's home (GET content/summary/): the mistakes to triage by kind, the reviews waiting (and
// those for me), the questions and solutions changed since publish, the published books still missing a legal
// deposit, the last import. Each card shows only what the API gives this person (a part it leaves null is not
// drawn); nothing is counted here.
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Problem } from "@/components/data/problem";
import { StatusChip } from "@/components/data/status-chip";
import { ContentNav } from "@/components/modules/content/nav";
import { PageHeader } from "@/components/shell/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError } from "@/lib/api/errors";
import { attempt, staffPage } from "@/lib/api/page";
import { getContentSummary } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDate, formatDateTime } from "@/lib/format";
import { has, hasAny, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.content.title };

const words = copy.content;

export default async function ContentHome() {
  const { manifest, transport, path } = await staffPage("/content/");
  if (!hasAny(manifest, [P.booksView, P.papersView, P.reportsView])) notFound();
  const summary = has(manifest, P.reportsView) ? await attempt(getContentSummary(transport), path) : null;
  return (
    <>
      <PageHeader title={words.title} lead={words.lead} />
      <ContentNav manifest={manifest} current="home" />
      {summary instanceof ApiError ? (
        <Problem error={summary} />
      ) : summary ? (
        <div className="grid gap-5 min-[720px]:grid-cols-2 min-[1180px]:grid-cols-3">
          <Card>
            <CardHeader>
              <CardTitle>{words.home.reportsTitle}</CardTitle>
            </CardHeader>
            <CardContent>
              {summary.reports_open.total ? (
                <>
                  <p>{words.home.reportsTotal(summary.reports_open.total)}</p>
                  <ul className="m-0 flex list-none flex-col gap-1 p-0 text-[15px]">
                    {Object.entries(summary.reports_open.by_category).map(([category, count]) => (
                      <li key={category} className="flex justify-between gap-3">
                        <span>{labelOf(words.reports.categories, category)}</span>
                        <span className="font-mono">{count}</span>
                      </li>
                    ))}
                  </ul>
                </>
              ) : (
                <p className="text-muted-foreground">{words.home.reportsNone}</p>
              )}
              <Link href="/content/reports/" className="font-semibold">
                {words.home.reportsLink}
              </Link>
            </CardContent>
          </Card>
          {summary.reviews_waiting !== null ? (
            <Card>
              <CardHeader>
                <CardTitle>{words.home.reviewsTitle}</CardTitle>
              </CardHeader>
              <CardContent>
                <p>{words.home.reviewsWaiting(summary.reviews_waiting)}</p>
                {summary.reviews_mine !== null ? <p>{words.home.reviewsMine(summary.reviews_mine)}</p> : null}
                <Link href="/content/reviews/?mine=true" className="font-semibold">
                  {words.home.reviewsLink}
                </Link>
              </CardContent>
            </Card>
          ) : null}
          {summary.drafts !== null ? (
            <Card>
              <CardHeader>
                <CardTitle>{words.home.draftsTitle}</CardTitle>
              </CardHeader>
              <CardContent>
                <p>{words.home.drafts(summary.drafts)}</p>
                <Link href="/content/papers/?changed=true" className="font-semibold">
                  {words.home.draftsLink}
                </Link>
              </CardContent>
            </Card>
          ) : null}
          {summary.legal_deposits_missing !== null ? (
            <Card>
              <CardHeader>
                <CardTitle>{words.home.depositsTitle}</CardTitle>
              </CardHeader>
              <CardContent>
                {summary.legal_deposits_missing.length ? (
                  <ul className="m-0 flex list-none flex-col gap-2 p-0 text-[15px]">
                    {summary.legal_deposits_missing.map((book) => (
                      <li key={book.book} className="flex flex-col gap-0.5">
                        <Link href={`/content/books/${book.book}/`} className="font-semibold">
                          {book.title}
                        </Link>
                        <span className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                          {book.missing.map((library) => labelOf(words.deposits.libraries, library)).join(", ")}
                          {" · "}
                          {words.deposits.due(formatDate(book.due_on))}
                          {book.overdue ? <StatusChip tone="bad">{words.deposits.overdue}</StatusChip> : null}
                        </span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-muted-foreground">{words.home.depositsNone}</p>
                )}
                <Link href="/content/legal-deposits/" className="font-semibold">
                  {words.home.depositsLink}
                </Link>
              </CardContent>
            </Card>
          ) : null}
          {has(manifest, P.papersView) ? (
            <Card>
              <CardHeader>
                <CardTitle>{words.home.importTitle}</CardTitle>
              </CardHeader>
              <CardContent>
                {summary.last_import ? (
                  <p>
                    {labelOf(words.subjectNames, String((summary.last_import.params as { subject?: string })?.subject ?? ""))}
                    {" · "}
                    {labelOf(words.imports.kinds, String(summary.last_import.dry_run))}
                    {" · "}
                    {labelOf(copy.jobs.states, summary.last_import.state)}
                    {" · "}
                    {formatDateTime(summary.last_import.created)}
                  </p>
                ) : (
                  <p className="text-muted-foreground">{words.home.importNone}</p>
                )}
                <Link href="/content/imports/" className="font-semibold">
                  {words.home.importLink}
                </Link>
              </CardContent>
            </Card>
          ) : null}
        </div>
      ) : null}
    </>
  );
}
