// /privacy/processors/: the processor register (GET processors/): who processes personal data for ExamLeaf, for
// what, where, under which agreement; adding one (POST processors/, #new).
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { StatusChip } from "@/components/data/status-chip";
import { NewProcessorForm } from "@/components/modules/privacy/processors";
import { PageHeader, Section } from "@/components/shell/page-header";
import { EmptyState } from "@/components/ui/empty-state";
import { Table, TableCell, TableHead } from "@/components/ui/table";
import { ApiError } from "@/lib/api/errors";
import { attempt, staffPage } from "@/lib/api/page";
import { listProcessors } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { formatDate } from "@/lib/format";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.privacy.processorsTitle };

export default async function ProcessorsPage() {
  const { manifest, transport, path } = await staffPage("/privacy/processors/");
  const processors = await attempt(listProcessors(transport), path);
  const adding = has(manifest, P.processorsAdd);
  return (
    <>
      <PageHeader
        title={copy.privacy.processorsTitle}
        lead={copy.privacy.processorsLead}
        actions={
          adding ? (
            <a href="#new" className="inline-flex min-h-11 items-center font-semibold">
              {copy.privacy.processorNew}
            </a>
          ) : null
        }
      />
      <div className="flex flex-col gap-10">
        {processors instanceof ApiError ? (
          <Problem error={processors} />
        ) : processors.results.length === 0 ? (
          <EmptyState title={copy.privacy.emptyProcessorsTitle}>
            <p>{copy.privacy.emptyProcessorsText}</p>
          </EmptyState>
        ) : (
          <Table caption={copy.privacy.processorsTitle}>
            <thead>
              <tr>
                <TableHead>{copy.privacy.processorColumns.name}</TableHead>
                <TableHead>{copy.privacy.processorColumns.purpose}</TableHead>
                <TableHead>{copy.privacy.processorColumns.country}</TableHead>
                <TableHead>{copy.privacy.processorColumns.categories}</TableHead>
                <TableHead>{copy.privacy.processorColumns.contract}</TableHead>
                <TableHead>{copy.privacy.processorColumns.active}</TableHead>
              </tr>
            </thead>
            <tbody>
              {processors.results.map((processor) => (
                <tr key={processor.id}>
                  <TableCell className="font-semibold">{processor.name}</TableCell>
                  <TableCell>{processor.purpose}</TableCell>
                  <TableCell>{processor.country}</TableCell>
                  <TableCell>{processor.data_categories}</TableCell>
                  <TableCell>
                    {processor.contract_ends_on ? formatDate(processor.contract_ends_on) : copy.common.none}
                  </TableCell>
                  <TableCell>
                    <StatusChip tone={processor.active === false ? "stopped" : "good"}>
                      {processor.active === false ? copy.common.no : copy.common.yes}
                    </StatusChip>
                  </TableCell>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
        {adding ? (
          <Section id="new" title={copy.privacy.processorTitle}>
            <NewProcessorForm />
          </Section>
        ) : null}
      </div>
    </>
  );
}
