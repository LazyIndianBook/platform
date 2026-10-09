// /orders/returns/: the returns asked for (GET orders/returns/), open ones first by the filter; each opens its record.
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Problem } from "@/components/data/problem";
import { OrdersNav } from "@/components/modules/orders/orders-nav";
import { ReturnsTable } from "@/components/modules/orders/returns-table";
import { PageHeader } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, type SearchParams, staffPage } from "@/lib/api/page";
import { listReturns } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.orders.returns.title };

export default async function ReturnsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/orders/returns/", params));
  if (!has(manifest, P.returnsView)) notFound();
  const page = await attempt(
    listReturns(
      Object.fromEntries(["status", "open", "reason", "order", "cursor"].map((name) => [name, param(params, name)])),
      transport,
    ),
    path,
  );
  return (
    <>
      <PageHeader title={copy.orders.returns.title} lead={copy.orders.returns.lead} />
      <OrdersNav manifest={manifest} current="returns" />
      {page instanceof ApiError ? (
        <Problem error={page} />
      ) : (
        <ReturnsTable rows={page.results} next={page.next} previous={page.previous} />
      )}
    </>
  );
}
