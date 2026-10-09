// /orders/packing/: packer mode (GET orders/packing/): the orders to pack, oldest first (a PACKER's scope: paid,
// packed, shipped and cash-on-delivery orders placed), not held, not test orders; mark packed with 5 s to undo, the
// packing slip and label of each, and the pick list of those chosen.
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Problem } from "@/components/data/problem";
import { OrdersNav } from "@/components/modules/orders/orders-nav";
import { PackingQueue } from "@/components/modules/orders/packing-queue";
import { PageHeader } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, type SearchParams, staffPage } from "@/lib/api/page";
import { listPacking } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.orders.packing.title };

export default async function PackingPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/orders/packing/", params));
  if (!has(manifest, P.ordersView)) notFound();
  const page = await attempt(listPacking({ cursor: param(params, "cursor") }, transport), path);
  return (
    <>
      <PageHeader title={copy.orders.packing.title} lead={copy.orders.packing.lead} />
      <OrdersNav manifest={manifest} current="packing" />
      {page instanceof ApiError ? (
        <Problem error={page} />
      ) : (
        <>
          <PackingQueue rows={page.results} />
          {page.next ? (
            <p className="mt-4">
              <Link href={`/orders/packing/?cursor=${encodeURIComponent(page.next)}`} className="font-semibold">
                {copy.table.next}
              </Link>
            </p>
          ) : null}
        </>
      )}
    </>
  );
}
