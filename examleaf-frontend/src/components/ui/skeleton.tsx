// .skeleton: a still placeholder that keeps the final size (motion.md: no shimmer, no pulse).
import { cn } from "cn";
import * as React from "react";

function Skeleton({ className, ...props }: React.ComponentProps<"span">) {
  return (
    <span
      data-slot="skeleton"
      aria-hidden="true"
      className={cn("block h-3 rounded-sm bg-border", className)}
      {...props}
    />
  );
}

export { Skeleton };
