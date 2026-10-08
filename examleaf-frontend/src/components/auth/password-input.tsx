"use client";

// A password box with Show / Hide inside it, as the Password login and New password boards draw it: what was typed
// can be checked before it is sent. Field gives the control its id and aria-*, which land on the input.
import { cn } from "cn";
import { useState } from "react";

import { Input } from "@/components/ui/input";

export function PasswordInput({ className, ...props }: Omit<React.ComponentProps<"input">, "type">) {
  const [shown, setShown] = useState(false);
  return (
    <div className="relative">
      <Input
        type={shown ? "text" : "password"}
        autoCapitalize="off"
        autoCorrect="off"
        spellCheck={false}
        className={cn("pr-[72px]", className)}
        {...props}
      />
      <button
        type="button"
        aria-label={shown ? "Hide password" : "Show password"}
        onClick={() => setShown(!shown)}
        className="absolute inset-y-0 right-0 inline-flex min-w-[68px] cursor-pointer items-center justify-center rounded-r-lg px-3 text-sm font-semibold text-primary hover:text-red-ink"
      >
        {shown ? "Hide" : "Show"}
      </button>
    </div>
  );
}
