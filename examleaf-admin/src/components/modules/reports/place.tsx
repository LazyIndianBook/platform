// Sales by place (GET reports/sales-by-place/): by state (the place of supply), district or PIN code. A place with
// fewer orders than the minimum is not shown: its row says "fewer than 10" and its numbers are nothing, and the totals
// are of the rows shown only, which the page says. A state's row opens its districts.
import Link from "next/link";

import { EmptyState } from "@/components/ui/empty-state";
import { Table, TableCell, TableHead } from "@/components/ui/table";
import type { PlaceReport } from "@/lib/api/staff";
import { copy } from "@/lib/copy";

import { count, maxOf, rupees } from "./numbers";
import { defined, Fewer, Measure } from "./parts";

/** The report's address at a level (and a state), keeping the period. */
export function placeHref(keep: Record<string, string>, level: string, state: string): string {
  const query = new URLSearchParams({ ...keep, level, ...(state ? { state } : {}) });
  return `/reports/place/?${query}`;
}

export function PlaceTable({ report, keep }: { report: PlaceReport; keep: Record<string, string> }) {
  const words = copy.reports.place;
  if (report.rows.length === 0)
    return (
      <EmptyState art="orders" title={words.emptyTitle}>
        <p>{words.emptyText}</p>
      </EmptyState>
    );
  const hover = defined(report.columns);
  const max = maxOf(report.rows.map((row) => row.net));
  return (
    <div className="flex flex-col gap-3">
      {report.hidden_rows ? (
        <p className="m-0 text-[15px]">{words.hiddenNote(report.hidden_rows, report.minimum)}</p>
      ) : null}
      <Table caption={words.table}>
        <thead>
          <tr>
            <TableHead title={hover.label}>{words.levels[report.level as keyof typeof words.levels]}</TableHead>
            <TableHead numeric title={hover.orders}>
              {words.orders}
            </TableHead>
            <TableHead numeric title={hover.units}>
              {words.units}
            </TableHead>
            <TableHead numeric title={hover.net}>
              {words.net}
            </TableHead>
          </tr>
        </thead>
        <tbody>
          {report.rows.map((row) => (
            <tr key={`${row.level}|${row.state ?? ""}|${row.district ?? ""}|${row.pin ?? ""}|${row.label}`}>
              <TableCell>
                {report.level === "state" && row.state && !row.hidden ? (
                  <Link href={placeHref(keep, "district", row.state)}>
                    {row.label}
                    <span className="sr-only">: {words.openDistricts}</span>
                  </Link>
                ) : (
                  row.label
                )}
              </TableCell>
              {row.hidden ? (
                <Fewer under={row.under} span={3} />
              ) : (
                <>
                  <TableCell numeric>{count(row.orders)}</TableCell>
                  <TableCell numeric>{count(row.units)}</TableCell>
                  <TableCell numeric>
                    <Measure value={row.net} max={max}>
                      {rupees(row.net)}
                    </Measure>
                  </TableCell>
                </>
              )}
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <th scope="row">{words.totalShown}</th>
            <TableCell numeric>{count(report.totals_shown.orders)}</TableCell>
            <TableCell numeric>{count(report.totals_shown.units)}</TableCell>
            <TableCell numeric>{rupees(report.totals_shown.net)}</TableCell>
          </tr>
        </tfoot>
      </Table>
    </div>
  );
}
