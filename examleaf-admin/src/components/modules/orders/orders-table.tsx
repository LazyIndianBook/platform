"use client";

// Orders as a list (GET orders/): the tabs (all, to pack, shipped, returns, cancelled, drafts) and the filters in the
// address, saved views ("orders"), the customer masked, the status with the COD badge (its risk), the hold and the
// tags in each row; test orders only when asked. A search for a person is recorded by the API (its keyed hash only).
// Chosen rows get the bulk bar (mark packed with 5 s to undo, print, cancel with the count typed); Export takes the
// list's filters; Space looks at an order beside the list. Bulk work runs as jobs whose progress shows here.
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { type Column, DataTable } from "@/components/data/data-table";
import { ConfirmDialog } from "@/components/data/confirm-typed";
import { JobProgress } from "@/components/data/job-progress";
import { ErrorSummary } from "@/components/forms/error-summary";
import { useAction } from "@/components/forms/use-action";
import { useCan } from "@/components/shell/manifest";
import { Section } from "@/components/shell/page-header";
import { toast } from "@/components/ui/toaster";
import { type Job, type OrderRow, type SavedView, startOrdersJob } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDateTime } from "@/lib/format";
import { P } from "@/lib/modules";

import { rupees } from "./format";
import { OrderBadges, OrderStatus, TagList } from "./order-badges";
import { OrderPeek } from "./order-peek";
import { OrdersBulk } from "./orders-bulk";
import { UndoNotice, useUndo, UNDO_SECONDS } from "./undo";

/** The list's filters an export takes (the API's EXPORT_FILTERS: never a search). */
export const EXPORT_FILTERS = ["status", "method", "courier", "created_from", "created_to", "shipping", "tag"].concat([
  "hold",
  "risk",
  "livemode",
  "tab",
]);

const options = (table: Record<string, string>) => Object.entries(table).map(([value, label]) => ({ value, label }));

