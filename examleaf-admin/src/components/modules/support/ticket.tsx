"use client";

// A ticket's parts that act, each drawn when the manifest allows it and each the API's to decide: take it, the
// requester's email address or mobile number revealed with a reason (logged), the status with only the fields its
// category asks for at closing (the API's `closing_fields`, its moves from `transitions`), reopening, who handles it,
// the acknowledgement sent again or recorded as given another way, and sorting or correcting its details.
import { useRouter } from "next/navigation";
import { useState } from "react";

import { MaskedValue } from "@/components/data/masked-value";
import { ActionForm, formText } from "@/components/forms/action-form";
import { ErrorSummary } from "@/components/forms/error-summary";
import { fieldError, useAction } from "@/components/forms/use-action";
import { useCan } from "@/components/shell/manifest";
import { Button } from "@/components/ui/button";
import { Field, FormGrid } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { toast } from "@/components/ui/toaster";
import {
  type Agent,
  acknowledgeTicket,
  assignTicket,
  changeTicket,
  claimTicket,
  reopenTicket,
  revealRequester,
  type Schemas,
  setTicketStatus,
  type TicketRecord,
  type TicketStatus,
} from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { P } from "@/lib/modules";

import { statusLabel } from "./shared";

const DONE = new Set(["resolved", "closed"]);
const options = (table: Record<string, string>) => Object.entries(table).map(([value, label]) => ({ value, label }));

