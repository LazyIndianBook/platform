// .badge, Direction A (Components board, 05): square chips (radius 3), Public Sans 700 13, 24 px tall. Tiers and
// subjects keep their colour and their words; "code" is a paper code in mono on a control hairline. Order statuses in
// the mono label voice, as the board lists them: an outline while the order moves (AWAITING PAYMENT gold, PAID green,
// PACKED blue), filled when it got there (SHIPPED blue, DELIVERED green), grey when it stopped (CANCELLED an outline,
// REFUNDED on paper 2). "stamp" is the one turned red-ink label of a screen; "gold" is the flat BEST VALUE chip of a
// choice card. Existing variants and exports unchanged; "refunded" is new.
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "cn";
import * as React from "react";

const STATUS = "border-[1.5px] bg-transparent px-2 py-1.5 font-mono text-xs font-semibold tracking-[0.04em] uppercase";

const badgeCva = cva(
  "inline-flex min-h-6 items-center gap-1.5 rounded-[3px] px-2.5 py-1 font-body text-[13px] leading-none font-bold whitespace-nowrap no-underline [&_svg]:size-3.5",
  {
    variants: {
      variant: {
        muted: "bg-muted text-muted-foreground",
        easy: "bg-easy text-white",
        medium: "bg-medium text-white",
        hard: "bg-hard text-white",
        gold: "min-h-0 border-[1.5px] border-red-ink bg-transparent px-1.5 font-mono text-[11px] font-semibold tracking-[0.04em] text-red-ink uppercase",
        stamp:
          "-rotate-[4deg] border-[1.5px] border-red-ink bg-transparent py-[7px] font-mono text-[13px] font-semibold tracking-[0.04em] text-red-ink uppercase",
        code: "border border-input bg-transparent px-2 py-1.5 font-mono text-[13px] font-medium text-foreground",
        physics: "subject-physics bg-(--base) text-white",
        chemistry: "subject-chemistry bg-(--base) text-white",
        maths: "subject-maths bg-(--base) text-white",
        biology: "subject-biology bg-(--base) text-white",
        awaiting: cn(STATUS, "border-[#c9a03a] text-gold-text"),
        paid: cn(STATUS, "border-easy text-easy"),
        progress: cn(STATUS, "border-medium text-medium"),
        shipped: cn(STATUS, "border-medium bg-medium text-white"),
        delivered: cn(STATUS, "border-easy bg-easy text-white"),
        closed: cn(STATUS, "border-input text-muted-foreground"),
        refunded: cn(STATUS, "border-input bg-paper-2 text-muted-foreground"),
      },
    },
    defaultVariants: { variant: "muted" },
  },
);

/** The chip's classes, merged (a variant's padding replaces the base's, the caller's classes win last). */
function badgeVariants({ className, ...variants }: VariantProps<typeof badgeCva> & { className?: string } = {}) {
  return cn(badgeCva(variants), className);
}

const TIER_VARIANT = { E: "easy", M: "medium", H: "hard" } as const;

/** The chip for an order's status (shop API Order.status); unknown statuses fall back to "closed". */
const STATUS_VARIANT: Record<string, VariantProps<typeof badgeCva>["variant"]> = {
  awaiting_payment: "awaiting",
  pending: "awaiting",
  paid: "paid",
  confirmed: "paid",
  packed: "progress",
  shipped: "shipped",
  delivered: "delivered",
  cancelled: "closed",
  refunded: "refunded",
};

function Badge({ className, variant, ...props }: React.ComponentProps<"span"> & VariantProps<typeof badgeCva>) {
  return <span data-slot="badge" className={cn(badgeVariants({ variant }), className)} {...props} />;
}

function BadgeLink({ className, variant, ...props }: React.ComponentProps<"a"> & VariantProps<typeof badgeCva>) {
  return (
    <a
      data-slot="badge"
      className={cn(badgeVariants({ variant }), "h-auto min-h-11 px-4 text-[15px] hover:underline", className)}
      {...props}
    />
  );
}

export { Badge, BadgeLink, badgeVariants, STATUS_VARIANT, TIER_VARIANT };
