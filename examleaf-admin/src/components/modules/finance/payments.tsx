"use client";

// Payments (GET finance/payments/?status=&method=&stuck=&created_from=&created_to=&livemode=&q=), newest first, with
// Razorpay's ids and, once settled, the fee: the "Stuck" tab is the API's own filter (waiting on Razorpay too long, or
// captured on an order still pending). On a payment's record, "Ask Razorpay again" (POST finance/payments/{id}/
// reconcile/, staff.replay_webhook): Razorpay's answer recorded by the backend, which says what it changed.
import { useRouter } from "next/navigation";
import { useState } from "react";

import { type Column, DataTable } from "@/components/data/data-table";
import { StatusChip } from "@/components/data/status-chip";
import { ErrorSummary } from "@/components/forms/error-summary";
import { useAction } from "@/components/forms/use-action";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { toast } from "@/components/ui/toaster";
import {
  type FinancePayment,
  type FinancePaymentDetail,
  type FinanceReconciled,
  reconcileFinancePayment,
  type SavedView,
} from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDate, formatDateTime } from "@/lib/format";

import { inr, toneOfFinance } from "./format";

/** A payment's status as a chip, with what else the API marks: stuck, a link, TEST. */
export function PaymentState({
  payment,
}: {
  payment: Pick<FinancePayment, "status" | "stuck" | "is_test" | "is_link">;
}) {
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      <StatusChip tone={toneOfFinance(payment.status)}>
        {labelOf(copy.orders.paymentStatuses, payment.status)}
      </StatusChip>
      {payment.stuck ? <StatusChip tone="bad">{copy.finance.stuck}</StatusChip> : null}
      {payment.is_link ? <StatusChip tone="stopped">{copy.finance.linkChip}</StatusChip> : null}
      {payment.is_test ? <StatusChip tone="stopped">{copy.finance.test}</StatusChip> : null}
    </span>
  );
}

