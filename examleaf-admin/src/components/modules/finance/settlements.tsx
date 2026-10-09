"use client";

// Razorpay's settlements (GET finance/settlements/?state=&date_from=&date_to=&q=), newest day first, each opening its
// own page with its lines (GET finance/settlements/{id}/lines/?matched=&type=). FINANCE (staff.reconcile_settlements)
// fetches a day as a background job (POST finance/settlements/fetch/, a dry run first if they like: JobProgress, its
// result the counts) and matches a line Razorpay's ids did not by hand (POST finance/settlements/{id}/match/: a
// payment, a refund, or an adjustment accepted, always with a note). The backend matches, evaluates and posts.
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ConfirmDialog } from "@/components/data/confirm-typed";
import { type Column, DataTable } from "@/components/data/data-table";
import { JobProgress } from "@/components/data/job-progress";
import { StatusChip } from "@/components/data/status-chip";
import { ErrorSummary } from "@/components/forms/error-summary";
import { fieldError, useAction } from "@/components/forms/use-action";
import { useCan } from "@/components/shell/manifest";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { toast } from "@/components/ui/toaster";
import { ApiError } from "@/lib/api/errors";
import {
  fetchSettlements,
  FINAL_JOB_STATES,
  type FinanceSettlement,
  type FinanceSettlementLine,
  type Job,
  matchSettlementLine,
  type SavedView,
} from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDate, formatDateTime } from "@/lib/format";
import { P } from "@/lib/modules";

import { inr, toneOfFinance } from "./format";

const words = copy.finance.settlements;

export function SettlementState({ settlement }: { settlement: Pick<FinanceSettlement, "state" | "is_test"> }) {
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      <StatusChip tone={toneOfFinance(settlement.state)}>{labelOf(words.states, settlement.state)}</StatusChip>
      {settlement.is_test ? <StatusChip tone="stopped">{copy.finance.test}</StatusChip> : null}
    </span>
  );
}

export function SettlementsTable({
  rows,
  next,
  previous,
  views,
}: {
  rows: FinanceSettlement[];
  next: string | null;
  previous: string | null;
  views: SavedView[] | null;
}) {
  const c = words.columns;
  const columns: Column<FinanceSettlement>[] = [
    { key: "id", label: c.id, render: (row) => <span className="font-mono text-[14px]">{row.settlement_id}</span> },
    { key: "date", label: c.date, render: (row) => formatDate(row.date) },
    {
      key: "utr",
      label: c.utr,
      render: (row) => <span className="font-mono text-[14px]">{row.utr || copy.common.none}</span>,
    },
    { key: "gross", label: c.gross, render: (row) => inr(row.gross), numeric: true },
    { key: "fees", label: c.fees, render: (row) => inr(row.fees), numeric: true },
    { key: "tax", label: c.tax, render: (row) => inr(row.tax), numeric: true, hidden: true },
    { key: "adjustments", label: c.adjustments, render: (row) => inr(row.adjustments), numeric: true, hidden: true },
    { key: "net", label: c.net, render: (row) => inr(row.net), numeric: true },
    { key: "state", label: c.state, render: (row) => <SettlementState settlement={row} /> },
    { key: "posted", label: c.posted, render: (row) => formatDateTime(row.posted_at), hidden: true },
    { key: "problem", label: c.problem, render: (row) => row.problem || copy.common.none, wrap: true, hidden: true },
  ];
  return (
    <DataTable
      listKey="finance-settlements"
      caption={words.title}
      rows={rows}
      columns={columns}
      rowId={(row) => String(row.id)}
      rowHref={(row) => `/finance/settlements/${row.id}/`}
      next={next}
      previous={previous}
      views={views}
      presets={{
        name: "state",
        label: words.which,
        all: words.all,
        options: Object.entries(words.states).map(([value, label]) => ({ value, label })),
      }}
      filters={[
        { name: "q", label: words.search, type: "search" },
        { name: "date_from", label: copy.finance.from, type: "date" },
        { name: "date_to", label: copy.finance.to, type: "date" },
        {
          name: "livemode",
          label: copy.finance.modeFilter,
          type: "select",
          any: copy.finance.modeOptions.default,
          options: [{ value: "false", label: copy.finance.modeOptions.test }],
        },
      ]}
      empty={{ title: words.emptyTitle, text: words.emptyText }}
    />
  );
}

