"use client";

// What can be done for the requester from their ticket (each is written on the ticket and in the audit trail by the
// API, which also checks each one's own permission): for each of their orders a refund (not shipped yet: cancelled
// and refunded in full; shipped: the copies sent back, each from zero so nothing is refunded by accident, or an
// amount), cancelling it (a confirmation first), the invoice or the confirmation email again; their course access
// extended by some days with a reason; a book code looked up (one line to answer with); a data request started from a
// grievance or privacy ticket. A refund above the person's limit answers with the change request that waits.
import { useRouter } from "next/navigation";
import { useId, useState } from "react";

import { ConfirmDialog } from "@/components/data/confirm-typed";
import { ActionForm, formText } from "@/components/forms/action-form";
import { ErrorSummary } from "@/components/forms/error-summary";
import { fieldError, useAction } from "@/components/forms/use-action";
import { useCan } from "@/components/shell/manifest";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FormGrid } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { toast } from "@/components/ui/toaster";
import { ApiError } from "@/lib/api/errors";
import {
  cancelFromTicket,
  extendAccess,
  lookUpBookCode,
  refundFromTicket,
  resendConfirmation,
  resendInvoice,
  type Schemas,
  type SidebarOrder,
  startDataRequest,
  type TicketRecord,
} from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { formatDate, formatInr } from "@/lib/format";
import { P } from "@/lib/modules";

import { dataRequestOpen } from "./shared";

const money = (value: string | null | undefined) =>
  formatInr(value === null || value === undefined ? null : Number(value));

/** A refund's body from the form: the copies chosen (from zero), else the amount; nothing chosen is no body at all,
 *  so a shipped order is never refunded in full by an empty form. */
export function refundBody(order: SidebarOrder, form: FormData, reason: string): Schemas["RefundRequest"] | null {
  if (order.refund_mode === "cancel") return { order: order.number, reason };
  const lines = order.items
    .map((item) => ({ item: item.id, quantity: Number(form.get(`line-${item.id}`) || 0) }))
    .filter((line) => line.quantity > 0);
  const amount = String(form.get("amount") ?? "").trim();
  if (lines.length) return { order: order.number, lines, reason };
  if (amount) return { order: order.number, amount, reason };
  return null;
}

function RefundForm({ ticket, order }: { ticket: TicketRecord; order: SidebarOrder }) {
  const id = useId();
  const router = useRouter();
  const { run, busy, error, setError } = useAction();
  return (
    <form
      noValidate
      className="flex flex-col gap-3"
      onSubmit={async (event) => {
        event.preventDefault();
        const element = event.currentTarget;
        const form = new FormData(element);
        const body = refundBody(order, form, String(form.get("reason") ?? "").trim());
        if (!body) {
          setError(new ApiError(400, "invalid", copy.support.refundChoose));
          return;
        }
        const ok = await run(() => refundFromTicket(ticket.number, body));
        if (!ok) return;
        element.reset();
        toast.success(copy.support.refunded);
        router.refresh();
      }}
    >
      <p className="m-0 text-[15px] text-muted-foreground">
        {order.refund_mode === "cancel" ? copy.support.refundCancel : copy.support.refundPartial}
      </p>
      {order.refund_warning ? <Alert variant="warning" title={order.refund_warning} /> : null}
      <ErrorSummary
        error={error}
        idPrefix={`${id}-`}
        labels={{ lines: copy.support.refundLines, amount: copy.support.refundAmount, reason: copy.common.reason }}
      />
      {order.refund_mode === "partial" ? (
        <>
          <fieldset id={`${id}-lines`} className="m-0 flex min-w-0 flex-col gap-2 border-0 p-0">
            <legend className="mb-1 text-[15px] font-semibold">{copy.support.refundLines}</legend>
            {order.items.map((item) => (
              <div key={item.id} className="flex flex-wrap items-center gap-3">
                <Input
                  id={`${id}-line-${item.id}`}
                  name={`line-${item.id}`}
                  type="number"
                  inputMode="numeric"
                  min={0}
                  max={item.quantity}
                  defaultValue={0}
                  className="w-24"
                />
                <label htmlFor={`${id}-line-${item.id}`} className="text-[15px]">
                  {copy.support.refundLine(item.title, item.quantity)} · {money(item.unit_price)}
                </label>
              </div>
            ))}
          </fieldset>
          <Field
            id={`${id}-amount`}
            label={copy.support.refundAmount}
            optional
            help={copy.support.refundAmountHelp}
            error={fieldError(error, "amount")}
          >
            <Input name="amount" inputMode="decimal" autoComplete="off" className="w-40" />
          </Field>
        </>
      ) : null}
      <Field
        id={`${id}-reason`}
        label={copy.common.reason}
        help={copy.common.reasonHelp}
        error={fieldError(error, "reason")}
      >
        <Textarea name="reason" rows={2} aria-required="true" maxLength={300} />
      </Field>
      <div>
        <Button type="submit" busy={busy}>
          {copy.support.refundButton}
        </Button>
      </div>
    </form>
  );
}