export function PaymentsTable({
  rows,
  next,
  previous,
  views,
}: {
  rows: FinancePayment[];
  next: string | null;
  previous: string | null;
  views: SavedView[] | null;
}) {
  const c = copy.finance.paymentColumns;
  const columns: Column<FinancePayment>[] = [
    { key: "payment", label: c.payment, render: (row) => <span className="font-mono">#{row.id}</span> },
    { key: "order", label: c.order, render: (row) => <span className="font-mono text-[14px]">{row.order}</span> },
    { key: "method", label: c.method, render: (row) => labelOf(copy.orders.methods, row.method) },
    { key: "status", label: c.status, render: (row) => <PaymentState payment={row} /> },
    { key: "amount", label: c.amount, render: (row) => inr(row.amount), numeric: true },
    {
      key: "razorpay",
      label: c.razorpay,
      render: (row) => (
        <span className="font-mono text-[14px]">
          {row.razorpay_payment_id || row.razorpay_payment_link_id || row.reference || copy.common.none}
        </span>
      ),
    },
    { key: "created", label: c.created, render: (row) => formatDateTime(row.created) },
    { key: "fee", label: c.fee, render: (row) => inr(row.fee), numeric: true, hidden: true },
    {
      key: "settlement",
      label: c.settlement,
      render: (row) =>
        row.settlement ? (
          <span className="font-mono text-[14px]">
            {row.settlement.settlement_id} · {formatDate(row.settlement.date)}
          </span>
        ) : (
          copy.finance.notSettled
        ),
      hidden: true,
    },
  ];
  return (
    <DataTable
      listKey="finance-payments"
      caption={copy.finance.paymentsTitle}
      rows={rows}
      columns={columns}
      rowId={(row) => String(row.id)}
      rowHref={(row) => `/finance/payments/${row.id}/`}
      next={next}
      previous={previous}
      views={views}
      presets={{
        name: "stuck",
        label: copy.finance.paymentsPresets,
        all: copy.finance.allPayments,
        options: [{ value: "true", label: copy.finance.stuckPayments }],
      }}
      filters={[
        { name: "q", label: copy.finance.searchPayments, type: "search" },
        {
          name: "status",
          label: c.status,
          type: "select",
          options: Object.entries(copy.orders.paymentStatuses).map(([value, label]) => ({ value, label })),
        },
        {
          name: "method",
          label: c.method,
          type: "select",
          options: Object.entries(copy.orders.methods).map(([value, label]) => ({ value, label })),
        },
        { name: "created_from", label: copy.finance.from, type: "date" },
        { name: "created_to", label: copy.finance.to, type: "date" },
        {
          name: "livemode",
          label: copy.finance.modeFilter,
          type: "select",
          any: copy.finance.modeOptions.default,
          options: [{ value: "false", label: copy.finance.modeOptions.test }],
        },
      ]}
      empty={{ title: copy.finance.paymentsEmptyTitle, text: copy.finance.paymentsEmptyText }}
    />
  );
}

/** "Ask Razorpay again": the backend asks, records what Razorpay took and answers with what changed. */
export function ReconcileButton({ payment }: { payment: Pick<FinancePayment, "id"> }) {
  const router = useRouter();
  const { run, busy, error } = useAction();
  const [answer, setAnswer] = useState<FinanceReconciled | null>(null);
  return (
    <div className="flex flex-col gap-3">
      <div>
        <Button
          variant="secondary"
          size="sm"
          busy={busy}
          onClick={() =>
            run(async () => {
              const result = await reconcileFinancePayment(payment.id);
              setAnswer(result);
              toast.success(copy.finance.asked);
              router.refresh();
            })
          }
        >
          {copy.finance.reconcile}
        </Button>
      </div>
      <ErrorSummary error={error} />
      {answer ? (
        <Alert variant={answer.paid ? "success" : "info"} title={answer.detail}>
          {Object.keys(answer.changes).length ? (
            <ul className="m-0 pl-5">
              {Object.entries(answer.changes).map(([what, change]) => {
                const [before, after] = change as unknown as [unknown, unknown];
                return <li key={what}>{copy.finance.changed(what, String(before ?? ""), String(after ?? ""))}</li>;
              })}
            </ul>
          ) : null}
        </Alert>
      ) : null}
    </div>
  );
}

/** The payment's refunds: how much, how, its state and Razorpay's reference (the ARN once the bank gave it). */
export function PaymentRefunds({ refunds }: { refunds: FinancePaymentDetail["refunds"] }) {
  if (!refunds.length) return <p className="m-0 text-[15px] text-muted-foreground">{copy.orders.noRefunds}</p>;
  const c = copy.finance.refundColumns;
  return (
    <div
      data-slot="table-wrap"
      className="table-wrap"
      role="region"
      aria-label={copy.table.region(copy.finance.refundsOf)}
      tabIndex={0}
    >
      <table>
        <caption className="sr-only">{copy.finance.refundsOf}</caption>
        <thead>
          <tr>
            <th scope="col">{c.refund}</th>
            <th scope="col" className="num">
              {c.amount}
            </th>
            <th scope="col">{c.method}</th>
            <th scope="col">{c.status}</th>
            <th scope="col">{c.reference}</th>
            <th scope="col">{c.asked}</th>
            <th scope="col">{c.made}</th>
          </tr>
        </thead>
        <tbody>
          {refunds.map((refund) => (
            <tr key={refund.id}>
              <td className="font-mono">#{refund.id}</td>
              <td className="num">{inr(refund.amount)}</td>
              <td>
                {labelOf(copy.orders.refundMethods, refund.method)}
                {refund.method === "source" ? (
                  <span className="block text-sm text-muted-foreground">
                    {labelOf(copy.finance.speeds, refund.speed)}
                  </span>
                ) : null}
              </td>
              <td>
                <StatusChip tone={toneOfFinance(refund.status)}>
                  {labelOf(copy.orders.refundStatuses, refund.status)}
                </StatusChip>
              </td>
              <td className="font-mono text-[14px]">{refund.arn || refund.razorpay_refund_id || copy.common.none}</td>
              <td>{formatDateTime(refund.created)}</td>
              <td>{formatDateTime(refund.processed_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Razorpay's webhooks seen for it (kept 7 days), oldest first. */
export function PaymentWebhooks({ webhooks }: { webhooks: FinancePaymentDetail["webhooks"] }) {
  if (!webhooks.length) return <p className="m-0 text-[15px] text-muted-foreground">{copy.finance.noWebhooks}</p>;
  return (
    <ul className="m-0 flex list-none flex-col p-0 text-[15px]">
      {webhooks.map((hook) => (
        <li key={hook.event_id} className="flex flex-wrap gap-x-3 border-b border-border py-2 last:border-b-0">
          <span className="font-mono text-[14px]">{hook.name}</span>
          <span className="text-muted-foreground">{formatDateTime(hook.received_at)}</span>
        </li>
      ))}
    </ul>
  );
}

/** What the last webhook said of it: its allowed fields only (no card, bank or contact field), as Razorpay sent them. */
export function LastWebhook({ payload }: { payload: unknown }) {
  if (!payload || (typeof payload === "object" && !Object.keys(payload).length)) return null;
  return (
    <details>
      <summary className="min-h-11 cursor-pointer text-[15px] font-semibold text-primary">
        {copy.finance.lastWebhook}
      </summary>
      <pre className="m-0 mt-2 max-h-96 overflow-auto rounded-lg border border-border bg-card p-3 font-mono text-[13px]">
        {JSON.stringify(payload, null, 2)}
      </pre>
    </details>
  );
}
