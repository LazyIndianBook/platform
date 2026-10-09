// A customer's merged timeline (GET users/{id}/timeline/): one list, newest first, of what happened to the account,
// from orders and payments to the staff's own actions on it. Each row is `{at, kind, label, href}`; the label is
// numbers and codes in words, never an address or a number, and the href is the console's page for the thing. The API
// leaves out the parts the reader's role may not read (`withheld`) and, for a student under 18, shows the course as
// counts and never as a trail. Opening a timeline is a recorded read; the 200 newest rows come at once, the older ones
// by `before`.
import { cn } from "cn";
import Link from "next/link";

import type { CustomerTimeline, TimelineRow } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDateTime } from "@/lib/format";
import { Table, TableCell, TableHead } from "@/components/ui/table";

/** The kinds a timeline holds, in the API's order. */
export const TIMELINE_KINDS = Object.keys(copy.customers.timeline.kinds);

/** A row's link: the console's own path only (the API names pages of the console; anything else is no link). */
export const safeHref = (href: string | null | undefined) =>
  href && href.startsWith("/") && !href.startsWith("//") ? href : null;

/** The kinds a reader may narrow to: all but the withheld ones. */
export const shownKinds = (withheld: readonly string[]) => TIMELINE_KINDS.filter((kind) => !withheld.includes(kind));

/** The address of a timeline: its record, a kind and the older rows' cursor (`before`) in the query. */
export function timelineHref(id: number, query: { kind?: string; before?: string | null } = {}): string {
  const search = new URLSearchParams();
  if (query.kind) search.set("kind", query.kind);
  if (query.before) search.set("before", query.before);
  const text = search.toString();
  return `/users/${id}/timeline/${text ? `?${text}` : ""}`;
}

export function TimelineRows({ rows, caption }: { rows: TimelineRow[]; caption?: string }) {
  const words = copy.customers.timeline;
  return (
    <Table caption={caption ?? words.region}>
      <thead>
        <tr>
          <TableHead>{words.columns.when}</TableHead>
          <TableHead>{words.columns.kind}</TableHead>
          <TableHead>{words.columns.what}</TableHead>
        </tr>
      </thead>
      <tbody>
        {rows.map((row, index) => {
          const href = safeHref(row.href);
          return (
            <tr key={`${row.at}-${row.kind}-${index}`}>
              <TableCell className="whitespace-nowrap">
                <time dateTime={row.at}>{formatDateTime(row.at)}</time>
              </TableCell>
              <TableCell className="whitespace-nowrap text-muted-foreground">
                {labelOf(words.kinds, row.kind)}
              </TableCell>
              <TableCell className="min-w-64">
                {href ? (
                  <Link href={href} className="font-semibold">
                    {row.label}
                  </Link>
                ) : (
                  row.label
                )}
              </TableCell>
            </tr>
          );
        })}
      </tbody>
    </Table>
  );
}

/** The links that narrow a timeline to one kind (and back to everything). */
export function TimelineKinds({ id, current, withheld }: { id: number; current: string; withheld: readonly string[] }) {
  const words = copy.customers.timeline;
  const options = [
    { value: "", label: words.everything },
    ...shownKinds(withheld).map((kind) => ({ value: kind, label: labelOf(words.kinds, kind) })),
  ];
  return (
    <nav aria-label={words.show} className="overflow-x-auto border-b border-border">
      <ul className="m-0 flex list-none p-0">
        {options.map((option) => (
          <li key={option.value || "all"}>
            <Link
              href={timelineHref(id, { kind: option.value })}
              aria-current={current === option.value ? "page" : undefined}
              className={cn(
                "inline-flex min-h-11 items-center px-3.5 text-[15px] font-semibold whitespace-nowrap text-muted-foreground no-underline hover:text-foreground",
                current === option.value && "text-foreground shadow-[inset_0_-2px_0_var(--red-ink)]",
              )}
            >
              {option.label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}

/** What the reader's role leaves out, in words ("Orders, Payments"); null when nothing is left out. */
export function withheldWords(timeline: Pick<CustomerTimeline, "withheld">): string | null {
  const kinds = TIMELINE_KINDS.filter((kind) => timeline.withheld.includes(kind));
  return kinds.length
    ? copy.customers.timeline.withheld(kinds.map((kind) => labelOf(copy.customers.timeline.kinds, kind)).join(", "))
    : null;
}
