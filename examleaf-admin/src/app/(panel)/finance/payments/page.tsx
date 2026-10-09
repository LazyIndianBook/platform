// /finance/payments/: every payment, newest first (GET finance/payments/?status=&method=&stuck=&created_from=
// &created_to=&livemode=&q=&cursor=), each opening its own page; the test ones only when asked for.
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { FinanceTabs } from "@/components/modules/finance/finance-tabs";
import { PaymentsTable } from "@/components/modules/finance/payments";
import { PageHeader } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, type SearchParams, staffPage } from "@/lib/api/page";
import { listFinancePayments, listSavedViews } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.finance.paymentsTitle };

const FILTERS = ["status", "method", "stuck", "created_from", "created_to", "livemode", "q", "cursor"] as const;

export default async function PaymentsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/finance/payments/", params));
  const filters = Object.fromEntries(FILTERS.map((name) => [name, param(params, name)]));
  const [page, views] = await Promise.all([
    attempt(listFinancePayments(filters, transport), path),
    has(manifest, P.savedViewsView) ? attempt(listSavedViews("finance-payments", transport), path) : null,
  ]);
  return (
    <>
      <PageHeader title={copy.finance.paymentsTitle} lead={copy.finance.paymentsLead} />
      <FinanceTabs manifest={manifest} current="payments" />
      {page instanceof ApiError ? (
        <Problem error={page} />
      ) : (
        <PaymentsTable
          rows={page.results}
          next={page.next}
          previous={page.previous}
          views={views instanceof ApiError ? null : views}
        />
      )}
    </>
  );
}
