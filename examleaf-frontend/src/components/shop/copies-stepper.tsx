"use client";

// Copies of a book, Direction A (Product and Cart artboards): − / the number in mono / + in one box with hairlines
// between, 44 px a cell (52 px tall on the product page: `tall`). The buttons report a step, typing reports the text
// as it is; the owner decides when to send it (copies() in shop.ts reads it). While a step is sent (busy) or at a
// limit the buttons are aria-disabled and ignore presses, never disabled: the pressed button keeps the keyboard focus
// for the next press (accessibility review F1).
import { cn } from "cn";
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
  /** the product page's 52 px box */
  tall?: boolean;
};

const cell = "min-h-0 rounded-none border-0 bg-transparent px-0 text-foreground hover:bg-secondary-hover";

export function CopiesStepper({
  value,
  onValue,
  min = 1,
  max = MAX_COPIES,
  label,
  disabled,
  busy,
  tall = false,
  className,
  ...input
}: Props) {
  const count = copies(value, max) ?? min;
  const step = (to: number, allowed: boolean) => (allowed && !busy ? () => onValue(String(to), "step") : undefined);
  const height = tall ? "h-12 nav:h-[52px]" : "h-11";
  return (
    <div
      className={cn(
        "inline-flex shrink-0 items-stretch rounded-[4px] border-[1.5px] border-input bg-card has-aria-invalid:border-destructive",
        disabled && "bg-muted",
      )}
    >
      <Button
        type="button"
        variant="secondary"
        size="icon"
        aria-label={`One copy fewer of ${label}`}
        disabled={disabled}
        aria-disabled={busy || count <= min || undefined}
        onClick={step(count - 1, count > min)}
        className={cn(cell, height, "rounded-l-[3px] border-r border-border", tall ? "w-11 nav:w-12" : "w-11")}
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
        className={cn(
          "min-h-0 rounded-none border-0 bg-transparent px-1 text-center font-mono text-base font-medium tabular-nums hover:not-disabled:not-focus:border-0",
          "[appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none",
          height,
          tall ? "w-10 nav:w-[52px]" : "w-11",
          className,
        )}
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
        className={cn(cell, height, "rounded-r-[3px] border-l border-border", tall ? "w-11 nav:w-12" : "w-11")}
      >
        <Plus aria-hidden="true" />
      </Button>
    </div>
  );
}
