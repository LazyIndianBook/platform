// The Finance module's own places, as tabs under the page's head (links: each a page of its own), drawn by the
// manifest: today, payments, refunds, offline payments, payment links, settlements. The API checks every call again.
import { cn } from "cn";
import Link from "next/link";

import type { Manifest } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { hasAny, P } from "@/lib/modules";

export type FinanceTab = keyof typeof copy.finance.tabs;

const TABS: { key: FinanceTab; href: string; any: string[] }[] = [
  { key: "today", href: "/finance/", any: [P.paymentsView, P.codView] },
  { key: "payments", href: "/finance/payments/", any: [P.paymentsView] },
  { key: "refunds", href: "/finance/refunds/", any: [P.refundsView] },
  { key: "offline", href: "/finance/offline-payments/", any: [P.paymentsView] },
  { key: "links", href: "/finance/payment-links/", any: [P.paymentsView] },
  { key: "settlements", href: "/finance/settlements/", any: [P.settlementsView] },
];

/** The tabs this manifest opens. */
export const financeTabs = (manifest: Pick<Manifest, "permissions">) => TABS.filter((tab) => hasAny(manifest, tab.any));

export function FinanceTabs({ manifest, current }: { manifest: Pick<Manifest, "permissions">; current: FinanceTab }) {
  return (
    <nav aria-label={copy.finance.tabsLabel} className="-mt-3 mb-6 overflow-x-auto border-b border-border">
      <ul className="m-0 flex list-none p-0">
        {financeTabs(manifest).map((tab) => (
          <li key={tab.key}>
            <Link
              href={tab.href}
              aria-current={tab.key === current ? "page" : undefined}
              className={cn(
                "inline-flex min-h-11 items-center px-4 text-[15px] font-semibold whitespace-nowrap text-muted-foreground no-underline hover:text-foreground",
                tab.key === current && "text-foreground shadow-[inset_0_-2px_0_var(--red-ink)]",
              )}
            >
              {copy.finance.tabs[tab.key]}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
