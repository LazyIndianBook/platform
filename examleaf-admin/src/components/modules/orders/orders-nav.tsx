// The Orders module's own pages as a row of links under the header (the list, the packing queue, returns, quotes),
// each drawn for whoever the manifest lets use it; the current one is marked.
import { cn } from "cn";
import Link from "next/link";

import type { Manifest } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export type OrdersPage = "all" | "packing" | "returns" | "quotes";

const PAGES: { key: OrdersPage; href: string; permission: string }[] = [
  { key: "all", href: "/orders/", permission: P.ordersView },
  { key: "packing", href: "/orders/packing/", permission: P.packOrder },
  { key: "returns", href: "/orders/returns/", permission: P.returnsView },
  { key: "quotes", href: "/orders/quotes/", permission: P.quotesView },
];

export function OrdersNav({ manifest, current }: { manifest: Manifest; current: OrdersPage }) {
  const shown = PAGES.filter((page) => has(manifest, page.permission));
  if (shown.length < 2) return null;
  return (
    <nav aria-label={copy.orders.nav.label} className="-mt-3 mb-6 overflow-x-auto border-b border-border">
      <ul className="m-0 flex list-none p-0">
        {shown.map((page) => (
          <li key={page.key}>
            <Link
              href={page.href}
              aria-current={page.key === current ? "page" : undefined}
              className={cn(
                "inline-flex min-h-11 items-center px-4 text-[15px] font-semibold whitespace-nowrap text-muted-foreground no-underline hover:text-foreground",
                page.key === current && "text-foreground shadow-[inset_0_-2px_0_var(--red-ink)]",
              )}
            >
              {copy.orders.nav[page.key]}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
