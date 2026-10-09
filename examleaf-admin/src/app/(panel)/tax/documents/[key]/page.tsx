// /tax/documents/<key>/: one invoice or credit note by its number, dashes for its slashes (GET tax/documents/{number}/):
// its facts, what Rule 46 asks that it misses, its lines and shipping, its credit notes, the PDF (a look at the
// buyer's details: the server records it), and cancelling it (POST tax/documents/{number}/cancel/: typed and
// re-authenticated) in the Danger section; its notes and audit events beside.
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Problem } from "@/components/data/problem";
import { Facts, RecordPage } from "@/components/data/record-page";
import { recordSide } from "@/components/data/record-side";
import { CancelDocument } from "@/components/modules/tax/documents";
import { DocumentLines, DocumentState, documentType } from "@/components/modules/tax/records";
import { Section } from "@/components/shell/page-header";
import { Alert } from "@/components/ui/alert";
import { ApiError } from "@/lib/api/errors";
import { attempt, staffPage } from "@/lib/api/page";
import { getTaxDocument, taxDocumentPdfHref } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { formatDate, formatDateTime, formatInr } from "@/lib/format";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.tax.documentsTitle };

const keyOf = (number: string) => number.replaceAll("/", "-");
const inr = (value: string | null) => (value === null ? copy.common.unknown : formatInr(Number(value)));

export default async function DocumentPage({ params }: { params: Promise<{ key: string }> }) {
  const { key } = await params;
  if (!/^[A-Za-z0-9-]{1,40}$/.test(key)) notFound();
  const { manifest, transport, path } = await staffPage(`/tax/documents/${key}/`);
  const document = await attempt(getTaxDocument(key, transport), path, "404");
  const back = { href: "/tax/documents/", label: copy.tax.documentsTitle };
  if (document instanceof ApiError) {
    return (
      <RecordPage title={key} back={back}>
        <Problem error={document} />
      </RecordPage>
    );
  }
  const target = {
    type: document.kind === "credit_note" ? "shop.creditnote" : "shop.invoice",
    id: String(document.id),
  };
  const roundOff = Number(document.round_off);
  return (
    <RecordPage
      eyebrow={documentType(document)}
      title={<span className="font-mono">{document.number}</span>}
      lead={document.title}
      back={back}
      status={<DocumentState document={document} />}
      actions={
        document.has_pdf ? (
          <a href={taxDocumentPdfHref(document.key)} className="inline-flex min-h-11 items-center font-semibold">
            {copy.tax.pdf}
          </a>
        ) : null
      }
      side={recordSide({
        manifest,
        transport,
        path,
        audit: { target_type: target.type, target_id: target.id },
        note: target,
      })}
      danger={has(manifest, P.taxCancel) && !document.cancelled_at ? <CancelDocument document={document} /> : null}
    >
      <p className="m-0 text-sm text-muted-foreground">{document.has_pdf ? copy.tax.pdfNote : copy.tax.noPdf}</p>
      {document.checks.length ? (
        <Alert variant="warning" title={copy.tax.checks}>
          <ul className="m-0 pl-5">
            {document.checks.map((check) => (
              <li key={check}>{check}</li>
            ))}
          </ul>
        </Alert>
      ) : null}
      <Facts
        items={[
          { label: copy.tax.date, value: formatDate(document.date) },
          { label: copy.tax.order, value: <span className="font-mono">{document.order}</span> },
          ...(document.against
            ? [
                {
                  label: copy.tax.against,
                  value: (
                    <Link href={`/tax/documents/${keyOf(document.against)}/`} className="font-mono">
                      {document.against}
                    </Link>
                  ),
                },
              ]
            : []),
          { label: copy.tax.place, value: document.place_label },
          { label: copy.tax.total, value: inr(document.total) },
          { label: copy.tax.taxable, value: inr(document.taxable_value) },
          { label: copy.tax.exempt, value: inr(document.exempt_value) },
          { label: copy.tax.gst, value: inr(document.tax_amount) },
          ...(roundOff ? [{ label: copy.tax.roundOff, value: formatInr(roundOff) }] : []),
          ...(document.cancelled_at
            ? [
                { label: copy.tax.cancelledAt, value: formatDateTime(document.cancelled_at) },
                { label: copy.tax.cancelReason, value: document.cancel_reason || copy.common.none },
              ]
            : []),
        ]}
      />
      <Section id="lines" title={copy.tax.lines} lead={document.charges.length ? copy.tax.chargesLead : undefined}>
        <DocumentLines document={document} />
      </Section>
      {document.kind === "invoice" ? (
        <Section id="credit-notes" title={copy.tax.creditNotes}>
          {document.credit_notes.length ? (
            <ul className="m-0 flex list-none flex-wrap gap-x-6 gap-y-2 p-0">
              {document.credit_notes.map((number) => (
                <li key={number}>
                  <Link href={`/tax/documents/${keyOf(number)}/`} className="font-mono">
                    {number}
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="m-0 text-[15px] text-muted-foreground">{copy.tax.noCreditNotes}</p>
          )}
        </Section>
      ) : null}
    </RecordPage>
  );
}
