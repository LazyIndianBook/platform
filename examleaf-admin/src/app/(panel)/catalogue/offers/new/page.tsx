// /catalogue/offers/new/: a new automatic offer (POST catalogue/offers/, through offer.create: beyond your discount
// limit it waits for FINANCE; the dark-pattern guardrails are the API's), the shelves and collections from GET
// catalogue/options/; for whoever may make one.
import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { Problem } from "@/components/data/problem";
import { OfferForm } from "@/components/modules/catalogue/terms";
import { PageHeader } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, staffPage } from "@/lib/api/page";
import { getCatalogueOptions } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.catalogue.newOffer };

export default async function NewOfferPage() {
  const { manifest, transport, path } = await staffPage("/catalogue/offers/new/");
  if (!has(manifest, P.offersAdd)) redirect("/catalogue/offers/");
  const options = await attempt(getCatalogueOptions(transport), path);
  return (
    <>
      <PageHeader
        title={copy.catalogue.newOffer}
        lead={copy.catalogue.newOfferLead}
        back={{ href: "/catalogue/offers/", label: copy.catalogue.offersTitle }}
      />
      {options instanceof ApiError ? <Problem error={options} /> : <OfferForm offer={null} options={options} />}
    </>
  );
}
