// My record's parts (Account artboard "Record", Gaps "Record filters", Phone "Phone record"), drawn from the API's
// answers without any state: the filters as links (a subject's tab, a tier's chip, Clear all), each saved attempt as
// a MarkedRow with its marks in the marks column, each tier's average as a row of its own after its papers, and the
// honest state of a filter that matches nothing.
import Link from "next/link";

import { MarkedRow } from "@/components/ui/band";
import type { components } from "@/lib/api/schema";
import { formatDate } from "@/lib/dates";
import { shortCode, TIERS, type TierCode } from "@/lib/site";

import { CompactEmpty } from "./parts";

type Attempt = components["schemas"]["Attempt"];
type TierAverage = components["schemas"]["TierAverage"];

export type RecordFilter = { subject?: number; tier?: TierCode };

/** My record's address for a filter (and a page). */
export function recordHref({ subject, tier }: RecordFilter, page = 1): string {
  const query = new URLSearchParams({
    ...(subject ? { subject: String(subject) } : {}),
    ...(tier ? { tier } : {}),
    ...(page > 1 ? { page: String(page) } : {}),
  }).toString();
  return query ? `/account/record/?${query}` : "/account/record/";
}

const SWATCH: Record<TierCode, string> = { E: "bg-easy", M: "bg-medium", H: "bg-hard" };
const ORDER: TierCode[] = ["E", "M", "H"];

