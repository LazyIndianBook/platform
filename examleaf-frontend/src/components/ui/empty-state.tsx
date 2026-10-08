// .empty: a dashed card with a drawing (64 viewBox, 1.75 stroke, one marker-yellow highlight: the Django site's
// templates/_empty_art.html), an optional eyebrow, the title (h1 on the 404, h2 elsewhere), a line of text and ONE
// button, with an optional text link after it.
import { cn } from "cn";
import * as React from "react";

export type EmptyArt = "sheet" | "cart" | "orders" | "attempts" | "results" | "missing";

const ART: Record<EmptyArt, React.ReactNode> = {
  sheet: (
    <>
      <rect x="20" y="27.5" width="19" height="7" rx="1.5" fill="#FFE27A" stroke="none" />
      <path d="M15 6h24l11 11v41H15z" />
      <path d="M39 6v11h11M21 22h12M21 31h16M21 40h22M21 49h9" />
      <circle cx="43" cy="50" r="6" />
      <path d="M40.5 50l2 2 3.5-4" />
    </>
  ),
  cart: (
    <>
      <rect x="16" y="40" width="32" height="8" rx="1.5" fill="#FFE27A" stroke="none" />
      <path d="M12 22h40l-3 36H15z" />
      <path d="M24 22v-5a8 8 0 0 1 16 0v5" />
      <rect x="26" y="28" width="12" height="16" rx="1" strokeDasharray="3 3" />
    </>
  ),
  orders: (
    <>
      <ellipse cx="28" cy="60" rx="17" ry="2.5" fill="#FFE27A" stroke="none" />
      <path d="M8 32l20-9 20 9v20l-20 9-20-9z" />
      <path d="M8 32l20 9 20-9M28 41v20M18 27.5l20 9" />
      <path d="M52 22s-6-5.5-6-10a6 6 0 0 1 12 0c0 4.5-6 10-6 10z" />
      <circle cx="52" cy="12" r="2" />
      <path d="M52 26c0 5-3 8-9 9.5" strokeDasharray="2 4" />
    </>
  ),
  attempts: (
    <>
      <rect x="16" y="40" width="8" height="14" rx="1" fill="#FFE27A" stroke="none" />
      <path d="M10 8v46h46" />
      <path d="M20 54V40M32 54V32M44 54V24" strokeDasharray="2 4" />
      <path d="M40 26l14-14 5 5-14 14h-5z" />
      <path d="M50 16l5 5" />
    </>
  ),
  results: (
    <>
      <circle cx="46" cy="20" r="9" fill="#FFE27A" stroke="none" />
      <path d="M8 24h12a6 6 0 0 1 6 6v24a5 5 0 0 0-5-5H8zM44 30v19H31a5 5 0 0 0-5 5V30a6 6 0 0 1 6-6h3" />
      <circle cx="46" cy="20" r="9" />
      <path d="M52.5 26.5l7 7" />
    </>
  ),
  missing: (
    <>
      <rect x="22" y="27" width="22" height="9" rx="1.5" fill="#FFE27A" stroke="none" />
      <path d="M16 6h22l12 12v40H16z" />
      <path d="M38 6v12h12" />
      <path d="M27 30a6 6 0 1 1 8.5 5.4c-1.6.8-2.5 2-2.5 3.6v1.5M33 46.5v.01" />
    </>
  ),
};

function EmptyDrawing({ art }: { art: EmptyArt }) {
  return (
    <svg
      viewBox="0 0 64 64"
      width="64"
      height="64"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className="shrink-0 text-primary"
    >
      {ART[art]}
    </svg>
  );
}

type EmptyStateProps = {
  art?: EmptyArt;
  eyebrow?: string;
  title: string;
  headingLevel?: 1 | 2;
  children?: React.ReactNode;
  action?: React.ReactNode;
  after?: React.ReactNode;
  className?: string;
};

function EmptyState({
  art = "missing",
  eyebrow,
  title,
  headingLevel = 2,
  children,
  action,
  after,
  className,
}: EmptyStateProps) {
  const Heading = headingLevel === 1 ? "h1" : "h2";
  return (
    <div
      className={cn(
        "mx-auto flex max-w-[760px] flex-col items-center gap-3.5 rounded-lg border-2 border-dashed border-border bg-card px-6 py-12 text-center text-balance [&>*]:m-0",
        className,
      )}
    >
      <EmptyDrawing art={art} />
      {eyebrow ? <p className="text-[15px] font-semibold text-muted-foreground">{eyebrow}</p> : null}
      <Heading>{title}</Heading>
      {children ? (
        <div className="flex max-w-[34rem] flex-col gap-2 text-muted-foreground [&>p]:m-0">{children}</div>
      ) : null}
      {action ? <div className="mt-2">{action}</div> : null}
      {after}
    </div>
  );
}

export { EmptyDrawing, EmptyState };
