"use client";

// What can be done to an order now, as the API lists it (`actions`: the state machine's moves crossed with the
// person's permissions; `primary` is the one next step): the header's button, and the Actions section with the rest
// (send by hand, mark delivered, the payment link, a payment received offline, a message again, the invoice made or
// sent again). Nothing here decides: a move the API refuses comes back in its words.
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ConfirmDialog } from "@/components/data/confirm-typed";
import { ErrorSummary } from "@/components/forms/error-summary";
import { fieldError, useAction } from "@/components/forms/use-action";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { toast } from "@/components/ui/toaster";
import {
  moveOrder,
  notifyOrder,
  type OrderDetail,
  type OrderMove,
  paymentLink,
  recordOfflinePayment,
  type Schemas,
  shipOrder,
} from "@/lib/api/staff";
import { copy } from "@/lib/copy";

import { field, FormDialog } from "./form-dialog";

const COURIERS: Schemas["CourierEnum"][] = [
  "India Post",
  "Delhivery",
  "Blue Dart",
  "Ekart",
  "DTDC",
  "Xpressbees",
].concat(["Other"]) as Schemas["CourierEnum"][];
const NOTIFY: Schemas["OrderNotifyKindEnum"][] = ["placed", "paid", "packed", "shipped", "delivered"].concat([
  "cancelled",
  "refunded",
]) as Schemas["OrderNotifyKindEnum"][];

const can = (order: OrderDetail, name: string) => order.actions.some((action) => action.name === name);

