"use client";

// Payment links (GET finance/payment-links/?kind=order|invoice&state=&q=): a staff order's (sent to the customer by
// email, again on request) or a B2B invoice's of ERPNext (its address for staff to send: no contact of a B2B customer
// is kept on the platform). Each row's actions are what the API allows for its state: send again or cancel an order's
// open link (shop.change_order); cancel a B2B link, ask Razorpay about it again (staff.replay_webhook), and record the
// Payment Entry FINANCE posted in ERPNext by hand once paid (staff.reconcile_settlements: ERPNext's contract takes
// only the platform's own invoices). A new link: an order's number or an ERPNext invoice's name (POST payment-links/).
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ConfirmDialog } from "@/components/data/confirm-typed";
import { CopyButton } from "@/components/data/copy-button";
import { type Column, DataTable } from "@/components/data/data-table";
import { StatusChip } from "@/components/data/status-chip";
import { ActionForm, formText } from "@/components/forms/action-form";
import { fieldError, useAction } from "@/components/forms/use-action";
import { useCan } from "@/components/shell/manifest";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { toast } from "@/components/ui/toaster";
import { errorText } from "@/lib/api/errors";
import {
  askPaymentLink,
  type FinanceLink,
  type FinanceLinkAnswer,
  markInvoiceLinkPosted,
  reconcileInvoiceLink,
  type SavedView,
} from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDateTime } from "@/lib/format";
import { P } from "@/lib/modules";

import { inr, toneOfFinance } from "./format";

/** What a person may do with a link now: the API's rules for its state, crossed with the manifest's permissions. */
export function linkActions(link: FinanceLink, can: (permission: string) => boolean) {
  const open = link.state === "sent";
  return {
    send: link.kind === "order" && open && can(P.ordersChange),
    cancel: open && can(P.ordersChange),
    ask: link.kind === "invoice" && open && can(P.reconcile),
    posted: link.kind === "invoice" && link.state === "paid" && !link.posted_at && can(P.reconcileSettlements),
  };
}

const target = (link: FinanceLink) =>
  link.kind === "order" ? { order: link.order ?? "" } : { invoice: link.invoice ?? "" };

export function LinkActions({ link }: { link: FinanceLink }) {
  const router = useRouter();
  const can = useCan();
  const { run, busy, error } = useAction();
  const [pressed, setPressed] = useState<string | null>(null);
  const allowed = linkActions(link, can);
  const name = link.order ?? link.invoice ?? "";
  const act = (key: string, work: () => Promise<unknown>, done: string) => {
    setPressed(key);
    run(async () => {
      await work();
      toast.success(done);
      router.refresh();
    });
  };
  if (!Object.values(allowed).some(Boolean)) return null;
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      {allowed.send ? (
        <Button
          size="sm"
          variant="secondary"
          busy={busy && pressed === "send"}
          onClick={() => act("send", () => askPaymentLink({ ...target(link), action: "send" }), copy.finance.sentAgain)}
        >
          {copy.finance.sendAgain}
          <span className="sr-only">: {name}</span>
        </Button>
      ) : null}
      {allowed.ask ? (
        <Button
          size="sm"
          variant="secondary"
          busy={busy && pressed === "ask"}
          onClick={() => act("ask", () => reconcileInvoiceLink(link.id), copy.finance.asked)}
        >
          {copy.finance.reconcile}
          <span className="sr-only">: {name}</span>
        </Button>
      ) : null}
      {allowed.cancel ? (
        <ConfirmDialog
          triggerLabel={
            <>
              {copy.finance.cancelLink}
              <span className="sr-only">: {name}</span>
            </>
          }
          title={copy.finance.cancelLinkTitle(name)}
          text={copy.finance.cancelLinkText}
          confirmLabel={copy.finance.cancelLink}
          success={copy.finance.linkCancelled}
          onConfirm={() => askPaymentLink({ ...target(link), action: "cancel" })}
        />
      ) : null}
      {allowed.posted ? (
        <ConfirmDialog
          triggerLabel={
            <>
              {copy.finance.markPosted}
              <span className="sr-only">: {name}</span>
            </>
          }
          triggerVariant="primary"
          title={copy.finance.markPostedTitle(name)}
          text={copy.finance.markPostedText}
          confirmLabel={copy.finance.markPosted}
          confirmVariant="primary"
          fields={[{ name: "erp_name", label: copy.finance.erpName, help: copy.finance.erpNameHelp }]}
          success={copy.finance.postedToast}
          onConfirm={({ values }) => markInvoiceLinkPosted(link.id, values.erp_name ?? "")}
        />
      ) : null}
      {error ? <span className="text-sm font-semibold text-destructive">{errorText(error)}</span> : null}
    </span>
  );
}

