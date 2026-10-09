// /catalogue/collections/: hand-picked lists of products in their order (GET catalogue/collections/), each changed
// (for whoever may change them), and a new one (for whoever may add one).
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { CollectionsList, NewCollectionForm } from "@/components/modules/catalogue/categories";
import { CatalogueTabs } from "@/components/modules/catalogue/tabs";
import { PageHeader, Section } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, staffPage } from "@/lib/api/page";
import { listCollections } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.catalogue.collectionsTitle };

export default async function CollectionsPage() {
  const { manifest, transport, path } = await staffPage("/catalogue/collections/");
  const page = await attempt(listCollections(transport), path);
  return (
    <>
      <PageHeader title={copy.catalogue.collectionsTitle} lead={copy.catalogue.collectionsLead} />
      <CatalogueTabs manifest={manifest} current="collections" />
      <div className="flex max-w-[50rem] flex-col gap-10">
        {page instanceof ApiError ? (
          <Problem error={page} />
        ) : (
          <CollectionsList rows={page.results} canChange={has(manifest, P.collectionsChange)} />
        )}
        {has(manifest, P.collectionsAdd) ? (
          <Section id="new" title={copy.catalogue.newCollection}>
            <NewCollectionForm />
          </Section>
        ) : null}
      </div>
    </>
  );
}
