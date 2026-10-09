"use client";

// Customers as a list (GET users/?q=&class_level=&is_active=): masked contact details only (a reveal happens on the
// record, with a reason), the class and board, the account's state and its flags (under 18, a parent's confirmation
// awaited). The search finds an email address exactly, a mobile number, or three letters or more of a name.
import { type Column, DataTable } from "@/components/data/data-table";
import { StatusChip, toneOf } from "@/components/data/status-chip";
import type { Customer, CustomerDetail, SavedView } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { classOf } from "@/lib/display";
import { formatDate } from "@/lib/format";

/** The flags of an account, as chips: a child's, a consent awaited, a lock-out (the detail only). */
export function CustomerFlagChips({ user }: { user: Customer & Partial<Pick<CustomerDetail, "locked">> }) {
  const flags = [
    user.under_18 ? ["child", "moving"] : null,
    user.consent === "pending" ? ["consent_pending", "waiting"] : null,
    user.locked ? ["locked", "bad"] : null,
  ].filter((flag): flag is [string, "moving" | "waiting" | "bad"] => flag !== null);
  if (!flags.length) return null;
  return (
    <span className="inline-flex flex-wrap gap-1.5">
      {flags.map(([flag, tone]) => (
        <StatusChip key={flag} tone={tone}>
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
  const columns: Column<Customer>[] = [
    { key: "name", label: copy.users.columns.name, render: (user) => user.full_name || user.email },
    {
      key: "email",
      label: copy.users.columns.email,
      render: (user) => <span className="font-mono text-[14px]">{user.email || copy.common.none}</span>,
    },
    {
      key: "phone",
      label: copy.users.columns.phone,
      render: (user) => <span className="font-mono text-[14px]">{user.phone || copy.common.none}</span>,
    },
    { key: "class", label: copy.users.columns.class, render: (user) => classOf(user) || copy.common.none },
    {
      key: "status",
      label: copy.users.columns.status,
      render: (user) => (
        <span className="inline-flex flex-wrap items-center gap-1.5">
          <StatusChip tone={toneOf(user.status)}>{labelOf(copy.users.statuses, user.status)}</StatusChip>
          <CustomerFlagChips user={user} />
        </span>
      ),
    },
    { key: "joined", label: copy.users.columns.joined, render: (user) => formatDate(user.created) },
    {
      key: "lastSeen",
      label: copy.users.columns.lastSeen,
      render: (user) => (user.last_login ? formatDate(user.last_login) : copy.common.never),
      hidden: true,
    },
  ];
  return (
    <DataTable
      listKey="users"
      caption={copy.users.title}
      rows={rows}
      columns={columns}
      rowId={(user) => String(user.id)}
      rowHref={(user) => `/users/${user.id}/`}
      next={next}
      previous={previous}
      views={views}
      filters={[
        { name: "q", label: copy.filters.searchList(copy.users.title.toLowerCase()), type: "search" },
        {
          name: "class_level",
          label: copy.users.columns.class,
          type: "select",
          options: Object.entries(copy.users.classLevel).map(([value, label]) => ({ value, label })),
        },
        {
          name: "is_active",
          label: copy.users.activeFilter,
          type: "select",
          options: Object.entries(copy.users.activeOptions).map(([value, label]) => ({ value, label })),
        },
      ]}
      empty={{ title: copy.users.emptyTitle, text: copy.users.emptyText }}
    />
  );
}
