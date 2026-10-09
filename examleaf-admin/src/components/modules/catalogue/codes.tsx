"use client";

// A single-use coupon's codes (GET catalogue/coupons/{code}/codes/: used or not and by which order, never who) and a
// school's batch made by a job (POST jobs/ coupon_codes: how many, a prefix, the school's name): its progress, and its
// CSV for the school through the job's own link (its starter's, for a week). Above your bulk_rows the job waits for
// an approver first (the job says which change request).
import { useRouter } from "next/navigation";
import { useState } from "react";

import { type Column, DataTable } from "@/components/data/data-table";
import { JobProgress } from "@/components/data/job-progress";
import { StatusChip } from "@/components/data/status-chip";
import { ActionForm, formText } from "@/components/forms/action-form";
import { fieldError } from "@/components/forms/use-action";
import { Field, FormGrid } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { type CatalogueCode, type Job, startCatalogueJob } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { formatDateTime } from "@/lib/format";

/** The job's params from the form: the coupon's code, how many, the prefix in capitals, the school's name. */
export function codesParams(coupon: string, form: FormData) {
  return {
    coupon,
    count: Number(formText(form, "count")),
    prefix: formText(form, "prefix").toUpperCase(),
    note: formText(form, "note"),
  };
}

export function CodesTable({
  rows,
  next,
  previous,
}: {
  rows: CatalogueCode[];
  next: string | null;
  previous: string | null;
}) {
  const columns: Column<CatalogueCode>[] = [
    { key: "code", label: copy.catalogue.columns.code, render: (row) => <span className="font-mono">{row.code}</span> },
    { key: "note", label: copy.catalogue.columns.school, render: (row) => row.note || copy.common.none, wrap: true },
    {
      key: "used",
      label: copy.catalogue.columns.used,
      render: (row) =>
        row.used ? (
          <StatusChip tone="done">{copy.catalogue.usedBy(row.order ?? "")}</StatusChip>
        ) : (
          <StatusChip tone="good">{copy.catalogue.unused}</StatusChip>
        ),
    },
    { key: "made", label: copy.catalogue.columns.made, render: (row) => formatDateTime(row.created) },
  ];
  return (
    <DataTable
      listKey="catalogue-codes"
      caption={copy.catalogue.codesTitle}
      rows={rows}
      columns={columns}
      rowId={(row) => row.code}
      next={next}
      previous={previous}
      filters={[
        {
          name: "used",
          label: copy.catalogue.columns.used,
          type: "select",
          options: [
            { value: "true", label: copy.catalogue.usedOnly },
            { value: "false", label: copy.catalogue.unusedOnly },
          ],
        },
      ]}
      empty={{ title: copy.catalogue.codesEmptyTitle, text: copy.catalogue.codesEmptyText }}
    />
  );
}

/** A school's batch of codes, made by a job; its progress, then its file. */
export function MakeCodes({ coupon }: { coupon: string }) {
  const router = useRouter();
  const [job, setJob] = useState<Job | null>(null);
  const f = copy.catalogue.fields;
  return (
    <div className="flex flex-col gap-4">
      {job ? <JobProgress key={job.id} job={job} onDone={() => router.refresh()} /> : null}
      <ActionForm
        id="codes"
        submitLabel={copy.catalogue.makeCodes}
        success={copy.catalogue.codesStarted}
        labels={{ "params.count": f.count, "params.prefix": f.prefix, "params.note": f.school }}
        onSubmit={(form) => startCatalogueJob("coupon_codes", codesParams(coupon, form))}
        onDone={(result) => setJob(result as Job)}
      >
        {(error) => (
          <>
            <FormGrid>
              <Field
                id="codes-params.count"
                label={f.count}
                help={copy.catalogue.help.count}
                error={fieldError(error, "params.count")}
              >
                <Input name="count" inputMode="numeric" autoComplete="off" aria-required="true" />
              </Field>
              <Field
                id="codes-params.prefix"
                label={f.prefix}
                help={copy.catalogue.help.prefix}
                error={fieldError(error, "params.prefix")}
              >
                <Input
                  name="prefix"
                  autoComplete="off"
                  maxLength={10}
                  className="font-mono uppercase"
                  aria-required="true"
                />
              </Field>
            </FormGrid>
            <Field
              id="codes-params.note"
              label={f.school}
              help={copy.catalogue.help.school}
              error={fieldError(error, "params.note")}
            >
              <Input name="note" autoComplete="off" maxLength={200} aria-required="true" />
            </Field>
            {fieldError(error, "params.coupon") ? (
              <p className="m-0 text-sm font-semibold text-destructive">
                {fieldError(error, "params.coupon")?.join(" ")}
              </p>
            ) : null}
          </>
        )}
      </ActionForm>
    </div>
  );
}
