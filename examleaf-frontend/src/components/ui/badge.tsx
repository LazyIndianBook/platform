// .badge, Direction A: square chips (radius 3), Public Sans 700 13. Tiers and subjects keep their colour and their
// words. New: order-status chips in the mono label voice (outline for in-progress states, filled for final ones),
// and "stamp" for the one red-ink label of a screen (BEST VALUE). Existing variants and exports unchanged.
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "cn";
import * as React from "react";

const badgeVariants = cva(
  "inline-flex min-h-6 items-center gap-1 rounded-[3px] px-2.5 py-1 font-body text-[13px] leading-none font-bold whitespace-nowrap no-underline [&_svg]:size-3.5",
  {
    variants: {
      variant: {
        muted: "bg-muted text-muted-foreground",
        easy: "bg-easy text-white",
        medium: "bg-medium text-white",
        hard: "bg-hard text-white",
        gold: "border-[1.5px] border-red-ink bg-transparent font-mono text-xs font-semibold tracking-[0.04em] text-red-ink uppercase",
        stamp:
          "-rotate-[4deg] border-[1.5px] border-red-ink bg-transparent font-mono text-xs font-semibold tracking-[0.04em] text-red-ink uppercase",
        code: "border border-input bg-transparent font-mono text-[13px] font-medium text-foreground",
        physics: "subject-physics bg-(--base) text-white",
        chemistry: "subject-chemistry bg-(--base) text-white",
        maths: "subject-maths bg-(--base) text-white",
        biology: "subject-biology bg-(--base) text-white",
        awaiting:
          "border-[1.5px] border-[#c9a03a] bg-transparent font-mono text-xs font-semibold tracking-[0.04em] text-gold-text uppercase",
        paid: "border-[1.5px] border-easy bg-transparent font-mono text-xs font-semibold tracking-[0.04em] text-easy uppercase",
        progress:
          "border-[1.5px] border-medium bg-transparent font-mono text-xs font-semibold tracking-[0.04em] text-medium uppercase",
        shipped: "bg-medium font-mono text-xs font-semibold tracking-[0.04em] text-white uppercase",
        delivered: "bg-easy font-mono text-xs font-semibold tracking-[0.04em] text-white uppercase",
        closed:
          "border-[1.5px] border-input bg-secondary font-mono text-xs font-semibold tracking-[0.04em] text-muted-foreground uppercase",
      },
    },
    defaultVariants: { variant: "muted" },
  },
);

const TIER_VARIANT = { E: "easy", M: "medium", H: "hard" } as const;

/** The chip for an order's status (shop API Order.status); unknown statuses fall back to "closed". */
const STATUS_VARIANT: Record<string, VariantProps<typeof badgeVariants>["variant"]> = {
  awaiting_payment: "awaiting",
  pending: "awaiting",
  paid: "paid",
  confirmed: "paid",
  packed: "progress",
  shipped: "shipped",
  delivered: "delivered",
  cancelled: "closed",
  refunded: "closed",
};

function Badge({ className, variant, ...props }: React.ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return <span data-slot="badge" className={cn(badgeVariants({ variant }), className)} {...props} />;
}

function BadgeLink({ className, variant, ...props }: React.ComponentProps<"a"> & VariantProps<typeof badgeVariants>) {
  return (
    <a
      data-slot="badge"
      className={cn(badgeVariants({ variant }), "h-auto min-h-11 px-4 text-[15px] hover:underline", className)}
      {...props}
    />
  );
}

export { Badge, BadgeLink, badgeVariants, STATUS_VARIANT, TIER_VARIANT };