function SimpleAction({ label, success, work }: { label: string; success: string; work: () => Promise<unknown> }) {
  const router = useRouter();
  const { run, busy, error } = useAction();
  return (
    <div className="flex flex-col gap-2">
      <Button
        variant="secondary"
        size="sm"
        busy={busy}
        onClick={() =>
          run(async () => {
            await work();
            toast.success(success);
            router.refresh();
          })
        }
      >
        {label}
      </Button>
      {error ? <ErrorSummary error={error} /> : null}
    </div>
  );
}

function OrderActions({ ticket, order }: { ticket: TicketRecord; order: SidebarOrder }) {
  const can = useCan();
  const refunding = can(P.refundOrder) && order.payments.some((payment) => payment.status === "captured");
  const cancelling = can(P.ordersChange) && order.refund_mode === "cancel";
  const handling = can(P.ticketsHandle);
  return (
    <details className="border border-border bg-card" open={order.linked}>
      <summary className="flex min-h-11 cursor-pointer flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2 text-[15px]">
        <span className="font-mono font-semibold">{order.number}</span>
        <span className="text-muted-foreground">
          {copy.support.orderStatus(order.status_label, money(order.total))}
        </span>
        {order.linked ? <span className="text-sm text-muted-foreground">({copy.support.thisTicket})</span> : null}
      </summary>
      <div className="flex flex-col gap-5 border-t border-border p-4">
        {refunding ? (
          <section aria-label={`${copy.support.refund}: ${order.number}`} className="flex flex-col gap-3">
            <h4 className="m-0 font-head text-base">{copy.support.refund}</h4>
            <RefundForm ticket={ticket} order={order} />
          </section>
        ) : null}
        <div className="flex flex-wrap items-start gap-3">
          {cancelling ? (
            <ConfirmDialog
              triggerLabel={copy.support.cancelOrder}
              title={copy.support.cancelTitle(order.number)}
              text={copy.support.cancelText}
              confirmLabel={copy.support.cancelOrder}
              reason
              success={copy.support.cancelled}
              onConfirm={({ reason }) => cancelFromTicket(ticket.number, { order: order.number, reason })}
            />
          ) : null}
          {handling && order.invoice ? (
            <SimpleAction
              label={copy.support.resendInvoice}
              success={copy.support.invoiceSent}
              work={() => resendInvoice(ticket.number, order.number)}
            />
          ) : null}
          {handling && order.placed_at ? (
            <SimpleAction
              label={copy.support.resendConfirmation}
              success={copy.support.confirmationSent}
              work={() => resendConfirmation(ticket.number, order.number)}
            />
          ) : null}
        </div>
      </div>
    </details>
  );
}

function ExtendForm({ ticket }: { ticket: TicketRecord }) {
  const rows = (ticket.sidebar.entitlements ?? []).filter((row) => row.valid_until);
  const id = `extend-${ticket.id}`;
  if (!rows.length) return <p className="m-0 text-[15px] text-muted-foreground">{copy.support.noExtendable}</p>;
  return (
    <ActionForm
      id={id}
      submitLabel={copy.support.extendButton}
      success={copy.support.extended}
      variant="secondary"
      labels={{ entitlement: copy.support.extendWhich, days: copy.support.extendDays, reason: copy.common.reason }}
      onSubmit={(form) =>
        extendAccess(ticket.number, {
          entitlement: Number(formText(form, "entitlement")),
          days: Number(formText(form, "days")),
          reason: formText(form, "reason"),
        })
      }
    >
      {(error) => (
        <>
          <FormGrid>
            <Field id={`${id}-entitlement`} label={copy.support.extendWhich} error={fieldError(error, "entitlement")}>
              <Select name="entitlement" defaultValue={String(rows[0].id)}>
                {rows.map((row) => (
                  <option key={row.id} value={row.id}>
                    {`${row.subject} · ${copy.support.until(formatDate(row.valid_until ?? ""))}`}
                  </option>
                ))}
              </Select>
            </Field>
            <Field
              id={`${id}-days`}
              label={copy.support.extendDays}
              help={copy.support.extendDaysHelp}
              error={fieldError(error, "days")}
            >
              <Input name="days" type="number" inputMode="numeric" min={1} max={365} aria-required="true" />
            </Field>
          </FormGrid>
          <Field
            id={`${id}-reason`}
            label={copy.common.reason}
            help={copy.common.reasonHelp}
            error={fieldError(error, "reason")}
          >
            <Textarea name="reason" rows={2} aria-required="true" maxLength={200} />
          </Field>
        </>
      )}
    </ActionForm>
  );
}

