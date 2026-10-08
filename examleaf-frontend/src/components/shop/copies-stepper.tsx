"use client";

// Copies of a book: − / the number / +, 44 px each (the cart's lines, the product's buy form). The buttons report a
// step, typing reports the text as it is; the owner decides when to send it (copies() in shop.ts reads it).
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
};

export function CopiesStepper({ value, onValue, min = 1, max = MAX_COPIES, label, disabled, ...input }: Props) {
  const count = copies(value, max) ?? min;
  return (
    <div className="inline-flex items-center gap-1">
      <Button
        type="button"
        variant="secondary"
        size="icon"
        aria-label={`One copy fewer of ${label}`}
        disabled={disabled || count <= min}
        onClick={() => onValue(String(count - 1), "step")}
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
        onChange={(event) => onValue(event.target.value, "type")}
        className="w-[4.5rem] px-2 text-center tabular-nums"
        {...input}
      />
      <Button
        type="button"
        variant="secondary"
        size="icon"
        aria-label={`One copy more of ${label}`}
        disabled={disabled || count >= max}
        onClick={() => onValue(String(count + 1), "step")}
      >
        <Plus aria-hidden="true" />
      </Button>
    </div>
  );
}
