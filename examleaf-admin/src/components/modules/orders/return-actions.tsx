"use client";

// A return's next step (the API's `next`: its state machine's moves), each drawn for whoever may take it: approve or
// decline it (staff.handle_return; a decline says why to the customer), send the return label, then the packing room
// receives it and inspects it (staff.receive_return: back into stock or damaged) and adds photographs; once inspected,
// its refund through the order's refund dialog. The API refuses anything else in its words.
import { useRouter } from "next/navigation";
import { useId, useState } from "react";

import { ErrorSummary } from "@/components/forms/error-summary";
import { fieldError, useAction } from "@/components/forms/use-action";
import { useCan } from "@/components/shell/manifest";
import { Button } from "@/components/ui/button";
import { Radio } from "@/components/ui/choice";
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { toast } from "@/components/ui/toaster";
import { addReturnPhoto, moveReturn, type OrderDetail, type ReturnDetail } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { P } from "@/lib/modules";

import { field, FormDialog } from "./form-dialog";
import { RefundDialog } from "./refund-dialog";

function Step({ label, done, onRun }: { label: string; done: string; onRun: () => Promise<unknown> }) {
  const router = useRouter();
  const { run, busy, error } = useAction();
  return (
    <span className="inline-flex flex-col gap-2">
      <Button
        size="sm"
        busy={busy}
        onClick={() =>
          run(async () => {
            await onRun();
            toast.success(done);
            router.refresh();
          })
        }
      >
        {label}
      </Button>
      <ErrorSummary error={error} />
    </span>
  );
}

function Photo({ back }: { back: ReturnDetail }) {
  const id = useId();
  const router = useRouter();
  const { run, busy, error } = useAction();
  const [file, setFile] = useState<File | null>(null);
  return (
    <form
      className="flex flex-wrap items-end gap-2"
      onSubmit={async (event) => {
        event.preventDefault();
        if (!file) return;
        const form = event.currentTarget;
        const ok = await run(() => addReturnPhoto(back.id, file));
        if (!ok) return;
        form.reset();
        setFile(null);
        toast.success(copy.orders.returns.photoAdded);
        router.refresh();
      }}
    >
      <Field
        id={`${id}-photo`}
        label={copy.orders.returns.addPhoto}
        help={copy.orders.returns.photoHelp}
        error={fieldError(error, "photo")}
        className="min-w-0 flex-[0_1_22rem]"
      >
        <Input
          type="file"
          accept="image/jpeg,image/png,image/webp"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
        />
      </Field>
      <Button type="submit" size="sm" variant="secondary" busy={busy} disabled={!file}>
        {copy.orders.returns.addPhoto}
      </Button>
      {error && !fieldError(error, "photo") ? <ErrorSummary error={error} /> : null}
    </form>
  );
}

export function ReturnActions({ back, order }: { back: ReturnDetail; order: OrderDetail | null }) {
  const can = useCan();
  const next = new Set(back.next);
  const handle = can(P.handleReturn);
  const receive = can(P.receiveReturn);
  const r = copy.orders.returns;
  const steps = [
    handle && next.has("approve") ? (
      <Step key="approve" label={r.approve} done={r.approved} onRun={() => moveReturn(back.id, { move: "approve" })} />
    ) : null,
    handle && next.has("decline") ? (
      <FormDialog
        key="decline"
        triggerLabel={r.decline}
        triggerVariant="destructive"
        title={r.declineTitle}
        text={r.declineText}
        submitLabel={r.decline}
        submitVariant="destructive"
        success={r.declined}
        labels={{ note: r.declineNote }}
        onSubmit={(form) => moveReturn(back.id, { move: "decline", note: field(form, "note") })}
      >
        {(prefix, error) => (
          <Field id={`${prefix}note`} label={r.declineNote} error={fieldError(error, "note")}>
            <Textarea name="note" rows={2} aria-required="true" />
          </Field>
        )}
      </FormDialog>
    ) : null,
    handle && next.has("label") ? (
      <FormDialog
        key="label"
        triggerLabel={r.label}
        title={r.label}
        text={r.labelText}
        submitLabel={r.label}
        success={r.labelSent}
        labels={{ courier: r.labelCourier, awb: r.labelAwb }}
        onSubmit={(form) =>
          moveReturn(back.id, { move: "label", courier: field(form, "courier"), awb: field(form, "awb") })
        }
      >
        {(prefix, error) => (
          <>
            <Field id={`${prefix}courier`} label={r.labelCourier} error={fieldError(error, "courier")}>
              <Input name="courier" autoComplete="off" aria-required="true" defaultValue="India Post" />
            </Field>
            <Field id={`${prefix}awb`} label={r.labelAwb} error={fieldError(error, "awb")}>
              <Input name="awb" autoComplete="off" aria-required="true" className="font-mono" />
            </Field>
          </>
        )}
      </FormDialog>
    ) : null,
    receive && next.has("receive") ? (
      <Step key="receive" label={r.receive} done={r.received} onRun={() => moveReturn(back.id, { move: "receive" })} />
    ) : null,
    receive && next.has("inspect") ? (
      <FormDialog
        key="inspect"
        triggerLabel={r.inspect}
        title={r.inspect}
        text={r.inspectText}
        submitLabel={r.inspect}
        success={r.inspected}
        onSubmit={(form) =>
          moveReturn(back.id, {
            move: "inspect",
            outcome: field(form, "outcome") === "damaged" ? "damaged" : "restocked",
          })
        }
      >
        {() => (
          <fieldset className="m-0 border-0 p-0">
            <legend className="mb-1 text-[15px] font-semibold">{r.inspect}</legend>
            <Radio name="outcome" value="restocked" defaultChecked>
              {r.restocked}
            </Radio>
            <Radio name="outcome" value="damaged">
              {r.damaged}
            </Radio>
          </fieldset>
        )}
      </FormDialog>
    ) : null,
    can(P.refundOrder) && next.has("refund") && order ? (
      <RefundDialog key="refund" order={order} returnId={back.id} triggerLabel={r.refund} triggerVariant="primary" />
    ) : null,
  ].filter(Boolean);
  return (
    <div className="flex flex-col gap-4">
      {steps.length ? (
        <div className="flex flex-wrap items-start gap-2.5">{steps}</div>
      ) : (
        <p className="m-0 text-[15px] text-muted-foreground">{r.nothingNext}</p>
      )}
      {receive && back.photos < 5 && back.status !== "declined" ? <Photo back={back} /> : null}
    </div>
  );
}
