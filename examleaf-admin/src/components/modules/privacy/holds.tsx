"use client";

// Legal holds (GET privacy/holds/?active=&reason=&target_type=&user=): each keeps an account or one record (an order,
// an invoice, a credit note, a payment, a refund, a data request) from the erasure and the retention clean-up until
// its day or its release. Below the list a hold is added on an account (its number) or a record (its kind and number:
// the API finds it, 400 "No such record." otherwise); on a hold's page it is released with a reason.
import { useState } from "react";

import { ConfirmDialog } from "@/components/data/confirm-typed";
import { type Column, DataTable } from "@/components/data/data-table";
import { StatusChip } from "@/components/data/status-chip";
import { ActionForm, formText } from "@/components/forms/action-form";
import { fieldError } from "@/components/forms/use-action";
import { useCan } from "@/components/shell/manifest";
import { Field, FormGrid } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import {
  createHold,
  type HoldReason,
  type HoldTarget,
  type LegalHold,
  releaseHold,
  type SavedView,
} from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { heldLabel, holdState } from "@/lib/display";
import { formatDate, formatDateTime } from "@/lib/format";
import { P } from "@/lib/modules";

const REASONS = Object.keys(copy.legal.holdReasons) as HoldReason[];
const TARGETS = Object.keys(copy.legal.targets);

export function HoldsTable({
  rows,
  next,
  previous,
  views,
}: {
  rows: LegalHold[];
  next: string | null;
  previous: string | null;
  views: SavedView[] | null;
}) {
  const columns: Column<LegalHold>[] = [
    {
      key: "hold",
      label: copy.legal.holdColumns.hold,
      render: (hold) => `${copy.legal.holdNumber(hold.id)} · ${heldLabel(hold)}`,
    },
    {
      key: "reason",
      label: copy.legal.holdColumns.reason,
      render: (hold) => labelOf(copy.legal.holdReasons, hold.reason),
    },
    {
      key: "until",
      label: copy.legal.holdColumns.until,
      render: (hold) => (hold.until ? formatDate(hold.until) : copy.legal.untilReleased),
    },
    { key: "made", label: copy.legal.holdColumns.made, render: (hold) => formatDateTime(hold.created) },
    {
      key: "state",
      label: copy.legal.holdColumns.state,
      render: (hold) => {
        const state = holdState(hold);
        return (
          <StatusChip tone={state === "active" ? "waiting" : "stopped"}>
            {labelOf(copy.legal.holdStates, state)}
          </StatusChip>
        );
      },
    },
  ];
  return (
    <DataTable
      listKey="legal-holds"
      caption={copy.legal.holdsTitle}
      rows={rows}
      columns={columns}
      rowId={(hold) => String(hold.id)}
      rowHref={(hold) => `/privacy/holds/${hold.id}/`}
      next={next}
      previous={previous}
      views={views}
      filters={[
        {
          name: "active",
          label: copy.legal.activeFilter,
          type: "select",
          options: Object.entries(copy.legal.activeOptions).map(([value, label]) => ({ value, label })),
        },
        {
          name: "reason",
          label: copy.legal.holdColumns.reason,
          type: "select",
          options: REASONS.map((reason) => ({ value: reason, label: copy.legal.holdReasons[reason] })),
        },
        {
          name: "target_type",
          label: copy.legal.targetFilter,
          type: "select",
          options: TARGETS.filter(Boolean).map((value) => ({ value, label: copy.legal.targets[value] })),
        },
        { name: "user", label: copy.legal.userFilter, type: "text" },
      ]}
      empty={{ title: copy.legal.holdsEmptyTitle, text: copy.legal.holdsEmptyText }}
    />
  );
}

/** A new hold: on an account (`user`) or one record (`target_type` and its number, `target_id`). */
export function NewHoldForm({ today }: { today: string }) {
  const [kind, setKind] = useState("");
  const number = kind ? "target_id" : "user";
  return (
    <ActionForm
      id="new-hold"
      submitLabel={copy.legal.holdCreate}
      success={copy.legal.holdCreated}
      labels={{
        target_type: copy.legal.holdKind,
        user: copy.legal.holdUser,
        target_id: copy.legal.holdTarget,
        reason: copy.legal.holdReason,
        note: copy.legal.holdNote,
        until: copy.legal.holdUntil,
      }}
      onDone={() => setKind("")}
      onSubmit={(form) => {
        const given = formText(form, number);
        const target = kind
          ? { target_type: kind as HoldTarget, target_id: given }
          : { user: /^\d+$/.test(given) ? Number(given) : null };
        return createHold({
          ...target,
          reason: formText(form, "reason") as HoldReason,
          note: formText(form, "note"),
          until: formText(form, "until") || null,
        });
      }}
    >
      {(error) => (
        <>
          <FormGrid>
            <Field id="new-hold-target_type" label={copy.legal.holdKind} error={fieldError(error, "target_type")}>
              <Select
                name="target_type"
                value={kind}
                onChange={(event) => setKind(event.target.value)}
                data-no-draft=""
              >
                {TARGETS.map((value) => (
                  <option key={value} value={value}>
                    {copy.legal.targets[value]}
                  </option>
                ))}
              </Select>
            </Field>
            <Field
              key={number}
              id={`new-hold-${number}`}
              label={kind ? copy.legal.holdTarget : copy.legal.holdUser}
              help={kind ? copy.legal.holdTargetHelp : copy.legal.holdUserHelp}
              error={fieldError(error, number) ?? fieldError(error, kind ? "user" : "target_id")}
            >
              <Input name={number} autoComplete="off" aria-required="true" inputMode={kind ? "text" : "numeric"} />
            </Field>
          </FormGrid>
          <FormGrid>
            <Field id="new-hold-reason" label={copy.legal.holdReason} error={fieldError(error, "reason")}>
              <Select name="reason" defaultValue="dispute">
                {REASONS.map((reason) => (
                  <option key={reason} value={reason}>
                    {copy.legal.holdReasons[reason]}
                  </option>
                ))}
              </Select>
            </Field>
            <Field
              id="new-hold-until"
              label={copy.legal.holdUntil}
              optional
              help={copy.legal.holdUntilHelp}
              error={fieldError(error, "until")}
            >
              <Input name="until" type="date" min={today} />
            </Field>
          </FormGrid>
          <Field
            id="new-hold-note"
            label={copy.legal.holdNote}
            optional
            help={copy.legal.holdNoteHelp}
            error={fieldError(error, "note")}
          >
            <Textarea name="note" rows={3} maxLength={2000} />
          </Field>
        </>
      )}
    </ActionForm>
  );
}

export function ReleaseHold({ hold }: { hold: LegalHold }) {
  const can = useCan();
  if (!hold.active || !can(P.holdsManage)) return null;
  return (
    <ConfirmDialog
      triggerLabel={copy.legal.release}
      triggerVariant="destructive"
      title={copy.legal.releaseTitle}
      text={copy.legal.releaseText}
      confirmLabel={copy.legal.release}
      reason
      success={copy.legal.released}
      onConfirm={({ reason }) => releaseHold(hold.id, reason)}
    />
  );
}
