"use client";

// A legal clock (acknowledge a data request within 48 hours, tell CERT-In within 6): the time left or how late it is,
// coloured by urgency and always in words (green while there is time, gold in the last quarter of its window, the
// error red once it is late), with the due time beside it. It starts from the server's `now`, so the first render is
// the server's, then moves on every half minute.
import { useEffect, useState } from "react";

import { StatusChip, type Tone } from "@/components/data/status-chip";
import { copy } from "@/lib/copy";
import { formatDateTime, remaining, urgency } from "@/lib/format";

const TONE = { ok: "good", soon: "waiting", overdue: "bad", done: "stopped" } as const satisfies Record<string, Tone>;

export function useNow(start: number, every = 30_000): number {
  const [now, setNow] = useState(start);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), every);
    return () => clearInterval(timer);
  }, [every]);
  return now;
}

type ClockProps = {
  label: string;
  start: string | null;
  due: string | null;
  /** When it was done (acknowledged, reported): the clock stops. */
  doneAt?: string | null;
  /** How the done time reads (props cross from server components, so a word, not a function). */
  doneAs?: "acknowledged" | "reported";
  now: number;
  compact?: boolean;
};

export function Clock({ label, start, due, doneAt, doneAs = "reported", now: initial, compact = false }: ClockProps) {
  const now = useNow(initial);
  if (doneAt) {
    return (
      <span className="inline-flex flex-wrap items-center gap-x-2 gap-y-1">
        {compact ? (
          <span className="sr-only">{label}: </span>
        ) : (
          <span className="text-sm text-muted-foreground">{label}</span>
        )}
        <span className="text-sm">{copy.privacy[doneAs](formatDateTime(doneAt))}</span>
      </span>
    );
  }
  if (!due) return <span className="text-sm text-muted-foreground">{copy.common.unknown}</span>;
  const state = urgency(start, due, now);
  return (
    <span className="inline-flex flex-wrap items-center gap-x-2 gap-y-1" data-urgency={state}>
      {compact ? (
        <span className="sr-only">{label}: </span>
      ) : (
        <span className="text-sm text-muted-foreground">{label}</span>
      )}
      <StatusChip tone={TONE[state]}>{remaining(due, now)}</StatusChip>
      {compact ? null : <span className="font-mono text-xs text-muted-foreground">{formatDateTime(due)}</span>}
    </span>
  );
}
