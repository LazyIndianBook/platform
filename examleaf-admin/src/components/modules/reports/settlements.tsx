// Razorpay's settlements (GET reports/settlements/): for each, what the customers paid, the fees and the GST on them,
// the refunds taken off and what reached the bank, with the bank's UTR, newest first. Until the Finance module has
// them the report says it is not set up, and why, and shows nothing in their place. A figure the module does not keep
// is a dash, never a zero.
import { EmptyState } from "@/components/ui/empty-state";
import { Table, TableCell, TableHead } from "@/components/ui/table";
import type { SettlementsReport } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { formatDate } from "@/lib/format";

import { rupees } from "./numbers";
import { defined } from "./parts";

export function SettlementsTable({ report }: { report: SettlementsReport }) {
  const words = copy.reports.settlements;
  if (!report.configured)
    return (
      <EmptyState art="sheet" eyebrow={words.notSetUpEyebrow} title={words.notSetUpTitle}>
        <p>{report.note || words.notSetUpText}</p>
      </EmptyState>
    );
  if (report.rows.length === 0)
    return (
      <EmptyState art="sheet" title={words.emptyTitle}>
        <p>{words.emptyText}</p>
      </EmptyState>
    );
  const hover = defined(report.columns);
  return (
    <Table caption={words.table}>
      <thead>
        <tr>
          <TableHead title={hover.date}>{words.date}</TableHead>
          <TableHead title={hover.reference}>{words.settlement}</TableHead>
          <TableHead numeric title={hover.gross}>
            {words.gross}
          </TableHead>
          <TableHead numeric title={hover.fees}>
            {words.fees}
          </TableHead>
          <TableHead numeric title={hover.tax}>
            {words.tax}
          </TableHead>
          <TableHead numeric title={hover.refunds}>
            {words.refunds}
          </TableHead>
          <TableHead numeric title={hover.net}>
            {words.net}
          </TableHead>
          <TableHead title={hover.utr}>{words.utr}</TableHead>
          <TableHead title={hover.state}>{words.state}</TableHead>
        </tr>
      </thead>
      <tbody>
        {report.rows.map((row) => (
          <tr key={row.reference}>
            <TableCell>{row.date ? formatDate(row.date) : "–"}</TableCell>
            <TableCell className="font-mono">{row.reference}</TableCell>
            <TableCell numeric>{rupees(row.gross)}</TableCell>
            <TableCell numeric>{rupees(row.fees)}</TableCell>
            <TableCell numeric>{rupees(row.tax)}</TableCell>
            <TableCell numeric>{rupees(row.refunds)}</TableCell>
            <TableCell numeric>{rupees(row.net)}</TableCell>
            <TableCell className="font-mono">{row.utr || "–"}</TableCell>
            <TableCell>{row.state || "–"}</TableCell>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}
