// /course/entitlements/: access to the course (GET course/entitlements/): filtered by subject, source and state, or
// found by an account's whole email address (a lookup the API records by its hash); one row extended or revoked at
// once, many as a bulk job with a dry run; access given to one account, or to many by their numbers.
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Problem } from "@/components/data/problem";
import { AccessTable, GrantForm } from "@/components/modules/course/access";
import { CourseNav } from "@/components/modules/course/nav";
import { PageHeader, Section } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, type SearchParams, staffPage } from "@/lib/api/page";
import { listEntitlements, listSavedViews } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.course.access.title };

const words = copy.course.access;

export default async function AccessPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/course/entitlements/", params));
  if (!has(manifest, P.accessView)) notFound();
  const filters = Object.fromEntries(
    ["q", "subject", "source", "state", "cursor"].map((name) => [name, param(params, name) || undefined]),
  );
  const [page, views] = await Promise.all([
    attempt(listEntitlements(filters, transport), path),
    has(manifest, P.savedViewsView) ? attempt(listSavedViews("course-entitlements", transport), path) : null,
  ]);
  return (
    <>
      <PageHeader eyebrow={copy.course.title} title={words.title} lead={words.lead} />
      <CourseNav manifest={manifest} current="access" />
      <div className="flex flex-col gap-8">
        {page instanceof ApiError ? (
          <Problem error={page} />
        ) : (
          <AccessTable
            rows={page.results}
            next={page.next}
            previous={page.previous}
            views={views instanceof ApiError ? null : views}
          />
        )}
        {has(manifest, P.accessGrant) ? (
          <Section id="grant" title={words.grant} lead={words.grantLead}>
            <GrantForm />
          </Section>
        ) : null}
      </div>
    </>
  );
}
