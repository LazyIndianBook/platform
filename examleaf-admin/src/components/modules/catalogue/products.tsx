"use client";

// The product list with its chips (GET catalogue/products/: the GST that disagrees with the master, what the courier
// lacks, off sale), the stock list (GET catalogue/stock/: the copies, what orders hold, the back-in-stock requests) and
// the back-in-stock requests by product (GET catalogue/stock-alerts/, never who asked): the filters in the address,
// saved views as tabs, each row opening the product.
import { type Column, DataTable } from "@/components/data/data-table";
import { StatusChip } from "@/components/data/status-chip";
import type { CatalogueAlertRow, CatalogueProductRow, CatalogueStockRow, SavedView } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDateTime, formatNumber } from "@/lib/format";

import { rupees, STOCK_TONES } from "./shared";

const ONLY = [{ value: "true", label: copy.catalogue.onlyThose }];
const options = (table: Record<string, string>) => Object.entries(table).map(([value, label]) => ({ value, label }));

/** What a product needs, as chips: its GST against the master, the courier's data, off sale. */
export function ProductChips({
  row,
}: {
  row: Pick<CatalogueProductRow, "tax_problem" | "courier_problem" | "is_active">;
}) {
  if (!row.tax_problem && !row.courier_problem && row.is_active) return <>{copy.catalogue.nothingNeeded}</>;
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      {row.tax_problem ? <StatusChip tone="bad">{copy.catalogue.chips.tax}</StatusChip> : null}
      {row.courier_problem ? <StatusChip tone="waiting">{copy.catalogue.chips.courier}</StatusChip> : null}
      {!row.is_active ? <StatusChip tone="stopped">{copy.catalogue.offSale}</StatusChip> : null}
    </span>
  );
}

function Name({ title, slug }: { title: string; slug: string }) {
  return (
    <span className="flex flex-col">
      <span className="font-semibold">{title}</span>
      <span className="font-mono text-[13px] text-muted-foreground">{slug}</span>
    </span>
  );
}

export function ProductsTable({
  rows,
  next,
  previous,
  views,
}: {
  rows: CatalogueProductRow[];
  next: string | null;
  previous: string | null;
  views: SavedView[] | null;
}) {
  const columns: Column<CatalogueProductRow>[] = [
    {
      key: "product",
      label: copy.catalogue.columns.product,
      render: (row) => <Name title={row.title} slug={row.slug} />,
    },
    { key: "kind", label: copy.catalogue.columns.kind, render: (row) => labelOf(copy.catalogue.kinds, row.kind) },
    {
      key: "price",
      label: copy.catalogue.columns.price,
      numeric: true,
      render: (row) => (
        <span className="flex flex-col items-end">
          <span className="font-semibold">{rupees(row.price)}</span>
          {row.price !== row.mrp ? (
            <span className="text-[13px] text-muted-foreground">{copy.catalogue.mrpOf(rupees(row.mrp))}</span>
          ) : null}
        </span>
      ),
    },
    {
      key: "stock",
      label: copy.catalogue.columns.stock,
      render: (row) => (
        <span className="inline-flex flex-wrap items-center gap-1.5">
          <StatusChip tone={STOCK_TONES[row.stock_state] ?? "stopped"}>
            {labelOf(copy.catalogue.stockStates, row.stock_state)}
          </StatusChip>
          {row.stock_state !== "none" ? <span className="font-mono">{formatNumber(row.available)}</span> : null}
        </span>
      ),
    },
    { key: "needs", label: copy.catalogue.columns.needs, render: (row) => <ProductChips row={row} />, wrap: true },
    {
      key: "categories",
      label: copy.catalogue.columns.categories,
      render: (row) => row.categories.join(", ") || copy.common.none,
      hidden: true,
      wrap: true,
    },
    {
      key: "modified",
      label: copy.catalogue.columns.modified,
      render: (row) => formatDateTime(row.modified),
      hidden: true,
    },
  ];
  return (
    <DataTable
      listKey="catalogue-products"
      caption={copy.catalogue.productsTitle}
      rows={rows}
      columns={columns}
      rowId={(row) => row.slug}
      rowHref={(row) => `/catalogue/products/${encodeURIComponent(row.slug)}/`}
      next={next}
      previous={previous}
      views={views}
      filters={[
        { name: "q", label: copy.catalogue.search, type: "search" },
        { name: "kind", label: copy.catalogue.columns.kind, type: "select", options: options(copy.catalogue.kinds) },
        {
          name: "published",
          label: copy.catalogue.filters.published,
          type: "select",
          options: [
            { value: "true", label: copy.catalogue.onSale },
            { value: "false", label: copy.catalogue.offSale },
          ],
        },
        {
          name: "stock",
          label: copy.catalogue.columns.stock,
          type: "select",
          options: options(copy.catalogue.bookStates),
        },
        { name: "tax_problem", label: copy.catalogue.filters.taxProblem, type: "select", options: ONLY },
        { name: "incomplete", label: copy.catalogue.filters.incomplete, type: "select", options: ONLY },
      ]}
      empty={{ title: copy.catalogue.productsEmptyTitle, text: copy.catalogue.productsEmptyText }}
    />
  );
}

