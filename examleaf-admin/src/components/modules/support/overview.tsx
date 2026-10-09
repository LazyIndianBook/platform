// The top of /support/ (server components): the module's numbers over 30 days (GET support/summary/: what was received,
// the median first reply and resolution, what is open and past a deadline now, the deadlines missed; test orders and
// spam left out by the API) and the queue's tabs, links that keep the list's filters and start it from its first page.
import { cn } from "cn";
import Link from "next/link";

import type { SupportSummary } from "@/lib/api/staff";
import type { SearchParams } from "@/lib/api/page";
import { copy } from "@/lib/copy";
import { formatDuration, formatNumber } from "@/lib/format";

import { type Tab, TABS } from "./shared";

const hours = (value: number | null) => (value === null ? copy.support.noneYet : formatDuration(value * 3_600_000));
const sum = (counts: Record<string, number>) => Object.values(counts).reduce((total, count) => total + count, 0);

export function SupportNumbers({ summary }: { summary: SupportSummary }) {
  const items = [
    { label: copy.support.received, value: formatNumber(summary.received) },
    { label: copy.support.firstResponse, value: hours(summary.first_response_hours) },
    { label: copy.support.resolution, value: hours(summary.resolution_hours) },
    { label: copy.support.backlog, value: formatNumber(sum(summary.backlog)) },
    { label: copy.support.overdue, value: formatNumber(summary.overdue), alert: summary.overdue > 0 },
    { label: copy.support.breaches, value: formatNumber(sum(summary.breaches)), alert: sum(summary.breaches) > 0 },
  ];
  return (
    <section aria-labelledby="support-numbers" className="flex flex-col gap-3">
      <h2 id="support-numbers" className="m-0 font-head text-xl leading-tight">
        {copy.support.numbers}
      </h2>
      <dl className="m-0 grid grid-cols-2 gap-3 min-[700px]:grid-cols-3 min-[1100px]:grid-cols-6">
        {items.map((item) => (
          <div key={item.label} className="flex min-w-0 flex-col gap-1 border border-border bg-card px-4 py-3">
            <dt className="text-sm text-muted-foreground">{item.label}</dt>
            <dd className={cn("m-0 font-mono text-lg font-semibold", item.alert && "text-destructive")}>
              {item.value}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

/** The tab's address: the list's filters kept (status only in All), from the first page, outside any saved view. */
export function tabHref(tab: Tab, params: SearchParams): string {
  const search = new URLSearchParams();
  for (const name of ["q", "category", "priority", "source", "test", ...(tab === "all" ? ["status"] : [])]) {
    const value = params[name];
    const first = Array.isArray(value) ? value[0] : value;
    if (first) search.set(name, first);
  }
  if (tab !== "due") search.set("tab", tab);
  const query = search.toString();
  return query ? `/support/?${query}` : "/support/";
}

export function QueueTabs({ current, params }: { current: Tab; params: SearchParams }) {
  return (
    <nav aria-label={copy.support.tabsLabel} className="overflow-x-auto border-b border-border">
      <ul className="m-0 flex list-none p-0">
        {TABS.map((tab) => (
          <li key={tab}>
            <Link
              href={tabHref(tab, params)}
              aria-current={tab === current ? "page" : undefined}
              className={cn(
                "inline-flex min-h-11 items-center px-4 text-[15px] font-semibold whitespace-nowrap text-muted-foreground no-underline hover:text-foreground",
                tab === current && "text-foreground shadow-[inset_0_-2px_0_var(--red-ink)]",
              )}
            >
              {copy.support.tabs[tab]}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
