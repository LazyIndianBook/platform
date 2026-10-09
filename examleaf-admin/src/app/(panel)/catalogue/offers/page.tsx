// /catalogue/offers/: the automatic offers (GET catalogue/offers/?q=&state=&scope=&combinable=&cursor=), each with
// its discount, scope, state and uses; a new one for whoever may make one (through offer.create).
import type { Metadata } from "next";
import Link from "next/link";

import { Problem } from "@/components/data/problem";
import { CatalogueTabs } from "@/components/modules/catalogue/tabs";
import { OffersTable } from "@/components/modules/catalogue/terms-tables";
import { PageHeader } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, type SearchParams, staffPage } from "@/lib/api/page";
import { listOffers, listSavedViews } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.catalogue.offersTitle };

export default async function OffersPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/catalogue/offers/", params));
  const filters = Object.fromEntries(
    ["q", "state", "scope", "combinable", "cursor"].map((name) => [name, param(params, name)]),
  );
  const [page, views] = await Promise.all([
    attempt(listOffers(filters, transport), path),
    has(manifest, P.savedViewsView) ? attempt(listSavedViews("catalogue-offers", transport), path) : null,
  ]);
  return (
    <>
      <PageHeader
        title={copy.catalogue.offersTitle}
        lead={copy.catalogue.offersLead}
        actions={
          has(manifest, P.offersAdd) ? (
            <Link href="/catalogue/offers/new/" className="inline-flex min-h-11 items-center font-semibold">
              {copy.catalogue.newOffer}
            </Link>
          ) : null
        }
      />
      <CatalogueTabs manifest={manifest} current="offers" />
      {page instanceof ApiError ? (
        <Problem error={page} />
      ) : (
        <OffersTable
          rows={page.results}
          next={page.next}
          previous={page.previous}
          views={views instanceof ApiError ? null : views}
        />
      )}
    </>
  );
}
