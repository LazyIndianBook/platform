// /privacy/processors/: the processor register (GET processors/), which the access exports' recipients list and a
// cross-border switch read; adding one (POST processors/, #new).
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
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
        ) : processors.length === 0 ? (
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
              </tr>
            </thead>
            <tbody>
              {processors.map((processor) => (
                <tr key={processor.id}>
                  <TableCell className="font-semibold">{processor.name}</TableCell>
                  <TableCell>{processor.purpose}</TableCell>
                  <TableCell>{processor.country}</TableCell>
                  <TableCell>{processor.data_categories.join(", ")}</TableCell>
                  <TableCell>
                    {processor.contract_until ? formatDate(processor.contract_until) : copy.common.none}
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
