// The sales report (GET reports/sales/): the lines of the orders placed in the period, grouped by a title, a subject, a
// class, a board or an edition and, if asked, by day, week or month. Units, gross, discount and net as the API sums
// them; the net's bar is the share of the largest net in the table. The totals are the whole period's (an order with
// lines in two groups is one order in the total).
import { EmptyState } from "@/components/ui/empty-state";
import { Table, TableCell, TableHead } from "@/components/ui/table";
import type { SalesReport } from "@/lib/api/staff";
import { copy } from "@/lib/copy";

import { count, maxOf, periodLabel, rupees } from "./numbers";
import { defined, Measure } from "./parts";

export function SalesTable({ report }: { report: SalesReport }) {
  const words = copy.reports.sales;
  if (report.rows.length === 0)
    return (
      <EmptyState art="orders" title={words.emptyTitle}>
        <p>{words.emptyText}</p>
      </EmptyState>
    );
  const hover = defined(report.columns);
  const max = maxOf(report.rows.map((row) => row.net));
  const byPeriod = report.grain !== "none";
  return (
    <Table caption={words.table}>
      <thead>
        <tr>
          <TableHead title={hover.label}>{words.by[report.by as keyof typeof words.by] ?? report.by}</TableHead>
          {byPeriod ? <TableHead title={hover.period_start}>{words.period}</TableHead> : null}
          <TableHead numeric title={hover.orders}>
            {words.orders}
          </TableHead>
          <TableHead numeric title={hover.units}>
            {words.units}
          </TableHead>
          <TableHead numeric title={hover.gross}>
            {words.gross}
          </TableHead>
          <TableHead numeric title={hover.discount}>
            {words.discount}
          </TableHead>
          <TableHead numeric title={hover.net}>
            {words.net}
          </TableHead>
        </tr>
      </thead>
      <tbody>
        {report.rows.map((row) => (
          <tr key={`${row.key}|${row.period_start ?? ""}`}>
            <TableCell>{row.label}</TableCell>
            {byPeriod ? <TableCell>{periodLabel(report.grain, row.period_start)}</TableCell> : null}
            <TableCell numeric>{count(row.orders)}</TableCell>
            <TableCell numeric>{count(row.units)}</TableCell>
            <TableCell numeric>{rupees(row.gross)}</TableCell>
            <TableCell numeric>{rupees(row.discount)}</TableCell>
            <TableCell numeric>
              <Measure value={row.net} max={max}>
                {rupees(row.net)}
              </Measure>
            </TableCell>
          </tr>
        ))}
      </tbody>
      <tfoot>
        <tr>
          <th scope="row" colSpan={byPeriod ? 2 : 1}>
            {words.total}
          </th>
          <TableCell numeric>{count(report.totals.orders)}</TableCell>
          <TableCell numeric>{count(report.totals.units)}</TableCell>
          <TableCell numeric>{rupees(report.totals.gross)}</TableCell>
          <TableCell numeric>{rupees(report.totals.discount)}</TableCell>
          <TableCell numeric>{rupees(report.totals.net)}</TableCell>
        </tr>
      </tfoot>
    </Table>
  );
}
