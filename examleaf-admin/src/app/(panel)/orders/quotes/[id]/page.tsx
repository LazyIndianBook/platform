// /orders/quotes/<id>/: one quotation request (GET orders/quotes/{id}/): the school and contact (masked), its books,
// discount and shipping, the quotation PDF, and its conversion to a staff order (once; a change request above the
// person's discount limit). One that became an order links to it; one whose order waits for approval says which
// change request.
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Problem } from "@/components/data/problem";
import { Facts, RecordPage } from "@/components/data/record-page";
import { recordSide } from "@/components/data/record-side";
import { StatusChip } from "@/components/data/status-chip";
import { stateTone } from "@/components/modules/orders/format";
import { QuoteConvert, QuoteItems } from "@/components/modules/orders/quotes";
import { Section } from "@/components/shell/page-header";
import { Alert } from "@/components/ui/alert";
import { ApiError } from "@/lib/api/errors";
import { attempt, recordId, staffPage } from "@/lib/api/page";
import { getQuote, quotationHref } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDate, formatDateTime } from "@/lib/format";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.orders.quotes.title };

export default async function QuotePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { manifest, transport, path } = await staffPage(`/orders/quotes/${encodeURIComponent(id)}/`);
  if (!has(manifest, P.quotesView)) notFound();
  const quote = await attempt(getQuote(recordId(id), transport), path, "404");
  const back = { href: "/orders/quotes/", label: copy.orders.quotes.title };
  if (quote instanceof ApiError) {
    return (
      <RecordPage title={copy.orders.quotes.title} back={back}>
        <Problem error={quote} />
      </RecordPage>
    );
  }
  const q = copy.orders.quotes;
  const f = q.facts;
  return (
    <RecordPage
      eyebrow={q.eyebrow}
      title={quote.school}
      back={back}
      status={<StatusChip tone={stateTone(quote.status)}>{labelOf(q.statuses, quote.status)}</StatusChip>}
      side={recordSide({
        manifest,
        transport,
        path,
        audit: { target_type: "shop.quoterequest", target_id: String(quote.id) },
        note: { type: "shop.quoterequest", id: String(quote.id) },
      })}
    >
      <Section id="details" title={copy.common.details}>
        <Facts
          items={[
            { label: f.school, value: `${quote.school} (${quote.number})` },
            { label: f.contact, value: quote.contact_name },
            { label: f.email, value: <span className="font-mono">{quote.email}</span> },
            { label: f.phone, value: <span className="font-mono">{quote.phone}</span> },
            ...(quote.gstin ? [{ label: f.gstin, value: <span className="font-mono">{quote.gstin}</span> }] : []),
            { label: f.pin, value: quote.delivery_pin },
            { label: f.discount, value: `${Number(quote.discount_percent)}%` },
            { label: f.shipping, value: `₹${Number(quote.shipping_fee).toLocaleString("en-IN")}` },
            { label: f.quoted, value: quote.quoted_at ? formatDateTime(quote.quoted_at) : copy.common.none },
            ...(quote.valid_until ? [{ label: f.valid, value: formatDate(quote.valid_until) }] : []),
          ]}
        />
        {quote.has_quotation ? (
          <p className="m-0">
            {/* the API's PDF (the session's cookie): a page load, not a route here */}
            <a href={quotationHref(quote.id)} className="font-semibold">
              {q.quotation}
            </a>
          </p>
        ) : (
          <p className="m-0 text-[15px] text-muted-foreground">{q.noQuotation}</p>
        )}
      </Section>
      <Section id="items" title={q.items}>
        <QuoteItems quote={quote} />
      </Section>
      {quote.note ? (
        <Section id="note" title={q.note}>
          <p className="m-0 text-[15px] whitespace-pre-line">{quote.note}</p>
        </Section>
      ) : null}
      <Section id="convert" title={q.convert}>
        {quote.order ? (
          <p className="m-0 text-[15px]">
            {has(manifest, P.ordersView) ? (
              <Link href={`/orders/${encodeURIComponent(quote.order)}/`} className="font-semibold">
                {q.ordered(quote.order)}
              </Link>
            ) : (
              q.ordered(quote.order)
            )}
          </p>
        ) : quote.waiting ? (
          <Alert variant="info" title={q.waiting(String(quote.waiting))}>
            <p>
              <Link href={`/approvals/${quote.waiting}/`} className="font-semibold">
                {copy.approval.open}
              </Link>
            </p>
          </Alert>
        ) : has(manifest, P.quotesChange) && has(manifest, P.ordersAdd) ? (
          <QuoteConvert quote={quote} />
        ) : (
          <p className="m-0 text-[15px] text-muted-foreground">{copy.common.none}</p>
        )}
      </Section>
    </RecordPage>
  );
}
