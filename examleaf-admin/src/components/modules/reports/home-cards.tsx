// Home's numbers (GET home/): the cards of the person's roles, each one figure with its words. A total (the money, the
// orders, the codes, the active learners) sits beside the period before it as a plain sentence, with no chart; a queue
// (what waits for someone) is the figure of this moment. Each card is a link to the list or report it counts, already
// filtered, with its definition on hover (a title) and, for a keyboard and a phone, "How this is counted" opened under
// it. "Data as of" says when the numbers were worked out; test data is said before the cards, and how many test orders
// were left out. A card that could not be worked out says so and still links to the list.
import Link from "next/link";

import { Problem } from "@/components/data/problem";
import { StatusChip } from "@/components/data/status-chip";
import { Alert } from "@/components/ui/alert";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/errors";
import { attempt } from "@/lib/api/page";
import { getHome, type Home, type HomeCard, type HomePeriod, type Transport } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { formatDateTime, formatTime } from "@/lib/format";

import { cardValue, comparisonWords, lastDays } from "./numbers";

const PERIODS: HomePeriod[] = ["today", "week", "month"];

export function NumberCard({ card }: { card: HomeCard }) {
  const words = copy.reports.home;
  const compare = comparisonWords(card);
  return (
    <li className="flex min-w-0">
      <Card className="w-full">
        <CardContent className="gap-2 p-5">
          <Link
            href={card.href}
            title={card.definition}
            className="flex flex-col gap-1.5 text-foreground no-underline hover:no-underline"
          >
            <span className="text-[15px] leading-snug font-semibold">{card.label}</span>
            <span className="numeral text-[32px]">{cardValue(card)}</span>
          </Link>
          {card.error ? <p className="text-sm font-semibold text-destructive">{card.error}</p> : null}
          {compare ? <p className="text-[15px]">{compare}</p> : null}
          <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
            <span>{card.period ? lastDays(card.period.days) : words.now}</span>
            {card.test_mode ? <StatusChip tone="waiting">{words.testChip}</StatusChip> : null}
          </p>
          <details>
            <summary className="min-h-11 cursor-pointer py-2.5 text-[15px] font-semibold">
              {words.howCounted}
              <span className="sr-only">: {card.label}</span>
            </summary>
            <p className="pb-2 text-[15px] leading-relaxed text-muted-foreground">{card.definition}</p>
            <p className="text-sm text-muted-foreground">{words.workedOut(formatTime(card.as_of))}</p>
          </details>
        </CardContent>
      </Card>
    </li>
  );
}

function CardList({ cards, label }: { cards: HomeCard[]; label: string }) {
  if (cards.length === 0) return null;
  return (
    <div className="flex flex-col gap-3">
      <h3 className="m-0 label-mono uppercase">{label}</h3>
      <ul className="m-0 grid list-none grid-cols-[repeat(auto-fill,minmax(15rem,1fr))] gap-4 p-0">
        {cards.map((card) => (
          <NumberCard key={card.key} card={card} />
        ))}
      </ul>
    </div>
  );
}

/** The cards as the API gave them: totals first, then what waits. */
export function HomeNumbers({ home }: { home: Home }) {
  const words = copy.reports.home;
  if (home.cards.length === 0) return null;
  return (
    <section aria-labelledby="home-numbers" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
        <div className="flex flex-col gap-1">
          <h2 id="home-numbers" className="m-0 font-head text-xl leading-tight tracking-normal">
            {words.title}
          </h2>
          <p className="m-0 text-[15px] text-muted-foreground">{copy.reports.asOf(formatDateTime(home.as_of))}</p>
        </div>
        {home.cards.some((card) => card.group === "measure") ? (
          <nav aria-label={words.periodLabel} className="flex flex-wrap gap-1.5">
            {PERIODS.map((key) => (
              <Link
                key={key}
                href={key === "week" ? "/" : `/?period=${key}`}
                aria-current={home.period.key === key ? "true" : undefined}
                className={
                  home.period.key === key
                    ? "inline-flex min-h-11 items-center rounded-md border-[1.5px] border-foreground bg-card px-3.5 text-[15px] font-semibold no-underline"
                    : "inline-flex min-h-11 items-center rounded-md border border-border px-3.5 text-[15px] no-underline hover:bg-secondary"
                }
              >
                {words.periods[key]}
              </Link>
            ))}
          </nav>
        ) : null}
      </div>
      {home.test_mode ? (
        <Alert variant="warning" title={copy.reports.testTitle}>
          <p>{copy.reports.testText}</p>
        </Alert>
      ) : null}
      {home.test_orders_left_out > 0 ? (
        <p className="m-0 text-[15px]">{words.testLeftOut(home.test_orders_left_out)}</p>
      ) : null}
      <CardList cards={home.cards.filter((card) => card.group === "measure")} label={words.totals} />
      <CardList cards={home.cards.filter((card) => card.group !== "measure")} label={words.waiting} />
    </section>
  );
}

/** The numbers, fetched on their own so that Home shows them as soon as they are ready (the page streams them). */
export async function HomeCards({
  transport,
  path,
  period,
}: {
  transport: Transport;
  path: string;
  period: HomePeriod | "";
}) {
  const home = await attempt(getHome(period, transport), path);
  if (home instanceof ApiError) return <Problem error={home} what={copy.reports.home.title} />;
  return <HomeNumbers home={home} />;
}

/** What stands in the cards' place while they load: their size, no motion. */
export function HomeCardsSkeleton() {
  return (
    <section aria-busy="true" className="flex flex-col gap-4">
      <p role="status" className="sr-only">
        {copy.reports.home.loading}
      </p>
      <Skeleton className="h-6 w-40" />
      <div className="grid grid-cols-[repeat(auto-fill,minmax(15rem,1fr))] gap-4" aria-hidden="true">
        {[0, 1, 2, 3].map((index) => (
          <Skeleton key={index} className="h-40 rounded-lg" />
        ))}
      </div>
    </section>
  );
}
