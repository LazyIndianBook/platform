"use client";

// The audit trail as a list (GET audit/): who did what to which record, when, with what outcome and why; filtered
// through the address. A row opens the event in a side sheet with every field, the before and after of what changed
// and its place in the hash chain. Export takes the list's filters (POST audit/export/): the file at once up to 5,000
// rows within the person's limit (a download), else a background job with its progress (one above the limit waits
// for an admin's approval first).
import Link from "next/link";
import { useState } from "react";

import { type Column, DataTable } from "@/components/data/data-table";
import { actorLabel } from "@/components/data/event-timeline";
import { JobProgress } from "@/components/data/job-progress";
import { Facts } from "@/components/data/record-page";
import { StatusChip } from "@/components/data/status-chip";
import { ErrorSummary } from "@/components/forms/error-summary";
import { useAction } from "@/components/forms/use-action";
import { useCan } from "@/components/shell/manifest";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/dialog";
import { toast } from "@/components/ui/toaster";
import { type AuditEvent, exportAudit, type Job, type SavedView } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDateTime } from "@/lib/format";
import { P } from "@/lib/modules";
import { targetHref } from "@/lib/targets";

/** A value of a change as text: JSON for anything that is not a plain string. */
export function shown(value: unknown): string {
  if (value === null || value === undefined) return copy.common.none;
  return typeof value === "string" ? value : JSON.stringify(value);
}

/** The event's `changes`, {field: [before, after]}, as rows (the schema types it as any JSON). */
function changesOf(event: AuditEvent): [string, unknown, unknown][] {
  const changes = event.changes && typeof event.changes === "object" ? (event.changes as Record<string, unknown>) : {};
  return Object.entries(changes).map(([field, pair]) =>
    Array.isArray(pair) ? [field, pair[0], pair[1]] : [field, undefined, pair],
  );
}

const targetText = (event: AuditEvent) =>
  event.target_label || (event.target_type ? `${event.target_type} ${event.target_id ?? ""}`.trim() : copy.common.none);

