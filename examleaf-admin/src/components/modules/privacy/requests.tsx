"use client";

// The data-rights queue (GET data-requests/?status=&kind=&overdue=) with its clocks: acknowledge within 48 hours
// (ack_due_at), answer within the law's limit (due_at: a month today, 90 days for the DPDP rights from 13 May 2027),
// each as time left in words and coloured by urgency. Below the list, a request that came by email, phone or letter
// can be logged. On a request, its steps as the API has them: acknowledge, record the identity check, keep notes,
// an erasure's dry run and the erasure itself (a second person approves it), an access request's data by email,
// the answer's text, and closing it with the outcome and the answer sent.
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ApprovalNotice } from "@/components/data/approval-notice";
import { Clock } from "@/components/data/clock";
import { ConfirmDialog } from "@/components/data/confirm-typed";
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
import { ApiError } from "@/lib/api/errors";
import {
  acknowledgeDataRequest,
  closeDataRequest,
  createDataRequest,
  type DataRequest,
  type DataRequestRow,
  eraseForRequest,
  type ErasureReport,
  erasureReport,
  exportForRequest,
  type SavedView,
  type Schemas,
  updateDataRequest,
  verifyIdentity,
} from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDateTime, fromLocalInput, toLocalInput } from "@/lib/format";
import { P } from "@/lib/modules";

export const KINDS = Object.keys(copy.privacy.kinds) as Schemas["DataRequestKindEnum"][];

