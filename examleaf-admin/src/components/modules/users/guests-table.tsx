"use client";

// The guest buyers' tab (GET users/?kind=guests): people who bought without an account, one row for each email address
// on the orders, masked as everywhere, with how many orders carry it and the newest order, which the row opens (the
// Orders module's page). A row is an address, not an account: no class, no consent, no actions. The search takes an
// email address (exactly), a mobile number or three letters of a name, and the API records it as a lookup.
import { type Column, DataTable } from "@/components/data/data-table";
import { useCan } from "@/components/shell/manifest";
import type { CustomerGuest } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { formatDate } from "@/lib/format";
import { P } from "@/lib/modules";

import { kindPresets } from "./users-table";

export function GuestsTable({
  rows,
  next,
  previous,
}: {
  rows: CustomerGuest[];
  next: string | null;
  previous: string | null;
}) {
  const can = useCan();
  const words = copy.customers.guests;
  const orders = can(P.ordersView);
  const columns: Column<CustomerGuest>[] = [
    { key: "name", label: words.columns.name, render: (guest) => guest.name || guest.email },
    {
      key: "email",
      label: words.columns.email,
      render: (guest) => <span className="font-mono text-[14px]">{guest.email || copy.common.none}</span>,
    },
    {
      key: "phone",
      label: words.columns.phone,
      render: (guest) => <span className="font-mono text-[14px]">{guest.phone || copy.common.none}</span>,
    },
    { key: "orders", label: words.columns.orders, numeric: true, render: (guest) => guest.orders },
    {
      key: "last",
      label: words.columns.last,
      render: (guest) => <span className="font-mono">{guest.last_order}</span>,
    },
    {
      key: "at",
      label: words.columns.at,
      render: (guest) => (guest.last_order_at ? formatDate(guest.last_order_at) : copy.common.none),
    },
  ];
  return (
    <DataTable
      listKey="users-guests"
      caption={words.title}
      rows={rows}
      columns={columns}
      rowId={(guest) => String(guest.id)}
      rowHref={(guest) => (orders && guest.last_order ? `/orders/${encodeURIComponent(guest.last_order)}/` : null)}
      next={next}
      previous={previous}
      presets={kindPresets(true)}
      filters={[{ name: "q", label: copy.filters.searchList(words.title.toLowerCase()), type: "search" }]}
      empty={{ title: words.emptyTitle, text: words.emptyText }}
    />
  );
}
