// A record's state as a chip, in the kit's order-status voice (badge.tsx): an outline while it waits or moves, filled
// once it got there, grey when it stopped, the error red when it failed. Always the words, never the colour alone.
import { cn } from "cn";

import { badgeVariants } from "@/components/ui/badge";

export type Tone = "waiting" | "moving" | "good" | "done" | "stopped" | "bad";

const VARIANT = {
  waiting: "awaiting",
  moving: "progress",
  good: "paid",
  done: "delivered",
  stopped: "closed",
  bad: "closed",
} as const;

/** The tone of the states the staff API sends; anything else is grey. */
const TONES: Record<string, Tone> = {
  pending: "waiting",
  received: "waiting",
  invited: "waiting",
  open: "waiting",
  snoozed: "stopped",
  acknowledged: "moving",
  in_progress: "moving",
  contained: "moving",
  approved: "good",
  active: "good",
  executed: "done",
  responded: "done",
  done: "done",
  closed: "stopped",
  expired: "stopped",
  revoked: "stopped",
  offboarded: "stopped",
  inactive: "stopped",
  erased: "stopped",
  rejected: "bad",
  failed: "bad",
  suspended: "bad",
  pending_deletion: "bad",
};

export function toneOf(state: string): Tone {
  return TONES[state] ?? "stopped";
}

export function StatusChip({
  tone,
  children,
  className,
}: {
  tone: Tone;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      data-slot="badge"
      data-tone={tone}
      className={cn(
        badgeVariants({ variant: VARIANT[tone] }),
        tone === "bad" && "border-destructive text-destructive",
        className,
      )}
    >
      {children}
    </span>
  );
}
