"use client";

// The data-rights queue (GET data-requests/?state=&type=) with its clocks: acknowledge within 48 hours, respond within
// the law's limit (the API's due_at: a month under today's rules, 90 days once the DPDP Rules apply), each as time left
// in words and coloured by urgency. Below the list, a request that came by email, phone or letter can be logged.
// On a request: acknowledge it, keep notes (sent with the version read, so a colleague's change is not overwritten),
// run an erasure's dry run, and copy a drafted reply.
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Clock } from "@/components/data/clock";
import { CopyButton } from "@/components/data/copy-button";
import { type Column, DataTable } from "@/components/data/data-table";
import { StatusChip, toneOf } from "@/components/data/status-chip";
import { ActionForm, formText } from "@/components/forms/action-form";
import { ErrorSummary } from "@/components/forms/error-summary";
import { fieldError, useAction } from "@/components/forms/use-action";
import { useDraftForm } from "@/components/forms/use-draft";
import { useCan } from "@/components/shell/manifest";
import { Button } from "@/components/ui/button";
import { Field, FormGrid } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { toast } from "@/components/ui/toaster";
import {
  acknowledgeDataRequest,
  createDataRequest,
  DATA_REQUEST_TYPES,
  type DataRequest,
  type DryRun,
  erasureDryRun,
  type SavedView,
  updateDataRequest,
} from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { requesterLabel } from "@/lib/display";
import { formatDate, formatDateTime, fromLocalInput, toLocalInput } from "@/lib/format";
import { P } from "@/lib/modules";

export function RequestsTable({
  rows,
  next,
  previous,
  views,
  now,
}: {
  rows: DataRequest[];
  next: string | null;
  previous: string | null;
  views: SavedView[] | null;
  now: number;
}) {
  const columns: Column<DataRequest>[] = [
    {
      key: "type",
      label: copy.privacy.columns.type,
      render: (request) => `${labelOf(copy.privacy.types, request.type)} · ${request.id}`,
    },
    {
      key: "requester",
      label: copy.privacy.columns.requester,
      render: (request) => <span className="font-mono text-[14px]">{requesterLabel(request)}</span>,
    },
    {
      key: "channel",
      label: copy.privacy.columns.channel,
      render: (request) => labelOf(copy.privacy.channels, request.channel),
      hidden: true,
    },
    { key: "received", label: copy.privacy.columns.received, render: (request) => formatDateTime(request.received_at) },
    {
      key: "ack",
      label: copy.privacy.columns.ack,
      render: (request) => (
        <Clock
          label={copy.privacy.ackClock}
          start={request.received_at}
          due={request.ack_due_at}
          doneAt={request.acknowledged_at}
          doneAs="acknowledged"
          now={now}
          compact
        />
      ),
    },
    {
      key: "due",
      label: copy.privacy.columns.due,
      render: (request) =>
        ["responded", "closed", "rejected"].includes(request.state) ? (
          labelOf(copy.privacy.states, request.state)
        ) : (
          <Clock label={copy.privacy.dueClock} start={request.received_at} due={request.due_at} now={now} compact />
        ),
    },
    {
      key: "state",
      label: copy.privacy.columns.state,
      render: (request) => (
        <StatusChip tone={toneOf(request.state)}>{labelOf(copy.privacy.states, request.state)}</StatusChip>
      ),
    },
  ];
  return (
    <DataTable
      listKey="data-requests"
      caption={copy.privacy.requestsTitle}
      rows={rows}
      columns={columns}
      rowId={(request) => request.id}
      rowLabel={(request) => `${labelOf(copy.privacy.types, request.type)} ${request.id}`}
      rowHref={(request) => `/privacy/requests/${request.id}/`}
      next={next}
      previous={previous}
      views={views}
      filters={[
        {
          name: "state",
          label: copy.privacy.columns.state,
          type: "select",
          options: ["received", "acknowledged", "in_progress", "responded", "closed", "rejected"].map((state) => ({
            value: state,
            label: copy.privacy.states[state],
          })),
        },
        {
          name: "type",
          label: copy.privacy.columns.type,
          type: "select",
          options: DATA_REQUEST_TYPES.map((type) => ({ value: type, label: copy.privacy.types[type] })),
        },
      ]}
      empty={{ title: copy.privacy.emptyRequestsTitle, text: copy.privacy.emptyRequestsText }}
    />
  );
}

export function LogRequestForm({ now }: { now: number }) {
  return (
    <ActionForm
      id="new-request"
      submitLabel={copy.privacy.logButton}
      success={copy.privacy.logged}
      labels={{
        type: copy.privacy.columns.type,
        channel: copy.privacy.channel,
        requester_email: copy.privacy.requesterEmail,
        requester_phone: copy.privacy.requesterPhone,
        received_at: copy.privacy.receivedAt,
      }}
      onSubmit={(form) =>
        createDataRequest({
          type: formText(form, "type"),
          channel: formText(form, "channel"),
          received_at: fromLocalInput(formText(form, "received_at")),
          ...(formText(form, "requester_email") ? { requester_email: formText(form, "requester_email") } : {}),
          ...(formText(form, "requester_phone") ? { requester_phone: formText(form, "requester_phone") } : {}),
          ...(formText(form, "notes") ? { notes: formText(form, "notes") } : {}),
        })
      }
    >
      {(error) => (
        <>
          <FormGrid>
            <Field id="new-request-type" label={copy.privacy.columns.type} error={fieldError(error, "type")}>
              <Select name="type" defaultValue="" aria-required="true">
                <option value="">{copy.privacy.columns.type}</option>
                {DATA_REQUEST_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {copy.privacy.types[type]}
                  </option>
                ))}
              </Select>
            </Field>
            <Field id="new-request-channel" label={copy.privacy.channel} error={fieldError(error, "channel")}>
              <Select name="channel" defaultValue="email">
                {Object.entries(copy.privacy.channels).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field
              id="new-request-received_at"
              label={copy.privacy.receivedAt}
              error={fieldError(error, "received_at")}
            >
              <Input name="received_at" type="datetime-local" defaultValue={toLocalInput(now)} aria-required="true" />
            </Field>
          </FormGrid>
          <FormGrid>
            <Field
              id="new-request-requester_email"
              label={copy.privacy.requesterEmail}
              optional
              error={fieldError(error, "requester_email")}
            >
              <Input name="requester_email" type="email" autoComplete="off" />
            </Field>
            <Field
              id="new-request-requester_phone"
              label={copy.privacy.requesterPhone}
              optional
              error={fieldError(error, "requester_phone")}
            >
              <Input name="requester_phone" type="tel" autoComplete="off" />
            </Field>
          </FormGrid>
          <Field id="new-request-notes" label={copy.privacy.notes} optional help={copy.privacy.notesHelp}>
            <Textarea name="notes" rows={3} />
          </Field>
        </>
      )}
    </ActionForm>
  );
}

