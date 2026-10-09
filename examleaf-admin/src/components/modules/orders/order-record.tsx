// An order's record, the parts that only show (GET orders/{number}/): its books with what each was invoiced at, the
// money in and out, the documents, the parcels, the customer (masked: the full view is the customer's page), the
// cash-on-delivery risk, its returns, its ERPNext documents and its timeline (the history, payments, parcels,
// messages, notes, returns and, for whoever reads the audit log, its audit events).
import Link from "next/link";

import { Facts } from "@/components/data/record-page";
import { StatusChip } from "@/components/data/status-chip";
import type { OrderDetail, OrderTimelineEntry } from "@/lib/api/staff";
import { copy, humanize, labelOf } from "@/lib/copy";
import { formatDate, formatDateTime } from "@/lib/format";

import { riskTone, rupees, stateTone } from "./format";

const none = <p className="m-0 text-[15px] text-muted-foreground">{copy.common.none}</p>;

function Wrap({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div data-slot="table-wrap" className="table-wrap" role="region" aria-label={copy.table.region(label)} tabIndex={0}>
      {children}
    </div>
  );
}

export function OrderLines({ order }: { order: OrderDetail }) {
  const c = copy.orders.lineColumns;
  return (
    <Wrap label={copy.orders.sections.lines}>
      <table>
        <caption className="sr-only">{copy.orders.sections.lines}</caption>
        <thead>
          <tr>
            <th scope="col">{c.title}</th>
            <th scope="col">{c.hsn}</th>
            <th scope="col" className="num">
              {c.copies}
            </th>
            <th scope="col" className="num">
              {c.price}
            </th>
            <th scope="col" className="num">
              {c.discount}
            </th>
            <th scope="col" className="num">
              {c.invoiced}
            </th>
            <th scope="col" className="num">
              {c.refunded}
            </th>
          </tr>
        </thead>
        <tbody>
          {order.lines.map((line) => (
            <tr key={line.id}>
              <td className="min-w-48">
                <span className="flex flex-col">
                  <span>{line.title}</span>
                  {line.isbn ? <span className="font-mono text-[13px] text-muted-foreground">{line.isbn}</span> : null}
                </span>
              </td>
              <td className="font-mono text-[14px] whitespace-nowrap">
                {line.hsn_code} · {Number(line.gst_rate)}%
              </td>
              <td className="num">{line.quantity}</td>
              <td className="num">{rupees(line.unit_price)}</td>
              <td className="num">{rupees(line.discount)}</td>
              <td className="num">{rupees(line.invoiced)}</td>
              <td className="num">{line.refunded ? `${line.refunded} / ${line.quantity}` : "0"}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <th scope="row" colSpan={5} className="text-left">
              {copy.orders.totals.total}
            </th>
            <td className="num" colSpan={2}>
              {rupees(order.total)}
            </td>
          </tr>
        </tfoot>
      </table>
    </Wrap>
  );
}

export function OrderTotals({ order }: { order: OrderDetail }) {
  return (
    <Facts
      items={[
        { label: copy.orders.totals.subtotal, value: rupees(order.subtotal) },
        ...order.savings.map((saving) => ({ label: saving.label, value: `− ${rupees(saving.amount)}` })),
        ...(order.coupon_code ? [{ label: copy.orders.totals.coupon, value: order.coupon_code }] : []),
        { label: copy.orders.totals.shipping, value: rupees(order.shipping_fee) },
        { label: copy.orders.totals.total, value: <strong>{rupees(order.total)}</strong> },
        { label: copy.orders.columns.payment, value: labelOf(copy.orders.methods, order.payment_method) },
        { label: copy.orders.totals.created, value: formatDateTime(order.created) },
        ...(order.placed_at ? [{ label: copy.orders.totals.placed, value: formatDateTime(order.placed_at) }] : []),
        ...(order.created_by ? [{ label: copy.orders.totals.createdBy, value: order.created_by }] : []),
        ...(order.quote ? [{ label: copy.orders.totals.quote, value: order.quote }] : []),
      ]}
    />
  );
}

export function OrderPayments({ order }: { order: OrderDetail }) {
  if (!order.payments.length) return <p className="m-0 text-[15px] text-muted-foreground">{copy.orders.noPayments}</p>;
  const c = copy.orders.paymentColumns;
  return (
    <Wrap label={copy.orders.sections.payments}>
      <table>
        <caption className="sr-only">{copy.orders.sections.payments}</caption>
        <thead>
          <tr>
            <th scope="col">{c.method}</th>
            <th scope="col" className="num">
              {c.amount}
            </th>
            <th scope="col">{c.status}</th>
            <th scope="col">{c.reference}</th>
            <th scope="col">{c.date}</th>
            <th scope="col" className="num">
              {c.left}
            </th>
          </tr>
        </thead>
        <tbody>
          {order.payments.map((payment) => (
            <tr key={payment.id}>
              <td>{labelOf(copy.orders.methods, payment.method)}</td>
              <td className="num">{rupees(payment.amount)}</td>
              <td>
                <span className="inline-flex flex-wrap gap-1.5">
                  <StatusChip tone={stateTone(payment.status)}>
                    {labelOf(copy.orders.paymentStatuses, payment.status)}
                  </StatusChip>
                  {payment.older_than_6_months ? <StatusChip tone="waiting">{copy.orders.older}</StatusChip> : null}
                </span>
              </td>
              <td className="font-mono text-[13px] break-all">
                {payment.razorpay_payment_id || payment.reference || payment.razorpay_order_id || copy.common.none}
              </td>
              <td className="whitespace-nowrap">{formatDateTime(payment.created)}</td>
              <td className="num">{rupees(payment.refundable)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Wrap>
  );
}

export function OrderDocuments({ order }: { order: OrderDetail }) {
  if (!order.documents.length)
    return <p className="m-0 text-[15px] text-muted-foreground">{copy.orders.documents.none}</p>;
  return (
    <ul className="m-0 flex list-none flex-col gap-2 p-0 text-[15px]">
      {order.documents.map((document) => (
        <li key={`${document.kind}-${document.id}`} className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="font-semibold">{copy.orders.documents[document.kind]}</span>
          <span className="font-mono text-[14px]">{document.number}</span>
          {document.amount ? <span>{rupees(document.amount)}</span> : null}
          <span className="text-muted-foreground">{formatDate(document.created)}</span>
          {document.ready ? (
            // a PDF of the API (the session's cookie): a page load, not a route here
            <a href={document.url} className="inline-flex min-h-11 items-center font-semibold">
              {copy.orders.download}
              <span className="sr-only">: {document.number}</span>
            </a>
          ) : (
            <StatusChip tone="waiting">{copy.orders.documents.notReady}</StatusChip>
          )}
        </li>
      ))}
    </ul>
  );
}

export function OrderParcels({ order }: { order: OrderDetail }) {
  if (!order.shipments.length) return <p className="m-0 text-[15px] text-muted-foreground">{copy.orders.noParcels}</p>;
  const c = copy.orders.parcelColumns;
  return (
    <Wrap label={copy.orders.sections.parcels}>
      <table>
        <caption className="sr-only">{copy.orders.sections.parcels}</caption>
        <thead>
          <tr>
            <th scope="col">{c.courier}</th>
            <th scope="col">{c.tracking}</th>
            <th scope="col">{c.state}</th>
            <th scope="col">{c.last}</th>
            <th scope="col">{c.sent}</th>
          </tr>
        </thead>
        <tbody>
          {order.shipments.map((parcel) => (
            <tr key={parcel.id}>
              <td>{parcel.detail?.courier_name || parcel.courier}</td>
              <td className="font-mono text-[14px]">
                {parcel.tracking_url ? (
                  <a href={parcel.tracking_url} target="_blank" rel="noopener noreferrer">
                    {parcel.tracking_number} <span className="sr-only">{copy.common.opensElsewhere}</span>
                  </a>
                ) : (
                  parcel.tracking_number || copy.common.none
                )}
              </td>
              <td>
                {parcel.detail?.status
                  ? labelOf(copy.orders.parcels, parcel.detail.status)
                  : parcel.delivered_at
                    ? copy.orders.parcels.delivered
                    : copy.common.none}
              </td>
              <td className="min-w-40">
                {parcel.last_event
                  ? `${parcel.last_event.carrier_label || humanize(parcel.last_event.status ?? "")}${parcel.last_event.location ? `, ${parcel.last_event.location}` : ""} · ${formatDateTime(parcel.last_event.occurred_at)}`
                  : copy.common.none}
              </td>
              <td className="whitespace-nowrap">{formatDateTime(parcel.shipped_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Wrap>
  );
}

export function OrderCustomer({ order, canOpen }: { order: OrderDetail; canOpen: boolean }) {
  const address = order.address;
  return (
    <div className="flex flex-col gap-3">
      <Facts
        items={[
          { label: copy.orders.customer.name, value: order.customer.name || copy.common.none },
          { label: copy.orders.customer.email, value: <span className="font-mono">{order.customer.email}</span> },
          { label: copy.orders.customer.phone, value: <span className="font-mono">{order.customer.phone}</span> },
          {
            label: copy.orders.customer.address,
            value: [
              address.line1,
              address.line2,
              address.city,
              address.district,
              labelOf(copy.orders.states, address.state),
              address.pin,
            ]
              .filter(Boolean)
              .join(", "),
          },
        ]}
      />
      {order.customer.id === null ? (
        <p className="m-0 text-[15px] text-muted-foreground">{copy.orders.customer.guest}</p>
      ) : canOpen ? (
        <p className="m-0">
          <Link href={`/users/${order.customer.id}/`} className="font-semibold">
            {copy.orders.customer.account}
          </Link>
        </p>
      ) : null}
    </div>
  );
}

export function OrderRisk({ order }: { order: OrderDetail }) {
  if (!order.risk_bucket) return <p className="m-0 text-[15px] text-muted-foreground">{copy.orders.risk.none}</p>;
  return (
    <div className="flex flex-col gap-2">
      <p className="m-0">
        <StatusChip tone={riskTone(order.risk_bucket)}>{labelOf(copy.orders.risks, order.risk_bucket)}</StatusChip>
      </p>
      {order.risk_reasons.length ? (
        <ul className="m-0 pl-5 text-[15px]">
          {order.risk_reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export function OrderReturns({ order }: { order: OrderDetail }) {
  if (!order.returns.length) return none;
  return (
    <ul className="m-0 flex list-none flex-col gap-2 p-0 text-[15px]">
      {order.returns.map((back) => (
        <li key={back.id} className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <Link href={`/orders/returns/${back.id}/`} className="font-mono font-semibold">
            {back.number}
          </Link>
          <StatusChip tone={stateTone(back.status)}>{labelOf(copy.orders.returns.statuses, back.status)}</StatusChip>
          <span>{back.reason_label}</span>
          <span className="text-muted-foreground">{formatDate(back.created)}</span>
        </li>
      ))}
    </ul>
  );
}

export function OrderErp({ order }: { order: OrderDetail }) {
  if (!order.erp.length) return <p className="m-0 text-[15px] text-muted-foreground">{copy.orders.noErp}</p>;
  return (
    <ul className="m-0 flex list-none flex-col gap-1 p-0 text-[15px]">
      {order.erp.map((link) => (
        <li key={`${link.model}-${link.object_id}`}>
          {link.doctype} <span className="font-mono">{link.name}</span>
          <span className="text-muted-foreground"> · {formatDateTime(link.synced_at)}</span>
        </li>
      ))}
    </ul>
  );
}

export function OrderTimeline({ entries }: { entries: OrderTimelineEntry[] }) {
  if (!entries.length) return <p className="m-0 text-[15px] text-muted-foreground">{copy.orders.noTimeline}</p>;
  return (
    <ol aria-label={copy.orders.sections.timeline} className="m-0 flex list-none flex-col gap-0 p-0">
      {entries.map((entry, index) => (
        <li
          key={`${entry.at}-${index}`}
          className="grid grid-cols-[minmax(7rem,auto)_minmax(0,1fr)] gap-x-4 border-b border-border py-2 text-[15px] last:border-b-0"
        >
          <span className="font-mono text-[12px] tracking-[0.04em] text-muted-foreground uppercase">
            {labelOf(copy.orders.timelineKinds, entry.kind)}
          </span>
          <span className="flex min-w-0 flex-col">
            <span className="break-words">{entry.label}</span>
            <span className="text-sm text-muted-foreground">
              {entry.actor ? `${entry.actor} · ` : ""}
              <time dateTime={entry.at}>{formatDateTime(entry.at)}</time>
            </span>
          </span>
        </li>
      ))}
    </ol>
  );
}