function EventSheet({ event, onClose }: { event: AuditEvent | null; onClose: () => void }) {
  const changes = event ? changesOf(event) : [];
  const href = event ? targetHref(event.target_type, event.target_id, event.action) : null;
  const details = event?.details && typeof event.details === "object" ? event.details : null;
  return (
    <Dialog open={event !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="w-[min(36rem,calc(100%-32px))] [&[open]]:mr-0 [&[open]]:ml-auto [&[open]]:h-[calc(100dvh-32px)] [&[open]]:max-h-none">
        <DialogHeader>{copy.audit.eventTitle}</DialogHeader>
        {event ? (
          <DialogBody>
            <DialogDescription className="font-mono text-[13px] break-all">{event.action}</DialogDescription>
            <Facts
              items={[
                { label: copy.audit.columns.ts, value: formatDateTime(event.ts) },
                {
                  label: copy.audit.columns.actor,
                  value:
                    event.actor_type === "staff" && event.actor_id ? (
                      <Link href={`/people/${event.actor_id}/`}>{actorLabel(event)}</Link>
                    ) : (
                      actorLabel(event)
                    ),
                },
                ...(event.on_behalf_of
                  ? [
                      {
                        label: copy.audit.onBehalfOf,
                        value: copy.audit.actor(copy.audit.actorTypes.user, event.on_behalf_of),
                      },
                    ]
                  : []),
                ...(event.permission
                  ? [{ label: copy.audit.permission, value: <code className="break-all">{event.permission}</code> }]
                  : []),
                {
                  label: copy.audit.columns.target,
                  value: href ? <Link href={href}>{targetText(event)}</Link> : targetText(event),
                },
                { label: copy.audit.columns.outcome, value: labelOf(copy.audit.outcomes, event.outcome ?? "success") },
                { label: copy.audit.columns.reason, value: event.reason || copy.common.none },
                ...(event.change_request_id
                  ? [
                      {
                        label: copy.audit.changeRequest,
                        value: (
                          <Link href={`/approvals/${event.change_request_id}/`}>
                            {copy.approval.number(String(event.change_request_id))}
                          </Link>
                        ),
                      },
                    ]
                  : []),
                ...(event.break_glass ? [{ label: copy.audit.breakGlass, value: copy.common.yes }] : []),
                { label: copy.audit.requestId, value: <code>{event.request_id || copy.common.none}</code> },
                { label: copy.audit.ip, value: <code>{event.ip ?? copy.common.unknown}</code> },
                { label: copy.audit.chain, value: event.chain ?? copy.common.unknown },
                { label: copy.audit.hash, value: <code className="break-all">{event.hash}</code> },
              ]}
            />
            <h3 className="mt-2 font-head text-lg">{copy.audit.changes}</h3>
            {changes.length ? (
              <div
                data-slot="table-wrap"
                className="table-wrap"
                role="region"
                aria-label={copy.audit.changes}
                tabIndex={0}
              >
                <table>
                  <caption className="sr-only">{copy.audit.changes}</caption>
                  <thead>
                    <tr>
                      <th scope="col">{copy.audit.field}</th>
                      <th scope="col">{copy.audit.before}</th>
                      <th scope="col">{copy.audit.after}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {changes.map(([field, before, after]) => (
                      <tr key={field}>
                        <th scope="row" className="font-mono text-[13px] font-medium normal-case">
                          {field}
                        </th>
                        <td className="font-mono text-[13px] break-all">{shown(before)}</td>
                        <td className="font-mono text-[13px] break-all">{shown(after)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p>{copy.audit.noChanges}</p>
            )}
            {details && Object.keys(details).length ? (
              <>
                <h3 className="mt-2 font-head text-lg">{copy.audit.details}</h3>
                <pre className="code-block" role="region" tabIndex={0} aria-label={copy.audit.details}>
                  {JSON.stringify(details, null, 2)}
                </pre>
              </>
            ) : null}
          </DialogBody>
        ) : null}
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="secondary">{copy.common.close}</Button>
          </DialogClose>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** A file in the browser's downloads, from a Blob. */
function save(file: Blob, name: string) {
  const url = URL.createObjectURL(file);
  const link = Object.assign(document.createElement("a"), { href: url, download: name });
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function ExportAudit({ filters }: { filters: Record<string, string> }) {
  const [open, setOpen] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  const { run, busy, error, setError } = useAction();
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) {
          setError(null);
          setJob(null);
        }
      }}
    >
      <Button variant="secondary" size="sm" onClick={() => setOpen(true)}>
        {copy.audit.export}
      </Button>
      <DialogContent>
        <DialogHeader>{copy.audit.exportTitle}</DialogHeader>
        <DialogBody>
          <DialogDescription>{copy.audit.exportText}</DialogDescription>
        </DialogBody>
        <ErrorSummary error={error} />
        {job ? <JobProgress job={job} /> : null}
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="secondary">{job ? copy.common.close : copy.common.cancel}</Button>
          </DialogClose>
          {job ? null : (
            <Button
              busy={busy}
              onClick={() =>
                run(async () => {
                  const answer = await exportAudit(filters);
                  if ("job" in answer) return setJob(answer.job);
                  save(answer.file, answer.name);
                  toast.success(copy.audit.exported);
                  setOpen(false);
                })
              }
            >
              {copy.audit.exportStart}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function AuditTable({
  rows,
  next,
  previous,
  views,
  filters,
}: {
  rows: AuditEvent[];
  next: string | null;
  previous: string | null;
  views: SavedView[] | null;
  /** The API's filters the list shows, for the export. */
  filters: Record<string, string>;
}) {
  const can = useCan();
  const [open, setOpen] = useState<AuditEvent | null>(null);
  const columns: Column<AuditEvent>[] = [
    {
      key: "ts",
      label: copy.audit.columns.ts,
      render: (event) => formatDateTime(event.ts),
      className: "whitespace-nowrap",
    },
    { key: "actor", label: copy.audit.columns.actor, render: (event) => actorLabel(event) },
    {
      key: "action",
      label: copy.audit.columns.action,
      render: (event) => <code className="text-[13px] break-all">{event.action}</code>,
    },
    { key: "target", wrap: true, label: copy.audit.columns.target, render: targetText },
    {
      key: "outcome",
      label: copy.audit.columns.outcome,
      render: (event) => (
        <StatusChip tone={(event.outcome ?? "success") === "success" ? "good" : "bad"}>
          {labelOf(copy.audit.outcomes, event.outcome ?? "success")}
        </StatusChip>
      ),
    },
    {
      key: "reason",
      label: copy.audit.columns.reason,
      render: (event) => event.reason ?? "",
      hidden: true,
      wrap: true,
    },
  ];
  return (
    <>
      <DataTable
        listKey="audit"
        caption={copy.audit.title}
        rows={rows}
        columns={columns}
        rowId={(event) => String(event.id)}
        onOpen={setOpen}
        next={next}
        previous={previous}
        views={views}
        filters={[
          { name: "action_prefix", label: copy.audit.filters.actionPrefix, type: "search" },
          { name: "actor", label: copy.audit.filters.actor, type: "text" },
          { name: "target_type", label: copy.audit.filters.targetType, type: "text" },
          { name: "target_id", label: copy.audit.filters.targetId, type: "text" },
          { name: "change_request", label: copy.audit.filters.changeRequest, type: "text" },
          {
            name: "outcome",
            label: copy.audit.filters.outcome,
            type: "select",
            options: Object.entries(copy.audit.outcomes).map(([value, label]) => ({ value, label })),
          },
          {
            name: "break_glass",
            label: copy.audit.filters.breakGlass,
            type: "select",
            options: [{ value: "true", label: copy.common.yes }],
          },
          { name: "since", label: copy.filters.from, type: "date" },
          { name: "until", label: copy.filters.to, type: "date" },
        ]}
        toolbar={can(P.auditExport) ? <ExportAudit filters={filters} /> : null}
        empty={{ title: copy.audit.emptyTitle, text: copy.audit.emptyText }}
      />
      <EventSheet event={open} onClose={() => setOpen(null)} />
    </>
  );
}
