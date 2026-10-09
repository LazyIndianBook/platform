// /support/export/: the grievance register (a dated CSV of the complaints received, acknowledged and resolved, with the
// days taken and the NCH dockets; no personal data) as a background job (POST jobs/, staff.export_grievances), and the
// person's earlier exports (GET jobs/?kind=grievance_export&mine=true).
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Problem } from "@/components/data/problem";
import { GrievanceRegister } from "@/components/modules/support/register";
import { PageHeader } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, staffPage } from "@/lib/api/page";
import { listJobs } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.support.register };

export default async function GrievanceRegisterPage() {
  const { manifest, transport, path } = await staffPage("/support/export/");
  if (!has(manifest, P.grievancesExport)) notFound();
  const jobs = has(manifest, P.jobsView)
    ? await attempt(listJobs({ kind: "grievance_export", mine: true, page_size: 10 }, transport), path)
    : null;
  return (
    <>
      <PageHeader
        title={copy.support.register}
        lead={copy.support.registerLead}
        back={{ href: "/support/", label: copy.support.title }}
      />
      {jobs instanceof ApiError ? <Problem error={jobs} what={copy.support.registerJobs} /> : null}
      <GrievanceRegister jobs={jobs && !(jobs instanceof ApiError) ? jobs.results : []} />
    </>
  );
}
