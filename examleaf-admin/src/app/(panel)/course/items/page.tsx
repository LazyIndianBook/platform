// /course/items/: the quiz bank (GET course/items/), its filters in the address (subject, kind, difficulty, Bloom
// level, source, the item analysis' flags, an open report, words of the item) and saved views; the statistics columns
// with "N/A" under 30 learners; the chosen items' metadata changed together, a dry run first.
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Problem } from "@/components/data/problem";
import { BankTable } from "@/components/modules/course/bank-table";
import { CourseNav } from "@/components/modules/course/nav";
import { PageHeader } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, type SearchParams, staffPage } from "@/lib/api/page";
import { listItems, listSavedViews } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.course.bank.title };

const FILTERS = ["q", "subject", "kind", "difficulty", "bloom", "source", "flags", "flagged", "chapter", "cursor"];

export default async function BankPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/course/items/", params));
  if (!has(manifest, P.itemsView)) notFound();
  const filters = Object.fromEntries(FILTERS.map((name) => [name, param(params, name) || undefined]));
  const [page, views] = await Promise.all([
    attempt(listItems(filters, transport), path),
    has(manifest, P.savedViewsView) ? attempt(listSavedViews("course-items", transport), path) : null,
  ]);
  return (
    <>
      <PageHeader eyebrow={copy.course.title} title={copy.course.bank.title} lead={copy.course.bank.lead} />
      <CourseNav manifest={manifest} current="items" />
      {page instanceof ApiError ? (
        <Problem error={page} />
      ) : (
        <BankTable
          rows={page.results}
          next={page.next}
          previous={page.previous}
          views={views instanceof ApiError ? null : views}
        />
      )}
    </>
  );
}
