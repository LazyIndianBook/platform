// /privacy/policies/: the legal pages (GET privacy/policies/: privacy, terms, refunds, shipping, contact), each with the
// version in force and its day, what it changed, a version waiting for its day, and the placeholders still to fill in.
import type { Metadata } from "next";
import Link from "next/link";

import { Problem } from "@/components/data/problem";
import { PageHeader } from "@/components/shell/page-header";
import { Table, TableCell, TableHead } from "@/components/ui/table";
import { ApiError } from "@/lib/api/errors";
import { attempt, staffPage } from "@/lib/api/page";
import { listPolicies } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { formatDate } from "@/lib/format";

export const metadata: Metadata = { title: copy.legal.policiesTitle };

export default async function PoliciesPage() {
  const { transport, path } = await staffPage("/privacy/policies/");
  const policies = await attempt(listPolicies(transport), path);
  return (
    <>
      <PageHeader title={copy.legal.policiesTitle} lead={copy.legal.policiesLead} />
      {policies instanceof ApiError ? (
        <Problem error={policies} />
      ) : (
        <Table caption={copy.legal.policiesTitle} className="min-w-[44rem]">
          <thead>
            <tr>
              <TableHead>{copy.legal.policyColumns.page}</TableHead>
              <TableHead>{copy.legal.policyColumns.version}</TableHead>
              <TableHead>{copy.legal.policyColumns.summary}</TableHead>
              <TableHead>{copy.legal.policyColumns.scheduled}</TableHead>
              <TableHead numeric>{copy.legal.policyColumns.fill}</TableHead>
            </tr>
          </thead>
          <tbody>
            {policies.map((policy) => (
              <tr key={policy.slug}>
                <TableCell>
                  <Link href={`/privacy/policies/${policy.slug}/`} className="font-semibold">
                    {policy.title}
                  </Link>
                </TableCell>
                <TableCell>{copy.legal.policyFrom(policy.number, formatDate(policy.effective_from))}</TableCell>
                <TableCell className="text-sm">{policy.summary || copy.common.none}</TableCell>
                <TableCell>
                  {policy.scheduled
                    ? copy.legal.scheduledLine(policy.scheduled.number, formatDate(policy.scheduled.effective_from))
                    : copy.legal.noneScheduled}
                </TableCell>
                <TableCell numeric>{policy.placeholders.toLocaleString("en-IN")}</TableCell>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </>
  );
}
