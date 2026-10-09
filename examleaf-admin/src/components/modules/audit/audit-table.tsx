"use client";

// The audit trail as a list (GET audit/): who did what to which record, when, with what outcome and why; searched and
// filtered through the address. A row opens the event in a side sheet with every field, the before and after of what
// changed and the event's place in the hash chain. Export asks for a range of days; the file is made in the
// background (POST audit/export/) and lands in the inbox.
import Link from "next/link";
import { useId, useState } from "react";

import { type Column, DataTable } from "@/components/data/data-table";
import { actorLabel } from "@/components/data/event-timeline";
import { JobProgress } from "@/components/data/job-progress";
import { Facts } from "@/components/data/record-page";
import { StatusChip } from "@/components/data/status-chip";
import { ErrorSummary } from "@/components/forms/error-summary";
import { fieldError, useAction } from "@/components/forms/use-action";
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
import { Field, FormGrid } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { type AuditEvent, exportAudit, type SavedView } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDateTime } from "@/lib/format";
import { P } from "@/lib/modules";
import { targetHref } from "@/lib/targets";

/** A value of a change as text: JSON for anything that is not a plain string. */
export function shown(value: unknown): string {
  if (value === null || value === undefined) return copy.common.none;
  return typeof value === "string" ? value : JSON.stringify(value);
}

function EventSheet({ event, onClose }: { event: AuditEvent | null; onClose: () => void }) {
  const changes = event ? Object.entries(event.changes) : [];
  const href = event ? targetHref(event.target) : null;
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
                  value: `${actorLabel(event)}${event.actor.email && event.actor.name ? ` (${event.actor.email})` : ""} · ${labelOf(copy.audit.actorTypes, event.actor.type)}`,
                },
                ...(event.on_behalf_of
                  ? [{ label: copy.audit.onBehalfOf, value: event.on_behalf_of.name || event.on_behalf_of.email }]
                  : []),
                {
                  label: copy.audit.columns.target,
                  value: event.target ? (
                    href ? (
                      <Link href={href}>{event.target.label || `${event.target.type} ${event.target.id}`}</Link>
                    ) : (
                      event.target.label || `${event.target.type} ${event.target.id}`
                    )
                  ) : (
                    copy.common.none
                  ),
                },
                { label: copy.audit.columns.outcome, value: labelOf(copy.audit.outcomes, event.outcome) },
                { label: copy.audit.columns.reason, value: event.reason ?? copy.common.none },
                { label: copy.audit.requestId, value: <code>{event.request_id ?? copy.common.none}</code> },
                { label: copy.audit.ip, value: <code>{event.ip ?? copy.common.unknown}</code> },
                { label: copy.audit.hash, value: <code className="break-all">{event.hash ?? copy.common.none}</code> },
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
                    {changes.map(([field, [before, after]]) => (
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

function ExportAudit() {
  const id = useId();
  const [open, setOpen] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const { run, busy, error, setError } = useAction();
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) {
          setError(null);
          setJobId(null);
        }
      }}
    >
      <Button variant="secondary" size="sm" onClick={() => setOpen(true)}>
        {copy.audit.export}
      </Button>
      <DialogContent>
        <DialogHeader>{copy.audit.exportTitle}</DialogHeader>
        <form
          noValidate
          className="flex flex-col gap-3.5"
          onSubmit={(event) => {
            event.preventDefault();
            const form = new FormData(event.currentTarget);
            run(async () => {
              const started = await exportAudit({
                from: String(form.get("from") ?? ""),
                to: String(form.get("to") ?? ""),
              });
              setJobId(started.job_id);
            });
          }}
        >
          <DialogBody>
            <DialogDescription>{copy.audit.exportText}</DialogDescription>
          </DialogBody>
          <ErrorSummary error={error} idPrefix={`${id}-`} labels={{ from: copy.common.from, to: copy.common.to }} />
          <FormGrid>
            <Field id={`${id}-from`} label={copy.common.from} error={fieldError(error, "from")}>
              <Input name="from" type="date" aria-required="true" />
            </Field>
            <Field id={`${id}-to`} label={copy.common.to} error={fieldError(error, "to")}>
              <Input name="to" type="date" aria-required="true" />
            </Field>
          </FormGrid>
          {jobId ? <JobProgress jobId={jobId} /> : null}
          <DialogFooter>
            <Button variant="secondary" onClick={() => setOpen(false)}>
              {jobId ? copy.common.close : copy.common.cancel}
            </Button>
            {jobId ? null : (
              <Button type="submit" busy={busy}>
                {copy.audit.exportStart}
              </Button>
            )}
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function AuditTable({
  rows,
  next,
  previous,
  views,
}: {
  rows: AuditEvent[];
  next: string | null;
  previous: string | null;
  views: SavedView[] | null;
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
    {
      key: "target",
      wrap: true,
      label: copy.audit.columns.target,
      render: (event) =>
        event.target?.label || (event.target ? `${event.target.type} ${event.target.id}` : copy.common.none),
    },
    {
      key: "outcome",
      label: copy.audit.columns.outcome,
      render: (event) => (
        <StatusChip tone={event.outcome === "success" ? "good" : "bad"}>
          {labelOf(copy.audit.outcomes, event.outcome)}
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
        rowId={(event) => event.id}
        rowLabel={(event) => `${event.action}, ${formatDateTime(event.ts)}`}
        onOpen={setOpen}
        next={next}
        previous={previous}
        views={views}
        filters={[
          { name: "q", label: copy.audit.filters.q, type: "search" },
          { name: "actor", label: copy.audit.filters.actor, type: "text" },
          { name: "action", label: copy.audit.filters.action, type: "text" },
          { name: "target_type", label: copy.audit.filters.targetType, type: "text" },
          { name: "target_id", label: copy.audit.filters.targetId, type: "text" },
          { name: "from", label: copy.filters.from, type: "date" },
          { name: "to", label: copy.filters.to, type: "date" },
        ]}
        toolbar={can(P.auditExport) ? <ExportAudit /> : null}
        empty={{ title: copy.audit.emptyTitle, text: copy.audit.emptyText }}
      />
      <EventSheet event={open} onClose={() => setOpen(null)} />
    </>
  );
}
