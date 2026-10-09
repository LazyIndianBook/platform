"use client";

// A frequent action that is easy to take back is sent after 5 seconds with Undo in the meantime (research, admin UX
// 6.4: undo for the frequent and reversible, a confirmation for the rest), so the API needs no "unpack": the call is
// simply not made. `start(work)` begins the wait; Undo stops it; leaving the page sends it at once (what was asked is
// done, and the list read again shows the truth). Screen readers hear the start once, not each second.
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";

export const UNDO_SECONDS = 5;

type Pending = { left: number; message: string };

export function useUndo(seconds = UNDO_SECONDS) {
  const [pending, setPending] = useState<Pending | null>(null);
  const work = useRef<(() => void) | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const stop = () => {
    if (timer.current) clearInterval(timer.current);
    timer.current = null;
  };

  /** Runs `send` after the wait unless undone; `message` says what is about to happen. */
  const start = (message: string, send: () => void) => {
    stop();
    work.current?.(); // one waiting already: it goes now, the new one waits
    work.current = send;
    let left = seconds;
    setPending({ left, message });
    timer.current = setInterval(() => {
      left -= 1;
      if (left > 0) {
        setPending({ left, message });
        return;
      }
      stop();
      setPending(null);
      const due = work.current;
      work.current = null;
      due?.();
    }, 1000);
  };

  const undo = () => {
    stop();
    work.current = null;
    setPending(null);
  };

  // leaving the page: what waits is sent now rather than lost
  useEffect(
    () => () => {
      stop();
      const due = work.current;
      work.current = null;
      due?.();
    },
    [],
  );

  return { pending, start, undo };
}

export function UndoNotice({
  pending,
  undo,
  undoLabel,
}: {
  pending: Pending | null;
  undo: () => void;
  undoLabel: string;
}) {
  if (!pending) return null;
  return (
    <div className="flex flex-wrap items-center gap-3 border-l-[3px] border-primary bg-info-bg py-1.5 pr-1.5 pl-3">
      <p className="m-0 text-[15px]" role="status">
        {pending.message}{" "}
        <span aria-hidden="true" className="font-mono text-sm text-muted-foreground">
          ({pending.left})
        </span>
      </p>
      <Button size="sm" variant="secondary" onClick={undo}>
        {undoLabel}
      </Button>
    </div>
  );
}
