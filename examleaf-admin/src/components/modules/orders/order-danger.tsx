"use client";

// An order's Danger section, drawn for what the API lists for this person: cancel (a reason, whether the customer
// asked; a cash-on-delivery parcel back undelivered: its copies back into stock or not, and its invoice credited),
// the refund dialog, and a return asked for on the customer's behalf (the copies of each book, a reason, their words).
import { useId, useState } from "react";

import { DangerRow } from "@/components/data/record-page";
import { fieldError } from "@/components/forms/use-action";
import { Checkbox } from "@/components/ui/choice";
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { askReturn, cancelOrder, type OrderDetail, type Schemas } from "@/lib/api/staff";
import { copy } from "@/lib/copy";

import { field, FormDialog } from "./form-dialog";
import { RefundDialog } from "./refund-dialog";

const has = (order: OrderDetail, name: string) => order.actions.some((action) => action.name === name);

function CancelOrder({ order }: { order: OrderDetail }) {
  const returned = order.status === "shipped";
  return (
    <FormDialog
      triggerLabel={copy.orders.cancel.action}
      triggerVariant="destructive"
      title={copy.orders.cancel.title}
      text={returned ? copy.orders.cancel.returnedText : copy.orders.cancel.text}
      submitLabel={copy.orders.cancel.submit}
      submitVariant="destructive"
      success={copy.orders.cancel.done}
      labels={{ reason: copy.orders.cancel.reason }}
      onSubmit={(form) =>
        cancelOrder(order.number ?? "", {
          reason: field(form, "reason"),
          customer_requested: form.get("customer_requested") === "on",
          restock: returned ? form.get("restock") === "on" : true,
        })
      }
    >
      {(prefix, error) => (
        <>
          <Field
            id={`${prefix}reason`}
            label={copy.orders.cancel.reason}
            help={copy.orders.cancel.reasonHelp}
            error={fieldError(error, "reason")}
          >
            <Textarea name="reason" rows={2} aria-required="true" />
          </Field>
          <Checkbox name="customer_requested">{copy.orders.cancel.asked}</Checkbox>
          {returned ? (
            <Checkbox name="restock" defaultChecked>
              <span className="flex flex-col">
                <span>{copy.orders.cancel.restock}</span>
                <span className="text-sm text-muted-foreground">{copy.orders.cancel.restockHelp}</span>
              </span>
            </Checkbox>
          ) : null}
        </>
      )}
    </FormDialog>
  );
}

const REASONS: Schemas["ReturnReasonEnum"][] = ["damaged", "misprint", "wrong_item", "late", "not_as_described"].concat(
  ["other"],
) as Schemas["ReturnReasonEnum"][];

function AskReturn({ order }: { order: OrderDetail }) {
  const id = useId();
  const [copies, setCopies] = useState<Record<number, number>>({});
  const lines = order.lines.filter((line) => !line.digital && line.returnable > 0);
  return (
    <FormDialog
      triggerLabel={copy.orders.returnAsk.action}
      title={copy.orders.returnAsk.title}
      text={copy.orders.returnAsk.text}
      submitLabel={copy.orders.returnAsk.submit}
      success={copy.orders.returnAsk.done}
      wide
      labels={{ reason: copy.orders.returnAsk.reason, note: copy.orders.returnAsk.note }}
      onSubmit={(form) =>
        askReturn(order.number ?? "", {
          lines: Object.entries(copies)
            .filter(([, count]) => count > 0)
            .map(([item, quantity]) => ({ item: Number(item), quantity })),
          reason: field(form, "reason") as Schemas["ReturnReasonEnum"],
          note: field(form, "note"),
        })
      }
      onDone={() => setCopies({})}
    >
      {(prefix, error) => (
        <>
          {lines.map((line) => (
            <Field
              key={line.id}
              id={`${id}-line-${line.id}`}
              label={copy.orders.returnAsk.copies(line.title)}
              help={copy.orders.refund.left(line.returnable)}
            >
              <Input
                type="number"
                inputMode="numeric"
                min={0}
                max={line.returnable}
                value={String(copies[line.id] ?? 0)}
                onChange={(event) => {
                  const value = Math.max(0, Math.min(line.returnable, Math.floor(Number(event.target.value) || 0)));
                  setCopies((current) => ({ ...current, [line.id]: value }));
                }}
                className="w-28"
              />
            </Field>
          ))}
          <Field id={`${prefix}reason`} label={copy.orders.returnAsk.reason} error={fieldError(error, "reason")}>
            <Select name="reason" defaultValue="damaged">
              {REASONS.map((reason) => (
                <option key={reason} value={reason}>
                  {copy.orders.returnReasons[reason]}
                </option>
              ))}
            </Select>
          </Field>
          <Field id={`${prefix}note`} label={copy.orders.returnAsk.note} optional error={fieldError(error, "note")}>
            <Textarea name="note" rows={3} />
          </Field>
        </>
      )}
    </FormDialog>
  );
}

export function OrderDanger({ order }: { order: OrderDetail }) {
  return (
    <div className="flex flex-col gap-4">
      {has(order, "cancel") ? (
        <DangerRow
          title={copy.orders.cancel.action}
          text={order.status === "shipped" ? copy.orders.cancel.returnedText : copy.orders.cancel.text}
        >
          <CancelOrder order={order} />
        </DangerRow>
      ) : null}
      {has(order, "refund") ? (
        <DangerRow title={copy.orders.refund.action} text={copy.orders.refund.text}>
          <RefundDialog order={order} />
        </DangerRow>
      ) : null}
      {has(order, "return") ? (
        <DangerRow title={copy.orders.returnAsk.action} text={copy.orders.returnAsk.text}>
          <AskReturn order={order} />
        </DangerRow>
      ) : null}
    </div>
  );
}
