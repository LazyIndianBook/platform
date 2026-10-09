// /finance/payment-links/: payment links (GET finance/payment-links/?kind=&state=&livemode=&q=&cursor=): the staff
// orders' (sent to the customer by email) or, `?kind=invoice`, the B2B invoices' of ERPNext; each row's actions as its
// state allows. A new link, for whoever may change orders (POST finance/payment-links/).
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { FinanceTabs } from "@/components/modules/finance/finance-tabs";
import { LinksTable, NewLinkForm } from "@/components/modules/finance/links";
import { PageHeader, Section } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, type SearchParams, staffPage } from "@/lib/api/page";
import { listPaymentLinks, listSavedViews } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.finance.linksTitle };

const FILTERS = ["kind", "state", "livemode", "q", "cursor"] as const;

export default async function PaymentLinksPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/finance/payment-links/", params));
  const filters = Object.fromEntries(FILTERS.map((name) => [name, param(params, name)]));
  const [page, views] = await Promise.all([
    attempt(listPaymentLinks(filters, transport), path),
    has(manifest, P.savedViewsView) ? attempt(listSavedViews("finance-links", transport), path) : null,
  ]);
  return (
    <>
      <PageHeader title={copy.finance.linksTitle} lead={copy.finance.linksLead} />
      <FinanceTabs manifest={manifest} current="links" />
      <div className="flex flex-col gap-10">
        {page instanceof ApiError ? (
          <Problem error={page} />
        ) : (
          <LinksTable
            rows={page.results}
            next={page.next}
            previous={page.previous}
            views={views instanceof ApiError ? null : views}
          />
        )}
        {has(manifest, P.ordersChange) ? (
          <Section id="new-link" title={copy.finance.newLink} lead={copy.finance.newLinkLead}>
            <NewLinkForm />
          </Section>
        ) : null}
      </div>
    </>
  );
}
