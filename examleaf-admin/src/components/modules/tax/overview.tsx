// The tax module's overview parts, drawn from the API's answers as they come (no figure is worked out here): the
// month's due dates (GET tax/calendar/), the threshold card (GET tax/thresholds/) and table 13 (GET tax/series/).
import Link from "next/link";

import { StatusChip } from "@/components/data/status-chip";
import { Table, TableCell, TableHead } from "@/components/ui/table";
import type { SeriesRegister, TaxCalendar, ThresholdCard, ThresholdRow } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { formatDate, formatInr } from "@/lib/format";

import { monthLabel, shiftMonth } from "./periods";

/** A threshold line's figure: rupees, or a number of documents. */
export const thresholdValue = (row: Pick<ThresholdRow, "count" | "value">) =>
  row.count ? copy.tax.documentsCount(Number(row.value)) : formatInr(Number(row.value));

export function CalendarList({ calendar }: { calendar: TaxCalendar }) {
  const previous = shiftMonth(calendar.month, -1);
  const next = shiftMonth(calendar.month, 1);
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="m-0 text-[15px]">
          <span className="font-semibold">{copy.tax.monthOf(monthLabel(calendar.month))}</span>
          <span className="text-muted-foreground">
            {" · "}
            {calendar.qrmp ? copy.tax.qrmp : copy.tax.monthly}
          </span>
        </p>
        <nav aria-label={copy.tax.month} className="flex flex-wrap gap-2">
          <Link href={`/tax/?month=${previous}`} className="inline-flex min-h-11 items-center font-semibold">
            {copy.tax.previousMonth}
            <span className="sr-only">: {monthLabel(previous)}</span>
          </Link>
          <Link href={`/tax/?month=${next}`} className="inline-flex min-h-11 items-center font-semibold">
            {copy.tax.nextMonth}
            <span className="sr-only">: {monthLabel(next)}</span>
          </Link>
        </nav>
      </div>
      {calendar.items.length === 0 ? (
        <p className="m-0 text-[15px] text-muted-foreground">{copy.tax.nothingDue}</p>
      ) : (
        <ul className="m-0 flex list-none flex-col p-0">
          {calendar.items.map((item) => (
            <li
              key={`${item.key}-${item.due}`}
              className="grid gap-x-6 gap-y-1 border-b border-border py-3 min-[640px]:grid-cols-[7rem_minmax(0,1fr)]"
            >
              <span className="font-mono text-[15px] font-semibold">{formatDate(item.due)}</span>
              <div className="flex min-w-0 flex-col gap-1">
                <p className="m-0 flex flex-wrap items-center gap-2 text-[15px] font-semibold">
                  {item.title}
                  {item.past ? <StatusChip tone="stopped">{copy.tax.past}</StatusChip> : null}
                  {item.applies ? null : <StatusChip tone="stopped">{copy.tax.notRequired}</StatusChip>}
                </p>
                <p className="m-0 text-[15px] text-muted-foreground">
                  {copy.tax.covers(item.covers)}
                  {item.note ? `. ${item.note}` : ""}
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}
      {calendar.crossed.length ? (
        <p className="m-0 text-[15px]">
          <span className="font-semibold">{copy.tax.crossedThisYear}: </span>
          {calendar.crossed.map((row) => row.label).join("; ")}.
        </p>
      ) : null}
    </div>
  );
}

export function Thresholds({ card }: { card: ThresholdCard }) {
  return (
    <div className="flex flex-col gap-4">
      <p className="m-0 text-[15px] text-muted-foreground">
        {card.as_of ? copy.tax.asOf(formatDate(card.as_of), card.financial_year) : copy.tax.notYet}
      </p>
      {card.rows.length ? (
        <Table caption={copy.table.region(copy.tax.thresholds)}>
          <thead>
            <tr>
              <TableHead>{copy.tax.thresholdColumns.line}</TableHead>
              <TableHead numeric>{copy.tax.thresholdColumns.value}</TableHead>
              <TableHead numeric>{copy.tax.thresholdColumns.limit}</TableHead>
              <TableHead>{copy.tax.thresholdColumns.state}</TableHead>
            </tr>
          </thead>
          <tbody>
            {card.rows.map((row) => (
              <tr key={row.line}>
                <TableCell>{row.label}</TableCell>
                <TableCell numeric>{thresholdValue(row)}</TableCell>
                <TableCell numeric>{formatInr(Number(row.limit))}</TableCell>
                <TableCell>
                  <StatusChip tone={row.crossed ? "moving" : "stopped"}>
                    {row.crossed ? copy.tax.crossed : copy.tax.notCrossed}
                  </StatusChip>
                </TableCell>
              </tr>
            ))}
          </tbody>
        </Table>
      ) : null}
      <dl className="m-0 grid gap-x-8 gap-y-2 min-[640px]:grid-cols-[minmax(10rem,auto)_minmax(0,1fr)]">
        <dt className="text-sm font-semibold text-muted-foreground">{copy.tax.previousTurnover(card.previous_year)}</dt>
        <dd className="m-0 font-mono text-[15px]">{formatInr(Number(card.previous_turnover))}</dd>
        <dt className="text-sm font-semibold text-muted-foreground">{copy.tax.returns}</dt>
        <dd className="m-0 text-[15px]">{card.qrmp ? copy.tax.qrmp : copy.tax.monthly}</dd>
        <dt className="text-sm font-semibold text-muted-foreground">{copy.tax.hsnDigits}</dt>
        <dd className="m-0 font-mono text-[15px]">{card.hsn_digits}</dd>
      </dl>
      <p className="m-0 text-sm text-muted-foreground">{card.basis}</p>
    </div>
  );
}

export function SeriesTable({ register }: { register: SeriesRegister }) {
  const prefixes = Object.entries(register.prefixes)
    .map(([type, prefix]) => `${prefix} (${copy.tax.types[type] ?? type.replaceAll("_", " ")})`)
    .join(", ");
  return (
    <div className="flex flex-col gap-3">
      {register.rows.length === 0 ? (
        <p className="m-0 text-[15px] text-muted-foreground">{copy.tax.seriesEmpty}</p>
      ) : (
        <Table caption={copy.table.region(copy.tax.seriesThisYear)}>
          <thead>
            <tr>
              <TableHead>{copy.tax.seriesColumns.series}</TableHead>
              <TableHead>{copy.tax.seriesColumns.nature}</TableHead>
              <TableHead>{copy.tax.seriesColumns.first}</TableHead>
              <TableHead>{copy.tax.seriesColumns.last}</TableHead>
              <TableHead numeric>{copy.tax.seriesColumns.total}</TableHead>
              <TableHead numeric>{copy.tax.seriesColumns.cancelled}</TableHead>
              <TableHead numeric>{copy.tax.seriesColumns.next}</TableHead>
            </tr>
          </thead>
          <tbody>
            {register.rows.map((row) => (
              <tr key={`${row.series}-${row.financial_year}`}>
                <TableCell className="font-mono font-semibold">{row.series}</TableCell>
                <TableCell>{row.nature}</TableCell>
                <TableCell className="font-mono">{row.first}</TableCell>
                <TableCell className="font-mono">{row.last}</TableCell>
                <TableCell numeric>{row.total}</TableCell>
                <TableCell numeric>{row.cancelled}</TableCell>
                <TableCell numeric>{row.next_number ?? copy.common.none}</TableCell>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
      <p className="m-0 text-sm text-muted-foreground">{copy.tax.seriesFrom(register.series_from, prefixes)}</p>
    </div>
  );
}
