"use client";

// Change requests as a list (GET change-requests/?status=&awaiting=&mine=): what would change, on which record, for
// how much, who asked and when it expires. Pending by default. Below the list, asking for a refund (POST
// change-requests/ with order.refund): within the person's limit it runs at once, above it a change request waits.
import { type Column, DataTable } from "@/components/data/data-table";
import { StatusChip, toneOf } from "@/components/data/status-chip";
import { ActionForm, formText } from "@/components/forms/action-form";
import { fieldError } from "@/components/forms/use-action";
import { staffLabel } from "@/lib/display";
import { useManifest } from "@/components/shell/manifest";
import { Field, FormGrid } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { askChange, type ChangeRequest, type SavedView } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDateTime, formatInr } from "@/lib/format";

export function ApprovalsTable({
  rows,
  next,
  previous,
  views,
}: {
  rows: ChangeRequest[];
  next: string | null;
  previous: string | null;
  views: SavedView[] | null;
}) {
  const manifest = useManifest();
  const columns: Column<ChangeRequest>[] = [
    {
      key: "action",
      label: copy.approvals.columns.action,
      render: (request) => (
        <span className="flex flex-col">
          <span>{request.label}</span>
          <code className="text-[13px] font-normal break-all">{request.action}</code>
        </span>
      ),
    },
    {
      key: "target",
      wrap: true,
      label: copy.approvals.columns.target,
      render: (request) => request.target_label || request.target_id || copy.common.none,
    },
    {
      key: "amount",
      label: copy.approvals.columns.amount,
      render: (request) => (request.amount ? formatInr(Number(request.amount)) : ""),
      numeric: true,
    },
    {
      key: "maker",
      label: copy.approvals.columns.maker,
      render: (request) => staffLabel(request.maker, manifest.user.id),
    },
    {
      key: "expires",
      label: copy.approvals.columns.expires,
      render: (request) => formatDateTime(request.expires_at),
    },
    {
      key: "state",
      label: copy.approvals.columns.state,
      render: (request) => (
        <StatusChip tone={toneOf(request.status ?? "pending")}>
          {labelOf(copy.approvals.states, request.status)}
        </StatusChip>
      ),
    },
  ];
  return (
    <DataTable
      listKey="approvals"
      caption={copy.approvals.title}
      rows={rows}
      columns={columns}
      rowId={(request) => String(request.id)}
      rowHref={(request) => `/approvals/${request.id}/`}
      next={next}
      previous={previous}
      views={views}
      filters={[
        {
          name: "status",
          label: copy.approvals.columns.state,
          type: "select",
          options: [
            ...["approved", "rejected", "executed", "expired", "failed"].map((state) => ({
              value: state,
              label: copy.approvals.states[state],
            })),
            { value: "all", label: copy.common.all },
          ],
          any: copy.approvals.states.pending,
        },
        {
          name: "who",
          label: copy.approvals.columns.maker,
          type: "select",
          options: [
            { value: "awaiting", label: copy.approvals.awaiting },
            { value: "mine", label: copy.approvals.mine },
          ],
          any: copy.common.anyone,
        },
      ]}
      empty={{ title: copy.approvals.emptyTitle, text: copy.approvals.emptyText }}
    />
  );
}

export function AskRefundForm() {
  return (
    <ActionForm
      id="ask-refund"
      submitLabel={copy.approvals.askButton}
      success={copy.approvals.asked}
      labels={{ target: copy.approvals.askOrder, amount: copy.approvals.askAmount, reason: copy.common.reason }}
      onSubmit={(form) =>
        askChange({
          action: "order.refund",
          target: formText(form, "target"),
          payload: formText(form, "amount") ? { amount: formText(form, "amount") } : {},
          reason: formText(form, "reason"),
        })
      }
    >
      {(error) => (
        <>
          <FormGrid>
            <Field id="ask-refund-target" label={copy.approvals.askOrder} error={fieldError(error, "target")}>
              <Input name="target" autoComplete="off" aria-required="true" className="font-mono" />
            </Field>
            <Field
              id="ask-refund-amount"
              label={copy.approvals.askAmount}
              optional
              help={copy.approvals.askAmountHelp}
              error={fieldError(error, "amount")}
            >
              <Input name="amount" inputMode="decimal" autoComplete="off" />
            </Field>
          </FormGrid>
          <Field
            id="ask-refund-reason"
            label={copy.common.reason}
            help={copy.common.reasonHelp}
            error={fieldError(error, "reason")}
          >
            <Textarea name="reason" rows={2} aria-required="true" />
          </Field>
        </>
      )}
    </ActionForm>
  );
}
