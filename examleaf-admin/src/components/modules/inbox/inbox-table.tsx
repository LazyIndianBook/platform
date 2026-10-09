"use client";

// The inbox as a list: what waits (its record one click away), its kind, when it is due, who has it. Open items can
// be marked done, snoozed until a time, or taken; several at once through the bulk bar (a background job). Filters:
// open, snoozed or done; the kind; mine or anyone's.
import { useRouter } from "next/navigation";
import { useState } from "react";

import { type Column, DataTable } from "@/components/data/data-table";
import { StatusChip } from "@/components/data/status-chip";
import { ErrorSummary } from "@/components/forms/error-summary";
import { useAction } from "@/components/forms/use-action";
import { useCan, useManifest } from "@/components/shell/manifest";
import { Popover } from "@/components/shell/popover";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "@/components/ui/toaster";
import { type InboxItem, inboxAssign, inboxDone, inboxSnooze, type SavedView } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDateTime, fromLocalInput, toLocalInput } from "@/lib/format";
import { P } from "@/lib/modules";
import { targetHref } from "@/lib/targets";

/** Tomorrow at 09:00 in India, as a datetime-local value. */
function tomorrowMorning(now: number): string {
  return `${toLocalInput(now + 86_400_000).slice(0, 10)}T09:00`;
}

function RowActions({ item, now }: { item: InboxItem; now: number }) {
  const router = useRouter();
  const manifest = useManifest();
  const { run, busy, error } = useAction();
  const [what, setWhat] = useState<string | null>(null);
  const act = (label: string, success: string, work: () => Promise<unknown>) => {
    setWhat(label);
    run(async () => {
      await work();
      toast.success(success);
      router.refresh();
    });
  };
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-nowrap items-center gap-1.5">
        <Button
          size="sm"
          variant="secondary"
          busy={busy && what === "done"}
          onClick={() => act("done", copy.inbox.markedDone, () => inboxDone(item.id))}
        >
          {copy.inbox.done}
          <span className="sr-only">: {item.title}</span>
        </Button>
        <Popover
          button={
            <>
              {copy.inbox.snooze}
              <span className="sr-only">: {item.title}</span>
            </>
          }
          buttonClassName="min-h-11 border-[1.5px] px-3 text-[15px]"
        >
          {(close) => (
            <form
              className="flex flex-col gap-2"
              onSubmit={(event) => {
                event.preventDefault();
                const until = String(new FormData(event.currentTarget).get("until") ?? "");
                close();
                act("snooze", copy.inbox.snoozed, () => inboxSnooze(item.id, fromLocalInput(until)));
              }}
            >
              <label htmlFor={`snooze-${item.id}`} className="text-sm font-semibold">
                {copy.inbox.snoozeUntil}
              </label>
              <Input
                id={`snooze-${item.id}`}
                name="until"
                type="datetime-local"
                defaultValue={tomorrowMorning(now)}
                className="min-h-11"
                required
              />
              <Button type="submit" size="sm">
                {copy.inbox.snooze}
              </Button>
            </form>
          )}
        </Popover>
        {item.assignee?.id !== manifest.user.id ? (
          <Button
            size="sm"
            variant="ghost"
            busy={busy && what === "assign"}
            onClick={() => act("assign", copy.inbox.assigned, () => inboxAssign(item.id, manifest.user.id))}
          >
            {copy.inbox.assignToMe}
            <span className="sr-only">: {item.title}</span>
          </Button>
        ) : null}
      </div>
      {error ? (
        <div className="max-w-80 whitespace-normal">
          <ErrorSummary error={error} />
        </div>
      ) : null}
    </div>
  );
}

export function InboxTable({
  rows,
  next,
  previous,
  views,
  state,
  now,
}: {
  rows: InboxItem[];
  next: string | null;
  previous: string | null;
  views: SavedView[] | null;
  state: string;
  now: number;
}) {
  const can = useCan();
  const changing = can(P.inboxChange) && state === "open";
  const columns: Column<InboxItem>[] = [
    { key: "title", label: copy.inbox.columns.title, render: (item) => item.title },
    {
      key: "kind",
      label: copy.inbox.columns.kind,
      render: (item) => <StatusChip tone="moving">{labelOf(copy.inbox.kinds, item.kind)}</StatusChip>,
    },
    {
      key: "due",
      label: copy.inbox.columns.due,
      render: (item) =>
        item.snoozed_until && state === "snoozed"
          ? copy.inbox.snoozedUntil(formatDateTime(item.snoozed_until))
          : item.due_at
            ? formatDateTime(item.due_at)
            : copy.common.none,
    },
    {
      key: "assignee",
      label: copy.inbox.columns.assignee,
      render: (item) => item.assignee?.name || item.assignee?.email || copy.inbox.unassigned,
    },
    { key: "created", label: copy.inbox.columns.created, render: (item) => formatDateTime(item.created_at) },
    ...(changing
      ? [
          {
            key: "actions",
            label: copy.common.actions,
            render: (item: InboxItem) => <RowActions item={item} now={now} />,
          },
        ]
      : []),
  ];

  return (
    <DataTable
      listKey="inbox"
      caption={copy.inbox.title}
      rows={rows}
      columns={columns}
      rowId={(item) => item.id}
      rowLabel={(item) => item.title}
      rowHref={(item) => targetHref(item.target)}
      next={next}
      previous={previous}
      views={views}
      filters={[
        {
          name: "state",
          label: copy.inbox.stateLabel,
          type: "select",
          options: [
            { value: "snoozed", label: copy.inbox.states.snoozed },
            { value: "done", label: copy.inbox.states.done },
          ],
          any: copy.inbox.states.open,
        },
        {
          name: "kind",
          label: copy.inbox.kind,
          type: "select",
          options: Object.entries(copy.inbox.kinds)
            .filter(([kind]) => kind !== "change_request")
            .map(([value, label]) => ({ value, label })),
        },
        {
          name: "assignee",
          label: copy.inbox.assignee,
          type: "select",
          options: [{ value: "anyone", label: copy.common.anyone }],
          any: copy.common.me,
        },
      ]}
      bulk={
        changing
          ? [
              { action: "inbox.done", label: copy.inbox.done },
              { action: "inbox.assign_me", label: copy.inbox.assignToMe },
            ]
          : []
      }
      empty={{ title: copy.inbox.emptyTitle, text: copy.inbox.emptyText }}
    />
  );
}
