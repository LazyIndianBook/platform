// /catalogue/products/new/: a new product (POST catalogue/products/), the forms' choices from GET catalogue/options/;
// for whoever may add one (shop.add_product), the others are sent to the list.
import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { Problem } from "@/components/data/problem";
import { NewProductForm } from "@/components/modules/catalogue/new-product";
import { PageHeader } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, staffPage } from "@/lib/api/page";
import { getCatalogueOptions } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.catalogue.newProduct };

export default async function NewProductPage() {
  const { manifest, transport, path } = await staffPage("/catalogue/products/new/");
  if (!has(manifest, P.productsAdd)) redirect("/catalogue/products/");
  const options = await attempt(getCatalogueOptions(transport), path);
  return (
    <>
      <PageHeader
        title={copy.catalogue.newProduct}
        lead={copy.catalogue.newProductLead}
        back={{ href: "/catalogue/products/", label: copy.catalogue.productsTitle }}
      />
      {options instanceof ApiError ? <Problem error={options} /> : <NewProductForm options={options} />}
    </>
  );
}
