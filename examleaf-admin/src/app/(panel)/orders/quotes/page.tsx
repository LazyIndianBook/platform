// /orders/quotes/: the schools' and booksellers' quotation requests (GET orders/quotes/?status=).
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Problem } from "@/components/data/problem";
import { OrdersNav } from "@/components/modules/orders/orders-nav";
import { QuotesTable } from "@/components/modules/orders/quotes";
import { PageHeader } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, type SearchParams, staffPage } from "@/lib/api/page";
import { listQuotes } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.orders.quotes.title };

export default async function QuotesPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/orders/quotes/", params));
  if (!has(manifest, P.quotesView)) notFound();
  const page = await attempt(
    listQuotes({ status: param(params, "status"), cursor: param(params, "cursor") }, transport),
    path,
  );
  return (
    <>
      <PageHeader title={copy.orders.quotes.title} lead={copy.orders.quotes.lead} />
      <OrdersNav manifest={manifest} current="quotes" />
      {page instanceof ApiError ? (
        <Problem error={page} />
      ) : (
        <QuotesTable rows={page.results} next={page.next} previous={page.previous} />
      )}
    </>
  );
}