type Fetched = {
  day?: string;
  mode?: string;
  dry_run?: boolean;
  settlements?: number;
  new_settlements?: number;
  lines?: number;
  new_lines?: number;
  matched_lines?: number;
  orders_paid_now?: number;
  states?: Record<string, number>;
};

/** What a fetch found: the job's result, as the backend counted it. */
export function FetchResult({ job }: { job: Pick<Job, "result" | "dry_run"> }) {
  const result = (job.result ?? {}) as Fetched;
  const counts: [string, number][] = [
    [words.counts.settlements, result.settlements ?? 0],
    [words.counts.newSettlements, result.new_settlements ?? 0],
    [words.counts.lines, result.lines ?? 0],
    [words.counts.matchedLines, result.matched_lines ?? 0],
    [words.counts.ordersPaid, result.orders_paid_now ?? 0],
  ];
  const states = Object.entries(result.states ?? {});
  return (
    <div className="flex flex-col gap-3">
      {job.dry_run ? <p className="m-0 text-[15px] text-muted-foreground">{words.dryRunKept}</p> : null}
      <dl className="m-0 grid grid-cols-[repeat(auto-fit,minmax(9rem,1fr))] gap-3">
        {counts.map(([label, count]) => (
          <div key={label} className="flex flex-col gap-0.5 rounded-lg border border-border bg-card px-3 py-2">
            <dt className="text-sm text-muted-foreground">{label}</dt>
            <dd className="m-0 font-mono text-xl">{count.toLocaleString("en-IN")}</dd>
          </div>
        ))}
      </dl>
      {states.length ? (
        <p className="m-0 text-[15px]">
          {states.map(([state, count]) => `${labelOf(words.states, state)}: ${count}`).join(" · ")}
        </p>
      ) : null}
    </div>
  );
}

/** A day of Razorpay's settlements fetched as a job (yesterday by default: Razorpay settles the day after). */
export function FetchForm({ yesterday, today }: { yesterday: string; today: string }) {
  const router = useRouter();
  const { run, busy, error } = useAction();
  const [job, setJob] = useState<Job | null>(null);
  const [done, setDone] = useState<Job | null>(null);
  const finished = (over: Job | null) => {
    setDone(over);
    if (over?.state === "done" && !over.dry_run) {
      toast.success(words.fetched);
      router.refresh();
    }
  };
  return (
    <div className="flex max-w-[48rem] flex-col gap-5">
      <ErrorSummary error={error} labels={{ day: words.day }} idPrefix="fetch-" />
      <form
        noValidate
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          const form = new FormData(event.currentTarget);
          run(async () => {
            setDone(null);
            const started = await fetchSettlements({
              day: String(form.get("day") ?? ""),
              dry_run: form.get("dry_run") === "on",
            });
            setJob(started);
            if (FINAL_JOB_STATES.has(started.state)) finished(started);
          });
        }}
      >
        <Field id="fetch-day" label={words.day} help={words.dayHelp} error={fieldError(error, "day")}>
          <Input name="day" type="date" defaultValue={yesterday} max={today} aria-required="true" className="w-auto" />
        </Field>
        <label className="flex min-h-11 cursor-pointer items-center gap-3 text-[15px]">
          <input type="checkbox" data-slot="checkbox" name="dry_run" />
          {words.dryRun}
        </label>
        <div>
          <Button type="submit" busy={busy}>
            {words.fetch}
          </Button>
        </div>
      </form>
      {job ? (
        <section aria-labelledby="fetch-job-title" className="flex flex-col gap-3">
          <h3 id="fetch-job-title" className="m-0 text-[15px] font-semibold">
            {words.fetching}
          </h3>
          <JobProgress key={job.id} job={job} onDone={finished} />
          {done?.state === "done" ? <FetchResult job={done} /> : null}
        </section>
      ) : null}
    </div>
  );
}

