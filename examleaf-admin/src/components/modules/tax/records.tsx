// The tax records' read-only parts, as the API gives them (no figure is worked out here; server pages and the client
// lists both use them): the products that disagree with the master (GET tax/problems/), a code's rate history and its
// products (GET tax/hsn/{code}/), a document's type, state, lines and shipping (GET tax/documents/{number}/).
import Link from "next/link";

import { StatusChip } from "@/components/data/status-chip";
import { Table, TableCell, TableHead } from "@/components/ui/table";
import type { HsnCodeDetail, TaxDocument, TaxDocumentDetail, TaxProblem } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDate, formatInr } from "@/lib/format";

const inr = (value: string) => formatInr(Number(value));

/** A rate as the master gives it: "18 % (Taxable) from 22 Sep 2025". */
export const rateText = (rate: { rate: string; taxability: string; effective_from: string }) =>
  copy.tax.rateOn(rate.rate, labelOf(copy.tax.taxability, rate.taxability), formatDate(rate.effective_from));

/** What a document is: its type, or a credit note. */
export const documentType = (document: Pick<TaxDocument, "kind" | "document_type">) =>
  document.kind === "credit_note" ? copy.tax.creditNote : labelOf(copy.tax.types, document.document_type);

export function DocumentState({ document }: { document: Pick<TaxDocument, "cancelled_at" | "test"> }) {
  return (
    <span className="inline-flex flex-wrap gap-1.5">
      {document.cancelled_at ? (
        <StatusChip tone="bad">{copy.tax.cancelled}</StatusChip>
      ) : (
        <StatusChip tone="done">{copy.tax.issued}</StatusChip>
      )}
      {document.test ? <StatusChip tone="stopped">{copy.tax.test}</StatusChip> : null}
    </span>
  );
}

export function TaxProblems({ problems }: { problems: TaxProblem[] }) {
  if (!problems.length) return <p className="m-0 text-[15px] text-muted-foreground">{copy.tax.problemsNone}</p>;
  return (
    <Table caption={copy.table.region(copy.tax.problems)}>
      <thead>
        <tr>
          <TableHead>{copy.tax.problemColumns.product}</TableHead>
          <TableHead>{copy.tax.problemColumns.code}</TableHead>
          <TableHead numeric>{copy.tax.problemColumns.rate}</TableHead>
          <TableHead>{copy.tax.problemColumns.problem}</TableHead>
        </tr>
      </thead>
      <tbody>
        {problems.map((product) => (
          <tr key={product.id}>
            <TableCell>{product.title}</TableCell>
            <TableCell className="font-mono">
              {product.hsn_code ? (
                <Link href={`/tax/hsn/${encodeURIComponent(product.hsn_code)}/`}>{product.hsn_code}</Link>
              ) : (
                copy.common.none
              )}
            </TableCell>
            <TableCell numeric>{copy.tax.rate(product.gst_rate)}</TableCell>
            <TableCell className="whitespace-normal">{product.problem}</TableCell>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}

export function RatesTable({ rates }: { rates: HsnCodeDetail["rates"] }) {
  return (
    <Table caption={copy.table.region(copy.tax.rates)}>
      <thead>
        <tr>
          <TableHead>{copy.tax.rateColumns.from}</TableHead>
          <TableHead>{copy.tax.rateColumns.until}</TableHead>
          <TableHead numeric>{copy.tax.rateColumns.rate}</TableHead>
          <TableHead>{copy.tax.rateColumns.taxability}</TableHead>
          <TableHead>{copy.tax.rateColumns.notification}</TableHead>
          <TableHead>{copy.tax.rateColumns.serial}</TableHead>
          <TableHead>{copy.tax.rateColumns.note}</TableHead>
        </tr>
      </thead>
      <tbody>
        {rates.map((rate) => (
          <tr key={rate.id}>
            <TableCell>{formatDate(rate.effective_from)}</TableCell>
            <TableCell>{rate.until ? formatDate(rate.until) : copy.tax.openEnded}</TableCell>
            <TableCell numeric>{copy.tax.rate(rate.rate)}</TableCell>
            <TableCell>{labelOf(copy.tax.taxability, rate.taxability)}</TableCell>
            <TableCell>{rate.notification}</TableCell>
            <TableCell>{rate.serial || copy.common.none}</TableCell>
            <TableCell className="whitespace-normal">{rate.note || copy.common.none}</TableCell>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}

export function LinkedProducts({ products }: { products: HsnCodeDetail["linked"] }) {
  if (!products.length) return <p className="m-0 text-[15px] text-muted-foreground">{copy.tax.productsOnEmpty}</p>;
  return (
    <Table caption={copy.table.region(copy.tax.productsOn)}>
      <thead>
        <tr>
          <TableHead>{copy.tax.problemColumns.product}</TableHead>
          <TableHead numeric>{copy.tax.problemColumns.rate}</TableHead>
          <TableHead>{copy.tax.problemColumns.problem}</TableHead>
        </tr>
      </thead>
      <tbody>
        {products.map((product) => (
          <tr key={product.id}>
            <TableCell>{product.title}</TableCell>
            <TableCell numeric>{copy.tax.rate(product.gst_rate)}</TableCell>
            <TableCell className="whitespace-normal">
              {product.problem ? (
                <span className="inline-flex flex-wrap items-center gap-2">
                  <StatusChip tone="bad">{copy.tax.disagrees}</StatusChip>
                  {product.problem}
                </span>
              ) : (
                <StatusChip tone="done">{copy.tax.agrees}</StatusChip>
              )}
            </TableCell>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}

export function DocumentLines({ document }: { document: TaxDocumentDetail }) {
  return (
    <Table caption={copy.table.region(copy.tax.lines)}>
      <thead>
        <tr>
          <TableHead>{copy.tax.lineColumns.item}</TableHead>
          <TableHead>{copy.tax.lineColumns.code}</TableHead>
          <TableHead numeric>{copy.tax.lineColumns.quantity}</TableHead>
          <TableHead numeric>{copy.tax.lineColumns.rate}</TableHead>
          <TableHead numeric>{copy.tax.lineColumns.amount}</TableHead>
          <TableHead numeric>{copy.tax.lineColumns.taxable}</TableHead>
          <TableHead numeric>{copy.tax.lineColumns.gst}</TableHead>
        </tr>
      </thead>
      <tbody>
        {document.lines.map((line, index) => (
          <tr key={index}>
            <TableCell className="whitespace-normal">
              {line.title}
              {line.bundle ? <span className="text-muted-foreground"> ({copy.tax.partOf(line.bundle)})</span> : null}
            </TableCell>
            <TableCell className="font-mono">{line.hsn_code || copy.common.none}</TableCell>
            <TableCell numeric>{line.quantity}</TableCell>
            <TableCell numeric>{copy.tax.rate(line.rate)}</TableCell>
            <TableCell numeric>{inr(line.amount)}</TableCell>
            <TableCell numeric>{inr(line.taxable)}</TableCell>
            <TableCell numeric>{inr(line.tax)}</TableCell>
          </tr>
        ))}
        {document.charges.map((charge, index) => (
          <tr key={`charge-${index}`}>
            <TableCell className="whitespace-normal">{copy.tax.chargeLine(charge.label, charge.rate)}</TableCell>
            <TableCell>{copy.common.none}</TableCell>
            <TableCell numeric />
            <TableCell numeric>{copy.tax.rate(charge.rate)}</TableCell>
            <TableCell numeric>{inr(charge.amount)}</TableCell>
            <TableCell numeric>{inr(charge.taxable)}</TableCell>
            <TableCell numeric>{inr(charge.tax)}</TableCell>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}
