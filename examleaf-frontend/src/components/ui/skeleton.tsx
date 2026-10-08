// .skeleton, Direction A (Components board, 08: "LOADING · still placeholder, no shimmer"): a square block in paper 2
// that keeps the final size; it never moves (motion.md: no shimmer, no pulse) and is hidden from screen readers.
import { cn } from "cn";
import * as React from "react";

function Skeleton({ className, ...props }: React.ComponentProps<"span">) {
  return <span data-slot="skeleton" aria-hidden="true" className={cn("block h-3 bg-paper-2", className)} {...props} />;
}

export { Skeleton };