function BookCodeLookup({ ticket }: { ticket: TicketRecord }) {
  const id = `code-${ticket.id}`;
  const router = useRouter();
  const { run, busy, error } = useAction();
  const [line, setLine] = useState("");
  return (
    <form
      noValidate
      className="flex max-w-[40rem] flex-col gap-3"
      onSubmit={async (event) => {
        event.preventDefault();
        const element = event.currentTarget;
        const code = String(new FormData(element).get("code") ?? "").trim();
        let answer = "";
        const ok = await run(async () => {
          answer = (await lookUpBookCode(ticket.number, code)).line;
        });
        if (!ok) return;
        element.reset();
        setLine(answer);
        router.refresh();
      }}
    >
      <ErrorSummary error={error} idPrefix={`${id}-`} labels={{ code: copy.support.bookCodeLabel }} />
      <Field
        id={`${id}-code`}
        label={copy.support.bookCodeLabel}
        help={copy.support.bookCodeHelp}
        error={fieldError(error, "code")}
      >
        <Input
          name="code"
          autoComplete="off"
          autoCapitalize="characters"
          spellCheck={false}
          className="font-mono"
          data-no-draft=""
        />
      </Field>
      <div>
        <Button type="submit" variant="secondary" busy={busy}>
          {copy.support.lookUp}
        </Button>
      </div>
      <p role="status" className="m-0 text-[15px] font-semibold">
        {line}
      </p>
    </form>
  );
}

function DataRequestForm({ ticket }: { ticket: TicketRecord }) {
  const id = `data-request-${ticket.id}`;
  return (
    <ActionForm
      id={id}
      submitLabel={copy.support.dataRequestButton}
      success={copy.support.dataRequestStarted}
      variant="secondary"
      labels={{ kind: copy.support.dataRequestKind, summary: copy.support.dataRequestSummary }}
      onSubmit={(form) =>
        startDataRequest(ticket.number, {
          kind: formText(form, "kind") as Schemas["DataRequestKindEnum"],
          summary: formText(form, "summary"),
        })
      }
    >
      {(error) => (
        <>
          <Field id={`${id}-kind`} label={copy.support.dataRequestKind} error={fieldError(error, "kind")}>
            <Select name="kind" defaultValue={ticket.category === "grievance" ? "grievance" : "access"}>
              {Object.entries(copy.privacy.kinds).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>
          <Field
            id={`${id}-summary`}
            label={copy.support.dataRequestSummary}
            optional
            help={copy.support.dataRequestSummaryHelp}
            error={fieldError(error, "summary")}
          >
            <Textarea name="summary" rows={2} maxLength={300} />
          </Field>
        </>
      )}
    </ActionForm>
  );
}

export function TicketActions({ ticket }: { ticket: TicketRecord }) {
  const can = useCan();
  const orders = ticket.sidebar.orders;
  return (
    <div className="flex flex-col gap-8">
      {orders ? (
        <section aria-labelledby={`orders-${ticket.id}`} className="flex flex-col gap-3">
          <h3 id={`orders-${ticket.id}`} className="m-0 font-head text-lg">
            {copy.support.ordersActions}
          </h3>
          <p className="m-0 text-sm text-muted-foreground">{copy.support.ordersLead}</p>
          {orders.length ? (
            orders.map((order) => <OrderActions key={order.number} ticket={ticket} order={order} />)
          ) : (
            <p className="m-0 text-[15px] text-muted-foreground">{copy.support.noOrders}</p>
          )}
        </section>
      ) : null}
      {ticket.sidebar.entitlements && can(P.accessExtend) ? (
        <section aria-labelledby={`extend-${ticket.id}-title`} className="flex flex-col gap-3">
          <h3 id={`extend-${ticket.id}-title`} className="m-0 font-head text-lg">
            {copy.support.extend}
          </h3>
          <ExtendForm ticket={ticket} />
        </section>
      ) : null}
      {can(P.bookCodesView) ? (
        <section aria-labelledby={`code-${ticket.id}-title`} className="flex flex-col gap-3">
          <h3 id={`code-${ticket.id}-title`} className="m-0 font-head text-lg">
            {copy.support.bookCode}
          </h3>
          <BookCodeLookup ticket={ticket} />
        </section>
      ) : null}
      {dataRequestOpen(ticket, can) ? (
        <section aria-labelledby={`data-request-${ticket.id}-title`} className="flex flex-col gap-3">
          <h3 id={`data-request-${ticket.id}-title`} className="m-0 font-head text-lg">
            {copy.support.startDataRequest}
          </h3>
          <p className="m-0 text-sm text-muted-foreground">{copy.support.dataRequestLead}</p>
          <DataRequestForm ticket={ticket} />
        </section>
      ) : null}
    </div>
  );
}
