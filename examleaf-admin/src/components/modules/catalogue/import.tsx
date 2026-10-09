"use client";

// Products in a spreadsheet, the admin's export format with the courier's columns. The import: a CSV uploaded and its
// dry run (POST catalogue/import/, a job: what each row would make, change or leave, a price that would wait for its
// approval, each row's error), then its apply naming that dry run (POST jobs/ product_import), the same file within a
// day: each row through the panel's own rules, stock never imported. The export: the list's filters as a job (POST
// jobs/ product_export), its file through the job's link, cells that would start a formula escaped; above your
// export_rows an approver first.
import { useState } from "react";

import { JobProgress } from "@/components/data/job-progress";
import { ActionForm, formText } from "@/components/forms/action-form";
import { fieldError, useAction } from "@/components/forms/use-action";
import { Button } from "@/components/ui/button";
import { Field, FormGrid } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { ApiError, errorText } from "@/lib/api/errors";
import { type Job, startCatalogueJob, uploadProductImport } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatNumber } from "@/lib/format";

type Counts = Record<"created" | "updated" | "unchanged" | "errors" | "prices_waiting", number>;
type Row = { line: number; slug: string; outcome: string; fields: string[]; price: string | null };

/** A product_import job's result, read with care (the schema types it as any JSON). */
export function importResult(job: Pick<Job, "result">): { counts: Counts; rows: Row[] } {
  const result = (job.result ?? {}) as { counts?: Partial<Counts>; rows?: unknown };
  const count = (name: keyof Counts) => Number(result.counts?.[name] ?? 0) || 0;
  const rows = Array.isArray(result.rows) ? (result.rows as Row[]) : [];
  return {
    counts: {
      created: count("created"),
      updated: count("updated"),
      unchanged: count("unchanged"),
      errors: count("errors"),
      prices_waiting: count("prices_waiting"),
    },
    rows,
  };
}

/** The file a dry run read, for its apply. */
const fileOf = (job: Pick<Job, "params">) => String((job.params as { file?: unknown } | null)?.file ?? "");

