// The Catalogue module's own places, as tabs under the page's head (links: each a page of its own), drawn by the
// manifest: the overview, products, stock, coupons, offers, shipping rates, categories, collections, the import and
// export. The API checks every call again.
import { cn } from "cn";
import Link from "next/link";

import type { Manifest } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { hasAny, P } from "@/lib/modules";

export type CatalogueTab = keyof typeof copy.catalogue.tabs;

const TABS: { key: CatalogueTab; href: string; any: string[] }[] = [
  { key: "overview", href: "/catalogue/", any: [P.productsView] },
  { key: "products", href: "/catalogue/products/", any: [P.productsView] },
  { key: "stock", href: "/catalogue/stock/", any: [P.productsView] },
  { key: "coupons", href: "/catalogue/coupons/", any: [P.couponsView] },
  { key: "offers", href: "/catalogue/offers/", any: [P.offersView] },
  { key: "rates", href: "/catalogue/shipping-rates/", any: [P.ratesView] },
  { key: "categories", href: "/catalogue/categories/", any: [P.categoriesView] },
  { key: "collections", href: "/catalogue/collections/", any: [P.collectionsView] },
  { key: "import", href: "/catalogue/import/", any: [P.productsImport, P.productsExport] },
];

/** The tabs this manifest opens. */
export const catalogueTabs = (manifest: Pick<Manifest, "permissions">) =>
  TABS.filter((tab) => hasAny(manifest, tab.any));

export function CatalogueTabs({
  manifest,
  current,
}: {
  manifest: Pick<Manifest, "permissions">;
  current: CatalogueTab;
}) {
  return (
    <nav aria-label={copy.catalogue.tabsLabel} className="-mt-3 mb-6 overflow-x-auto border-b border-border">
      <ul className="m-0 flex list-none p-0">
        {catalogueTabs(manifest).map((tab) => (
          <li key={tab.key}>
            <Link
              href={tab.href}
              aria-current={tab.key === current ? "page" : undefined}
              className={cn(
                "inline-flex min-h-11 items-center px-4 text-[15px] font-semibold whitespace-nowrap text-muted-foreground no-underline hover:text-foreground",
                tab.key === current && "text-foreground shadow-[inset_0_-2px_0_var(--red-ink)]",
              )}
            >
              {copy.catalogue.tabs[tab.key]}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