export function OrdersTable({
  rows,
  next,
  previous,
  views,
}: {
  rows: OrderRow[];
  next: string | null;
  previous: string | null;
  views: SavedView[] | null;
}) {
  const can = useCan();
  const router = useRouter();
  const params = useSearchParams();
  const undo = useUndo();
  const starting = useAction();
  const [job, setJob] = useState<{ job: Job; title: string } | null>(null);
  const [peek, setPeek] = useState<OrderRow | null>(null);
  const jobs = can(P.jobsView);
  const bulk = jobs && (can(P.packOrder) || can(P.ordersChange));

  const onJob = (started: Job, title: string) => setJob({ job: started, title });
  const onPack = (numbers: string[]) =>
    undo.start(copy.orders.bulk.packing(numbers.length, UNDO_SECONDS), () => {
      starting.run(async () => onJob(await startOrdersJob("orders_pack", { targets: numbers }), copy.orders.bulk.pack));
    });

  const filters = Object.fromEntries(
    EXPORT_FILTERS.flatMap((name) => (params.get(name) ? [[name, params.get(name) as string]] : [])),
  );

  const columns: Column<OrderRow>[] = [
    {
      key: "number",
      label: copy.orders.columns.number,
      render: (row) => <span className="font-mono">{row.number}</span>,
    },
    {
      key: "placed",
      label: copy.orders.columns.placed,
      render: (row) => formatDateTime(row.placed_at ?? row.created),
    },
    {
      key: "customer",
      label: copy.orders.columns.customer,
      wrap: true,
      render: (row) => (
        <span className="flex flex-col">
          <span>{row.customer.name || copy.orders.guest}</span>
          <span className="font-mono text-[13px] text-muted-foreground">{row.customer.email}</span>
        </span>
      ),
    },
    {
      key: "status",
      label: copy.orders.columns.status,
      wrap: true,
      render: (row) => (
        <span className="inline-flex flex-wrap items-center gap-1.5">
          <OrderStatus order={row} />
          <OrderBadges order={row} />
        </span>
      ),
    },
    { key: "total", label: copy.orders.columns.total, numeric: true, render: (row) => rupees(row.total) },
    {
      key: "items",
      label: copy.orders.columns.items,
      wrap: true,
      render: (row) => <span className="text-[14px]">{row.items.join(", ")}</span>,
    },
    { key: "tags", label: copy.orders.columns.tags, render: (row) => <TagList tags={row.tags} /> },
    {
      key: "payment",
      label: copy.orders.columns.payment,
      render: (row) => labelOf(copy.orders.methods, row.payment_method),
      hidden: true,
    },
    {
      key: "courier",
      label: copy.orders.columns.courier,
      render: (row) =>
        row.courier ? (
          <span className="flex flex-col">
            <span>{row.courier.name}</span>
            <span className="font-mono text-[13px] text-muted-foreground">{row.courier.tracking_number}</span>
          </span>
        ) : (
          copy.common.none
        ),
      hidden: true,
    },
  ];

  return (
    <div className="flex flex-col gap-4">
      <UndoNotice pending={undo.pending} undo={undo.undo} undoLabel={copy.orders.bulk.undo} />
      <ErrorSummary error={starting.error} />
      {job ? (
        <Section title={`${copy.orders.bulk.progress}: ${job.title}`}>
          <JobProgress
            key={job.job.id}
            job={job.job}
            onDone={(finished) => {
              if (finished?.state === "done" && finished.kind === "orders_pack") toast.success(copy.orders.bulk.packed);
              router.refresh();
            }}
          />
        </Section>
      ) : null}
      <DataTable
        listKey="orders"
        caption={copy.orders.title}
        rows={rows}
        columns={columns}
        rowId={(row) => String(row.id)}
        rowHref={(row) => (row.number ? `/orders/${encodeURIComponent(row.number)}/` : null)}
        next={next}
        previous={previous}
        views={views}
        presets={{
          name: "tab",
          label: copy.orders.tabs.label,
          all: copy.orders.tabs.all,
          options: ["to_pack", "shipped", "returns", "cancelled", "drafts"].map((value) => ({
            value,
            label: copy.orders.tabs[value],
          })),
        }}
        filters={[
          { name: "q", label: copy.orders.filters.search, type: "search" },
          { name: "status", label: copy.orders.filters.status, type: "select", options: options(copy.orders.statuses) },
          { name: "method", label: copy.orders.filters.method, type: "select", options: options(copy.orders.methods) },
          { name: "risk", label: copy.orders.filters.risk, type: "select", options: options(copy.orders.risks) },
          { name: "hold", label: copy.orders.filters.hold, type: "select", options: options(copy.orders.holdOptions) },
          {
            name: "livemode",
            label: copy.orders.filters.mode,
            type: "select",
            options: options(copy.orders.modeOptions),
            any: copy.orders.modeAny,
          },
          {
            name: "shipping",
            label: copy.orders.filters.parcel,
            type: "select",
            options: [...options(copy.orders.parcels), { value: "none", label: copy.orders.noParcel }],
          },
          { name: "courier", label: copy.orders.filters.courier, type: "text" },
          { name: "tag", label: copy.orders.filters.tag, type: "text" },
          { name: "created_from", label: copy.orders.filters.from, type: "date" },
          { name: "created_to", label: copy.orders.filters.to, type: "date" },
        ]}
        selection={
          bulk
            ? {
                label: (row) => copy.orders.select.row(row.number ?? String(row.id)),
                page: copy.orders.select.page,
                bulk: (chosen, clear) => <OrdersBulk rows={chosen} clear={clear} onPack={onPack} onJob={onJob} />,
              }
            : undefined
        }
        onPeek={setPeek}
        toolbar={
          jobs && can(P.ordersExport) ? (
            <ConfirmDialog
              triggerLabel={copy.orders.bulk.export}
              triggerVariant="secondary"
              title={copy.orders.bulk.exportTitle}
              text={copy.orders.bulk.exportText}
              confirmLabel={copy.orders.bulk.exportStart}
              confirmVariant="primary"
              onConfirm={() => startOrdersJob("orders_export", { filters })}
              onDone={(started) => onJob(started as Job, copy.orders.bulk.export)}
            />
          ) : undefined
        }
        empty={{ title: copy.orders.emptyTitle, text: copy.orders.emptyText }}
      />
      <p className="m-0 text-sm text-muted-foreground">{copy.orders.peek.hint}</p>
      <OrderPeek row={peek} onClose={() => setPeek(null)} />
    </div>
  );
}