export function ImportOutcome({ job }: { job: Pick<Job, "result" | "dry_run"> }) {
  const { counts, rows } = importResult(job);
  return (
    <div className="flex flex-col gap-4">
      <dl className="m-0 grid grid-cols-[repeat(auto-fit,minmax(min(140px,100%),1fr))] gap-3">
        {(Object.keys(counts) as (keyof Counts)[]).map((name) => (
          <div key={name} className="rounded-lg border border-border bg-card p-3">
            <dt className="text-sm text-muted-foreground">{copy.catalogue.importCounts[name]}</dt>
            <dd className="m-0 font-mono text-xl font-semibold">{formatNumber(counts[name])}</dd>
          </div>
        ))}
      </dl>
      {rows.length ? (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full border-collapse text-left text-[15px]">
            <caption className="sr-only">{job.dry_run ? copy.catalogue.dryRows : copy.catalogue.appliedRows}</caption>
            <thead>
              <tr className="border-b border-border">
                <th scope="col" className="p-2.5">
                  {copy.catalogue.columns.line}
                </th>
                <th scope="col" className="p-2.5">
                  {copy.catalogue.columns.product}
                </th>
                <th scope="col" className="p-2.5">
                  {copy.catalogue.columns.outcome}
                </th>
                <th scope="col" className="p-2.5">
                  {copy.catalogue.columns.fields}
                </th>
                <th scope="col" className="p-2.5">
                  {copy.catalogue.columns.priceWay}
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={`${row.line}-${row.slug}`} className="border-b border-border last:border-0">
                  <td className="p-2.5 font-mono">{row.line}</td>
                  <td className="p-2.5 font-mono break-all">{row.slug}</td>
                  <td className="p-2.5">{labelOf(copy.catalogue.outcomes, row.outcome)}</td>
                  <td className="p-2.5">{row.fields.join(", ")}</td>
                  <td className="p-2.5">{row.price ? labelOf(copy.catalogue.priceWays, row.price) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}

export function ImportPanel() {
  const [dry, setDry] = useState<Job | null>(null);
  const [dryDone, setDryDone] = useState<Job | null>(null);
  const [applied, setApplied] = useState<Job | null>(null);
  const [appliedDone, setAppliedDone] = useState<Job | null>(null);
  const applying = useAction();
  const start = (job: Job) => {
    setDry(job);
    setDryDone(null);
    setApplied(null);
    setAppliedDone(null);
  };
  return (
    <div className="flex flex-col gap-6">
      <ActionForm
        id="import"
        submitLabel={copy.catalogue.runDryRun}
        success={copy.catalogue.dryRunStarted}
        labels={{ file: copy.catalogue.fields.file }}
        onSubmit={async (form) => {
          const file = form.get("file");
          if (!(file instanceof File) || !file.size)
            throw new ApiError(400, "invalid", copy.catalogue.chooseFile, { file: [copy.catalogue.chooseFile] });
          return uploadProductImport(file);
        }}
        onDone={(result) => start(result as Job)}
      >
        {(error) => (
          <Field
            id="import-file"
            label={copy.catalogue.fields.file}
            help={copy.catalogue.help.importFile}
            error={fieldError(error, "file")}
          >
            <Input name="file" type="file" accept=".csv,text/csv" className="py-2.5" />
          </Field>
        )}
      </ActionForm>
      {dry ? (
        <section aria-label={copy.catalogue.dryRun} className="flex flex-col gap-4">
          <h3 className="m-0 font-head text-lg font-semibold">{copy.catalogue.dryRun}</h3>
          <JobProgress key={dry.id} job={dry} onDone={(job) => setDryDone(job)} />
          {dryDone?.state === "done" ? (
            <>
              <ImportOutcome job={dryDone} />
              {applied ? null : (
                <div className="flex flex-wrap items-center gap-3">
                  <Button
                    busy={applying.busy}
                    onClick={() =>
                      applying.run(async () =>
                        setApplied(
                          await startCatalogueJob("product_import", { file: fileOf(dryDone), dry_run_job: dryDone.id }),
                        ),
                      )
                    }
                  >
                    {copy.catalogue.apply}
                  </Button>
                  <span className="text-sm text-muted-foreground">{copy.catalogue.applyHelp}</span>
                  {applying.error ? (
                    <span className="text-sm font-semibold text-destructive">{errorText(applying.error)}</span>
                  ) : null}
                </div>
              )}
            </>
          ) : null}
        </section>
      ) : null}
      {applied ? (
        <section aria-label={copy.catalogue.applied} className="flex flex-col gap-4">
          <h3 className="m-0 font-head text-lg font-semibold">{copy.catalogue.applied}</h3>
          <JobProgress key={applied.id} job={applied} onDone={(job) => setAppliedDone(job)} />
          {appliedDone?.state === "done" ? <ImportOutcome job={appliedDone} /> : null}
        </section>
      ) : null}
    </div>
  );
}

/** The export's filters, as the product list names them (empty: every product). */
export function exportFilters(form: FormData): Record<string, string> {
  const names = ["kind", "published", "stock", "tax_problem", "incomplete", "q"];
  return Object.fromEntries(names.map((name) => [name, formText(form, name)]).filter(([, value]) => value));
}

export function ExportPanel() {
  const [job, setJob] = useState<Job | null>(null);
  const f = copy.catalogue.filters;
  const any = <option value="">{copy.filters.any}</option>;
  return (
    <div className="flex flex-col gap-4">
      <ActionForm
        id="export"
        submitLabel={copy.catalogue.export}
        success={copy.catalogue.exportStarted}
        labels={{ "params.filters": copy.catalogue.filters.label }}
        onSubmit={(form) => startCatalogueJob("product_export", { filters: exportFilters(form) })}
        onDone={(result) => setJob(result as Job)}
      >
        {(error) => (
          <>
            <FormGrid>
              <Field id="export-q" label={copy.catalogue.search} optional error={fieldError(error, "params.filters.q")}>
                <Input name="q" autoComplete="off" />
              </Field>
              <Field id="export-kind" label={copy.catalogue.columns.kind} optional>
                <Select name="kind" defaultValue="">
                  {any}
                  {Object.entries(copy.catalogue.kinds).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field id="export-published" label={f.published} optional>
                <Select name="published" defaultValue="">
                  {any}
                  <option value="true">{copy.catalogue.onSale}</option>
                  <option value="false">{copy.catalogue.offSale}</option>
                </Select>
              </Field>
            </FormGrid>
            <FormGrid>
              <Field id="export-stock" label={copy.catalogue.columns.stock} optional>
                <Select name="stock" defaultValue="">
                  {any}
                  {Object.entries(copy.catalogue.bookStates).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field id="export-tax_problem" label={f.taxProblem} optional>
                <Select name="tax_problem" defaultValue="">
                  {any}
                  <option value="true">{copy.catalogue.onlyThose}</option>
                </Select>
              </Field>
              <Field id="export-incomplete" label={f.incomplete} optional>
                <Select name="incomplete" defaultValue="">
                  {any}
                  <option value="true">{copy.catalogue.onlyThose}</option>
                </Select>
              </Field>
            </FormGrid>
          </>
        )}
      </ActionForm>
      {job ? <JobProgress key={job.id} job={job} /> : null}
    </div>
  );
}
