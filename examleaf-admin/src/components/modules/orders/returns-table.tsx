"use client";

// Returns as a list (GET orders/returns/?status=&open=&reason=&order=): the state, the reason, the books, who asked
// (the customer on the website, or staff for them) and when; a row opens the return.
import { type Column, DataTable } from "@/components/data/data-table";
import { StatusChip } from "@/components/data/status-chip";
import type { ReturnRow } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDateTime } from "@/lib/format";

import { stateTone } from "./format";

const options = (table: Record<string, string>) => Object.entries(table).map(([value, label]) => ({ value, label }));

export function ReturnsTable({
  rows,
  next,
  previous,
}: {
  rows: ReturnRow[];
  next: string | null;
  previous: string | null;
}) {
  const c = copy.orders.returns.columns;
  const columns: Column<ReturnRow>[] = [
    { key: "number", label: c.number, render: (row) => <span className="font-mono">{row.number}</span> },
    { key: "order", label: c.order, render: (row) => <span className="font-mono">{row.order}</span> },
    {
      key: "status",
      label: c.status,
      render: (row) => (
        <StatusChip tone={stateTone(row.status)}>{labelOf(copy.orders.returns.statuses, row.status)}</StatusChip>
      ),
    },
    { key: "reason", label: c.reason, render: (row) => row.reason_label },
    {
      key: "books",
      label: c.books,
      wrap: true,
      render: (row) => row.lines.map((line) => `${line.title} × ${line.quantity}`).join(", "),
    },
    {
      key: "by",
      label: c.by,
      render: (row) => (row.by_customer ? copy.orders.returns.byCustomer : copy.orders.returns.byStaff),
    },
    { key: "asked", label: c.asked, render: (row) => formatDateTime(row.created) },
  ];
  const f = copy.orders.returns.filters;
  return (
    <DataTable
      listKey="order-returns"
      caption={copy.orders.returns.title}
      rows={rows}
      columns={columns}
      rowId={(row) => String(row.id)}
      rowHref={(row) => `/orders/returns/${row.id}/`}
      next={next}
      previous={previous}
      filters={[
        { name: "status", label: f.status, type: "select", options: options(copy.orders.returns.statuses) },
        { name: "open", label: f.open, type: "select", options: options(copy.orders.returns.openOptions) },
        { name: "reason", label: f.reason, type: "select", options: options(copy.orders.returnReasons) },
        { name: "order", label: f.order, type: "text" },
      ]}
      empty={{ title: copy.orders.returns.emptyTitle, text: copy.orders.returns.emptyText }}
    />
  );
}
