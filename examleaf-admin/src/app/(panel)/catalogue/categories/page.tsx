// /catalogue/categories/: the shop's shelves as a tree (GET catalogue/categories/), each moved with what is under it
// or renamed (for whoever may change them), and a new shelf (for whoever may add one).
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { CategoryTree, NewCategoryForm } from "@/components/modules/catalogue/categories";
import { CatalogueTabs } from "@/components/modules/catalogue/tabs";
import { PageHeader, Section } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, staffPage } from "@/lib/api/page";
import { listCategories } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.catalogue.categoriesTitle };

export default async function CategoriesPage() {
  const { manifest, transport, path } = await staffPage("/catalogue/categories/");
  const tree = await attempt(listCategories(transport), path);
  return (
    <>
      <PageHeader title={copy.catalogue.categoriesTitle} lead={copy.catalogue.categoriesLead} />
      <CatalogueTabs manifest={manifest} current="categories" />
      <div className="flex max-w-[50rem] flex-col gap-10">
        {tree instanceof ApiError ? (
          <Problem error={tree} />
        ) : (
          <CategoryTree tree={tree} canChange={has(manifest, P.categoriesChange)} />
        )}
        {has(manifest, P.categoriesAdd) && !(tree instanceof ApiError) ? (
          <Section id="new" title={copy.catalogue.newShelf}>
            <NewCategoryForm tree={tree} />
          </Section>
        ) : null}
      </div>
    </>
  );
}
