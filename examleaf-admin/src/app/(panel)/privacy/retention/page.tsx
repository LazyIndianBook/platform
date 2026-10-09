// /privacy/retention/: the retention schedule as the backend keeps it in code (GET privacy/retention/, examleaf-web's
// examleaf/retention.py): for each kind of record the law's minimum today with its source and the day it changes,
// what this site keeps, and what deletes it. Read-only: the schedule changes in code, with its tests.
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { PageHeader } from "@/components/shell/page-header";
import { Table, TableCell, TableHead } from "@/components/ui/table";
import { ApiError } from "@/lib/api/errors";
import { attempt, staffPage } from "@/lib/api/page";
import { getRetention } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { formatDate } from "@/lib/format";

export const metadata: Metadata = { title: copy.legal.retentionTitle };

export default async function RetentionPage() {
  const { transport, path } = await staffPage("/privacy/retention/");
  const rules = await attempt(getRetention(transport), path);
  return (
    <>
      <PageHeader title={copy.legal.retentionTitle} lead={copy.legal.retentionLead} />
      {rules instanceof ApiError ? (
        <Problem error={rules} />
      ) : (
        <Table caption={copy.legal.retentionTitle} className="min-w-[48rem]">
          <thead>
            <tr>
              <TableHead>{copy.legal.retentionColumns.records}</TableHead>
              <TableHead>{copy.legal.retentionColumns.minimum}</TableHead>
              <TableHead>{copy.legal.retentionColumns.keep}</TableHead>
              <TableHead>{copy.legal.retentionColumns.by}</TableHead>
            </tr>
          </thead>
          <tbody>
            {rules.map((rule) => (
              <tr key={rule.key}>
                <TableCell>{rule.records}</TableCell>
                <TableCell>
                  <span className="block font-semibold">{rule.minimum}</span>
                  <span className="block text-sm text-muted-foreground">{rule.source}</span>
                  {rule.changes_on && rule.next_minimum ? (
                    <span className="block text-sm">
                      {copy.legal.changesOn(formatDate(rule.changes_on), rule.next_minimum)}
                    </span>
                  ) : null}
                </TableCell>
                <TableCell>
                  {rule.keep}
                  {rule.trim_days ? (
                    <span className="block text-sm text-muted-foreground">{copy.legal.trimmed(rule.trim_days)}</span>
                  ) : null}
                </TableCell>
                <TableCell className="text-sm">{rule.enforced_by}</TableCell>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </>
  );
}