export function LinksTable({
  rows,
  next,
  previous,
  views,
}: {
  rows: FinanceLink[];
  next: string | null;
  previous: string | null;
  views: SavedView[] | null;
}) {
  const c = copy.finance.linkColumns;
  const columns: Column<FinanceLink>[] = [
    {
      key: "what",
      label: c.what,
      render: (row) => <span className="font-mono">{row.kind === "order" ? row.order : row.invoice}</span>,
    },
    { key: "amount", label: c.amount, render: (row) => inr(row.amount), numeric: true },
    {
      key: "state",
      label: c.state,
      render: (row) => (
        <span className="inline-flex flex-wrap items-center gap-1.5">
          <StatusChip tone={toneOfFinance(row.state)}>{labelOf(copy.finance.linkStates, row.state)}</StatusChip>
          {row.posted_at ? <StatusChip tone="done">{copy.finance.postedChip}</StatusChip> : null}
          {row.is_test ? <StatusChip tone="stopped">{copy.finance.test}</StatusChip> : null}
        </span>
      ),
    },
    { key: "sent", label: c.sent, render: (row) => formatDateTime(row.last_sent_at ?? row.sent_at) },
    { key: "expires", label: c.expires, render: (row) => formatDateTime(row.expires_at) },
    {
      key: "url",
      label: c.url,
      render: (row) =>
        row.url && row.state === "sent" ? (
          <CopyButton value={row.url} label={copy.finance.copyLink} what={row.order ?? row.invoice ?? ""} />
        ) : (
          copy.common.none
        ),
    },
    { key: "paid", label: c.paid, render: (row) => formatDateTime(row.paid_at), hidden: true },
    {
      key: "erp",
      label: c.erp,
      render: (row) => <span className="font-mono text-[14px]">{row.erp_name || copy.common.none}</span>,
      hidden: true,
    },
    { key: "by", label: c.by, render: (row) => row.created_by || copy.common.none, hidden: true },
    { key: "actions", label: c.actions, render: (row) => <LinkActions link={row} /> },
  ];
  return (
    <DataTable
      listKey="finance-links"
      caption={copy.finance.linksTitle}
      rows={rows}
      columns={columns}
      rowId={(row) => `${row.kind}-${row.id}`}
      rowHref={(row) => (row.kind === "order" && row.order ? `/orders/${encodeURIComponent(row.order)}/` : null)}
      next={next}
      previous={previous}
      views={views}
      presets={{
        name: "kind",
        label: copy.finance.linkKinds,
        all: copy.finance.orderLinks,
        options: [{ value: "invoice", label: copy.finance.invoiceLinks }],
      }}
      filters={[
        { name: "q", label: copy.finance.searchLinks, type: "search" },
        {
          name: "state",
          label: c.state,
          type: "select",
          options: Object.entries(copy.finance.linkStates).map(([value, label]) => ({ value, label })),
        },
        {
          name: "livemode",
          label: copy.finance.modeFilter,
          type: "select",
          any: copy.finance.modeOptions.default,
          options: [{ value: "false", label: copy.finance.modeOptions.test }],
        },
      ]}
      empty={{ title: copy.finance.linksEmptyTitle, text: copy.finance.linksEmptyText }}
    />
  );
}

/** A new link (or an order's again): an order's number or an ERPNext invoice's name. The answer's address shows
 *  once made, for staff to send the B2B customer. */
export function NewLinkForm() {
  const [made, setMade] = useState<FinanceLinkAnswer | null>(null);
  const [kind, setKind] = useState<"order" | "invoice">("order");
  return (
    <div className="flex flex-col gap-4">
      <ActionForm
        id="finance-link"
        submitLabel={copy.finance.makeLink}
        success={copy.finance.linkMade}
        labels={{ order: copy.finance.orderNumber, invoice: copy.finance.invoiceName }}
        onSubmit={(form) => {
          const name = formText(form, kind);
          return askPaymentLink(
            kind === "order" ? { order: name, action: "send" } : { invoice: name, action: "send" },
          ).then((answer) => {
            setMade(answer);
            return answer;
          });
        }}
      >
        {(error) => (
          <div className="grid gap-4 min-[640px]:grid-cols-[minmax(10rem,14rem)_minmax(0,1fr)]">
            <Field id="finance-link-kind" label={copy.finance.linkFor}>
              <Select
                name="kind"
                value={kind}
                onChange={(event) => setKind(event.target.value === "invoice" ? "invoice" : "order")}
              >
                <option value="order">{copy.finance.forOrder}</option>
                <option value="invoice">{copy.finance.forInvoice}</option>
              </Select>
            </Field>
            <Field
              key={kind}
              id={`finance-link-${kind}`}
              label={kind === "order" ? copy.finance.orderNumber : copy.finance.invoiceName}
              help={kind === "order" ? copy.finance.orderHelp : copy.finance.invoiceHelp}
              error={fieldError(error, kind)}
            >
              <Input name={kind} autoComplete="off" spellCheck={false} className="font-mono" aria-required="true" />
            </Field>
          </div>
        )}
      </ActionForm>
      {made ? (
        <Alert variant="success" title={made.detail}>
          {made.url ? (
            <p className="flex flex-wrap items-center gap-3">
              <span className="font-mono break-all">{made.url}</span>
              <CopyButton value={made.url} label={copy.finance.copyLink} what={made.order ?? made.invoice ?? ""} />
            </p>
          ) : null}
        </Alert>
      ) : null}
    </div>
  );
}
