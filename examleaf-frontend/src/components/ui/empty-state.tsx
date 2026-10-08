// .empty, Direction A (Components board, 08; States, "Empty states"): a dashed sheet on paper with the marks-voice
// glyph "[ — ]" in red ink instead of a drawing, an optional eyebrow, the title in the serif (h1 on the 404, a 20 px
// h2 elsewhere), a line of text in 15 px and ONE action, with an optional text link after it. `art` is still accepted
// so every caller compiles; it picks the glyph, which is decorative.
import { cn } from "cn";
import * as React from "react";

export type EmptyArt = "sheet" | "cart" | "orders" | "attempts" | "results" | "missing";

const GLYPH: Record<EmptyArt, string> = {
  sheet: "[ — ]",
  cart: "[ 0 ]",
  orders: "[ № ]",
  attempts: "[ — ]",
  results: "[ 0 ]",
  missing: "[ ? ]",
};

function EmptyDrawing({ art }: { art: EmptyArt }) {
  return (
    <span aria-hidden="true" className="font-mono text-[28px] leading-none font-semibold text-red-ink">
      {GLYPH[art]}
    </span>
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
        "flex max-w-[760px] flex-col items-start gap-2.5 border-[1.5px] border-dashed border-[#c9c0ae] bg-transparent p-6 text-left [&>*]:m-0",
        className,
      )}
    >
      <EmptyDrawing art={art} />
      {eyebrow ? <p className="label-mono uppercase">{eyebrow}</p> : null}
      <Heading className={headingLevel === 1 ? "" : "text-xl leading-tight tracking-normal"}>{title}</Heading>
      {children ? (
        <div className="flex max-w-[34rem] flex-col gap-2 text-[15px] leading-[1.55] text-[#4a5060] [&>p]:m-0">
          {children}
        </div>
      ) : null}
      {action ? <div className="mt-1">{action}</div> : null}
      {after}
    </div>
  );
}

export { EmptyDrawing, EmptyState };
