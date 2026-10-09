"use client";

// The list's bulk bar, for the chosen orders: mark packed (sent after 5 s, with Undo: the list's owner keeps the
// wait), print their packing slips, labels or invoices as one PDF, and cancel them (a reason, and the count typed, at
// most 250). Each is a background job (POST jobs/): its progress shows above the list, the rows the API refused with
// its reasons. What the person may not do is not drawn; the API decides the rest, row by row.
import { useId, useState } from "react";

import { ConfirmTyped } from "@/components/data/confirm-typed";
import { ErrorSummary } from "@/components/forms/error-summary";
import { useAction } from "@/components/forms/use-action";
import { useCan } from "@/components/shell/manifest";
import { Button } from "@/components/ui/button";
import { Radio } from "@/components/ui/choice";
import {
  Dialog,
  DialogBody,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/dialog";
import { type Job, type OrderRow, startOrdersJob } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { P } from "@/lib/modules";

export const MAX_CANCEL = 250;
const DOCUMENTS = ["packing_slip", "label", "invoices"] as const;

type BulkProps = {
  rows: OrderRow[];
  clear: () => void;
  /** Mark packed: the list waits 5 s with Undo, then starts the job. */
  onPack: (numbers: string[]) => void;
  onJob: (job: Job, title: string) => void;
};

function PrintDialog({ numbers, onJob, clear }: { numbers: string[]; onJob: BulkProps["onJob"]; clear: () => void }) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const [document, setDocument] = useState<(typeof DOCUMENTS)[number]>("packing_slip");
  const { run, busy, error, setError } = useAction();
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) setError(null);
      }}
    >
      <Button size="sm" variant="secondary" onClick={() => setOpen(true)}>
        {copy.orders.bulk.print}
      </Button>
      <DialogContent>
        <DialogHeader>{copy.orders.bulk.printTitle}</DialogHeader>
        <form
          noValidate
          className="flex flex-col gap-3.5"
          onSubmit={async (event) => {
            event.preventDefault();
            await run(async () => {
              const job = await startOrdersJob("orders_print", { targets: numbers, document });
              setOpen(false);
              clear();
              onJob(job, copy.orders.bulk.documents[document]);
            });
          }}
        >
          <DialogBody>
            <DialogDescription>{copy.orders.bulk.printText}</DialogDescription>
            <fieldset className="m-0 border-0 p-0">
              <legend className="mb-1 text-[15px] font-semibold">{copy.orders.bulk.printWhat}</legend>
              {DOCUMENTS.map((kind) => (
                <Radio
                  key={kind}
                  name={`${id}-document`}
                  value={kind}
                  checked={document === kind}
                  onChange={() => setDocument(kind)}
                >
                  {copy.orders.bulk.documents[kind]}
                </Radio>
              ))}
            </fieldset>
          </DialogBody>
          <ErrorSummary error={error} />
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="secondary">{copy.common.cancel}</Button>
            </DialogClose>
            <Button type="submit" busy={busy}>
              {copy.orders.bulk.printStart}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function OrdersBulk({ rows, clear, onPack, onJob }: BulkProps) {
  const can = useCan();
  const numbers = rows.flatMap((row) => (row.number ? [row.number] : []));
  const count = numbers.length;
  const packing = can(P.packOrder);
  return (
    <>
      <p className="m-0 text-[15px] font-semibold" role="status">
        {copy.orders.select.selected(count)}
      </p>
      <div className="flex flex-wrap items-center gap-2" role="group" aria-label={copy.orders.bulk.label}>
        {packing ? (
          <Button
            size="sm"
            onClick={() => {
              onPack(numbers);
              clear();
            }}
          >
            {copy.orders.bulk.pack}
          </Button>
        ) : null}
        {packing ? <PrintDialog numbers={numbers} onJob={onJob} clear={clear} /> : null}
        {can(P.ordersChange) ? (
          <ConfirmTyped
            label={String(count)}
            triggerLabel={copy.orders.bulk.cancel}
            triggerVariant="destructive"
            title={copy.orders.bulk.cancelTitle(count)}
            text={count > MAX_CANCEL ? copy.orders.bulk.cancelMax : copy.orders.bulk.cancelText}
            confirmLabel={copy.orders.bulk.cancelStart}
            reason
            reasonHelp={copy.orders.bulk.cancelReasonHelp}
            disabled={count > MAX_CANCEL}
            onConfirm={({ reason }) => startOrdersJob("orders_cancel", { targets: numbers, reason })}
            onDone={(job) => {
              clear();
              onJob(job as Job, copy.orders.bulk.cancel);
            }}
          />
        ) : null}
        <Button size="sm" variant="ghost" onClick={clear}>
          {copy.orders.select.clear}
        </Button>
      </div>
      {count > MAX_CANCEL && can(P.ordersChange) ? (
        <p className="m-0 basis-full text-sm text-muted-foreground">{copy.orders.bulk.cancelMax}</p>
      ) : null}
    </>
  );
}
