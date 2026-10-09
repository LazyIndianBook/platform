"use client";

// The storefront's tax documents (GET tax/documents/?kind=&series=&document_type=&month=&cancelled=&test=&search=):
// invoices or credit notes, newest first, by series and month, the cancelled ones marked. On a document, cancelling it
// (POST tax/documents/{number}/cancel/: a reason, a re-authentication, and its number typed first): it keeps its
// number, and its order and refunds are left as they are.
import { ConfirmTyped } from "@/components/data/confirm-typed";
import { type Column, DataTable } from "@/components/data/data-table";
import { DangerRow } from "@/components/data/record-page";
import { cancelTaxDocument, type SavedView, type TaxDocument } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { formatDate, formatInr } from "@/lib/format";

import { monthLabel } from "./periods";
import { documentType, DocumentState } from "./records";

const money = (value: string | null) => (value === null ? copy.common.unknown : formatInr(Number(value)));

export function DocumentsTable({
  rows,
  next,
  previous,
  views,
  months,
}: {
  rows: TaxDocument[];
  next: string | null;
  previous: string | null;
  views: SavedView[] | null;
  /** The months to choose from, newest first ("2026-10"). */
  months: string[];
}) {
  const columns: Column<TaxDocument>[] = [
    {
      key: "number",
      label: copy.tax.documentColumns.number,
      render: (row) => <span className="font-mono">{row.number}</span>,
    },
    { key: "type", label: copy.tax.documentColumns.type, render: documentType },
    { key: "date", label: copy.tax.documentColumns.date, render: (row) => formatDate(row.date) },
    {
      key: "order",
      label: copy.tax.documentColumns.order,
      render: (row) => (
        <span className="font-mono text-[14px]">
          {row.order}
          {row.against ? ` · ${copy.tax.against.toLowerCase()} ${row.against}` : ""}
        </span>
      ),
    },
    { key: "place", label: copy.tax.documentColumns.place, render: (row) => row.place_label, hidden: true },
    { key: "total", label: copy.tax.documentColumns.total, render: (row) => money(row.total), numeric: true },
    {
      key: "taxable",
      label: copy.tax.documentColumns.taxable,
      render: (row) => money(row.taxable_value),
      numeric: true,
      hidden: true,
    },
    { key: "gst", label: copy.tax.documentColumns.gst, render: (row) => money(row.tax_amount), numeric: true },
    { key: "state", label: copy.tax.documentColumns.state, render: (row) => <DocumentState document={row} /> },
  ];
  return (
    <DataTable
      listKey="tax-documents"
      caption={copy.tax.documentsTitle}
      rows={rows}
      columns={columns}
      rowId={(row) => `${row.kind}-${row.id}`}
      rowHref={(row) => `/tax/documents/${encodeURIComponent(row.key)}/`}
      next={next}
      previous={previous}
      views={views}
      filters={[
        { name: "search", label: copy.tax.searchDocuments, type: "search" },
        {
          name: "kind",
          label: copy.tax.documentKind,
          type: "select",
          any: copy.tax.documentKinds.invoice,
          options: [{ value: "credit_note", label: copy.tax.documentKinds.credit_note }],
        },
        {
          name: "month",
          label: copy.tax.month,
          type: "select",
          options: months.map((month) => ({ value: month, label: monthLabel(month) })),
        },
        {
          name: "document_type",
          label: copy.tax.documentColumns.type,
          type: "select",
          options: Object.entries(copy.tax.types).map(([value, label]) => ({ value, label })),
        },
        { name: "series", label: copy.tax.seriesFilter, type: "text" },
        {
          name: "cancelled",
          label: copy.tax.cancelledFilter,
          type: "select",
          options: Object.entries(copy.tax.cancelledOptions).map(([value, label]) => ({ value, label })),
        },
        {
          name: "test",
          label: copy.tax.testFilter,
          type: "select",
          any: copy.tax.testOptions.false,
          options: [{ value: "true", label: copy.tax.testOptions.true }],
        },
      ]}
      empty={{ title: copy.tax.documentsEmptyTitle, text: copy.tax.documentsEmptyText }}
    />
  );
}

/** The Danger section's row: cancel the document, typing its number first, with a reason. */
export function CancelDocument({ document }: { document: Pick<TaxDocument, "key" | "number"> }) {
  return (
    <DangerRow title={copy.tax.cancelRow} text={copy.tax.cancelRowText}>
      <ConfirmTyped
        label={document.number}
        triggerLabel={copy.tax.cancel}
        triggerVariant="destructive"
        title={copy.tax.cancelTitle}
        text={copy.tax.cancelText}
        confirmLabel={copy.tax.cancelButton}
        reason
        reasonHelp={copy.tax.reasonHelp}
        success={copy.tax.cancelledToast}
        onConfirm={({ reason }) => cancelTaxDocument(document.key, reason)}
      />
    </DangerRow>
  );
}
