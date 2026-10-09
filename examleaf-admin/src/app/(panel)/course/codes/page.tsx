// /course/codes/: book codes. The lookup box (a typed or scanned code answered in one line: unused, redeemed by whom
// as a link, void, or unknown), a print run's codes made with the printer's file, and the print runs (GET
// course/codes/batches/: filters by subject, state and label; saved views), each its page. Each part only for whom
// the manifest opens it: SUPPORT looks codes up, SALES makes a school order's print run, the owners void.
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Problem } from "@/components/data/problem";
import { BatchesTable, CodeLookup, MakeBatch } from "@/components/modules/course/codes";
import { CourseNav } from "@/components/modules/course/nav";
import { PageHeader, Section } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, type SearchParams, staffPage } from "@/lib/api/page";
import { listBatches, listSavedViews } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, hasAny, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.course.codes.title };

const words = copy.course.codes;

export default async function CodesPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/course/codes/", params));
  if (!hasAny(manifest, [P.batchesView, P.bookCodesView])) notFound();
  const batches = has(manifest, P.batchesView);
  const filters = Object.fromEntries(
    ["q", "subject", "state", "cursor"].map((name) => [name, param(params, name) || undefined]),
  );
  const [page, views] = await Promise.all([
    batches ? attempt(listBatches(filters, transport), path) : null,
    batches && has(manifest, P.savedViewsView) ? attempt(listSavedViews("course-batches", transport), path) : null,
  ]);
  return (
    <>
      <PageHeader eyebrow={copy.course.title} title={words.title} lead={words.lead} />
      <CourseNav manifest={manifest} current="codes" />
      <div className="flex flex-col gap-10">
        {has(manifest, P.bookCodesView) ? (
          <Section id="lookup" title={words.lookup} lead={words.lookupLead}>
            <CodeLookup />
          </Section>
        ) : null}
        {has(manifest, P.codesMake) ? (
          <Section id="make" title={words.make} lead={words.makeLead}>
            <MakeBatch />
          </Section>
        ) : null}
        {page ? (
          <Section
            id="batches"
            title={words.batches}
            actions={
              <Link href="/course/report/" className="font-semibold">
                {words.report}
              </Link>
            }
          >
            {page instanceof ApiError ? (
              <Problem error={page} />
            ) : (
              <BatchesTable
                rows={page.results}
                next={page.next}
                previous={page.previous}
                views={views instanceof ApiError ? null : views}
              />
            )}
          </Section>
        ) : null}
      </div>
    </>
  );
}
