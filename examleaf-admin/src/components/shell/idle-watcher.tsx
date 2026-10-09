"use client";

// The idle limit of staff sessions (the manifest's idle_timeout_s: 15 or 30 minutes by role) and their absolute end
// (absolute_expires_at, 8 hours from the log-in), both read from the manifest, never assumed. Activity is a key, a
// click, a tap or the wheel, in any tab of the console (the last one is shared through localStorage); while there is
// activity the server is told now and then (GET session/; never in the background, or an idle session would never
// end), so its own idle clock, which the backend enforces, stays in step. Two minutes before the end a dialog says
// when it happens and offers to stay (WCAG 2.2.1); at the end the console signs out and goes to sign-in, coming back
// here afterwards. What was typed into forms is kept as it was typed (useDraftForm), so nothing is lost by it.
import { useCallback, useEffect, useRef, useState } from "react";

import { signOut } from "@/components/shell/sign-out";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/dialog";
import { getSession } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { formatTime } from "@/lib/format";

export const ACTIVITY_KEY = "examleaf-admin:last-activity";
const WARN_MS = 120_000;
const PING_MS = 5 * 60_000;
const TICK_MS = 5_000;
const EVENTS = ["pointerdown", "keydown", "wheel", "touchstart"] as const;

/** When the warning shows and when the session ends, from the last activity (ms since 1970). */
export function idleDeadlines(lastActivity: number, idleSeconds: number) {
  const end = lastActivity + idleSeconds * 1000;
  return { warnAt: end - Math.min(WARN_MS, (idleSeconds * 1000) / 4), end };
}

function sharedActivity(): number {
  try {
    return Number(window.localStorage.getItem(ACTIVITY_KEY)) || 0;
  } catch {
    return 0;
  }
}

function shareActivity(at: number) {
  try {
    window.localStorage.setItem(ACTIVITY_KEY, String(at));
  } catch {
    // storage off: this tab keeps its own clock
  }
}

type Warning = { kind: "idle" | "end"; at: number } | null;

export function IdleWatcher({ idleSeconds, absoluteEnd }: { idleSeconds: number; absoluteEnd: string | null }) {
  const [warning, setWarning] = useState<Warning>(null);
  const last = useRef(0);
  const pinged = useRef(0);
  const leaving = useRef(false);

  const leave = useCallback((reason: "idle" | "expired") => {
    if (leaving.current) return;
    leaving.current = true;
    void signOut(reason, true);
  }, []);

  const touch = useCallback(() => {
    const now = Date.now();
    if (now - last.current < 1000) return;
    last.current = now;
    shareActivity(now);
    if (now - pinged.current > PING_MS) {
      pinged.current = now;
      getSession().catch(() => undefined); // a 401 here sends the person to sign in (the transport)
    }
  }, []);

  useEffect(() => {
    const now = Date.now();
    last.current = Math.max(now, sharedActivity());
    pinged.current = now;
    shareActivity(last.current);
    for (const name of EVENTS) window.addEventListener(name, touch, { passive: true, capture: true });
    const end = absoluteEnd ? Date.parse(absoluteEnd) : NaN;
    const tick = () => {
      const now = Date.now();
      const lastActivity = Math.max(last.current, sharedActivity());
      last.current = lastActivity;
      const idle = idleDeadlines(lastActivity, idleSeconds);
      if (now >= idle.end) return leave("idle");
      if (Number.isFinite(end) && now >= end) return leave("expired");
      if (Number.isFinite(end) && end - now <= WARN_MS && end <= idle.end) setWarning({ kind: "end", at: end });
      else if (now >= idle.warnAt)
        setWarning((shown) => (shown?.kind === "end" ? shown : { kind: "idle", at: idle.end }));
      else setWarning((shown) => (shown?.kind === "idle" ? null : shown));
    };
    const timer = setInterval(tick, TICK_MS);
    return () => {
      clearInterval(timer);
      for (const name of EVENTS) window.removeEventListener(name, touch, { capture: true });
    };
  }, [idleSeconds, absoluteEnd, leave, touch]);

  const stay = () => {
    pinged.current = 0; // tell the server at once
    last.current = 0;
    touch();
    setWarning(null);
  };

  return (
    <Dialog
      open={warning !== null}
      onOpenChange={(open) => {
        if (!open && warning?.kind === "idle") stay();
        else if (!open) setWarning(null);
      }}
    >
      <DialogContent role="alertdialog">
        <DialogHeader>{warning?.kind === "end" ? copy.idle.endTitle : copy.idle.warnTitle}</DialogHeader>
        <DialogBody>
          <DialogDescription>
            {warning
              ? warning.kind === "end"
                ? copy.idle.endText(formatTime(warning.at))
                : copy.idle.warnText(formatTime(warning.at))
              : null}
          </DialogDescription>
          <p>{copy.idle.keep}</p>
        </DialogBody>
        <DialogFooter>
          <Button
            variant="secondary"
            onClick={() => {
              if (leaving.current) return;
              leaving.current = true;
              void signOut("signed-out");
            }}
          >
            {copy.idle.signOutNow}
          </Button>
          <DialogClose asChild>
            <Button>{warning?.kind === "end" ? copy.common.close : copy.idle.stay}</Button>
          </DialogClose>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
