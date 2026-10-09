"use client";

// A customer's email address or mobile number as the API sends it, masked (r•••@example.com). Reveal asks why (the
// reason goes into the audit trail with the person's name), then calls the API's reveal, which logs it, may ask to
// confirm it's you, and is rate limited; the value shows for 60 seconds, then the mask comes back by itself. The one
// button is Reveal, then Hide now, so the dialog gives the focus back to it.
import { useEffect, useId, useState } from "react";

import { ErrorSummary } from "@/components/forms/error-summary";
import { fieldError, useAction } from "@/components/forms/use-action";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Textarea } from "@/components/ui/input";
import { copy } from "@/lib/copy";

export const REVEAL_SECONDS = 60;

type MaskedValueProps = {
  masked: string | null;
  /** What it is, in words: "email address". */
  what: string;
  /** Calls the API's reveal with the reason; answers the value. Left out: no Reveal (the manifest says no). */
  reveal?: (reason: string) => Promise<string>;
};

export function MaskedValue({ masked, what, reveal }: MaskedValueProps) {
  const id = useId();
  const [open, setOpen] = useState(false);
  // the value and the moment it hides again: counted from a deadline, so a tab asleep in the background (or a clock
  // that jumps) never shows it longer than 60 seconds
  const [revealed, setRevealed] = useState<{ value: string; until: number; now: number } | null>(null);
  const { run, busy, error, setError } = useAction();
  const shown = revealed !== null;
  const value = revealed?.value ?? null;
  const left = revealed ? Math.max(0, Math.ceil((revealed.until - revealed.now) / 1000)) : 0;

  useEffect(() => {
    if (!shown) return;
    const timer = setInterval(() => {
      const now = Date.now();
      setRevealed((current) => (current && now < current.until ? { ...current, now } : null));
    }, 1000);
    return () => clearInterval(timer);
  }, [shown]);
  const setValue = (next: string | null) => {
    const now = Date.now();
    setRevealed(next === null ? null : { value: next, until: now + REVEAL_SECONDS * 1000, now });
  };

  if (!masked) return <span className="text-muted-foreground">{copy.masked.none}</span>;

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
      <span aria-live="polite" className="font-mono text-[15px] font-medium">
        {shown ? value || copy.masked.none : masked}
      </span>
      <span className="text-sm text-muted-foreground">{shown ? copy.masked.hiddenIn(left) : null}</span>
      {reveal ? (
        <Button
          variant={shown ? "ghost" : "secondary"}
          size="sm"
          onClick={() => (shown ? setValue(null) : setOpen(true))}
        >
          {shown ? copy.masked.hide : copy.masked.reveal} <span className="sr-only">{what}</span>
        </Button>
      ) : null}
      {reveal ? (
        <Dialog
          open={open}
          onOpenChange={(next) => {
            setOpen(next);
            if (!next) setError(null);
          }}
        >
          <DialogContent>
            <DialogHeader>{copy.masked.revealTitle(what)}</DialogHeader>
            <form
              noValidate
              className="flex flex-col gap-3.5"
              onSubmit={async (event) => {
                event.preventDefault();
                const reason = String(new FormData(event.currentTarget).get("reason") ?? "").trim();
                let answer = "";
                const ok = await run(async () => {
                  answer = await reveal(reason);
                });
                if (!ok) return;
                setValue(answer);
                setOpen(false);
              }}
            >
              <DialogBody>
                <DialogDescription>{copy.masked.revealText}</DialogDescription>
              </DialogBody>
              <ErrorSummary error={error} idPrefix={`${id}-`} labels={{ reason: copy.common.reason }} />
              <Field
                id={`${id}-reason`}
                label={copy.common.reason}
                help={copy.common.reasonHelp}
                error={fieldError(error, "reason")}
              >
                <Textarea name="reason" rows={3} aria-required="true" />
              </Field>
              <DialogFooter>
                {/* a plain button, not the dialog's safe one: the dialog opens on the reason */}
                <Button variant="secondary" onClick={() => setOpen(false)}>
                  {copy.common.cancel}
                </Button>
                <Button type="submit" busy={busy}>
                  {copy.masked.revealButton}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      ) : null}
    </div>
  );
}
