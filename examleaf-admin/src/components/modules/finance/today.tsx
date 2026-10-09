// Finance today (GET finance/today/): a line a duty, as the API counts it (test orders left out on the live site, each
// line only for whoever may see its records), each a link to where it is dealt with; an invoice's or credit note's
// copy in ERPNext; and the books' pages in ERPNext. Nothing is counted here.
import { ExternalLink } from "lucide-react";
import Link from "next/link";

import type { FinanceDocumentErp, FinanceToday, FinanceTodayRow } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDate, formatDateTime } from "@/lib/format";

import { inr } from "./format";

/** Where each line is dealt with: the console's page, filtered to it (none: its words only). */
export const TODAY_HREFS: Record<string, string> = {
  refunds_to_approve: "/finance/refunds/?state=waiting",
  bank_refunds: "/finance/refunds/?state=pending&method=bank",
  offline_to_approve: "/finance/offline-payments/?state=waiting",
  stuck_payments: "/finance/payments/?stuck=true",
  b2b_to_post: "/finance/payment-links/?kind=invoice&state=paid",
  settlement_lines: "/finance/settlements/?state=mismatched",
  settlements_mismatched: "/finance/settlements/?state=mismatched",
  cod_receivable: "/shipping/",
  cod_overdue: "/shipping/",
  cod_mismatched: "/shipping/",
  credit_notes_refused: "/inbox/?kind=credit_note_missing",
  sync_differences: "/system/sync/",
};

/** A line's words beside its name: how many wait (or that nothing does, or that it is not set up), the oldest, the
 *  amount. */
export function todayWords(row: FinanceTodayRow): string {
  if (!row.configured || row.count === null) return copy.finance.notConfigured;
  if (row.count === 0) return copy.finance.nothingWaits;
  const parts = [copy.finance.waiting(row.count)];
  if (row.amount !== null && Number(row.amount) !== 0) parts.push(inr(row.amount));
  if (row.oldest) parts.push(copy.finance.oldest(formatDate(row.oldest)));
  return parts.join(" · ");
}

export function TodayList({ today }: { today: FinanceToday }) {
  return (
    <div className="flex flex-col gap-3">
      {!today.livemode ? <p className="m-0 text-sm text-muted-foreground">{copy.finance.testKeys}</p> : null}
      <ul className="m-0 flex list-none flex-col p-0">
        {today.rows.map((row) => {
          const href = row.configured && row.count ? TODAY_HREFS[row.key] : undefined;
          const name = labelOf(copy.finance.today, row.key);
          return (
            <li
              key={row.key}
              data-waiting={row.count ? "" : undefined}
              className="grid gap-x-6 gap-y-1 border-b border-border py-3 min-[640px]:grid-cols-[minmax(14rem,22rem)_minmax(0,1fr)]"
            >
              {href ? (
                <Link href={href} className="inline-flex min-h-11 items-center font-semibold">
                  {name}
                </Link>
              ) : (
                <span className="inline-flex min-h-11 items-center font-semibold text-muted-foreground">{name}</span>
              )}
              <span className={row.count ? "self-center text-[15px]" : "self-center text-[15px] text-muted-foreground"}>
                {todayWords(row)}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/** A document's number as the API's path takes it: dashes for its slashes ("EL/2026-27/00123" → "EL-2026-27-00123"). */
export const documentKey = (number: string) => number.trim().replaceAll("/", "-");

/** ERPNext's copy of an invoice or credit note (GET finance/documents/{number}/erp/): its state in words, its name
 *  there, and the outbox rows that carried it. */
export function DocumentErpState({ document }: { document: FinanceDocumentErp }) {
  const words = copy.finance.documents;
  return (
    <div className="flex flex-col gap-3">
      <dl className="m-0 grid gap-x-8 gap-y-2 min-[640px]:grid-cols-[minmax(10rem,auto)_minmax(0,1fr)]">
        <dt className="text-sm font-semibold text-muted-foreground">{words.number}</dt>
        <dd className="m-0 font-mono">
          <Link href={`/tax/documents/${documentKey(document.number)}/`}>{document.number}</Link>
        </dd>
        <dt className="text-sm font-semibold text-muted-foreground">{words.state}</dt>
        <dd className="m-0">{labelOf(words.states, document.state)}</dd>
        <dt className="text-sm font-semibold text-muted-foreground">{words.inErp}</dt>
        <dd className="m-0">
          {document.name ? (
            <>
              {document.doctype} <span className="font-mono">{document.name}</span>
              {document.synced_at ? (
                <span className="text-muted-foreground"> · {formatDateTime(document.synced_at)}</span>
              ) : null}
            </>
          ) : (
            copy.common.none
          )}
        </dd>
      </dl>
      {document.outbox.length ? (
        <ul className="m-0 flex list-none flex-col gap-1 p-0 text-[15px]">
          {document.outbox.map((row, index) => (
            <li key={String(row.id ?? index)} className="flex flex-col">
              <span>
                {words.outboxRow(String(row.event ?? ""), labelOf(words.outboxStates, String(row.state ?? "")))}
              </span>
              {row.last_error ? <span className="text-sm text-muted-foreground">{String(row.last_error)}</span> : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/** The books' pages in ERPNext (its Desk under NEXT_PUBLIC_ERP_URL), in a new tab, said in words. */
export const ERP_PAGES: { key: keyof typeof copy.finance.erp; path: string }[] = [
  { key: "accounting", path: "/app/accounting" },
  { key: "payouts", path: "/app/payment-entry?payment_type=Pay" },
  { key: "purchases", path: "/app/purchase-invoice" },
  { key: "receivables", path: "/app/query-report/Accounts Receivable" },
  { key: "bank", path: "/app/bank-reconciliation-tool" },
  { key: "period", path: "/app/accounting-period" },
  { key: "msme", path: "/app/supplier" },
  { key: "accounts", path: "/app/account/view/tree" },
];

export function ErpLinks({ base }: { base: string }) {
  return (
    <ul className="m-0 grid list-none gap-x-8 gap-y-1 p-0 min-[640px]:grid-cols-2">
      {ERP_PAGES.map((page) => (
        <li key={page.key}>
          <a
            href={`${base}${encodeURI(page.path)}`}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex min-h-11 items-center gap-2 font-semibold"
          >
            {copy.finance.erp[page.key]}
            <span className="sr-only">
              {" "}
              ({copy.shell.erpOpens}, {copy.common.opensElsewhere})
            </span>
            <ExternalLink aria-hidden="true" className="size-4 text-muted-foreground" />
          </a>
        </li>
      ))}
    </ul>
  );
}
