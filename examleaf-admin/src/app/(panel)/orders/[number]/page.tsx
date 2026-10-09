// /orders/<number>/: one order (GET orders/{number}/; a child's order: the server records the read as a look at a
// child's data). The header with its status and the one next action the API names; its books and money, payments,
// refunds, documents, parcels, the customer masked (the full view is theirs), the COD risk, the hold and tags, its
// returns, the actions, its ERPNext documents and the timeline; notes and audit events beside; Danger last (cancel,
// the refund dialog, a return). The address takes an order's id too: the inbox's and the audit trail's links use it.
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Problem } from "@/components/data/problem";
import { RecordPage } from "@/components/data/record-page";
import { recordSide } from "@/components/data/record-side";
import { NextAction, OrderMoves } from "@/components/modules/orders/order-actions";
import { OrderBadges, OrderStatus } from "@/components/modules/orders/order-badges";
import { hasDanger } from "@/components/modules/orders/format";
import { OrderDanger } from "@/components/modules/orders/order-danger";
import { HoldAndTags, OrderRefunds } from "@/components/modules/orders/order-panels";
import {
  OrderCustomer,
  OrderDocuments,
  OrderErp,
  OrderLines,
  OrderParcels,
  OrderPayments,
  OrderReturns,
  OrderRisk,
  OrderTimeline,
  OrderTotals,
} from "@/components/modules/orders/order-record";
import { Section } from "@/components/shell/page-header";
import { Alert } from "@/components/ui/alert";
import { ApiError } from "@/lib/api/errors";
import { attempt, staffPage } from "@/lib/api/page";
import { getOrder } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.orders.title };

export default async function OrderPage({ params }: { params: Promise<{ number: string }> }) {
  const { number } = await params;
  const { manifest, transport, path } = await staffPage(`/orders/${encodeURIComponent(number)}/`);
  if (!has(manifest, P.ordersView)) notFound();
  const order = await attempt(getOrder(number, transport), path, "404");
  const back = { href: "/orders/", label: copy.orders.title };
  if (order instanceof ApiError) {
    return (
      <RecordPage title={copy.orders.title} back={back}>
        <Problem error={order} />
      </RecordPage>
    );
  }
  const s = copy.orders.sections;
  return (
    <RecordPage
      eyebrow={copy.orders.eyebrow}
      title={<span className="font-mono">{order.number}</span>}
      back={back}
      status={
        <>
          <OrderStatus order={order} />
          <OrderBadges order={order} />
        </>
      }
      actions={<NextAction order={order} />}
      side={recordSide({
        manifest,
        transport,
        path,
        audit: { target_type: "shop.order", target_id: String(order.id) },
        note: { type: "shop.order", id: String(order.id) },
      })}
      danger={hasDanger(order) ? <OrderDanger order={order} /> : undefined}
      dangerTitle={copy.orders.danger}
    >
      {order.customer.is_minor ? <Alert variant="warning" title={copy.orders.recordLogged} /> : null}
      {order.is_test ? <Alert variant="info" title={copy.orders.testOrder} /> : null}
      <Section id="lines" title={s.lines}>
        <OrderLines order={order} />
        <OrderTotals order={order} />
      </Section>
      <Section id="payments" title={s.payments}>
        <OrderPayments order={order} />
      </Section>
      <Section id="refunds" title={s.refunds}>
        <OrderRefunds order={order} />
      </Section>
      <Section id="documents" title={s.documents}>
        <OrderDocuments order={order} />
      </Section>
      <Section id="parcels" title={s.parcels}>
        <OrderParcels order={order} />
      </Section>
      <Section id="customer" title={s.customer}>
        <OrderCustomer order={order} canOpen={has(manifest, P.usersView)} />
      </Section>
      {order.is_cod || order.risk_bucket ? (
        <Section id="risk" title={s.risk}>
          <OrderRisk order={order} />
        </Section>
      ) : null}
      <Section id="hold" title={s.hold}>
        <HoldAndTags order={order} />
      </Section>
      {order.returns.length ? (
        <Section id="returns" title={s.returns}>
          <OrderReturns order={order} />
        </Section>
      ) : null}
      <Section id="actions" title={s.actions} lead={copy.orders.actionsLead}>
        <OrderMoves order={order} />
      </Section>
      <Section id="erp" title={s.erp}>
        <OrderErp order={order} />
      </Section>
      <Section id="timeline" title={s.timeline}>
        <OrderTimeline entries={order.timeline} />
      </Section>
    </RecordPage>
  );
}