function MoveButton({
  order,
  move,
  label,
  done,
  variant = "secondary",
}: {
  order: OrderDetail;
  move: OrderMove;
  label: string;
  done: string;
  variant?: "primary" | "secondary";
}) {
  const router = useRouter();
  const { run, busy, error } = useAction();
  return (
    <span className="inline-flex flex-col gap-2">
      <Button
        size="sm"
        variant={variant}
        busy={busy}
        onClick={() =>
          run(async () => {
            await moveOrder(order.number ?? "", move);
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

function ShipDialog({ order, primary }: { order: OrderDetail; primary?: boolean }) {
  return (
    <FormDialog
      triggerLabel={copy.orders.moves.ship}
      triggerVariant={primary ? "primary" : "secondary"}
      title={copy.orders.ship.title}
      text={copy.orders.ship.text}
      submitLabel={copy.orders.ship.submit}
      success={copy.orders.done.ship}
      labels={{
        courier: copy.orders.ship.courier,
        tracking_number: copy.orders.ship.tracking,
        tracking_url: copy.orders.ship.url,
      }}
      onSubmit={(form) =>
        shipOrder(order.number ?? "", {
          courier: field(form, "courier") as Schemas["CourierEnum"],
          tracking_number: field(form, "tracking_number"),
          tracking_url: field(form, "tracking_url"),
        })
      }
    >
      {(prefix, error) => (
        <>
          <Field id={`${prefix}courier`} label={copy.orders.ship.courier} error={fieldError(error, "courier")}>
            <Select name="courier" defaultValue="India Post">
              {COURIERS.map((courier) => (
                <option key={courier} value={courier}>
                  {courier}
                </option>
              ))}
            </Select>
          </Field>
          <Field
            id={`${prefix}tracking_number`}
            label={copy.orders.ship.tracking}
            error={fieldError(error, "tracking_number")}
          >
            <Input name="tracking_number" autoComplete="off" aria-required="true" className="font-mono" />
          </Field>
          <Field
            id={`${prefix}tracking_url`}
            label={copy.orders.ship.url}
            optional
            help={copy.orders.ship.urlHelp}
            error={fieldError(error, "tracking_url")}
          >
            <Input name="tracking_url" type="url" autoComplete="off" />
          </Field>
        </>
      )}
    </FormDialog>
  );
}

function OfflinePaymentDialog({ order }: { order: OrderDetail }) {
  return (
    <FormDialog
      triggerLabel={copy.orders.moves.offline_payment}
      title={copy.orders.offline.title}
      text={copy.orders.offline.text}
      submitLabel={copy.orders.offline.submit}
      success={copy.orders.offline.recorded}
      labels={{ reference: copy.orders.offline.reference, reason: copy.common.reason }}
      onSubmit={(form) =>
        recordOfflinePayment(order.number ?? "", { reference: field(form, "reference"), reason: field(form, "reason") })
      }
    >
      {(prefix, error) => (
        <>
          <Field id={`${prefix}reference`} label={copy.orders.offline.reference} error={fieldError(error, "reference")}>
            <Input name="reference" autoComplete="off" aria-required="true" className="font-mono" />
          </Field>
          <Field id={`${prefix}reason`} label={copy.common.reason} error={fieldError(error, "reason")}>
            <Textarea name="reason" rows={2} aria-required="true" />
          </Field>
        </>
      )}
    </FormDialog>
  );
}

function NotifyDialog({ order }: { order: OrderDetail }) {
  return (
    <FormDialog
      triggerLabel={copy.orders.notify.title}
      title={copy.orders.notify.title}
      text={copy.orders.notify.text}
      submitLabel={copy.orders.notify.submit}
      success={copy.orders.notify.sent}
      labels={{ kind: copy.orders.notify.kind }}
      onSubmit={(form) => notifyOrder(order.number ?? "", field(form, "kind") as Schemas["OrderNotifyKindEnum"])}
    >
      {(prefix, error) => (
        <Field id={`${prefix}kind`} label={copy.orders.notify.kind} error={fieldError(error, "kind")}>
          <Select name="kind" defaultValue={order.status === "pending" ? "placed" : order.status}>
            {NOTIFY.map((kind) => (
              <option key={kind} value={kind}>
                {copy.orders.notify.kinds[kind]}
              </option>
            ))}
          </Select>
        </Field>
      )}
    </FormDialog>
  );
}

function PaymentLink({ order, primary, send = true }: { order: OrderDetail; primary?: boolean; send?: boolean }) {
  const router = useRouter();
  const { run, busy, error } = useAction();
  const [link, setLink] = useState<string | null>(null);
  const waiting = order.payments.find((payment) => payment.payment_link_url && payment.status === "created");
  return (
    <span className="inline-flex flex-col gap-2">
      <span className="inline-flex flex-wrap gap-2">
        {send ? (
          <Button
            size="sm"
            variant={primary ? "primary" : "secondary"}
            busy={busy}
            onClick={() =>
              run(async () => {
                const sent = await paymentLink(order.number ?? "", "send");
                setLink(sent.url);
                toast.success(copy.orders.link.sent);
                router.refresh();
              })
            }
          >
            {copy.orders.link.send}
          </Button>
        ) : null}
        {waiting && !primary ? (
          <ConfirmDialog
            triggerLabel={copy.orders.link.cancel}
            title={copy.orders.link.cancelTitle}
            text={copy.orders.link.cancelText}
            confirmLabel={copy.orders.link.cancel}
            success={copy.orders.link.cancelled}
            onConfirm={() => paymentLink(order.number ?? "", "cancel")}
          />
        ) : null}
      </span>
      {send && (link || waiting) ? (
        <span className="font-mono text-sm break-all">{link ?? waiting?.payment_link_url}</span>
      ) : null}
      <ErrorSummary error={error} />
    </span>
  );
}

/** The header's button: the one next step the API names. */
export function NextAction({ order }: { order: OrderDetail }) {
  const next = order.actions.find((action) => action.primary)?.name;
  switch (next) {
    case "pack":
    case "deliver":
    case "release":
      return (
        <MoveButton
          order={order}
          move={next}
          label={copy.orders.moves[next]}
          done={copy.orders.done[next]}
          variant="primary"
        />
      );
    case "ship":
      return <ShipDialog order={order} primary />;
    case "payment_link":
      return <PaymentLink order={order} primary />;
    default:
      return null;
  }
}

/** The Actions section: every other move the API lists for this person. */
export function OrderMoves({ order }: { order: OrderDetail }) {
  const primary = order.actions.find((action) => action.primary)?.name;
  const invoice = order.documents.find((document) => document.kind === "invoice");
  const shown = (name: string) => can(order, name) && name !== primary;
  const any =
    ["pack", "ship", "deliver", "payment_link", "offline_payment", "notify", "invoice"].some(shown) ||
    (can(order, "payment_link") && primary === "payment_link");
  if (!any) return <p className="m-0 text-[15px] text-muted-foreground">{copy.common.none}</p>;
  return (
    <div className="flex flex-wrap items-start gap-2.5">
      {shown("pack") ? (
        <MoveButton order={order} move="pack" label={copy.orders.moves.pack} done={copy.orders.done.pack} />
      ) : null}
      {shown("ship") ? <ShipDialog order={order} /> : null}
      {shown("deliver") ? (
        <MoveButton order={order} move="deliver" label={copy.orders.moves.deliver} done={copy.orders.done.deliver} />
      ) : null}
      {can(order, "payment_link") ? <PaymentLink order={order} send={primary !== "payment_link"} /> : null}
      {shown("offline_payment") ? <OfflinePaymentDialog order={order} /> : null}
      {shown("notify") ? <NotifyDialog order={order} /> : null}
      {can(order, "invoice") && (!invoice || !invoice.ready) ? (
        <MoveButton
          order={order}
          move="invoice/regenerate"
          label={copy.orders.documents.regenerate}
          done={copy.orders.documents.regenerated}
        />
      ) : null}
      {can(order, "invoice") && invoice?.ready ? (
        <MoveButton
          order={order}
          move="invoice/resend"
          label={copy.orders.documents.resend}
          done={copy.orders.documents.resent}
        />
      ) : null}
    </div>
  );
}
