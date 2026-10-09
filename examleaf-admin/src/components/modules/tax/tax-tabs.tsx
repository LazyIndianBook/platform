// The tax module's own places, as tabs under the page's head (links: each a page of its own), drawn by the manifest:
// the overview, the master, the documents and their series, the GSTR-1 export. The API checks every call again.
import { cn } from "cn";
import Link from "next/link";

import type { Manifest } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { hasAny, P } from "@/lib/modules";

export type TaxTab = keyof typeof copy.tax.tabs;

const TABS: { key: TaxTab; href: string; any: string[] }[] = [
  { key: "overview", href: "/tax/", any: [P.taxThresholdsView, P.taxDocumentsView] },
  { key: "hsn", href: "/tax/hsn/", any: [P.taxHsnView] },
  { key: "documents", href: "/tax/documents/", any: [P.taxDocumentsView] },
  { key: "series", href: "/tax/series/", any: [P.taxDocumentsView] },
  { key: "gstr1", href: "/tax/gstr1/", any: [P.taxGstr1] },
];

/** The tabs this manifest opens. */
export const taxTabs = (manifest: Pick<Manifest, "permissions">) => TABS.filter((tab) => hasAny(manifest, tab.any));

export function TaxTabs({ manifest, current }: { manifest: Pick<Manifest, "permissions">; current: TaxTab }) {
  return (
    <nav aria-label={copy.tax.tabsLabel} className="-mt-3 mb-6 overflow-x-auto border-b border-border">
      <ul className="m-0 flex list-none p-0">
        {taxTabs(manifest).map((tab) => (
          <li key={tab.key}>
            <Link
              href={tab.href}
              aria-current={tab.key === current ? "page" : undefined}
              className={cn(
                "inline-flex min-h-11 items-center px-4 text-[15px] font-semibold whitespace-nowrap text-muted-foreground no-underline hover:text-foreground",
                tab.key === current && "text-foreground shadow-[inset_0_-2px_0_var(--red-ink)]",
              )}
            >
              {copy.tax.tabs[tab.key]}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