export function Acknowledge({ request }: { request: DataRequest }) {
  const router = useRouter();
  const can = useCan();
  const { run, busy, error } = useAction();
  if (request.acknowledged_at || !can(P.requestsChange)) return null;
  return (
    <div className="flex flex-col gap-3">
      <ErrorSummary error={error} />
      <div>
        <Button
          busy={busy}
          onClick={() =>
            run(async () => {
              await acknowledgeDataRequest(request.id);
              toast.success(copy.privacy.acknowledgedToast);
              router.refresh();
            })
          }
        >
          {copy.privacy.acknowledge}
        </Button>
      </div>
    </div>
  );
}

export function RequestNotes({ request }: { request: DataRequest }) {
  const router = useRouter();
  const can = useCan();
  const { ref, save, clear } = useDraftForm(`notes-${request.id}`);
  const { run, busy, error } = useAction();
  const editing = can(P.requestsChange);
  if (!editing) return <p className="m-0 text-[15px] whitespace-pre-wrap">{request.notes || copy.common.none}</p>;
  return (
    <form
      ref={ref}
      onInput={save}
      noValidate
      className="flex max-w-[44rem] flex-col gap-3"
      onSubmit={(event) => {
        event.preventDefault();
        const notes = String(new FormData(event.currentTarget).get("notes") ?? "");
        run(async () => {
          await updateDataRequest(request.id, { notes }, request.version);
          clear();
          toast.success(copy.privacy.notesSaved);
          router.refresh();
        });
      }}
    >
      <ErrorSummary error={error} idPrefix="request-" labels={{ notes: copy.privacy.notes }} />
      <Field
        id="request-notes"
        label={copy.privacy.notes}
        help={copy.privacy.notesHelp}
        error={fieldError(error, "notes")}
      >
        <Textarea name="notes" rows={5} defaultValue={request.notes} />
      </Field>
      <div>
        <Button type="submit" variant="secondary" busy={busy}>
          {copy.privacy.saveNotes}
        </Button>
      </div>
    </form>
  );
}

export function ErasureDryRun({ request }: { request: DataRequest }) {
  const can = useCan();
  const { run, busy, error } = useAction();
  const [result, setResult] = useState<DryRun | null>(null);
  if (request.type !== "erasure" || !can(P.requestsChange)) return null;
  return (
    <div className="flex flex-col gap-4">
      <ErrorSummary error={error} />
      <div>
        <Button
          variant="secondary"
          busy={busy}
          onClick={() =>
            run(async () => {
              setResult(await erasureDryRun(request.id));
            })
          }
        >
          {copy.privacy.dryRunButton}
        </Button>
      </div>
      {result ? (
        <div className="grid gap-6 min-[900px]:grid-cols-2" aria-live="polite">
          <div className="flex flex-col gap-2">
            <h3 className="m-0 font-head text-lg">{copy.privacy.willErase}</h3>
            {result.will_erase.length ? (
              <ul className="m-0 pl-5 text-[15px]">
                {result.will_erase.map((what) => (
                  <li key={what}>{what}</li>
                ))}
              </ul>
            ) : (
              <p className="m-0 text-[15px] text-muted-foreground">{copy.privacy.nothingErased}</p>
            )}
          </div>
          <div className="flex flex-col gap-2">
            <h3 className="m-0 font-head text-lg">{copy.privacy.held}</h3>
            {result.held.length ? (
              <ul className="m-0 flex list-none flex-col gap-2 p-0 text-[15px]">
                {result.held.map((held) => (
                  <li key={held.what} className="border-l-2 border-warning-line pl-3">
                    <strong>{held.what}</strong>: {held.why}
                    {held.until ? (
                      <span className="text-muted-foreground"> ({copy.privacy.heldUntil(formatDate(held.until))})</span>
                    ) : null}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="m-0 text-[15px] text-muted-foreground">{copy.privacy.nothingHeld}</p>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}

export function ResponseDraft({ request }: { request: DataRequest }) {
  const text = copy.privacy.templateText(labelOf(copy.privacy.types, request.type), formatDate(request.received_at));
  return (
    <div className="flex flex-col gap-3">
      <p className="m-0 max-w-[60ch] rounded-lg border border-border bg-card p-4 text-[15px] leading-relaxed">{text}</p>
      <div>
        <CopyButton value={text} label={copy.privacy.copyTemplate} />
      </div>
    </div>
  );
}
