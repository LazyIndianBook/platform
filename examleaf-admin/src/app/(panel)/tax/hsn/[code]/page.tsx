// /tax/hsn/<code>/: one code of the master (GET tax/hsn/{code}/): its rate today and the change to come, its history
// with each rate's dates and notification, the products on it (and how they disagree), a new dated rate behind the
// save bar (POST tax/hsn/{code}/rates/) for whoever may change the master; its notes and audit events beside.
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Problem } from "@/components/data/problem";
import { Facts, RecordPage } from "@/components/data/record-page";
import { recordSide } from "@/components/data/record-side";
import { StatusChip } from "@/components/data/status-chip";
import { NewRateForm } from "@/components/modules/tax/hsn";
import { LinkedProducts, RatesTable, rateText } from "@/components/modules/tax/records";
import { Section } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, staffPage } from "@/lib/api/page";
import { getHsnCode } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.tax.hsnTitle };

export default async function HsnCodePage({ params }: { params: Promise<{ code: string }> }) {
  const { code } = await params;
  if (!/^\d{4,8}$/.test(code)) notFound();
  const { manifest, transport, path } = await staffPage(`/tax/hsn/${code}/`);
  const found = await attempt(getHsnCode(code, transport), path, "404");
  const back = { href: "/tax/hsn/", label: copy.tax.hsnTitle };
  if (found instanceof ApiError) {
    return (
      <RecordPage title={code} back={back}>
        <Problem error={found} />
      </RecordPage>
    );
  }
  return (
    <RecordPage
      eyebrow={labelOf(copy.tax.kinds, found.kind)}
      title={<span className="font-mono">{found.code}</span>}
      lead={found.description}
      back={back}
      status={
        found.today ? (
          <StatusChip tone={found.today.taxability === "taxable" ? "moving" : "stopped"}>
            {copy.tax.rate(found.today.rate)} · {labelOf(copy.tax.taxability, found.today.taxability)}
          </StatusChip>
        ) : (
          <StatusChip tone="bad">{copy.tax.noRate}</StatusChip>
        )
      }
      side={recordSide({
        manifest,
        transport,
        path,
        audit: { target_type: "shop.hsncode", target_id: found.code },
        note: { type: "shop.hsncode", id: found.code },
      })}
    >
      <Facts
        items={[
          { label: copy.tax.kind, value: labelOf(copy.tax.kinds, found.kind) },
          { label: copy.tax.unit, value: <span className="font-mono">{found.uqc}</span> },
          { label: copy.tax.today, value: found.today ? rateText(found.today) : copy.tax.noRate },
          { label: copy.tax.nextChange, value: found.next_change ? rateText(found.next_change) : copy.tax.noChange },
        ]}
      />
      <Section id="rates" title={copy.tax.rates} lead={copy.tax.ratesLead}>
        <RatesTable rates={found.rates} />
      </Section>
      <Section id="products" title={copy.tax.productsOn}>
        <LinkedProducts products={found.linked} />
      </Section>
      {has(manifest, P.taxHsnChange) ? (
        <Section id="new-rate" title={copy.tax.newRate} lead={copy.tax.newRateLead}>
          <NewRateForm code={found.code} />
        </Section>
      ) : null}
    </RecordPage>
  );
}
