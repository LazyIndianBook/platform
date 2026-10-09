// /finance/payments/<id>/: one payment (GET finance/payments/{id}/; a child's order's: the server records the read).
// Its facts and Razorpay's ids, the fee and its settlement once settled, "Ask Razorpay again" for an online payment
// (staff.replay_webhook), its refunds, the webhooks seen and what the last one said (its allowed fields), and its
// timeline; notes and audit events beside.
import type { Metadata } from "next";
import Link from "next/link";

import { Problem } from "@/components/data/problem";
import { Facts, RecordPage } from "@/components/data/record-page";
import { recordSide } from "@/components/data/record-side";
import { inr } from "@/components/modules/finance/format";
import {
  LastWebhook,
  PaymentRefunds,
  PaymentState,
  PaymentWebhooks,
  ReconcileButton,
} from "@/components/modules/finance/payments";
import { OrderTimeline } from "@/components/modules/orders/order-record";
import { Section } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, recordId, staffPage } from "@/lib/api/page";
import { getFinancePayment } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDate, formatDateTime } from "@/lib/format";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.finance.paymentsTitle };

const mono = (value: string | null | undefined) =>
  value ? <span className="font-mono text-[14px] break-all">{value}</span> : copy.common.none;

export default async function PaymentPage({ params }: { params: Promise<{ id: string }> }) {
  const id = recordId((await params).id);
  const { manifest, transport, path } = await staffPage(`/finance/payments/${id}/`);
  const found = await attempt(getFinancePayment(id, transport), path, "404");
  const back = { href: "/finance/payments/", label: copy.finance.paymentsTitle };
  const title = copy.finance.rowName("payment", id);
  if (found instanceof ApiError) {
    return (
      <RecordPage title={title} back={back}>
        <Problem error={found} />
      </RecordPage>
    );
  }
  const online = found.method === "razorpay";
  return (
    <RecordPage
      eyebrow={labelOf(copy.orders.methods, found.method)}
      title={title}
      lead={copy.finance.paymentLead(found.order, inr(found.amount))}
      back={back}
      status={<PaymentState payment={found} />}
      side={recordSide({
        manifest,
        transport,
        path,
        audit: { target_type: "shop.payment", target_id: String(found.id) },
        note: { type: "shop.payment", id: String(found.id) },
      })}
    >
      <Facts
        items={[
          {
            label: copy.finance.facts.order,
            value: (
              <Link href={`/orders/${encodeURIComponent(found.order)}/`} className="font-mono font-semibold">
                {found.order}
              </Link>
            ),
          },
          { label: copy.finance.facts.orderStatus, value: labelOf(copy.orders.statuses, found.order_status) },
          { label: copy.finance.facts.orderTotal, value: inr(found.order_total) },
          { label: copy.finance.facts.amount, value: inr(found.amount) },
          ...(online
            ? [
                { label: copy.finance.facts.razorpayOrder, value: mono(found.razorpay_order_id) },
                { label: copy.finance.facts.razorpayPayment, value: mono(found.razorpay_payment_id) },
                ...(found.razorpay_payment_link_id
                  ? [{ label: copy.finance.facts.razorpayLink, value: mono(found.razorpay_payment_link_id) }]
                  : []),
              ]
            : [{ label: copy.finance.facts.reference, value: mono(found.reference) }]),
          { label: copy.finance.facts.fee, value: found.fee === null ? copy.finance.notSettled : inr(found.fee) },
          { label: copy.finance.facts.feeTax, value: found.tax === null ? copy.finance.notSettled : inr(found.tax) },
          {
            label: copy.finance.facts.settlement,
            value: found.settlement ? (
              <Link href={`/finance/settlements/${found.settlement.id}/`} className="font-semibold">
                {found.settlement.settlement_id} · {formatDate(found.settlement.date)}
              </Link>
            ) : (
              copy.finance.notSettled
            ),
          },
          ...(found.error ? [{ label: copy.finance.facts.error, value: found.error }] : []),
          { label: copy.finance.facts.created, value: formatDateTime(found.created) },
        ]}
      />
      {online && has(manifest, P.reconcile) ? (
        <Section id="ask" title={copy.finance.askTitle} lead={copy.finance.askLead}>
          <ReconcileButton payment={found} />
        </Section>
      ) : null}
      <Section id="refunds" title={copy.finance.refundsOf}>
        <PaymentRefunds refunds={found.refunds} />
      </Section>
      {online ? (
        <Section id="webhooks" title={copy.finance.webhooksTitle} lead={copy.finance.webhooksLead}>
          <PaymentWebhooks webhooks={found.webhooks} />
          <LastWebhook payload={found.last_webhook} />
        </Section>
      ) : null}
      <Section id="timeline" title={copy.orders.sections.timeline}>
        <OrderTimeline entries={found.timeline} />
      </Section>
    </RecordPage>
  );
}
