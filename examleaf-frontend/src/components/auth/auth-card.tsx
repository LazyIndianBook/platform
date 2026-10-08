// The sign-in pages' frame (Auth, States and Phone boards of ExamLeaf A). Log in and Register are a Sheet: the margin
// glyph, the red double rule, the form, and a quiet aside that sits beside it from 1180 px (under it from 900 px).
// The narrow steps (a code, a new password, log out…) are the 560 px card the boards draw, centred under the header,
// with a margin glyph and a rule of their own. Under 900 px both are the form against the rule at the left edge.
import { cn } from "cn";

import { Sheet } from "@/components/ui/band";
import { safeNext } from "@/lib/auth/next-url";

/** Log in and Register. `wide`: the Register page, a form column and the 300 px aside; else the 480 px log-in column. */
export function AuthSheet({
  margin,
  aside,
  wide = false,
  children,
}: {
  margin: React.ReactNode;
  aside?: React.ReactNode;
  wide?: boolean;
  children: React.ReactNode;
}) {
  return (
    <Sheet
      margin={
        <span aria-hidden="true" className="mt-3 block">
          {margin}
        </span>
      }
      className="[&>.sheet-margin]:max-nav:hidden"
      bodyClassName="pt-14 pb-20 max-nav:pt-6 max-nav:pb-10"
    >
      <div
        className={cn(
          "grid items-start gap-y-10",
          wide
            ? "gap-x-14 min-[1180px]:grid-cols-[minmax(0,640px)_300px]"
            : "gap-x-[72px] min-[1180px]:grid-cols-[minmax(0,480px)_minmax(0,1fr)]",
        )}
      >
        <div className={cn("flex min-w-0 flex-col", wide ? "max-w-[640px] gap-5" : "max-w-[480px] gap-[18px]")}>
          {children}
        </div>
        {aside}
      </div>
    </Sheet>
  );
}

/** The aside of a sheet: a mono label and what follows, ruled off; `center`: centred beside the form, as the log-in
 *  board draws it (Register's sits at the top). Hidden on a phone unless `phone` (the log-in page's list is a pitch the
 *  phone boards leave out; Register's "What we keep" is the notice behind its consent). */
export function AuthAside({
  label,
  center = false,
  phone = false,
  children,
}: {
  label: string;
  center?: boolean;
  phone?: boolean;
  children: React.ReactNode;
}) {
  return (
    <aside
      className={cn(
        "flex min-w-0 flex-col gap-[18px] border-t border-border pt-8",
        "min-[1180px]:self-stretch min-[1180px]:border-t-0 min-[1180px]:border-l min-[1180px]:pt-0 min-[1180px]:pl-8",
        center && "min-[1180px]:justify-center min-[1180px]:pl-14",
        !phone && "max-nav:hidden",
      )}
    >
      <h2 className="label-mono uppercase">{label}</h2>
      {children}
    </aside>
  );
}

/** A narrow step: the 560 px card with its glyph in the margin and the double rule (under 900 px: the rule at the edge). */
export function AuthCard({ margin, children }: { margin: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="px-(--gutter) py-14 max-nav:p-0">
      <div className="mx-auto grid max-w-[560px] grid-cols-[64px_minmax(0,1fr)] max-nav:block max-nav:max-w-none max-nav:border-l-[3px] max-nav:border-double max-nav:border-red-ink">
        <span
          aria-hidden="true"
          className="pt-2 pl-6 font-mono text-sm leading-[1.4] font-semibold text-red-ink max-nav:hidden"
        >
          {margin}
        </span>
        <div className="flex min-w-0 flex-col gap-4 border-l-[3px] border-double border-red-ink pl-7 max-nav:border-l-0 max-nav:px-4 max-nav:pt-6 max-nav:pb-10">
          {children}
        </div>
      </div>
    </section>
  );
}

/** The page's h1: the 56 px title of Log in and Register (`page`), else the 36 px title of the narrow steps. */
export function AuthTitle({ page = false, className, ...props }: React.ComponentProps<"h1"> & { page?: boolean }) {
  return <h1 className={cn(!page && "text-h1-card leading-[1.05]", className)} {...props} />;
}

/** The sentence under a title: 16 px on the boards' ink-at-85% (15 px on a phone). */
export function Lead({ className, ...props }: React.ComponentProps<"p">) {
  return <p className={cn("m-0 text-base leading-[1.6] text-ink/85 max-nav:text-[15px]", className)} {...props} />;
}

/** Where the visitor goes after logging in, as the log-in board draws it: NEXT in red mono, then the path in mono.
 *  Never editable, and only for a path safeNext would send them to (not "/", the default). */
export function NextChip({ next }: { next: string | null | undefined }) {
  const path = safeNext(next, "");
  if (!path || path === "/") return null;
  return (
    <p className="m-0 flex items-baseline gap-2.5 bg-secondary px-3.5 py-3 text-[15px] leading-snug max-nav:px-3 max-nav:py-2.5 max-nav:text-sm">
      <span className="font-mono text-xs font-semibold text-red-ink max-nav:text-[11px]">NEXT</span>
      <span className="min-w-0">
        You&apos;ll go back to <code className="break-all">{path}</code>
      </span>
    </p>
  );
}

/** A button that reads as a link: "Send a new code", "Try Google again". */
export function LinkButton({ className, type = "button", ...props }: React.ComponentProps<"button">) {
  return (
    <button
      type={type}
      className={cn(
        "inline-flex min-h-11 cursor-pointer items-center font-semibold text-primary underline underline-offset-3 hover:text-red-ink disabled:cursor-not-allowed disabled:opacity-55",
        className,
      )}
      {...props}
    />
  );
}
