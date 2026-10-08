"use client";

// Copies of a book: − / the number / +, 44 px each (the cart's lines, the product's buy form). The buttons report a
// step, typing reports the text as it is; the owner decides when to send it (copies() in shop.ts reads it). While a
// step is sent (busy) or at a limit the buttons are aria-disabled and ignore presses, never disabled: the pressed
// button keeps the keyboard focus for the next press (accessibility review F1).
import { Minus, Plus } from "lucide-react";
import type * as React from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

import { copies, MAX_COPIES } from "./shop";

type Props = Omit<React.ComponentProps<"input">, "value" | "onChange"> & {
  value: string;
  onValue: (value: string, how: "step" | "type") => void;
  min?: number;
  max?: number;
  label: string;
  /** a step is being sent: presses wait, focus stays */
  busy?: boolean;
};

export function CopiesStepper({ value, onValue, min = 1, max = MAX_COPIES, label, disabled, busy, ...input }: Props) {
  const count = copies(value, max) ?? min;
  const step = (to: number, allowed: boolean) => (allowed && !busy ? () => onValue(String(to), "step") : undefined);
  return (
    <div className="inline-flex items-center gap-1">
      <Button
        type="button"
        variant="secondary"
        size="icon"
        aria-label={`One copy fewer of ${label}`}
        disabled={disabled}
        aria-disabled={busy || count <= min || undefined}
        onClick={step(count - 1, count > min)}
      >
        <Minus aria-hidden="true" />
      </Button>
      <Input
        type="number"
        inputMode="numeric"
        min={min}
        max={max}
        value={value}
        disabled={disabled}
        readOnly={busy}
        onChange={(event) => onValue(event.target.value, "type")}
        className="w-[4.5rem] px-2 text-center tabular-nums"
        {...input}
      />
      <Button
        type="button"
        variant="secondary"
        size="icon"
        aria-label={`One copy more of ${label}`}
        disabled={disabled}
        aria-disabled={busy || count >= max || undefined}
        onClick={step(count + 1, count < max)}
      >
        <Plus aria-hidden="true" />
      </Button>
    </div>
  );
}