export function RequestsTable({
  rows,
  next,
  previous,
  views,
  now,
}: {
  rows: DataRequestRow[];
  next: string | null;
  previous: string | null;
  views: SavedView[] | null;
  now: number;
}) {
  const columns: Column<DataRequestRow>[] = [
    {
      key: "kind",
      label: copy.privacy.columns.kind,
      render: (request) => `${labelOf(copy.privacy.kinds, request.kind)} · ${request.id}`,
    },
    {
      key: "requester",
      label: copy.privacy.columns.requester,
      render: (request) => <span className="font-mono text-[14px]">{request.requester}</span>,
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
          start={request.received_at ?? null}
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
        request.status === "closed" ? (
          labelOf(copy.privacy.outcomes, request.outcome)
        ) : (
          <Clock
            label={copy.privacy.dueClock}
            start={request.received_at ?? null}
            due={request.due_at}
            now={now}
            compact
          />
        ),
    },
    {
      key: "status",
      label: copy.privacy.columns.status,
      render: (request) => (
        <StatusChip tone={toneOf(request.status)}>{labelOf(copy.privacy.statuses, request.status)}</StatusChip>
      ),
    },
  ];
  return (
    <DataTable
      listKey="data-requests"
      caption={copy.privacy.requestsTitle}
      rows={rows}
      columns={columns}
      rowId={(request) => String(request.id)}
      rowHref={(request) => `/privacy/requests/${request.id}/`}
      next={next}
      previous={previous}
      views={views}
      filters={[
        {
          name: "status",
          label: copy.privacy.columns.status,
          type: "select",
          options: Object.entries(copy.privacy.statuses).map(([value, label]) => ({ value, label })),
        },
        {
          name: "kind",
          label: copy.privacy.columns.kind,
          type: "select",
          options: KINDS.map((kind) => ({ value: kind, label: copy.privacy.kinds[kind] })),
        },
        {
          name: "overdue",
          label: copy.privacy.overdueFilter,
          type: "select",
          options: Object.entries(copy.privacy.overdueOptions).map(([value, label]) => ({ value, label })),
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
        kind: copy.privacy.columns.kind,
        channel: copy.privacy.channel,
        requester: copy.privacy.requester,
        summary: copy.privacy.summary,
        received_at: copy.privacy.receivedAt,
        user: copy.privacy.userId,
      }}
      onSubmit={(form) =>
        createDataRequest({
          kind: formText(form, "kind") as DataRequest["kind"],
          channel: formText(form, "channel") as DataRequest["channel"],
          requester: formText(form, "requester"),
          summary: formText(form, "summary"),
          received_at: fromLocalInput(formText(form, "received_at")),
          user: formText(form, "user") ? Number(formText(form, "user")) : null,
          notes: formText(form, "notes"),
        })
      }
    >
      {(error) => (
        <>
          <FormGrid>
            <Field id="new-request-kind" label={copy.privacy.columns.kind} error={fieldError(error, "kind")}>
              <Select name="kind" defaultValue="" aria-required="true">
                <option value="">{copy.privacy.columns.kind}</option>
                {KINDS.map((kind) => (
                  <option key={kind} value={kind}>
                    {copy.privacy.kinds[kind]}
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
            <Field id="new-request-requester" label={copy.privacy.requester} error={fieldError(error, "requester")}>
              <Input name="requester" autoComplete="off" aria-required="true" />
            </Field>
            <Field
              id="new-request-user"
              label={copy.privacy.userId}
              optional
              help={copy.privacy.userIdHelp}
              error={fieldError(error, "user")}
            >
              <Input name="user" inputMode="numeric" autoComplete="off" />
            </Field>
          </FormGrid>
          <Field id="new-request-summary" label={copy.privacy.summary} error={fieldError(error, "summary")}>
            <Textarea name="summary" rows={3} aria-required="true" />
          </Field>
          <Field id="new-request-notes" label={copy.privacy.notes} optional help={copy.privacy.notesHelp}>
            <Textarea name="notes" rows={2} />
          </Field>
        </>
      )}
    </ActionForm>
  );
}

/** One step of a request: a button that calls the API, its error beside it, then a fresh render of the page. */
function Step({ label, success, work }: { label: string; success: string; work: () => Promise<unknown> }) {
  const router = useRouter();
  const { run, busy, error } = useAction();
  return (
    <div className="flex flex-col gap-3">
      <ErrorSummary error={error} />
      <div>
        <Button
          busy={busy}
          onClick={() =>
            run(async () => {
              await work();
              toast.success(success);
              router.refresh();
            })
          }
        >
          {label}
        </Button>
      </div>
    </div>
  );
}

export function Acknowledge({ request }: { request: DataRequest }) {
  const can = useCan();
  if (request.acknowledged_at || !can(P.requestsHandle)) return null;
  return (
    <Step
      label={copy.privacy.acknowledge}
      success={copy.privacy.acknowledgedToast}
      work={() => acknowledgeDataRequest(request.id)}
    />
  );
}

export function VerifyIdentity({ request }: { request: DataRequest }) {
  const can = useCan();
  if (request.identity_verified || !can(P.requestsHandle)) return null;
  return (
    <ActionForm
      id={`verify-${request.id}`}
      submitLabel={copy.privacy.verifyButton}
      success={copy.privacy.verified}
      variant="secondary"
      labels={{ note: copy.privacy.verifyNote }}
      onSubmit={(form) => verifyIdentity(request.id, formText(form, "note"))}
    >
      {(error) => (
        <Field
          id={`verify-${request.id}-note`}
          label={copy.privacy.verifyNote}
          help={copy.privacy.verifyNoteHelp}
          error={fieldError(error, "note")}
        >
          <Input name="note" autoComplete="off" aria-required="true" maxLength={300} />
        </Field>
      )}
    </ActionForm>
  );
}

export function RequestNotes({ request }: { request: DataRequest }) {
  const router = useRouter();
  const can = useCan();
  const { ref, save, clear } = useDraftForm(`notes-${request.id}`);
  const { run, busy, error } = useAction();
  if (!can(P.requestsHandle))
    return <p className="m-0 text-[15px] whitespace-pre-wrap">{request.notes || copy.common.none}</p>;
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
          await updateDataRequest(request.id, { notes });
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

/** A line the API wrote in lower case ("kept until 31 March 2035: …"), as the first of a list item. */
const sentence = (line: string) => line.charAt(0).toUpperCase() + line.slice(1);

function ReportView({ report }: { report: ErasureReport }) {
  return (
    <div className="flex flex-col gap-5" aria-live="polite">
      {report.blocks.length ? (
        <div className="flex flex-col gap-2">
          <h3 className="m-0 font-head text-lg">{copy.privacy.blocks}</h3>
          <ul className="m-0 flex list-none flex-col gap-1.5 p-0 text-[15px]">
            {report.blocks.map((block) => (
              <li key={block} className="border-l-2 border-destructive pl-3">
                {block}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <div className="grid gap-6 min-[900px]:grid-cols-2">
        <div className="flex flex-col gap-2">
          <h3 className="m-0 font-head text-lg">{copy.privacy.erase}</h3>
          {report.erase.length ? (
            <ul className="m-0 pl-5 text-[15px]">
              {report.erase.map((row) => (
                <li key={row.part}>
                  {sentence(row.what)} ({copy.privacy.count(row.count)})
                </li>
              ))}
            </ul>
          ) : (
            <p className="m-0 text-[15px] text-muted-foreground">{copy.privacy.nothingErased}</p>
          )}
        </div>
        <div className="flex flex-col gap-2">
          <h3 className="m-0 font-head text-lg">{copy.privacy.keep}</h3>
          {report.keep.length ? (
            <ul className="m-0 flex list-none flex-col gap-2 p-0 text-[15px]">
              {report.keep.map((row) => (
                <li key={row.part} className="border-l-2 border-warning-line pl-3">
                  {sentence(row.line)}
                </li>
              ))}
            </ul>
          ) : (
            <p className="m-0 text-[15px] text-muted-foreground">{copy.privacy.nothingKept}</p>
          )}
        </div>
      </div>
      {report.notes.length ? (
        <ul className="m-0 pl-5 text-sm text-muted-foreground">
          {report.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export function Erasure({ request }: { request: DataRequest }) {
  const can = useCan();
  const { run, busy, error } = useAction();
  const [report, setReport] = useState<ErasureReport | null>(null);
  const [asked, setAsked] = useState<ApiError | null>(null);
  if (request.kind !== "erasure" || !request.user) return null;
  return (
    <div className="flex flex-col gap-4">
      <ErrorSummary error={error} />
      <div className="flex flex-wrap gap-3">
        <Button
          variant="secondary"
          busy={busy}
          onClick={() => run(async () => setReport(await erasureReport(request.id)))}
        >
          {copy.privacy.dryRunButton}
        </Button>
        {can(P.requestsHandle) && request.status !== "closed" ? (
          <ConfirmDialog
            triggerLabel={copy.privacy.eraseButton}
            triggerVariant="destructive"
            title={copy.privacy.eraseTitle}
            text={copy.privacy.eraseText}
            confirmLabel={copy.privacy.eraseButton}
            reason
            onConfirm={async ({ reason }) => {
              try {
                await eraseForRequest(request.id, reason);
              } catch (caught) {
                // 400 with the dry run: what stops it now
                const body = caught instanceof ApiError ? (caught.body as Partial<ErasureReport> | null) : null;
                if (caught instanceof ApiError && caught.status === 400 && Array.isArray(body?.blocks))
                  setReport(body as ErasureReport);
                if (caught instanceof ApiError && caught.code === "approval_required") setAsked(caught);
                throw caught;
              }
            }}
          />
        ) : null}
      </div>
      {asked ? <ApprovalNotice approval={asked.approval} /> : null}
      {report ? <ReportView report={report} /> : null}
    </div>
  );
}

export function ExportData({ request }: { request: DataRequest }) {
  const can = useCan();
  if (request.kind !== "access" || !request.user || !request.identity_verified || !can(P.requestsExport)) return null;
  return (
    <Step label={copy.privacy.exportButton} success={copy.common.done} work={() => exportForRequest(request.id)} />
  );
}

export function ResponseText({ subject, body }: { subject: string; body: string }) {
  return (
    <div className="flex flex-col gap-3">
      <p className="m-0 font-semibold">{subject}</p>
      <p className="m-0 max-w-[68ch] rounded-lg border border-border bg-card p-4 text-[15px] leading-relaxed whitespace-pre-wrap">
        {body}
      </p>
      <div>
        <CopyButton value={`${subject}\n\n${body}`} label={copy.privacy.copyResponse} />
      </div>
    </div>
  );
}

export function CloseRequest({ request, draft }: { request: DataRequest; draft: string }) {
  const can = useCan();
  if (request.status === "closed" || !can(P.requestsHandle)) return null;
  return (
    <ActionForm
      id={`close-${request.id}`}
      submitLabel={copy.privacy.closeButton}
      success={copy.privacy.closed}
      labels={{ outcome: copy.privacy.closeOutcome, response: copy.privacy.closeResponse }}
      onSubmit={(form) =>
        closeDataRequest(request.id, {
          outcome: formText(form, "outcome") as Schemas["DataRequestOutcomeEnum"],
          response: formText(form, "response"),
        })
      }
    >
      {(error) => (
        <>
          <Field
            id={`close-${request.id}-outcome`}
            label={copy.privacy.closeOutcome}
            error={fieldError(error, "outcome")}
          >
            <Select name="outcome" defaultValue="done">
              {Object.entries(copy.privacy.outcomes).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>
          <Field
            id={`close-${request.id}-response`}
            label={copy.privacy.closeResponse}
            error={fieldError(error, "response")}
          >
            <Textarea name="response" rows={6} defaultValue={draft} aria-required="true" />
          </Field>
        </>
      )}
    </ActionForm>
  );
}
