// /settings/templates/: the message templates (GET templates/): what the site sends by SMS, email and (Phase D)
// WhatsApp, with the DLT and MSG91 ids sent, its state, when it was last used (DLT deactivates a template unused for
// 90 days), its yearly self-certification and what to see to; add, change and a test to yourself for whoever may
// (components/modules/settings/templates.tsx).
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { StatusChip, type Tone } from "@/components/data/status-chip";
import { AddTemplate, EditTemplate, TestTemplate } from "@/components/modules/settings/templates";
import { PageHeader } from "@/components/shell/page-header";
import { EmptyState } from "@/components/ui/empty-state";
import { Table, TableCell, TableHead } from "@/components/ui/table";
import { ApiError } from "@/lib/api/errors";
import { attempt, requestTime, staffPage } from "@/lib/api/page";
import { listTemplates } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatAgo, formatDate } from "@/lib/format";

const words = copy.management.templates;
const TONE: Record<string, Tone> = {
  draft: "stopped",
  submitted: "waiting",
  approved: "good",
  rejected: "bad",
  paused: "waiting",
  deactivated: "stopped",
};

export const metadata: Metadata = { title: words.title };

export default async function TemplatesPage() {
  const { transport, path } = await staffPage("/settings/templates/");
  const templates = await attempt(listTemplates({}, transport), path);
  const now = requestTime();
  return (
    <>
      <PageHeader
        title={words.title}
        lead={words.lead}
        back={{ href: "/settings/", label: copy.settings.title }}
        actions={<AddTemplate />}
      />
      {templates instanceof ApiError ? (
        <Problem error={templates} />
      ) : templates.length ? (
        <Table caption={words.title}>
          <thead>
            <tr>
              <TableHead>{words.columns.event}</TableHead>
              <TableHead>{words.columns.state}</TableHead>
              <TableHead>{words.columns.ids}</TableHead>
              <TableHead>{words.columns.used}</TableHead>
              <TableHead>{words.columns.certified}</TableHead>
              <TableHead>{copy.common.actions}</TableHead>
            </tr>
          </thead>
          <tbody>
            {templates.map((template) => (
              <tr key={template.id}>
                <TableCell>
                  <code className="font-semibold">{template.event}</code>
                  <span className="block text-sm text-muted-foreground">
                    {labelOf(words.channels, template.channel)} · {labelOf(words.languages, template.language)} ·{" "}
                    {labelOf(words.categories, template.category)}
                  </span>
                  {template.warnings.length ? (
                    <ul className="m-0 mt-1 flex list-none flex-col gap-0.5 p-0 text-sm font-semibold text-destructive">
                      {template.warnings.map((warning) => (
                        <li key={warning}>{warning}</li>
                      ))}
                    </ul>
                  ) : null}
                </TableCell>
                <TableCell>
                  <StatusChip tone={TONE[template.approval_state ?? "draft"] ?? "stopped"}>
                    {labelOf(words.states, template.approval_state ?? "draft")}
                  </StatusChip>
                </TableCell>
                <TableCell>
                  <span className="flex flex-col text-sm">
                    {template.dlt_template_id ? <span>DLT {template.dlt_template_id}</span> : null}
                    {template.msg91_id ? <span>MSG91 {template.msg91_id}</span> : null}
                    {template.whatsapp_name ? <span>WhatsApp {template.whatsapp_name}</span> : null}
                    {template.header ? (
                      <span>
                        {template.header}
                        {template.header_suffix ? `-${template.header_suffix}` : ""}
                      </span>
                    ) : null}
                  </span>
                </TableCell>
                <TableCell>{template.last_used_at ? formatAgo(template.last_used_at, now) : words.neverUsed}</TableCell>
                <TableCell>
                  {template.self_certified_on ? formatDate(template.self_certified_on) : words.notCertified}
                </TableCell>
                <TableCell>
                  <span className="flex flex-wrap items-start gap-2">
                    <EditTemplate template={template} />
                    <TestTemplate template={template} />
                  </span>
                </TableCell>
              </tr>
            ))}
          </tbody>
        </Table>
      ) : (
        <EmptyState title={words.emptyTitle}>
          <p>{words.emptyText}</p>
        </EmptyState>
      )}
    </>
  );
}
