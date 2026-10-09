// The reports' own places, as tabs under the page's head (links: each a page of its own), drawn by the manifest: a
// report opens for whoever holds the insights' permission and the permission of the data it reads (the sales lines,
// the book codes, the course's progress, cash on delivery), as the API asks for both. The API checks every call again.
import { cn } from "cn";
import Link from "next/link";

import type { Manifest } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export type ReportsTab = keyof typeof copy.reports.tabs;

const TABS: { key: ReportsTab; href: string; all: string[] }[] = [
  { key: "index", href: "/reports/", all: [P.insightsView] },
  { key: "sales", href: "/reports/sales/", all: [P.insightsView, P.orderItemsView] },
  { key: "place", href: "/reports/place/", all: [P.insightsView, P.orderItemsView] },
  { key: "codes", href: "/reports/codes/", all: [P.insightsView, P.bookCodesView] },
  { key: "health", href: "/reports/course-health/", all: [P.insightsView, P.progressView] },
  { key: "cod", href: "/reports/cod/", all: [P.insightsView, P.codView] },
  { key: "settlements", href: "/reports/settlements/", all: [P.insightsView] },
  { key: "cohorts", href: "/reports/cohorts/", all: [P.insightsView] },
  { key: "forecasts", href: "/reports/forecasts/", all: [P.insightsView] },
];

/** The tabs this manifest opens: those whose every permission it lists. */
export const reportsTabs = (manifest: Pick<Manifest, "permissions">) =>
  TABS.filter((tab) => tab.all.every((permission) => has(manifest, permission)));

/** Whether the manifest opens this report's page (else the page is a 404). */
export const opens = (manifest: Pick<Manifest, "permissions">, tab: ReportsTab) =>
  reportsTabs(manifest).some((each) => each.key === tab);

export function ReportsTabs({ manifest, current }: { manifest: Pick<Manifest, "permissions">; current: ReportsTab }) {
  return (
    <nav aria-label={copy.reports.tabsLabel} className="-mt-3 mb-6 overflow-x-auto border-b border-border">
      <ul className="m-0 flex list-none p-0">
        {reportsTabs(manifest).map((tab) => (
          <li key={tab.key}>
            <Link
              href={tab.href}
              aria-current={tab.key === current ? "page" : undefined}
              className={cn(
                "inline-flex min-h-11 items-center px-4 text-[15px] font-semibold whitespace-nowrap text-muted-foreground no-underline hover:text-foreground",
                tab.key === current && "text-foreground shadow-[inset_0_-2px_0_var(--red-ink)]",
              )}
            >
              {copy.reports.tabs[tab.key]}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
