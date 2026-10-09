// /catalogue/products/: every product with its chips (GET catalogue/products/?q=&kind=&published=&stock=&tax_problem=
// &incomplete=&category=&collection=&cursor=): the GST that disagrees with the master, what the courier lacks, the
// stock; saved views as tabs; a new product for whoever may add one.
import type { Metadata } from "next";
import Link from "next/link";

import { Problem } from "@/components/data/problem";
import { ProductsTable } from "@/components/modules/catalogue/products";
import { CatalogueTabs } from "@/components/modules/catalogue/tabs";
import { PageHeader } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, type SearchParams, staffPage } from "@/lib/api/page";
import { listCatalogueProducts, listSavedViews } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.catalogue.productsTitle };

const NAMES = ["q", "kind", "published", "stock", "tax_problem", "incomplete", "category", "collection", "cursor"];

export default async function ProductsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/catalogue/products/", params));
  const filters = Object.fromEntries(NAMES.map((name) => [name, param(params, name)]));
  const [page, views] = await Promise.all([
    attempt(listCatalogueProducts(filters, transport), path),
    has(manifest, P.savedViewsView) ? attempt(listSavedViews("catalogue-products", transport), path) : null,
  ]);
  return (
    <>
      <PageHeader
        title={copy.catalogue.productsTitle}
        lead={copy.catalogue.productsLead}
        actions={
          has(manifest, P.productsAdd) ? (
            <Link href="/catalogue/products/new/" className="inline-flex min-h-11 items-center font-semibold">
              {copy.catalogue.newProduct}
            </Link>
          ) : null
        }
      />
      <CatalogueTabs manifest={manifest} current="products" />
      {page instanceof ApiError ? (
        <Problem error={page} />
      ) : (
        <ProductsTable
          rows={page.results}
          next={page.next}
          previous={page.previous}
          views={views instanceof ApiError ? null : views}
        />
      )}
    </>
  );
}