/** A payment's or a refund's number as typed ("#123" or "123"), or the field's error. */
export function idOf(value: string, field: "payment" | "refund"): number {
  const digits = value.trim().replace(/^#/, "");
  if (/^\d{1,12}$/.test(digits) && Number(digits) > 0) return Number(digits);
  throw new ApiError(400, "invalid", words.idInvalid, { [field]: [words.idInvalid] });
}

/** Whether a line may be matched by hand now: not ours yet, the settlement not posted. The API checks again. */
export const matchable = (line: Pick<FinanceSettlementLine, "matched">, settlement: Pick<FinanceSettlement, "state">) =>
  !line.matched && settlement.state !== "posted";

export function MatchLine({
  settlement,
  line,
}: {
  settlement: Pick<FinanceSettlement, "id" | "state">;
  line: FinanceSettlementLine;
}) {
  const can = useCan();
  if (!can(P.reconcileSettlements) || !matchable(line, settlement)) return null;
  const target = line.type === "payment" ? "payment" : line.type === "refund" ? "refund" : null;
  return (
    <ConfirmDialog
      triggerLabel={
        <>
          {target ? words.match : words.accept}
          <span className="sr-only">: {line.entity_id}</span>
        </>
      }
      title={target ? words.matchTitle(line.entity_id) : words.acceptTitle(line.entity_id)}
      text={
        target === "payment" ? words.matchPaymentText : target === "refund" ? words.matchRefundText : words.acceptText
      }
      confirmLabel={target ? words.match : words.accept}
      confirmVariant="primary"
      fields={[
        ...(target ? [{ name: target, label: words.idLabel[target], help: words.idHelp(inr(line.amount)) }] : []),
        { name: "note", label: words.note, help: words.noteHelp },
      ]}
      success={target ? words.matched : words.accepted}
      onConfirm={({ values }) =>
        matchSettlementLine(settlement.id, {
          line: line.id,
          ...(target ? { [target]: idOf(values[target] ?? "", target) } : {}),
          accept: !target,
          note: values.note ?? "",
        })
      }
    />
  );
}

/** A line's own: the payment, the refund or the B2B link it is, or that it is not ours yet. */
function lineTarget(line: FinanceSettlementLine): React.ReactNode {
  if (line.payment) return words.paymentOf(line.payment.id, line.payment.order ?? "");
  if (line.refund) return words.refundOf(line.refund.id, line.refund.order ?? "");
  const link = line.link as { invoice?: string } | null;
  if (link?.invoice) return words.linkOf(link.invoice);
  return line.matched ? words.acceptedAsIs : words.notOurs;
}

export function LinesTable({
  settlement,
  rows,
  next,
  previous,
}: {
  settlement: Pick<FinanceSettlement, "id" | "state">;
  rows: FinanceSettlementLine[];
  next: string | null;
  previous: string | null;
}) {
  const c = words.lineColumns;
  const columns: Column<FinanceSettlementLine>[] = [
    { key: "entity", label: c.entity, render: (row) => <span className="font-mono text-[14px]">{row.entity_id}</span> },
    { key: "type", label: c.type, render: (row) => labelOf(words.lineTypes, row.type) },
    { key: "amount", label: c.amount, render: (row) => inr(row.amount), numeric: true },
    { key: "fee", label: c.fee, render: (row) => inr(row.fee), numeric: true },
    { key: "tax", label: c.tax, render: (row) => inr(row.tax), numeric: true, hidden: true },
    {
      key: "matched",
      label: c.matched,
      render: (row) => (
        <span className="inline-flex flex-col gap-0.5">
          <StatusChip tone={row.matched ? "done" : "bad"}>{row.matched ? words.ours : words.notOurs}</StatusChip>
          <span className="text-sm">{lineTarget(row)}</span>
        </span>
      ),
    },
    {
      key: "by",
      label: c.by,
      render: (row) => (row.matched ? row.matched_by || words.byId : copy.common.none),
      hidden: true,
    },
    { key: "note", label: c.note, render: (row) => row.note || copy.common.none, wrap: true, hidden: true },
    { key: "settled", label: c.settled, render: (row) => formatDateTime(row.settled_at), hidden: true },
    { key: "actions", label: c.actions, render: (row) => <MatchLine settlement={settlement} line={row} /> },
  ];
  return (
    <DataTable
      listKey="finance-settlement-lines"
      caption={words.lines}
      rows={rows}
      columns={columns}
      rowId={(row) => String(row.id)}
      next={next}
      previous={previous}
      presets={{
        name: "matched",
        label: words.whichLines,
        all: words.allLines,
        options: [{ value: "false", label: words.notOursLines }],
      }}
      filters={[
        {
          name: "type",
          label: c.type,
          type: "select",
          options: Object.entries(words.lineTypes).map(([value, label]) => ({ value, label })),
        },
      ]}
      empty={{ title: words.linesEmptyTitle, text: words.linesEmptyText }}
    />
  );
}
