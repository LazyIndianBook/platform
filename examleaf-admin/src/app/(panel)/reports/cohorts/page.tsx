// /reports/cohorts/: how many learners stay active week by week, by the month their course opened and how (GET
// insights/cohorts/, the insights' own list, drawn here and not rebuilt). Counted overnight while the learners' exam is
// ahead; a cohort week of fewer learners than the minimum shows no shares ("fewer than 10"); no row names a learner.
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Problem } from "@/components/data/problem";
import { ExportReport } from "@/components/modules/reports/export-report";
import { CohortTable } from "@/components/modules/reports/insights";
import { ReportHead } from "@/components/modules/reports/parts";
import { ReportPage } from "@/components/modules/reports/report-page";
import { opens } from "@/components/modules/reports/reports-tabs";
import { Pagination } from "@/components/ui/pagination";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, type SearchParams, staffPage } from "@/lib/api/page";
import { listCohorts } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { formatDateTime } from "@/lib/format";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.reports.cohorts.title };

const SIZE = 50;

export default async function CohortsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/reports/cohorts/", params));
  if (!opens(manifest, "cohorts")) notFound();
  const words = copy.reports.cohorts;
  const asked = Number(param(params, "page"));
  const page = Number.isInteger(asked) && asked > 0 ? asked : 1;
  const cohorts = await attempt(listCohorts({ page, page_size: SIZE }, transport), path);
  return (
    <ReportPage title={words.title} lead={words.lead} manifest={manifest} current="cohorts">
      {cohorts instanceof ApiError ? (
        <Problem error={cohorts} />
      ) : (
        <>
          <ReportHead
            report={{
              definition: `${cohorts.method}. ${words.definition}`,
              columns: [],
              as_of: cohorts.data_as_of ?? "",
              test_mode: false,
              period: null,
            }}
            counted={cohorts.data_as_of ? words.countedAt(formatDateTime(cohorts.data_as_of)) : words.notCounted}
          />
          <CohortTable page={cohorts} />
          <Pagination
            page={page}
            pages={Math.ceil(cohorts.count / SIZE)}
            href={(next) => `/reports/cohorts/?page=${next}`}
          />
          {has(manifest, P.exportReport) ? <ExportReport report="cohorts" filters={{}} /> : null}
        </>
      )}
    </ReportPage>
  );
}
