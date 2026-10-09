"use client";

// The system's pages' two forms: a restore drill recorded (POST system/backups/drills/: staff.manage_system, a recent
// authentication; the day, what was restored, from which backup, whether it worked, how long, notes) and a document
// looked up among the sync's links (GET system/sync/links/?q=: a reference, an ERPNext name, an object's id).
import { useState } from "react";

import { ActionForm, formText } from "@/components/forms/action-form";
import { ErrorSummary } from "@/components/forms/error-summary";
import { fieldError, useAction } from "@/components/forms/use-action";
import { useCan } from "@/components/shell/manifest";
import { Button } from "@/components/ui/button";
import { Field, FormGrid } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { Table, TableCell, TableHead } from "@/components/ui/table";
import { type ErpLinkRow, findErpLinks, recordDrill, type RestoreDrill } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { formatDateTime } from "@/lib/format";
import { P } from "@/lib/modules";

const words = copy.management;

export function DrillForm({ latest }: { latest: string }) {
  const can = useCan();
  if (!can(P.systemManage)) return null;
  const fields = words.backups.fields;
  return (
    <ActionForm
      id="restore-drill"
      submitLabel={words.backups.recordButton}
      success={words.backups.recorded}
      labels={fields}
      onSubmit={(form) =>
        recordDrill({
          performed_on: formText(form, "performed_on"),
          engine: formText(form, "engine") as RestoreDrill["engine"],
          backup: formText(form, "backup"),
          result: formText(form, "result") as RestoreDrill["result"],
          duration_minutes: Number(formText(form, "duration_minutes")),
          notes: formText(form, "notes"),
        })
      }
    >
      {(error) => (
        <>
          <h3 className="m-0 font-head text-lg">{words.backups.record}</h3>
          <FormGrid>
            <Field
              id="restore-drill-performed_on"
              label={fields.performed_on}
              error={fieldError(error, "performed_on")}
            >
              <Input name="performed_on" type="date" aria-required="true" />
            </Field>
            <Field id="restore-drill-engine" label={fields.engine} error={fieldError(error, "engine")}>
              <Select name="engine" defaultValue="platform">
                {Object.entries(words.backups.engines).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field id="restore-drill-result" label={fields.result} error={fieldError(error, "result")}>
              <Select name="result" defaultValue="passed">
                {Object.entries(words.backups.results).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field
              id="restore-drill-duration_minutes"
              label={fields.duration_minutes}
              error={fieldError(error, "duration_minutes")}
            >
              <Input name="duration_minutes" type="number" min={0} inputMode="numeric" aria-required="true" />
            </Field>
          </FormGrid>
          <Field id="restore-drill-backup" label={fields.backup} error={fieldError(error, "backup")}>
            <Input name="backup" defaultValue={latest} autoComplete="off" aria-required="true" className="font-mono" />
          </Field>
          <Field id="restore-drill-notes" label={fields.notes} optional error={fieldError(error, "notes")}>
            <Textarea name="notes" rows={2} />
          </Field>
        </>
      )}
    </ActionForm>
  );
}

export function LinkSearch() {
  const { run, busy, error } = useAction();
  const [rows, setRows] = useState<ErpLinkRow[] | null>(null);
  const sync = words.sync;
  return (
    <div className="flex flex-col gap-3">
      <form
        noValidate
        className="flex flex-wrap items-end gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          const q = String(new FormData(event.currentTarget).get("q") ?? "").trim();
          void run(async () => setRows(await findErpLinks(q)));
        }}
      >
        <Field id="erp-link-q" label={sync.query} help={sync.linksLead} error={fieldError(error, "q")}>
          <Input name="q" autoComplete="off" spellCheck={false} />
        </Field>
        <Button type="submit" variant="secondary" busy={busy}>
          {sync.find}
        </Button>
      </form>
      <ErrorSummary error={error} />
      <div role="status">
        {rows === null ? null : rows.length ? (
          <Table caption={copy.table.region(sync.links)}>
            <thead>
              <tr>
                <TableHead>{sync.linkColumns.reference}</TableHead>
                <TableHead>{sync.linkColumns.object}</TableHead>
                <TableHead>{sync.linkColumns.document}</TableHead>
                <TableHead>{sync.linkColumns.synced}</TableHead>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.examleaf_ref}>
                  <TableCell>
                    <code>{row.examleaf_ref}</code>
                  </TableCell>
                  <TableCell>
                    {row.model} #{row.object_id}
                  </TableCell>
                  <TableCell>
                    {row.doctype} <code>{row.name}</code>
                  </TableCell>
                  <TableCell>{formatDateTime(row.synced_at)}</TableCell>
                </tr>
              ))}
            </tbody>
          </Table>
        ) : (
          <p className="m-0 text-[15px] text-muted-foreground">{sync.noLinks}</p>
        )}
      </div>
    </div>
  );
}
