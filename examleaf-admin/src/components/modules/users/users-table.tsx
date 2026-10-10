"use client";

// Customers as a list (GET users/?kind=&q=&class_level=&is_active=): the tabs (everyone, students, parents, guest
// buyers: another table, guests-table.tsx), masked contact details only (a reveal happens on the record, with a
// reason), the class and board, the age band, a student under 18's parent consent and how it was given, the account's
// state and what is verified. The search finds an email address exactly, a mobile number, or three letters or more of a
// name, and the API records each such search as a lookup (its keyed hash, never the words). Chosen rows get the bulk bar
// (users-bulk.tsx), whose actions run as background jobs with their progress above the list.
import { useRouter } from "next/navigation";
import { useState } from "react";

import { type Column, DataTable } from "@/components/data/data-table";
import { JobProgress } from "@/components/data/job-progress";
import { StatusChip, toneOf } from "@/components/data/status-chip";
import { useCan } from "@/components/shell/manifest";
import { Section } from "@/components/shell/page-header";
import type { Customer, CustomerDetail, Job, SavedView } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { classOf } from "@/lib/display";
import { formatDate } from "@/lib/format";
import { P } from "@/lib/modules";

import { ageWords, verifiedWords } from "./badges";
import { UsersBulk } from "./users-bulk";

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

/** The list's tabs: the API's `kind` (nothing: everyone). The guest buyers come from the orders, so they are drawn for
 *  whoever may read orders. */
export function kindPresets(guests: boolean) {
  const tabs = copy.customers.tabs;
  return {
    name: "kind",
    label: tabs.label,
    all: tabs.all,
    options: [
      { value: "students", label: tabs.students },
      { value: "parents", label: tabs.parents },
      ...(guests ? [{ value: "guests", label: tabs.guests }] : []),
    ],
  };
}

export function UsersTable({
  rows,
  next,
  previous,
  views,
  guests,
}: {
  rows: Customer[];
  next: string | null;
  previous: string | null;
  views: SavedView[] | null;
  /** Whether the guest buyers' tab is drawn (the orders' reader). */
  guests: boolean;
}) {
  const can = useCan();
  const router = useRouter();
  const [job, setJob] = useState<{ job: Job; title: string } | null>(null);
  const bulk = can(P.jobsView) && (can(P.usersSuspend) || can(P.usersEndSessions) || can(P.usersResendVerification));

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
    { key: "age", label: copy.customers.columns.age, render: (user) => ageWords(user.age_band) },
    {
      key: "consent",
      label: copy.customers.columns.consent,
      wrap: true,
      render: (user) =>
        user.under_18 ? (
          <span className="flex flex-col">
            <span>{labelOf(copy.users.consentStates, user.consent)}</span>
            {user.consent === "verified" && user.consent_method ? (
              <span className="text-[13px] text-muted-foreground">
                {labelOf(copy.customers.methods, user.consent_method)}
              </span>
            ) : null}
          </span>
        ) : (
          <span className="text-muted-foreground">{copy.customers.notNeeded}</span>
        ),
    },
    {
      key: "status",
      label: copy.users.columns.status,
      render: (user) => (
        <span className="inline-flex flex-wrap items-center gap-1.5">
          <StatusChip tone={toneOf(user.status)}>{labelOf(copy.users.statuses, user.status)}</StatusChip>
          {user.locked ? <StatusChip tone="bad">{copy.users.flags.locked}</StatusChip> : null}
        </span>
      ),
    },
    { key: "verified", label: copy.customers.columns.verified, render: (user) => verifiedWords(user) },
    { key: "joined", label: copy.users.columns.joined, render: (user) => formatDate(user.created) },
    {
      key: "lastSeen",
      label: copy.users.columns.lastSeen,
      render: (user) => (user.last_login ? formatDate(user.last_login) : copy.common.never),
      hidden: true,
    },
    {
      key: "twoStep",
      label: copy.customers.columns.twoStep,
      render: (user) => (user.mfa_on ? copy.common.on : copy.common.off),
      hidden: true,
    },
    {
      key: "teacher",
      label: copy.customers.columns.teacher,
      render: (user) => labelOf(copy.users.teacherStates, user.teacher),
      hidden: true,
    },
  ];

  return (
    <div className="flex flex-col gap-4">
      {job ? (
        <Section title={`${copy.customers.bulk.progress}: ${job.title}`}>
          <JobProgress key={job.job.id} job={job.job} onDone={() => router.refresh()} />
        </Section>
      ) : null}
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
        presets={kindPresets(guests)}
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
        selection={
          bulk
            ? {
                label: (user) => copy.customers.bulk.row(user.full_name || user.email),
                page: copy.customers.bulk.page,
                bulk: (chosen, clear) => (
                  <UsersBulk rows={chosen} clear={clear} onJob={(started, title) => setJob({ job: started, title })} />
                ),
              }
            : undefined
        }
        empty={{ title: copy.users.emptyTitle, text: copy.users.emptyText }}
      />
    </div>
  );
}
