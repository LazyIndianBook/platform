// /catalogue/shipping-rates/: the delivery rates (GET catalogue/shipping-rates/), and a new one (POST) for whoever may
// add one; the states' names from GET catalogue/options/.
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { RateForm, RatesTable } from "@/components/modules/catalogue/rates";
import { CatalogueTabs } from "@/components/modules/catalogue/tabs";
import { PageHeader, Section } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, staffPage } from "@/lib/api/page";
import { getCatalogueOptions, listShippingRates } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.catalogue.ratesTitle };

export default async function RatesPage() {
  const { manifest, transport, path } = await staffPage("/catalogue/shipping-rates/");
  const [page, options] = await Promise.all([
    attempt(listShippingRates(transport), path),
    attempt(getCatalogueOptions(transport), path),
  ]);
  const states = options instanceof ApiError ? [] : options.states;
  return (
    <>
      <PageHeader title={copy.catalogue.ratesTitle} lead={copy.catalogue.ratesLead} />
      <CatalogueTabs manifest={manifest} current="rates" />
      <div className="flex flex-col gap-10">
        {page instanceof ApiError ? <Problem error={page} /> : <RatesTable rows={page.results} states={states} />}
        {has(manifest, P.ratesAdd) && !(options instanceof ApiError) ? (
          <Section id="new" title={copy.catalogue.newRate} lead={copy.catalogue.newRateLead}>
            <RateForm rate={null} states={states} />
          </Section>
        ) : null}
      </div>
    </>
  );
}
