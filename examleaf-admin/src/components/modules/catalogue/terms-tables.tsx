"use client";

// The coupons (GET catalogue/coupons/?q=&state=&kind=&single_use=) and the automatic offers (GET
// catalogue/offers/?q=&state=&scope=&combinable=): each with its discount, its state now and its uses (orders placed,
// test orders left out); each row opening its page.
import { type Column, DataTable } from "@/components/data/data-table";
import { StatusChip } from "@/components/data/status-chip";
import type { CatalogueCoupon, CatalogueOffer, SavedView } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDateTime, formatNumber } from "@/lib/format";

import { discountText, TERM_TONES } from "./shared";

const options = (table: Record<string, string>) => Object.entries(table).map(([value, label]) => ({ value, label }));

function State({ state }: { state: string }) {
  return <StatusChip tone={TERM_TONES[state] ?? "stopped"}>{labelOf(copy.catalogue.termStates, state)}</StatusChip>;
}

const until = (row: { valid_until: string | null }) =>
  row.valid_until ? formatDateTime(row.valid_until) : copy.catalogue.noEnd;

type ListProps<T> = { rows: T[]; next: string | null; previous: string | null; views: SavedView[] | null };

export function CouponsTable({ rows, next, previous, views }: ListProps<CatalogueCoupon>) {
  const columns: Column<CatalogueCoupon>[] = [
    {
      key: "code",
      label: copy.catalogue.columns.code,
      render: (row) => <span className="font-mono font-semibold">{row.code}</span>,
    },
    { key: "discount", label: copy.catalogue.columns.discount, render: (row) => discountText(row.kind, row.value) },
    { key: "state", label: copy.catalogue.columns.state, render: (row) => <State state={row.state} /> },
    { key: "uses", label: copy.catalogue.columns.uses, render: (row) => formatNumber(row.uses), numeric: true },
    { key: "until", label: copy.catalogue.columns.until, render: until },
    {
      key: "codes",
      label: copy.catalogue.columns.codes,
      render: (row) =>
        row.single_use ? copy.catalogue.codesCount(row.codes.made, row.codes.used) : copy.catalogue.oneCode,
    },
    {
      key: "description",
      label: copy.catalogue.columns.description,
      render: (row) => row.description || "—",
      hidden: true,
      wrap: true,
    },
  ];
  return (
    <DataTable
      listKey="catalogue-coupons"
      caption={copy.catalogue.couponsTitle}
      rows={rows}
      columns={columns}
      rowId={(row) => row.code}
      rowHref={(row) => `/catalogue/coupons/${encodeURIComponent(row.code)}/`}
      next={next}
      previous={previous}
      views={views}
      filters={[
        { name: "q", label: copy.catalogue.searchCode, type: "search" },
        {
          name: "state",
          label: copy.catalogue.columns.state,
          type: "select",
          options: options(copy.catalogue.termStates),
        },
        {
          name: "kind",
          label: copy.catalogue.fields.kind_discount,
          type: "select",
          options: options(copy.catalogue.discountKinds),
        },
        {
          name: "single_use",
          label: copy.catalogue.columns.codes,
          type: "select",
          options: [
            { value: "true", label: copy.catalogue.singleUseOnly },
            { value: "false", label: copy.catalogue.oneCode },
          ],
        },
      ]}
      empty={{ title: copy.catalogue.couponsEmptyTitle, text: copy.catalogue.couponsEmptyText }}
    />
  );
}

export function OffersTable({ rows, next, previous, views }: ListProps<CatalogueOffer>) {
  const columns: Column<CatalogueOffer>[] = [
    {
      key: "name",
      label: copy.catalogue.columns.offer,
      render: (row) => <span className="font-semibold">{row.name}</span>,
    },
    { key: "discount", label: copy.catalogue.columns.discount, render: (row) => discountText(row.kind, row.value) },
    { key: "scope", label: copy.catalogue.columns.scope, render: (row) => labelOf(copy.catalogue.scopes, row.scope) },
    { key: "state", label: copy.catalogue.columns.state, render: (row) => <State state={row.state} /> },
    { key: "uses", label: copy.catalogue.columns.uses, render: (row) => formatNumber(row.uses), numeric: true },
    { key: "until", label: copy.catalogue.columns.until, render: until },
    {
      key: "together",
      label: copy.catalogue.columns.together,
      render: (row) => (row.combinable ? copy.catalogue.combines : copy.catalogue.alone),
      hidden: true,
    },
  ];
  return (
    <DataTable
      listKey="catalogue-offers"
      caption={copy.catalogue.offersTitle}
      rows={rows}
      columns={columns}
      rowId={(row) => String(row.id)}
      rowHref={(row) => `/catalogue/offers/${row.id}/`}
      next={next}
      previous={previous}
      views={views}
      filters={[
        { name: "q", label: copy.catalogue.searchName, type: "search" },
        {
          name: "state",
          label: copy.catalogue.columns.state,
          type: "select",
          options: options(copy.catalogue.termStates),
        },
        { name: "scope", label: copy.catalogue.columns.scope, type: "select", options: options(copy.catalogue.scopes) },
        {
          name: "combinable",
          label: copy.catalogue.columns.together,
          type: "select",
          options: [
            { value: "true", label: copy.catalogue.combines },
            { value: "false", label: copy.catalogue.alone },
          ],
        },
      ]}
      empty={{ title: copy.catalogue.offersEmptyTitle, text: copy.catalogue.offersEmptyText }}
    />
  );
}
