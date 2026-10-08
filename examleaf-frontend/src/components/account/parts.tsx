// Small pieces the account pages share (Account artboard, Direction A: quiet, ruled, no stamps): the page heading with
// its quiet line on the right, a section's ruled heading, rows of label and value, the tier averages, the dashed empty
// box, the notice of an account that waits for a parent, and what a section shows when the API cannot answer.
import Link from "next/link";

import { Alert } from "@/components/ui/alert";
import { Badge, TIER_VARIANT } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { type EmptyArt, EmptyState } from "@/components/ui/empty-state";
import type { ApiError } from "@/lib/api/errors";
import { TIERS } from "@/lib/site";

/** A link that leads on ("Open My record →"): bold, 44 px tall. */
export const goLink = "inline-flex min-h-11 items-center gap-1.5 text-[15px] font-bold";

/** The design's empty box (States, "Empty states"): dashed, a serif title, a line and at most two ways on. `art` is
 *  still accepted for the old callers; the quiet pages draw no glyph. */
export function CompactEmpty({
  title,
  children,
  actions,
}: {
  art?: EmptyArt;
  title?: string;
  children: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-2 border-[1.5px] border-dashed border-[#c9c0ae] p-[18px] [&_p]:m-0">
      {title ? <p className="font-head text-xl leading-tight font-semibold">{title}</p> : null}
      <div className="flex flex-col gap-1 text-[15px] leading-normal text-ink/85">{children}</div>
      {actions ? <div className="flex flex-wrap gap-x-4 [&_a]:font-bold">{actions}</div> : null}
    </div>
  );
}

/** The page's title (serif, 48 px at most), a muted line under it and a quiet line on the right (the streak). */
export function PageHead({ title, lead, aside }: { title: string; lead?: React.ReactNode; aside?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
      <div className="flex min-w-0 flex-col gap-2 [&>*]:m-0">
        <h1 className="text-[clamp(34px,4vw,48px)] leading-none">{title}</h1>
        {lead ? <p className="text-base text-muted-foreground max-nav:text-sm">{lead}</p> : null}
      </div>
      {aside ? <p className="m-0 text-[15px] text-muted-foreground max-nav:text-[13px]">{aside}</p> : null}
    </div>
  );
}

/** A section's heading on a 1.5 px ink rule, with what belongs to it on the right (a link, the exam date). */
export function SectionHead({ id, title, children }: { id?: string; title: string; children?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-t-[1.5px] border-foreground pt-[18px]">
      <h2 id={id} className="m-0 text-2xl leading-[1.2] max-nav:text-[22px]">
        {title}
      </h2>
      {children}
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

/** The average for each tier as chips and figures (kept for callers outside the account's own pages). */
export function TierAverages({ averages }: { averages: Average[] }) {
  return (
    <ul
      aria-label="Average for each tier"
      className="m-0 grid list-none grid-cols-[repeat(auto-fit,minmax(min(160px,100%),1fr))] gap-3 p-0"
    >
      {averages.map(({ tier, count, average }) => (
        <li key={tier} className="flex flex-col items-start gap-1.5 border-t border-border pt-3">
          <Badge variant={TIER_VARIANT[tier]}>{TIERS[tier]}</Badge>
          <span className="font-mono text-2xl font-semibold text-red-ink tabular-nums">
            {average === null ? "—" : `${average}%`}
          </span>
          <span className="text-[15px] text-muted-foreground">
            {count ? `average of ${count} saved` : `No ${TIERS[tier]} paper saved yet`}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** "parent@example.com" → "p•••@example.com", a number → its last three digits: enough to recognise it on screen. */
export function maskContact(contact: string): string {
  const email = /^(.)[^@]*(@.+)$/.exec(contact);
  if (email) return `${email[1]}•••${email[2]}`;
  const digits = contact.replace(/\D/g, "");
  return digits.length > 3 ? `••••• ${digits.slice(-3)}` : contact;
}

/** While a parent's confirmation is awaited the API refuses what an account saves: say so before the student tries,
 *  and where the link goes again (Consent and your data, which can also change their address); `action` sends it
 *  from here instead. */
export function ConsentPending({
  what,
  contact,
  action,
}: {
  what: string;
  contact?: string;
  action?: React.ReactNode;
}) {
  return (
    <Alert variant="warning" title="Waiting for your parent">
      <p>
        {contact ? `We sent the consent link to ${maskContact(contact)}. ` : ""}Until they confirm your account, {what}.
      </p>
      <p className="flex flex-wrap items-center gap-x-4 font-bold">
        {action ?? <Link href="/account/privacy/#consent">Send the link again</Link>}
        <Link href="/account/privacy/#consent">
          {contact && !contact.includes("@") ? "Change their number" : "Change their email"}
        </Link>
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
