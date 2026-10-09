// /privacy/holds/: the legal holds (GET privacy/holds/?active=&reason=&target_type=&user=), newest first, and adding
// one on an account or a record (POST privacy/holds/, #new) for whoever may.
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { HoldsTable, NewHoldForm } from "@/components/modules/privacy/holds";
import { PageHeader, Section } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, requestTime, type SearchParams, staffPage } from "@/lib/api/page";
import { listHolds, listSavedViews } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { toLocalInput } from "@/lib/format";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.legal.holdsTitle };

export default async function HoldsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/privacy/holds/", params));
  const [page, views] = await Promise.all([
    attempt(
      listHolds(
        {
          active: param(params, "active"),
          reason: param(params, "reason"),
          target_type: param(params, "target_type"),
          user: param(params, "user"),
          cursor: param(params, "cursor"),
        },
        transport,
      ),
      path,
    ),
    has(manifest, P.savedViewsView) ? attempt(listSavedViews("legal-holds", transport), path) : null,
  ]);
  const adding = has(manifest, P.holdsManage);
  return (
    <>
      <PageHeader
        title={copy.legal.holdsTitle}
        lead={copy.legal.holdsLead}
        actions={
          adding ? (
            <a href="#new" className="inline-flex min-h-11 items-center font-semibold">
              {copy.legal.holdNew}
            </a>
          ) : null
        }
      />
      <div className="flex flex-col gap-10">
        {page instanceof ApiError ? (
          <Problem error={page} />
        ) : (
          <HoldsTable
            rows={page.results}
            next={page.next}
            previous={page.previous}
            views={views instanceof ApiError ? null : views}
          />
        )}
        {adding ? (
          <Section id="new" title={copy.legal.holdNew} lead={copy.legal.holdNewLead}>
            <NewHoldForm today={toLocalInput(requestTime()).slice(0, 10)} />
          </Section>
        ) : null}
      </div>
    </>
  );
}
