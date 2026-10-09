"use client";

// Customers as a list (GET users/?q=&kind=&status=): masked contact details only (a reveal happens on the record, with
// a reason), the kind of account, its state and its flags (a child, consent awaited, locked, suspended).
import { type Column, DataTable } from "@/components/data/data-table";
import { StatusChip, toneOf } from "@/components/data/status-chip";
import { useCan } from "@/components/shell/manifest";
import type { Customer, CustomerFlags, SavedView } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDate } from "@/lib/format";
import { P } from "@/lib/modules";

export function CustomerFlagChips({ flags }: { flags: CustomerFlags }) {
  const set = (Object.keys(flags) as (keyof CustomerFlags)[]).filter((flag) => flags[flag]);
  if (!set.length) return null;
  return (
    <span className="inline-flex flex-wrap gap-1.5">
      {set.map((flag) => (
        <StatusChip key={flag} tone={flag === "child" ? "moving" : flag === "consent_pending" ? "waiting" : "bad"}>
          {copy.users.flags[flag]}
        </StatusChip>
      ))}
    </span>
  );
}

export function UsersTable({
  rows,
  next,
  previous,
  views,
}: {
  rows: Customer[];
  next: string | null;
  previous: string | null;
  views: SavedView[] | null;
}) {
  const can = useCan();
  const columns: Column<Customer>[] = [
    { key: "name", label: copy.users.columns.name, render: (user) => user.name || user.masked_email || user.id },
    {
      key: "email",
      label: copy.users.columns.email,
      render: (user) => <span className="font-mono text-[14px]">{user.masked_email ?? copy.common.none}</span>,
    },
    {
      key: "phone",
      label: copy.users.columns.phone,
      render: (user) => <span className="font-mono text-[14px]">{user.masked_phone ?? copy.common.none}</span>,
    },
    { key: "kind", label: copy.users.columns.kind, render: (user) => labelOf(copy.users.kinds, user.kind) },
    {
      key: "status",
      label: copy.users.columns.status,
      render: (user) => (
        <span className="inline-flex flex-wrap items-center gap-1.5">
          <StatusChip tone={toneOf(user.status)}>{labelOf(copy.users.statuses, user.status)}</StatusChip>
          <CustomerFlagChips
            flags={{ ...user.flags, suspended: user.flags.suspended && user.status !== "suspended" }}
          />
        </span>
      ),
    },
    { key: "joined", label: copy.users.columns.joined, render: (user) => (user.joined ? formatDate(user.joined) : "") },
    {
      key: "lastSeen",
      label: copy.users.columns.lastSeen,
      render: (user) => (user.last_seen ? formatDate(user.last_seen) : copy.common.never),
      hidden: true,
    },
  ];
  return (
    <DataTable
      listKey="users"
      caption={copy.users.title}
      rows={rows}
      columns={columns}
      rowId={(user) => user.id}
      rowLabel={(user) => user.name || user.masked_email || user.id}
      rowHref={(user) => `/users/${user.id}/`}
      next={next}
      previous={previous}
      views={views}
      filters={[
        { name: "q", label: copy.filters.searchList(copy.users.title.toLowerCase()), type: "search" },
        {
          name: "kind",
          label: copy.users.columns.kind,
          type: "select",
          options: Object.entries(copy.users.kinds).map(([value, label]) => ({ value, label })),
        },
        {
          name: "status",
          label: copy.users.columns.status,
          type: "select",
          options: Object.entries(copy.users.statuses).map(([value, label]) => ({ value, label })),
        },
      ]}
      exportAction={can(P.usersExport) ? "users.export" : undefined}
      empty={{ title: copy.users.emptyTitle, text: copy.users.emptyText }}
    />
  );
}
