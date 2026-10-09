// /finance/refunds/: refunds, newest first (GET finance/refunds/?state=&method=&livemode=&q=&cursor=), with their ARN,
// the bank transfer's UTR and the credit note; `?state=waiting`: the change requests of order.refund waiting for a
// second person (each opens its approval). Under the list, how long a refund takes to reach the customer: what staff
// tell a customer who asks.
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { FinanceTabs } from "@/components/modules/finance/finance-tabs";
import { RequestsTable } from "@/components/modules/finance/requests";
import { PageHeader, Section } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, type SearchParams, staffPage } from "@/lib/api/page";
import { listFinanceRefunds, listSavedViews } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.finance.refundsTitle };

const FILTERS = ["state", "method", "livemode", "q", "cursor"] as const;

export default async function RefundsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/finance/refunds/", params));
  const filters = Object.fromEntries(FILTERS.map((name) => [name, param(params, name)]));
  const [page, views] = await Promise.all([
    attempt(listFinanceRefunds(filters, transport), path),
    has(manifest, P.savedViewsView) ? attempt(listSavedViews("finance-refunds", transport), path) : null,
  ]);
  return (
    <>
      <PageHeader title={copy.finance.refundsTitle} lead={copy.finance.refundsLead} />
      <FinanceTabs manifest={manifest} current="refunds" />
      <div className="flex flex-col gap-10">
        {page instanceof ApiError ? (
          <Problem error={page} />
        ) : (
          <RequestsTable
            kind="refunds"
            rows={page.results}
            next={page.next}
            previous={page.previous}
            views={views instanceof ApiError ? null : views}
          />
        )}
        <Section id="timelines" title={copy.finance.timelinesTitle} lead={copy.finance.timelinesLead}>
          <dl className="m-0 grid max-w-[60rem] gap-x-8 gap-y-3 min-[640px]:grid-cols-[minmax(12rem,auto)_minmax(0,1fr)]">
            {copy.finance.timelines.map((row) => (
              <div key={row.how} className="contents">
                <dt className="text-[15px] font-semibold">{row.how}</dt>
                <dd className="m-0 text-[15px]">{row.when}</dd>
              </div>
            ))}
          </dl>
        </Section>
      </div>
    </>
  );
}
