"use client";

// The HSN and SAC master (GET tax/hsn/?q=&kind=&taxability=): each code with its rate today and any change set to
// come; a code new to the master with its first rate (POST tax/hsn/), and a new dated rate of a code (POST
// tax/hsn/{code}/rates/, behind the save bar). The API refuses a rate that starts before the code's latest one: its
// history is never rewritten.
import { type Column, DataTable } from "@/components/data/data-table";
import { StatusChip } from "@/components/data/status-chip";
import { ActionForm, formText } from "@/components/forms/action-form";
import { fieldError } from "@/components/forms/use-action";
import { Field, FormGrid } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import type { ApiError } from "@/lib/api/errors";
import { addHsnCode, addHsnRate, type HsnCode, type SavedView, type Schemas, type Taxability } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";

import { rateText } from "./records";

export function HsnTable({
  rows,
  next,
  previous,
  views,
}: {
  rows: HsnCode[];
  next: string | null;
  previous: string | null;
  views: SavedView[] | null;
}) {
  const columns: Column<HsnCode>[] = [
    { key: "code", label: copy.tax.hsnColumns.code, render: (code) => <span className="font-mono">{code.code}</span> },
    { key: "description", label: copy.tax.hsnColumns.description, render: (code) => code.description, wrap: true },
    { key: "kind", label: copy.tax.hsnColumns.kind, render: (code) => labelOf(copy.tax.kinds, code.kind) },
    {
      key: "today",
      label: copy.tax.hsnColumns.today,
      render: (code) =>
        code.today ? (
          <span className="inline-flex flex-wrap items-center gap-1.5">
            <span className="font-mono">{copy.tax.rate(code.today.rate)}</span>
            <StatusChip tone={code.today.taxability === "taxable" ? "moving" : "stopped"}>
              {labelOf(copy.tax.taxability, code.today.taxability)}
            </StatusChip>
          </span>
        ) : (
          <StatusChip tone="bad">{copy.tax.noRate}</StatusChip>
        ),
    },
    {
      key: "next",
      label: copy.tax.hsnColumns.next,
      render: (code) => (code.next_change ? rateText(code.next_change) : copy.tax.noChange),
    },
    { key: "products", label: copy.tax.hsnColumns.products, render: (code) => code.products, numeric: true },
  ];
  return (
    <DataTable
      listKey="tax-hsn"
      caption={copy.tax.hsnTitle}
      rows={rows}
      columns={columns}
      rowId={(code) => code.code}
      rowHref={(code) => `/tax/hsn/${encodeURIComponent(code.code)}/`}
      next={next}
      previous={previous}
      views={views}
      filters={[
        { name: "q", label: copy.tax.search, type: "search" },
        {
          name: "kind",
          label: copy.tax.hsnColumns.kind,
          type: "select",
          options: Object.entries(copy.tax.kinds).map(([value, label]) => ({ value, label })),
        },
        {
          name: "taxability",
          label: copy.tax.fields.taxability,
          type: "select",
          options: Object.entries(copy.tax.taxability).map(([value, label]) => ({ value, label })),
        },
      ]}
      empty={{ title: copy.tax.hsnEmptyTitle, text: copy.tax.hsnEmptyText }}
    />
  );
}

const RATE_LABELS = {
  rate: copy.tax.fields.rate,
  taxability: copy.tax.fields.taxability,
  effective_from: copy.tax.fields.effective_from,
  effective_to: copy.tax.fields.effective_to,
  notification: copy.tax.fields.notification,
  serial: copy.tax.fields.serial,
  note: copy.tax.fields.note,
};

/** A rate's fields as the API takes them (a date left empty is none). */
export function rateBody(form: FormData): Schemas["NewHsnRateRequest"] {
  return {
    rate: formText(form, "rate"),
    taxability: formText(form, "taxability") as Taxability,
    effective_from: formText(form, "effective_from"),
    effective_to: formText(form, "effective_to") || null,
    notification: formText(form, "notification"),
    serial: formText(form, "serial"),
    note: formText(form, "note"),
  };
}

