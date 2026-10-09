"use client";

// The students under 18 waiting for a parent (GET users/consent-pending/), the first to register first: the parent's
// contact masked with the channel the link goes by, the links sent so far, when the last one went and when it stops
// working (7 days), how many went today of the day's limit (3 to one address or number), and whether the account only
// reads until a parent confirms. Each row can send the link again or record the consent by hand, when the manifest
// allows; the API decides (a text out of hours, the limit, a consent already on record) and records it.
import { type Column, DataTable } from "@/components/data/data-table";
import { StatusChip } from "@/components/data/status-chip";
import { useCan } from "@/components/shell/manifest";
import type { ConsentPending } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { classOf } from "@/lib/display";
import { formatDateTime } from "@/lib/format";
import { P } from "@/lib/modules";

import { ageWords } from "./badges";
import { ResendLink, VerifyConsent } from "./consent";

/** The last link's life: when it stops working, when it did, or that none went. */
export function linkEnds(row: Pick<ConsentPending, "links_sent" | "link_expires_at" | "link_expired">): string {
  const words = copy.customers.pending;
  if (!row.links_sent || !row.link_expires_at) return words.never;
  return row.link_expired
    ? words.ended(formatDateTime(row.link_expires_at))
    : words.until(formatDateTime(row.link_expires_at));
}

export function ConsentPendingTable({
  rows,
  next,
  previous,
}: {
  rows: ConsentPending[];
  next: string | null;
  previous: string | null;
}) {
  const can = useCan();
  const words = copy.customers.pending;
  // a link goes only while the site asks for a parent's confirmation (`blocking`); a consent by hand any time
  const resend = can(P.usersResendVerification) && rows.some((row) => row.blocking);
  const record = can(P.usersVerifyConsent);
  const columns: Column<ConsentPending>[] = [
    { key: "student", label: words.columns.student, render: (row) => row.full_name },
    { key: "class", label: words.columns.class, render: (row) => classOf(row) || copy.common.none },
    { key: "age", label: words.columns.age, render: (row) => ageWords(row.age_band) },
    {
      key: "parent",
      label: words.columns.parent,
      wrap: true,
      render: (row) =>
        row.parent_contact ? (
          <span className="font-mono text-[14px]">
            {words.contact(row.parent_contact, labelOf(words.channels, row.parent_channel))}
          </span>
        ) : (
          words.noContact
        ),
    },
    { key: "sent", label: words.columns.sent, numeric: true, render: (row) => row.links_sent },
    {
      key: "last",
      label: words.columns.last,
      render: (row) => (row.last_link_at ? formatDateTime(row.last_link_at) : words.never),
    },
    { key: "ends", label: words.columns.ends, wrap: true, render: (row) => linkEnds(row) },
    {
      key: "today",
      label: words.columns.today,
      render: (row) => words.today(row.links_today, row.daily_limit),
    },
    {
      key: "account",
      label: words.columns.account,
      wrap: true,
      render: (row) => (
        <span className="flex flex-col gap-0.5">
          <span>{row.blocking ? <StatusChip tone="waiting">{words.readOnly}</StatusChip> : words.inUse}</span>
          {row.email_verified ? null : <span className="text-[13px] text-muted-foreground">{words.noEmail}</span>}
        </span>
      ),
    },
    ...(resend || record
      ? [
          {
            key: "actions",
            label: words.columns.actions,
            render: (row: ConsentPending) => (
              <span className="inline-flex flex-wrap items-start gap-2">
                {resend && row.blocking ? <ResendLink id={row.id} name={row.full_name} /> : null}
                {record ? <VerifyConsent id={row.id} name={row.full_name} /> : null}
              </span>
            ),
          },
        ]
      : []),
  ];
  return (
    <DataTable
      listKey="consent-pending"
      caption={words.title}
      rows={rows}
      columns={columns}
      rowId={(row) => String(row.id)}
      rowHref={(row) => `/users/${row.id}/`}
      next={next}
      previous={previous}
      empty={{ title: words.emptyTitle, text: words.emptyText }}
    />
  );
}
