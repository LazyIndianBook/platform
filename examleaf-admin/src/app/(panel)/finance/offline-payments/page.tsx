// /finance/offline-payments/: money received by bank transfer or UPI (GET finance/offline-payments/?state=&livemode=
// &q=&cursor=): recorded (each opens its order) or, `?state=waiting`, waiting for FINANCE's approval (each opens its
// change request, where FINANCE checks the UTR against the bank statement and approves).
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { FinanceTabs } from "@/components/modules/finance/finance-tabs";
import { RequestsTable } from "@/components/modules/finance/requests";
import { PageHeader } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, type SearchParams, staffPage } from "@/lib/api/page";
import { listOfflinePayments, listSavedViews } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.finance.offlineTitle };

const FILTERS = ["state", "livemode", "q", "cursor"] as const;

export default async function OfflinePaymentsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/finance/offline-payments/", params));
  const filters = Object.fromEntries(FILTERS.map((name) => [name, param(params, name)]));
  const [page, views] = await Promise.all([
    attempt(listOfflinePayments(filters, transport), path),
    has(manifest, P.savedViewsView) ? attempt(listSavedViews("finance-offline", transport), path) : null,
  ]);
  return (
    <>
      <PageHeader title={copy.finance.offlineTitle} lead={copy.finance.offlineLead} />
      <FinanceTabs manifest={manifest} current="offline" />
      {page instanceof ApiError ? (
        <Problem error={page} />
      ) : (
        <RequestsTable
          kind="offline"
          rows={page.results}
          next={page.next}
          previous={page.previous}
          views={views instanceof ApiError ? null : views}
        />
      )}
    </>
  );
}