export function StockTable({
  rows,
  next,
  previous,
  views,
}: {
  rows: CatalogueStockRow[];
  next: string | null;
  previous: string | null;
  views: SavedView[] | null;
}) {
  const columns: Column<CatalogueStockRow>[] = [
    {
      key: "product",
      label: copy.catalogue.columns.product,
      render: (row) => <Name title={row.title} slug={row.slug} />,
    },
    {
      key: "state",
      label: copy.catalogue.columns.state,
      render: (row) => (
        <StatusChip tone={STOCK_TONES[row.state] ?? "stopped"}>
          {labelOf(copy.catalogue.stockStates, row.state)}
        </StatusChip>
      ),
    },
    { key: "stock", label: copy.catalogue.columns.copies, render: (row) => formatNumber(row.stock), numeric: true },
    {
      key: "reserved",
      label: copy.catalogue.columns.reserved,
      render: (row) => formatNumber(row.reserved),
      numeric: true,
    },
    {
      key: "awaiting",
      label: copy.catalogue.columns.awaiting,
      render: (row) => formatNumber(row.awaiting_payment),
      numeric: true,
    },
    { key: "alerts", label: copy.catalogue.columns.alerts, render: (row) => formatNumber(row.alerts), numeric: true },
  ];
  return (
    <DataTable
      listKey="catalogue-stock"
      caption={copy.catalogue.stockTitle}
      rows={rows}
      columns={columns}
      rowId={(row) => row.slug}
      rowHref={(row) => `/catalogue/products/${encodeURIComponent(row.slug)}/#stock`}
      next={next}
      previous={previous}
      views={views}
      filters={[
        { name: "q", label: copy.catalogue.search, type: "search" },
        {
          name: "state",
          label: copy.catalogue.columns.state,
          type: "select",
          options: options(copy.catalogue.bookStates),
        },
        {
          name: "published",
          label: copy.catalogue.filters.published,
          type: "select",
          options: [
            { value: "true", label: copy.catalogue.onSale },
            { value: "false", label: copy.catalogue.offSale },
          ],
        },
      ]}
      empty={{ title: copy.catalogue.stockEmptyTitle, text: copy.catalogue.stockEmptyText }}
    />
  );
}

export function AlertsTable({ rows }: { rows: CatalogueAlertRow[] }) {
  const columns: Column<CatalogueAlertRow>[] = [
    {
      key: "product",
      label: copy.catalogue.columns.product,
      render: (row) => <Name title={row.title} slug={row.product} />,
    },
    {
      key: "requests",
      label: copy.catalogue.columns.requests,
      render: (row) => formatNumber(row.requests),
      numeric: true,
    },
    { key: "last", label: copy.catalogue.columns.lastAsked, render: (row) => formatDateTime(row.last_asked) },
    {
      key: "available",
      label: copy.catalogue.columns.copies,
      render: (row) => formatNumber(row.available),
      numeric: true,
    },
  ];
  return (
    <DataTable
      listKey="catalogue-alerts"
      caption={copy.catalogue.alertsTitle}
      rows={rows}
      columns={columns}
      rowId={(row) => row.product}
      rowHref={(row) => `/catalogue/products/${encodeURIComponent(row.product)}/#stock`}
      next={null}
      previous={null}
      empty={{ title: copy.catalogue.alertsEmptyTitle, text: copy.catalogue.alertsEmptyText }}
    />
  );
}
