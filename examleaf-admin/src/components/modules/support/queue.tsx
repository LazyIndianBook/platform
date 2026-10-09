"use client";

// The queue as a list (GET support/tickets/): the next legal deadline first, as the API sorts it. Each row: the number
// and subject (the row's link), who wrote (masked), the category, the status, the deadline it runs on now counting down
// (red once late), who has it and how it came. Filters in the address: the search (a ticket's or an order's number,
// an email address or a mobile number: a lookup by email or phone is logged by the API, as its hash), the category,
// priority and source; the status (spam among them) in All; on a live site, the test orders' tickets.
import { Clock } from "@/components/data/clock";
import { type Column, DataTable } from "@/components/data/data-table";
import type { FilterDef } from "@/components/data/filter-bar";
import { StatusChip } from "@/components/data/status-chip";
import { useManifest } from "@/components/shell/manifest";
import type { Agent, SavedView, Ticket } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDate, formatDateTime } from "@/lib/format";

import {
  agentName,
  categoryLabel,
  clockLabel,
  requesterLabel,
  sourceLabel,
  statusLabel,
  type Tab,
  ticketTone,
} from "./shared";

const options = (table: Record<string, string>) => Object.entries(table).map(([value, label]) => ({ value, label }));

/** A ticket's deadline in the queue: the running clock counting down, else when it stopped (and if it was late). */
export function QueueClock({ ticket, now }: { ticket: Ticket; now: number }) {
  if (ticket.clock)
    return <Clock label={clockLabel(ticket)} start={ticket.received_at} due={ticket.next_due_at} now={now} compact />;
  const stopped = ticket.closed_at ?? ticket.resolved_at;
  const missed = ticket.ack_breached || ticket.due_breached;
  return (
    <span className="text-sm">
      {stopped ? copy.support.stoppedOn(statusLabel(ticket.status), formatDate(stopped)) : statusLabel(ticket.status)}
      {missed ? <span className="font-semibold text-destructive"> · {copy.support.missed}</span> : null}
    </span>
  );
}

export function TicketQueue({
  rows,
  next,
  previous,
  views,
  tab,
  agents,
  now,
}: {
  rows: Ticket[];
  next: string | null;
  previous: string | null;
  views: SavedView[] | null;
  tab: Tab;
  agents: Agent[] | null;
  now: number;
}) {
  const manifest = useManifest();
  const me = manifest.user.id;
  const columns: Column<Ticket>[] = [
    {
      key: "ticket",
      label: copy.support.columns.ticket,
      render: (ticket) => (
        <span className="flex flex-col gap-0.5">
          <span className="font-mono text-[14px]">{ticket.number}</span>
          <span className="font-normal">{ticket.subject}</span>
          {ticket.is_test ? (
            <StatusChip tone="stopped" className="self-start">
              {copy.support.test}
            </StatusChip>
          ) : null}
        </span>
      ),
    },
    { key: "requester", label: copy.support.columns.requester, render: requesterLabel, wrap: true },
    { key: "category", label: copy.support.columns.category, render: (ticket) => categoryLabel(ticket.category) },
    {
      key: "status",
      label: copy.support.columns.status,
      render: (ticket) => <StatusChip tone={ticketTone(ticket.status)}>{statusLabel(ticket.status)}</StatusChip>,
    },
    { key: "clock", label: copy.support.columns.clock, render: (ticket) => <QueueClock ticket={ticket} now={now} /> },
    {
      key: "assignee",
      label: copy.support.columns.assignee,
      render: (ticket) => agentName(agents, ticket.assignee, me),
    },
    { key: "source", label: copy.support.columns.source, render: (ticket) => sourceLabel(ticket.source) },
    {
      key: "priority",
      label: copy.support.columns.priority,
      render: (ticket) => labelOf(copy.support.priorities, ticket.priority),
      hidden: true,
    },
    {
      key: "received",
      label: copy.support.columns.received,
      render: (ticket) => formatDateTime(ticket.received_at),
      hidden: true,
    },
    {
      key: "messages",
      label: copy.support.columns.messages,
      render: (ticket) => ticket.message_count,
      numeric: true,
      hidden: true,
    },
  ];
  const filters: FilterDef[] = [
    { name: "q", label: copy.support.searchLabel, type: "search" },
    {
      name: "category",
      label: copy.support.columns.category,
      type: "select",
      options: options(copy.support.categories),
    },
    {
      name: "priority",
      label: copy.support.columns.priority,
      type: "select",
      options: options(copy.support.priorities),
    },
    { name: "source", label: copy.support.columns.source, type: "select", options: options(copy.support.sources) },
    ...(tab === "all"
      ? [
          {
            name: "status",
            label: copy.support.columns.status,
            type: "select" as const,
            options: options(copy.support.statuses),
          },
        ]
      : []),
    // a live site keeps a test order's tickets out of the list unless asked (the test environment has nothing else)
    ...(manifest.flags.test_mode
      ? []
      : [
          {
            name: "test",
            label: copy.support.testFilter,
            type: "select" as const,
            options: options(copy.support.testOptions),
          },
        ]),
  ];
  return (
    <DataTable
      listKey="support"
      caption={copy.support.title}
      rows={rows}
      columns={columns}
      rowId={(ticket) => String(ticket.id)}
      rowHref={(ticket) => `/support/tickets/${encodeURIComponent(ticket.number)}/`}
      next={next}
      previous={previous}
      views={views}
      filters={filters}
      empty={{ title: copy.support.emptyTitle, text: copy.support.emptyText }}
    />
  );
}
