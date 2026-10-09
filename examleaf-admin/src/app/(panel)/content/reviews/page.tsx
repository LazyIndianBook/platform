// /content/reviews/: the review queue (GET content/reviews/), oldest first: "Waiting for me" (?mine=true: open, for me or
// nobody, never my own edit) and the open, closed, by subject or state; each opens with its diff and preview.
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Problem } from "@/components/data/problem";
import { ContentNav } from "@/components/modules/content/nav";
import { ReviewsTable } from "@/components/modules/content/tables";
import { PageHeader } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, type SearchParams, staffPage } from "@/lib/api/page";
import { listReviews, listSavedViews } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.content.reviews.title };

export default async function ReviewsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/content/reviews/", params));
  if (!has(manifest, P.reviewsView)) notFound();
  const filters = Object.fromEntries(
    ["mine", "open", "subject", "state", "cursor"].map((name) => [name, param(params, name)]),
  );
  const [page, views] = await Promise.all([
    attempt(listReviews(filters, transport), path),
    has(manifest, P.savedViewsView) ? attempt(listSavedViews("content-reviews", transport), path) : null,
  ]);
  return (
    <>
      <PageHeader eyebrow={copy.content.title} title={copy.content.reviews.title} lead={copy.content.reviews.lead} />
      <ContentNav manifest={manifest} current="reviews" />
      {page instanceof ApiError ? (
        <Problem error={page} />
      ) : (
        <ReviewsTable
          rows={page.results}
          next={page.next}
          previous={page.previous}
          views={views instanceof ApiError ? null : views}
        />
      )}
    </>
  );
}
