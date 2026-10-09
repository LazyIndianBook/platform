"use client";

// The refunds' and the offline payments' lists (GET finance/refunds/, finance/offline-payments/): a row is a change
// request waiting for a second person (`kind` request: it opens its approval, /approvals/<id>/, where FINANCE
// approves the payload it read) or the refund or the payment itself (it opens its order). The tabs are the API's
// own `state`; a refund's ARN, its transfer's UTR and its credit note as the API gives them.
import { type Column, DataTable } from "@/components/data/data-table";
import { StatusChip } from "@/components/data/status-chip";
import type { FinanceRequestRow, SavedView } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDateTime } from "@/lib/format";

import { inr, toneOfFinance } from "./format";

type Kind = "refunds" | "offline";

/** Where a row opens: a request its approval, the rest their order. */
export const requestHref = (row: Pick<FinanceRequestRow, "kind" | "id" | "order">) =>
  row.kind === "request" ? `/approvals/${row.id}/` : `/orders/${encodeURIComponent(row.order)}/`;

/** A row's name: the change request's number, or the refund's or the payment's. */
export const requestName = (row: Pick<FinanceRequestRow, "kind" | "id">) =>
  row.kind === "request" ? copy.finance.requestName(row.id) : copy.finance.rowName(row.kind, row.id);

export function RequestsTable({
  kind,
  rows,
  next,
  previous,
  views,
}: {
  kind: Kind;
  rows: FinanceRequestRow[];
  next: string | null;
  previous: string | null;
  views: SavedView[] | null;
}) {
  const c = copy.finance.requestColumns;
  const refunds = kind === "refunds";
  const columns: Column<FinanceRequestRow>[] = [
    { key: "name", label: c.name, render: (row) => requestName(row) },
    { key: "order", label: c.order, render: (row) => <span className="font-mono text-[14px]">{row.order}</span> },
    { key: "amount", label: c.amount, render: (row) => inr(row.amount), numeric: true },
    {
      key: "status",
      label: c.status,
      render: (row) => (
        <StatusChip tone={toneOfFinance(row.status)}>{labelOf(copy.finance.rowStates, row.status)}</StatusChip>
      ),
    },
    ...(refunds
      ? [
          {
            key: "method",
            label: c.method,
            render: (row: FinanceRequestRow) =>
              row.method ? labelOf(copy.orders.refundMethods, row.method) : copy.common.none,
          },
          {
            key: "reference",
            label: c.reference,
            render: (row: FinanceRequestRow) => (
              <span className="font-mono text-[14px]">
                {row.arn || row.utr || row.razorpay_refund_id || copy.common.none}
              </span>
            ),
          },
          {
            key: "creditNote",
            label: c.creditNote,
            render: (row: FinanceRequestRow) => (
              <span className="font-mono text-[14px]">{row.credit_note ?? copy.common.none}</span>
            ),
            hidden: true,
          },
        ]
      : [
          {
            key: "reference",
            label: c.utr,
            render: (row: FinanceRequestRow) => (
              <span className="font-mono text-[14px]">{row.reference || copy.common.none}</span>
            ),
          },
        ]),
    { key: "by", label: c.by, render: (row) => row.by || copy.common.none },
    { key: "reason", label: c.reason, render: (row) => row.reason || copy.common.none, wrap: true, hidden: true },
    { key: "created", label: c.created, render: (row) => formatDateTime(row.created) },
  ];
  const states = refunds ? copy.finance.refundTabs : copy.finance.offlineTabs;
  return (
    <DataTable
      listKey={refunds ? "finance-refunds" : "finance-offline"}
      caption={refunds ? copy.finance.refundsTitle : copy.finance.offlineTitle}
      rows={rows}
      columns={columns}
      rowId={(row) => `${row.kind}-${row.id}`}
      rowHref={requestHref}
      next={next}
      previous={previous}
      views={views}
      presets={{
        name: "state",
        label: copy.finance.whichRows,
        all: refunds ? copy.finance.allRefunds : copy.finance.recorded,
        options: Object.entries(states).map(([value, label]) => ({ value, label })),
      }}
      filters={[
        { name: "q", label: copy.finance.searchOrder, type: "search" },
        ...(refunds
          ? [
              {
                name: "method",
                label: c.method,
                type: "select" as const,
                options: Object.entries(copy.orders.refundMethods).map(([value, label]) => ({ value, label })),
              },
            ]
          : []),
        {
          name: "livemode",
          label: copy.finance.modeFilter,
          type: "select",
          any: copy.finance.modeOptions.default,
          options: [{ value: "false", label: copy.finance.modeOptions.test }],
        },
      ]}
      empty={
        refunds
          ? { title: copy.finance.refundsEmptyTitle, text: copy.finance.refundsEmptyText }
          : { title: copy.finance.offlineEmptyTitle, text: copy.finance.offlineEmptyText }
      }
    />
  );
}
