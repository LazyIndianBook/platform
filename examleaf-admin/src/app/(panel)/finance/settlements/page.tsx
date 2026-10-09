// /finance/settlements/: Razorpay's settlements, newest day first (GET finance/settlements/?state=&date_from=&date_to=
// &livemode=&q=&cursor=), each opening its own page; for FINANCE, a day fetched as a job (POST finance/settlements/
// fetch/): the nightly run fetches yesterday's on its own, this is for a day it missed or one Razorpay settled late.
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { FinanceTabs } from "@/components/modules/finance/finance-tabs";
import { FetchForm, SettlementsTable } from "@/components/modules/finance/settlements";
import { PageHeader, Section } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, requestTime, type SearchParams, staffPage } from "@/lib/api/page";
import { listSavedViews, listSettlements } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.finance.settlements.title };

const FILTERS = ["state", "date_from", "date_to", "livemode", "q", "cursor"] as const;

/** A moment's day in India, as a date input wants it. */
const dayOf = (moment: number) =>
  new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(moment));

export default async function SettlementsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/finance/settlements/", params));
  const filters = Object.fromEntries(FILTERS.map((name) => [name, param(params, name)]));
  const [page, views] = await Promise.all([
    attempt(listSettlements(filters, transport), path),
    has(manifest, P.savedViewsView) ? attempt(listSavedViews("finance-settlements", transport), path) : null,
  ]);
  const now = requestTime();
  return (
    <>
      <PageHeader title={copy.finance.settlements.title} lead={copy.finance.settlements.lead} />
      <FinanceTabs manifest={manifest} current="settlements" />
      <div className="flex flex-col gap-10">
        {page instanceof ApiError ? (
          <Problem error={page} />
        ) : (
          <SettlementsTable
            rows={page.results}
            next={page.next}
            previous={page.previous}
            views={views instanceof ApiError ? null : views}
          />
        )}
        {has(manifest, P.reconcileSettlements) ? (
          <Section id="fetch" title={copy.finance.settlements.fetchTitle} lead={copy.finance.settlements.fetchLead}>
            <FetchForm yesterday={dayOf(now - 86_400_000)} today={dayOf(now)} />
          </Section>
        ) : null}
      </div>
    </>
  );
}