/** The rate's fields: `prefix` the form's id, `error` its answer (a nested one's fields as `first_rate.rate`). */
function RateFields({ prefix, error, nested = "" }: { prefix: string; error: ApiError | null; nested?: string }) {
  const problem = (name: string) => fieldError(error, `${nested}${name}`);
  const id = (name: string) => `${prefix}-${nested}${name}`; // the error summary links to the API's (nested) name
  return (
    <>
      <FormGrid>
        <Field id={id("rate")} label={copy.tax.fields.rate} error={problem("rate")}>
          <Input name="rate" inputMode="decimal" autoComplete="off" aria-required="true" />
        </Field>
        <Field
          id={id("taxability")}
          label={copy.tax.fields.taxability}
          help={copy.tax.fields.taxabilityHelp}
          error={problem("taxability")}
        >
          <Select name="taxability" defaultValue="taxable">
            {Object.entries(copy.tax.taxability).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
        </Field>
      </FormGrid>
      <FormGrid>
        <Field id={id("effective_from")} label={copy.tax.fields.effective_from} error={problem("effective_from")}>
          <Input name="effective_from" type="date" aria-required="true" />
        </Field>
        <Field
          id={id("effective_to")}
          label={copy.tax.fields.effective_to}
          optional
          help={copy.tax.fields.effectiveToHelp}
          error={problem("effective_to")}
        >
          <Input name="effective_to" type="date" />
        </Field>
      </FormGrid>
      <FormGrid>
        <Field
          id={id("notification")}
          label={copy.tax.fields.notification}
          help={copy.tax.fields.notificationHelp}
          error={problem("notification")}
        >
          <Input name="notification" autoComplete="off" aria-required="true" maxLength={100} />
        </Field>
        <Field id={id("serial")} label={copy.tax.fields.serial} optional error={problem("serial")}>
          <Input name="serial" autoComplete="off" maxLength={20} />
        </Field>
      </FormGrid>
      <Field
        id={id("note")}
        label={copy.tax.fields.note}
        optional
        help={copy.tax.fields.noteHelp}
        error={problem("note")}
      >
        <Input name="note" autoComplete="off" maxLength={300} />
      </Field>
    </>
  );
}

/** A new dated rate of a code, behind the save bar (a warning before leaving with it half typed). */
export function NewRateForm({ code }: { code: string }) {
  return (
    <ActionForm
      id={`rate-${code}`}
      submitLabel={copy.tax.saveRate}
      success={copy.tax.rateAdded}
      labels={RATE_LABELS}
      saveBar
      onSubmit={(form) => addHsnRate(code, rateBody(form))}
    >
      {(error) => <RateFields prefix={`rate-${code}`} error={error} />}
    </ActionForm>
  );
}

/** A code new to the master, with its first rate. */
export function NewCodeForm() {
  return (
    <ActionForm
      id="new-code"
      submitLabel={copy.tax.saveCode}
      success={copy.tax.codeAdded}
      labels={{
        code: copy.tax.fields.code,
        kind: copy.tax.fields.kind,
        description: copy.tax.fields.description,
        uqc: copy.tax.fields.uqc,
        ...Object.fromEntries(Object.entries(RATE_LABELS).map(([name, label]) => [`first_rate.${name}`, label])),
      }}
      saveBar
      onSubmit={(form) =>
        addHsnCode({
          code: formText(form, "code"),
          kind: formText(form, "kind") as Schemas["HsnKindEnum"],
          description: formText(form, "description"),
          uqc: formText(form, "uqc") || undefined,
          first_rate: rateBody(form),
        })
      }
    >
      {(error) => (
        <>
          <FormGrid>
            <Field id="new-code-code" label={copy.tax.fields.code} error={fieldError(error, "code")}>
              <Input name="code" inputMode="numeric" autoComplete="off" aria-required="true" maxLength={8} />
            </Field>
            <Field id="new-code-kind" label={copy.tax.fields.kind} error={fieldError(error, "kind")}>
              <Select name="kind" defaultValue="hsn">
                {Object.entries(copy.tax.kinds).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field
              id="new-code-uqc"
              label={copy.tax.fields.uqc}
              optional
              help={copy.tax.fields.uqcHelp}
              error={fieldError(error, "uqc")}
            >
              <Input name="uqc" autoComplete="off" maxLength={3} />
            </Field>
          </FormGrid>
          <Field id="new-code-description" label={copy.tax.fields.description} error={fieldError(error, "description")}>
            <Input name="description" autoComplete="off" aria-required="true" maxLength={200} />
          </Field>
          <RateFields prefix="new-code" error={error} nested="first_rate." />
        </>
      )}
    </ActionForm>
  );
}
