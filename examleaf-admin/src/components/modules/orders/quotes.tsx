"use client";

// Quotation requests (GET orders/quotes/): the school, the contact (masked), the copies, the state and the order it
// became; a request opens with its books and the conversion to a staff order (POST orders/quotes/{id}/convert/):
// the address, the email to use, the payment link; once only (the API refuses a second), and above the person's
// discount limit a change request waits instead.
import { useRouter } from "next/navigation";
import { useId } from "react";

import { ApprovalNotice } from "@/components/data/approval-notice";
import { type Column, DataTable } from "@/components/data/data-table";
import { StatusChip } from "@/components/data/status-chip";
import { ErrorSummary } from "@/components/forms/error-summary";
import { fieldError, useAction } from "@/components/forms/use-action";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/choice";
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { toast } from "@/components/ui/toaster";
import { convertQuote, type QuoteDetail, type QuoteRow } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDate } from "@/lib/format";

import { ADDRESS_LABELS, addressOf, AddressFields } from "./address-fields";
import { stateTone } from "./format";

export function QuotesTable({
  rows,
  next,
  previous,
}: {
  rows: QuoteRow[];
  next: string | null;
  previous: string | null;
}) {
  const q = copy.orders.quotes;
  const columns: Column<QuoteRow>[] = [
    { key: "number", label: q.columns.number, render: (row) => <span className="font-mono">{row.number}</span> },
    { key: "school", label: q.columns.school, wrap: true, render: (row) => row.school },
    {
      key: "contact",
      label: q.columns.contact,
      render: (row) => (
        <span className="flex flex-col">
          <span>{row.contact_name}</span>
          <span className="font-mono text-[13px] text-muted-foreground">{row.email}</span>
        </span>
      ),
    },
    { key: "copies", label: q.columns.copies, numeric: true, render: (row) => row.copies },
    {
      key: "status",
      label: q.columns.status,
      render: (row) => <StatusChip tone={stateTone(row.status)}>{labelOf(q.statuses, row.status)}</StatusChip>,
    },
    {
      key: "valid",
      label: q.columns.valid,
      render: (row) => (row.valid_until ? formatDate(row.valid_until) : copy.common.none),
    },
    {
      key: "order",
      label: q.columns.order,
      render: (row) => (row.order ? <span className="font-mono">{row.order}</span> : copy.common.none),
    },
  ];
  return (
    <DataTable
      listKey="order-quotes"
      caption={q.title}
      rows={rows}
      columns={columns}
      rowId={(row) => String(row.id)}
      rowHref={(row) => `/orders/quotes/${row.id}/`}
      next={next}
      previous={previous}
      filters={[
        {
          name: "status",
          label: q.columns.status,
          type: "select",
          options: Object.entries(q.statuses).map(([value, label]) => ({ value, label })),
        },
      ]}
      empty={{ title: q.emptyTitle, text: q.emptyText }}
    />
  );
}

export function QuoteConvert({ quote }: { quote: QuoteDetail }) {
  const id = useId();
  const router = useRouter();
  const q = copy.orders.quotes;
  const { run, busy, error } = useAction();
  if (error?.code === "approval_required") return <ApprovalNotice approval={error.approval} />;
  return (
    <form
      noValidate
      className="flex max-w-[44rem] flex-col gap-4"
      onSubmit={async (event) => {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        const text = (name: string) => String(form.get(name) ?? "").trim();
        await run(async () => {
          const answer = await convertQuote(quote.id, {
            address: addressOf(form),
            ...(text("email") ? { email: text("email") } : {}),
            send_link: form.get("send_link") === "on",
            note: text("note"),
            reason: text("reason") || q.convertReason,
          });
          const result = (answer.result ?? {}) as { order?: string };
          toast.success(q.converted);
          if (result.order) router.push(`/orders/${encodeURIComponent(result.order)}/`);
          else router.refresh();
        });
      }}
    >
      <p className="m-0 text-[15px] text-muted-foreground">{q.convertText}</p>
      <ErrorSummary
        error={error}
        idPrefix={`${id}-`}
        labels={{ ...ADDRESS_LABELS, email: copy.orders.create.email, reason: copy.common.reason }}
      />
      <AddressFields prefix={`${id}-`} error={error} />
      <Field
        id={`${id}-email`}
        label={copy.orders.create.email}
        optional
        help={copy.orders.create.emailHelp}
        error={fieldError(error, "email")}
      >
        <Input name="email" type="email" autoComplete="off" placeholder={quote.email} />
      </Field>
      <Checkbox name="send_link" defaultChecked>
        {copy.orders.create.sendLink}
      </Checkbox>
      <Field id={`${id}-note`} label={copy.orders.create.note} error={fieldError(error, "note")}>
        <Textarea name="note" rows={2} />
      </Field>
      <Field id={`${id}-reason`} label={copy.common.reason} optional error={fieldError(error, "reason")}>
        <Textarea name="reason" rows={2} />
      </Field>
      <div>
        <Button type="submit" busy={busy}>
          {q.convertSubmit}
        </Button>
      </div>
    </form>
  );
}

/** The quote's books as the request listed them (the schema gives them as JSON objects). */
export function QuoteItems({ quote }: { quote: QuoteDetail }) {
  const items = quote.items.map((item) => ({
    title: typeof item.title === "string" ? item.title : String(item.product ?? ""),
    quantity: Number(item.quantity) || 0,
  }));
  return (
    <ul className="m-0 flex list-none flex-col gap-1 p-0 text-[15px]">
      {items.map((item, index) => (
        <li key={`${item.title}-${index}`}>
          {item.title} <span className="font-mono text-muted-foreground">× {item.quantity}</span>
        </li>
      ))}
    </ul>
  );
}
