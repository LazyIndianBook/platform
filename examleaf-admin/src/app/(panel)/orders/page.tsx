// /orders/: every order (GET orders/?tab=&status=&method=&q=…): the tabs and filters in the address, saved views,
// the bulk bar, and Space to look at one; the customer masked. A search for a person is recorded by the API.
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Problem } from "@/components/data/problem";
import { OrdersNav } from "@/components/modules/orders/orders-nav";
import { OrdersTable } from "@/components/modules/orders/orders-table";
import { PageHeader } from "@/components/shell/page-header";
import { buttonVariants } from "@/components/ui/button";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, type SearchParams, staffPage } from "@/lib/api/page";
import { listOrders, listSavedViews } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.orders.title };

const FILTERS = ["tab", "status", "method", "risk", "hold", "livemode", "shipping", "courier", "tag", "q"].concat([
  "created_from",
  "created_to",
  "cursor",
]);

export default async function OrdersPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/orders/", params));
  if (!has(manifest, P.ordersView)) notFound();
  const [page, views] = await Promise.all([
    attempt(listOrders(Object.fromEntries(FILTERS.map((name) => [name, param(params, name)])), transport), path),
    has(manifest, P.savedViewsView) ? attempt(listSavedViews("orders", transport), path) : null,
  ]);
  return (
    <>
      <PageHeader
        title={copy.orders.title}
        lead={copy.orders.lead}
        actions={
          has(manifest, P.ordersAdd) ? (
            <Link href="/orders/new/" className={buttonVariants({ size: "sm" })}>
              {copy.orders.nav.new}
            </Link>
          ) : undefined
        }
      />
      <OrdersNav manifest={manifest} current="all" />
      {page instanceof ApiError ? (
        <Problem error={page} />
      ) : (
        <OrdersTable
          rows={page.results}
          next={page.next}
          previous={page.previous}
          views={views instanceof ApiError ? null : views}
        />
      )}
    </>
  );
}
