// /orders/returns/<id>/: one return (GET orders/returns/{id}/): its state and next step, the books, the customer's
// words, the decision, the return label, the photographs; notes and audit events beside. Its refund opens the
// order's refund dialog with the return named (its lines).
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Problem } from "@/components/data/problem";
import { Facts, RecordPage } from "@/components/data/record-page";
import { recordSide } from "@/components/data/record-side";
import { StatusChip } from "@/components/data/status-chip";
import { stateTone } from "@/components/modules/orders/format";
import { ReturnActions } from "@/components/modules/orders/return-actions";
import { Section } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, recordId, staffPage } from "@/lib/api/page";
import { getOrder, getReturn, returnPhotoHref } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDateTime } from "@/lib/format";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.orders.returns.title };

export default async function ReturnPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { manifest, transport, path } = await staffPage(`/orders/returns/${encodeURIComponent(id)}/`);
  if (!has(manifest, P.returnsView)) notFound();
  const back = await attempt(getReturn(recordId(id), transport), path, "404");
  const up = { href: "/orders/returns/", label: copy.orders.returns.title };
  if (back instanceof ApiError) {
    return (
      <RecordPage title={copy.orders.returns.title} back={up}>
        <Problem error={back} />
      </RecordPage>
    );
  }
  // the refund dialog reads the order's refund facts (payment, methods, warnings)
  const refunding = back.next.includes("refund") && has(manifest, P.refundOrder);
  const order = refunding ? await attempt(getOrder(back.order, transport), path) : null;
  const r = copy.orders.returns;
  return (
    <RecordPage
      eyebrow={r.eyebrow}
      title={<span className="font-mono">{back.number}</span>}
      back={up}
      status={<StatusChip tone={stateTone(back.status)}>{labelOf(r.statuses, back.status)}</StatusChip>}
      side={recordSide({
        manifest,
        transport,
        path,
        audit: { target_type: "shop.returnrequest", target_id: String(back.id) },
        note: { type: "shop.returnrequest", id: String(back.id) },
      })}
    >
      <Section id="next" title={r.next}>
        {order instanceof ApiError ? <Problem error={order} /> : null}
        <ReturnActions back={back} order={order instanceof ApiError ? null : order} />
      </Section>
      <Section id="details" title={copy.common.details}>
        <Facts
          items={[
            {
              label: r.facts.order,
              value: has(manifest, P.ordersView) ? (
                <Link href={`/orders/${encodeURIComponent(back.order)}/`} className="font-mono">
                  {back.order}
                </Link>
              ) : (
                <span className="font-mono">{back.order}</span>
              ),
            },
            { label: r.facts.reason, value: back.reason_label },
            { label: r.facts.by, value: back.by_customer ? r.byCustomer : r.byStaff },
            { label: r.facts.asked, value: formatDateTime(back.created) },
            ...(back.decision_note ? [{ label: r.facts.decision, value: back.decision_note }] : []),
            ...(back.return_awb
              ? [{ label: r.facts.label, value: `${back.return_courier} ${back.return_awb}`.trim() }]
              : []),
            ...(back.received_at ? [{ label: r.facts.received, value: formatDateTime(back.received_at) }] : []),
            ...(back.inspected_at ? [{ label: r.facts.inspected, value: formatDateTime(back.inspected_at) }] : []),
            ...(back.refund ? [{ label: r.facts.refund, value: `#${back.refund}` }] : []),
          ]}
        />
      </Section>
      <Section id="books" title={r.lines}>
        <ul className="m-0 flex list-none flex-col gap-1 p-0 text-[15px]">
          {back.lines.map((line) => (
            <li key={line.item}>
              {line.title} <span className="font-mono text-muted-foreground">× {line.quantity}</span>
            </li>
          ))}
        </ul>
      </Section>
      <Section id="note" title={r.note}>
        <p className="m-0 text-[15px] whitespace-pre-line">{back.note || r.noNote}</p>
      </Section>
      <Section id="photos" title={r.photos}>
        {back.photos ? (
          <ul className="m-0 flex list-none flex-wrap gap-3 p-0">
            {Array.from({ length: back.photos }, (_, index) => (
              <li key={index}>
                {/* the API's image (the session's cookie): a page load, not a route here */}
                <a href={returnPhotoHref(back.id, index)} className="font-semibold">
                  {r.photo(index)}
                </a>
              </li>
            ))}
          </ul>
        ) : (
          <p className="m-0 text-[15px] text-muted-foreground">{r.noPhotos}</p>
        )}
      </Section>
    </RecordPage>
  );
}
