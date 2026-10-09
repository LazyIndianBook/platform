"use client";

// The parts of an order's record that act in place: its hold (hold with a reason, release) and tags (add, remove),
// and its refunds, where FINANCE shows a bank refund's account with a reason (logged) and marks the transfer made with
// its UTR (the credit note follows, once).
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ConfirmDialog } from "@/components/data/confirm-typed";
import { StatusChip } from "@/components/data/status-chip";
import { ErrorSummary } from "@/components/forms/error-summary";
import { fieldError, useAction } from "@/components/forms/use-action";
import { useCan } from "@/components/shell/manifest";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { toast } from "@/components/ui/toaster";
import { holdOrder, markRefundPaid, moveOrder, type OrderDetail, showRefundPayee, tagOrder } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDateTime } from "@/lib/format";
import { P } from "@/lib/modules";

import { field, FormDialog } from "./form-dialog";
import { rupees, stateTone } from "./format";

const allowed = (order: OrderDetail, name: string) => order.actions.some((action) => action.name === name);

export function HoldAndTags({ order }: { order: OrderDetail }) {
  const router = useRouter();
  const release = useAction();
  const tags = useAction();
  const [draft, setDraft] = useState("");
  const tagging = allowed(order, "tags");
  const change = (body: { add?: string[]; remove?: string[] }, done: string) =>
    tags.run(async () => {
      await tagOrder(order.number ?? "", body);
      toast.success(done);
      setDraft("");
      router.refresh();
    });
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-2">
        <p className="m-0 text-[15px]">
          {order.hold
            ? `${copy.orders.hold.by(order.hold.by, formatDateTime(order.hold.at))} ${order.hold.reason}`
            : copy.orders.hold.none}
        </p>
        <div className="flex flex-wrap gap-2">
          {allowed(order, "hold") ? (
            <FormDialog
              triggerLabel={copy.orders.hold.hold}
              title={copy.orders.hold.holdTitle}
              text={copy.orders.hold.holdText}
              submitLabel={copy.orders.hold.hold}
              success={copy.orders.hold.held}
              labels={{ reason: copy.common.reason }}
              onSubmit={(form) => holdOrder(order.number ?? "", field(form, "reason"))}
            >
              {(prefix, error) => (
                <Field id={`${prefix}reason`} label={copy.common.reason} error={fieldError(error, "reason")}>
                  <Textarea name="reason" rows={2} aria-required="true" />
                </Field>
              )}
            </FormDialog>
          ) : null}
          {allowed(order, "release") ? (
            <Button
              size="sm"
              variant="secondary"
              busy={release.busy}
              onClick={() =>
                release.run(async () => {
                  await moveOrder(order.number ?? "", "release");
                  toast.success(copy.orders.hold.released);
                  router.refresh();
                })
              }
            >
              {copy.orders.hold.release}
            </Button>
          ) : null}
        </div>
        <ErrorSummary error={release.error} />
      </div>

      <div className="flex flex-col gap-2">
        <h3 className="m-0 text-[15px] font-semibold">{copy.orders.sections.tags}</h3>
        {order.tags.length ? (
          <ul className="m-0 flex list-none flex-wrap gap-2 p-0">
            {order.tags.map((tag) => (
              <li
                key={tag}
                className="inline-flex items-center gap-1 border border-border bg-paper-2 pl-2 font-mono text-[13px]"
              >
                {tag}
                {tagging ? (
                  <button
                    type="button"
                    className="inline-flex size-8 cursor-pointer items-center justify-center text-[17px] text-muted-foreground hover:text-destructive"
                    aria-label={copy.orders.tags.remove(tag)}
                    onClick={() => change({ remove: [tag] }, copy.orders.tags.removed)}
                  >
                    ×
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="m-0 text-[15px] text-muted-foreground">{copy.orders.tags.none}</p>
        )}
        {tagging ? (
          <form
            className="flex flex-wrap items-end gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              if (draft.trim()) change({ add: [draft.trim()] }, copy.orders.tags.added);
            }}
          >
            <Field
              id="order-tag"
              label={copy.orders.tags.add}
              help={copy.orders.tags.help}
              error={fieldError(tags.error, "add")}
              className="min-w-0 flex-[0_1_18rem]"
            >
              <Input
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                maxLength={60}
                autoComplete="off"
              />
            </Field>
            <Button type="submit" size="sm" variant="secondary" busy={tags.busy}>
              {copy.orders.tags.add}
            </Button>
          </form>
        ) : null}
        {tags.error && !fieldError(tags.error, "add") ? <ErrorSummary error={tags.error} /> : null}
      </div>
    </div>
  );
}

function Payee({ refund }: { refund: OrderDetail["refunds"][number] }) {
  const [shown, setShown] = useState<string | null>(null);
  if (shown) return <span className="font-mono text-[14px] break-all">{copy.orders.payeeShown(shown)}</span>;
  return (
    <ConfirmDialog
      triggerLabel={copy.orders.showPayee}
      triggerVariant="ghost"
      title={copy.orders.showPayeeTitle}
      text={copy.orders.showPayeeText}
      confirmLabel={copy.orders.showPayee}
      confirmVariant="primary"
      reason
      onConfirm={({ reason }) => showRefundPayee(refund.id, reason)}
      onDone={(result) => {
        const payee = result as { upi?: string; account?: string; ifsc?: string; name?: string };
        setShown(payee.upi || [payee.name, payee.account, payee.ifsc].filter(Boolean).join(", "));
      }}
    />
  );
}

export function OrderRefunds({ order }: { order: OrderDetail }) {
  const can = useCan();
  if (!order.refunds.length) return <p className="m-0 text-[15px] text-muted-foreground">{copy.orders.noRefunds}</p>;
  const c = copy.orders.refundColumns;
  const finance = can(P.approveRefund);
  return (
    <div
      data-slot="table-wrap"
      className="table-wrap"
      role="region"
      aria-label={copy.table.region(copy.orders.sections.refunds)}
      tabIndex={0}
    >
      <table>
        <caption className="sr-only">{copy.orders.sections.refunds}</caption>
        <thead>
          <tr>
            <th scope="col" className="num">
              {c.amount}
            </th>
            <th scope="col">{c.method}</th>
            <th scope="col">{c.status}</th>
            <th scope="col">{c.to}</th>
            <th scope="col">{c.reference}</th>
            <th scope="col">{c.note}</th>
            <th scope="col">{c.asked}</th>
          </tr>
        </thead>
        <tbody>
          {order.refunds.map((refund) => {
            const bankDue = refund.method === "bank" && refund.status === "pending";
            return (
              <tr key={refund.id}>
                <td className="num">{rupees(refund.amount)}</td>
                <td className="min-w-40">
                  <span className="flex flex-col">
                    <span>{labelOf(copy.orders.refundMethods, refund.method)}</span>
                    <span className="text-sm text-muted-foreground">{refund.reason}</span>
                  </span>
                </td>
                <td>
                  <StatusChip tone={stateTone(refund.status)}>
                    {labelOf(copy.orders.refundStatuses, refund.status)}
                  </StatusChip>
                </td>
                <td className="min-w-40">
                  {refund.payee_masked ? (
                    <span className="flex flex-col items-start gap-1">
                      <span className="font-mono text-[14px]">{refund.payee_masked}</span>
                      {finance && bankDue ? <Payee refund={refund} /> : null}
                    </span>
                  ) : (
                    copy.common.none
                  )}
                </td>
                <td className="font-mono text-[13px] break-all">
                  {refund.utr || refund.arn || refund.razorpay_refund_id || copy.common.none}
                </td>
                <td className="font-mono text-[13px]">{refund.credit_note ?? copy.common.none}</td>
                <td className="whitespace-nowrap">
                  <span className="flex flex-col items-start gap-1.5">
                    {formatDateTime(refund.created)}
                    {finance && bankDue ? (
                      <FormDialog
                        triggerLabel={copy.orders.markPaid}
                        triggerVariant="primary"
                        title={copy.orders.markPaidTitle}
                        text={copy.orders.markPaidText}
                        submitLabel={copy.orders.markPaid}
                        success={copy.orders.paid}
                        labels={{ utr: copy.orders.utr }}
                        onSubmit={(form) => markRefundPaid(refund.id, field(form, "utr"))}
                      >
                        {(prefix, error) => (
                          <Field
                            id={`${prefix}utr`}
                            label={copy.orders.utr}
                            help={copy.orders.utrHelp}
                            error={fieldError(error, "utr")}
                          >
                            <Input name="utr" autoComplete="off" aria-required="true" className="font-mono" />
                          </Field>
                        )}
                      </FormDialog>
                    ) : null}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
