// /finance/settlements/<id>/: one of Razorpay's settlements (GET finance/settlements/{id}/): its figures, what does not
// match (the backend's words), when it matched and when its Journal Entry went to ERPNext (its outbox row's state),
// then its lines (GET finance/settlements/{id}/lines/?matched=&type=&cursor=), a line not ours yet matched by hand by
// FINANCE; notes and audit events beside (each match is one, with its note).
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { Facts, RecordPage } from "@/components/data/record-page";
import { recordSide } from "@/components/data/record-side";
import { inr } from "@/components/modules/finance/format";
import { LinesTable, SettlementState } from "@/components/modules/finance/settlements";
import { Section } from "@/components/shell/page-header";
import { Alert } from "@/components/ui/alert";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, recordId, type SearchParams, staffPage } from "@/lib/api/page";
import { getSettlement, listSettlementLines } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDate, formatDateTime } from "@/lib/format";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.finance.settlements.title };

const words = copy.finance.settlements;

export default async function SettlementPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<SearchParams>;
}) {
  const id = recordId((await params).id);
  const query = await searchParams;
  const { manifest, transport, path } = await staffPage(`/finance/settlements/${id}/`);
  const lines = has(manifest, P.settlementLinesView);
  const filters = { matched: param(query, "matched"), type: param(query, "type"), cursor: param(query, "cursor") };
  const [found, page] = await Promise.all([
    attempt(getSettlement(id, transport), path, "404"),
    lines ? attempt(listSettlementLines(id, filters, transport), path) : null,
  ]);
  const back = { href: "/finance/settlements/", label: words.title };
  if (found instanceof ApiError) {
    return (
      <RecordPage title={words.name(String(id))} back={back}>
        <Problem error={found} />
      </RecordPage>
    );
  }
  const counts = found.counts as Record<string, number>;
  return (
    <RecordPage
      eyebrow={formatDate(found.date)}
      title={<span className="font-mono">{found.settlement_id}</span>}
      lead={words.recordLead(inr(found.net), found.utr)}
      back={back}
      status={<SettlementState settlement={found} />}
      side={recordSide({
        manifest,
        transport,
        path,
        audit: { target_type: "shop.settlement", target_id: String(found.id) },
        note: { type: "shop.settlement", id: String(found.id) },
      })}
    >
      {found.state === "mismatched" && found.problem ? (
        <Alert variant="warning" title={words.problemTitle}>
          <p>{found.problem}</p>
        </Alert>
      ) : null}
      <Facts
        items={[
          { label: words.columns.gross, value: inr(found.gross) },
          { label: words.columns.fees, value: inr(found.fees) },
          { label: words.columns.tax, value: inr(found.tax) },
          { label: words.columns.adjustments, value: inr(found.adjustments) },
          { label: words.columns.net, value: <strong>{inr(found.net)}</strong> },
          { label: words.columns.utr, value: <span className="font-mono">{found.utr || copy.common.none}</span> },
          { label: words.counted, value: words.countsText(counts.lines ?? 0, counts.unmatched ?? 0) },
          { label: words.matchedAt, value: formatDateTime(found.matched_at) },
          { label: words.columns.posted, value: formatDateTime(found.posted_at) },
          {
            label: words.erp,
            value: found.erp ? (
              <span className="flex flex-col">
                <span>
                  {labelOf(words.erpStates, found.erp.state)}
                  {found.erp.name ? <span className="font-mono"> · {found.erp.name}</span> : null}
                </span>
                {found.erp.last_error ? (
                  <span className="text-sm text-muted-foreground">{found.erp.last_error}</span>
                ) : null}
              </span>
            ) : found.is_test ? (
              words.erpTest
            ) : (
              words.erpNone
            ),
          },
        ]}
      />
      {page ? (
        <Section id="lines" title={words.lines} lead={words.linesLead}>
          {page instanceof ApiError ? (
            <Problem error={page} />
          ) : (
            <LinesTable settlement={found} rows={page.results} next={page.next} previous={page.previous} />
          )}
        </Section>
      ) : null}
    </RecordPage>
  );
}
