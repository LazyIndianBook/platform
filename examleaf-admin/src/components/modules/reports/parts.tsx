// What every report page shares, drawn from the API's answers (no figure is worked out here): the head that says how the
// numbers are counted, when they were worked out and whether they are test data; the form that puts a period and the
// report's filters in the address (a plain GET form: the page is rendered again from the server, with or without
// script); a bar, and the cell that stands for a group too small to show. A report is tables and plain bars (CSS
// widths): nothing needs a legend to be read, and the number is always written beside its bar.
import { Fragment } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { TableCell } from "@/components/ui/table";
import type { ReportColumn } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { formatDate, formatDateTime } from "@/lib/format";

import { barWidth } from "./numbers";

/** What every report answers besides its own parts. */
export type Envelope = {
  definition: string;
  columns: ReportColumn[];
  as_of: string;
  test_mode: boolean;
  period: { start: string; end: string; days: number } | null;
};

/** The columns' definitions by key, for a column heading's hover text. */
export const defined = (columns: ReportColumn[]): Record<string, string> =>
  Object.fromEntries(columns.map((column) => [column.key, column.definition]));

/** The head of a report: test data said first, the period and when it was worked out, and "How this is counted" (a
 *  disclosure, so a keyboard has it too) with the report's words and each column's. `counted` replaces "Data as of"
 *  where a night's job made the rows. */
export function ReportHead({ report, counted }: { report: Envelope; counted?: string }) {
  const words = copy.reports;
  return (
    <div className="flex flex-col gap-3">
      {report.test_mode ? (
        <Alert variant="warning" title={words.testTitle}>
          <p>{words.testText}</p>
        </Alert>
      ) : null}
      <p className="m-0 flex flex-wrap gap-x-5 gap-y-1 text-[15px] text-muted-foreground">
        {report.period ? (
          <span>
            {words.period(formatDate(report.period.start), formatDate(report.period.end), report.period.days)}
          </span>
        ) : null}
        <span>{counted ?? words.asOf(formatDateTime(report.as_of))}</span>
      </p>
      <details className="max-w-[60rem] rounded-lg border border-border bg-card px-4">
        <summary className="flex min-h-11 cursor-pointer items-center font-semibold">{words.howCounted}</summary>
        <div className="flex flex-col gap-3 pb-4">
          <p className="m-0 text-[15px] leading-relaxed">{report.definition}</p>
          {report.columns.length ? (
            <dl className="m-0 grid gap-x-6 gap-y-2 text-[15px] min-[640px]:grid-cols-[minmax(8rem,14rem)_minmax(0,1fr)]">
              {report.columns.map((column) => (
                <Fragment key={column.key}>
                  <dt className="font-semibold">{column.label}</dt>
                  <dd className="m-0 text-muted-foreground">{column.definition}</dd>
                </Fragment>
              ))}
            </dl>
          ) : null}
        </div>
      </details>
    </div>
  );
}

/** The filters of a report in its address: a GET form to the report's own page. */
export function ReportForm({ action, label, children }: { action: string; label: string; children: React.ReactNode }) {
  return (
    <form method="get" action={action} aria-label={label} className="flex flex-wrap items-end gap-x-4 gap-y-3">
      {children}
      <Button type="submit" variant="secondary" size="sm">
        {copy.reports.show}
      </Button>
    </form>
  );
}

/** A period's two days (never after `today`: the API refuses a day to come). */
export function DayFields({ id, from, to, today }: { id: string; from: string; to: string; today: string }) {
  return (
    <>
      <Field id={`${id}-from`} label={copy.reports.from} className="w-44">
        <Input name="from" type="date" defaultValue={from} max={today} />
      </Field>
      <Field id={`${id}-to`} label={copy.reports.to} className="w-44">
        <Input name="to" type="date" defaultValue={to} max={today} />
      </Field>
    </>
  );
}

/** One of a few choices as a filter (the phone's own picker). */
export function ChoiceField({
  id,
  name,
  label,
  value,
  options,
  className = "w-48",
}: {
  id: string;
  name: string;
  label: string;
  value: string;
  options: { value: string; label: string }[];
  className?: string;
}) {
  return (
    <Field id={id} label={label} className={className}>
      <Select name={name} defaultValue={value}>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </Select>
    </Field>
  );
}

/** A bar for a figure beside its number: a still 6 px bar, the share of the largest figure of its table. */
export function Bar({ value, max }: { value: string | number | null | undefined; max: number }) {
  return (
    <span aria-hidden="true" className="mt-1 ml-auto block h-1.5 w-full min-w-24 bg-rule-soft">
      <span className="block h-full bg-primary" style={{ width: `${barWidth(value, max)}%` }} />
    </span>
  );
}

/** A figure with its bar under it, right-aligned as the table's numbers are. */
export function Measure({
  children,
  value,
  max,
}: {
  children: React.ReactNode;
  value: string | number | null | undefined;
  max: number;
}) {
  return (
    <span className="flex flex-col items-end">
      <span>{children}</span>
      <Bar value={value} max={max} />
    </span>
  );
}

/** A group too small to show: "fewer than 10" over the columns its numbers would have taken. */
export function Fewer({ under, span }: { under: number | null; span: number }) {
  return (
    <TableCell colSpan={span} className="text-muted-foreground">
      {copy.reports.fewer(under ?? 0)}
    </TableCell>
  );
}
