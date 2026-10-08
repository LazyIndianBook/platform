// Small pieces the account pages share (Account artboard; Django's account.css): the page heading, rows of label and
// value (.dl-rows), the tier averages (.tier-avgs), the notice of an account that waits for a parent, and what a card
// shows when the API cannot answer.
import Link from "next/link";

import { Alert } from "@/components/ui/alert";
import { Badge, TIER_VARIANT } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { type EmptyArt, EmptyDrawing, EmptyState } from "@/components/ui/empty-state";
import type { ApiError } from "@/lib/api/errors";
import { TIERS } from "@/lib/site";

/** A card's own empty state: the drawing beside a line of text, in a dashed box (My account, Learning). */
export function CompactEmpty({ art, children }: { art: EmptyArt; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-4 rounded-lg border-2 border-dashed border-border p-4 text-muted-foreground [&_p]:m-0">
      <EmptyDrawing art={art} />
      <div>{children}</div>
    </div>
  );
}

export function PageHead({ title, lead }: { title: string; lead?: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5 [&>*]:m-0">
      <h1>{title}</h1>
      {lead ? <p className="text-muted-foreground">{lead}</p> : null}
    </div>
  );
}

export function Rows({ children }: { children: React.ReactNode }) {
  return <dl className="m-0 text-base leading-relaxed">{children}</dl>;
}

export function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[minmax(120px,200px)_1fr] gap-4 border-t border-border py-3 max-nav:grid-cols-1 max-nav:gap-0.5">
      <dt className="font-semibold text-muted-foreground">{label}</dt>
      <dd className="m-0 min-w-0 [overflow-wrap:anywhere] [&_a]:font-semibold">{children}</dd>
    </div>
  );
}

type Average = { tier: "E" | "M" | "H"; count: number; average: number | null };

/** The average for each tier: every tier on My account ("–" before a paper of it), only the saved ones on My record. */
export function TierAverages({ averages }: { averages: Average[] }) {
  return (
    <ul
      aria-label="Average for each tier"
      className="m-0 grid list-none grid-cols-[repeat(auto-fit,minmax(min(160px,100%),1fr))] gap-3 p-0"
    >
      {averages.map(({ tier, count, average }) => (
        <li key={tier} className="flex flex-col items-start gap-1.5 rounded-lg border border-border bg-background p-4">
          <Badge variant={TIER_VARIANT[tier]}>{TIERS[tier]}</Badge>
          <span className="font-head text-[30px] leading-[1.1] font-extrabold text-primary tabular-nums">
            {average === null ? "–" : `${average}%`}
          </span>
          <span className="text-[15px] text-muted-foreground">
            {count ? `average of ${count} paper${count === 1 ? "" : "s"}` : `No ${TIERS[tier]} paper saved yet`}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** While a parent's confirmation is awaited the API refuses what an account saves: say so before the student tries. */
export function ConsentPending({ what }: { what: string }) {
  return (
    <Alert variant="warning" title="Waiting for your parent's or guardian's consent">
      <p>
        Until they confirm your account, {what}. <Link href="/account/privacy/">Send them the link again</Link>.
      </p>
    </Alert>
  );
}

/** A call that failed: the unavailable state when the server could not answer, else the API's own reason. */
export function Problem({ error, what, retry }: { error: ApiError; what: string; retry: string }) {
  if (!error.unavailable) {
    return (
      <Alert variant="warning" title={`${what} cannot be shown`}>
        <p>{error.message}</p>
      </Alert>
    );
  }
  return (
    <EmptyState
      art="missing"
      title="ExamLeaf cannot be reached just now"
      action={
        <Link href={retry} className={buttonVariants({ variant: "primary" })}>
          Try again
        </Link>
      }
    >
      <p>{what} needs our server, which is not answering. Please try again in a minute.</p>
    </EmptyState>
  );
}
