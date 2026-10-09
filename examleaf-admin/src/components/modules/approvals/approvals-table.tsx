"use client";

// Change requests as a list (GET change-requests/?state=): what would change, on which record, for how much, who
// asked and when it expires. Pending by default.
import { type Column, DataTable } from "@/components/data/data-table";
import { StatusChip, toneOf } from "@/components/data/status-chip";
import type { ChangeRequest, SavedView } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDateTime, formatInr } from "@/lib/format";

export function ApprovalsTable({
  rows,
  next,
  previous,
  views,
}: {
  rows: ChangeRequest[];
  next: string | null;
  previous: string | null;
  views: SavedView[] | null;
}) {
  const columns: Column<ChangeRequest>[] = [
    {
      key: "action",
      label: copy.approvals.columns.action,
      render: (request) => <code className="text-[13px] break-all">{request.action}</code>,
    },
    {
      key: "target",
      wrap: true,
      label: copy.approvals.columns.target,
      render: (request) => request.target?.label ?? copy.common.none,
    },
    {
      key: "amount",
      label: copy.approvals.columns.amount,
      render: (request) => (request.amount === null ? "" : formatInr(request.amount)),
      numeric: true,
    },
    {
      key: "maker",
      label: copy.approvals.columns.maker,
      render: (request) => request.maker.name || request.maker.email,
    },
    {
      key: "expires",
      label: copy.approvals.columns.expires,
      render: (request) => (request.expires_at ? formatDateTime(request.expires_at) : copy.common.none),
    },
    {
      key: "state",
      label: copy.approvals.columns.state,
      render: (request) => (
        <StatusChip tone={toneOf(request.state)}>{labelOf(copy.approvals.states, request.state)}</StatusChip>
      ),
    },
  ];
  return (
    <DataTable
      listKey="approvals"
      caption={copy.approvals.title}
      rows={rows}
      columns={columns}
      rowId={(request) => request.id}
      rowLabel={(request) => `${request.action} ${request.id}`}
      rowHref={(request) => `/approvals/${request.id}/`}
      next={next}
      previous={previous}
      views={views}
      filters={[
        {
          name: "state",
          label: copy.approvals.columns.state,
          type: "select",
          options: [
            ...["approved", "rejected", "executed", "expired", "failed"].map((state) => ({
              value: state,
              label: copy.approvals.states[state],
            })),
            { value: "all", label: copy.common.all },
          ],
          any: copy.approvals.states.pending,
        },
      ]}
      empty={{ title: copy.approvals.emptyTitle, text: copy.approvals.emptyText }}
    />
  );
}