/** One request from a button: busy, its toast, a fresh render; its error beside it. */
function ActionButton({
  label,
  success,
  work,
  variant = "secondary",
}: {
  label: string;
  success: string;
  work: () => Promise<unknown>;
  variant?: "primary" | "secondary";
}) {
  const router = useRouter();
  const { run, busy, error } = useAction();
  return (
    <div className="flex flex-col gap-2">
      <ErrorSummary error={error} />
      <div>
        <Button
          variant={variant}
          size="sm"
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

export function ClaimButton({ number }: { number: string }) {
  return <ActionButton label={copy.support.take} success={copy.support.taken} work={() => claimTicket(number)} />;
}

/** The requester's address or number, masked; Reveal (with a reason) for whoever may reveal contact details. */
export function RequesterValue({
  number,
  field,
  masked,
}: {
  number: string;
  field: "email" | "phone";
  masked: string;
}) {
  const can = useCan();
  return (
    <MaskedValue
      masked={masked || null}
      what={field === "email" ? copy.masked.email : copy.masked.phone}
      reveal={can(P.usersReveal) ? (reason) => revealRequester(number, field, reason) : undefined}
    />
  );
}

export function StatusForm({ ticket }: { ticket: TicketRecord }) {
  const [next, setNext] = useState("");
  const closing = DONE.has(next);
  const asks = (name: string) => closing && ticket.closing_fields.includes(name);
  const id = `status-${ticket.id}`;
  return (
    <div className="flex flex-col gap-4">
      {ticket.transitions.length ? (
        <ActionForm
          id={id}
          submitLabel={copy.support.changeStatus}
          success={copy.support.statusChanged}
          labels={{
            status: copy.support.newStatus,
            resolution: copy.support.resolutionText,
            order: copy.support.orderNumber,
            record: copy.support.paperCode,
            category: copy.support.category,
            data_request: copy.support.dataRequest,
          }}
          onSubmit={(form) =>
            setTicketStatus(ticket.number, {
              status: formText(form, "status") as TicketStatus,
              resolution: formText(form, "resolution"),
              order: formText(form, "order"),
              record: formText(form, "record"),
            })
          }
          onDone={() => setNext("")}
        >
          {(error) => (
            <>
              <Field id={`${id}-status`} label={copy.support.newStatus} error={fieldError(error, "status")}>
                <Select
                  name="status"
                  value={next}
                  data-no-draft=""
                  aria-required="true"
                  onChange={(event) => setNext(event.currentTarget.value)}
                >
                  <option value="">{copy.support.chooseStatus}</option>
                  {ticket.transitions.map((status) => (
                    <option key={status} value={status}>
                      {statusLabel(status)}
                    </option>
                  ))}
                </Select>
              </Field>
              {asks("category") && !ticket.category ? (
                <p className="m-0 text-[15px] font-semibold text-destructive">{copy.support.sortFirst}</p>
              ) : null}
              {asks("data_request") && !ticket.data_request ? (
                <p className="m-0 text-[15px] font-semibold text-destructive">{copy.support.dataRequestFirst}</p>
              ) : null}
              {asks("resolution") ? (
                <Field
                  id={`${id}-resolution`}
                  label={copy.support.resolutionText}
                  help={copy.support.resolutionHelp}
                  error={fieldError(error, "resolution")}
                >
                  <Textarea name="resolution" rows={3} defaultValue={ticket.resolution} aria-required="true" />
                </Field>
              ) : null}
              {asks("order") && !ticket.order ? (
                <Field
                  id={`${id}-order`}
                  label={copy.support.orderNumber}
                  help={copy.support.orderHelp}
                  error={fieldError(error, "order")}
                >
                  <Input name="order" autoComplete="off" className="font-mono" aria-required="true" />
                </Field>
              ) : null}
              {asks("record") && !ticket.record ? (
                <Field
                  id={`${id}-record`}
                  label={copy.support.paperCode}
                  help={copy.support.paperHelp}
                  error={fieldError(error, "record")}
                >
                  <Input name="record" autoComplete="off" className="font-mono" aria-required="true" />
                </Field>
              ) : null}
            </>
          )}
        </ActionForm>
      ) : ticket.status === "closed" ? (
        <p className="m-0 text-[15px] text-muted-foreground">{copy.support.noMoves}</p>
      ) : null}
      {DONE.has(ticket.status) ? (
        <div className="flex flex-col gap-2">
          <p className="m-0 text-[15px] text-muted-foreground">{copy.support.reopenText}</p>
          <ActionButton
            label={copy.support.reopen}
            success={copy.support.reopenedToast}
            work={() => reopenTicket(ticket.number)}
          />
        </div>
      ) : null}
    </div>
  );
}

export function AssignForm({ ticket, agents }: { ticket: TicketRecord; agents: Agent[] | null }) {
  const handlers = (agents ?? []).filter((agent) => agent.handles || agent.id === ticket.assignee);
  const id = `assign-${ticket.id}`;
  return (
    <ActionForm
      id={id}
      submitLabel={copy.support.assign}
      success={copy.support.assigned}
      variant="secondary"
      labels={{ assignee: copy.support.assignTo }}
      onSubmit={(form) =>
        assignTicket(ticket.number, formText(form, "assignee") ? Number(formText(form, "assignee")) : null)
      }
    >
      {(error) => (
        <Field id={`${id}-assignee`} label={copy.support.assignTo} error={fieldError(error, "assignee")}>
          <Select name="assignee" defaultValue={ticket.assignee ? String(ticket.assignee) : ""} data-no-draft="">
            <option value="">{copy.support.nobody}</option>
            {handlers.map((agent) => (
              <option key={agent.id} value={agent.id}>
                {agent.name}
              </option>
            ))}
          </Select>
        </Field>
      )}
    </ActionForm>
  );
}

export function Acknowledgement({ ticket }: { ticket: TicketRecord }) {
  const id = `ack-${ticket.id}`;
  return (
    <div className="flex flex-col gap-5">
      {ticket.ack_held ? <p className="m-0 text-[15px]">{copy.support.ackHeld}</p> : null}
      <ActionButton
        label={ticket.acknowledged_at ? copy.support.sendAckAgain : copy.support.sendAck}
        success={copy.support.ackSent}
        work={() => acknowledgeTicket(ticket.number)}
      />
      {!ticket.acknowledged_at ? (
        <ActionForm
          id={id}
          submitLabel={copy.support.ackRecord}
          success={copy.support.ackRecorded}
          variant="secondary"
          labels={{ note: copy.support.ackHow }}
          onSubmit={(form) => acknowledgeTicket(ticket.number, formText(form, "note"))}
        >
          {(error) => (
            <Field
              id={`${id}-note`}
              label={copy.support.ackOtherWay}
              help={copy.support.ackHowHelp}
              error={fieldError(error, "note")}
            >
              <Input name="note" autoComplete="off" maxLength={300} aria-required="true" />
            </Field>
          )}
        </ActionForm>
      ) : null}
    </div>
  );
}

type Change = Schemas["PatchedTicketChangeRequest"];

/** The form's values that differ from the ticket's (the contact details only when typed: they are masked here). */
export function changedDetails(ticket: TicketRecord, form: FormData): Change {
  const text = (name: string) => formText(form, name);
  const now: Record<string, string> = {
    category: ticket.category ?? "",
    priority: ticket.priority,
    language: ticket.language,
    source: ticket.source,
    nch_docket: ticket.nch_docket,
    subject: ticket.subject,
    name: ticket.requester.name,
    order: ticket.order ?? "",
    record: ticket.record ?? "",
  };
  const change: Record<string, string> = {};
  for (const [name, before] of Object.entries(now))
    if (form.has(name) && text(name) !== before) change[name] = text(name);
  for (const name of ["email", "phone"]) if (text(name)) change[name] = text(name);
  return change as Change;
}

export function DetailsForm({ ticket }: { ticket: TicketRecord }) {
  const id = `details-${ticket.id}`;
  return (
    <ActionForm
      id={id}
      submitLabel={copy.support.saveDetails}
      success={copy.support.detailsSaved}
      variant="secondary"
      className="flex max-w-[48rem] flex-col gap-4"
      labels={{
        category: copy.support.category,
        priority: copy.support.priority,
        language: copy.support.language,
        source: copy.support.source,
        nch_docket: copy.support.docket,
        subject: copy.support.subject,
        name: copy.support.name,
        email: copy.support.email,
        phone: copy.support.phone,
        order: copy.support.orderNumber,
        record: copy.support.paperCode,
      }}
      onSubmit={(form) => changeTicket(ticket.number, changedDetails(ticket, form))}
    >
      {(error) => (
        <>
          <FormGrid>
            <Field id={`${id}-category`} label={copy.support.category} error={fieldError(error, "category")}>
              <Select name="category" defaultValue={ticket.category ?? ""}>
                <option value="">{copy.support.notSorted}</option>
                {options(copy.support.categories).map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field id={`${id}-priority`} label={copy.support.priority} error={fieldError(error, "priority")}>
              <Select name="priority" defaultValue={ticket.priority}>
                {options(copy.support.priorities).map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field id={`${id}-language`} label={copy.support.language} error={fieldError(error, "language")}>
              <Select name="language" defaultValue={ticket.language}>
                {options(copy.support.languages).map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Select>
            </Field>
          </FormGrid>
          <FormGrid>
            <Field id={`${id}-source`} label={copy.support.source} error={fieldError(error, "source")}>
              <Select name="source" defaultValue={ticket.source}>
                {options(copy.support.sources).map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field id={`${id}-nch_docket`} label={copy.support.docket} optional error={fieldError(error, "nch_docket")}>
              <Input name="nch_docket" defaultValue={ticket.nch_docket} autoComplete="off" className="font-mono" />
            </Field>
          </FormGrid>
          <Field id={`${id}-subject`} label={copy.support.subject} error={fieldError(error, "subject")}>
            <Input name="subject" defaultValue={ticket.subject} autoComplete="off" maxLength={200} />
          </Field>
          <FormGrid>
            <Field id={`${id}-order`} label={copy.support.orderNumber} optional error={fieldError(error, "order")}>
              <Input name="order" defaultValue={ticket.order ?? ""} autoComplete="off" className="font-mono" />
            </Field>
            <Field id={`${id}-record`} label={copy.support.paperCode} optional error={fieldError(error, "record")}>
              <Input name="record" defaultValue={ticket.record ?? ""} autoComplete="off" className="font-mono" />
            </Field>
          </FormGrid>
          <FormGrid>
            <Field id={`${id}-name`} label={copy.support.name} optional error={fieldError(error, "name")}>
              <Input name="name" defaultValue={ticket.requester.name} autoComplete="off" maxLength={120} />
            </Field>
            <Field
              id={`${id}-email`}
              label={copy.support.email}
              optional
              help={copy.support.keepContact}
              error={fieldError(error, "email")}
            >
              <Input name="email" type="email" autoComplete="off" data-no-draft="" />
            </Field>
            <Field
              id={`${id}-phone`}
              label={copy.support.phone}
              optional
              help={copy.support.keepContact}
              error={fieldError(error, "phone")}
            >
              <Input name="phone" type="tel" autoComplete="off" data-no-draft="" />
            </Field>
          </FormGrid>
        </>
      )}
    </ActionForm>
  );
}
