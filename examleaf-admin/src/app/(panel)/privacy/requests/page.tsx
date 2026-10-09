// /privacy/requests/: the data-rights queue with its clocks (GET data-requests/?state=&type=), and logging a request
// that came another way (POST data-requests/, #new).
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { LogRequestForm, RequestsTable } from "@/components/modules/privacy/requests";
import { PageHeader, Section } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, requestTime, type SearchParams, staffPage } from "@/lib/api/page";
import { listDataRequests, listSavedViews } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.privacy.requestsTitle };

export default async function DataRequestsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/privacy/requests/", params));
  const [page, views] = await Promise.all([
    attempt(
      listDataRequests(
        { state: param(params, "state"), type: param(params, "type"), cursor: param(params, "cursor") },
        transport,
      ),
      path,
    ),
    attempt(listSavedViews("data-requests", transport), path),
  ]);
  const now = requestTime();
  const logging = has(manifest, P.requestsAdd);
  return (
    <>
      <PageHeader
        title={copy.privacy.requestsTitle}
        lead={copy.privacy.requestsLead}
        actions={
          logging ? (
            <a href="#new" className="inline-flex min-h-11 items-center font-semibold">
              {copy.privacy.logRequest}
            </a>
          ) : null
        }
      />
      <div className="flex flex-col gap-10">
        {page instanceof ApiError ? (
          <Problem error={page} />
        ) : (
          <RequestsTable
            rows={page.results}
            next={page.next}
            previous={page.previous}
            views={views instanceof ApiError ? null : views}
            now={now}
          />
        )}
        {logging ? (
          <Section id="new" title={copy.privacy.logTitle} lead={copy.privacy.logText}>
            <LogRequestForm now={now} />
          </Section>
        ) : null}
      </div>
    </>
  );
}