/** The subjects as tabs (each with its count of saved marks), then the tiers as chips and Clear all: plain links. */
export function RecordFilters({
  filter,
  total,
  subjects,
}: {
  filter: RecordFilter;
  total: number;
  subjects: { id: number; name: string; count: number }[];
}) {
  const tab =
    "relative inline-flex min-h-11 flex-none items-center px-4 font-semibold whitespace-nowrap text-muted-foreground no-underline first:pl-0 hover:text-foreground hover:no-underline aria-[current=true]:text-foreground aria-[current=true]:shadow-[inset_0_-2px_0_var(--red-ink)] max-nav:border max-nav:border-input max-nav:px-3 max-nav:text-sm max-nav:first:pl-3 max-nav:aria-[current=true]:border-foreground max-nav:aria-[current=true]:bg-foreground max-nav:aria-[current=true]:text-background max-nav:aria-[current=true]:shadow-none";
  const chip =
    "inline-flex min-h-11 items-center gap-1.5 border px-3 text-sm font-semibold whitespace-nowrap text-foreground no-underline hover:no-underline";
  return (
    <div className="flex flex-col gap-3">
      <nav aria-label="Subjects">
        <ul className="m-0 flex list-none gap-1.5 overflow-x-auto border-border p-0 nav:gap-0 nav:border-b">
          {[{ id: 0, name: "All", count: total }, ...subjects].map((item) => (
            <li key={item.id} className="flex">
              <Link
                href={recordHref({ subject: item.id || undefined, tier: filter.tier })}
                aria-current={(filter.subject ?? 0) === item.id ? "true" : undefined}
                className={tab}
              >
                {item.name} · {item.count}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
      <nav aria-label="Tiers" className="flex flex-wrap items-center gap-2">
        {ORDER.map((tier) =>
          filter.tier === tier ? (
            <Link
              key={tier}
              href={recordHref({ subject: filter.subject })}
              aria-current="true"
              className={`${chip} border-[1.5px] border-foreground bg-card`}
            >
              {TIERS[tier]}
              <span aria-hidden="true">×</span>
              <span className="sr-only">: show every tier</span>
            </Link>
          ) : (
            <Link key={tier} href={recordHref({ ...filter, tier })} className={`${chip} border-border`}>
              <span className="sr-only">Show only </span>
              {TIERS[tier]}
            </Link>
          ),
        )}
        {filter.subject || filter.tier ? (
          <Link href="/account/record/" className="inline-flex min-h-11 items-center px-2 text-sm font-semibold">
            Clear all
          </Link>
        ) : null}
      </nav>
    </div>
  );
}

// the marks column: 17 px on a desktop; on a phone 72 px wide (59.5/70 fits), the figure right-aligned
const markColumn =
  "nav:[&>.mark]:text-[17px] max-nav:grid-cols-[minmax(0,1fr)_72px] max-nav:[&>.mark]:justify-self-end";

const minutes = (value: number | null | undefined) => (value ? ` · ${value} min` : "");

/** The attempts of this page grouped by tier (Easy first, oldest first within), each group closed by its average. */
export function RecordList({
  attempts,
  averages,
  short,
}: {
  attempts: Attempt[];
  averages: TierAverage[];
  /** A subject is chosen: "E-01" for "PHY-E01". */
  short: boolean;
}) {
  const groups = ORDER.map((tier) => ({
    tier,
    rows: attempts
      .filter((attempt) => attempt.tier === tier)
      .sort((a, b) => `${a.date}${a.created}`.localeCompare(`${b.date}${b.created}`)),
    average: averages.find((row) => row.tier === tier),
  })).filter((group) => group.rows.length);
  return (
    <div className="flex flex-col">
      <div
        aria-hidden="true"
        className="marked-row border-b-[1.5px] border-foreground pb-2.5 font-mono text-xs leading-none text-muted-foreground max-nav:hidden"
      >
        <span className="grid grid-cols-[100px_120px_minmax(0,1fr)_88px] gap-4">
          <span>PAPER</span>
          <span>TIER</span>
          <span>SAVED ON</span>
          <span />
        </span>
        <span className="justify-self-center">MARKS</span>
      </div>
      <ul
        aria-label="The marks you saved"
        className="m-0 list-none p-0 max-nav:border-t-[1.5px] max-nav:border-foreground"
      >
        {groups.map(({ tier, rows, average }) => (
          <li key={tier}>
            <ul aria-label={`${TIERS[tier]} papers`} className="m-0 list-none p-0">
              {rows.map((attempt) => (
                <li key={attempt.id} className="relative">
                  <MarkedRow
                    className={`items-center border-b border-border py-3.5 max-nav:min-h-12 max-nav:py-2.5 ${markColumn}`}
                    mark={`${Number(attempt.marks_obtained)}/${attempt.full_marks}`}
                    markLabel={`${Number(attempt.marks_obtained)} of ${attempt.full_marks} marks`}
                  >
                    <span className="grid grid-cols-[auto_minmax(0,1fr)] items-baseline gap-x-2.5 gap-y-1 nav:grid-cols-[100px_120px_minmax(0,1fr)_88px] nav:gap-x-4">
                      <span className="flex items-center gap-2.5 font-mono text-[15px] font-medium max-nav:text-sm">
                        <span aria-hidden="true" className={`size-2 flex-none nav:hidden ${SWATCH[tier]}`} />
                        {short ? shortCode(attempt.paper) : attempt.paper}
                      </span>
                      <span className="flex items-center gap-2 max-nav:sr-only">
                        <span aria-hidden="true" className={`size-2.5 flex-none ${SWATCH[tier]}`} />
                        {TIERS[tier]}
                      </span>
                      <span className="flex min-w-0 flex-col text-muted-foreground max-nav:text-[13px]">
                        <span>
                          {attempt.date ? formatDate(attempt.date) : ""}
                          <span className="max-nav:hidden">{minutes(attempt.time_taken_minutes)}</span>
                        </span>
                        {attempt.notes ? (
                          <span className="line-clamp-2 text-sm whitespace-pre-line text-ink/85 max-nav:hidden">
                            {attempt.notes}
                          </span>
                        ) : null}
                      </span>
                      {/* phones: the whole row is the link ("Tap a paper to edit or delete its marks") */}
                      <Link
                        href={`/account/record/${attempt.id}/edit/`}
                        className="inline-flex min-h-11 items-center text-[15px] font-semibold max-nav:absolute max-nav:inset-0 max-nav:min-h-0 max-nav:text-[0px]"
                      >
                        Edit<span className="sr-only"> {attempt.paper}</span>
                      </Link>
                    </span>
                  </MarkedRow>
                </li>
              ))}
            </ul>
            {average ? (
              <MarkedRow
                className={`items-center border-b border-foreground bg-paper-2 py-3 ${markColumn}`}
                mark={`${average.average}%`}
                markLabel={`average of ${average.count} saved`}
              >
                <span className="pl-1 text-[15px] font-semibold">{TIERS[tier]} average</span>
              </MarkedRow>
            ) : null}
          </li>
        ))}
      </ul>
      <p className="m-0 pt-3 text-[13px] text-muted-foreground nav:hidden">Tap a paper to edit or delete its marks.</p>
    </div>
  );
}

/** A filter that matches nothing says so (G10): what is missing, what else is saved, and the way back to all. */
export function RecordNoMatch({
  subject,
  tier,
  inSubject,
  total,
}: {
  subject?: string;
  tier?: TierCode;
  /** saved marks of the chosen subject (any tier) */
  inSubject: number;
  /** saved marks in all */
  total: number;
}) {
  const what = [tier && TIERS[tier], subject].filter(Boolean).join(" ");
  const other =
    subject && tier && inSubject
      ? `You have ${inSubject} other ${subject} paper${inSubject === 1 ? "" : "s"} saved.`
      : `You have ${total} other paper${total === 1 ? "" : "s"} saved.`;
  return (
    <CompactEmpty
      title="No papers match these filters"
      actions={<Link href="/account/record/">Clear the filters</Link>}
    >
      <p>
        You haven&apos;t saved {/^[AEIOU]/.test(what) ? "an" : "a"} {what} paper yet. {other}
      </p>
    </CompactEmpty>
  );
}
