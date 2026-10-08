// .badge: 24 px pill, Poppins 700 12. Tiers and subjects carry their meaning in the words too, never colour alone.
// Subject chips use the subject base colour; inside a .qr-card they flip to the pill colour with base text.
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "cn";
import * as React from "react";

const badgeVariants = cva(
  "inline-flex h-6 items-center gap-1 rounded-pill px-2.5 font-head text-xs leading-none font-bold whitespace-nowrap no-underline [&_svg]:size-3.5",
  {
    variants: {
      variant: {
        muted: "bg-muted text-muted-foreground",
        easy: "bg-easy text-white",
        medium: "bg-medium text-white",
        hard: "bg-hard text-white",
        gold: "bg-gold text-[#1b2330]",
        code: "border border-[rgba(169,184,214,0.5)] bg-transparent text-night-muted",
        physics: "subject-physics bg-(--base) text-white [.qr-card_&]:bg-(--pill) [.qr-card_&]:text-(--base)",
        chemistry: "subject-chemistry bg-(--base) text-white [.qr-card_&]:bg-(--pill) [.qr-card_&]:text-(--base)",
        maths: "subject-maths bg-(--base) text-white [.qr-card_&]:bg-(--pill) [.qr-card_&]:text-(--base)",
        biology: "subject-biology bg-(--base) text-white [.qr-card_&]:bg-(--pill) [.qr-card_&]:text-(--base)",
      },
    },
    defaultVariants: { variant: "muted" },
  },
);

const TIER_VARIANT = { E: "easy", M: "medium", H: "hard" } as const;

function Badge({ className, variant, ...props }: React.ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return <span data-slot="badge" className={cn(badgeVariants({ variant }), className)} {...props} />;
}

/** A chip that is a link (min 44 px tall): "The other books". */
function BadgeLink({ className, variant, ...props }: React.ComponentProps<"a"> & VariantProps<typeof badgeVariants>) {
  return (
    <a
      data-slot="badge"
      className={cn(badgeVariants({ variant }), "h-auto min-h-11 px-4 text-[15px] hover:underline", className)}
      {...props}
    />
  );
}

export { Badge, BadgeLink, badgeVariants, TIER_VARIANT };
