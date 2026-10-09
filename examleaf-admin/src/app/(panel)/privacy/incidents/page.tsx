// /privacy/incidents/: the breach register with its 6-hour and 72-hour clocks (GET incidents/), and recording a new
// incident (POST incidents/, #new) as soon as it is noticed.
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { IncidentsTable, NewIncidentForm } from "@/components/modules/privacy/incidents";
import { PageHeader, Section } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, requestTime, type SearchParams, staffPage } from "@/lib/api/page";
import { listIncidents, listSavedViews } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.privacy.incidentsTitle };

export default async function IncidentsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/privacy/incidents/", params));
  const [page, views] = await Promise.all([
    attempt(listIncidents({ state: param(params, "state"), cursor: param(params, "cursor") }, transport), path),
    attempt(listSavedViews("incidents", transport), path),
  ]);
  const now = requestTime();
  const recording = has(manifest, P.incidentsAdd);
  return (
    <>
      <PageHeader
        title={copy.privacy.incidentsTitle}
        lead={copy.privacy.incidentsLead}
        actions={
          recording ? (
            <a href="#new" className="inline-flex min-h-11 items-center font-semibold">
              {copy.privacy.incidentNew}
            </a>
          ) : null
        }
      />
      <div className="flex flex-col gap-10">
        {page instanceof ApiError ? (
          <Problem error={page} />
        ) : (
          <IncidentsTable
            rows={page.results}
            next={page.next}
            previous={page.previous}
            views={views instanceof ApiError ? null : views}
            now={now}
          />
        )}
        {recording ? (
          <Section id="new" title={copy.privacy.incidentTitle} lead={copy.privacy.incidentText}>
            <NewIncidentForm now={now} />
          </Section>
        ) : null}
      </div>
    </>
  );
}
