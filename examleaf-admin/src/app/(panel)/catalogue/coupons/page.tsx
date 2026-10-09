// /catalogue/coupons/: the coupons (GET catalogue/coupons/?q=&state=&kind=&single_use=&cursor=) with their discount,
// state, uses and single-use codes; a new one for whoever may make one (through coupon.create).
import type { Metadata } from "next";
import Link from "next/link";

import { Problem } from "@/components/data/problem";
import { CatalogueTabs } from "@/components/modules/catalogue/tabs";
import { CouponsTable } from "@/components/modules/catalogue/terms-tables";
import { PageHeader } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, type SearchParams, staffPage } from "@/lib/api/page";
import { listCoupons, listSavedViews } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.catalogue.couponsTitle };

export default async function CouponsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/catalogue/coupons/", params));
  const filters = Object.fromEntries(
    ["q", "state", "kind", "single_use", "cursor"].map((name) => [name, param(params, name)]),
  );
  const [page, views] = await Promise.all([
    attempt(listCoupons(filters, transport), path),
    has(manifest, P.savedViewsView) ? attempt(listSavedViews("catalogue-coupons", transport), path) : null,
  ]);
  return (
    <>
      <PageHeader
        title={copy.catalogue.couponsTitle}
        lead={copy.catalogue.couponsLead}
        actions={
          has(manifest, P.couponsAdd) ? (
            <Link href="/catalogue/coupons/new/" className="inline-flex min-h-11 items-center font-semibold">
              {copy.catalogue.newCoupon}
            </Link>
          ) : null
        }
      />
      <CatalogueTabs manifest={manifest} current="coupons" />
      {page instanceof ApiError ? (
        <Problem error={page} />
      ) : (
        <CouponsTable
          rows={page.results}
          next={page.next}
          previous={page.previous}
          views={views instanceof ApiError ? null : views}
        />
      )}
    </>
  );
}
