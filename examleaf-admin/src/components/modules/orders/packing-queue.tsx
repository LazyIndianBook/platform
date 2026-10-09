"use client";

// Packer mode (GET orders/packing/): one column of cards, oldest first, large targets. Each order shows what to pick
// (each book once with its copies), where it goes, the weight hint and, for cash on delivery, the cash to collect
// and the risk. Mark packed is sent after 5 seconds with Undo (one at a time: a second one sends the first at once);
// its packing slip and 4×6 label open as PDFs; chosen orders (or the whole page) print as one pick list.
import { useRouter } from "next/navigation";
import { useState } from "react";

import { StatusChip } from "@/components/data/status-chip";
import { ErrorSummary } from "@/components/forms/error-summary";
import { useAction } from "@/components/forms/use-action";
import { useCan } from "@/components/shell/manifest";
import { Button, buttonVariants } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/choice";
import { EmptyState } from "@/components/ui/empty-state";
import { toast } from "@/components/ui/toaster";
import { moveOrder, orderPdfHref, type PackingRow, pickList } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatAgo } from "@/lib/format";
import { P } from "@/lib/modules";

import { riskTone, rupees } from "./format";
import { TagList } from "./order-badges";
import { UndoNotice, useUndo, UNDO_SECONDS } from "./undo";

/** A PDF answer saved as a file of this name (the browser's download). */
export function saveBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

export function PackingQueue({ rows }: { rows: PackingRow[] }) {
  const can = useCan();
  const router = useRouter();
  const undo = useUndo();
  const packing = useAction();
  const printing = useAction();
  const [chosen, setChosen] = useState<ReadonlySet<string>>(() => new Set());
  const [waiting, setWaiting] = useState<string | null>(null);
  const packer = can(P.packOrder);

  if (!rows.length)
    return (
      <EmptyState art="orders" title={copy.orders.packing.emptyTitle}>
        <p>{copy.orders.packing.emptyText}</p>
      </EmptyState>
    );

  const pack = (number: string) => {
    setWaiting(number);
    undo.start(copy.orders.bulk.packing(1, UNDO_SECONDS), () => {
      packing.run(async () => {
        try {
          await moveOrder(number, "pack");
          toast.success(copy.orders.bulk.packed);
          router.refresh();
        } finally {
          setWaiting(null);
        }
      });
    });
  };
  const numbers = chosen.size
    ? rows.filter((row) => chosen.has(row.number)).map((row) => row.number)
    : rows.map((row) => row.number);

  return (
    <div className="flex max-w-[44rem] flex-col gap-4">
      <UndoNotice
        pending={undo.pending}
        undo={() => {
          undo.undo();
          setWaiting(null);
          toast.success(copy.orders.bulk.undone);
        }}
        undoLabel={copy.orders.bulk.undo}
      />
      <ErrorSummary error={packing.error} />
      <ol className="m-0 flex list-none flex-col gap-4 p-0">
        {rows.map((row) => (
          <li key={row.number} className="flex flex-col gap-3 border border-border bg-card p-4">
            <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
              <h2 className="m-0 font-mono text-lg">{row.number}</h2>
              <span className="text-sm text-muted-foreground">{formatAgo(row.placed_at)}</span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {row.is_cod ? (
                <StatusChip tone={row.risk_bucket ? riskTone(row.risk_bucket) : "waiting"}>
                  {copy.orders.packing.collect(rupees(row.total))}
                </StatusChip>
              ) : null}
              {row.risk_bucket ? (
                <StatusChip tone={riskTone(row.risk_bucket)}>{labelOf(copy.orders.risks, row.risk_bucket)}</StatusChip>
              ) : null}
              <TagList tags={row.tags} />
            </div>
            <p className="m-0 text-[15px]">
              <span className="font-semibold">{copy.orders.packing.to}: </span>
              {row.destination || copy.common.unknown}
            </p>
            <div>
              <p className="m-0 text-[15px] font-semibold">{copy.orders.packing.pick}</p>
              <ul className="m-0 flex list-none flex-col gap-1 p-0 text-[17px]">
                {row.pick.map((line) => (
                  <li key={`${line.title}-${line.isbn}`} className="flex flex-wrap gap-x-2">
                    <span>{line.title}</span>
                    <span className="font-mono font-semibold">{copy.orders.packing.copies(line.quantity)}</span>
                    {line.isbn ? <span className="font-mono text-sm text-muted-foreground">{line.isbn}</span> : null}
                  </li>
                ))}
              </ul>
            </div>
            <p className="m-0 text-sm text-muted-foreground">
              {row.weight_g === null ? copy.orders.packing.noWeight : copy.orders.packing.weight(row.weight_g)}
            </p>
            <div className="flex flex-wrap items-center gap-2.5">
              {packer ? (
                <Button disabled={waiting === row.number} onClick={() => pack(row.number)}>
                  {copy.orders.bulk.pack}
                </Button>
              ) : null}
              {packer ? (
                // PDFs of the API (the session's cookie): page loads, not routes here
                <>
                  <a
                    href={orderPdfHref(row.number, "packing-slip")}
                    className={buttonVariants({ variant: "secondary" })}
                  >
                    {copy.orders.packing.slip}
                    <span className="sr-only">: {row.number}</span>
                  </a>
                  <a href={orderPdfHref(row.number, "label")} className={buttonVariants({ variant: "secondary" })}>
                    {copy.orders.packing.label}
                    <span className="sr-only">: {row.number}</span>
                  </a>
                </>
              ) : null}
            </div>
            {packer ? (
              <Checkbox
                checked={chosen.has(row.number)}
                onChange={(event) => {
                  const on = event.target.checked;
                  setChosen((current) => {
                    const next = new Set(current);
                    if (on) next.add(row.number);
                    else next.delete(row.number);
                    return next;
                  });
                }}
              >
                {copy.orders.packing.choose(row.number)}
              </Checkbox>
            ) : null}
          </li>
        ))}
      </ol>
      {packer ? (
        <div
          data-bulk-bar=""
          className="sticky bottom-0 z-10 flex flex-col gap-2 border-t-[1.5px] border-foreground bg-background py-3"
        >
          <Button
            variant="secondary"
            busy={printing.busy}
            onClick={() =>
              printing.run(async () => {
                saveBlob(await pickList(numbers), "ExamLeaf-pick-list.pdf");
                toast.success(copy.orders.packing.pickListMade);
              })
            }
          >
            {chosen.size ? copy.orders.packing.pickList(numbers.length) : copy.orders.packing.pickListAll}
          </Button>
          <ErrorSummary error={printing.error} />
        </div>
      ) : null}
    </div>
  );
}
