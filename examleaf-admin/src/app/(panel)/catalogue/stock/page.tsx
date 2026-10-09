// /catalogue/stock/: the books' copies, the fewest first (GET catalogue/stock/?q=&state=&published=&cursor=): the
// low-stock line, what orders hold (placed and not yet sent, or waiting to be paid; test orders left out on a live
// site), the back-in-stock requests. Each row opens its product's stock, where the copies are set by hand.
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { StockTable } from "@/components/modules/catalogue/products";
import { CatalogueTabs } from "@/components/modules/catalogue/tabs";
import { PageHeader } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, type SearchParams, staffPage } from "@/lib/api/page";
import { listCatalogueStock, listSavedViews } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.catalogue.stockTitle };

export default async function StockPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/catalogue/stock/", params));
  const filters = Object.fromEntries(["q", "state", "published", "cursor"].map((name) => [name, param(params, name)]));
  const [page, views] = await Promise.all([
    attempt(listCatalogueStock(filters, transport), path),
    has(manifest, P.savedViewsView) ? attempt(listSavedViews("catalogue-stock", transport), path) : null,
  ]);
  return (
    <>
      <PageHeader title={copy.catalogue.stockTitle} lead={copy.catalogue.stockLead} />
      <CatalogueTabs manifest={manifest} current="stock" />
      {page instanceof ApiError ? (
        <Problem error={page} />
      ) : (
        <StockTable
          rows={page.results}
          next={page.next}
          previous={page.previous}
          views={views instanceof ApiError ? null : views}
        />
      )}
    </>
  );
}
